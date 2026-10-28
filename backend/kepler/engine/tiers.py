"""Kepler's three models, named after Kepler's three laws of planetary motion.

    Orbit  (1st law: every orbit is an ellipse)       the shape of normal: cheapest, fastest, basic reasoning
    Area   (2nd law: equal areas in equal times)      steady, consistent sweep: the balanced default
    Time   (3rd law: period² ∝ distance³)             relates everything to everything: deepest reasoning

A metric uses its own tier if set, else the workspace default, else Area.
Every model is free and no prices are shown while billing is disabled (PAYMENTS_ENABLED follows kepler/billing).
"""
from dataclasses import asdict, dataclass

from .. import billing
from .seasonal import POOLING


@dataclass(frozen=True)
class Tier:
    id: str
    name: str
    law: str
    tagline: str
    custom_models: bool        # per-customer trained baselines (else the shared base model)
    slices: bool               # also watch every dimension value on its own
    pooling: tuple             # evidence windows (buckets) for sustained shifts
    base_lags: int             # days of same-time-of-day history in the shared baseline
    history_days: int          # days loaded per scoring window
    learned_filter: bool       # blend in the classifier trained on the team's 👍/👎
    drilldown: int             # 1 = best single dimension, 2 = also the exact segment (dim × dim)
    reasoning: bool            # related incidents across metrics, impact estimate, written reasoning chain
    price_preview: str         # shown, never charged during the beta
    price_per_metric_month: float
    rank: int                  # 1 = most capable
    combos: int = 0            # also watch up to N exact segments (dim × dim) as their own series

    def public(self) -> dict:
        d = asdict(self)
        if not PAYMENTS_ENABLED:  # keep prices server-side only while payments are off
            d.pop("price_preview")
            d.pop("price_per_metric_month")
        return d


TIERS: dict[str, Tier] = {
    "orbit": Tier(
        id="orbit", name="Orbit", law="Kepler's 1st law: every orbit is an ellipse",
        tagline="The shape of normal. A shared baseline on whole metrics: cheapest and fastest, basic reasoning.",
        custom_models=False, slices=False, pooling=(3,), base_lags=7, history_days=8, learned_filter=False,
        drilldown=1, reasoning=False, price_preview="Free", price_per_metric_month=0.0, rank=3),
    "area": Tier(
        id="area", name="Area", law="Kepler's 2nd law: equal areas in equal times",
        tagline="Steady and consistent. Custom models per metric and slice, sustained-shift evidence, a filter that "
                "learns from your team, and where it broke.",
        custom_models=True, slices=True, pooling=POOLING, base_lags=14, history_days=15, learned_filter=True,
        drilldown=1, reasoning=False, price_preview="$4 / metric / month", price_per_metric_month=4.0, rank=2),
    "time": Tier(
        id="time", name="Time", law="Kepler's 3rd law: the square of the period ∝ the cube of the distance",
        tagline="Relates everything to everything. Area plus slow-burn detection (2-4 h evidence), exact-segment "
                "watching (ios × EU), incidents linked across metrics, impact in real units and a written reasoning chain.",
        custom_models=True, slices=True, pooling=POOLING + (24, 48), base_lags=14, history_days=15, learned_filter=True,
        drilldown=2, reasoning=True, combos=8, price_preview="$12 / metric / month", price_per_metric_month=12.0, rank=1),
}
DEFAULT_TIER = "area"
# Payments follow the billing locks (kepler/billing): while charging is off — today, always — there's no paywall and
# no price appears in the API, CLI, chat or dashboard. The per-tier prices above are only kept as a starting point.
PAYMENTS_ENABLED = billing.charging_enabled()
PAYWALL = {"enabled": PAYMENTS_ENABLED,
           "note": "Every model is free: billing is disabled." if not PAYMENTS_ENABLED else "Paid models are billed through Razorpay."}


def get(tier_id: str | None) -> Tier:
    return TIERS.get((tier_id or "").lower(), TIERS[DEFAULT_TIER])


def of(metric, settings: dict | None = None) -> Tier:
    """Effective tier for a metric row: its own override, else the workspace default, else Area."""
    own = metric["tier"] if "tier" in metric.keys() else None
    return get(own or (settings or {}).get("model_tier") or DEFAULT_TIER)
