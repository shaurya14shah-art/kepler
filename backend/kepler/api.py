"""Kepler HTTP API + background worker."""
import json
import logging
import math
import secrets
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, billing, config, connectors, db, security, simulator
from .billing import razorpay
from .db import BUCKET, DAY, bucket_of, segment_key
from .engine import compare, detector, tiers
from .engine.classifier import FeedbackModel
from .integrations import REGISTRY
from .integrations.inbound import parse_otlp, parse_segment
from .notify import notify, send_test

log = logging.getLogger("kepler")
TICK_S = 5
STALE_S = 30 * 60

state = {"seeding": False, "last_tick": 0, "last_error": None}


# ---------------------------------------------------------------- background worker

def _due_connectors():
    now = int(time.time())
    with db.session() as c:
        return [r for r in c.execute("SELECT * FROM connectors WHERE enabled = 1").fetchall()
                if now - (r["last_run"] or 0) >= r["interval_s"]]


def _settled_by_metric(c) -> dict[str, int]:
    """metric name -> last bucket fully covered by its source's last successful pull."""
    out = {}
    for r in c.execute("SELECT config_json, last_ok FROM connectors").fetchall():
        name = json.loads(r["config_json"]).get("metric")
        if name:
            settled = bucket_of(r["last_ok"] or 0) - BUCKET
            out[name] = max(out.get(name, 0), settled)
    return out


def tick():
    if state["seeding"]:
        return
    settings = db.get_settings()
    if settings.get("demo_mode") == "1":
        simulator.step()
    for row in _due_connectors():
        connectors.run(row)
    now_upto = bucket_of(time.time()) - BUCKET  # last *completed* bucket
    with db.session() as c:
        metrics = c.execute(
            "SELECT m.*, (SELECT MAX(ts) FROM points p WHERE p.metric_id = m.id) AS last_ts FROM metrics m"
        ).fetchall()
        settled = _settled_by_metric(c)
    _auto_train(time.time())
    for m in metrics:
        # pulled metrics: a bucket is only final once a pull happened after it ended
        upto = min(now_upto, settled[m["name"]]) if m["name"] in settled else now_upto
        if not m["last_ts"] or m["last_scored_ts"] >= upto or upto - m["last_ts"] > 6 * 3600:
            continue
        with db.session() as rc:
            detector.prewarm(rc, m, upto)
        with db.session(write=True) as c:
            detector.score_latest(c, m, upto, notify_fn=notify, max_stale=detector.PREWARMED_S)


def worker(stop: threading.Event):
    """The background loop: demo data, scheduled pulls, scoring. Runs until the app shuts down (`stop` is set)."""
    while not stop.is_set():
        try:
            tick()
            state["last_tick"] = int(time.time())
            state["last_error"] = None
        except Exception as e:  # keep the loop alive; surface the error in /api/health
            log.exception("worker tick failed")
            state["last_error"] = f"{type(e).__name__}: {e}"
        stop.wait(TICK_S)


def _seed_demo():
    state["seeding"] = True
    try:
        simulator.seed()
    finally:
        state["seeding"] = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    with db.session() as c:
        has_demo = c.execute("SELECT 1 FROM metrics WHERE source = 'demo' LIMIT 1").fetchone()
    if db.get_settings().get("demo_mode") == "1" and not has_demo:
        threading.Thread(target=_seed_demo, daemon=True).start()
    stop = threading.Event()  # one per app run, so a restarted app never revives a stopped worker
    threading.Thread(target=worker, args=(stop,), daemon=True, name="kepler-worker").start()
    try:
        yield
    finally:
        stop.set()
        compare.shutdown()


app = FastAPI(title="Kepler", version=__version__, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


class BodyLimit:
    """Refuses request bodies over the limit with a 413, before anything is parsed: from Content-Length up front, and
    by counting as it arrives when the size isn't declared (chunked uploads). CSV uploads have their own, larger
    limit (plus room for the multipart wrapping)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = MAX_CSV_BYTES + 1024 * 1024 if scope["path"] == "/api/import/csv" else MAX_BODY_BYTES
        detail = f"request body larger than {limit // (1024 * 1024)} MB"
        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > limit):
            return await JSONResponse({"detail": detail}, status_code=413)(scope, receive, send)
        seen = 0

        async def counted():
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:  # raised while the route reads its body: FastAPI answers it as a 413
                    raise HTTPException(413, detail)
            return message
        await self.app(scope, counted, send)


app.add_middleware(BodyLimit)


@app.middleware("http")
async def require_key(request: Request, call_next):
    if security.needs_key(request.url.path):
        if not security.authorized(request.headers, request.cookies):
            return JSONResponse({"detail": "access key required"}, status_code=401)
    return await call_next(request)


# ---------------------------------------------------------------- helpers

def _clean(x):
    if isinstance(x, float) and not math.isfinite(x):
        return None
    if isinstance(x, (np.floating,)):
        return _clean(float(x))
    return x


def _metric(c, metric_id: int):
    m = c.execute("SELECT * FROM metrics WHERE id = ?", (metric_id,)).fetchone()
    if not m:
        raise HTTPException(404, "metric not found")
    return m


def _incident_dict(c, inc, metric=None):
    metric = metric or c.execute("SELECT * FROM metrics WHERE id = ?", (inc["metric_id"],)).fetchone()
    d = detector.decision(inc, metric)
    if d["tier"] == "time":
        d["reasoning"] = detector.reasoning(c, inc, metric)
    d["feedback"] = inc["feedback"]
    d["related"] = detector.related_incidents(c, inc)
    d["metric_id"] = metric["id"]
    d["unit"] = metric["unit"]
    return d


def _series(c, metric, start: int, end: int, slice_: str = ""):
    # the chart plus HISTORY_DAYS of history, in whole weeks beyond the first day so that charts of any length share
    # a few cached windows (a 24 h chart's first hours get 14 days of history instead of 15: same baseline)
    span = -(-(end - start) // (DAY * BUCKET))
    extra = 0 if span <= 1 else -(-span // 7) * 7
    scored = detector.score_window(c, metric, end, days=detector.HISTORY_DAYS + extra,
                                   slice_=slice_, max_stale=detector.DISPLAY_STALE_S,
                                   refreshing_ok=detector.DISPLAY_REFRESH_S)
    i0 = int(np.searchsorted(scored["ts"], start))
    zs = detector.shown_z(c, metric, scored, i0)
    pts = []
    for i in range(i0, len(scored["ts"])):
        v = scored["v"][i]
        pts.append({
            "ts": int(scored["ts"][i]),
            "value": _clean(float(v)) if not np.isnan(v) else None,
            "expected": _clean(float(scored["expected"][i])),
            "lower": _clean(max(float(scored["lower"][i]), 0.0)) if metric["agg"] == "sum" else _clean(float(scored["lower"][i])),
            "upper": _clean(float(scored["upper"][i])),
            "z": _clean(float(zs[i - i0])),
        })
    return pts, scored["model"], int(scored.get("k") or 1) * BUCKET


# ---------------------------------------------------------------- health / overview

MAX_BODY_BYTES = 10 * 1024 * 1024       # JSON bodies (ingest, OTLP, Segment, settings…)
MAX_CSV_BYTES = 50 * 1024 * 1024        # CSV history uploads

@app.get("/api/health")
def health():
    return {"ok": True, "seeding": state["seeding"], "last_tick": state["last_tick"], "last_error": state["last_error"],
            "auto_train": config.AUTO_TRAIN, "now": int(time.time())}


# ---------------------------------------------------------------- dashboard sign-in (the access key → a cookie)

class SessionIn(BaseModel):
    key: str = Field(min_length=1, max_length=200)


@app.get("/api/session")
def session_status(request: Request):
    signed_in = not config.AUTH_REQUIRED or security.authorized(request.headers, request.cookies)
    return {"auth_required": config.AUTH_REQUIRED, "signed_in": signed_in}


@app.post("/api/session")
def sign_in(body: SessionIn, request: Request):
    addr = request.client.host if request.client else "unknown"
    if security.too_many_attempts(addr):
        raise HTTPException(429, "too many wrong attempts: wait a few minutes")
    key = body.key.strip()
    if not security.key_matches(key):
        security.record_failure(addr)
        raise HTTPException(401, "that access key isn't right")
    resp = JSONResponse({"ok": True})
    resp.set_cookie(security.COOKIE, security.session_token(key), max_age=security.SESSION_DAYS * 86400, httponly=True,
                    samesite="strict", secure=config.SECURE_COOKIES, path="/")
    return resp


@app.delete("/api/session")
def sign_out():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(security.COOKIE, path="/")
    return resp


@app.get("/api/overview")
def overview():
    now = int(time.time())
    upto = bucket_of(now) - BUCKET
    out = []
    with db.session() as c:
        metrics = c.execute("SELECT * FROM metrics ORDER BY id").fetchall()
        for m in metrics:
            last_ts = c.execute("SELECT MAX(ts) t FROM points WHERE metric_id = ?", (m["id"],)).fetchone()["t"]
            end = min(upto, last_ts or upto)
            pts, model, _ = _series(c, m, end - 6 * 3600, end)
            open_inc = c.execute("SELECT * FROM incidents WHERE metric_id = ? AND status = 'open' ORDER BY confidence DESC",
                                 (m["id"],)).fetchall()
            latest = next((p for p in reversed(pts) if p["value"] is not None), None)
            status = "anomaly" if open_inc else ("stale" if not last_ts or now - last_ts > STALE_S + BUCKET else "ok")
            out.append({
                "id": m["id"], "name": m["name"], "unit": m["unit"], "agg": m["agg"], "source": m["source"],
                "description": m["description"], "bad_direction": m["bad_direction"],
                "status": status, "model": model.kind, "model_label": model.label,
                "tier": detector.tier_for(c, m).id, "tier_override": m["tier"],
                "muted_until": (m["muted_until"] or 0) if (m["muted_until"] or 0) > now else 0,
                "latest": latest, "last_ts": last_ts,
                "sparkline": [{"ts": p["ts"], "value": p["value"], "expected": p["expected"]} for p in pts],
                "open_incidents": [_incident_dict(c, i, m) for i in open_inc],
            })
        day_ago = now - 86400
        stats = c.execute(
            "SELECT SUM(status = 'open') open, SUM(start_ts >= ?) last24, SUM(feedback = 1) tp, SUM(feedback = 0) fp, "
            "COUNT(*) total FROM incidents", (day_ago,)).fetchone()
    return {"metrics": out, "stats": {k: stats[k] or 0 for k in stats.keys()}, "seeding": state["seeding"], "now": now,
            "maintenance_until": _maintenance_until(db.get_settings())}


# ---------------------------------------------------------------- metrics

@app.get("/api/metrics/{metric_id}/series")
def metric_series(metric_id: int, hours: int = 24, slice: str = ""):
    hours = max(1, min(hours, 24 * 14))
    with db.session() as c:
        m = _metric(c, metric_id)
        last_ts = c.execute("SELECT MAX(ts) t FROM points WHERE metric_id = ?", (m["id"],)).fetchone()["t"] or 0
        end = min(bucket_of(time.time()) - BUCKET, last_ts) if last_ts else bucket_of(time.time())
        start = end - hours * 3600
        pts, model, every = _series(c, m, start, end, slice)
        incs = c.execute("SELECT * FROM incidents WHERE metric_id = ? AND end_ts >= ? AND slice = ? ORDER BY start_ts",
                         (m["id"], start, slice)).fetchall()
        slices = detector.slices(c, m, end)[1:]
        return {"metric": dict(m), "slice": slice, "slices": slices, "model": model.label, "model_kind": model.kind,
                "tier": detector.tier_for(c, m).id, "reports_every_s": every,
                "points": pts, "incidents": [_incident_dict(c, i, m) for i in incs]}


@app.get("/api/metrics/{metric_id}/breakdown")
def metric_breakdown(metric_id: int):
    """Current state of every slice: how far each one is from its own expectation right now."""
    with db.session() as c:
        m = _metric(c, metric_id)
        last_ts = c.execute("SELECT MAX(ts) t FROM points WHERE metric_id = ?", (m["id"],)).fetchone()["t"]
        if not last_ts:
            return {"slices": []}
        end = min(bucket_of(time.time()) - BUCKET, last_ts)
        out = []
        for s in detector.slices(c, m, end)[1:]:
            sc = detector.score_window(c, m, end, days=detector.HISTORY_DAYS, slice_=s, max_stale=detector.DISPLAY_STALE_S,
                                       refreshing_ok=detector.DISPLAY_REFRESH_S)
            v, e, z = sc["v"][-1], sc["expected"][-1], detector.shown_z(c, m, sc, len(sc["ts"]) - 1)[0]
            dim, val = s.split("=", 1)
            out.append({"slice": s, "dimension": dim, "value": val, "observed": _clean(float(v)),
                        "expected": _clean(float(e)), "z": _clean(float(z)),
                        "change_pct": _clean(float((v - e) / e * 100)) if e and abs(e) > 0.05 else None})
        return {"slices": out}


class MetricPatch(BaseModel):
    unit: str | None = None
    description: str | None = None
    bad_direction: str | None = Field(None, pattern="^(up|down|both)$")
    agg: str | None = Field(None, pattern="^(sum|mean)$")
    tier: str | None = Field(None, pattern="^(orbit|area|time|default)$")  # 'default' = follow the workspace
    muted_until: int | None = Field(None, ge=0)  # pause alerts until this time (epoch seconds); 0 = unmute


MAX_MUTE_S = 30 * 86400  # a mute always ends: nobody should find a metric silenced months later


@app.patch("/api/metrics/{metric_id}")
def patch_metric(metric_id: int, body: MetricPatch):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if fields.get("muted_until", 0) > time.time() + MAX_MUTE_S:
        raise HTTPException(400, "a mute can last at most 30 days")
    if fields.get("tier") == "default":
        fields["tier"] = None
    with db.session(write=True) as c:
        _metric(c, metric_id)
        if "tier" in body.model_fields_set and body.tier == "default":
            c.execute("UPDATE metrics SET tier = NULL WHERE id = ?", (metric_id,))
            fields.pop("tier", None)
        if fields:
            c.execute(f"UPDATE metrics SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?", [*fields.values(), metric_id])
        return dict(_metric(c, metric_id))


@app.delete("/api/metrics/{metric_id}")
def delete_metric(metric_id: int):
    with db.session(write=True) as c:
        _metric(c, metric_id)
        c.execute("DELETE FROM incident_notes WHERE incident_id IN (SELECT id FROM incidents WHERE metric_id = ?)", (metric_id,))
        for tbl in ("points", "incidents", "models"):
            c.execute(f"DELETE FROM {tbl} WHERE metric_id = ?", (metric_id,))
        c.execute("DELETE FROM metrics WHERE id = ?", (metric_id,))
    return {"deleted": metric_id}


# ---------------------------------------------------------------- incidents

@app.get("/api/incidents")
def list_incidents(status: str | None = None, metric_id: int | None = None, limit: int = 100):
    q, args = "SELECT * FROM incidents WHERE 1=1", []
    if status:
        q += " AND status = ?"
        args.append(status)
    if metric_id:
        q += " AND metric_id = ?"
        args.append(metric_id)
    q += " ORDER BY start_ts DESC LIMIT ?"
    args.append(min(limit, 500))
    with db.session() as c:
        return [_incident_dict(c, i) for i in c.execute(q, args).fetchall()]


@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: int):
    with db.session() as c:
        inc = c.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
        if not inc:
            raise HTTPException(404, "incident not found")
        m = _metric(c, inc["metric_id"])
        start, end = inc["start_ts"] - 4 * 3600, min(inc["end_ts"] + 2 * 3600, bucket_of(time.time()) - BUCKET)
        pts, _, _ = _series(c, m, start, end, inc["slice"])
        sent = c.execute("SELECT kind, delivered, error, created_at FROM notifications WHERE incident_id = ? ORDER BY id",
                         (incident_id,)).fetchall()
        return {"decision": _incident_dict(c, inc, m), "points": pts, "notifications": [dict(n) for n in sent],
                "notes": _notes(c, incident_id)}


def _notes(c, incident_id: int) -> list[dict]:
    return [dict(r) for r in c.execute("SELECT id, text, created_at FROM incident_notes WHERE incident_id = ? ORDER BY id",
                                       (incident_id,))]


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@app.post("/api/incidents/{incident_id}/notes")
def add_note(incident_id: int, body: NoteIn):
    """What the team found or did about an incident: shown with it in the dashboard, `kepler explain` and the API."""
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "a note needs some text")
    with db.session(write=True) as c:
        if not c.execute("SELECT 1 FROM incidents WHERE id = ?", (incident_id,)).fetchone():
            raise HTTPException(404, "incident not found")
        cur = c.execute("INSERT INTO incident_notes(incident_id, text, created_at) VALUES (?, ?, ?)",
                        (incident_id, text, int(time.time())))
        return {"id": cur.lastrowid, "text": text, "notes": _notes(c, incident_id)}


@app.delete("/api/incidents/{incident_id}/notes/{note_id}")
def delete_note(incident_id: int, note_id: int):
    with db.session(write=True) as c:
        if not c.execute("DELETE FROM incident_notes WHERE id = ? AND incident_id = ?", (note_id, incident_id)).rowcount:
            raise HTTPException(404, "note not found")
        return {"deleted": note_id, "notes": _notes(c, incident_id)}


@app.get("/api/report")
def get_report(days: int = Query(7, ge=1, le=90)):
    """What Kepler saw over the last `days` days: incidents, how long they lasted, labels, outages, mutes."""
    from . import report
    with db.session() as c:
        r = report.build(c, days)
    return {**r, "text": report.text(r)}


@app.post("/api/report/send")
def send_report(days: int = Query(7, ge=1, le=90)):
    """Post the report to Slack and every email destination (for a weekly cron: `kepler report --send`)."""
    from . import report
    with db.session(write=True) as c:
        r = report.build(c, days)
        return {"sent": report.send(c, r), "text": report.text(r)}


class Feedback(BaseModel):
    label: int | None = Field(None, ge=0, le=1)  # 1 = real incident, 0 = false alarm, null = clear


@app.post("/api/incidents/{incident_id}/feedback")
def incident_feedback(incident_id: int, body: Feedback):
    with db.session(write=True) as c:
        if not c.execute("SELECT 1 FROM incidents WHERE id = ?", (incident_id,)).fetchone():
            raise HTTPException(404, "incident not found")
        c.execute("UPDATE incidents SET feedback = ? WHERE id = ?", (body.label, incident_id))
        n = c.execute("SELECT COUNT(*) n FROM incidents WHERE feedback IS NOT NULL").fetchone()["n"]
    return {"ok": True, "labels": n}


# ---------------------------------------------------------------- model tiers (Orbit / Area / Time)

BENCH_FILE = Path(__file__).resolve().parent / "engine" / "tier_benchmark.json"


@app.get("/api/tiers")
def list_tiers():
    with db.session() as c:
        st = db.get_settings(c)
        usage = {t: 0 for t in tiers.TIERS}
        for m in c.execute("SELECT * FROM metrics").fetchall():
            usage[tiers.of(m, st).id] += 1
    bench = json.loads(BENCH_FILE.read_text()) if BENCH_FILE.exists() else {}
    out = {"default": st.get("model_tier", tiers.DEFAULT_TIER), "paywall": tiers.PAYWALL,
           "tiers": [{**t.public(), "metrics": usage[t.id], "benchmark": bench.get(t.id)} for t in tiers.TIERS.values()]}
    if tiers.PAYMENTS_ENABLED:
        preview = sum(tiers.TIERS[t].price_per_metric_month * n for t, n in usage.items())
        out["monthly_preview"] = {"amount": preview, "charged": 0.0, "currency": "USD"}
    return out


@app.get("/api/metrics/{metric_id}/compare")
def compare_tiers(metric_id: int):
    """Run all three models on this metric's latest data, cold (no cache), and compare verdict, speed and cost.
    The models run in a child process, and the result is reused until something it depends on changes
    (engine/compare.py)."""
    with db.session() as c:
        m = _metric(c, metric_id)
        last_ts = c.execute("SELECT MAX(ts) t FROM points WHERE metric_id = ?", (m["id"],)).fetchone()["t"]
        if not last_ts:
            raise HTTPException(400, "metric has no data yet")
        end = min(bucket_of(time.time()) - BUCKET, last_ts)
        st = db.get_settings(c)
    rows, reused = compare.latest(dict(m), end, st)
    return {"metric": m["name"], "at": end, "current": tiers.of(m, st).id, "tiers": rows, "paywall": tiers.PAYWALL,
            **({"reused": True} if reused else {})}


# ---------------------------------------------------------------- models

# ---------------------------------------------------------------- billing (Razorpay; disabled: Kepler is free)
# Every route below refuses while billing is off (see kepler/billing): nothing is sent to Razorpay and nothing is
# charged. The webhook route doesn't even exist from the outside until billing is on (404).

class CheckoutIn(BaseModel):
    plan: str = Field(min_length=1, max_length=40)


class VerifyIn(BaseModel):
    razorpay_payment_id: str = Field(min_length=1, max_length=80)
    razorpay_signature: str = Field(min_length=1, max_length=200)
    razorpay_order_id: str = Field("", max_length=80)
    razorpay_subscription_id: str = Field("", max_length=80)


@app.get("/api/billing")
def billing_status():
    return billing.status()


@app.post("/api/billing/checkout")
def billing_checkout(body: CheckoutIn):
    try:
        return razorpay.checkout(body.plan)
    except billing.BillingDisabled as e:
        raise HTTPException(403, str(e)) from None
    except razorpay.CheckoutError as e:
        raise HTTPException(400, str(e)) from None


@app.post("/api/billing/verify")
def billing_verify(body: VerifyIn):
    try:
        plan = razorpay.verify_checkout(body.razorpay_payment_id, body.razorpay_signature,
                                        body.razorpay_order_id, body.razorpay_subscription_id)
    except billing.BillingDisabled as e:
        raise HTTPException(403, str(e)) from None
    except razorpay.CheckoutError as e:
        raise HTTPException(400, str(e)) from None
    return {"plan": plan, "status": "active"}


@app.post("/api/billing/webhook/razorpay")
async def billing_webhook(request: Request):
    if not billing.charging_enabled():
        raise HTTPException(404, "billing is disabled")
    body = await request.body()
    if len(body) > 1024 * 1024:
        raise HTTPException(413, "webhook body too large")
    try:
        return razorpay.handle_webhook(body, request.headers)
    except billing.BillingDisabled:
        raise HTTPException(404, "billing is disabled") from None
    except (razorpay.CheckoutError, ValueError) as e:
        raise HTTPException(400, str(e)) from None


@app.get("/api/models")
def models():
    with db.session() as c:
        rows = c.execute(
            "SELECT m.id, m.name, COUNT(md.slice) slices, MAX(md.trained_at) trained_at, "
            "MAX(CASE WHEN md.slice = '' THEN md.params_json END) params "
            "FROM metrics m LEFT JOIN models md ON md.metric_id = m.id GROUP BY m.id ORDER BY m.id").fetchall()
        out = []
        for r in rows:
            p = json.loads(r["params"]) if r["params"] else None
            out.append({"metric_id": r["id"], "metric": r["name"], "kind": "custom" if p else "base",
                        "slices_trained": r["slices"], "trained_at": r["trained_at"],
                        "period": ("weekly" if p and p["period"] == 7 * DAY else "daily") if p else None,
                        "trained_days": round(p["n_days"], 1) if p else None,
                        "profile": p["profile"][:: max(1, len(p["profile"]) // 168)] if p else None})
        fm = FeedbackModel.load(c)
        labels = c.execute("SELECT SUM(feedback = 1) pos, SUM(feedback = 0) neg, SUM(feedback IS NULL) unl FROM incidents").fetchone()
        return {"metrics": out, "feedback": {**fm.meta, "active": fm.pipe is not None, "weight": fm.weight},
                "labels": {k: labels[k] or 0 for k in labels.keys()}}


_train_lock = threading.Lock()


TRAIN_COOLDOWN_S = 60
# models retrain on their own this often, and as soon as a metric has the 7 days of data a custom model needs. (Daily
# was measured too: on the NAB benchmark it let models absorb slow-building anomalies, 4 fewer timely catches and 5%
# more false alarms than weekly.)
AUTO_TRAIN_EVERY_S = 7 * 86400
AUTO_TRAIN_CHECK_S = 3600       # how often the worker looks


def retrain_due(conn, now: float) -> bool:
    """Should the worker retrain? When models are a week old (AUTO_TRAIN_EVERY_S), or a metric has the 7 days of data a
    custom model needs but has none yet. Without this, a server kept the models from its first `kepler train`."""
    last = conn.execute("SELECT MAX(trained_at) t FROM models").fetchone()["t"]
    if last and now - last >= AUTO_TRAIN_EVERY_S:
        return True
    untrained = conn.execute(
        "SELECT 1 FROM metrics m WHERE NOT EXISTS (SELECT 1 FROM models WHERE metric_id = m.id) AND "
        "(SELECT MAX(ts) - MIN(ts) FROM points p WHERE p.metric_id = m.id) >= ? LIMIT 1", (7 * 86400,)).fetchone()
    return bool(untrained)


def _auto_train(now: float) -> None:
    if not config.AUTO_TRAIN or state["seeding"] or now - state.get("auto_train_checked", 0) < AUTO_TRAIN_CHECK_S:
        return
    state["auto_train_checked"] = now
    with db.session() as c:
        due = retrain_due(c, now)
    if due:  # in its own thread: training takes seconds and scoring must not wait for it
        threading.Thread(target=train, kwargs={"force": True}, daemon=True, name="kepler-auto-train").start()


@app.post("/api/models/train")
def train(force: bool = False):
    """Fit on a read connection, then write the results in one short transaction. Concurrent requests share one run,
    and a run in the last minute is reused (models cannot meaningfully change that fast) unless force=true."""
    last = state.get("last_train")
    if last and not force and time.time() - state.get("last_train_at", 0) < TRAIN_COOLDOWN_S:
        return {**last, "reused": True}
    if not _train_lock.acquire(blocking=False):
        with _train_lock:  # someone else is training: wait for it and return its report
            return state.get("last_train") or {"metrics": [], "feedback": {}}
    try:
        with db.session() as rc:
            rec = detector.DeferredWrites(rc)
            report = detector.train_all(rec)
        with db.session(write=True) as wc:
            rec.apply(wc)
        detector.bump_models()
        state["last_train"], state["last_train_at"] = report, time.time()
        return report
    finally:
        _train_lock.release()


# ---------------------------------------------------------------- push API (public, key-authenticated)

class IngestPoint(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    value: float
    ts: float | None = None
    dims: dict[str, str] | None = None
    agg: str = Field("sum", pattern="^(sum|mean)$")


class IngestBody(BaseModel):
    metrics: list[IngestPoint] = Field(..., max_length=10000)


def _check_key(key: str | None):
    if not key or not secrets.compare_digest(key, db.get_settings().get("api_key", "")):
        raise HTTPException(401, "invalid or missing X-Kepler-Key")


@app.post("/api/v1/ingest")
def ingest(body: IngestBody, x_kepler_key: str | None = Header(None)):
    _check_key(x_kepler_key)
    now = time.time()
    by_metric: dict[str, list] = {}
    with db.session(write=True) as c:
        ids = {}
        for p in body.metrics:
            if not math.isfinite(p.value):
                continue
            if p.name not in ids:
                ids[p.name] = db.ensure_metric(c, p.name, agg=p.agg, source="push")
            by_metric.setdefault(p.name, []).append((p.ts or now, segment_key(p.dims), p.value, 1.0))
        for name, rows in by_metric.items():
            db.add_points(c, ids[name], rows, mode="add")
    return {"accepted": sum(len(r) for r in by_metric.values()), "metrics": list(by_metric)}


@app.get("/api/v1/decision/{metric_name}")
def latest_decision(metric_name: str, x_kepler_key: str | None = Header(None)):
    """Typed decision for a metric right now: 'normal' or the open anomaly. Built for machines (CI gates, bots)."""
    _check_key(x_kepler_key)
    with db.session() as c:
        m = c.execute("SELECT * FROM metrics WHERE name = ?", (metric_name,)).fetchone()
        if not m:
            raise HTTPException(404, "metric not found")
        incs = c.execute("SELECT * FROM incidents WHERE metric_id = ? AND status = 'open' ORDER BY confidence DESC",
                         (m["id"],)).fetchall()
        if incs:
            return {"decision": "anomaly", "incidents": [detector.decision(i, m) for i in incs]}
        last_ts = c.execute("SELECT MAX(ts) t FROM points WHERE metric_id = ?", (m["id"],)).fetchone()["t"] or 0
        upto = min(bucket_of(time.time()) - BUCKET, last_ts) if last_ts else bucket_of(time.time()) - BUCKET
        settled = _settled_by_metric(c).get(m["name"])
        if settled:  # pulled metric: judge the last bucket that was complete at the last successful pull
            upto = min(upto, settled)
        sc = detector.score_window(c, m, upto, days=detector.HISTORY_DAYS)
        z, v, e = float(detector.shown_z(c, m, sc, len(sc["ts"]) - 1)[0]), float(sc["v"][-1]), float(sc["expected"][-1])
        rel = (v - e) / max(abs(e), 1e-9) if math.isfinite(v) and math.isfinite(e) else 0.0
        # exactly the evaluation the alerting path uses (direction, min change %, sensitivity)
        run = detector.run_length(sc["z"], len(sc["z"]) - 1)
        is_anom, prob, _, _ = detector.evaluate(m, "", upto, v, e, z, lambda: float(sc["base_z"][-1]), max(run, 1),
                                                FeedbackModel.load(c), db.get_settings(c))
        prob = prob if math.isfinite(z) and math.isfinite(e) else None
        verdict = "watch" if is_anom else "normal"
        return {"decision": verdict, "metric": m["name"], "observed": _clean(v), "expected": _clean(e),
                "expected_range": [_clean(max(float(sc["lower"][-1]), 0.0)), _clean(float(sc["upper"][-1]))],
                "change_pct": _clean(rel * 100), "z_score": _clean(z),
                "anomaly_probability": None if prob is None else round(prob, 3),
                "model": sc["model"].label, "at": upto}


# ---------------------------------------------------------------- CSV + connectors

@app.post("/api/import/csv")
async def import_csv(file: UploadFile = File(...), metric: str = Form(""), agg: str = Form("sum"),
                     bad_direction: str = Form("both")):
    raw = await file.read(MAX_CSV_BYTES + 1)  # never read more than the limit into memory
    if len(raw) > MAX_CSV_BYTES:
        raise HTTPException(413, "CSV larger than 50 MB")
    try:
        return connectors.import_csv(raw, metric or None, agg, bad_direction)
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e)) from e


class ConnectorIn(BaseModel):
    type: str
    name: str
    interval_s: int = Field(300, ge=60, le=86400)
    config: dict


def _pull_type(t: str):
    integ = REGISTRY.get(t)
    if not integ or integ.direction != "pull":
        raise HTTPException(400, f"unknown pull integration '{t}'")
    return integ


def _redact(cfg: dict, ctype: str | None = None) -> dict:
    import re
    out = dict(cfg)
    secret = REGISTRY[ctype].secret_fields() if ctype in REGISTRY else set()
    for k in secret | {"token", "secret", "api_key", "app_key", "secret_key", "secret_access_key"}:
        if out.get(k):
            out[k] = "••••"
    if "dsn" in cfg:  # show host/db but not the password
        out["dsn"] = re.sub(r"(://[^:/@]+:)[^@]+@", r"\1••••@", cfg["dsn"])
        out["dsn"] = re.sub(r"(password=)\S+", r"\1••••", out["dsn"])
    return out


@app.get("/api/integrations")
def integrations():
    return [i.public() for i in REGISTRY.values()]


@app.get("/api/connectors")
def list_connectors():
    with db.session() as c:
        return [{**{k: r[k] for k in r.keys() if k != "config_json"}, "config": _redact(json.loads(r["config_json"]), r["type"]),
                 "label": REGISTRY[r["type"]].label if r["type"] in REGISTRY else r["type"]}
                for r in c.execute("SELECT * FROM connectors ORDER BY id").fetchall()]


@app.post("/api/connectors/test")
def test_connector(body: ConnectorIn):
    _pull_type(body.type)
    try:
        pts = connectors.fetch(body.type, body.config)
    except Exception as e:
        return {"ok": False, "message": f"{type(e).__name__}: {str(e)[:300]}"}
    segs = sorted({p[1] for p in pts})[:10]
    return {"ok": True, "message": f"{len(pts)} points, {len(segs)} segment(s)", "sample": pts[:5], "segments": segs}


@app.post("/api/connectors")
def create_connector(body: ConnectorIn):
    _pull_type(body.type)
    if not body.config.get("metric"):
        raise HTTPException(400, "config.metric (the metric name) is required")
    with db.session(write=True) as c:
        cur = c.execute("INSERT INTO connectors(type, name, config_json, interval_s) VALUES (?,?,?,?)",
                        (body.type, body.name, json.dumps(body.config), body.interval_s))
        cid = cur.lastrowid
    return {"id": cid}


@app.post("/api/connectors/{cid}/run")
def run_connector(cid: int):
    with db.session() as c:
        row = c.execute("SELECT * FROM connectors WHERE id = ?", (cid,)).fetchone()
    if not row:
        raise HTTPException(404, "connector not found")
    ok, msg, n = connectors.run(row)
    return {"ok": ok, "message": msg, "points": n}


@app.delete("/api/connectors/{cid}")
def delete_connector(cid: int):
    with db.session(write=True) as c:
        c.execute("DELETE FROM connectors WHERE id = ?", (cid,))
    return {"deleted": cid}


# ---------------------------------------------------------------- destinations (write incidents back into other tools)

class DestinationIn(BaseModel):
    type: str
    name: str
    config: dict
    min_severity: str = Field("medium", pattern="^(medium|high|critical)$")


def _dest_type(t: str):
    integ = REGISTRY.get(t)
    if not integ or integ.direction != "destination":
        raise HTTPException(400, f"unknown destination '{t}'")
    return integ


SAMPLE_DECISION = {
    "decision": "anomaly", "incident_id": 0, "metric": "kepler_test", "slice": None, "status": "open",
    "direction": "spike", "severity": "medium", "confidence": 0.99, "observed": 1.0, "expected": 0.0,
    "expected_range": [0.0, 0.5], "change_pct": 100.0, "z_score": 9.9, "where": [], "started_at": 0,
    "last_seen_at": 0, "model": {"baseline": "test"},
}


@app.get("/api/destinations")
def list_destinations():
    with db.session() as c:
        return [{**{k: r[k] for k in r.keys() if k != "config_json"}, "config": _redact(json.loads(r["config_json"]), r["type"]),
                 "label": REGISTRY[r["type"]].label if r["type"] in REGISTRY else r["type"]}
                for r in c.execute("SELECT * FROM destinations ORDER BY id").fetchall()]


@app.post("/api/destinations/test")
def test_destination(body: DestinationIn):
    integ = _dest_type(body.type)
    d = {**SAMPLE_DECISION, "started_at": int(time.time()), "last_seen_at": int(time.time())}
    try:
        integ.send(body.config, d, "test", None)
        return {"ok": True, "message": f"Test event sent to {integ.label}"}
    except Exception as e:
        return {"ok": False, "message": f"{type(e).__name__}: {str(e)[:300]}"}


@app.post("/api/destinations")
def create_destination(body: DestinationIn):
    _dest_type(body.type)
    with db.session(write=True) as c:
        cur = c.execute("INSERT INTO destinations(type, name, config_json, min_severity) VALUES (?,?,?,?)",
                        (body.type, body.name, json.dumps(body.config), body.min_severity))
        return {"id": cur.lastrowid}


@app.delete("/api/destinations/{did}")
def delete_destination(did: int):
    with db.session(write=True) as c:
        c.execute("DELETE FROM destinations WHERE id = ?", (did,))
        c.execute("DELETE FROM destination_refs WHERE destination_id = ?", (did,))
    return {"deleted": did}


# ---------------------------------------------------------------- inbound receivers (Segment, OpenTelemetry)

def _store(source: str, series: dict[tuple[str, str], list]) -> dict:
    now = time.time()
    with db.session(write=True) as c:
        for (name, agg), rows in series.items():
            mid = db.ensure_metric(c, name, agg=agg, source=source)
            db.add_points(c, mid, [(ts or now, seg, v, n) for ts, seg, v, n in rows], mode="add")
    return {"accepted": sum(len(r) for r in series.values()), "metrics": sorted({n for n, _ in series})}


def _key_from(request: Request, key: str | None) -> str | None:
    if key:
        return key
    auth = request.headers.get("authorization", "")
    return request.headers.get("x-kepler-key") or (auth[7:] if auth.lower().startswith("bearer ") else None)


async def _json_body(request: Request):
    try:
        return await request.json()
    except ValueError:
        raise HTTPException(400, "body is not valid JSON") from None


@app.post("/api/v1/hooks/segment")
async def segment_hook(request: Request, key: str | None = Query(None), dims: str = Query("")):
    """Segment Webhook destination. Auth: ?key=… or X-Kepler-Key / Authorization: Bearer header."""
    _check_key(_key_from(request, key))
    body = await _json_body(request)
    parsed = parse_segment(body, [d.strip() for d in dims.split(",") if d.strip()])
    return _store("segment", {(name, "sum"): rows for name, rows in parsed.items()})


@app.post("/v1/metrics")
async def otlp_metrics(request: Request):
    """OTLP/HTTP metrics receiver (JSON encoding). Auth: X-Kepler-Key or Authorization: Bearer header."""
    _check_key(_key_from(request, None))
    if "json" not in request.headers.get("content-type", ""):
        raise HTTPException(415, "Kepler accepts OTLP/HTTP with JSON encoding: set the exporter's encoding to json")
    body = await _json_body(request)
    if not isinstance(body, dict):
        raise HTTPException(400, "expected an OTLP ExportMetricsServiceRequest object")
    try:
        with db.session(write=True) as c:
            series = parse_otlp(body, c)
    except (AttributeError, TypeError, KeyError, ValueError) as e:  # structurally broken payload
        raise HTTPException(400, f"malformed OTLP payload: {type(e).__name__}") from e
    result = _store("otlp", series)
    return {"partialSuccess": {}, **result}


# ---------------------------------------------------------------- settings / notifications

class SettingsIn(BaseModel):
    sensitivity: float | None = Field(None, ge=0.05, le=0.99)
    min_change_pct: float | None = Field(None, ge=0, le=500)
    slack_webhook_url: str | None = None
    demo_mode: bool | None = None
    model_tier: str | None = Field(None, pattern="^(orbit|area|time)$")
    muted_until: int | None = Field(None, ge=0)  # maintenance mode: pause every alert until then; 0 = end it


@app.get("/api/settings")
def get_settings():
    s = db.get_settings()
    return {"sensitivity": float(s["sensitivity"]), "min_change_pct": float(s["min_change_pct"]),
            "slack_webhook_url": s.get("slack_webhook_url", ""), "demo_mode": s.get("demo_mode") == "1",
            "api_key": s["api_key"], "bucket_seconds": BUCKET, "model_tier": s.get("model_tier", tiers.DEFAULT_TIER),
            "muted_until": _maintenance_until(s)}


def _maintenance_until(settings: dict) -> int:
    until = int(float(settings.get("muted_until") or 0))
    return until if until > time.time() else 0


@app.put("/api/settings")
def put_settings(body: SettingsIn):
    if body.slack_webhook_url and not body.slack_webhook_url.startswith("https://hooks.slack.com/"):
        raise HTTPException(400, "Slack webhook URLs start with https://hooks.slack.com/")
    if (body.muted_until or 0) > time.time() + MAX_MUTE_S:
        raise HTTPException(400, "maintenance mode can last at most 30 days")
    for k, v in body.model_dump().items():
        if v is None:
            continue
        db.set_setting(k, ("1" if v else "0") if isinstance(v, bool) else str(v))
    return get_settings()


@app.post("/api/settings/rotate-key")
def rotate_key():
    db.set_setting("api_key", "kp_" + secrets.token_hex(16))
    return get_settings()


@app.post("/api/settings/test-slack")
def test_slack():
    url = db.get_settings().get("slack_webhook_url", "")
    if not url:
        raise HTTPException(400, "set a Slack webhook URL first")
    ok, msg = send_test(url)
    return {"ok": ok, "message": msg}


@app.get("/api/notifications")
def notifications(limit: int = 50):
    with db.session() as c:
        rows = c.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT ?", (min(limit, 200),)).fetchall()
        return [{**dict(r), "payload": json.loads(r["text"])} for r in rows]


# ---------------------------------------------------------------- demo

@app.get("/api/demo/scenarios")
def scenarios():
    return [{"id": k, "label": v["label"], "metric": v["metric"], "where": v["where"]} for k, v in simulator.SCENARIOS.items()]


class InjectIn(BaseModel):
    scenario: str


def _require_demo():
    """Demo controls can fake incidents and wipe data: they only exist while demo mode is on."""
    if db.get_settings().get("demo_mode") != "1":
        raise HTTPException(404, "demo mode is off")


@app.post("/api/demo/inject")
def inject(body: InjectIn):
    _require_demo()
    if body.scenario not in simulator.SCENARIOS:
        raise HTTPException(404, "unknown scenario")
    if state["seeding"]:
        raise HTTPException(409, "demo data is still being generated")
    info = simulator.inject(body.scenario)
    upto = bucket_of(time.time()) - BUCKET
    with db.session() as rc:
        detector.prewarm(rc, rc.execute("SELECT * FROM metrics WHERE name = ?", (info["metric"],)).fetchone(), upto)
    with db.session(write=True) as c:
        m = c.execute("SELECT * FROM metrics WHERE name = ?", (info["metric"],)).fetchone()
        detector.score_latest(c, m, upto, notify_fn=notify, max_stale=detector.PREWARMED_S)
        inc = c.execute("SELECT id FROM incidents WHERE metric_id = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
                        (m["id"],)).fetchone()
    return {**info, "incident_id": inc["id"] if inc else None}


@app.post("/api/demo/reset")
def reset_demo():
    _require_demo()
    if state["seeding"]:
        raise HTTPException(409, "already seeding")
    simulator._injections.clear()
    threading.Thread(target=_seed_demo, daemon=True).start()
    return {"ok": True}


# ---------------------------------------------------------------- frontend (production build)

_BUNDLED = Path(__file__).resolve().parent / "web"                                # inside an installed wheel
_REPO_BUILD = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"  # a development checkout
# installed package: the bundled copy; source checkout: whichever build is newer (so a fresh `npm run build` shows up)
_builds = [p for p in (_BUNDLED, _REPO_BUILD) if (p / "index.html").exists()]
DIST = max(_builds, key=lambda p: (p / "index.html").stat().st_mtime) if _builds else _REPO_BUILD
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith(("api/", "v1/")):
            raise HTTPException(404, "not found")
        f = (DIST / path).resolve()
        ok = path and f.is_file() and f.is_relative_to(DIST.resolve())
        if ok:
            return FileResponse(f)
        # the page itself is always revalidated, so an upgrade shows up on the next load (its assets are hashed)
        return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache"})
