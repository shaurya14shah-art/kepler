"""'No data' incidents: a metric that stops reporting for longer than is usual for it."""
import json

import numpy as np
import pytest

from kepler import connectors, db, notify
from kepler.cli.render import change_text
from kepler.db import BUCKET, DAY
from kepler.engine import detector
from kepler.integrations.outbound import headline

START = 1_790_000_000 // (DAY * BUCKET) * (DAY * BUCKET)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "kepler.db")
    db.init_db()
    db.set_setting("demo_mode", "0")


def _run(values, name="cpu_pct"):
    """Import a 5-minute gauge (NaN = no reading), then score it bucket by bucket like the worker."""
    rows = "".join(f"{START + i * BUCKET},{x}\n" for i, x in enumerate(values) if np.isfinite(x))
    connectors.import_csv(("timestamp,value\n" + rows).encode(), name, "mean", "both")
    with db.session(write=True) as c:
        c.execute("UPDATE metrics SET last_scored_ts = 0")
        m = c.execute("SELECT * FROM metrics WHERE name = ?", (name,)).fetchone()
        detector.backfill(c, m, START + 2 * DAY * BUCKET, START + (len(values) - 1) * BUCKET)
        return [detector.decision(i, m) for i in c.execute("SELECT * FROM incidents WHERE metric_id = ?", (m["id"],))]


def test_a_metric_that_goes_silent_opens_one_incident_and_resolves_when_data_returns(workspace):
    v = np.random.default_rng(1).normal(40, 2, 4 * DAY)
    gap = slice(3 * DAY, 3 * DAY + 36)  # 3 hours without a reading
    v[gap] = np.nan
    silent = [d for d in _run(v) if d["kind"] == "no_data"]
    assert len(silent) == 1
    d = silent[0]
    assert d["status"] == "resolved" and d["silent_since"] == START + (3 * DAY - 1) * BUCKET
    assert d["started_at"] == START + 3 * DAY * BUCKET


def test_routine_gaps_stay_quiet_but_an_unusual_one_alerts(workspace):
    v = np.random.default_rng(2).normal(40, 2, 6 * DAY)
    for day in range(6):  # a two-hour gap every day: normal for this sensor
        v[day * DAY + 100: day * DAY + 124] = np.nan
    assert not [d for d in _run(v, "sensor_a") if d["kind"] == "no_data"]
    v[4 * DAY + 150: 4 * DAY + 150 + 12 * 12] = np.nan  # 12 hours: far beyond its usual gaps
    assert [d for d in _run(v, "sensor_b") if d["kind"] == "no_data"]


def test_alerts_say_no_data_instead_of_a_change():
    d = {"kind": "no_data", "metric": "cpu_pct", "incident_id": 9, "silent_since": START, "started_at": START + 300,
         "direction": "drop", "change_pct": 0.0, "severity": "high", "where": [], "confidence": 0.99}
    assert headline(d, "opened").startswith("NO DATA: cpu_pct has sent nothing since")
    assert headline(d, "resolved") == "Resolved: cpu_pct is reporting again"
    assert notify.build_message(d, "opened")[0].startswith("📭 NO DATA: cpu_pct")
    assert change_text(d).startswith("no data since") and change_text({**d, "kind": "anomaly"}).startswith("▼")
    assert json.dumps(d)  # (and the decision stays plain JSON)
