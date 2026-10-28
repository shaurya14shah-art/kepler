"""Shared traffic model for Orbitly: the same daily rhythm drives live traffic and the 3-week history backfill,
so Kepler's learned baseline matches what the live app does."""
import math

PLATFORMS = {"web": 0.5, "ios": 0.3, "android": 0.2}
REGIONS = {"US": 0.5, "EU": 0.3, "IN": 0.2}
PEAK_HOUR_UTC = {"US": 18, "EU": 13, "IN": 8}
ROUTES = {"/feed": 0.55, "/search": 0.25, "/upload": 0.12, "/login": 0.08}

SIGNUPS_PER_MIN_PEAK = 4.0     # whole app, at a region's daily peak
REQUESTS_PER_SEC_PEAK = 6.0    # whole app
BASE_ERROR_RATE = 0.004        # normal 5xx share
BASE_LATENCY_S = {"/feed": 0.06, "/search": 0.12, "/upload": 0.25, "/login": 0.04}
REGION_LATENCY = {"US": 1.0, "EU": 1.1, "IN": 1.35}


def activity(region: str, ts: float) -> float:
    """0.3..1.0 daily curve per region, with a weekend dip."""
    hour = (ts % 86400) / 3600
    bump = ((1 + math.cos(2 * math.pi * (hour - PEAK_HOUR_UTC[region]) / 24)) / 2) ** 1.5
    weekday = int((ts // 86400 + 3) % 7)  # 0 = Monday
    return (0.3 + 0.7 * bump) * (0.78 if weekday >= 5 else 1.0)


def mix(ts: float):
    """Yield (platform, region, share_of_traffic) for the current moment."""
    total = sum(REGIONS[r] * activity(r, ts) for r in REGIONS)
    for r, rw in REGIONS.items():
        for p, pw in PLATFORMS.items():
            yield p, r, pw * rw * activity(r, ts) / max(total, 1e-9)


def load(ts: float) -> float:
    """Overall load factor (0..1) relative to the busiest moment."""
    return sum(REGIONS[r] * activity(r, ts) for r in REGIONS)
