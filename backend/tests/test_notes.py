"""Incident notes: what the team found or did, kept with the incident."""
import time

import pytest
from fastapi.testclient import TestClient

from kepler import api, db


@pytest.fixture
def incident(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "kepler.db")
    db.init_db()
    db.set_setting("demo_mode", "0")  # (else starting the app seeds 21 days of demo data)
    with db.session(write=True) as c:
        mid = db.ensure_metric(c, "api_errors", agg="sum", bad_direction="up", source="push")
        t = int(time.time()) // 300 * 300 - 3600
        iid = c.execute("INSERT INTO incidents(metric_id, start_ts, end_ts, peak_ts, observed, expected, lower, upper, z, "
                        "confidence, severity, direction, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (mid, t, t, t, 90.0, 10.0, 5.0, 15.0, 9.0, 0.99, "critical", "spike", "resolved", t)).lastrowid
    with TestClient(api.app) as client:
        client.headers["X-Kepler-Key"] = db.get_settings()["api_key"]
        yield client, mid, iid


def test_add_list_and_delete_notes(incident):
    c, _, iid = incident
    assert c.get(f"/api/incidents/{iid}").json()["notes"] == []
    first = c.post(f"/api/incidents/{iid}/notes", json={"text": "  rolled back deploy 4.2  "}).json()
    c.post(f"/api/incidents/{iid}/notes", json={"text": "root cause: a bad config flag"})
    notes = c.get(f"/api/incidents/{iid}").json()["notes"]
    assert [n["text"] for n in notes] == ["rolled back deploy 4.2", "root cause: a bad config flag"]
    left = c.delete(f"/api/incidents/{iid}/notes/{first['id']}").json()["notes"]
    assert [n["text"] for n in left] == ["root cause: a bad config flag"]
    assert c.delete(f"/api/incidents/{iid}/notes/{first['id']}").status_code == 404


def test_notes_are_validated(incident):
    c, _, iid = incident
    assert c.post(f"/api/incidents/{iid}/notes", json={"text": ""}).status_code == 422
    assert c.post(f"/api/incidents/{iid}/notes", json={"text": "   "}).status_code == 422
    assert c.post(f"/api/incidents/{iid}/notes", json={"text": "x" * 2001}).status_code == 422
    assert c.post("/api/incidents/999999/notes", json={"text": "hello"}).status_code == 404


def test_deleting_a_metric_deletes_its_incidents_notes(incident):
    c, mid, iid = incident
    c.post(f"/api/incidents/{iid}/notes", json={"text": "gone with the metric"})
    c.delete(f"/api/metrics/{mid}")
    with db.session() as conn:
        assert not conn.execute("SELECT 1 FROM incident_notes").fetchone()


def test_the_cli_prints_notes_as_text_never_markup(capsys):
    from kepler.cli import commands
    commands._print_notes([{"id": 1, "text": "[red]not markup[/] & <b>", "created_at": 1_790_000_000}])
    printed = capsys.readouterr().out
    assert "[red]not markup[/] & <b>" in printed
