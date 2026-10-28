"""The weekly report (kepler.report): what Kepler saw, as numbers, as text, and sent to Slack and email."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from kepler import api, db, report

NOW = int(time.time())


@pytest.fixture
def week(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "kepler.db")
    db.init_db()
    db.set_setting("demo_mode", "0")  # (else starting the app seeds 21 days of demo data)
    with db.session(write=True) as c:
        a = db.ensure_metric(c, "api_errors", agg="sum", bad_direction="up", source="push")
        b = db.ensure_metric(c, "cpu_pct", agg="mean", bad_direction="both", source="csv")
        c.execute("UPDATE metrics SET muted_until = ? WHERE id = ?", (NOW + 3600, b))

        def inc(mid, ago_h, mins, severity, status="resolved", feedback=None, kind=None):
            t = NOW - ago_h * 3600
            return c.execute(
                "INSERT INTO incidents(metric_id, start_ts, end_ts, peak_ts, observed, expected, lower, upper, z, confidence, "
                "severity, direction, status, feedback, model_json, created_at) VALUES (?,?,?,?,1,1,1,1,5,0.9,?,'spike',?,?,?,?)",
                (mid, t, t + mins * 60 - 300, t, severity, status, feedback, json.dumps({"kind": kind} if kind else {}), t)).lastrowid
        first = inc(a, 30, 20, "critical", feedback=1)
        inc(a, 50, 10, "high", feedback=0)
        inc(a, 2, 5, "medium", status="open")
        inc(b, 70, 40, "high", kind="no_data")
        inc(a, 24 * 9, 15, "high")  # the week before
        c.execute("INSERT INTO incident_notes(incident_id, text, created_at) VALUES (?, 'rolled back', ?)", (first, NOW))


def test_the_numbers(week):
    with db.session() as c:
        r = report.build(c, 7, NOW)
    assert r["incidents"] == 3 and r["previous_period"] == 1
    assert r["by_severity"] == {"critical": 1, "high": 1, "medium": 1}
    assert r["top_metrics"] == [("api_errors", 3)] and r["open_now"] == 1
    assert r["median_minutes"] == 15 and r["data_outages"] == ["cpu_pct"]
    assert r["labelled"] == {"real": 1, "false": 1, "precision": 0.5} and r["unlabelled"] == 1
    assert r["muted"] == ["cpu_pct"] and r["notes"] == 1


def test_the_text(week):
    with db.session() as c:
        t = report.text(report.build(c, 7, NOW))
    for line in ("Incidents: 3 (1 critical, 1 high, 1 medium); +2 vs the 7 days before", "Most incidents: api_errors (3)",
                 "Data outages (stopped reporting): cpu_pct", "1 real, 1 false alarms (50% precision)", "Muted: cpu_pct"):
        assert line in t, line


def test_a_quiet_week(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "quiet.db")
    db.init_db()
    with db.session() as c:
        assert "No incidents. All quiet." in report.text(report.build(c, 7, NOW))


def test_sending_to_slack_and_email(week, monkeypatch):
    sent = {"slack": [], "smtp": []}

    class Ok:
        status_code = 200
    monkeypatch.setattr("httpx.post", lambda url, json=None, timeout=None: sent["slack"].append(json["text"]) or Ok())
    monkeypatch.setattr("kepler.integrations.outbound.smtp_send", lambda cfg, msg: sent["smtp"].append(msg))
    db.set_setting("slack_webhook_url", "https://hooks.slack.com/services/T0/B0/x")
    with db.session(write=True) as c:
        c.execute("INSERT INTO destinations(type, name, config_json) VALUES ('email', 'on-call', ?)",
                  (json.dumps({"host": "smtp.acme.test", "sender": "k@acme.test", "to": "a@acme.test, b@acme.test"}),))
        results = report.send(c, report.build(c, 7, NOW))
    assert [r["ok"] for r in results] == [True, True]
    assert sent["slack"][0].startswith("Kepler report, last 7 days")
    msg = sent["smtp"][0]
    assert msg["Subject"] == "[Kepler] Report: 3 incidents in 7 days" and msg["To"] == "a@acme.test, b@acme.test"


def test_the_api(week):
    with TestClient(api.app) as c:
        c.headers["X-Kepler-Key"] = db.get_settings()["api_key"]
        r = c.get("/api/report?days=7").json()
        assert r["incidents"] == 3 and r["text"].startswith("Kepler report")
        assert c.get("/api/report?days=0").status_code == 422
