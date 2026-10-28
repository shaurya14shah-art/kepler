"""Baseline models: what *should* a metric be right now?

Two models, same output (expected value + noise scale per bucket):

* BaseModel   - shared, zero-training. Median of the same time-of-day over the
                previous 7 days, level-adjusted, with a rolling robust (MAD) scale.
                Works from day 2 for any customer.
* CustomModel - trained per customer and per metric on their own history. Learns a
                weekly (or daily) seasonal profile and a time-of-day noise profile,
                with past incidents removed from the training data.
"""
import time
import warnings

import numpy as np
import pandas as pd
from scipy.special import betainc, ndtri, pdtr, pdtrc

from ..db import BUCKET, DAY, WEEK

MAD_K = 1.4826
BAND_Z = 3.0
# tail calibration (CustomModel.fit): each training day's top 0.5% of z (pooled, as alerts use it), against where a well-calibrated
# z sits at that quantile; the median over days is how much heavier this series' tails are than the model assumes
TAIL_Q, TAIL_REF, TAIL_MAX = 0.995, 2.576, 6.0
# training drops points the untrained model finds wildly anomalous (|z| > 4), but at most this share of them: for a
# high-volume series that model's noise is far too small, and a fixed |z| > 4 would leave a profile and a noise
# estimate from the few points that happened to fit (NYC taxi: 1% noise, so ordinary ±20% swings scored |z| 30)
CLEAN_MAX_SHARE = 0.02


def _floors(expected: np.ndarray, agg: str) -> np.ndarray:
    e = np.abs(np.nan_to_num(expected, nan=0.0))
    floor = 0.03 * e
    if agg == "sum":  # counts are at least Poisson-noisy
        floor = np.maximum(floor, np.sqrt(np.maximum(e, 1.0)))
    return np.maximum(floor, 1e-6)


def _weekend(ts: np.ndarray) -> np.ndarray:
    return (((ts // 86400) + 3) % 7) >= 5


def _robust_center(stack: np.ndarray, trimmed: bool) -> np.ndarray:
    """Median, or for counts a mean that drops the highest and lowest day (less jumpy at small values)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        med = np.nanmedian(stack, axis=0)
        if not trimmed:
            return med
        cnt = np.sum(~np.isnan(stack), axis=0)
        tot = np.nansum(stack, axis=0)
        tm = (tot - np.nanmax(stack, axis=0) - np.nanmin(stack, axis=0)) / np.maximum(cnt - 2, 1)
    return np.where(cnt >= 4, tm, med)


def _seasonal_median(ts: np.ndarray, v: np.ndarray, period: int, lags: int, trimmed: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """Median of the same time-of-day on previous days, preferring days of the same type (weekday/weekend)."""
    n = len(v)
    stack = np.full((lags, n), np.nan)
    same = np.full((lags, n), np.nan)
    wk = _weekend(ts)
    for k in range(1, lags + 1):
        shift = k * period
        if shift < n:
            stack[k - 1, shift:] = v[: n - shift]
            match = wk[shift:] == wk[: n - shift]
            same[k - 1, shift:] = np.where(match, v[: n - shift], np.nan)
    med_all = _robust_center(stack, trimmed)
    med_same = _robust_center(same, trimmed)
    n_same = np.sum(~np.isnan(same), axis=0)
    med = np.where(n_same >= 3, med_same, med_all)
    return med, np.sum(~np.isnan(stack), axis=0)


def _level_factor(v: np.ndarray, e: np.ndarray, window: int, lo=0.7, hi=1.4, fill=1.0) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(np.abs(e) > 1e-9, v / e, np.nan)
    lvl = pd.Series(ratio).shift(1).rolling(window, min_periods=max(3, window // 4)).median().to_numpy()
    return np.clip(np.nan_to_num(lvl, nan=fill), lo, hi)


def _poisson_z(v, e):
    """Exact Poisson tail probability of observing v when e is expected, as a signed z-score."""
    v = np.nan_to_num(np.round(np.maximum(v, 0)), nan=0.0)
    lam = np.maximum(np.nan_to_num(e, nan=0.0), 1e-6)
    low = v < lam
    # only the relevant tail per bucket (scipy.special directly: the scipy.stats wrappers cost more than the math)
    p = np.empty(len(v)) if np.ndim(v) else np.empty(())
    p[low] = pdtr(v[low], lam[low])                      # P(X <= v)
    p[~low] = pdtrc(v[~low] - 1, lam[~low])              # P(X >= v)
    z = 0.0 - ndtri(np.clip(p, 1e-300, 0.5))             # = norm.isf (+0.0, not -0.0, at the median)
    return np.where(low, -z, z)


def _mixed_poisson_z(v, lam, extra):
    """_poisson_z for a count whose expected value lam is itself uncertain, with variance `extra`: the exact tail of a
    Poisson whose rate is gamma-distributed around lam (a negative binomial). Near lam it is a z on lam + extra; far out
    (an outage's zeros) it is the tail the rate's uncertainty really allows, not a z shrunk by a fixed factor."""
    v = np.nan_to_num(np.round(np.maximum(v, 0)), nan=0.0)
    lam = np.maximum(np.nan_to_num(lam, nan=0.0), 1e-6)
    extra = np.maximum(np.nan_to_num(extra, nan=0.0), 1e-6 * lam)
    n, q = lam ** 2 / extra, lam / (lam + extra)
    low = v < lam
    p = np.empty(len(v))
    p[low] = betainc(n[low], v[low] + 1, q[low])          # P(X <= v)
    p[~low] = betainc(v[~low], n[~low], 1 - q[~low])       # P(X >= v)  (v >= 1 here)
    z = 0.0 - ndtri(np.clip(p, 1e-300, 0.5))
    return np.where(low, -z, z)


POOLING = (3, 6, 12)
SMOOTH = 5  # the custom profile is a moving average of this many positions' medians (CustomModel.fit)


def _median_var(n):
    """Variance of the median of n draws per unit variance of one draw: pi / (2n + 1) is within 1% of the exact value
    for normal draws (4% for even n >= 4); up to 2 draws it is their mean. A position with no data counts as one."""
    n = np.asarray(n, dtype=float)
    return np.where(n >= 3, np.pi / (2 * n + 1), 1 / np.clip(n, 1, 2))


def _expectation_var(e, s2, q, windows):
    """Var(sum of e) over each pooling window ending at each bucket, for the custom model's e = profile x level.
    e: expected values, s2: one bucket's variance, q: _median_var of each bucket's profile position, padded by
    SMOOTH // 2 positions on both sides. Both errors are shared within a window, so they do not average out like the
    buckets' own noise: each position's median feeds SMOOTH neighbouring buckets, and the level is an average ratio
    over the previous day (CustomModel.score), whose error (the day's noise and its profile's) every bucket shares."""
    h = SMOOTH // 2
    raw = q * np.pad(np.nan_to_num(s2), h, mode="edge")  # each position's median, in today's units
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = np.nan_to_num((1 + q[h:len(q) - h]) * s2 / e ** 2, nan=0.0, posinf=0.0)  # each bucket's share
        csum, i = np.concatenate([[0.0], np.cumsum(rel)]), np.arange(len(rel))
        lvl = np.nan_to_num((csum[i] - csum[np.maximum(i - DAY, 0)]) / np.minimum(i, DAY) ** 2)  # (the day before i)
    out = {}
    for w in windows:
        k = (np.convolve(np.ones(w), np.ones(SMOOTH)) / SMOOTH) ** 2  # each nearby position's weight in the window sum
        se = pd.Series(e).rolling(w, min_periods=w).sum().to_numpy()
        out[w] = np.concatenate([np.full(w - 1, np.nan), np.convolve(raw, k, mode="valid")]) + se ** 2 * lvl
    return out


def _tailed(z, tail):
    """z divided by a learned tail factor for its direction ((up, down); None: no calibration)."""
    if not tail:
        return z
    return np.where(z > 0, z / tail[0], z / tail[1])




NATIVE_STEPS = (12, 6, 4, 3, 2)  # coarser reporting intervals Kepler recognises, in buckets (an hour down to 10 min)


def native_step(v: np.ndarray) -> int:
    """How many buckets one reading covers: 1 for data that changes every 5 minutes. A metric reported every 30 or 60
    minutes (held, or spread over its buckets) only changes on a regular grid: k when at least 90% of its value
    changes fall on one phase of a k-bucket grid (noisy 5-minute data changes anywhere, so ~1/k of its changes would)."""
    ok = np.isfinite(v)
    idx = np.nonzero(ok)[0]
    if len(idx) < 48:
        return 1
    changes = idx[1:][np.diff(v[idx]) != 0]
    if len(changes) < 24:
        return 1
    for k in NATIVE_STEPS:
        if np.bincount(changes % k, minlength=k).max() >= 0.9 * len(changes):
            return k
    return 1


def _finish(v, e, scale, agg, kind, windows=POOLING, prof_q=None, tail=None):
    # a coarser metric (one reading per k buckets): a pooled window of w buckets carries only ~w/k readings' evidence
    # (its buckets repeat the same reading). (Pooling over 3/6/12 readings instead of buckets was tried: more false
    # alarms on the NAB benchmark, and no more timely catches.)
    k = native_step(v)
    noise = scale  # one bucket's spread as the model estimates it: the floors are a margin for single buckets on top
    scale = np.maximum(scale, _floors(e, agg))
    lam = phi = None
    with np.errstate(invalid="ignore", divide="ignore"):
        if agg == "sum":
            # counts: exact Poisson test, inflated by how over-dispersed this series really is.
            # An expected count is never exactly 0: floor it by the series' recent average rate.
            recent = pd.Series(v).shift(1).rolling(DAY, min_periods=12).mean().to_numpy()
            lam = np.maximum(np.nan_to_num(e, nan=0.0), np.maximum(0.5, 0.3 * np.nan_to_num(recent, nan=0.0)))
            # (residual spread also contains the noise of the expectation itself: ~30% for a 4-6 day average)
            phi = np.clip(scale ** 2 / (1.3 * np.maximum(lam, 1.0)), 1.0, 25.0)
            z = _poisson_z(v, lam) / np.sqrt(phi)
        else:
            z = (v - e) / scale
        # a pooled window's sum is compared with the sum of e, which has errors of its own (not just the buckets' noise):
        # each profile position's median carries the noise of the values it was trained on (counts: at least Poisson)
        ev = None
        if prof_q is not None:
            s2 = noise ** 2 if agg != "sum" else lam * np.clip(noise ** 2 / (1.3 * np.maximum(lam, 1.0)), 1.0, 25.0)
            ev = _expectation_var(lam if agg == "sum" else e, s2, prof_q, windows)
        # sustained shifts: pool evidence over the last 3/6/12 buckets (catches small slices going quiet),
        # but only when the buckets consistently deviate the same way (not one old spike carried forward)
        z0 = z.copy()
        pool = {"v": v, "e": e, "scale": scale, "lam": lam, "phi": phi, "z0": z0, "agg": agg, "windows": windows, "ev": ev,
                "tail": tail, "k": k}
        for w in windows:
            # share of the window's own buckets that deviate the same way as the window as a whole
            pos = pd.Series((z0 > 0).astype(float)).rolling(w, min_periods=w).mean().to_numpy()
            neg = pd.Series((z0 < 0).astype(float)).rolling(w, min_periods=w).mean().to_numpy()
            zw = _window_z(pool, w, only=(np.abs(z0) >= 0.5) & ((pos >= 0.8) | (neg >= 0.8)))  # (where it may be used)
            zw = zw / np.sqrt(min(k, w))
            consistent = np.where(zw > 0, pos, neg)
            use = (np.isfinite(zw) & (np.sign(zw) == np.sign(z)) & (np.abs(z0) >= 0.5)
                   & (consistent >= 0.8) & (np.abs(zw) > np.abs(z)))
            z = np.where(use, zw, z)
        # a series whose own history is burstier than the model's noise needs a bigger surprise (scaling per direction
        # after pooling picks the same windows, since it never changes which of two same-sign z is larger)
        z = _tailed(z, tail)
    up, down = tail or (1.0, 1.0)
    return {
        "expected": e,
        "scale": scale,
        "z": z,
        "lower": e - BAND_Z * scale * down,
        "upper": e + BAND_Z * scale * up,
        "kind": kind,
        "pool": pool,  # what pooled_z needs to redo the pooling for one bucket
        "k": pool["k"],  # buckets per reading (native_step)
    }


def _window_z(p: dict, w: int, at=None, only=None) -> np.ndarray:
    """z of the sum of the last w buckets, at every bucket (NaN before the first w), only at bucket index `at`, or only
    where the mask `only` is set (NaN elsewhere: the tail probabilities are what costs)."""
    def roll(x, how="sum"):
        if at is not None:
            return np.array([getattr(np, how)(x[at - w + 1:at + 1])])
        return getattr(pd.Series(x).rolling(w, min_periods=w), how)().to_numpy()[k]
    k = slice(None) if only is None or at is not None else np.nonzero(only)[0]
    ev = None if not p.get("ev") else (p["ev"][w][k] if at is None else p["ev"][w][at:at + 1])
    if p["agg"] == "sum":
        pm, sv, sl = roll(p["phi"], "mean"), roll(p["v"]), roll(p["lam"])
        if ev is None:
            z = _poisson_z(sv, sl) / np.sqrt(pm)
        else:
            z = _mixed_poisson_z(sv, sl, ev / pm) / np.sqrt(pm)  # (so that near sl the variance is pm * sl + ev)
    else:
        z = (roll(p["v"]) - roll(p["e"])) / np.sqrt(roll(p["scale"] ** 2) + (0.0 if ev is None else ev))
    if isinstance(k, slice):
        return z
    out = np.full(len(p["v"]), np.nan)
    out[k] = z
    return out


def pooled_z(out: dict, i: int, blocked) -> float:
    """z at bucket i exactly as _finish pools it, but skipping every window that contains a blocked bucket
    (evidence already reported by an incident must not be pooled again)."""
    p = out["pool"]
    z0 = p["z0"]
    z = z0[i]
    blocked = sorted(blocked)
    with np.errstate(invalid="ignore", divide="ignore"):
        for w in p["windows"]:
            a = i - w + 1
            if a < 0 or any(a <= b <= i for b in blocked):
                continue
            sl = slice(a, i + 1)
            zw = _window_z(p, w, at=i)[0] / np.sqrt(min(p.get("k", 1), w))
            consistent = np.mean(z0[sl] > 0) if zw > 0 else np.mean(z0[sl] < 0)
            if (np.isfinite(zw) and np.sign(zw) == np.sign(z) and abs(z0[i]) >= 0.5
                    and consistent >= 0.8 and abs(zw) > abs(z)):
                z = zw
    return float(_tailed(np.float64(z), p.get("tail")))


def _clipped_level(v: np.ndarray, shape: np.ndarray, level: float, window: int) -> np.ndarray:
    """Recent level as a clipped mean ratio to the trained profile: robust to zeros and incidents."""
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.clip(v / np.maximum(shape * level, 1e-9), 0, 3)
    r = pd.Series(ratio).shift(1).rolling(window, min_periods=window // 4).mean().to_numpy()
    return level * np.nan_to_num(r, nan=1.0)


def _too_wild(bz: np.ndarray) -> np.ndarray:
    """Training points to drop as wildly anomalous: |z| > 4 under the untrained model, but at most the CLEAN_MAX_SHARE
    most extreme. A well-modelled series keeps exactly the |z| > 4 rule."""
    if CLEAN_MAX_SHARE >= 1 or not len(bz):
        return bz > 4.0
    return bz > max(4.0, float(np.quantile(bz, 1 - CLEAN_MAX_SHARE)))


class BaseModel:
    kind = "base"
    label = "Shared base model (14-day seasonal baseline)"

    def __init__(self, lags: int = 14, windows=POOLING):
        self.lags, self.windows = lags, windows
        if lags != 14:
            self.label = f"Shared base model ({lags}-day seasonal baseline)"

    def score(self, ts: np.ndarray, v: np.ndarray, agg: str) -> dict:
        seasonal, count = _seasonal_median(ts, v, DAY, self.lags, trimmed=(agg == "sum"))
        recent = pd.Series(v).shift(1).rolling(12, min_periods=3).median().to_numpy()
        e = np.where(count >= 2, seasonal, recent)
        e = e * np.where(count >= 2, _level_factor(v, seasonal, 24), 1.0)
        resid = v - e
        r = pd.Series(resid).shift(1)
        med = r.rolling(3 * DAY, min_periods=DAY // 2).median()
        mad = (r - med).abs().rolling(3 * DAY, min_periods=DAY // 2).median()
        scale = MAD_K * mad.to_numpy()
        scale = np.where(np.isnan(scale), np.nanstd(v) if np.isfinite(np.nanstd(v)) else 1.0, scale)
        return _finish(v, e, scale, agg, self.kind, self.windows)


class CustomModel:
    """Per-metric trained profile. params are JSON-serialisable."""

    kind = "custom"

    def __init__(self, params: dict):
        self.params = params
        self.period = params["period"]
        self.profile = np.asarray(params["profile"], dtype=float)
        self.rel_scale = np.asarray(params["rel_scale"], dtype=float)
        # training values behind each position's median (models trained before this was kept: one per period seen)
        per = params["n_days"] // 7 if self.period == WEEK else params["n_days"]
        self.profile_n = np.asarray(params.get("profile_n", np.full(self.period, per)), dtype=float)
        self.tail = params.get("tail")  # learned tail factors (_learn_tail); None for models trained before them

    @property
    def label(self):
        p = "weekly" if self.period == WEEK else "daily"
        return f"Custom {p} profile (trained on {self.params['n_days']:.0f} days)"

    def _pos(self, ts):
        if self.period == WEEK:
            # align weeks to Monday 00:00 UTC (epoch was a Thursday)
            return ((ts // BUCKET) + 3 * DAY) % WEEK
        return (ts // BUCKET) % DAY

    def score(self, ts: np.ndarray, v: np.ndarray, agg: str, windows=POOLING) -> dict:
        pos = self._pos(ts).astype(int)
        shape = self.profile[pos]
        # level = recent actual/shape ratio; the trained level until recent data exists
        e = shape * _clipped_level(v, shape, self.params["level"], DAY)
        tod = ((ts // BUCKET) % DAY).astype(int)
        scale = self.rel_scale[tod] * np.abs(e)
        h = SMOOTH // 2  # (ts is a run of consecutive buckets)
        near = np.concatenate([pos[0] - np.arange(h, 0, -1), pos, pos[-1] + np.arange(1, h + 1)]) % self.period
        return _finish(v, e, scale, agg, self.kind, windows, prof_q=_median_var(self.profile_n[near]), tail=self.tail)

    @staticmethod
    def fit(ts: np.ndarray, v: np.ndarray, agg: str, exclude: np.ndarray | None = None) -> "CustomModel | None":
        ok = ~np.isnan(v)
        n_days = ok.sum() / DAY
        if n_days < 7:
            return None
        # (choosing weekly / daily / flat by held-out fit was tried: on the NAB benchmark it cut false alarms 3-6% but
        # cost 1-2 timely catches, so the profile stays weekly with two weeks of data, daily before)
        period = WEEK if n_days >= 14 else DAY
        clean = v.copy()
        # drop known incidents and anything the base model finds wildly anomalous
        if exclude is not None:
            clean[exclude] = np.nan
        base = BaseModel().score(ts, v, agg)
        clean[_too_wild(np.abs(np.nan_to_num(base["z"])))] = np.nan

        if period == WEEK:
            pos = (((ts // BUCKET) + 3 * DAY) % WEEK).astype(int)
        else:
            pos = ((ts // BUCKET) % DAY).astype(int)
        df = pd.DataFrame({"pos": pos, "v": clean})
        prof = df.groupby("pos")["v"].median().reindex(range(period))
        n_pos = df.groupby("pos")["v"].count().reindex(range(period), fill_value=0)
        prof = prof.interpolate(limit_direction="both").fillna(np.nanmedian(clean))
        # circular smoothing
        arr = prof.to_numpy()
        padded = np.concatenate([arr[-(SMOOTH // 2):], arr, arr[:SMOOTH // 2]])
        arr = np.convolve(padded, np.ones(SMOOTH) / SMOOTH, mode="valid")
        level = float(np.nanmean(arr)) or 1.0
        shape = arr / level

        # relative noise per time-of-day, from in-sample residuals
        fitted = shape[pos] * _clipped_level(clean, shape[pos], level, DAY)
        with np.errstate(divide="ignore", invalid="ignore"):
            rel = (clean - fitted) / np.abs(fitted)
        tod = ((ts // BUCKET) % DAY).astype(int)
        rd = pd.DataFrame({"tod": tod, "r": rel})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            # per time-of-day MAD, vectorised (a per-group Python lambda was ~70% of training time)
            g = rd.groupby("tod")["r"]
            mad = MAD_K * (rd["r"] - g.transform("median")).abs().groupby(rd["tod"]).median()
        mad = mad.reindex(range(DAY)).interpolate(limit_direction="both")
        mad = mad.fillna(float(np.nanmedian(mad)) if mad.notna().any() else 0.1).to_numpy()
        mad = np.convolve(np.concatenate([mad[-6:], mad, mad[:5]]), np.ones(12) / 12, mode="valid")
        mad = np.clip(mad, 0.01, 5.0)

        model = CustomModel({
            "period": int(period),
            "profile": [round(float(x), 6) for x in shape],
            "rel_scale": [round(float(x), 6) for x in mad],
            "profile_n": [int(x) for x in n_pos],
            "level": level,
            "n_days": float(n_days),
            "trained_at": int(time.time()),
        })
        model.params["tail"] = model.tail = _learn_tail(model, ts, v, agg)
        return model


def _learn_tail(model: "CustomModel", ts: np.ndarray, v: np.ndarray, agg: str) -> list[float]:
    """(up, down): how much heavier this series' tails are than the model's noise, per direction, on the z that decides
    alerts (pooled windows that assume independent buckets included). Scored on the raw training data, bursts included
    (incidents are excluded from the profile, so the model alone never sees them): the median over training days of
    each day's 99.5th-percentile z, relative to 2.58. Bursts that happen most days raise it; a real incident fills
    hours of one day and moves the median of the days very little. (One factor per kind of evidence, single buckets
    and each pooling window apart, was tried: more false alarms and no more timely catches on the NAB benchmark.)"""
    z = model.score(ts, v, agg)["z"]  # (model.tail is still None: uncalibrated z)
    d = pd.DataFrame({"day": (ts // BUCKET) // DAY, "z": z}).dropna()
    d = d[d.groupby("day")["z"].transform("size") >= DAY // 2]  # whole-ish days only
    if d["day"].nunique() < 3:
        return [1.0, 1.0]
    g = d.groupby("day")["z"]
    up, down = np.nanmedian(g.quantile(TAIL_Q)), -np.nanmedian(g.quantile(1 - TAIL_Q))
    return [round(float(np.clip(x / TAIL_REF, 1.0, TAIL_MAX)), 3) for x in (up, down)]
