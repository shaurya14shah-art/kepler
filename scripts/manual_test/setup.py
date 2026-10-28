"""Manual test kit: real datasets replayed through a local Postgres, watched by a Kepler test workspace.

Run from the repo root once the Kepler test server is up (docs/manual-test.md has every step):

    backend/.venv/bin/python -I scripts/manual_test/setup.py

What it does:
  1. Reads the Numenta Anomaly Benchmark files in backend/data/manual-test/nab/ (MIT licence; real data with
     labelled anomalies): tweet volumes for 10 companies, an AWS load balancer's request count, NYC taxi passengers.
  2. Shifts each dataset in time so up to 4 weeks of history end now, and the rest lies in the future. It's timed so
     that a real labelled anomaly happens soon: tweets ~45 min, load balancer ~1 h 40 min, taxi ~3 h after setup.
  3. Loads it into Postgres (database kepler_test). Tables in schema `replay` hold every row. Views in `public`
     (tweets, elb_requests, taxi_passengers) show only rows up to now(), which is what a live app's tables would
     show, so the future rows "arrive" as the clock passes them.
  4. Imports the history into Kepler and trains it. Adds one Postgres pull per metric (every minute) and a signed
     webhook destination for alerts (scripts/manual_test/webhook_receiver.py).
  5. Writes backend/data/manual-test/schedule.json: when each labelled anomaly happens. check.py reads it.

No account or password is involved: Postgres runs on this Mac and trusts local connections.
"""
import argparse
import csv
import json
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql

from kepler.cli.client import Client, KeplerError

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "backend" / "data" / "manual-test"
NAB = DATA / "nab"
SECRET = DATA / "webhook.secret"
SCHEDULE = DATA / "schedule.json"
PG_DB = "kepler_test"
DSN = f"postgresql://localhost:5432/{PG_DB}"
BUCKET = 300
DAY = 86400
HISTORY_DAYS = 28
COMPANIES = ["AAPL", "AMZN", "GOOG", "FB", "IBM", "KO", "PFE", "UPS", "CVS", "CRM"]

DATASETS = {
    "tweet_mentions": dict(
        table="tweets", column="mentions", sql_type="integer", dim="company", lead_min=45, alert_when="up",
        files={c: f"Twitter_volume_{c}.csv" for c in COMPANIES},
        about="Tweets mentioning each of 10 companies, every 5 minutes (NAB realTweets)"),
    "elb_requests": dict(
        table="elb_requests", column="requests", sql_type="double precision", dim=None, lead_min=100, alert_when="up",
        files={None: "elb_request_count_8c0756.csv"},
        about="Requests through a real AWS Elastic Load Balancer, every 5 minutes (NAB realAWSCloudwatch)"),
    "taxi_passengers": dict(
        table="taxi_passengers", column="passengers", sql_type="double precision", dim=None, lead_min=180,
        alert_when="both", files={None: "nyc_taxi.csv"}, spread_s=1800,
        about="NYC taxi passengers; each 30-minute count is spread evenly over its six 5-minute buckets (NAB realKnownCause)"),
}


def query(metric: str) -> str:
    d = DATASETS[metric]
    dim = f"{d['dim']}, " if d["dim"] else ""
    return (f"SELECT date_bin('5 minutes', ts, TIMESTAMPTZ '2000-01-01') AS ts, {dim}sum({d['column']}) AS value\n"
            f"FROM {d['table']} WHERE ts > now() - interval '3 hours'\nGROUP BY {'1, 2' if d['dim'] else '1'}")


def read_series(path: Path, spread_s: int | None) -> list[tuple[int, float]]:
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            t = int(datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp())
            v = float(r["value"])
            if spread_s:  # one count per 30 minutes → six 5-minute buckets with a sixth each
                n = spread_s // BUCKET
                rows += [(t + k * BUCKET, v / n) for k in range(n)]
            else:
                rows.append((t, v))
    return rows


def windows(labels: dict, filename: str) -> list[tuple[int, int]]:
    key = next(k for k in labels if k.endswith("/" + filename))
    to_s = lambda s: int(datetime.fromisoformat(s[:19]).replace(tzinfo=timezone.utc).timestamp())  # noqa: E731
    return [(to_s(a), to_s(b)) for a, b in labels[key]]


def pick_anchor(start: int, anomalies: list[dict], lead_s: int) -> int:
    """The moment of the original data that becomes 'now': just before a labelled anomaly, with as much history before
    it as possible (at least 21 days when the data has it), and as many other anomalies as possible soon after."""
    mids = sorted(a["mid"] for a in anomalies)
    enough = [m for m in mids if m - lead_s - start >= 21 * DAY] or [max(mids)]
    score = lambda m: (sum(1 for x in mids if m - lead_s < x <= m - lead_s + 3 * DAY), m)  # noqa: E731
    return max(enough, key=score) - lead_s


def build(now: int) -> dict:
    labels = json.loads((NAB / "combined_windows.json").read_text())
    plan = {}
    for metric, d in DATASETS.items():
        series = {seg: read_series(NAB / fn, d.get("spread_s")) for seg, fn in d["files"].items()}
        anomalies = [{"slice": seg, "start": a, "end": b, "mid": (a + b) // 2}
                     for seg, fn in d["files"].items() for a, b in windows(labels, fn)]
        start = min(r[0][0] for r in series.values())
        anchor = pick_anchor(start, anomalies, d["lead_min"] * 60)
        shift = (now - anchor) // 60 * 60
        first = anchor - HISTORY_DAYS * DAY
        rows = [(t + shift, seg, v) for seg, pts in series.items() for t, v in pts if t >= first]
        end = max(r[0] for r in rows)
        sched = [{"metric": metric, "slice": f"{d['dim']}={a['slice']}" if a["slice"] else None,
                  "at": a["mid"] + shift, "window": [a["start"] + shift, a["end"] + shift]}
                 for a in anomalies if first <= a["mid"] and a["mid"] + shift <= end]
        plan[metric] = dict(rows=rows, shift=shift, end=end, schedule=sched)
    return plan


def load_postgres(plan: dict) -> None:
    with psycopg.connect("postgresql://localhost:5432/postgres", autocommit=True) as pg:
        if not pg.execute("SELECT 1 FROM pg_database WHERE datname = %s", (PG_DB,)).fetchone():
            pg.execute(f"CREATE DATABASE {PG_DB}")
    with psycopg.connect(DSN) as pg:
        pg.execute("CREATE SCHEMA IF NOT EXISTS replay")
        for metric, d in DATASETS.items():
            t, col = d["table"], d["column"]
            dim = f"{d['dim']} text NOT NULL, " if d["dim"] else ""
            pg.execute(f"DROP TABLE IF EXISTS replay.{t} CASCADE")
            pg.execute(f"CREATE TABLE replay.{t} (ts timestamptz NOT NULL, {dim}{col} {d['sql_type']} NOT NULL)")
            cols = ["ts"] + ([d["dim"]] if d["dim"] else []) + [col]
            with pg.cursor().copy(f"COPY replay.{t} ({', '.join(cols)}) FROM STDIN") as cp:
                for ts, seg, v in plan[metric]["rows"]:
                    when = datetime.fromtimestamp(ts, timezone.utc)
                    cp.write_row([when, seg, int(v) if d["sql_type"] == "integer" else v] if d["dim"] else [when, v])
            pg.execute(f"CREATE INDEX ON replay.{t} (ts)")
            pg.execute(f"CREATE VIEW public.{t} AS SELECT * FROM replay.{t} WHERE ts <= now()")
            pg.execute(sql.SQL("COMMENT ON VIEW {} IS {}").format(  # COMMENT takes no query parameters
                sql.Identifier("public", t), sql.Literal(f"{d['about']}. Replay: rows appear as their time passes.")))


def history_csv(metric: str, rows: list, now: int) -> Path:
    """Past rows in Kepler's import format, summed per 5-minute bucket like the pull query."""
    d = DATASETS[metric]
    sums: dict[tuple, float] = {}
    for ts, seg, v in rows:
        b = ts // BUCKET * BUCKET
        if b + BUCKET <= now:  # complete buckets only: the pull fills in the current one
            sums[(b, seg)] = sums.get((b, seg), 0.0) + v
    path = DATA / "history" / f"{metric}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "metric", "value"] + ([d["dim"]] if d["dim"] else []))
        for (b, seg), v in sorted(sums.items()):
            w.writerow([b, metric, round(v, 3)] + ([seg] if d["dim"] else []))
    return path


def configure_kepler(c: Client, plan: dict, now: int, webhook: str) -> None:
    taken = {m["name"] for m in c.metrics()} & set(DATASETS)
    if taken:
        sys.exit(f"this Kepler workspace already has {', '.join(sorted(taken))}: start from a fresh test workspace "
                 "(docs/manual-test.md, 'Start over')")
    for metric, d in DATASETS.items():
        r = c.upload_csv(history_csv(metric, plan[metric]["rows"], now), metric, "sum", d["alert_when"])
        print(f"  imported {r['rows']:,} rows of history into {metric}")
        body = {"type": "postgres", "name": f"Postgres: {metric}", "interval_s": 60,
                "config": {"dsn": DSN, "query": query(metric), "metric": metric, "agg": "sum",
                           "bad_direction": d["alert_when"]}}
        t = c.post("/api/connectors/test", body)
        if not t["ok"]:
            sys.exit(f"the Postgres pull for {metric} failed its test: {t['message']}")
        c.post("/api/connectors", body)
        print(f"  pull for {metric}: every minute from Postgres ({t['message']})")
    print("  training…", end=" ", flush=True)
    c.post("/api/models/train?force=true")
    print("done")
    if not SECRET.exists():
        SECRET.write_text(secrets.token_hex(24))
        SECRET.chmod(0o600)
    dest = {"type": "webhook", "name": "Local test receiver", "min_severity": "medium",
            "config": {"url": webhook, "secret": SECRET.read_text().strip()}}
    t = c.post("/api/destinations/test", dest)
    c.post("/api/destinations", dest)
    print(f"  alerts → {webhook} (signed) {'✓ receiver answered' if t['ok'] else '· receiver not running yet: ' + t['message']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default="http://localhost:8100", help="the Kepler test server")
    ap.add_argument("--webhook", default="http://127.0.0.1:8788/kepler", help="where alerts go")
    ap.add_argument("--postgres-only", action="store_true", help="(re)load Postgres and stop")
    args = ap.parse_args()
    missing = [fn for d in DATASETS.values() for fn in d["files"].values() if not (NAB / fn).exists()]
    if missing or not (NAB / "combined_windows.json").exists():
        sys.exit(f"missing NAB files in {NAB}: download them first (docs/manual-test.md)")
    now = int(time.time())
    plan = build(now)
    load_postgres(plan)
    for metric, p in plan.items():
        print(f"postgres: {DATASETS[metric]['table']:<16} {len(p['rows']):>7,} rows, replay runs until "
              f"{datetime.fromtimestamp(p['end']).strftime('%a %d %b %H:%M')}")
    if not args.postgres_only:
        c = Client(args.url)
        try:
            c.get("/api/health")
        except KeplerError as e:
            sys.exit(f"no Kepler test server at {args.url} ({e}): start it first (docs/manual-test.md)")
        configure_kepler(c, plan, now, args.webhook)
    sched = sorted((a for p in plan.values() for a in p["schedule"]), key=lambda a: a["at"])
    SCHEDULE.write_text(json.dumps({"created": now, "url": args.url, "anomalies": sched}, indent=1))
    print("\nlabelled real anomalies still to come (local time):")
    for a in [a for a in sched if a["at"] > now][:12]:
        print(f"  {datetime.fromtimestamp(a['at']).strftime('%a %d %b %H:%M')}  {a['metric']}"
              f"{' · ' + a['slice'] if a['slice'] else ''}")
    print("\ncheck what Kepler caught at any time:  backend/.venv/bin/python -I scripts/manual_test/check.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
