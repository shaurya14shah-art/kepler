"""Metrics that report less often than every 5 minutes: detected, and shown as such."""
import time

import numpy as np
from fastapi.testclient import TestClient

from kepler import api, db


def _upload(c, name, values, step):
    t0 = (int(time.time()) // 3600 - len(values)) * 3600
    rows = "".join(f"{t0 + i * 300},{name},{v}\n" for i, v in enumerate(np.repeat(values, step)))
    r = c.post("/api/import/csv", files={"file": (f"{name}.csv", "timestamp,metric,value\n" + rows, "text/csv")},
               data={"agg": "mean"})
    assert r.status_code == 200, r.text
    return next(m["id"] for m in c.get("/api/overview").json()["metrics"] if m["name"] == name)


def test_the_series_api_says_how_often_a_metric_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "kepler.db")
    db.init_db()
    db.set_setting("demo_mode", "0")
    rng = np.random.default_rng(1)
    with TestClient(api.app) as c:
        c.headers["X-Kepler-Key"] = db.get_settings()["api_key"]
        hourly = _upload(c, "ad_cpc", rng.normal(0.5, 0.05, 5 * 24), 12)
        five_min = _upload(c, "cpu_pct", rng.normal(40, 3, 5 * 24 * 12), 1)
        assert c.get(f"/api/metrics/{hourly}/series?hours=48").json()["reports_every_s"] == 3600
        assert c.get(f"/api/metrics/{five_min}/series?hours=48").json()["reports_every_s"] == 300
