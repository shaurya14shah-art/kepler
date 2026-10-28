"""Orbitly: a small, real web app used as a test subject for Kepler.

* Sign-ups are stored in Postgres (table `users`), which Kepler reads with its Postgres connector.
* Every request is counted and timed with prometheus_client at /metrics, which Prometheus scrapes and
  Kepler then queries with its Prometheus connector.
* /admin/faults switches on a realistic breakage for N minutes, so you can check Kepler catches it.

Run: uvicorn app:app --port 9200   (from lab/orbitly, with ORBITLY_DSN set)
"""
import os
import random
import threading
import time

import psycopg
from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel

from model import BASE_ERROR_RATE, BASE_LATENCY_S, PLATFORMS, REGION_LATENCY, REGIONS

DSN = os.environ.get("ORBITLY_DSN", "postgresql://localhost:5433/orbitly")

REQUESTS = Counter("http_requests_total", "HTTP requests", ["route", "status", "platform"])
LATENCY = Histogram("http_request_duration_seconds", "Request latency", ["region"],
                    buckets=(0.025, 0.05, 0.1, 0.2, 0.4, 0.8, 1.6, 3.2))

# fault name -> (description, expiry time)
FAULTS = {
    "ios_errors": "Bad iOS release: 60% of iOS /feed requests fail with 500",
    "android_signups": "Android sign-up form broken: Android sign-ups fail",
    "eu_slow": "EU database replica degraded: EU requests ~4x slower",
}
active: dict[str, float] = {}
lock = threading.Lock()

app = FastAPI(title="Orbitly")


def is_on(name: str) -> bool:
    with lock:
        exp = active.get(name)
        if exp and exp < time.time():
            del active[name]
            return False
        return exp is not None


def client(request: Request) -> tuple[str, str]:
    platform = request.headers.get("x-platform", "web")
    region = request.headers.get("x-region", "US")
    return (platform if platform in PLATFORMS else "web"), (region if region in REGIONS else "US")


def serve(route: str, request: Request) -> dict:
    platform, region = client(request)
    delay = BASE_LATENCY_S.get(route, 0.05) * REGION_LATENCY[region] * random.lognormvariate(0, 0.35)
    if region == "EU" and is_on("eu_slow"):
        delay *= 4
    fail = random.random() < BASE_ERROR_RATE
    if route == "/feed" and platform == "ios" and is_on("ios_errors"):
        fail = fail or random.random() < 0.6
    time.sleep(min(delay, 2.0))
    LATENCY.labels(region).observe(delay)
    status = "500" if fail else "200"
    REQUESTS.labels(route, status, platform).inc()
    if fail:
        raise HTTPException(500, "internal error")
    return {"ok": True, "route": route}


@app.get("/feed")
def feed(request: Request):
    return serve("/feed", request)


@app.get("/search")
def search(request: Request):
    return serve("/search", request)


@app.post("/upload")
def upload(request: Request):
    return serve("/upload", request)


@app.post("/login")
def login(request: Request):
    return serve("/login", request)


class SignupIn(BaseModel):
    plan: str = "free"


@app.post("/signup")
def signup(body: SignupIn, request: Request):
    platform, region = client(request)
    if platform == "android" and is_on("android_signups"):
        REQUESTS.labels("/signup", "500", platform).inc()
        raise HTTPException(500, "signup form error")
    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute("INSERT INTO users(platform, region, plan) VALUES (%s, %s, %s)", (platform, region, body.plan))
    REQUESTS.labels("/signup", "200", platform).inc()
    return {"ok": True}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


class FaultIn(BaseModel):
    name: str
    minutes: float = 30


@app.get("/admin/faults")
def list_faults():
    now = time.time()
    return {"available": FAULTS,
            "active": {k: round((v - now) / 60, 1) for k, v in active.items() if v > now}}


@app.post("/admin/faults")
def start_fault(body: FaultIn):
    if body.name not in FAULTS:
        raise HTTPException(404, f"unknown fault; choose from {sorted(FAULTS)}")
    with lock:
        active[body.name] = time.time() + body.minutes * 60
    return {"started": body.name, "minutes": body.minutes, "what": FAULTS[body.name]}


@app.delete("/admin/faults/{name}")
def stop_fault(name: str):
    with lock:
        active.pop(name, None)
    return {"stopped": name}
