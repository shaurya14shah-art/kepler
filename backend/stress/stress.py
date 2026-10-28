"""Kepler stress test. Starts its own server on a throwaway database and attacks every surface.

    cd backend && .venv/bin/python stress/stress.py [--seconds 45] [--workers 24] [--port 8765]

An ERROR is anything a user should never see: an HTTP 5xx, a hang/timeout, a crash or traceback, a worker error,
an invariant violation (e.g. NaN in JSON, confidence outside [0,1]). Rejecting bad input with a 4xx is correct
behaviour and is counted separately. Exit code 0 only when there are zero errors.
"""
import argparse
import asyncio
import csv
import math
import os
import random
import shutil
import signal
import string
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
KEPLER = str(Path(PY).with_name("kepler"))


class Report:
    def __init__(self):
        self.lock = threading.Lock()
        self.errors: list[tuple[str, str]] = []
        self.ok = Counter()
        self.rejected = Counter()
        self.lat = defaultdict(list)

    def error(self, where: str, what: str):
        with self.lock:
            self.errors.append((where, what[-900:] if "Traceback" in what else what[:400]))

    def good(self, where: str):
        with self.lock:
            self.ok[where] += 1

    def reject(self, where: str):
        with self.lock:
            self.rejected[where] += 1


R = Report()


# ---------------------------------------------------------------- helpers

def walk_numbers(obj, path="$"):
    """Yield (path, value) for every float in a JSON object (to catch NaN/inf leaking out)."""
    if isinstance(obj, float):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk_numbers(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:50]):
            yield from walk_numbers(v, f"{path}[{i}]")


def check_decision(d: dict, where: str):
    c = d.get("confidence")
    if c is not None and not (0 <= c <= 1):
        R.error(where, f"confidence out of range: {c}")
    if d.get("severity") not in (None, "critical", "high", "medium"):
        R.error(where, f"bad severity {d.get('severity')}")


def call(c: httpx.Client, method: str, path: str, tag: str, expect_reject=False, **kw):
    t0 = time.perf_counter()
    try:
        r = c.request(method, path, **kw)
    except httpx.TimeoutException:
        R.error(tag, f"{method} {path} timed out")
        return None
    except httpx.HTTPError as e:
        R.error(tag, f"{method} {path} transport error {type(e).__name__}: {e}")
        return None
    R.lat[tag].append(time.perf_counter() - t0)
    if r.status_code >= 500:
        R.error(tag, f"{method} {path} → {r.status_code}: {r.text[:300]}")
        return None
    if r.status_code >= 400:
        if expect_reject:
            R.reject(tag)
        else:
            R.error(tag, f"{method} {path} unexpectedly rejected {r.status_code}: {r.text[:200]}")
        return None
    if expect_reject:
        R.reject(tag)  # accepted something odd but did not break; fine
    if "json" in r.headers.get("content-type", ""):
        try:
            body = r.json()
        except ValueError:
            R.error(tag, f"{method} {path} invalid JSON")
            return None
        for p, v in walk_numbers(body):
            if not math.isfinite(v):
                R.error(tag, f"{method} {path} non-finite number at {p}")
                break
        R.good(tag)
        return body
    R.good(tag)
    return r.text


def rand_text(n=None):
    n = n or random.randint(0, 40)
    pool = string.ascii_letters + string.digits + " _-./#%=?!'\"😀ü中\t"
    return "".join(random.choice(pool) for _ in range(n))


# ---------------------------------------------------------------- server

def start_server(port: int, tmp: Path) -> subprocess.Popen:
    env = {**os.environ, "KEPLER_DB": str(tmp / "stress.db"), "KEPLER_HOME": str(tmp / "home"), "KEPLER_NO_NOTIFY": "1",
           "KEPLER_AUTH": "off"}
    log = open(tmp / "server.log", "w")
    proc = subprocess.Popen([str(Path(PY).with_name("uvicorn")), "kepler.api:app", "--port", str(port), "--log-level", "warning",
                             "--timeout-keep-alive", "75"],
                            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            h = httpx.get(base + "/api/health", timeout=2).json()
            if not h["seeding"] and h["last_tick"]:
                return proc
        except (httpx.HTTPError, ValueError, KeyError):
            pass
        time.sleep(0.5)
    proc.kill()
    raise SystemExit("server did not become ready (see server.log)")


# ---------------------------------------------------------------- phase 1: API flood

def api_flood(base: str, seconds: int, workers: int):
    with httpx.Client(base_url=base, timeout=10) as c0:
        key = c0.get("/api/settings").json()["api_key"]
        metrics = c0.get("/api/overview").json()["metrics"]
        scenarios = [s["id"] for s in c0.get("/api/demo/scenarios").json()]
    names = [m["name"] for m in metrics]
    H = {"X-Kepler-Key": key}
    stop = time.time() + seconds

    skip = set(filter(None, os.environ.get("STRESS_SKIP", "").split(",")))

    def action(c: httpx.Client):
        m = random.choice(metrics)
        roll = random.random()
        if ("train" in skip and 0.77 <= roll < 0.79) or ("inject" in skip and 0.79 <= roll < 0.83):
            return
        if roll < 0.12:
            call(c, "GET", "/api/overview", "overview")
        elif roll < 0.22:
            call(c, "GET", f"/api/metrics/{m['id']}/series", "series", params={"hours": random.choice([1, 6, 24, 72, 168, 999999, -5]),
                                                                              "slice": random.choice(["", "platform=ios", "region=EU", "nope=1", rand_text(8)])})
        elif roll < 0.28:
            call(c, "GET", f"/api/metrics/{m['id']}/breakdown", "breakdown")
        elif roll < 0.36:
            r = call(c, "GET", f"/api/v1/decision/{random.choice(names)}", "decision", headers=H)
            if r and r.get("decision") == "anomaly":
                for d in r["incidents"]:
                    check_decision(d, "decision")
        elif roll < 0.44:
            incs = call(c, "GET", "/api/incidents", "incidents", params={"limit": random.choice([1, 10, 200, 5000]),
                                                                          "status": random.choice([None, "open", "resolved"])})
            if incs:
                d = random.choice(incs)
                check_decision(d, "incidents")
                call(c, "GET", f"/api/incidents/{d['incident_id']}", "incident")
                if random.random() < 0.3:
                    call(c, "POST", f"/api/incidents/{d['incident_id']}/feedback", "feedback", json={"label": random.choice([0, 1, None])})
        elif roll < 0.60:  # ingest, valid and hostile
            pts = []
            for _ in range(random.randint(1, 300)):
                pts.append({"name": random.choice(names[:3] + ["stress_metric", "stress-💥", "x" * 120]),
                            "value": random.choice([1, 0, -5, 1e12, 0.5, random.random() * 100]),
                            "ts": random.choice([None, time.time(), time.time() - 86400 * 30, 0, 4102444800]),
                            "dims": random.choice([None, {"platform": random.choice(["ios", "web"])}, {"k": rand_text(10)}, {}]),
                            "agg": random.choice(["sum", "sum", "mean"])})
            call(c, "POST", "/api/v1/ingest", "ingest", headers=H, json={"metrics": pts})
        elif roll < 0.64:  # garbage the server must reject cleanly
            bad = random.choice([
                ("POST", "/api/v1/ingest", {"json": {"metrics": [{"name": "", "value": 1}]}, "headers": H}),
                ("POST", "/api/v1/ingest", {"json": {"metrics": "nope"}, "headers": H}),
                ("POST", "/api/v1/ingest", {"content": b"{not json", "headers": {**H, "content-type": "application/json"}}),
                ("POST", "/api/v1/ingest", {"json": {"metrics": []}, "headers": {"X-Kepler-Key": "wrong"}}),
                ("GET", "/api/incidents/99999999", {}),
                ("GET", "/api/metrics/99999999/series", {}),
                ("GET", "/api/metrics/abc/series", {}),
                ("POST", "/api/incidents/1/feedback", {"json": {"label": 7}}),
                ("PUT", "/api/settings", {"json": {"sensitivity": 5}}),
                ("PUT", "/api/settings", {"json": {"slack_webhook_url": "https://evil.example/x"}}),
                ("POST", "/api/connectors", {"json": {"type": "nope", "name": "x", "config": {}}}),
                ("POST", "/api/connectors/test", {"json": {"type": "datadog", "name": "x", "config": {}}}),
                ("POST", "/api/destinations/test", {"json": {"type": "webhook", "name": "x", "config": {"url": "not a url"}}}),
                ("POST", "/api/demo/inject", {"json": {"scenario": "nope"}}),
                ("POST", "/v1/metrics", {"content": b"\x00\x01", "headers": {**H, "content-type": "application/x-protobuf"}}),
                ("POST", "/v1/metrics", {"json": {"resourceMetrics": [{"scopeMetrics": [{"metrics": [{"name": "g", "gauge": {"dataPoints": [{"asDouble": "NaN"}]}}]}]}]}, "headers": H}),
                ("POST", "/api/v1/hooks/segment", {"json": {"type": "track"}, "params": {"key": key}}),
                ("POST", "/api/v1/hooks/segment", {"json": {"batch": [{"type": "track", "event": rand_text(30), "timestamp": "garbage"}]}, "params": {"key": key}}),
                ("PATCH", "/api/metrics/1", {"json": {"bad_direction": "sideways"}}),
                ("GET", "/api/v1/decision/does-not-exist", {"headers": H}),
            ])
            call(c, bad[0], bad[1], "garbage", expect_reject=True, **bad[2])
        elif roll < 0.68:
            r = call(c, "POST", "/api/v1/hooks/segment", "segment", params={"key": key, "dims": "plan,context.os.name"},
                     json={"batch": [{"type": random.choice(["track", "page", "identify"]), "event": random.choice(["Signed Up", "Clicked 💥", ""]),
                                      "properties": {"plan": random.choice(["pro", None, 3])}, "context": {"os": {"name": "iOS"}},
                                      "timestamp": random.choice(["2026-10-19T12:01:00Z", None])} for _ in range(random.randint(1, 50))]})
        elif roll < 0.71:
            ns = str(int(time.time() * 1e9))
            call(c, "POST", "/v1/metrics", "otlp", headers=H, json={"resourceMetrics": [{"resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "svc"}}]},
                "scopeMetrics": [{"metrics": [
                    {"name": "req.count", "sum": {"aggregationTemporality": 2, "isMonotonic": True, "dataPoints": [{"startTimeUnixNano": "1", "timeUnixNano": ns, "asInt": str(random.randint(0, 10**6))}]}},
                    {"name": "lat", "histogram": {"aggregationTemporality": random.choice([1, 2]), "dataPoints": [{"timeUnixNano": ns, "count": str(random.randint(0, 50)), "sum": random.random() * 100}]}},
                    {"name": "depth", "gauge": {"dataPoints": [{"timeUnixNano": ns, "asDouble": random.random()}]}}]}]}]})
        elif roll < 0.72:
            call(c, "PUT", "/api/settings", "settings", json={"sensitivity": random.choice([0.3, 0.5, 0.6]), "min_change_pct": random.choice([10, 15])})
        elif roll < 0.74:  # model tiers: switch the default / one metric, compare, catalog
            pick = random.random()
            if pick < 0.3:
                call(c, "PUT", "/api/settings", "tier", json={"model_tier": random.choice(["orbit", "area", "time"])})
            elif pick < 0.6:
                call(c, "PATCH", f"/api/metrics/{m['id']}", "tier", json={"tier": random.choice(["orbit", "area", "time", "default"])})
            elif pick < 0.8:
                call(c, "GET", f"/api/metrics/{m['id']}/compare", "compare")
            else:
                call(c, "GET", "/api/tiers", "tiers")
                call(c, "PUT", "/api/settings", "garbage", expect_reject=True, json={"model_tier": "jupiter"})
        elif roll < 0.77:
            call(c, "GET", "/api/models", "models")
        elif roll < 0.79:
            call(c, "POST", "/api/models/train", "train")
        elif roll < 0.83:
            r = call(c, "POST", "/api/demo/inject", "inject", json={"scenario": random.choice(scenarios)})
        elif roll < 0.86:
            raw = random.choice([
                "timestamp,metric,value,region\n" + "\n".join(f"2026-10-0{1 + i % 8}T{i % 24:02d}:00:00Z,csv_m,{i % 7},{random.choice(['US', 'EU'])}" for i in range(200)),
                "timestamp,value\n2026-10-01T00:00:00Z,abc\n,\n",
                "garbage without columns",
                "",
                "timestamp,metric,value\n" + "9999999999999,x,1\n",
                "﻿timestamp,metric,value\n2026-10-01,bom_metric,1\n",
            ])
            call(c, "POST", "/api/import/csv", "csv", expect_reject=True, files={"file": ("x.csv", raw.encode(), "text/csv")},
                 data={"metric": random.choice(["", "csv_fallback"]), "agg": "sum", "bad_direction": "both"})
        elif roll < 0.89:
            call(c, "GET", "/api/notifications", "notifications")
            call(c, "GET", "/api/connectors", "connectors")
            call(c, "GET", "/api/destinations", "destinations")
            call(c, "GET", "/api/integrations", "integrations")
        elif roll < 0.91:
            call(c, "POST", "/api/connectors/test", "connector_test", json={"type": "prometheus", "name": "x",
                 "config": {"url": "http://127.0.0.1:9", "query": "up", "metric": "p"}})
        elif roll < 0.93:
            call(c, "PATCH", f"/api/metrics/{m['id']}", "patch", json={"description": rand_text(20)})
        elif roll < 0.95:
            call(c, "GET", "/", "spa")
            call(c, "GET", "/..%2f..%2fetc%2fpasswd", "spa")
        else:
            call(c, "GET", "/api/health", "health")

    def loop():
        with httpx.Client(base_url=base, timeout=30) as c:
            while time.time() < stop:
                try:
                    action(c)
                except Exception:
                    R.error("flood-client", traceback.format_exc())

    with ThreadPoolExecutor(workers) as ex:
        for f in [ex.submit(loop) for _ in range(workers)]:
            f.result()


# ---------------------------------------------------------------- phase 2: engine edge cases (in-process)

def engine_edges(tmp: Path):
    os.environ["KEPLER_DB"] = str(tmp / "engine.db")
    sys.path.insert(0, str(ROOT))
    from kepler import db
    from kepler.db import BUCKET, DAY
    from kepler.engine import detector
    from kepler.engine.drilldown import drilldown

    db.DB_PATH = Path(os.environ["KEPLER_DB"])
    db.init_db()
    now = int(time.time()) // BUCKET * BUCKET - BUCKET
    n = 15 * DAY
    ts = [now - (n - i) * BUCKET for i in range(n)]
    rng = random.Random(7)
    cases = {
        "all_zero": lambda i: 0.0,
        "constant": lambda i: 5.0,
        "huge": lambda i: 1e15 + rng.random(),
        "tiny": lambda i: 1e-9 * rng.random(),
        "negative": lambda i: -50 + rng.gauss(0, 3),
        "sparse": lambda i: 1.0 if rng.random() < 0.01 else None,
        "step_change": lambda i: 10.0 if i < n * 0.7 else 400.0,
        "spiky": lambda i: 1e6 if i % 997 == 0 else rng.random(),
        "short_history": lambda i: rng.random() if i > n - 30 else None,
        "one_point": lambda i: 3.0 if i == n - 1 else None,
    }
    for name, fn in cases.items():
        for agg in ("sum", "mean"):
            mname = f"edge_{name}_{agg}"
            try:
                with db.session(write=True) as c:
                    mid = db.ensure_metric(c, mname, agg=agg, source="push")
                    rows = []
                    for i, t in enumerate(ts):
                        v = fn(i)
                        if v is not None:
                            rows.append((t, "", v, 1.0))
                            if name in ("constant", "step_change", "spiky"):
                                rows.append((t, f"platform={'ios' if i % 2 else 'web'}", v / 2, 1.0))
                    db.add_points(c, mid, rows, mode="replace")
                with db.session(write=True) as c:
                    m = c.execute("SELECT * FROM metrics WHERE id = ?", (mid,)).fetchone()
                    detector.backfill(c, m, now - 3 * DAY * BUCKET, now)
                    detector.score_latest(c, c.execute("SELECT * FROM metrics WHERE id = ?", (mid,)).fetchone(), now)
                    drilldown(c, m, [now - BUCKET, now])
                    for inc in c.execute("SELECT * FROM incidents WHERE metric_id = ?", (mid,)).fetchall():
                        d = detector.decision(inc, m)
                        check_decision(d, f"engine:{mname}")
                        for p, v in walk_numbers(d):
                            if not math.isfinite(v):
                                R.error(f"engine:{mname}", f"non-finite {p}")
                                break
                R.good("engine")
            except Exception:
                R.error(f"engine:{mname}", traceback.format_exc())
    # high cardinality: 400 segments
    try:
        with db.session(write=True) as c:
            mid = db.ensure_metric(c, "edge_high_cardinality", agg="sum", source="push")
            rows = [(t, f"user={u}|region={u % 7}", float(rng.randint(0, 3)), 1.0) for t in ts[-3 * DAY:] for u in range(0, 400, 7)]
            db.add_points(c, mid, rows, mode="replace")
            m = c.execute("SELECT * FROM metrics WHERE id = ?", (mid,)).fetchone()
            t0 = time.time()
            detector.score_latest(c, m, now)
            if time.time() - t0 > 30:
                R.error("engine:high_cardinality", f"scoring took {time.time() - t0:.0f}s")
        with db.session(write=True) as c:
            t0 = time.time()
            detector.train_all(c, now)
            R.good("engine")
            if time.time() - t0 > 60:
                R.error("engine:train_all", f"training took {time.time() - t0:.0f}s")
    except Exception:
        R.error("engine:high_cardinality/train", traceback.format_exc())


# ---------------------------------------------------------------- phase 3: bot fuzz

def bot_fuzz(base: str, n: int):
    from kepler.bot.brain import Bot
    from kepler.cli.client import Client
    bot = Bot(Client(base))
    samples = ["", " ", "?", "#", "#0", "#99999999", "explain #-1", "label 4000000000 real", "set sensitivity to 900%",
               "set sensitivity to -5%", "show signups for the last 0 hours", "show signups last 99999 days", "1", "2", "3",
               "🙂" * 200, "a" * 5000, "'; DROP TABLE incidents; --", "{{metric}}", "\x00\x01", "why", "explain it", "copy that",
               "open #1 in the browser", "connect", "connect nothing", "demo", "train", "is =ios ok", "plot =", "show region=",
               "label it real", "label it false", "mark #1 as real", "split nonexistent by region", "why did zzzzzz drop"]
    texts = samples + [rand_text(random.randint(1, 120)) for _ in range(n)]
    import kepler.device as dev
    dev.copy = lambda text: True          # never touch the real clipboard
    dev.open_url = lambda url: True       # never open real browser tabs
    for t in texts:
        try:
            r = bot.handle(t)
            if r is None or "intent" not in r.decision:
                R.error("bot", f"no decision for {t[:40]!r}")
            elif r.decision.get("intent") == "error" and "HTTP 5" in r.text:
                R.error("bot", f"server 5xx via bot for {t[:40]!r}: {r.text[:200]}")
            else:
                c = r.decision.get("confidence", 0)
                if not (0 <= c <= 1):
                    R.error("bot", f"confidence {c} for {t[:40]!r}")
                R.good("bot")
        except Exception:
            R.error("bot", f"{t[:40]!r}: {traceback.format_exc()}")


# ---------------------------------------------------------------- phase 4: CLI commands

def cli_sweep(base: str, tmp: Path):
    env = {**os.environ, "KEPLER_URL": base, "KEPLER_HOME": str(tmp / "home"), "KEPLER_CONFIG": str(tmp / "home" / "config.json"),
           "KEPLER_NO_NOTIFY": "1", "NO_COLOR": "1", "COLUMNS": "100"}
    csvp = tmp / "cli.csv"
    with open(csvp, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "metric", "value", "region"])
        for i in range(3 * 288):
            w.writerow([time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(1790812800 + i * 300)), "cli_metric", random.randint(0, 9), random.choice(["US", "EU"])])
    cmds = [
        ["status"], ["status", "--json"], ["status", "--exit-code"], ["decide", "api_errors"], ["decide", "api_errors", "--json"],
        ["decide", "does_not_exist"], ["metrics"], ["metric", "signups", "--hours", "6"], ["metric", "signups", "--slice", "platform=ios"],
        ["metric", "nope"], ["incidents"], ["incidents", "--open", "--json"], ["explain", "1"], ["explain", "99999999"],
        ["watch", "--once"], ["analyze", str(csvp)], ["analyze", str(csvp), "--json"], ["analyze", "/no/such/file.csv"],
        ["send", "cli_sent", "3", "--dim", "a=b"], ["label", "1", "real"], ["label", "1", "clear"], ["models"], ["models", "--json"],
        ["settings"], ["settings", "--sensitivity", "55"], ["key"], ["alerts"], ["demo"], ["demo", "ios_release_bug"], ["demo", "nope"],
        ["tiers"], ["tier", "time"], ["compare", "api_errors"], ["metric", "signups", "--tier", "orbit"],
        ["metric", "signups", "--tier", "default"], ["tier", "area"], ["ask", "which", "models", "are", "there"],
        ["integrations"], ["connect", "datadog"], ["connect", "prometheus", "url=http://127.0.0.1:9", "query=up", "metric=x", "--test"],
        ["connect", "nope"], ["connect", "datadog", "badfield"], ["pulls"], ["destinations"], ["import", str(csvp)],
        ["completion", "zsh"], ["completion", "bash"], ["agent", "status"], ["agent", "install", "--print"], ["config"],
        ["ask", "is", "everything", "ok"], ["ask", "--json", "why", "did", "api", "errors", "spike"], ["ask", "🙂"], ["__complete", "metrics"],
        ["--version"], ["--help"],
    ]
    for cmd in cmds:
        tag = "cli:" + " ".join(cmd[:2])
        try:
            p = subprocess.run([KEPLER, *cmd], env=env, capture_output=True, text=True, timeout=120, input="")
        except subprocess.TimeoutExpired:
            R.error(tag, "timed out")
            continue
        if "Traceback (most recent call last)" in p.stderr + p.stdout:
            R.error(tag, (p.stderr or p.stdout)[-600:])
        elif p.returncode not in (0, 1, 2, 3):
            R.error(tag, f"exit {p.returncode}: {(p.stderr or p.stdout)[-300:]}")
        elif p.returncode == 3 and "error:" not in p.stderr:
            R.error(tag, f"exit 3 without an error message: {p.stderr[-200:]}")
        else:
            R.good("cli")


# ---------------------------------------------------------------- phase 5: TUI monkey test

def tui_monkey(base: str, seconds: int):
    os.environ["KEPLER_NO_NOTIFY"] = "1"
    import kepler.device as dev
    dev.copy = lambda text: True
    dev.open_url = lambda url: True
    dev.agent_install = lambda *a, **k: "skipped in stress test"
    dev.agent_uninstall = lambda *a, **k: "skipped in stress test"
    from kepler.cli.client import Client
    from kepler.tui.app import KeplerApp

    keys = list("123456") + ["r", "t", "d", "?", "escape", "escape", "enter", "down", "down", "up", "tab", "shift+tab",
                             "ctrl+k", "ctrl+k", "slash", "f", "space", "n", "n", "left", "right", "pagedown", "home"]
    chat = ["status", "why did api errors spike", "show signups last 6h", "explain it", "label it real", "help",
            "which models are there", "use time for api errors", "switch to area", rand_text(30)]

    async def run():
        app = KeplerApp(Client(base))
        async with app.run_test(size=(140, 44)) as pilot:
            await pilot.pause(1.5)
            await pilot.press("enter")
            await pilot.pause(3)
            end = time.time() + seconds
            while time.time() < end:
                if random.random() < 0.12:
                    await pilot.press("slash")
                    await pilot.press(*list(random.choice(chat)))
                    await pilot.press("enter")
                    await pilot.press("escape")
                else:
                    k = random.choice(keys)
                    if k == "q":
                        continue
                    await pilot.press(k)
                await pilot.pause(random.choice([0, 0.05, 0.2]))
            await pilot.pause(3)
            for w in app.workers:
                if w.error:
                    R.error("tui-worker", f"{w.name}: {type(w.error).__name__}: {w.error}")
            R.good("tui")

    try:
        asyncio.run(run())
    except Exception:
        R.error("tui", traceback.format_exc())


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=45, help="API flood duration")
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--fuzz", type=int, default=300, help="random bot messages")
    ap.add_argument("--tui-seconds", type=int, default=25)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--max-p95", type=float, default=3.0, help="seconds; slower API p95 counts as an error")
    args = ap.parse_args()
    seed = args.seed if args.seed is not None else random.randrange(10**6)
    random.seed(seed)
    tmp = Path(tempfile.mkdtemp(prefix="kepler-stress-"))
    os.environ["KEPLER_HOME"] = str(tmp / "home")
    base = f"http://127.0.0.1:{args.port}"
    t_all = time.time()
    print(f"kepler stress · seed {seed} · tmp {tmp}")
    proc = start_server(args.port, tmp)
    try:
        for name, fn in (("api flood", lambda: api_flood(base, args.seconds, args.workers)),
                         ("engine edge cases", lambda: engine_edges(tmp)),
                         ("bot fuzz", lambda: bot_fuzz(base, args.fuzz)),
                         ("cli sweep", lambda: cli_sweep(base, tmp)),
                         ("tui monkey", lambda: tui_monkey(base, args.tui_seconds))):
            t0 = time.time()
            before = len(R.errors)
            fn()
            print(f"  {name:<18} {time.time() - t0:6.1f}s   errors +{len(R.errors) - before}")
        h = httpx.get(base + "/api/health", timeout=10).json()
        if h.get("last_error"):
            R.error("server-worker", h["last_error"])
    finally:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
    logtxt = (tmp / "server.log").read_text(errors="replace")
    for chunk in logtxt.split("Traceback (most recent call last)")[1:]:
        R.error("server-log", "Traceback" + chunk[-900:].split("\nINFO")[0])

    total = sum(R.ok.values())
    print(f"\n  requests/actions ok: {total:,}   bad input rejected cleanly: {sum(R.rejected.values()):,}")
    lat = [x for v in R.lat.values() for x in v]
    if lat:
        lat.sort()
        print(f"  api latency  p50 {lat[len(lat) // 2] * 1000:.0f} ms   p95 {lat[int(len(lat) * .95)] * 1000:.0f} ms   max {lat[-1] * 1000:.0f} ms")
        slow = sorted(((k, sorted(v)[int(len(v) * .95)]) for k, v in R.lat.items() if v), key=lambda x: -x[1])[:4]
        print("  slowest p95: " + ", ".join(f"{k} {v * 1000:.0f}ms" for k, v in slow))
        p95 = lat[int(len(lat) * .95)]
        if p95 > args.max_p95:
            R.error("latency", f"API p95 {p95:.1f}s exceeds {args.max_p95}s under {args.workers} concurrent clients")
    grouped = Counter(w for w, _ in R.errors)
    print(f"\n  ERRORS: {len(R.errors)}" + (f"  ({', '.join(f'{k}×{v}' for k, v in grouped.most_common())})" if R.errors else ""))
    seen = set()
    for where, what in R.errors:
        sig = (where, what[:120])
        if sig in seen:
            continue
        seen.add(sig)
        print(f"\n  ✗ [{where}] {what}")
        if len(seen) >= 15:
            print("  … (more)")
            break
    print(f"\n  total {time.time() - t_all:.0f}s · seed {seed}")
    if R.errors:
        (tmp / "errors.txt").write_text("\n\n".join(f"[{w}] {e}" for w, e in R.errors))
        print(f"  kept {tmp} (server.log, errors.txt)")
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(1 if R.errors else 0)


if __name__ == "__main__":
    main()
