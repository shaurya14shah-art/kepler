"""Live traffic for Orbitly: requests and sign-ups from simulated web/iOS/Android users in US/EU/IN,
following the same daily rhythm as the backfilled history.

    python traffic.py [--url http://localhost:9200] [--speed 1.0]
"""
import argparse
import asyncio
import random
import time

import httpx
import numpy as np

from model import REQUESTS_PER_SEC_PEAK, ROUTES, SIGNUPS_PER_MIN_PEAK, load, mix


def pick(ts: float) -> tuple[str, str]:
    r, acc = random.random(), 0.0
    for platform, region, share in mix(ts):
        acc += share
        if r <= acc:
            return platform, region
    return "web", "US"


async def one(client: httpx.AsyncClient, kind: str, ts: float, stats: dict):
    platform, region = pick(ts)
    headers = {"x-platform": platform, "x-region": region}
    try:
        if kind == "signup":
            r = await client.post("/signup", json={"plan": random.choice(["free", "free", "free", "pro"])}, headers=headers)
        else:
            route = random.choices(list(ROUTES), weights=list(ROUTES.values()))[0]
            r = await (client.get(route, headers=headers) if route in ("/feed", "/search") else client.post(route, headers=headers))
        stats[r.status_code] = stats.get(r.status_code, 0) + 1
    except httpx.HTTPError:
        stats["conn_err"] = stats.get("conn_err", 0) + 1


async def main(url: str, speed: float):
    stats: dict = {}
    rng = np.random.default_rng()
    last_report = time.time()
    async with httpx.AsyncClient(base_url=url, timeout=10) as client:
        pending: set = set()
        while True:
            now = time.time()
            factor = load(now) * speed
            # Poisson arrivals per 100 ms tick, at exactly the rates the backfilled history used
            n_req = int(rng.poisson(REQUESTS_PER_SEC_PEAK * factor * 0.1))
            n_sign = int(rng.poisson(SIGNUPS_PER_MIN_PEAK / 60 * factor * 0.1))
            for _ in range(n_req):
                pending.add(asyncio.create_task(one(client, "request", now, stats)))
            for _ in range(n_sign):
                pending.add(asyncio.create_task(one(client, "signup", now, stats)))
            pending = {t for t in pending if not t.done()}
            if now - last_report > 60:
                print(time.strftime("%H:%M:%S"), "load", round(factor, 2), "responses", dict(sorted(stats.items(), key=str)), flush=True)
                stats.clear()
                last_report = now
            await asyncio.sleep(0.1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:9200")
    ap.add_argument("--speed", type=float, default=1.0, help="traffic multiplier")
    a = ap.parse_args()
    asyncio.run(main(a.url, a.speed))
