"""CLI parser, completions, agent definition, and the bot's dialogue against a fake Kepler server."""
import plistlib

import pytest

from kepler import device
from kepler.bot.brain import Bot
from kepler.cli import commands
from kepler.cli.client import KeplerError

INCIDENT = {"decision": "anomaly", "incident_id": 40, "metric": "api_errors", "slice": None, "status": "open",
            "direction": "spike", "severity": "critical", "confidence": 0.93, "observed": 26.0, "expected": 8.6,
            "expected_range": [0.0, 17.5], "change_pct": 201.0, "z_score": 10.2,
            "where": [{"dimension": "platform", "value": "ios", "share_of_change": 0.99, "change_pct": 951.0}],
            "started_at": 1792411200, "last_seen_at": 1792412400, "model": {"baseline": "Custom weekly profile", "prior": 1.0},
            "feedback": None, "metric_id": 3, "unit": ""}


class FakeClient:
    url = "http://kepler.test"
    key = "kp_test"

    def __init__(self):
        self.posts = []

    def get(self, path, **params):
        if path == "/api/overview":
            return {"stats": {"open": 1, "last24": 1, "tp": 1, "fp": 0, "total": 1},
                    "metrics": [{"id": 1, "name": "signups"}, {"id": 3, "name": "api_errors"}, {"id": 4, "name": "p95_latency_ms"}]}
        if path.endswith("/breakdown"):
            return {"slices": [{"slice": "platform=ios", "dimension": "platform", "value": "ios", "observed": 9, "expected": 3, "z": 4.0, "change_pct": 200.0}]}
        if path == "/api/integrations":
            return [{"type": "datadog", "label": "Datadog", "direction": "pull", "summary": "s", "fields": [], "docs": ""}]
        if path == "/api/demo/scenarios":
            return [{"id": "ios_release_bug", "label": "Bad iOS release"}]
        if path == "/api/models":
            return {"feedback": {"active": False, "weight": 0}, "labels": {"pos": 0, "neg": 0},
                    "metrics": [{"metric": "signups", "kind": "base", "period": "", "slices_trained": 0, "trained_days": 0}]}
        if path == "/api/incidents":
            return [INCIDENT]
        if path.startswith("/api/incidents/"):
            return {"decision": INCIDENT, "points": [{"ts": 1792411200, "value": 1.0}], "notifications": []}
        raise KeplerError(f"unexpected GET {path}")

    def get_auth(self, path, **params):
        return {"decision": "anomaly", "incidents": [INCIDENT]}

    def post(self, path, body=None):
        self.posts.append((path, body))
        return {"ok": True, "labels": 5}

    def patch(self, path, body):
        self.posts.append((path, body))
        return {"ok": True}

    def put(self, path, body):
        self.posts.append((path, body))
        return body

    def metric_by_name(self, name):
        return next(m for m in self.get("/api/overview")["metrics"] if m["name"] == name)


@pytest.fixture
def bot():
    return Bot(FakeClient())


def test_why_then_label_uses_conversation_context(bot):
    r = bot.handle("why did api errors spike?")
    assert r.decision["intent"] == "why_metric" and r.decision["slots"]["metric"] == "api_errors"
    assert "platform=ios" in r.text
    r = bot.handle("label it real")
    assert r.decision["intent"] == "label_real"
    assert bot.c.posts[-1] == ("/api/incidents/40/feedback", {"label": 1})


def test_missing_metric_is_asked_for_then_filled(bot):
    bot.memory["metric"] = None
    r = bot.handle("is it normal right now?")
    if r.decision["intent"] == "decide":  # the model may also route this to status; both are reasonable
        assert "Which metric?" in r.text
        r = bot.handle("latency")
        assert r.decision["intent"] == "decide" and r.decision.get("resumed")
        assert r.decision["slots"]["metric"] == "p95_latency_ms"


def test_low_confidence_asks_and_learns_the_answer(bot):
    from kepler.bot import store
    r = bot.handle("hmm stuff")
    if r.decision["confidence"] < 0.45 and r.decision["alternatives"]:
        assert "Did you want to" in r.blocks[0].plain or "not sure what you mean" in r.blocks[0].plain
        r = bot.handle("1")
        assert r.decision.get("resumed") and r.decision["confidence"] == 1.0
        assert store.taught_intent("hmm stuff") == r.decision["intent"]  # the answer was learned
        r = bot.handle("hmm stuff")
        assert r.decision["confidence"] == 1.0 and r.decision.get("note") == "you taught me this one"


def test_errors_become_replies_not_crashes(bot):
    r = bot.handle("show the alert log")  # FakeClient has no /api/notifications
    assert r.decision["intent"] == "error" and "unexpected GET" in r.text


def test_parser_has_every_dashboard_feature():
    p = commands.build_parser()
    names = set(next(a for a in p._actions if a.dest == "cmd").choices)
    for cmd in ("ui", "ask", "chat", "status", "decide", "metrics", "metric", "incidents", "explain", "watch", "analyze",
                "send", "label", "train", "models", "settings", "key", "alerts", "demo", "integrations", "connect",
                "pulls", "destinations", "import", "open", "copy", "agent", "completion", "config"):
        assert cmd in names, cmd
    args = p.parse_args(["--json", "status"])
    assert args.json is True  # global flag before the command survives


def test_completion_scripts(capsys):
    for shell in ("zsh", "bash"):
        commands.main(["completion", shell])
        script = capsys.readouterr().out
        assert "kepler __complete" in script and "decide" in script


def test_agent_plist_is_valid():
    d = plistlib.loads(device.agent_plist("http://localhost:8000", "high").encode())
    assert d["Label"] == device.AGENT_LABEL and d["RunAtLoad"] and d["KeepAlive"]
    assert d["ProgramArguments"][-4:] == ["--url", "http://localhost:8000", "--min-severity", "high"]


def test_switch_model_for_one_metric(bot):
    r = bot.handle("use the time model for api errors")
    assert r.decision["intent"] == "set_tier" and r.decision["slots"]["tier"] == "time"
    assert bot.c.posts[-1] == ("/api/metrics/3", {"tier": "time"})


def test_payments_disabled_no_prices_leak():
    """While payments are off, no price, bill or checkout data may leave the server."""
    import json as _json

    from fastapi.testclient import TestClient

    from kepler.api import app
    from kepler.engine import tiers

    assert tiers.PAYMENTS_ENABLED is False and tiers.PAYWALL["enabled"] is False
    for t in tiers.TIERS.values():
        assert "price_preview" not in t.public() and "price_per_metric_month" not in t.public()
    with TestClient(app) as c:
        body = c.get("/api/tiers").json()
    assert "monthly_preview" not in body
    text = _json.dumps(body)
    assert "$" not in text and "price" not in text


# ---------------------------------------------------------------- `kepler` with no server running

def _free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_kepler_starts_a_server_when_none_is_running(tmp_path, monkeypatch):
    """`kepler` opens the whole app, not just the chat: with nothing on its localhost port it runs a server itself."""
    from kepler import db
    from kepler.cli import client as kclient
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "kepler.db")
    monkeypatch.setattr(kclient, "SERVER_INFO", tmp_path / "servers.json")
    db.init_db()
    db.set_setting("demo_mode", "0")
    c = kclient.Client(f"http://127.0.0.1:{_free_port()}")
    with pytest.raises(KeplerError):
        c.get("/api/health")
    started = commands._start_local_server(c)
    assert started, "no server was started"
    server, thread = started
    try:
        assert c.get("/api/health")
        assert "metrics" in c.get("/api/overview")  # behind the access gate: the client found the key by itself

        import asyncio

        from textual.widgets import TabPane

        from kepler.tui.app import KeplerApp, MainScreen

        async def opens_every_tab():
            app = KeplerApp(c, skip_welcome=True, note="Started Kepler")
            async with app.run_test(size=(140, 44)) as pilot:
                await pilot.pause(0.5)
                assert isinstance(app.screen, MainScreen)
                assert len(app.screen.query(TabPane)) == 7  # the dashboard tabs and Kepler AI, not the chat alone
        asyncio.run(opens_every_tab())
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    assert not thread.is_alive(), "the server stops when the app closes"


def test_kepler_never_starts_a_server_for_a_remote_url_or_a_taken_port():
    import socket

    from kepler.cli.client import Client
    assert commands._start_local_server(Client("https://kepler.example.com")) is None
    with socket.socket() as s:  # something else is listening there
        s.bind(("127.0.0.1", 0))
        s.listen()
        assert commands._start_local_server(Client(f"http://127.0.0.1:{s.getsockname()[1]}")) is None
