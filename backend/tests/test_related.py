"""Related incidents: other metrics that broke within 15 minutes of an incident, shown and alerted together."""
import time

import pytest
from fastapi.testclient import TestClient

from kepler import api, db, notify
from kepler.engine import detector

T = int(time.time()) // 300 * 300 - 7200


@pytest.fixture
def three(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "kepler.db")
    db.init_db()
    ids = []
    with db.session(write=True) as c:
        for name, start, obs, direction in (("api_errors", T, 90.0, "spike"), ("signups", T + 300, 4.0, "drop"),
                                            ("cpu_pct", T + 7200, 95.0, "spike")):
            mid = db.ensure_metric(c, name, agg="sum", bad_direction="both", source="push")
            ids.append(c.execute(
                "INSERT INTO incidents(metric_id, start_ts, end_ts, peak_ts, observed, expected, lower, upper, z, confidence, "
                "severity, direction, status, created_at) VALUES (?,?,?,?,?,10,5,15,8,0.95,'critical',?,'open',?)",
                (mid, start, start + 600, start, obs, direction, start)).lastrowid)
    return ids


def test_incidents_that_start_together_list_each_other(three):
    errors, signups, cpu = three
    with db.session() as c:
        by_id = {i["id"]: i for i in c.execute("SELECT * FROM incidents")}
        assert [r["metric"] for r in detector.related_incidents(c, by_id[errors])] == ["signups"]
        assert [r["incident_id"] for r in detector.related_incidents(c, by_id[signups])] == [errors]
        assert detector.related_incidents(c, by_id[cpu]) == []  # two hours later: something else


def test_the_api_and_the_first_alert_carry_them(three, monkeypatch):
    errors = three[0]
    with TestClient(api.app) as client:
        client.headers["X-Kepler-Key"] = db.get_settings()["api_key"]
        assert client.get(f"/api/incidents/{errors}").json()["decision"]["related"][0]["metric"] == "signups"
    sent = []

    class Ok:
        status_code, text = 200, "ok"
    db.set_setting("slack_webhook_url", "https://hooks.slack.com/services/T/B/x")
    monkeypatch.setattr(notify.httpx, "post", lambda url, json=None, timeout=None: sent.append(json) or Ok())
    monkeypatch.setattr("kepler.integrations.outbound.dispatch", lambda *a, **k: None)
    with db.session(write=True) as c:
        notify.notify(c, errors, "opened")
    assert "Also now: signups ▼" in sent[0]["text"]
