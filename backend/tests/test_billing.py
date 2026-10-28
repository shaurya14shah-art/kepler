"""Billing must never charge while it's disabled, and must be correct the day it's enabled.

The first group checks the product as shipped: every money path refuses, nothing reaches Razorpay, no prices leak.
The second group opens every lock *inside the test only*, with a fake Razorpay (no network), to check that checkout,
signature verification and webhooks work when you decide to turn billing on.
"""
import json

import pytest

from kepler import billing
from kepler.billing import plans, razorpay

TEST_KEYS = {"RAZORPAY_KEY_ID": "rzp_test_K3pl3rT3stK3y1", "RAZORPAY_KEY_SECRET": "test-secret-not-real",
             "RAZORPAY_WEBHOOK_SECRET": "test-webhook-secret"}


@pytest.fixture
def no_network(monkeypatch):
    import httpx
    calls = []

    def refuse(*a, **k):
        calls.append(a)
        raise AssertionError("billing tried to reach the network")
    monkeypatch.setattr(httpx, "post", refuse)
    return calls


@pytest.fixture
def api():
    from fastapi.testclient import TestClient

    from kepler import db
    from kepler.api import app
    with TestClient(app) as c:
        c.headers["X-Kepler-Key"] = db.get_settings()["api_key"]
        yield c


# ---------------------------------------------------------------- as shipped: free, nothing can be charged

def test_shipped_with_charging_off_in_the_code():
    assert billing.CHARGING_ALLOWED is False
    assert billing.charging_enabled() is False
    s = billing.status()
    assert s["enabled"] is False and s["mode"] == "disabled" and s["plan"] == "free"
    assert "nothing can be charged" in s["message"]
    assert all(p["amount"] is None and p["for_sale"] is False for p in s["plans"])


def test_every_paid_plan_has_no_price():
    assert [p.id for p in plans.PLANS.values() if p.for_sale] == []


@pytest.mark.parametrize("call", [
    lambda: razorpay.checkout("pro"),
    lambda: razorpay.verify_checkout("pay_1", "sig", order_id="order_1"),
    lambda: razorpay.handle_webhook(b"{}", {}),
    lambda: razorpay._post("/orders", {"amount": 100}),
])
def test_every_money_path_refuses(call, no_network):
    with pytest.raises(billing.BillingDisabled):
        call()
    assert no_network == []


def test_keys_and_env_alone_cannot_turn_it_on(monkeypatch, no_network):
    """Even with KEPLER_BILLING=on and real-looking keys, the lock in the code keeps it off."""
    monkeypatch.setenv("KEPLER_BILLING", "on")
    for k, v in TEST_KEYS.items():
        monkeypatch.setenv(k, v)
    assert billing.charging_enabled() is False
    assert billing.blockers() == ["charging is switched off in the code (kepler/billing/__init__.py: CHARGING_ALLOWED = False)"]
    with pytest.raises(billing.BillingDisabled):
        razorpay.checkout("pro")
    assert no_network == []


def test_api_refuses_and_hides_prices(api, no_network):
    s = api.get("/api/billing").json()
    assert s["enabled"] is False and s["plan"] == "free" and s["key_id"] is None
    assert not {"key_secret", "webhook_secret"} & set(s)  # secret values are never part of the status
    assert api.post("/api/billing/checkout", json={"plan": "pro"}).status_code == 403
    assert api.post("/api/billing/verify", json={"razorpay_payment_id": "pay_1", "razorpay_signature": "x",
                                                 "razorpay_order_id": "order_1"}).status_code == 403
    assert api.post("/api/billing/webhook/razorpay", content=b"{}").status_code == 404
    tiers = api.get("/api/tiers").json()
    assert tiers["paywall"]["enabled"] is False and "$" not in json.dumps(tiers) and "price" not in json.dumps(tiers)
    assert no_network == []


def test_status_never_shows_secrets(monkeypatch):
    for k, v in TEST_KEYS.items():
        monkeypatch.setenv(k, v)
    text = json.dumps(billing.status())
    assert TEST_KEYS["RAZORPAY_KEY_SECRET"] not in text and TEST_KEYS["RAZORPAY_WEBHOOK_SECRET"] not in text
    assert TEST_KEYS["RAZORPAY_KEY_ID"] not in text  # masked


# ---------------------------------------------------------------- the day it's switched on (inside this test only)

@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(billing, "CHARGING_ALLOWED", True)
    monkeypatch.setenv("KEPLER_BILLING", "on")
    for k, v in TEST_KEYS.items():
        monkeypatch.setenv(k, v)
    priced = plans.Plan("pro", "Pro", "test", amount=49900)  # a test price, never shipped
    monkeypatch.setitem(plans.PLANS, "pro", priced)
    assert billing.charging_enabled()


@pytest.fixture
def fake_razorpay(monkeypatch):
    import httpx
    sent = []

    class Resp:
        status_code = 200
        text = ""

        def __init__(self, data):
            self._d = data

        def json(self):
            return self._d

    def post(url, json=None, auth=None, timeout=None):
        sent.append((url, json, auth))
        return Resp({"id": "order_TEST123", "amount": json.get("amount"), "currency": json.get("currency")})
    monkeypatch.setattr(httpx, "post", post)
    return sent


def test_live_keys_need_explicit_confirmation(enabled, monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_live_SomeLiveKey9")
    assert not billing.charging_enabled()
    assert billing.blockers() == ["live keys need KEPLER_BILLING_LIVE=yes as well"]


def test_unpriced_plan_is_refused(enabled, fake_razorpay):
    with pytest.raises(razorpay.CheckoutError):
        razorpay.checkout("business")  # still no price
    assert fake_razorpay == []


def test_checkout_verify_and_webhook_flow(enabled, fake_razorpay, api):
    from kepler import db
    with db.session(write=True) as c:
        c.execute("DELETE FROM billing_subscriptions")
        c.execute("DELETE FROM billing_events")
    order = api.post("/api/billing/checkout", json={"plan": "pro"}).json()
    assert order["order_id"] == "order_TEST123" and order["amount"] == 49900 and order["key_id"].startswith("rzp_test_")
    url, payload, auth = fake_razorpay[0]
    assert url.endswith("/v1/orders") and auth == (TEST_KEYS["RAZORPAY_KEY_ID"], TEST_KEYS["RAZORPAY_KEY_SECRET"])
    assert billing.current_plan() == "free"  # created, not paid

    bad = api.post("/api/billing/verify", json={"razorpay_payment_id": "pay_1", "razorpay_signature": "forged",
                                                "razorpay_order_id": "order_TEST123"})
    assert bad.status_code == 400 and billing.current_plan() == "free"

    sig = razorpay.payment_signature("order_TEST123", "pay_1", TEST_KEYS["RAZORPAY_KEY_SECRET"])
    ok = api.post("/api/billing/verify", json={"razorpay_payment_id": "pay_1", "razorpay_signature": sig,
                                               "razorpay_order_id": "order_TEST123"})
    assert ok.json() == {"plan": "pro", "status": "active"} and billing.current_plan() == "pro"

    body = json.dumps({"event": "subscription.cancelled",
                       "payload": {"order": {"entity": {"id": "order_TEST123"}}}}).encode()
    good = {"X-Razorpay-Signature": razorpay.webhook_signature(body, TEST_KEYS["RAZORPAY_WEBHOOK_SECRET"]),
            "X-Razorpay-Event-Id": "evt_1"}
    assert api.post("/api/billing/webhook/razorpay", content=body, headers={**good, "X-Razorpay-Signature": "nope"}).status_code == 400
    assert api.post("/api/billing/webhook/razorpay", content=body, headers=good).json()["applied"] is True
    assert api.post("/api/billing/webhook/razorpay", content=body, headers=good).json()["applied"] is False  # once only
    assert billing.current_plan() == "free"  # cancelled


def test_signatures_match_razorpays_formula():
    import hashlib
    import hmac
    expected = hmac.new(b"s3cret", b"order_A|pay_B", hashlib.sha256).hexdigest()
    assert razorpay.payment_signature("order_A", "pay_B", "s3cret") == expected
    assert razorpay.subscription_signature("pay_B", "sub_C", "s3cret") == hmac.new(b"s3cret", b"pay_B|sub_C", hashlib.sha256).hexdigest()
    assert razorpay.signature_ok(expected, expected) and not razorpay.signature_ok(expected, "x") and not razorpay.signature_ok(expected, None)
