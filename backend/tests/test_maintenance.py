"""Maintenance mode: every alert in the workspace paused for a while; detection and incidents go on."""
import time

import pytest
from fastapi.testclient import TestClient

from kepler import api, db, notify


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "kepler.db")
    db.init_db()
    sent = []
    monkeypatch.setattr("kepler.integrations.outbound.dispatch", lambda conn, d, kind: sent.append(kind))
    with db.session(write=True) as c:
        mid = db.ensure_metric(c, "signups", agg="sum", bad_direction="both", source="push")
        t = int(time.time()) // 300 * 300
        iid = c.execute("INSERT INTO incidents(metric_id, start_ts, end_ts, peak_ts, observed, expected, lower, upper, z, "
                        "confidence, severity, direction, status, created_at) VALUES (?,?,?,?,3,40,30,50,-6,0.95,'critical','drop','open',?)",
                        (mid, t, t, t, t)).lastrowid
    return iid, sent


def test_maintenance_mode_silences_every_metric(ws):
    iid, sent = ws
    db.set_setting("muted_until", str(int(time.time()) + 3600))
    with db.session(write=True) as c:
        notify.notify(c, iid, "opened")
        note = c.execute("SELECT error FROM notifications WHERE incident_id = ?", (iid,)).fetchone()["error"]
    assert sent == [] and note.startswith("muted until")
    db.set_setting("muted_until", str(int(time.time()) - 60))  # over: alerts go out again
    with db.session(write=True) as c:
        notify.notify(c, iid, "opened")
    assert sent == ["opened"]


def test_the_api_turns_it_on_and_off_and_caps_it(ws):
    with TestClient(api.app) as c:
        c.headers["X-Kepler-Key"] = db.get_settings()["api_key"]
        until = int(time.time()) + 7200
        assert c.put("/api/settings", json={"muted_until": until}).json()["muted_until"] == until
        assert c.get("/api/overview").json()["maintenance_until"] == until
        assert c.put("/api/settings", json={"muted_until": int(time.time()) + 31 * 86400}).status_code == 400
        assert c.put("/api/settings", json={"muted_until": 0}).json()["muted_until"] == 0
        db.set_setting("muted_until", str(int(time.time()) - 5))
        assert c.get("/api/settings").json()["muted_until"] == 0  # an expired window reads as off
