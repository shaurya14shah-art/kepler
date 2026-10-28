"""Benchmark Kepler's detection on real data with labelled anomalies: the Numenta Anomaly Benchmark (NAB).

It replays each series the way production sees it. The first 15% of a series, and at least 3 days, only trains the
model, like NAB's probationary period. After that, Kepler scores it bucket by bucket with a model retrained every 7
days on the past only.

- **Caught:** a labelled anomaly window counts as caught when an incident starts inside it.
- **False alarm:** an incident that starts outside every window.
- **Near the label:** caught by an incident that starts within 3 hours of the labelled moment (the window's centre).
  NAB's windows are 1.5 days wide, so a false alarm that happens to fall inside one also counts as caught: this is
  the stricter measure of real detections.
- **Lag:** the median time from the labelled moment to the first incident.

    cd backend && .venv/bin/python -I stress/bench_nab.py [--tier area|orbit|time|all] [--save]

BENCH_SET="module.CONSTANT=value;…" overrides engine constants for an ablation. --save writes
stress/bench_nab_baseline.json; later runs print the change against it, so a model change is kept only
if it catches more without more false alarms. Needs the NAB files in data/manual-test/nab/ (docs/manual-test.md).
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAB = HERE.parent / "data" / "manual-test" / "nab"
BASELINE = HERE / "bench_nab_baseline.json"
COMPANIES = ["AAPL", "AMZN", "GOOG", "FB", "IBM", "KO", "PFE", "UPS", "CVS", "CRM"]
# Counts (summed per bucket): file → alert direction. Tweets and requests spike; taxi demand moves both ways.
COUNTS = {**{f"Twitter_volume_{c}.csv": "up" for c in COMPANIES}, "elb_request_count_8c0756.csv": "up", "nyc_taxi.csv": "both"}


def _series() -> dict:
    """file → (alert direction, agg): the counts above, plus every other NAB file present, as gauges (CPU, latency,
    temperature, bytes, traffic speed, ad prices: averaged per bucket, alerting both ways)."""
    gauges = sorted(p.name for p in NAB.glob("*.csv") if p.name not in COUNTS) if NAB.exists() else []
    return {**{f: (bad, "sum") for f, bad in COUNTS.items()}, **{f: ("both", "mean") for f in gauges}}


SERIES = _series()
WEEK = 7 * 86400
HOLD_GAUGES = True  # a coarse gauge holds its value over its interval (False: one point per interval, gaps between)
NEAR = 3 * 3600  # 'near the label': an incident starting this close to the labelled moment


def _epoch(s: str) -> int:
    return int(datetime.fromisoformat(s[:19]).replace(tzinfo=timezone.utc).timestamp())


def run_one(filename: str, tier: str) -> dict:
    """One series, in a fresh process and database (the engine caches scored windows per metric id)."""
    os.environ["KEPLER_DB"] = os.path.join(tempfile.mkdtemp(prefix="nab-"), "bench.db")
    import ast
    import importlib
    # ablations: BENCH_SET="kepler.engine.seasonal.TAIL_MAX=1;kepler.engine.detector.RESOLVE_HOLD_MAX=3"
    for item in filter(None, os.environ.get("BENCH_SET", "").split(";")):
        target, value = item.split("=", 1)
        module, attr = target.strip().rsplit(".", 1)
        setattr(importlib.import_module(module), attr, ast.literal_eval(value.strip()))
    import csv
    import io

    from kepler import connectors, db
    from kepler.db import BUCKET
    from kepler.engine import detector

    db.DB_PATH = Path(os.environ["KEPLER_DB"])
    db.init_db()
    db.set_setting("demo_mode", "0")
    db.set_setting("model_tier", tier)
    for item in filter(None, os.environ.get("BENCH_SETTINGS", "").split(";")):  # e.g. BENCH_SETTINGS="min_change_pct=0"
        db.set_setting(*(x.strip() for x in item.split("=", 1)))
    bad, agg = SERIES[filename]
    with open(NAB / filename, newline="") as f:
        rows = [(_epoch(r["timestamp"]), float(r["value"])) for r in csv.DictReader(f)]
    gaps = sorted(b[0] - a[0] for a, b in zip(rows, rows[1:]))
    step = min(max(BUCKET, round(gaps[len(gaps) // 2] / BUCKET) * BUCKET), 3600)  # the series' own interval
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["timestamp", "value"])
    for t, v in rows:
        # a coarser point covers several buckets: a count is spread over them (a sixth each for 30 minutes), a
        # gauge holds its value
        for k in range(step // BUCKET if (agg == "sum" or HOLD_GAUGES) else 1):
            w.writerow([t + k * BUCKET, v * BUCKET / step if agg == "sum" else v])
    info = connectors.import_csv(out.getvalue().encode(), "series", agg, bad)["metrics"]["series"]
    start, end = db.bucket_of(info["from"]), db.bucket_of(info["to"])
    probation = start + max(3 * 86400, (end - start) * 15 // 100) // BUCKET * BUCKET
    labels = json.loads((NAB / "combined_windows.json").read_text())
    key = next(k for k in labels if k.endswith("/" + filename))
    all_windows = [(_epoch(a), _epoch(b)) for a, b in labels[key]]
    share = float(os.environ.get("BENCH_LABEL_SHARE") or 0)  # simulate a team labelling some incidents every week
    rng = __import__("random").Random(filename)
    with db.session(write=True) as c:
        c.execute("UPDATE metrics SET last_scored_ts = 0")
        t = probation
        while t < end:  # walk forward: train on the past (and its labels), score the next week, repeat
            detector.train_all(c, now=t)
            m = c.execute("SELECT * FROM metrics WHERE name = 'series'").fetchone()
            nxt = min(t + int(float(os.environ.get("BENCH_RETRAIN_DAYS") or 7) * 86400), end)  # retrain cadence
            detector.backfill(c, m, t, nxt)
            if share:
                for inc in c.execute("SELECT id, start_ts FROM incidents WHERE start_ts >= ? AND start_ts <= ?",
                                     (t, nxt)).fetchall():
                    if rng.random() < share:
                        # as a person would: real when it is the labelled event (within 6 h of it), else a false alarm
                        real = any(abs(inc["start_ts"] - (a + b) // 2) <= 6 * 3600 for a, b in all_windows)
                        c.execute("UPDATE incidents SET feedback = ? WHERE id = ?", (int(real), inc["id"]))
            t = nxt + BUCKET
        incs = [dict(r) for r in c.execute("SELECT start_ts, end_ts, severity, confidence, model_json FROM incidents "
                                           "ORDER BY start_ts")]
    windows = [(a, b) for a, b in all_windows if b > probation]
    caught, near, lags, used, per_label = 0, 0, [], set(), []
    for a, b in windows:
        hit = [i for i, inc in enumerate(incs) if a <= inc["start_ts"] <= b]
        used.update(hit)
        if hit:
            caught += 1
            lags.append((incs[hit[0]]["start_ts"] - (a + b) // 2) / 60)
        near += any(abs(incs[i]["start_ts"] - (a + b) // 2) <= NEAR for i in hit)
        mid = (a + b) // 2
        per_label.append({"at": mid, "near_start": any(abs(inc["start_ts"] - mid) <= NEAR for inc in incs),
                          "open_near": any(inc["start_ts"] <= mid + NEAR and inc["end_ts"] >= mid - NEAR for inc in incs)})
    outside = [inc for i, inc in enumerate(incs) if i not in used and inc["start_ts"] >= probation]
    # a metric that stopped reporting is a data outage, not a value anomaly: counted apart (NAB labels values only)
    outages = [inc for inc in outside if '"kind":"no_data"' in (inc["model_json"] or "")]
    false = [inc for inc in outside if inc not in outages]
    weeks = (end - probation) / WEEK
    return {"file": filename, "tier": tier, "agg": agg, "windows": len(windows), "caught": caught, "near": near,
            "false_alarms": len(false), "data_outages": len(outages), "labels": per_label,
            "weeks": round(weeks, 2), "lag_min": lags}


def run_all(tier: str, jobs: int) -> list[dict]:
    def one(fn):
        p = subprocess.run([sys.executable, "-I", __file__, "--one", fn, "--tier", tier],
                           capture_output=True, text=True, timeout=1800)
        if p.returncode:
            raise RuntimeError(f"{fn}: {p.stderr[-800:]}")
        return json.loads(p.stdout.strip().splitlines()[-1])
    with ThreadPoolExecutor(jobs) as ex:
        return list(ex.map(one, SERIES))


def summary(rows: list[dict]) -> dict:
    lags = [x for r in rows for x in r["lag_min"]]
    labels = [lab for r in rows for lab in r.get("labels", [])]
    weeks = sum(r["weeks"] for r in rows)
    return {"caught": sum(r["caught"] for r in rows), "near": sum(r.get("near", 0) for r in rows),
            "windows": sum(r["windows"] for r in rows),
            "open_near": sum(lab["open_near"] for lab in labels),
            "false_alarms": sum(r["false_alarms"] for r in rows), "data_outages": sum(r.get("data_outages", 0) for r in rows),
            "weeks": round(weeks, 1),
            "fa_per_week": round(sum(r["false_alarms"] for r in rows) / weeks, 2) if weeks else 0.0,
            "median_lag_min": round(statistics.median(lags)) if lags else None}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tier", default="area", choices=["orbit", "area", "time", "all"])
    ap.add_argument("--jobs", type=int, default=max(2, (os.cpu_count() or 4) // 2))
    ap.add_argument("--save", action="store_true", help="save as the baseline to compare later runs against")
    ap.add_argument("--labels", type=float, default=0.0, metavar="SHARE",
                    help="simulate a team labelling this share of each week's incidents (👍 within 6 h of a labelled anomaly, else 👎)")
    ap.add_argument("--one", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.labels:
        os.environ["BENCH_LABEL_SHARE"] = str(args.labels)
    if args.one:
        print(json.dumps(run_one(args.one, args.tier)))
        return 0
    missing = [f for f in [*SERIES, "combined_windows.json"] if not (NAB / f).exists()]
    if missing:
        sys.exit(f"missing NAB files in {NAB}: see docs/manual-test.md ('Getting the data again')")
    base = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
    result = {}
    for tier in (["orbit", "area", "time"] if args.tier == "all" else [args.tier]):
        rows = run_all(tier, args.jobs)
        s = summary(rows)
        result[tier] = {"summary": s, "series": rows}
        print(f"\n{tier}: caught {s['caught']}/{s['windows']} labelled anomalies ({s['near']} started and {s['open_near']} open "
              f"within 3 h of the label) · "
              f"{s['false_alarms']} false alarms, {s['data_outages']} data outages "
              f"({s['fa_per_week']}/week over {s['weeks']} weeks) · median lag {s['median_lag_min']} min vs the label")
        for r in rows:
            print(f"  {r['file']:<40} {r['caught']}/{r['windows']} caught ({r['near']} near) · {r['false_alarms']:>3} false")
        for kind, agg in (("counts", "sum"), ("gauges", "mean")):
            g = summary([r for r in rows if r.get("agg") == agg])
            if g["windows"] or g["false_alarms"]:
                print(f"  {kind}: caught {g['caught']}/{g['windows']}, {g['open_near']} open near the label, "
                      f"{g['false_alarms']} false alarms ({g['fa_per_week']}/week)")
        if tier in base:
            b = base[tier]["summary"]
            print(f"  vs baseline: caught {s['caught'] - b['caught']:+d} · open near the label "
                  f"{s['open_near'] - b.get('open_near', s['open_near']):+d}"
                  f" · false alarms {s['false_alarms'] - b['false_alarms']:+d}")
    if args.save:
        BASELINE.write_text(json.dumps({**base, **result}, indent=1))
        print(f"\nsaved as the baseline: {BASELINE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
