"""`kepler doctor`: the health checks behind it (diagnose), against a fake server."""
import time

from kepler.cli.client import KeplerError
from kepler.cli.commands import diagnose


class Fake:
    url = "http://kepler.test"

    def __init__(self, **over):
        now = time.time()
        self.data = {
            "/api/health": {"ok": True, "seeding": False, "last_tick": now - 3, "last_error": None},
            "/api/settings": {"slack_webhook_url": "https://hooks.slack.com/x"},
            "/api/overview": {"metrics": [{"name": "signups", "status": "ok", "model": "custom", "open_incidents": [],
                                           "muted_until": 0}]},
            "/api/connectors": [{"id": 1, "name": "Postgres: signups", "last_status": "ok: 36 points", "last_run": now - 30,
                                 "interval_s": 60}],
            "/api/destinations": [],
            "/api/billing": {"enabled": False},
            "/api/models": {"metrics": [{"trained_at": now - 2 * 86400}]},
        }
        self.data.update(over)

    def get(self, path, **_):
        v = self.data[path]
        if isinstance(v, Exception):
            raise v
        return v


def levels(checks):
    return {level for level, _, _ in checks}


def test_a_healthy_setup_has_no_problems():
    checks = diagnose(Fake())
    assert "error" not in levels(checks) and "warn" not in levels(checks)
    assert any(c[1] == "alerts: Slack" for c in checks)


def test_an_unreachable_server_is_the_only_finding():
    checks = diagnose(Fake(**{"/api/health": KeplerError("can't reach Kepler at http://kepler.test")}))
    assert checks == [("error", "server", "can't reach Kepler at http://kepler.test")]


def test_a_rejected_key_stops_the_checks_there():
    checks = diagnose(Fake(**{"/api/settings": KeplerError("HTTP 401: access key required")}))
    assert checks[-1][:2] == ("error", "access key") and len(checks) == 2


def test_problems_are_found_and_explained():
    now = time.time()
    checks = diagnose(Fake(**{
        "/api/health": {"seeding": False, "last_tick": now - 600, "last_error": "OperationalError: database is locked"},
        "/api/settings": {"slack_webhook_url": ""},
        "/api/overview": {"metrics": [{"name": "signups", "status": "stale", "model": "base", "open_incidents": [{}],
                                       "muted_until": now + 3600}]},
        "/api/connectors": [{"id": 2, "name": "Postgres: signups", "last_status": "error: OperationalError: no route",
                             "last_run": now - 30, "interval_s": 60}],
    }))
    found = {(level, check) for level, check, _ in checks}
    assert {("error", "worker"), ("warn", "data"), ("error", "pull #2"), ("warn", "alerts"), ("info", "muted"),
            ("info", "incidents")} <= found


def test_stale_models_with_retraining_off_are_flagged():
    now = time.time()
    checks = diagnose(Fake(**{"/api/health": {"seeding": False, "last_tick": now - 3, "auto_train": False},
                              "/api/models": {"metrics": [{"trained_at": now - 30 * 86400}]}}))
    assert any(lv == "warn" and ck == "models" and "retraining is off" in dt for lv, ck, dt in checks)
