"""Muting a metric's alerts for a while: incidents are still recorded, but nothing goes out."""
import time

import pytest
from fastapi.testclient import TestClient

from kepler import api, db, notify
from kepler.cli.client import KeplerError
from kepler.cli.commands import mute_until


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "kepler.db")
    db.init_db()
    db.set_setting("demo_mode", "0")
    sent = []
    monkeypatch.setattr("kepler.integrations.outbound.dispatch", lambda conn, d, kind: sent.append(("dest", kind)))
    class Ok:
        status_code, text = 200, "ok"
    monkeypatch.setattr(notify.httpx, "post", lambda *a, **k: sent.append(("slack", a[0])) or Ok())
    db.set_setting("slack_webhook_url", "https://hooks.slack.example/T0/B0")
    with db.session(write=True) as c:
        mid = db.ensure_metric(c, "signups", agg="sum", bad_direction="both", source="push")
        t = int(time.time()) // 300 * 300
        cur = c.execute("INSERT INTO incidents(metric_id, start_ts, end_ts, peak_ts, observed, expected, lower, upper, z, "
                        "confidence, severity, direction, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (mid, t, t, t, 3.0, 40.0, 30.0, 50.0, -6.0, 0.95, "critical", "drop", "open", t))
    return mid, cur.lastrowid, sent


def _notes(incident_id):
    with db.session() as c:
        return [dict(r) for r in c.execute("SELECT kind, error FROM notifications WHERE incident_id = ?", (incident_id,))]


def test_alerts_go_out_when_not_muted(workspace):
    mid, iid, sent = workspace
    with db.session(write=True) as c:
        notify.notify(c, iid, "opened")
    assert ("dest", "opened") in sent and any(s[0] == "slack" for s in sent)


def test_a_muted_metric_records_the_incident_but_sends_nothing(workspace):
    mid, iid, sent = workspace
    with db.session(write=True) as c:
        c.execute("UPDATE metrics SET muted_until = ? WHERE id = ?", (int(time.time()) + 3600, mid))
        notify.notify(c, iid, "opened")
    assert sent == []
    assert _notes(iid)[0]["error"].startswith("muted until")
    with db.session(write=True) as c:  # the mute ends before the incident resolves: no 'resolved' for an unsent alert
        c.execute("UPDATE metrics SET muted_until = 0 WHERE id = ?", (mid,))
        notify.notify(c, iid, "resolved")
    assert sent == []


def test_the_api_mutes_unmutes_and_caps_a_mute_at_30_days(workspace):
    mid, _, _ = workspace
    key = db.get_settings()["api_key"]
    h = {"X-Kepler-Key": key}
    with TestClient(api.app) as c:
        until = int(time.time()) + 7200
        assert c.patch(f"/api/metrics/{mid}", json={"muted_until": until}, headers=h).json()["muted_until"] == until
        assert next(m for m in c.get("/api/overview", headers=h).json()["metrics"] if m["id"] == mid)["muted_until"] == until
        assert c.patch(f"/api/metrics/{mid}", json={"muted_until": int(time.time()) + 31 * 86400}, headers=h).status_code == 400
        assert c.patch(f"/api/metrics/{mid}", json={"muted_until": 0}, headers=h).json()["muted_until"] == 0
        assert next(m for m in c.get("/api/overview", headers=h).json()["metrics"] if m["id"] == mid)["muted_until"] == 0


def test_mute_durations_on_the_command_line():
    assert mute_until("30m", now=1000) == 1000 + 1800
    assert mute_until("2h", now=0) == 7200 and mute_until("1d", now=0) == 86400
    assert mute_until("off") == 0
    with pytest.raises(KeplerError):
        mute_until("soon")
