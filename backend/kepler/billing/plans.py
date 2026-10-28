"""The plan catalog: what Kepler could be sold as. Edit this file to set your plans.

Every plan's `amount` is in the currency's smallest unit (paise for INR, cents for USD). A plan whose amount is
None is not for sale: it is never shown with a price and checkout refuses it. Right now Kepler is free, so the
only plan in use is Free and the paid plans have no price.

To sell a plan later (see docs/billing.md):
  1. create the plan in your Razorpay dashboard (Subscriptions → Plans) and note its plan ID (plan_…)
  2. set `amount` here to the same price, and put the plan ID in the environment as RAZORPAY_PLAN_<ID>
     (e.g. RAZORPAY_PLAN_PRO=plan_ABC123)
"""
import os
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    tagline: str
    features: tuple[str, ...] = field(default_factory=tuple)
    amount: int | None = None          # smallest currency unit; None = not for sale
    currency: str = "INR"
    interval: str = "monthly"          # monthly | yearly

    @property
    def for_sale(self) -> bool:
        return self.amount is not None and self.amount > 0

    @property
    def razorpay_plan_id(self) -> str:
        return os.environ.get(f"RAZORPAY_PLAN_{self.id.upper()}", "").strip()

    def public(self, show_prices: bool) -> dict:
        d = asdict(self)
        d["features"] = list(self.features)
        d["for_sale"] = self.for_sale and show_prices
        if not show_prices:
            d["amount"] = None  # prices stay on the server while billing is off
        return d


PLANS: dict[str, Plan] = {
    "free": Plan("free", "Free", "Every feature, free during early access", features=(
        "All three detection models: Orbit, Area and Time",
        "Unlimited metrics and integrations",
        "Slack, Grafana, Datadog and webhook alerts",
        "Kepler AI: maths, proofs, knowledge library, PDF write-ups",
        "Self-hosted: your data stays on your servers",
    ), amount=0),
    # Example paid plans. They have no price, so nothing can be bought. Rename them, change the features and set
    # a price when you decide to charge.
    "pro": Plan("pro", "Pro", "For teams that rely on Kepler every day", features=(
        "Everything in Free",
        "Priority email support",
        "Help connecting your data sources",
    )),
    "business": Plan("business", "Business", "For companies with many teams", features=(
        "Everything in Pro",
        "Onboarding session and a named contact",
        "Invoice billing",
    )),
}
DEFAULT_PLAN = "free"


def get(plan_id: str) -> Plan | None:
    return PLANS.get((plan_id or "").strip().lower())
