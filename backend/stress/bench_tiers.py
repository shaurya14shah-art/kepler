"""Benchmark Kepler's three models (Orbit / Area / Time) on the simulated startup.

For each model: fresh database → 21 days of history with known incidents → backfill + label + train → re-score
the last 7 days with the trained models. Measures detection quality, root-cause accuracy, speed and compute cost.

    cd backend && .venv/bin/python stress/bench_tiers.py [--write]
--write saves the summary to kepler/engine/tier_benchmark.json (shown in the app's model picker).
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_one(tier: str) -> dict:
    """Runs in a fresh process so each model gets a clean database and cold caches."""
    os.environ["KEPLER_DB"] = os.path.join(tempfile.mkdtemp(), f"{tier}.db")
    sys.path.insert(0, str(ROOT))
    import numpy as np

    from kepler import db, simulator
    from kepler.db import BUCKET, DAY
    from kepler.engine import detector

    db.init_db()
    db.set_setting("model_tier", tier)
    now = int(time.time()) // BUCKET * BUCKET - BUCKET
    simulator.seed(now=now + BUCKET)                 # history, backfill, labels, training (as this tier)
    truth = simulator.history_incidents(now - 21 * DAY * BUCKET, now, np.random.default_rng(42))
    cut = now - 7 * DAY * BUCKET

    # hard cases (written into the last week): slow burns and a failure that only exists in one exact segment
    hard = [
        dict(metric="p95_latency_ms", where={"region": "EU"}, mult=1.6, ramp=True, kind="slow burn: EU latency +60% over 3 h"),
        dict(metric="signups", where={}, mult=0.6, ramp=True, kind="gradual decline: sign-ups -40% over 4 h"),
        dict(metric="api_errors", where={"platform": "ios", "region": "EU"}, mult=5.0, kind="combination only: iOS × EU errors 5x"),
    ]
    rng = np.random.default_rng(11)
    busy = [(t["start"] - 6 * 3600, t["end"] + 6 * 3600) for t in truth]
    slot = cut + DAY * BUCKET
    for h, length in zip(hard, (36, 48, 18)):
        while any(a <= slot + length * BUCKET and slot <= b for a, b in busy):
            slot += 3600
        h["start"] = slot
        h["end"] = slot + (length - 1) * BUCKET
        busy.append((h["start"] - 6 * 3600, h["end"] + 6 * 3600))
        slot = h["end"] + DAY * BUCKET
        ts = np.arange(h["start"], h["end"] + BUCKET, BUCKET, dtype=np.int64)
        with db.session(write=True) as c:
            mid = c.execute("SELECT id FROM metrics WHERE name = ?", (h["metric"],)).fetchone()["id"]
            db.add_points(c, mid, simulator.generate(h["metric"], ts, [h], rng), mode="replace")

    with db.session(write=True) as c:               # steady state: re-score last week with trained models
        c.execute("DELETE FROM incidents WHERE start_ts >= ?", (cut,))
        for m in c.execute("SELECT * FROM metrics").fetchall():
            detector.backfill(c, m, cut, now)
        incs = c.execute("SELECT m.name, i.* FROM incidents i JOIN metrics m ON m.id = i.metric_id WHERE i.start_ts >= ?",
                         (cut,)).fetchall()

    def overlaps(i, t):
        return i["name"] == t["metric"] and i["start_ts"] <= t["end"] + 3 * BUCKET and i["end_ts"] >= t["start"] - 3 * BUCKET

    real = [t for t in truth if t["real"] and t["start"] >= cut]
    caught = [t for t in real if any(overlaps(i, t) for i in incs)]
    noise = [i for i in incs if not any(overlaps(i, t) for t in truth)]
    root_ok = root_n = 0
    for i in incs:
        t = next((t for t in real if overlaps(i, t)), None)
        if t:
            root_n += 1
            where = json.loads(i["where_json"])
            root_ok += any({w["dimension"]: w["value"]} == t["where"] for w in where)
    delay = [max(0, min(i["start_ts"] for i in incs if overlaps(i, t)) - t["start"]) / 60 for t in caught]

    # speed: one cold 5-minute evaluation of every metric (what the worker does each bucket)
    with db.session() as c:
        metrics = c.execute("SELECT * FROM metrics").fetchall()
        times = []
        for _ in range(3):
            detector._CACHE.clear()
            t0 = time.perf_counter()
            for m in metrics:
                for s in detector.watched_slices(c, m, now):
                    detector.score_window(c, m, now, slice_=s)
            times.append((time.perf_counter() - t0) * 1000)
        series = sum(len(detector.watched_slices(c, m, now)) for m in metrics)
    with db.session() as c:
        rec = detector.DeferredWrites(c)
        t0 = time.perf_counter()
        detector.train_all(rec, now)
        train_s = time.perf_counter() - t0
    reasoning_ms = None
    with db.session() as c:
        rows = c.execute("SELECT i.*, i.metric_id AS mid FROM incidents i WHERE i.start_ts >= ?", (cut,)).fetchall()
        if tier == "time" and rows:
            t0 = time.perf_counter()
            for r in rows:
                detector.reasoning(c, r, c.execute("SELECT * FROM metrics WHERE id = ?", (r["mid"],)).fetchone())
            reasoning_ms = round((time.perf_counter() - t0) * 1000 / len(rows), 2)
        with_impact = sum(1 for r in rows if "impact" in json.loads(r["model_json"] or "{}"))
    def overlaps_h(i, h):
        return i["name"] == h["metric"] and i["start_ts"] <= h["end"] + 3 * BUCKET and i["end_ts"] >= h["start"]

    hard_caught = [h["kind"] for h in hard if any(overlaps_h(i, h) for i in incs)]
    noise = [i for i in noise if not any(overlaps_h(i, h) for h in hard)]
    eval_ms = statistics.median(times) / len(metrics)
    return {
        "recall": round(len(caught) / max(len(real), 1), 3), "caught": len(caught), "real": len(real),
        "noise_per_week": len(noise), "root_cause_accuracy": round(root_ok / max(root_n, 1), 3),
        "hard_cases_caught": len(hard_caught), "hard_cases": len(hard), "hard_caught": hard_caught,
        "median_detect_min": round(statistics.median(delay), 1) if delay else None,
        "series_per_metric": round(series / len(metrics), 1),
        "eval_ms_per_metric": round(eval_ms, 1),
        "cpu_seconds_per_metric_month": round(eval_ms / 1000 * 8640, 1),   # 8,640 five-minute evaluations / month
        "train_seconds": round(train_s, 2),
        "reasoning_ms_per_incident": reasoning_ms,
        "incidents_with_impact": with_impact,
        "measured_at": time.strftime("%Y-%m-%d"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--one", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.one:
        print(json.dumps(run_one(a.one)))
        return
    results = {}
    for tier in ("orbit", "area", "time"):
        t0 = time.time()
        p = subprocess.run([sys.executable, __file__, "--one", tier], capture_output=True, text=True, cwd=ROOT)
        if p.returncode:
            print(p.stderr[-2000:])
            raise SystemExit(f"{tier} failed")
        results[tier] = json.loads(p.stdout.strip().splitlines()[-1])
        print(f"{tier:<6} done in {time.time() - t0:.0f}s")
    cols = [("recall", "recall"), ("hard_cases_caught", "hard cases"), ("noise_per_week", "noise/wk"), ("root_cause_accuracy", "root cause"),
            ("median_detect_min", "detect (min)"), ("series_per_metric", "series/metric"),
            ("eval_ms_per_metric", "ms/eval"), ("cpu_seconds_per_metric_month", "CPU-s/metric/mo"), ("train_seconds", "train s"),
            ("reasoning_ms_per_incident", "reason ms/inc")]
    print("\n" + f"{'':<8}" + "".join(f"{h:>16}" for _, h in cols))
    for tier, r in results.items():
        print(f"{tier:<8}" + "".join(f"{str(r[k]):>16}" for k, _ in cols))
    if a.write:
        out = ROOT / "kepler" / "engine" / "tier_benchmark.json"
        out.write_text(json.dumps(results, indent=2))
        print(f"\nsaved {out}")


if __name__ == "__main__":
    main()
