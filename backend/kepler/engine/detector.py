"""Detection loop: score buckets, open/extend/resolve incidents, emit typed decisions.

Each metric is watched as a whole *and* per slice (every single dimension value, e.g.
platform=android). Slices catch breakages too small to move the total; they use a
stricter threshold and stay quiet while the whole metric already has an open incident.
Values too small to watch all the time are screened every bucket instead (small_slices).
"""
import json
import math
import threading
import time
import logging
import warnings
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
from scipy.special import bdtr, bdtrc, ndtr, ndtri

from ..db import BUCKET, DAY, DATA_VERSION, changed_since, changed_spans, dumps, get_settings, session as db_session
from .classifier import FeedbackModel, features
from .drilldown import drilldown, located
from . import tiers
from .seasonal import MAD_K, BaseModel, CustomModel, _mixed_poisson_z, pooled_z

log = logging.getLogger("kepler.detector")

HISTORY_DAYS = 15
RESOLVE_AFTER = 3  # normal buckets in a row before an incident resolves...
RESOLVE_HOLD_MAX = 12  # ...or as many as it has lasted, up to an hour (resolve_after)
RECOVERY_P = 0.05  # a series counts as coming back after an incident once that is this unlikely to be chance
Z_MIN = 3.0
Z_MIN_SLICE = 4.0
MIN_SLICE_SHARE = 0.05  # watch slices from 5% of the metric; smaller ones are only screened (small_slices)


# ---------------------------------------------------------------- data access

_RAW: OrderedDict = OrderedDict()  # (metric_id, start, end) -> (data version, raw points): shared by all its slices
_RAW_LOCK = threading.Lock()
_RAW_SIZE = 24


def _raw_points(conn, metric, start: int, end: int):
    """Every stored point of the metric in [start, end], read once and shared by the whole metric and each slice
    (scoring 13 series used to scan the same rows 13 times). Returns (bucket index, segment code, value_sum, n, segs)."""
    key = (metric["id"], start, end)
    with _RAW_LOCK:
        hit = _RAW.get(key)
        spans = changed_spans(metric["id"], hit[0], start, end) if hit is not None else [(start, end)]
        if not spans:
            _RAW.move_to_end(key)
            return hit[1]
    version = DATA_VERSION.get(metric["id"], 0)  # read before loading, so a concurrent write invalidates us
    # writes almost always touch a few recent buckets: re-read just those and keep the rest of the cached window
    full = spans == [(start, end)]
    cur = getattr(conn, "conn", conn).cursor()  # (DeferredWrites wraps a connection)
    cur.row_factory = None  # plain tuples: no Row object per point
    rows = cur.execute("SELECT ts, segment, value_sum, n FROM points WHERE metric_id = ? AND ("
                       + " OR ".join(["ts BETWEEN ? AND ?"] * len(spans)) + ")",
                       (metric["id"], *[t for s in spans for t in s])).fetchall()
    ts, seg, vs, n = zip(*rows) if rows else ((), (), (), ())
    idx, seg = (np.asarray(ts, dtype=np.int64) - start) // BUCKET, np.asarray(seg, dtype=object)
    vs, n = np.asarray(vs, dtype=float), np.asarray(n, dtype=float)
    if not full:
        o_idx, o_codes, o_vs, o_ns, o_segs = hit[1]
        keep = np.ones(len(o_idx), dtype=bool)
        for lo, hi in spans:
            keep &= (o_idx < (lo - start) // BUCKET) | (o_idx > (hi - start) // BUCKET)
        idx, vs, n = np.concatenate([o_idx[keep], idx]), np.concatenate([o_vs[keep], vs]), np.concatenate([o_ns[keep], n])
        seg = np.concatenate([np.asarray(o_segs, dtype=object)[o_codes[keep]], seg])
    codes, segs = pd.factorize(seg) if len(seg) else (np.zeros(0, dtype=np.int64), [])
    raw = (idx, codes, vs, n, list(segs))
    with _RAW_LOCK:
        _RAW[key] = (version, raw)
        while len(_RAW) > _RAW_SIZE:
            _RAW.popitem(last=False)
    return raw


def load_total(conn, metric, start: int, end: int, slice_: str = "") -> tuple[np.ndarray, np.ndarray]:
    ts = np.arange(start, end + BUCKET, BUCKET, dtype=np.int64)
    idx, codes, vs, ns, segs = _raw_points(conn, metric, start, end)
    if slice_:  # the segments containing every part of the slice (e.g. platform=ios, or platform=ios|region=EU)
        needle = f"|{slice_}|"
        keep = np.array([needle in f"|{sg}|" for sg in segs], dtype=bool)
        sel = keep[codes] if len(segs) else np.zeros(0, dtype=bool)
        idx, vs, ns = idx[sel], vs[sel], ns[sel]
    ok = (idx >= 0) & (idx < len(ts))
    idx, vs, ns = idx[ok], vs[ok], ns[ok]
    tot = np.bincount(idx, weights=vs, minlength=len(ts))
    cnt = np.bincount(idx, weights=ns, minlength=len(ts))
    seen_b = np.bincount(idx, minlength=len(ts)) > 0
    with np.errstate(invalid="ignore", divide="ignore"):
        val = np.where(cnt != 0, tot / cnt, tot) if metric["agg"] == "mean" else tot
    v = np.where(seen_b, val, np.nan)
    if metric["agg"] == "sum":
        # a count with no events in a bucket is a real zero (e.g. an outage), not missing data,
        # as long as the source is still reporting (we never invent zeros after its last point)
        seen = np.where(~np.isnan(v))[0]
        if len(seen):
            last = len(v) if (metric["source"] in ("push", "demo") and end - ts[seen[-1]] <= 6 * 3600) else seen[-1] + 1
            v[seen[0]:last] = np.nan_to_num(v[seen[0]:last], nan=0.0)
    return ts, v


MAX_SLICES = 12          # per metric
MIN_SLICE_BUCKETS = 24   # a slice needs data in >= 2 hours' worth of buckets over the last day


def slices(conn, metric, upto: int) -> list[str]:
    """'' plus the dimension values worth watching on their own: a meaningful share of the metric, data that
    actually recurs (so one-off values like user ids don't become slices), and at most MAX_SLICES of them."""
    latest = conn.execute("SELECT MAX(ts) t FROM points WHERE metric_id = ? AND ts <= ?", (metric["id"], upto)).fetchone()["t"]
    upto = latest or upto
    rows = conn.execute(
        "SELECT segment, SUM(n) w, SUM(ABS(value_sum)) s, COUNT(*) b FROM points "
        "WHERE metric_id = ? AND ts > ? AND segment != '' GROUP BY segment",
        (metric["id"], upto - DAY * BUCKET),
    ).fetchall()
    weight, buckets = {}, {}
    for r in rows:
        w = (r["w"] if metric["agg"] == "mean" else r["s"]) or 0
        for part in r["segment"].split("|"):
            weight[part] = weight.get(part, 0) + w
            buckets[part] = buckets.get(part, 0) + r["b"]
    # every dimension partitions the metric, so a slice's share is its weight over the grand total
    total = sum(((r["w"] if metric["agg"] == "mean" else r["s"]) or 0) for r in rows) or 1
    keep = [p for p, w in weight.items() if w / total >= MIN_SLICE_SHARE and buckets[p] >= MIN_SLICE_BUCKETS]
    keep = sorted(keep, key=lambda p: -weight[p])[:MAX_SLICES]
    return [""] + sorted(keep)


SCREEN_DAYS = 7  # a small segment's screening baseline: the same time of day on this many previous days


def small_slices(conn, metric, first: int, upto: int, watched: list[str], days: int = HISTORY_DAYS) -> dict:
    """Segments too small to watch all the time that are worth scoring for buckets first..upto:
    {slice: (z bar, buckets where it may open an incident)}.

    Every dimension value that recurs like a watched slice (so never a one-off value such as a user id) but isn't
    watched is screened cheaply, from the points the metric's own scoring reads anyway, against the median of the same
    time of day on previous days. It is scored with the full model only where its change in a bucket, in the metric's
    bad direction, is as large as a watched slice's whole volume: MIN_SLICE_SHARE of the metric's level then (for a
    mean, its weighted pull on the metric's mean). The 5% rule applies to what moved, not to the segment's usual size: an 80x
    spike in a 2% segment qualifies, a burst of a handful of events in a tiny one never does, and a small segment going
    quiet still only shows through the total. Its full-model z must then pass a bar that gives all screened segments
    together the false-alarm rate of one watched slice (Bonferroni). A slice with an open incident is kept until it
    resolves, without opening new ones."""
    start = upto - days * DAY * BUCKET
    idx, codes, vs, ns, segs = _raw_points(conn, metric, start, upto)
    nb = (upto - start) // BUCKET + 1
    rows = np.bincount(codes[idx > idx.max() - DAY], minlength=len(segs)) if len(idx) else np.zeros(len(segs))
    recur: dict = {}  # dimension value -> rows over the last day (as slices() counts them)
    for code in np.nonzero(rows)[0]:
        for part in segs[code].split("|") if segs[code] else ():
            recur[part] = recur.get(part, 0) + rows[code]
    cand = sorted(p for p, r in recur.items() if r >= MIN_SLICE_BUCKETS and p not in watched)
    bar = max(Z_MIN_SLICE, float(-ndtri(ndtr(-Z_MIN_SLICE) / max(len(cand), 1))))
    out = {r["slice"]: (bar, frozenset()) for r in conn.execute(
        "SELECT DISTINCT slice FROM incidents WHERE metric_id = ? AND status = 'open'", (metric["id"],))
        if r["slice"] not in watched}
    cur = np.arange(max((first - start) // BUCKET, 0), nb)
    if not cand or not len(cur):
        return out
    lags = cur[None, :] - DAY * np.arange(1, SCREEN_DAYS + 1)[:, None]
    need = np.unique(np.concatenate([cur, lags[lags >= 0]]))
    pos = np.full(nb, -1)
    pos[need] = np.arange(len(need))
    p = pos[idx]
    keep = p >= 0
    p, c, v, n = p[keep], codes[keep], vs[keep], ns[keep]
    seen = np.bincount(p, minlength=len(need)) > 0  # (a bucket with no points at all is missing, not zero)
    tot_v, tot_n = np.bincount(p, weights=v, minlength=len(need)), np.bincount(p, weights=n, minlength=len(need))
    # each candidate's sum per needed bucket: a segment key holds one value per dimension
    row_of = {part: k for k, part in enumerate(cand)}
    by_dim: dict = {}  # dimension -> segment code -> candidate row (-1: none)
    for code, sg in enumerate(segs):
        for part in sg.split("|") if sg else ():
            if part in row_of:
                by_dim.setdefault(part.split("=", 1)[0], np.full(len(segs), -1))[code] = row_of[part]
    sv, sn = np.zeros(len(cand) * len(need)), np.zeros(len(cand) * len(need))
    for dim_rows in by_dim.values():
        r = dim_rows[c]
        m = r >= 0
        sv += np.bincount(r[m] * len(need) + p[m], weights=v[m], minlength=len(sv))
        sn += np.bincount(r[m] * len(need) + p[m], weights=n[m], minlength=len(sn))
    sv, sn = sv.reshape(len(cand), -1), sn.reshape(len(cand), -1)
    lp, cp = np.where(lags >= 0, pos[np.maximum(lags, 0)], -1), pos[cur]
    with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # (all-NaN medians: no history at that time of day)
        if metric["agg"] == "mean":
            seg_x, tot_x = np.where(sn > 0, sv / sn, np.nan), np.where(tot_n > 0, tot_v / tot_n, np.nan)
        else:
            seg_x, tot_x = np.where(seen, sv, np.nan), np.where(seen, tot_v, np.nan)
        seg_x, tot_x = np.column_stack([seg_x, np.full(len(cand), np.nan)]), np.append(tot_x, np.nan)  # (-1: missing)
        level = np.abs(np.nanmedian(tot_x[lp], axis=0))
        hot, bad = np.zeros((len(cand), len(cur)), dtype=bool), metric["bad_direction"]
        for k in range(0, len(cand), 64):  # (bounded memory when backfilling a long range of a busy dimension)
            base = np.nanmedian(seg_x[k:k + 64][:, lp], axis=1)
            if metric["agg"] == "mean":  # its samples' pull on the metric's mean
                change = (sv[k:k + 64, cp] - sn[k:k + 64, cp] * base) / np.where(tot_n[cp] > 0, tot_n[cp], np.nan)
            else:
                change = seg_x[k:k + 64, cp] - base
            way = change if bad == "up" else -change if bad == "down" else np.abs(change)
            hot[k:k + 64] = way >= MIN_SLICE_SHARE * level
    ts = start + cur * BUCKET
    for k in np.nonzero(hot.any(axis=1))[0]:
        out[cand[k]] = (bar, frozenset(int(t) for t in ts[hot[k]]))
    return out


def small_z(scored: dict, i: int) -> float:
    """A small segment's evidence at bucket i: that bucket alone, as it was promoted for (small_slices), and for counts
    the exact tail of the over-dispersed count: a negative binomial with the model's expected value, and a variance from
    how far this segment strays from it at this time of day (Pearson residuals within an hour of it on the previous
    days, robustly), if that is more than the model's own estimate. Its single spread for the whole day understates a
    bursty segment's busy hours; the Poisson tail scaled down by the over-dispersion is far too thin that far out; and
    pooling several buckets adds up a skewed series' small biases. Each lets ordinary bursts of a noisy segment through."""
    pool = scored.get("pool")
    if pool is None:
        return float(scored["z"][i])
    if pool["agg"] != "sum":
        return float(pool["z0"][i])
    v, lam = scored["v"], pool["lam"]
    near = (i - DAY * np.arange(1, HISTORY_DAYS)[:, None] + np.arange(-12, 13)).ravel()
    near = near[near >= 0]
    r = (v[near] - lam[near]) / np.sqrt(np.maximum(lam[near], 0.5))
    r = r[np.isfinite(r)]
    phi = pool["phi"][i]
    if len(r) >= 50:
        phi = np.fmax(phi, (MAD_K * np.median(np.abs(r - np.median(r)))) ** 2)
    return float(_mixed_poisson_z(v[i:i + 1], lam[i:i + 1], np.array([(phi - 1) * lam[i]]))[0])


def detection_slices(conn, metric, first: int, upto: int, tier, days: int = HISTORY_DAYS) -> tuple[list[str], dict]:
    """The series a scoring pass over buckets first..upto covers: the watched ones, plus the small segments worth a
    full model then (small_slices, also returned)."""
    watched = watched_slices(conn, metric, upto, tier)
    small = small_slices(conn, metric, first, upto, watched, days) if tier.slices else {}
    return watched + sorted(small), small


def tier_for(conn, metric) -> "tiers.Tier":
    return tiers.of(metric, get_settings(conn))


def watched_slices(conn, metric, upto: int, tier=None) -> list[str]:
    """The series the detection loop watches: Orbit watches the whole metric only."""
    tier = tier or tier_for(conn, metric)
    if not tier.slices:
        return [""]
    out = slices(conn, metric, upto)
    if tier.combos:
        out += combo_slices(conn, metric, upto, tier.combos)
    return out


def combo_slices(conn, metric, upto: int, limit: int) -> list[str]:
    """The busiest exact multi-dimension segments (e.g. 'platform=ios|region=EU') with recurring data."""
    rows = conn.execute(
        "SELECT segment, SUM(n) w, SUM(ABS(value_sum)) s, COUNT(*) b FROM points "
        "WHERE metric_id = ? AND ts > ? AND segment LIKE '%|%' GROUP BY segment",
        (metric["id"], upto - DAY * BUCKET)).fetchall()
    total = sum(((r["w"] if metric["agg"] == "mean" else r["s"]) or 0) for r in rows) or 1
    keep = [r for r in rows if ((r["w"] if metric["agg"] == "mean" else r["s"]) or 0) / total >= MIN_SLICE_SHARE
            and r["b"] >= MIN_SLICE_BUCKETS]
    keep.sort(key=lambda r: -((r["w"] if metric["agg"] == "mean" else r["s"]) or 0))
    return [r["segment"] for r in keep[:limit]]


def get_model(conn, metric, slice_: str = ""):
    row = conn.execute("SELECT params_json FROM models WHERE metric_id = ? AND slice = ?",
                       (metric["id"], slice_)).fetchone()
    return CustomModel(json.loads(row["params_json"])) if row else BaseModel()


# Scored windows are cached: overview, breakdown, decisions and the worker all ask for the same windows.
# Keys include the metric's data version and the model version, so any write or retrain invalidates them.
_CACHE: OrderedDict = OrderedDict()
_CACHE_LOCK = threading.Lock()
_CACHE_SIZE = 192
MODEL_VERSION = [0]


def bump_models():
    MODEL_VERSION[0] += 1


_LATEST: OrderedDict = OrderedDict()       # (metric, agg, slice, days) -> (computed_at, result): display fallback
_INFLIGHT: dict = {}                       # key -> Lock held by the thread computing it (single-flight)
_COMPUTE = threading.BoundedSemaphore(3)   # at most 3 scoring computations at once: no CPU thrash under load


def _cached(key, start, end, metric_id, max_stale: float = 0.0):
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit is not None and (not changed_since(metric_id, hit[0], start, end)
                                or time.monotonic() - hit[2] <= max_stale):
            _CACHE.move_to_end(key)
            return hit[1]
    return None


DISPLAY_STALE_S = 30.0    # charts may show a window up to this old even if data arrived since (5-min buckets)
DISPLAY_REFRESH_S = 300.0  # ... or up to this old while another request is already rescoring it
PREWARMED_S = 15.0        # score_latest right after prewarm: reuse what prewarm just scored


def score_window(conn, metric, end: int, days: int = HISTORY_DAYS, slice_: str = "", tier=None,
                 max_stale: float = 0.0, refreshing_ok: float = 0.0):
    """Read-only result: callers must not mutate the returned arrays (they may be shared through the cache).

    Concurrent callers asking for the same window wait for the one computation in flight instead of repeating it.
    max_stale: a cached window computed at most that many seconds ago is fine even if data has arrived since, so a
    steady stream of writes doesn't force every read to rescore 15 days. refreshing_ok (display only): when the cached
    window is out of date, return the previous result if it is at most that old and rescore in the background (the
    latest one for this series, even from before a retrain, a tier switch or the last bucket closing)."""
    tier = tier or tier_for(conn, metric)
    key = (metric["id"], metric["agg"], slice_, end, days, MODEL_VERSION[0], tier.id)
    start = end - days * DAY * BUCKET
    out = _cached(key, start, end, metric["id"], max_stale)
    if out is not None:
        return out
    with _CACHE_LOCK:
        lock = _INFLIGHT.setdefault(key, threading.Lock())
        prev = _CACHE.get(key)
        prev = (prev[2], prev[1]) if prev is not None else _LATEST.get(key[:3] + key[4:5])
        usable = prev is not None and refreshing_ok and time.monotonic() - prev[0] <= refreshing_ok
        queue = usable and key not in _QUEUED
        if queue:
            _QUEUED.add(key)
    if usable:
        # stale-while-revalidate: answer now, rescore off the request path. The window's lock is only taken once the
        # rescore actually starts, so callers that need a fresh window never wait behind the refresh queue.
        if queue:
            try:
                _REFRESH.submit(_refresh, key, metric, end, days, slice_, tier)
            except RuntimeError:  # interpreter shutting down
                with _CACHE_LOCK:
                    _QUEUED.discard(key)
        return prev[1]
    lock.acquire()
    try:
        return _compute(conn, key, metric, end, days, slice_, tier, max_stale)
    finally:
        lock.release()


def _compute(conn, key, metric, end, days, slice_, tier, max_stale=0.0):
    """Score a window into the cache. The caller holds the window's in-flight lock."""
    start = end - days * DAY * BUCKET
    out = _cached(key, start, end, metric["id"], max_stale)  # someone else may have just computed it
    if out is not None:
        return out
    version = DATA_VERSION.get(metric["id"], 0)  # read before loading, so a concurrent write invalidates us
    with _COMPUTE:
        out = _score_window(conn, metric, end, days, slice_, tier)
    with _CACHE_LOCK:
        _CACHE[key] = (version, out, time.monotonic())
        _LATEST[key[:3] + key[4:5]] = (time.monotonic(), out)
        _LATEST.move_to_end(key[:3] + key[4:5])
        while len(_LATEST) > _CACHE_SIZE:
            _LATEST.popitem(last=False)
        while len(_CACHE) > _CACHE_SIZE:
            _CACHE.popitem(last=False)
        _INFLIGHT.pop(key, None)
    return out


_REFRESH = ThreadPoolExecutor(max_workers=2, thread_name_prefix="kepler-refresh")
_QUEUED: set = set()  # keys with a background rescore queued or running (one each)


def _refresh(key, metric, end, days, slice_, tier):
    try:
        with _CACHE_LOCK:
            lock = _INFLIGHT.setdefault(key, threading.Lock())
        if not lock.acquire(blocking=False):
            return  # a request is computing it right now: that fills the cache
        try:
            with db_session() as c:
                _compute(c, key, metric, end, days, slice_, tier)
        finally:
            lock.release()
    except Exception:  # e.g. the metric was deleted meanwhile: the next read simply tries again
        log.exception("background rescoring failed")
    finally:
        with _CACHE_LOCK:
            _QUEUED.discard(key)


class Scored(dict):
    """A scored window. For a custom model, "base_z" (the shared base model's z, a classifier feature) is computed on
    first access: it costs as much as the custom scoring itself and only matters for buckets that pass the z gates."""

    def __missing__(self, key):
        if key != "base_z":
            raise KeyError(key)
        z = BaseModel().score(self["ts"], self["v"], self["agg"])["z"]
        self["base_z"] = z  # racing threads compute the same array; either assignment is fine
        return z


def _score_window(conn, metric, end: int, days: int, slice_: str, tier):
    start = end - days * DAY * BUCKET
    ts, v = load_total(conn, metric, start, end, slice_)
    model = get_model(conn, metric, slice_) if tier.custom_models else BaseModel(tier.base_lags, tier.pooling)
    if model.kind == "base" and not np.isfinite(v).any():  # no data (e.g. a slice that doesn't exist): all NaN anyway
        nan = np.full(len(ts), np.nan)
        return Scored(expected=nan, scale=nan, z=nan, lower=nan, upper=nan, kind=model.kind, pool=None, base_z=nan,
                      ts=ts, v=v, agg=metric["agg"], model=model, slice=slice_, tier=tier)
    out = model.score(ts, v, metric["agg"], tier.pooling) if model.kind == "custom" else model.score(ts, v, metric["agg"])
    out = Scored(out)
    if model.kind != "custom":
        out["base_z"] = out["z"]
    out["ts"], out["v"], out["agg"], out["model"], out["slice"], out["tier"] = ts, v, metric["agg"], model, slice_, tier
    return out


# ---------------------------------------------------------------- decisions

def severity(conf: float, rel: float) -> str:
    if conf >= 0.85 and abs(rel) >= 0.5:
        return "critical"
    if conf >= 0.7 or (conf >= 0.5 and abs(rel) >= 1.0):
        return "high"
    return "medium"


def decision(inc, metric) -> dict:
    """The typed, Jev-style decision object for an incident."""
    rel = (inc["observed"] - inc["expected"]) / max(abs(inc["expected"]), 1e-9)
    where = json.loads(inc["where_json"] or "[]")
    return {
        "decision": "anomaly",
        "incident_id": inc["id"],
        "metric": metric["name"],
        "slice": inc["slice"] or None,
        "status": inc["status"],
        "direction": inc["direction"],
        "severity": inc["severity"],
        "confidence": round(inc["confidence"], 3),
        "observed": round(inc["observed"], 2),
        "expected": round(inc["expected"], 2),
        "expected_range": [round(max(inc["lower"], 0), 2), round(inc["upper"], 2)],
        "change_pct": round(rel * 100, 1),
        "z_score": round(inc["z"], 2),
        "where": where,
        # how sure the drilldown is of `where` ("traffic=too low to localize" when a quiet hour cannot tell)
        "where_confidence": where[0].get("confidence") if where else None,
        "started_at": inc["start_ts"],
        "last_seen_at": inc["end_ts"],
        "model": json.loads(inc["model_json"] or "{}"),
        "tier": json.loads(inc["model_json"] or "{}").get("tier", tiers.DEFAULT_TIER),
        # "no_data": the metric stopped reporting (observed/expected are its last reading); else a value anomaly
        "kind": json.loads(inc["model_json"] or "{}").get("kind", "anomaly"),
        "silent_since": json.loads(inc["model_json"] or "{}").get("last_seen"),
    }


RELATED_WINDOW_S = 15 * 60  # incidents that start this close together are likely one problem


def related_incidents(conn, inc) -> list[dict]:
    """Other incidents (any metric) that started within RELATED_WINDOW_S of this one: an api_errors spike and a sign-ups
    drop at the same minute are usually one outage, and on-call should see them together."""
    rows = conn.execute(
        "SELECT i.*, m.name AS metric_name FROM incidents i JOIN metrics m ON m.id = i.metric_id "
        "WHERE i.id != ? AND i.start_ts BETWEEN ? AND ? ORDER BY ABS(i.start_ts - ?) LIMIT 10",
        (inc["id"], inc["start_ts"] - RELATED_WINDOW_S, inc["start_ts"] + RELATED_WINDOW_S, inc["start_ts"])).fetchall()
    out = []
    for r in rows:
        kind = json.loads(r["model_json"] or "{}").get("kind", "anomaly")
        rel = (r["observed"] - r["expected"]) / max(abs(r["expected"]), 1e-9)
        out.append({"incident_id": r["id"], "metric": r["metric_name"], "slice": r["slice"] or None, "kind": kind,
                    "direction": r["direction"], "severity": r["severity"], "status": r["status"],
                    "started_at": r["start_ts"], "change_pct": round(rel * 100, 1)})
    return out


def reasoning(conn, inc, metric) -> dict:
    """Time model: link the incident to everything else going on, size its impact, and explain the decision."""
    d = decision(inc, metric)
    m = d["model"]
    pad = 3 * BUCKET
    rows = conn.execute(
        "SELECT i.*, m.name AS metric_name, m.unit AS metric_unit FROM incidents i JOIN metrics m ON m.id = i.metric_id "
        "WHERE i.id != ? AND i.start_ts <= ? AND i.end_ts >= ? ORDER BY i.start_ts LIMIT 10",
        (inc["id"], inc["end_ts"] + pad, inc["start_ts"] - pad)).fetchall()
    mine = {(w["dimension"], w["value"]) for w in d["where"] if located(w)}
    related = []
    for r in rows:
        where = json.loads(r["where_json"] or "[]")
        theirs = {(w["dimension"], w["value"]) for w in where if located(w)}
        shared = sorted(f"{k}={v}" for k, v in mine & theirs)
        related.append({"incident_id": r["id"], "metric": r["metric_name"], "direction": r["direction"],
                        "severity": r["severity"], "started_at": r["start_ts"], "shared": shared,
                        "where": [f"{w['dimension']}={w['value']}" for w in where if located(w)],
                        "likely_same_cause": bool(shared) or abs(r["start_ts"] - inc["start_ts"]) <= pad})
    buckets = (inc["end_ts"] - inc["start_ts"]) // BUCKET + 1
    impact = m.get("impact")
    unit = metric["unit"] or metric["name"]
    if impact is None:
        impact_text = None
    elif metric["agg"] == "sum":
        impact_text = f"≈ {abs(impact):,.0f} {unit} {'fewer' if impact < 0 else 'more'} than expected so far"
    else:
        impact_text = f"{impact / buckets:+.3g} {metric['unit'] or ''} vs normal on average for {buckets * 5} min".strip()
    where_txt = ", ".join(f"{w['dimension']}={w['value']} ({w['share_of_change']:.0%} of the change)"
                          for w in d["where"] if located(w)) or "spread across all segments"
    if d["where"] and not d["where"][0].get("localized", True):
        where_txt = (f"traffic too low to localize: too few events to tell which segment broke "
                     f"(best guess only {d['where_confidence'] or 0:.0%} sure)")
    steps = [
        f"Observed {d['observed']:g} vs an expected {d['expected']:g} (normal {d['expected_range'][0]:g}–"
        f"{d['expected_range'][1]:g}): {abs(d['change_pct']):.0f}% {'above' if d['direction'] == 'spike' else 'below'}, "
        f"z = {d['z_score']:.1f}, for {buckets} bucket{'s' if buckets != 1 else ''} ({buckets * 5} min).",
        f"Where: {where_txt}.",
    ]
    if impact_text:
        steps.append(f"Impact: {impact_text}.")
    same = [x for x in related if x["likely_same_cause"]]
    if same:
        steps.append("Linked: " + "; ".join(
            f"#{x['incident_id']} {x['metric']} {x['direction']}" + (f" on {', '.join(x['shared'])}" if x["shared"] else "")
            for x in same) + ", started together, so likely one root cause.")
    elif related:
        steps.append(f"Also happening: {len(related)} unrelated incident(s) in the same window.")
    else:
        steps.append("Isolated: no other metric moved at the same time.")
    if m.get("prior") is not None:
        learned = (f" blended with {m['learned']:.2f} learned from your labels (weight {m.get('weight', 0):.0%})"
                   if m.get("learned") is not None else "")
        steps.append(f"Confidence {d['confidence']:.2f}: statistical evidence {m['prior']:.2f}{learned}.")
    return {"impact": impact, "impact_text": impact_text, "related": related, "steps": steps}


def run_length(zs: np.ndarray, i: int, cap: int = 12) -> int:
    """How many buckets in a row (ending at i) deviate in the same direction (|z| >= 2)."""
    if not math.isfinite(zs[i]):
        return 0
    sign, n = np.sign(zs[i]), 0
    while i - n >= 0 and n < cap and math.isfinite(zs[i - n]) and abs(zs[i - n]) >= 2 and np.sign(zs[i - n]) == sign:
        n += 1
    return n


def evaluate(metric, slice_: str, ts: int, v: float, e: float, z: float, base_z, duration: int,
             fm: FeedbackModel, settings: dict, tier=None, z_min: float | None = None):
    """Returns (is_anomaly, confidence, rel, info) for one bucket. base_z may be a callable (only called when needed).
    z_min: a stricter bar than the series' usual one (a small segment's, see small_slices)."""
    if not all(map(math.isfinite, (v, e, z))):
        return False, 0.0, 0.0, {}
    rel = (v - e) / max(abs(e), 1e-9)
    z_min = z_min or (Z_MIN_SLICE if slice_ else Z_MIN)
    if abs(z) < z_min or abs(rel) * 100 < float(settings.get("min_change_pct", 15)):
        return False, 0.0, rel, {}
    bad = metric["bad_direction"]
    if (bad == "up" and z < 0) or (bad == "down" and z > 0):
        return False, 0.0, rel, {}
    if callable(base_z):
        base_z = base_z()
    feats = features(z, base_z, rel, duration, ts, metric["agg"])
    if tier is not None and not tier.learned_filter:
        fm = FeedbackModel()  # statistical prior only
    conf, p0, p1 = fm.confidence(feats, z, rel)
    info = {"prior": round(p0, 3), "learned": None if p1 is None else round(p1, 3), "weight": round(fm.weight, 2),
            "tier": tier.id if tier else tiers.DEFAULT_TIER,
            "features": [round(f, 4) for f in feats]}
    return conf >= float(settings.get("sensitivity", 0.5)), conf, rel, info


def _where(conn, metric, window, slice_, observed, expected, depth: int = 1, conf: float = 0.0):
    inner = drilldown(conn, metric, window, slice_, depth=depth)
    if not slice_:
        return inner
    parts = [p.split("=", 1) for p in slice_.split("|")]
    dim, val = " × ".join(p[0] for p in parts), " × ".join(p[1] for p in parts)
    # the slice is where the anomaly was detected: as sure as the detection itself
    head = {"dimension": dim, "value": val, "share_of_change": 1.0,
            "change_pct": round((observed - expected) / abs(expected) * 100, 1) if abs(expected) > 0.05 else None,
            "confidence": round(conf, 3)}
    # inside a slice, only add a second hint when it pins down a single value. The drilldown only names one that holds
    # most of the slice's own excess (level-free), so the slice may turn out to be where a break elsewhere shows
    # loudest: region=EU at its peak hour loses the most signups when android breaks everywhere
    extra = [w for w in inner if located(w)]
    return [head] + (extra if len(extra) == 1 else [])


def _where_rank(where: list) -> tuple:
    """How well a drilldown's answer is supported: one that names a segment first (a significant localization outweighs
    'all segments' or 'too low to localize'), then by confidence (-1: none, or stored before drilldowns had one)."""
    return (located(where[0]), where[0].get("confidence", -1.0)) if where else (False, -1.0)


def _refresh_where(conn, inc, where: list, peak: bool = False) -> bool:
    """Keep the best-supported localization an incident has had: evidence about *where* grows while it is open (a
    quiet hour may only be localizable after a few more buckets), and a weaker later window must not replace it.
    A slice incident's first entry is the slice itself: it follows the incident's peak (peak=True), as before."""
    old = json.loads(inc["where_json"] or "[]")
    k = 1 if inc["slice"] else 0
    new = (where[:k] if peak else old[:k]) + (where[k:] if _where_rank(where[k:]) > _where_rank(old[k:]) else old[k:])
    if new == old:
        return False
    conn.execute("UPDATE incidents SET where_json = ? WHERE id = ?", (dumps(new), inc["id"]))
    return True


def resolve_after(inc) -> int:
    """Normal buckets in a row before this incident resolves: RESOLVE_AFTER for a blip, as many as it has lasted for a
    longer one (at most RESOLVE_HOLD_MAX). The longer something was broken, the more calm it takes to call it fixed,
    so brief dips inside one long episode don't split it into many incidents and alerts."""
    lasted = (inc["end_ts"] - inc["start_ts"]) // BUCKET + 1
    return int(min(max(RESOLVE_AFTER, lasted), RESOLVE_HOLD_MAX))


def recent_incidents(conn, metric, t: int, lookback: int) -> list:
    """Incidents of this metric (any series) whose buckets or tail (at most one more lookback, see _tail_end) overlap
    the pooling lookback ending at bucket t."""
    return conn.execute("SELECT id, direction, start_ts, end_ts FROM incidents WHERE metric_id = ? AND end_ts >= ? "
                        "AND start_ts < ?", (metric["id"], t - 2 * lookback * BUCKET, t)).fetchall()


def _tail_end(z0: np.ndarray, sign: float, first: int, i: int, cap: int) -> int:
    """Last bucket (< i) of an incident's tail starting at `first`: the series counts as back once it has been normal
    (not deviating the incident's way by 0.5) RESOLVE_AFTER buckets in a row, as an incident needs to resolve. One
    noisy bucket on a small slice is not a recovery. A tail lasts at most `cap` buckets (one pooling lookback): a
    series still low after that is a problem of its own and may pool again."""
    run, stop = 0, min(i, first + cap)
    for k in range(max(first, 0), stop):
        run = run + 1 if z0[k] * sign < 0.5 else 0  # (a missing bucket is no recovery: NaN compares False)
        if run >= RESOLVE_AFTER:
            return k - run
    return stop - 1


def _recovering(pool: dict, sign: float, first: int, last: int, i: int) -> bool:
    """Has the series started to come back since an incident (buckets first..last), judged on the buckets after it
    up to i-1? Only then is what follows a tail. A slice still as far gone as during the incident (android at zero
    while the total that reported it already looks normal again) is not recovering more slowly: the outage is still
    going on for it, and its fresh buckets are evidence like any other.
    Counts: of the events in both periods, does the later one hold significantly more than its share of the expected
    (fewer, for a spike)? A conditional binomial test, so the rate itself need not be known. Means: a two-sample test
    of the periods' z-scores."""
    a, b = max(first, 0), last + 1
    if b >= i:
        return False
    if pool["agg"] == "sum":
        v, lam = np.nan_to_num(pool["v"]), pool["lam"]
        v_in, v_out = int(round(v[a:b].sum())), int(round(v[b:i].sum()))
        l_in, l_out = float(lam[a:b].sum()), float(lam[b:i].sum())
        n = v_in + v_out
        if n == 0 or l_out <= 0:
            return False
        share = l_out / (l_in + l_out)
        if sign < 0:  # a drop comes back with more events
            return v_out > 0 and bdtrc(v_out - 1, n, share) <= RECOVERY_P
        return bdtr(v_out, n, share) <= RECOVERY_P
    z_in, z_out = pool["z0"][a:b], pool["z0"][b:i]
    z_in, z_out = z_in[np.isfinite(z_in)], z_out[np.isfinite(z_out)]
    if not len(z_in) or not len(z_out):
        return False
    t = -sign * (z_out.mean() - z_in.mean()) / math.sqrt(1 / len(z_in) + 1 / len(z_out))
    return 0.5 * math.erfc(t / math.sqrt(2)) <= RECOVERY_P


def unreported_z(scored: dict, i: int, reported, own_open=None) -> float:
    """z at bucket i without pooling evidence an incident already reported.

    A pooled 6/12-bucket window that still holds an outage's buckets would otherwise keep a recovered metric
    'anomalous' until the window drains, or let a slice re-report the same outage once the parent incident closes.
    Buckets of any same-direction incident on this metric are off limits, except that the series' own open incident
    keeps its weak buckets: a slow drop found by pooling must be able to keep pooling to stay open.

    So is each such incident's tail when it reached this series (still deviating its way at the incident's last bucket):
    the buckets after it in which the series has not yet come back to its expected value (a slice that recovers
    slower than the rest, or a total still a bit low). Pooled over, that tail is the same outage again, not a new one;
    a later drop is new evidence once the series has been back (see _tail_end). A series that is not coming back at
    all has no tail (see _recovering): the incident's buckets stay off limits, its own later ones do not."""
    z = scored["z"][i]
    pool = scored.get("pool")
    if not reported or pool is None or not math.isfinite(z) or z == pool["z0"][i]:
        return z  # nothing was pooled, so nothing to take back
    z0 = pool["z0"]
    sign = 1.0 if z0[i] > 0 else -1.0
    direction = "spike" if sign > 0 else "drop"
    strong = Z_MIN_SLICE if scored["slice"] else Z_MIN
    t0, lo = int(scored["ts"][0]), i - max(pool["windows"]) + 1
    blocked = []
    for inc in reported:
        if inc["direction"] != direction:
            continue
        own = own_open is not None and inc["id"] == own_open["id"]
        last = (inc["end_ts"] - t0) // BUCKET
        for k in range(max((inc["start_ts"] - t0) // BUCKET, lo, 0), min(last, i - 1) + 1):
            if not own or abs(z0[k]) >= strong:
                blocked.append(k)
        # (only a series the incident reached has its tail, and only while it is coming back)
        if (not own and 0 <= last < i and z0[last] * sign >= 0.5
                and _recovering(pool, sign, (inc["start_ts"] - t0) // BUCKET, last, i)):
            blocked += range(max(last + 1, lo, 0), _tail_end(z0, sign, last + 1, i, max(pool["windows"])) + 1)
    return pooled_z(scored, i, blocked) if blocked else z


def shown_z(conn, metric, scored: dict, i0: int = 0) -> np.ndarray:
    """scored["z"] from index i0 as the alerting path judged it: without pooling evidence an incident already reported
    (so charts and breakdowns don't keep a recovered slice 'hot' while the pooled windows drain). A new array."""
    z = np.array(scored["z"][i0:], dtype=float)
    pool, ts = scored.get("pool"), scored["ts"]
    if pool is None or not len(z):
        return z
    lookback = 2 * max(pool["windows"]) * BUCKET  # an incident's buckets plus its tail (see recent_incidents)
    incs = conn.execute("SELECT id, slice, direction, start_ts, end_ts FROM incidents WHERE metric_id = ? AND end_ts >= ? "
                        "AND start_ts <= ?", (metric["id"], int(ts[i0]) - lookback, int(ts[-1]))).fetchall()
    if not incs:
        return z
    for j in np.nonzero(z != pool["z0"][i0:])[0]:  # only pooled buckets can change
        i = i0 + int(j)
        t = int(ts[i])
        rep = [x for x in incs if x["end_ts"] >= t - lookback and x["start_ts"] < t]
        if rep:
            # the series' own incident that this bucket would have extended (open at the time)
            own = next((x for x in rep if x["slice"] == scored["slice"] and x["end_ts"] >= t - resolve_after(x) * BUCKET),
                       None)
            z[j] = unreported_z(scored, i, rep, own)
    return z


def process_bucket(conn, metric, i: int, scored: dict, fm: FeedbackModel, settings: dict,
                   notify_fn=None, allow_open: bool = True, reported=None, small=None):
    """Apply the incident lifecycle for bucket index i of a scored window.

    Returns the incident id it touched, or with allow_open=False a ("candidate", |z|, direction) tuple when it
    would open a new incident (the caller picks one candidate per metric and direction). `reported` are the
    metric's recent incidents (recent_incidents): their buckets are not pooled again. `small`: the small segments
    being scored (small_slices), with their stricter bar and the buckets where they may open an incident."""
    slice_ = scored["slice"]
    ts = int(scored["ts"][i])
    v, e = scored["v"][i], scored["expected"][i]
    open_inc = conn.execute(
        "SELECT * FROM incidents WHERE metric_id = ? AND slice = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
        (metric["id"], slice_),
    ).fetchone()
    bar, hot = (small or {}).get(slice_, (None, None))
    z = small_z(scored, i) if bar is not None else unreported_z(scored, i, reported, open_inc)
    continuing = open_inc is not None and ts - open_inc["end_ts"] <= resolve_after(open_inc) * BUCKET
    k = scored.get("k") or 1  # buckets per reading: a coarser metric's duration counts readings, not buckets
    run = -(-run_length(scored["z"], i, cap=12 * k) // k)
    duration = max(run, -(-((ts - open_inc["start_ts"]) // BUCKET + 1) // k) if continuing else 1)
    tier = scored.get("tier") or tiers.get(None)
    is_anom, conf, rel, info = evaluate(metric, slice_, ts, v, e, z, lambda: scored["base_z"][i], duration, fm, settings,
                                        tier, bar)
    if is_anom and hot is not None and not continuing and ts not in hot:
        is_anom = False  # a small segment opens an incident only where its change was material
    model = scored["model"]
    feats = info.pop("features", None)
    model_info = {"baseline": model.label,
                  "filter": "shared prior" if info.get("learned") is None
                  else f"shared prior + feedback classifier ({fm.meta.get('n_labels', 0)} labels)",
                  **info}

    if is_anom and tier.reasoning:
        # Time: running impact in the metric's own units (sum of observed - expected over the incident)
        prev = json.loads(open_inc["model_json"] or "{}").get("impact", 0.0) if continuing else 0.0
        model_info["impact"] = round(prev + float(v - e), 3)
    # drill down over the last 30 min, never a single noisy bucket: the anomalous run so far and its onset, which
    # pooled detection flags a few buckets late when counts are small
    window = list(range(ts - 5 * BUCKET, ts + BUCKET, BUCKET))
    if is_anom:
        fields = dict(observed=float(v), expected=float(e), lower=float(scored["lower"][i]),
                      upper=float(scored["upper"][i]), z=float(z),
                      base_z=float(scored["base_z"][i]) if math.isfinite(scored["base_z"][i]) else None,
                      confidence=float(conf), severity=severity(conf, rel),
                      direction="spike" if z > 0 else "drop", peak_ts=ts, model_json=dumps(model_info),
                      features_json=dumps(feats))
        if continuing:
            conn.execute("UPDATE incidents SET end_ts = ? WHERE id = ?", (ts, open_inc["id"]))
            if "impact" in model_info:
                cur = json.loads(open_inc["model_json"] or "{}")
                conn.execute("UPDATE incidents SET model_json = ? WHERE id = ?",
                             (dumps({**cur, "impact": model_info["impact"]}), open_inc["id"]))
            # the peak is the bucket that deviates most; confidence only grows as the run goes on (a later, smaller
            # bucket with more evidence behind it raises the confidence but doesn't become the peak)
            peak = abs(z) > abs(open_inc["z"] or 0)
            if peak:
                conn.execute(f"UPDATE incidents SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                             [*fields.values(), open_inc["id"]])
            elif conf > (open_inc["confidence"] or 0):
                e0 = open_inc["expected"]
                rel0 = (open_inc["observed"] - e0) / max(abs(e0), 1e-9)
                conn.execute("UPDATE incidents SET confidence = ?, severity = ? WHERE id = ?",
                             (float(conf), severity(conf, rel0), open_inc["id"]))
            _refresh_where(conn, open_inc, _where(conn, metric, window, slice_, v, e, tier.drilldown, conf), peak)
            return open_inc["id"]
        if not allow_open:
            return ("candidate", abs(z), fields["direction"])
        if open_inc is not None:  # stale open incident with a gap: close it first
            conn.execute("UPDATE incidents SET status = 'resolved' WHERE id = ?", (open_inc["id"],))
        fields.update(metric_id=metric["id"], slice=slice_, start_ts=ts, end_ts=ts, status="open",
                      where_json=dumps(_where(conn, metric, window, slice_, v, e, tier.drilldown, conf)), created_at=ts)
        cur = conn.execute(f"INSERT INTO incidents({', '.join(fields)}) VALUES ({', '.join('?' * len(fields))})",
                           list(fields.values()))
        if notify_fn:
            notify_fn(conn, cur.lastrowid, "opened")
        return cur.lastrowid

    if open_inc is not None and continuing:
        # a normal bucket while the incident is still open: the window may now localize what the first ones could not
        _refresh_where(conn, open_inc, _where(conn, metric, window, slice_, open_inc["observed"], open_inc["expected"],
                                              tier.drilldown, open_inc["confidence"] or 0.0))
    if open_inc is not None and not continuing:
        conn.execute("UPDATE incidents SET status = 'resolved' WHERE id = ?", (open_inc["id"],))
        if notify_fn:
            notify_fn(conn, open_inc["id"], "resolved")
        return open_inc["id"]
    return None


SILENCE_MIN = 6  # a silence is never worth an alert before 30 minutes
NO_DATA_ALERTS = True  # (a switch for comparisons on the benchmark)
SILENCE_FACTOR = 3.0  # unusual = this many times the series' typical longest gap of a day (2x alerted on more
                      # routine gaps on the NAB benchmark, for no more catches)


def _silence_threshold(scored: dict, last: int):
    """Buckets without data that are unusual for this series, judged on the gaps between its readings before `last`
    (its most recent reading): SILENCE_FACTOR times the median over days of each day's longest gap, and at least 3
    readings and 30 minutes. A sensor that goes quiet for two hours every day is not alarming at two hours; one past
    outage doesn't make it deaf (a median of days). None while it has less than a day of readings to judge from."""
    cache = scored.setdefault("_silence", {})
    if last not in cache:
        v = scored["v"]
        seen = np.nonzero(np.isfinite(v[: last + 1]))[0]
        k = scored.get("k") or 1
        if len(seen) < max(24, DAY // (2 * k)) or seen[-1] - seen[0] < DAY:
            cache[last] = None
        else:
            gaps = pd.Series(np.diff(seen)).groupby(seen[1:] // DAY).max()  # each day's longest gap
            cache[last] = int(max(SILENCE_MIN, 3 * k, SILENCE_FACTOR * float(gaps.median())))
    return cache[last]


def _no_data(conn, metric, i: int, scored: dict, notify_fn=None):
    """A metric that has stopped reporting: open a "no data" incident once the silence is unusual for it (see
    _silence_threshold), keep it open while the silence lasts, resolve it when a reading arrives. Only for the whole
    metric, and only where a gap is a gap: pushed counts already read as zeros (and are judged as drops)."""
    v, ts = scored["v"], scored["ts"]
    t = int(ts[i])
    open_inc = conn.execute("SELECT * FROM incidents WHERE metric_id = ? AND slice = '' AND status = 'open' "
                            "AND model_json LIKE '%\"kind\":\"no_data\"%' ORDER BY id DESC LIMIT 1",
                            (metric["id"],)).fetchone()
    if math.isfinite(v[i]):
        if open_inc is not None:
            conn.execute("UPDATE incidents SET status = 'resolved' WHERE id = ?", (open_inc["id"],))
            if notify_fn:
                notify_fn(conn, open_inc["id"], "resolved")
        return
    seen = np.nonzero(np.isfinite(v[:i]))[0]
    if not len(seen):
        return
    last = int(seen[-1])
    limit = _silence_threshold(scored, last)
    if limit is None or i - last < limit:
        return
    if open_inc is not None:
        conn.execute("UPDATE incidents SET end_ts = ? WHERE id = ?", (t, open_inc["id"]))
        return
    e = float(scored["expected"][last]) if math.isfinite(scored["expected"][last]) else float(v[last])
    model = scored["model"]
    fields = dict(metric_id=metric["id"], slice="", start_ts=int(ts[last]) + BUCKET, end_ts=t, peak_ts=t,
                  observed=float(v[last]), expected=e, lower=e, upper=e, z=0.0, base_z=None, confidence=0.99,
                  severity="high", direction="drop", status="open", where_json="[]", created_at=t,
                  model_json=dumps({"kind": "no_data", "last_seen": int(ts[last]), "baseline": model.label,
                                    "silence_limit_min": limit * BUCKET // 60}))
    cur = conn.execute(f"INSERT INTO incidents({', '.join(fields)}) VALUES ({', '.join('?' * len(fields))})",
                       list(fields.values()))
    if notify_fn:
        notify_fn(conn, cur.lastrowid, "opened")


def _step(conn, metric, t: int, scored_all: list[dict], fm, settings, notify_fn=None, small=None):
    """One 5-minute window for one metric across all its series.

    Existing incidents are updated/resolved first. Then at most one new incident opens per direction: the
    strongest candidate, and only if no incident in that direction is already open. One outage = one alert,
    pinned on the series that shows it most clearly. A metric that has stopped reporting is a "no data" incident."""
    total = next((s for s in scored_all if not s["slice"]), None)
    if total is not None and NO_DATA_ALERTS:
        _no_data(conn, metric, (t - int(total["ts"][0])) // BUCKET, total, notify_fn)
    candidates = []
    lookback = max((max(s["pool"]["windows"]) for s in scored_all if s.get("pool")), default=1)
    reported = recent_incidents(conn, metric, t, lookback)
    for scored in scored_all:
        i = (t - int(scored["ts"][0])) // BUCKET
        r = process_bucket(conn, metric, i, scored, fm, settings, notify_fn, allow_open=False, reported=reported,
                           small=small)
        if isinstance(r, tuple):
            # prefer the simplest explanation: an exact segment (ios × EU) must be clearly stronger to beat 'ios'
            score = r[1] * (0.7 if "|" in scored["slice"] else 1.0)
            candidates.append((score, r[2], scored, i))
    for direction in ("spike", "drop"):
        busy = any(t - x["end_ts"] <= resolve_after(x) * BUCKET for x in conn.execute(
            "SELECT start_ts, end_ts FROM incidents WHERE metric_id = ? AND status = 'open' AND direction = ? AND end_ts >= ?",
            (metric["id"], direction, t - RESOLVE_HOLD_MAX * BUCKET)))
        best = max((c for c in candidates if c[1] == direction), key=lambda c: c[0], default=None)
        if best and not busy:
            process_bucket(conn, metric, best[3], best[2], fm, settings, notify_fn, allow_open=True, reported=reported,
                           small=small)


def _first_unscored(metric, upto: int) -> int:
    return max((metric["last_scored_ts"] or 0) + BUCKET, upto - 12 * BUCKET)


def prewarm(conn, metric, upto: int):
    """Compute (and cache) every window score_latest will need, using a *read* connection, so the write
    transaction that follows only does quick reads/writes instead of holding the lock while scoring."""
    tier = tier_for(conn, metric)
    for s in detection_slices(conn, metric, _first_unscored(metric, upto), upto, tier)[0]:
        score_window(conn, metric, upto, slice_=s, tier=tier)


def score_latest(conn, metric, upto: int, notify_fn=None, max_stale: float = 0.0):
    """Score every completed bucket after the metric's last_scored_ts, up to `upto`.

    max_stale: callers that just ran prewarm pass PREWARMED_S so the write transaction reuses those windows instead of
    rescoring under the write lock because a point arrived in between (equivalent to that point arriving late)."""
    first = _first_unscored(metric, upto)
    if first > upto:
        return
    fm = FeedbackModel.load(conn)
    settings = get_settings(conn)
    tier = tier_for(conn, metric)
    series, small = detection_slices(conn, metric, first, upto, tier)
    scored_all = [score_window(conn, metric, upto, slice_=s, tier=tier, max_stale=max_stale) for s in series]
    for t in range(first, upto + BUCKET, BUCKET):
        _step(conn, metric, t, scored_all, fm, settings, notify_fn, small)
    conn.execute("UPDATE metrics SET last_scored_ts = ? WHERE id = ?", (upto, metric["id"]))


def backfill(conn, metric, start: int, end: int):
    """Score history in one vectorised pass per slice (no notifications). Used for seeding and CSV imports."""
    days = (end - start) // (DAY * BUCKET) + HISTORY_DAYS
    fm = FeedbackModel.load(conn)
    settings = get_settings(conn)
    tier = tier_for(conn, metric)
    series, small = detection_slices(conn, metric, start, end, tier, days)
    scored_all = [score_window(conn, metric, end, days=days, slice_=s, tier=tier) for s in series]
    for t in range(start, end + BUCKET, BUCKET):
        _step(conn, metric, t, scored_all, fm, settings, small=small)
    conn.execute("UPDATE metrics SET last_scored_ts = MAX(last_scored_ts, ?) WHERE id = ?", (end, metric["id"]))


# ---------------------------------------------------------------- training

def train_all(conn, now: int | None = None) -> dict:
    """Fit a custom baseline per metric and slice, then the feedback classifier. Returns a report."""
    now = now or int(time.time()) // BUCKET * BUCKET
    report = {"metrics": [], "feedback": None}
    for metric in conn.execute("SELECT * FROM metrics").fetchall():
        start = now - 28 * DAY * BUCKET
        trained = 0
        label = None
        tier = tier_for(conn, metric)
        if not tier.custom_models:
            report["metrics"].append({"metric": metric["name"], "slices_trained": 0, "model": None,
                                      "status": f"{tier.name}: uses the shared model, nothing to train"})
            continue
        for slice_ in watched_slices(conn, metric, now, tier):
            ts, v = load_total(conn, metric, start, now, slice_)
            exclude = np.zeros(len(ts), dtype=bool)
            for inc in conn.execute(
                "SELECT start_ts, end_ts FROM incidents WHERE metric_id = ? AND (feedback IS NULL OR feedback = 1)",
                (metric["id"],),
            ):
                a = max(0, (inc["start_ts"] - start) // BUCKET - 2)
                b = min(len(ts), (inc["end_ts"] - start) // BUCKET + 3)
                exclude[a:b] = True
            model = CustomModel.fit(ts, v, metric["agg"], exclude)
            if model is None:
                continue
            conn.execute("INSERT OR REPLACE INTO models(metric_id, slice, kind, trained_at, n_points, params_json) "
                         "VALUES (?,?,?,?,?,?)",
                         (metric["id"], slice_, "custom", now, int((~np.isnan(v)).sum()), dumps(model.params)))
            trained += 1
            label = label or model.label
        report["metrics"].append({"metric": metric["name"], "slices_trained": trained,
                                  "status": "trained" if trained else "needs 7+ days of data (using base model)",
                                  "model": label})
    report["feedback"] = FeedbackModel.train(conn)
    bump_models()
    return report


class DeferredWrites:
    """Wraps a read connection: SELECTs run now, writes are recorded to apply later in one short transaction.
    Lets heavy training run without holding the database write lock."""

    def __init__(self, conn):
        self.conn = conn
        self.ops: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params=()):
        if sql.lstrip().split(None, 1)[0].upper() in ("INSERT", "UPDATE", "DELETE", "REPLACE"):
            self.ops.append((sql, tuple(params)))
            return None
        return self.conn.execute(sql, params)

    def apply(self, conn):
        for sql, params in self.ops:
            conn.execute(sql, params)
