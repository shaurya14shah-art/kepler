"""Billing for Kepler, through Razorpay. DISABLED: Kepler is free right now and nothing can be charged.

Charging needs every one of these locks open at once. Today the first one is shut in the code itself:

  1. CHARGING_ALLOWED = True    in this file (it is False: only you can change it, by editing this line)
  2. KEPLER_BILLING=on          in the server's environment (default off)
  3. RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET and RAZORPAY_WEBHOOK_SECRET set (no keys are stored in the code or repo)
  4. live keys (rzp_live_…) also need KEPLER_BILLING_LIVE=yes; test keys (rzp_test_…) never move real money
  5. the plan being bought has a price (see plans.py; every paid plan's price is None today)

While any lock is shut, every billing endpoint refuses before doing anything: no request is ever sent to Razorpay,
no order is created, and no prices appear in the API, CLI or dashboard. docs/billing.md explains how to open them
when you decide to charge.
"""
import os

from . import plans

# Lock 1. Kepler is free: keep this False until you have set prices, terms and a Razorpay account yourself.
CHARGING_ALLOWED = False

PROVIDER = "razorpay"


class BillingDisabled(Exception):
    """Raised by every code path that could move money while billing is off."""


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _flag(name: str) -> bool:
    return _env(name).lower() in ("1", "on", "true", "yes")


def keys() -> dict:
    return {"key_id": _env("RAZORPAY_KEY_ID"), "key_secret": _env("RAZORPAY_KEY_SECRET"),
            "webhook_secret": _env("RAZORPAY_WEBHOOK_SECRET")}


def mode() -> str:
    """'test' or 'live' from the key ID's prefix, '' when no key is set."""
    kid = keys()["key_id"]
    return "live" if kid.startswith("rzp_live_") else "test" if kid.startswith("rzp_test_") else ""


def blockers() -> list[str]:
    """Why charging is off, in plain words (empty only when every lock is open)."""
    out = []
    if not CHARGING_ALLOWED:
        out.append("charging is switched off in the code (kepler/billing/__init__.py: CHARGING_ALLOWED = False)")
    if not _flag("KEPLER_BILLING"):
        out.append("KEPLER_BILLING is not 'on'")
    k = keys()
    missing = [n for n, v in (("RAZORPAY_KEY_ID", k["key_id"]), ("RAZORPAY_KEY_SECRET", k["key_secret"]),
                              ("RAZORPAY_WEBHOOK_SECRET", k["webhook_secret"])) if not v]
    if missing:
        out.append("Razorpay keys not set: " + ", ".join(missing))
    elif not mode():
        out.append("RAZORPAY_KEY_ID doesn't look like a Razorpay key (rzp_test_… or rzp_live_…)")
    elif mode() == "live" and not _flag("KEPLER_BILLING_LIVE"):
        out.append("live keys need KEPLER_BILLING_LIVE=yes as well")
    return out


def charging_enabled() -> bool:
    return not blockers()


def guard() -> None:
    """Call first in anything that could create an order, a subscription or a charge."""
    why = blockers()
    if why:
        raise BillingDisabled("Billing is disabled: Kepler is free and nothing can be charged. (" + why[0] + ")")


def _masked(key_id: str) -> str | None:
    return (key_id[:9] + "…" + key_id[-2:]) if len(key_id) > 12 else ("set" if key_id else None)


def status() -> dict:
    """Safe to show anywhere: never includes secrets, and prices only when charging is enabled."""
    on = charging_enabled()
    return {
        "enabled": on,
        "provider": PROVIDER,
        "mode": (mode() if on else "disabled"),
        "message": ("Billing is live through Razorpay." if on else
                    "Kepler is free: billing is disabled and nothing can be charged."),
        "blockers": blockers(),
        "key_id": _masked(keys()["key_id"]),
        "plan": current_plan(),
        "plans": [p.public(show_prices=on) for p in plans.PLANS.values()],
    }


def current_plan() -> str:
    """The workspace's plan: its active subscription's plan, else Free."""
    try:
        from .. import db
        with db.session() as c:
            row = c.execute("SELECT plan FROM billing_subscriptions WHERE status = 'active' ORDER BY updated DESC LIMIT 1").fetchone()
        return row["plan"] if row else plans.DEFAULT_PLAN
    except Exception:  # noqa: BLE001 - no database yet (CLI on another machine): the default plan
        return plans.DEFAULT_PLAN
