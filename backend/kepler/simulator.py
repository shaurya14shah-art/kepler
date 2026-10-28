"""Demo mode: a simulated startup ("Orbitly") streaming realistic product + infra metrics.

Daily cycles per region, weekend dips, slow growth, Poisson noise, and incidents that
hit specific slices (a bad iOS release, an EU database, a stuck webhook queue...).
"""
import itertools
import time

import numpy as np

from . import db
from .db import BUCKET, DAY, segment_key

PLATFORM = {"web": 0.5, "ios": 0.3, "android": 0.2}
REGION = {"US": 0.5, "EU": 0.3, "IN": 0.2}
ENDPOINT = {"/feed": 0.4, "/search": 0.3, "/upload": 0.15, "/auth": 0.15}
QUEUE = {"emails": 0.5, "exports": 0.3, "webhooks": 0.2}
PEAK_HOUR = {"US": 18, "EU": 13, "IN": 8}

METRICS = {
    "signups": dict(agg="sum", unit="signups / 5m", bad="down", base=34, dims={"platform": PLATFORM, "region": REGION},
                    desc="New accounts created"),
    "active_sessions": dict(agg="sum", unit="sessions", bad="down", base=2100, dims={"platform": PLATFORM, "region": REGION},
                            desc="Concurrent user sessions"),
    "api_errors": dict(agg="sum", unit="5xx / 5m", bad="up", base=14, dims={"platform": PLATFORM, "region": REGION},
                       desc="HTTP 5xx responses from the public API"),
    "p95_latency_ms": dict(agg="mean", unit="ms", bad="up", base=170, dims={"endpoint": ENDPOINT, "region": REGION},
                           desc="95th percentile API latency"),
    "job_failures": dict(agg="sum", unit="failed jobs / 5m", bad="up", base=10, dims={"queue": QUEUE},
                         desc="Background jobs that errored"),
}

# preset incidents for the "inject" button
SCENARIOS = {
    "ios_release_bug": dict(metric="api_errors", where={"platform": "ios"}, mult=9.0,
                            label="Bad iOS release: 5xx errors spike on iOS"),
    "android_signup_broken": dict(metric="signups", where={"platform": "android"}, mult=0.05,
                                  label="Android sign-up form broken"),
    "eu_db_slow": dict(metric="p95_latency_ms", where={"region": "EU"}, mult=3.2,
                       label="EU database replica degraded: latency up"),
    "webhook_queue_stuck": dict(metric="job_failures", where={"queue": "webhooks"}, mult=14.0,
                                label="Webhook workers crash-looping"),
    "india_cdn_outage": dict(metric="active_sessions", where={"region": "IN"}, mult=0.35,
                             label="CDN outage in India: sessions drop"),
}

_injections: list[dict] = []  # live injected incidents: {metric, where, mult, start, end}


def _activity(region: str, ts: np.ndarray) -> np.ndarray:
    hour = (ts % 86400) / 3600
    d = np.cos(2 * np.pi * (hour - PEAK_HOUR[region]) / 24)
    bump = ((1 + d) / 2) ** 1.5
    dow = ((ts // 86400) + 3) % 7
    weekend = np.where(dow >= 5, 0.78, 1.0)
    growth = 1 + 0.004 * (ts - ts.min()) / 86400 if len(ts) else 1
    return (0.3 + 0.7 * bump) * weekend * growth


def _segments(dims: dict):
    names = list(dims)
    for combo in itertools.product(*(dims[n].items() for n in names)):
        seg = {n: v for n, (v, _) in zip(names, combo)}
        share = float(np.prod([w for _, w in combo]))
        yield seg, share


def _effect(name: str, seg: dict, ts: np.ndarray, effects: list[dict]) -> np.ndarray:
    mult = np.ones(len(ts))
    for e in effects:
        if e["metric"] != name or any(seg.get(k) != v for k, v in e["where"].items()):
            continue
        inside = (ts >= e["start"]) & (ts <= e["end"])
        if e.get("ramp"):  # gradual: 1x at the start, full effect at the end (a slow burn)
            frac = (ts[inside] - e["start"]) / max(e["end"] - e["start"], 1)
            mult[inside] *= 1 + (e["mult"] - 1) * frac
        else:
            mult[inside] *= e["mult"]
    return mult


def generate(name: str, ts: np.ndarray, effects: list[dict], rng) -> list[tuple]:
    spec = METRICS[name]
    rows = []
    for seg, share in _segments(spec["dims"]):
        region = seg.get("region")
        act = _activity(region, ts) if region else np.mean([_activity(r, ts) for r in REGION], axis=0)
        mult = _effect(name, seg, ts, effects)
        key = segment_key(seg)
        if spec["agg"] == "mean":
            ep_mult = {"/feed": 1.0, "/search": 1.4, "/upload": 2.2, "/auth": 0.6}.get(seg.get("endpoint"), 1.0)
            lat = spec["base"] * ep_mult * (0.85 + 0.3 * act) * mult + rng.normal(0, 6, len(ts))
            n = np.maximum(1, np.round(400 * share * act))
            rows += [(int(t), key, float(max(lat[i], 5) * n[i]), float(n[i])) for i, t in enumerate(ts)]
        else:
            lam = np.clip(spec["base"] * share * act * mult, 0, 1e7)  # overlapping effects can't overflow Poisson
            vals = rng.poisson(np.maximum(lam, 0))
            rows += [(int(t), key, float(vals[i]), 1.0) for i, t in enumerate(ts)]
    return rows


def ensure_metrics(conn) -> dict:
    return {name: db.ensure_metric(conn, name, agg=s["agg"], unit=s["unit"], bad_direction=s["bad"],
                                   description=s["desc"], source="demo")
            for name, s in METRICS.items()}


def history_incidents(start: int, end: int, rng) -> list[dict]:
    """Ground-truth incidents plus harmless blips (which teams would mark as false alarms)."""
    out = []
    keys = list(SCENARIOS)
    span = (end - start) // BUCKET
    for i in range(14):
        sc = SCENARIOS[keys[i % len(keys)]]
        s = start + int(rng.integers(8 * DAY, span - DAY)) * BUCKET
        out.append(dict(sc, start=s, end=s + int(rng.integers(3, 18)) * BUCKET, real=True))
    for _ in range(18):  # blips: short, small, on a minor slice
        sc = SCENARIOS[keys[int(rng.integers(len(keys)))]]
        s = start + int(rng.integers(8 * DAY, span - DAY)) * BUCKET
        mult = 1 + (sc["mult"] - 1) * 0.22 if sc["mult"] > 1 else 1 - (1 - sc["mult"]) * 0.45
        out.append(dict(sc, mult=mult, start=s, end=s, real=False))
    return out


def seed(days: int = 21, now: int | None = None) -> dict:
    """Wipe the demo metrics and regenerate `days` of history, then backfill, label and train."""
    from .engine.detector import backfill, train_all

    now = (now or int(time.time())) // BUCKET * BUCKET - BUCKET
    start = now - days * DAY * BUCKET
    rng = np.random.default_rng(42)
    truth = history_incidents(start, now, rng)
    ts = np.arange(start, now + BUCKET, BUCKET, dtype=np.int64)
    with db.session(write=True) as c:
        demo_ids = "SELECT id FROM metrics WHERE source = 'demo'"
        for tbl in ("points", "incidents", "models"):
            c.execute(f"DELETE FROM {tbl} WHERE metric_id IN ({demo_ids})")
        c.execute("DELETE FROM notifications")
        c.execute("DELETE FROM blobs WHERE key = 'feedback_model'")
        ids = ensure_metrics(c)
        c.execute("UPDATE metrics SET last_scored_ts = 0 WHERE source = 'demo'")
        for name, mid in ids.items():
            db.add_points(c, mid, generate(name, ts, truth, rng), mode="replace")
        c.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('sim_last_ts', ?)", (str(now),))

    with db.session(write=True) as c:
        for m in c.execute("SELECT * FROM metrics WHERE source = 'demo'").fetchall():
            backfill(c, m, start + 7 * DAY * BUCKET, now)
        # the simulated team has labelled ~80% of past alerts
        labelled = 0
        for inc in c.execute("SELECT i.id, i.start_ts, i.end_ts, m.name FROM incidents i JOIN metrics m ON m.id = i.metric_id").fetchall():
            if rng.random() > 0.8:
                continue
            real = any(t["real"] and t["metric"] == inc["name"] and t["start"] - 3 * BUCKET <= inc["end_ts"]
                       and inc["start_ts"] <= t["end"] + 3 * BUCKET for t in truth)
            c.execute("UPDATE incidents SET feedback = ?, status = 'resolved' WHERE id = ?", (1 if real else 0, inc["id"]))
            labelled += 1
        c.execute("UPDATE incidents SET status = 'resolved' WHERE end_ts < ?", (now - 6 * BUCKET,))
        report = train_all(c, now)
    report["seeded_days"] = days
    report["labelled_incidents"] = labelled
    return report


def step(now: int | None = None, score_fn=None) -> int:
    """Generate any completed buckets since the last run. Returns number of buckets written."""
    upto = (now or int(time.time())) // BUCKET * BUCKET - BUCKET
    with db.session(write=True) as c:
        last = int(db.get_settings(c).get("sim_last_ts") or 0)
        if not last or upto <= last:
            return 0
        first = max(last + BUCKET, upto - DAY * BUCKET)
        ts = np.arange(first, upto + BUCKET, BUCKET, dtype=np.int64)
        rng = np.random.default_rng(int(first))
        ids = ensure_metrics(c)
        for name, mid in ids.items():
            db.add_points(c, mid, generate(name, ts, _injections, rng), mode="replace")
        c.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('sim_last_ts', ?)", (str(upto),))
    return len(ts)


def inject(scenario: str) -> dict:
    """Start a live incident: rewrite the last 30 minutes with the effect and keep it going for 45 more."""
    sc = SCENARIOS[scenario]
    with db.session() as c:
        last = int(db.get_settings(c).get("sim_last_ts") or 0)
    start = last - 5 * BUCKET
    eff = dict(metric=sc["metric"], where=sc["where"], mult=sc["mult"], start=start, end=last + 9 * BUCKET)
    # re-injecting the same scenario restarts it instead of stacking multipliers; expired ones are dropped
    _injections[:] = [e for e in _injections if e["end"] >= last - DAY * BUCKET
                      and not (e["metric"] == eff["metric"] and e["where"] == eff["where"])]
    _injections.append(eff)
    ts = np.arange(start, last + BUCKET, BUCKET, dtype=np.int64)
    rng = np.random.default_rng([start, list(SCENARIOS).index(scenario)])  # same sim clock, same noise: replayable
    with db.session(write=True) as c:
        mid = ensure_metrics(c)[sc["metric"]]
        db.add_points(c, mid, generate(sc["metric"], ts, _injections, rng), mode="replace")
        c.execute("UPDATE metrics SET last_scored_ts = ? WHERE id = ?", (start - BUCKET, mid))
    return {"scenario": scenario, "metric": sc["metric"], "where": sc["where"], "until": eff["end"]}
