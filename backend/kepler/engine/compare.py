"""All three models on one metric's latest data, side by side: verdict, speed and the most unusual series.

Each model scores every series it watches from scratch (no cache), so `ms` is what that model really costs. The scoring
runs in a child process. Inside the server it shares one GIL with every request thread, and under the stress test's 24
clients a comparison that takes ~0.5 s on its own took 17 s, once past the client's 30 s timeout: SQLite hands the GIL
back on every row it reads, so a cold 15-day read crawls (50 ms alone, 1-3 s next to a few busy threads), and the
scoring itself queued for the shared compute gate once per series. A result is reused until anything it depends on
changes: new points from its window on, a retrain, the alert settings, the metric's own settings, or the next bucket.
"""
import logging
import math
import multiprocessing
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future, ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

from .. import db
from ..db import BUCKET, DAY
from . import detector, tiers
from .classifier import FeedbackModel

log = logging.getLogger("kepler.compare")

ISOLATE = True       # score in the child process; False scores here (the fallback when no process can be started)
MAX_AGE_S = BUCKET   # reuse a result at most this long, even if nothing it depends on seems to have changed
_FOREVER = 2 ** 62   # slices are chosen from every point after the window's start, also points after `end`

_MEMO: OrderedDict = OrderedDict()  # key -> (data version, computed at, rows)
_MEMO_SIZE = 64
_INFLIGHT: dict = {}                # key -> Future of the comparison being computed: concurrent asks wait for it
_LOCK = threading.Lock()
_POOL = None
_POOL_LOCK = threading.Lock()
_LOCAL = threading.Lock()           # the in-process fallback runs one comparison at a time


def latest(metric: dict, end: int, settings: dict) -> tuple[list[dict], bool]:
    """Every model's verdict on `metric` at bucket `end` (one row per tier, as the API shows them), and whether the
    rows were reused from an earlier ask. `metric` is the metric's row and `settings` the workspace settings."""
    mid = metric["id"]
    key = (mid, end, metric["name"], metric["agg"], metric["bad_direction"], metric["source"],
           settings.get("sensitivity"), settings.get("min_change_pct"), detector.MODEL_VERSION[0])
    start = end - max(t.history_days for t in tiers.TIERS.values()) * DAY * BUCKET
    with _LOCK:
        hit = _MEMO.get(key)
        if (hit is not None and time.monotonic() - hit[1] <= MAX_AGE_S
                and not db.changed_since(mid, hit[0], start, _FOREVER)):
            _MEMO.move_to_end(key)
            return hit[2], True
        fut = _INFLIGHT.get(key)
        mine = fut is None
        if mine:
            fut = _INFLIGHT[key] = Future()
    if not mine:
        return fut.result(), False
    version = db.DATA_VERSION.get(mid, 0)  # read before scoring, so a write meanwhile invalidates the result
    try:
        scored = _run(metric, end, settings)
        rows = [_row(t, *scored[t.id]) for t in tiers.TIERS.values()]
    except BaseException as e:
        with _LOCK:
            _INFLIGHT.pop(key, None)
        fut.set_exception(e)
        raise
    with _LOCK:
        _MEMO[key] = (version, time.monotonic(), rows)
        while len(_MEMO) > _MEMO_SIZE:
            _MEMO.popitem(last=False)
        _INFLIGHT.pop(key, None)
    fut.set_result(rows)
    return rows, False


def _row(t: "tiers.Tier", n: int, ms: float, best: dict | None) -> dict:
    return {"tier": t.id, "name": t.name, "series_watched": n, "ms": ms,
            "verdict": "anomaly" if best and best["anomaly"] else "normal", "top": best,
            "learned_filter": t.learned_filter, "reasoning": t.reasoning,
            **({"price_preview": t.price_preview} if tiers.PAYMENTS_ENABLED else {})}


def compute(conn, metric, end: int, settings: dict) -> dict:
    """Score `metric` at bucket `end` with every model, from scratch.
    tier id -> (series watched, ms, the series with the highest confidence)."""
    fm = FeedbackModel.load(conn)
    out = {}
    for t in tiers.TIERS.values():
        t0 = time.perf_counter()
        best = None
        series = detector.watched_slices(conn, metric, end, t)
        for s in series:
            sc = detector._score_window(conn, metric, end, t.history_days, s, t)
            i = len(sc["ts"]) - 1
            v, e, z = float(sc["v"][i]), float(sc["expected"][i]), float(sc["z"][i])
            run = detector.run_length(sc["z"], i)
            anom, conf, rel, _ = detector.evaluate(metric, s, end, v, e, z, lambda sc=sc, i=i: float(sc["base_z"][i]),
                                                   max(run, 1), fm, settings, t)
            if best is None or conf > best["confidence"]:
                best = {"series": s or "(whole metric)", "anomaly": bool(anom), "confidence": round(conf, 3),
                        "observed": _finite(v), "expected": _finite(e), "z": _finite(z)}
        out[t.id] = (len(series), round((time.perf_counter() - t0) * 1000, 1), best)
    return out


def _finite(x: float) -> float | None:
    return x if math.isfinite(x) else None


# ---------------------------------------------------------------- the child process

def _run(metric: dict, end: int, settings: dict) -> dict:
    if ISOLATE:
        try:
            fut = _pool().submit(_isolated, str(db.DB_PATH), metric, end, settings)
        except Exception:  # processes can't be started here (or we are shutting down)
            log.warning("comparison process unavailable, comparing in the server instead", exc_info=True)
        else:
            try:
                return fut.result()
            except BrokenProcessPool:  # it died: answer from here, and start a new one next time
                log.warning("comparison process died, comparing in the server instead")
                shutdown()
    with _LOCAL, detector._COMPUTE, db.session() as c:
        return compute(c, metric, end, settings)


def _pool() -> ProcessPoolExecutor:
    global _POOL
    with _POOL_LOCK:
        if _POOL is None:  # started on the first comparison: ~0.5 s, then kept
            # spawn, not fork: forking a threaded server is unsafe
            _POOL = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"))
        return _POOL


def shutdown():
    """Stop the child process, if one is running (the next comparison starts a new one)."""
    global _POOL
    with _POOL_LOCK:
        pool, _POOL = _POOL, None
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)


def _isolated(db_path: str, metric: dict, end: int, settings: dict) -> dict:
    """compute(), in the child process. It never sees the server's writes, which are what keep the engine's caches
    valid, so every comparison reads the database afresh."""
    db.DB_PATH = Path(db_path)
    detector._RAW.clear()
    try:
        with db.session() as c:
            return compute(c, metric, end, settings)
    finally:
        detector._RAW.clear()
