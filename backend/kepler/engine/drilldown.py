"""Root-cause drilldown: *where* did the metric break?

Adtributor-style attribution, weighted by evidence. For every dimension value we compare the actual total in the
incident window with what that slice normally does (same time-of-day over the last 7 days) and ask whether it moved
*further than the metric as a whole*: its excess over a proportional share of the actual total. A level shift that
hits every slice alike (a quiet weekend that a 7-day history overestimates, say) cancels out of every share; a broken
slice does not. Adtributor ranks slices by how far their share moved; here that shift is measured in units of its
noise: the exact binomial test of the share for counts (inflated by the noise of the expectation itself, and by how
over-dispersed the history is where counts are big enough to tell), a normal test for means. A share that moved because 3 events landed differently
than usual is not a broken slice.

The result is one of
  * the dimension value(s) holding most of that excess, each significant at LOCATE_CONF after a Bonferroni correction
    over every value tested ("platform=android");
  * "all segments": no slice can have moved materially further than the rest (its multiplier off the rest's by
    SPREAD_RATIO), and the traffic is enough to be sure of that;
  * "traffic too low to localize": neither; too few events to tell. Its confidence is that of the best guess, below
    LOCATE_CONF, so a quiet hour never names a segment it cannot back up.
Every entry carries a confidence; share_of_change is the share of the raw change in the window, as before.
"""
import math
from collections import defaultdict

import numpy as np
from scipy.special import bdtr, bdtrc, ndtri

from ..db import BUCKET, DAY, parse_segment

MAD_K = 1.4826
EP_TARGET = 0.67       # the values named hold at least this much of the excess moving the metric's way
MIN_SHARE = 0.1        # ... and each moved with the total (share of the raw change)
LOCATE_CONF = 0.95     # family-wise confidence needed to name (or rule out) a segment
SPREAD_RATIO = 0.5     # "all segments" rules out any slice moving 50% further than the rest, the change's way
BIG_CELL = 10          # expected events in a bucket for past days' spread to say anything about over-dispersion
EXACT_MAX = 10 ** 7    # exact binomial tails up to this many events; the normal test is exact enough beyond
NO_LOCATION = {"dimension": "traffic", "value": "too low to localize", "localized": False}


def located(w: dict) -> bool:
    """A where-entry that names a segment (not 'all segments', not 'too low to localize')."""
    return w["dimension"] != "*" and w.get("localized", True)


def _segment_totals(conn, metric, window: list[int], within: str = ""):
    """segment -> (actual, expected, noise variance of actual - expected, over-dispersion evidence: spread and Poisson
    variance of its cells big enough to show it, bare Poisson variance) over the window."""
    lag = DAY * BUCKET
    stamps = sorted({t - k * lag for t in window for k in range(0, 8)})
    rows = conn.execute(
        f"SELECT ts, segment, value_sum, n FROM points WHERE metric_id = ? AND ts IN ({','.join('?' * len(stamps))})",
        [metric["id"], *stamps],
    ).fetchall()
    data = defaultdict(dict)  # segment -> ts -> (value_sum, n)
    for r in rows:
        data[r["segment"]][r["ts"]] = (r["value_sum"], r["n"])

    totals = {}
    for seg, series in data.items():
        if not seg or (within and not set(within.split("|")) <= set(seg.split("|"))):
            continue
        actual = expected = var = spread = big = bare = 0.0
        for t in window:
            vs, n = series.get(t, (0.0, 0.0))
            hist = [series[t - k * lag] for k in range(1, 8) if (t - k * lag) in series]
            if len(hist) < 2:
                continue
            if metric["agg"] == "mean":
                means = [h[0] / h[1] for h in hist if h[1] > 0] or [0.0]
                exp_mean = float(np.median(means))
                expected += exp_mean * n
                # this bucket's mean is as noisy as past days' were (robust spread, at least 3%), and their median
                # adds ~pi/2k of that
                sd = max(MAD_K * _mad(means), 0.03 * abs(exp_mean))
                var += (n * sd) ** 2 * (1 + math.pi / (2 * len(means)))
            else:
                vals = sorted(h[0] for h in hist)
                # trimmed mean: robust to one bad day, less jumpy than a median of small counts
                e = float(np.mean(vals[1:-1]) if len(vals) >= 4 else np.median(vals))
                expected += e
                # counts are Poisson, and the expectation averages k days, adding 1/k of that again
                k = len(vals) - 2 if len(vals) >= 4 else len(vals)
                var += abs(e) * (1 + 1 / k)
                bare += abs(e)
                if abs(e) >= BIG_CELL:  # past days' robust spread only means something for counts this big
                    spread += (MAD_K * _mad(vals)) ** 2
                    big += abs(e)
            actual += vs
        totals[seg] = (actual, expected, var, spread, big, bare)
    return totals


def _mad(xs) -> float:
    xs = np.asarray(xs, dtype=float)
    return float(np.median(np.abs(xs - np.median(xs))))


def _tail(z: float) -> float:
    """One-sided p-value of z (the upper tail)."""
    return 0.5 * math.erfc(z / math.sqrt(2))


def _binom_z(a: float, n: float, p: float) -> float:
    """Exact binomial tail of a successes out of n at rate p, as a signed z-score (as seasonal._poisson_z does)."""
    a, n, p = int(round(a)), int(round(n)), min(max(p, 0.0), 1.0)
    a = min(max(a, 0), n)
    low = a < n * p
    tail = bdtr(a, n, p) if low else (bdtrc(a - 1, n, p) if a > 0 else 1.0)
    z = 0.0 - float(ndtri(min(max(tail, 1e-300), 0.5)))
    return -z if low else z


class _Evidence:
    """Scores one slice's excess over a proportional share of the actual total in the window."""

    def __init__(self, totals: dict, agg: str):
        self.A, self.E, self.VAR, spread, big, self.BARE = (sum(t[i] for t in totals.values()) for i in range(6))
        # sums: over-dispersed (or not counts at all) if past days spread more than Poisson; one factor for the whole
        # window, from every cell big enough to tell (7 small counts per cell are too few: their spread is mostly noise)
        self.phi = max(spread / big, 1.0) if big > 0 else 1.0
        # the exact (binomial) test needs whole events; anything else (or a lot of them) is tested on the normal scale
        self.exact = agg != "mean" and self.A <= EXACT_MAX and all(float(t[0]).is_integer() for t in totals.values())

    def __call__(self, a: float, e: float, var: float, bare: float) -> tuple[float, float, float]:
        """(excess, z, noise variance of the excess): how far the slice moved beyond the metric as a whole."""
        p = e / self.E
        x = a - p * self.A
        # the excess mixes the slice's own noise and the rest's: x = (1-p)(a - e) - p(rest actual - rest expected)
        s2 = self.phi * ((1 - p) ** 2 * var + p ** 2 * (self.VAR - var))
        if self.exact:
            s2p = (1 - p) ** 2 * bare + p ** 2 * (self.BARE - bare)  # what the binomial test itself assumes
            return x, _binom_z(a, self.A, p) / math.sqrt(max(s2 / s2p, 1.0) if s2p > 0 else 1.0), s2
        return x, (x / math.sqrt(s2) if s2 > 0 else 0.0), s2


def drilldown(conn, metric, window: list[int], within: str = "", depth: int = 1) -> list[dict]:
    """within: optional 'dim=val' slice to drill inside (its own dimension is skipped)."""
    skip_dims = {p.split("=", 1)[0] for p in within.split("|")} if within else set()
    totals = _segment_totals(conn, metric, window, within)
    if not totals:
        return []
    evidence = _Evidence(totals, metric["agg"])
    A, E = evidence.A, evidence.E
    delta = A - E
    if abs(delta) < 1e-9 or A <= 0 or E <= 0:
        return []
    sign = 1.0 if delta > 0 else -1.0

    by_dim = defaultdict(lambda: defaultdict(lambda: np.zeros(6)))
    for seg, tot in totals.items():
        for d, v in parse_segment(seg).items():
            if d not in skip_dims:
                by_dim[d][v] += tot
    tests = sum(len(values) for values in by_dim.values())

    def score(dim, val, a, e, var, spread, big, bare, m=tests):
        x, z, s2 = evidence(a, e, var, bare)
        return {"dimension": dim, "value": val, "share_of_change": (a - e) / delta, "a": a, "e": e,
                "change_pct": (a - e) / e if e > 0 else float("inf"), "excess": x, "z": z, "s2": s2, "p": e / E,
                "confidence": max(0.0, 1.0 - m * _tail(sign * z))}  # family-wise, toward the change only

    candidates, scored_all = [], []
    for dim, values in by_dim.items():
        scored = [score(dim, val, *tot) for val, tot in values.items()]
        scored_all += scored
        # slices that moved further than the metric, the metric's way, strongest evidence first
        movers = sorted((s for s in scored if sign * s["excess"] > 0), key=lambda s: -sign * s["z"])
        pool = sum(sign * s["excess"] for s in movers)
        chosen, held = [], 0.0
        for item in movers[:2]:
            if item["confidence"] < LOCATE_CONF or item["share_of_change"] <= MIN_SHARE:
                break
            chosen.append(item)
            held += sign * item["excess"]
            if held >= EP_TARGET * pool:
                break
        if chosen and held >= EP_TARGET * pool:
            candidates.append((sign * chosen[0]["z"], chosen))

    candidates.sort(key=lambda c: -c[0])
    # a second dimension only if it pins down a single value and has nearly as much evidence (half the chi-square)
    picked = candidates[:1] + [c for c in candidates[1:2] if c[0] ** 2 >= 0.5 * candidates[0][0] ** 2 and len(c[1]) == 1]
    where = [_entry(item) for _, chosen in picked for item in chosen]
    if depth >= 2 and where:
        # Time: also name the exact segment (e.g. platform=ios × region=EU) when one segment explains most of it
        seg, tot = max(totals.items(), key=lambda kv: (kv[1][0] - kv[1][1]) / delta)
        dims = parse_segment(seg)
        item = score(" × ".join(dims), " × ".join(dims.values()), *tot, m=len(totals))
        if len(dims) >= 2 and item["share_of_change"] >= 0.6 and item["confidence"] >= LOCATE_CONF:
            where.append(_entry(item))
    if where:
        return where

    # Nothing moved disproportionately. "All segments" only if no slice can have moved materially further than the rest:
    # had v's multiplier been SPREAD_RATIO off the rest's (the change's way), its excess would have been
    # (ratio - 1) * e * (1 - p) * rest multiplier. Level-free like the excess itself: a level the 7-day history gets
    # wrong (weekends, growth) cannot make a quiet hour look like a metric-wide change. Otherwise we cannot tell.
    total = {"share_of_change": 1.0, "change_pct": round(delta / E * 100, 1)}
    informative = [s for s in scored_all if 0 < s["p"] < 1 and s["s2"] > 0]
    if not informative:  # no dimension to split by
        return [{"dimension": "*", "value": "all segments", **total}]
    ruled_out = 1.0
    for s in informative:
        material = sign * SPREAD_RATIO * s["e"] * (1 - s["p"]) * (A - s["a"]) / (E - s["e"])
        ruled_out = min(ruled_out, max(0.0, 1.0 - tests * _tail((material - s["excess"]) * sign / math.sqrt(s["s2"]))))
    if ruled_out >= LOCATE_CONF:
        return [{"dimension": "*", "value": "all segments", **total, "confidence": round(ruled_out, 3)}]
    best = max((s["confidence"] for s in scored_all if sign * s["excess"] > 0), default=0.0)
    return [{**NO_LOCATION, **total, "confidence": round(best, 3)}]


def _entry(item: dict) -> dict:
    return {"dimension": item["dimension"], "value": item["value"],
            "share_of_change": round(float(min(item["share_of_change"], 9.99)), 3),
            "change_pct": round(float(item["change_pct"]) * 100, 1) if math.isfinite(item["change_pct"]) else None,
            "confidence": round(float(item["confidence"]), 3)}
