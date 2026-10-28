"""Give Orbitly 3 weeks of past life, so Kepler has history to learn "normal" from on day one.

* Postgres: inserts past sign-up rows into `users` (same daily rhythm as live traffic).
* Prometheus: writes an OpenMetrics file of past request counters / latency histograms, which setup.sh imports
  with Prometheus' own `promtool tsdb create-blocks-from openmetrics`.

    python seed_history.py --dsn postgresql://localhost:5433/orbitly --out history.om [--days 21]
"""
import argparse
import io
import math
import random
import time

import numpy as np
import psycopg

from model import (BASE_ERROR_RATE, BASE_LATENCY_S, PLATFORMS, REGION_LATENCY, REGIONS, REQUESTS_PER_SEC_PEAK, ROUTES,
                   SIGNUPS_PER_MIN_PEAK, activity, load, mix)

BUCKETS = (0.025, 0.05, 0.1, 0.2, 0.4, 0.8, 1.6, 3.2)


def seed_postgres(dsn: str, start: float, end: float, rng: np.random.Generator) -> int:
    buf = io.StringIO()
    n = 0
    t = start
    while t < end:
        for platform, region, share in mix(t):
            lam = SIGNUPS_PER_MIN_PEAK * load(t) * share  # sign-ups in this minute for this segment
            for _ in range(rng.poisson(lam)):
                ts = t + rng.random() * 60
                buf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(ts))}+00\t{platform}\t{region}\t"
                          f"{'pro' if rng.random() < 0.25 else 'free'}\n")
                n += 1
        t += 60
    buf.seek(0)
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            with cur.copy("COPY users (created_at, platform, region, plan) FROM STDIN") as cp:
                while chunk := buf.read(1 << 20):
                    cp.write(chunk)
    return n


def write_openmetrics(path: str, start: float, end: float, step: int, rng: np.random.Generator) -> int:
    """Cumulative counters sampled every `step` seconds, in OpenMetrics text format."""
    routes = list(ROUTES) + ["/signup"]
    req = {(r, s, p): 0.0 for r in routes for s in ("200", "500") for p in PLATFORMS}
    hist = {(reg, le): 0.0 for reg in REGIONS for le in BUCKETS + (math.inf,)}
    hsum = {reg: 0.0 for reg in REGIONS}
    hcount = {reg: 0.0 for reg in REGIONS}
    lines_req, lines_hist = [], []
    t = start
    while t < end:
        rps = REQUESTS_PER_SEC_PEAK * load(t)
        for platform, region, share in mix(t):
            n = rng.poisson(rps * share * step)
            if not n:
                continue
            # requests per route
            for route, w in ROUTES.items():
                k = rng.binomial(n, w)
                errs = rng.binomial(k, BASE_ERROR_RATE)
                req[(route, "200", platform)] += k - errs
                req[(route, "500", platform)] += errs
                # latency observations, summarised per region
                if k:
                    lat = BASE_LATENCY_S[route] * REGION_LATENCY[region] * rng.lognormal(0, 0.35, size=min(k, 200))
                    scale = k / len(lat)
                    for le in BUCKETS + (math.inf,):
                        hist[(region, le)] += float((lat <= le).sum()) * scale
                    hsum[region] += float(lat.sum()) * scale
                    hcount[region] += k
            signups = rng.poisson(SIGNUPS_PER_MIN_PEAK / 60 * load(t) * share * step)
            req[("/signup", "200", platform)] += signups
        ts = int(t)
        for (r, s, p), v in req.items():
            lines_req.append(f'http_requests_total{{route="{r}",status="{s}",platform="{p}"}} {v:.0f} {ts}')
        for (reg, le), v in hist.items():
            le_s = "+Inf" if le == math.inf else repr(le)
            lines_hist.append(f'http_request_duration_seconds_bucket{{region="{reg}",le="{le_s}"}} {v:.0f} {ts}')
        for reg in REGIONS:
            lines_hist.append(f'http_request_duration_seconds_sum{{region="{reg}"}} {hsum[reg]:.3f} {ts}')
            lines_hist.append(f'http_request_duration_seconds_count{{region="{reg}"}} {hcount[reg]:.0f} {ts}')
        t += step
    with open(path, "w") as f:
        # OpenMetrics needs each metric family's samples together
        f.write("# TYPE http_requests counter\n")
        f.write("\n".join(lines_req) + "\n")
        f.write("# TYPE http_request_duration_seconds histogram\n")
        f.write("\n".join(lines_hist) + "\n")
        f.write("# EOF\n")
    return len(lines_req) + len(lines_hist)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default="postgresql://localhost:5433/orbitly")
    ap.add_argument("--out", default="history.om")
    ap.add_argument("--days", type=int, default=21)
    ap.add_argument("--step", type=int, default=60, help="seconds between backfilled Prometheus samples")
    a = ap.parse_args()
    rng = np.random.default_rng(7)
    end = time.time() // 60 * 60 - 120  # stop just before 'now'; live traffic continues from here
    start = end - a.days * 86400
    t0 = time.time()
    n = seed_postgres(a.dsn, start, end, rng)
    print(f"postgres: {n:,} past sign-ups over {a.days} days ({time.time() - t0:.1f}s)")
    t0 = time.time()
    m = write_openmetrics(a.out, start, end, a.step, rng)
    print(f"prometheus: {m:,} samples written to {a.out} ({time.time() - t0:.1f}s)")
