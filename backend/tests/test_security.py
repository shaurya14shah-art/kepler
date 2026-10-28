"""Security regressions: things that must never come back."""
import pickle

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from kepler.engine.classifier import FEATURES, FeedbackModel, LinearScorer


def test_feedback_model_json_matches_sklearn():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(60, len(FEATURES)))
    y = (X[:, 0] + rng.normal(scale=0.5, size=60) > 0).astype(int)
    pipe = make_pipeline(StandardScaler(), LogisticRegression(max_iter=500)).fit(X, y)
    scorer = LinearScorer.from_json(LinearScorer.from_pipeline(pipe).to_json())
    for row in X[:10]:
        assert abs(scorer.probability(row) - pipe.predict_proba([row])[0, 1]) < 1e-9


class _Row(dict):
    pass


class _Conn:
    def __init__(self, data):
        self.data = data

    def execute(self, *a):
        class R:
            def fetchone(_):
                return _Row(data=self.data, meta_json='{"n_labels": 30}')
        return R()


def test_pickled_model_in_database_is_never_loaded():
    class Boom:
        def __reduce__(self):
            return (exec, ("raise SystemExit('pickle was executed')",))
    fm = FeedbackModel.load(_Conn(pickle.dumps(Boom())))
    assert fm.pipe is None  # ignored, not unpickled


def test_demo_controls_only_in_demo_mode(monkeypatch):
    from fastapi import HTTPException

    from kepler import api, db

    monkeypatch.setattr(db, "get_settings", lambda conn=None: {"demo_mode": "0"})
    for fn in (lambda: api.inject(api.InjectIn(scenario="ios_release_bug")), api.reset_demo):
        try:
            fn()
            raise AssertionError("demo control ran with demo mode off")
        except HTTPException as e:
            assert e.status_code == 404


def test_unknown_api_path_is_404_not_dashboard():
    from fastapi import HTTPException

    from kepler import api

    if not hasattr(api, "spa"):
        return  # no dashboard build present
    for path in ("api", "api/nope", "v1/nope"):
        try:
            api.spa(path)
            raise AssertionError(f"{path} served the dashboard")
        except HTTPException as e:
            assert e.status_code == 404


# ---------------------------------------------------------------- dashboard sign-in

def _client():
    from fastapi.testclient import TestClient

    from kepler.api import app
    return TestClient(app)


def test_gate_blocks_without_key_and_signin_unlocks():
    from kepler import db, security
    with _client() as c:
        assert c.get("/api/overview").status_code == 401
        assert c.get("/api/session").json() == {"auth_required": True, "signed_in": False}
        key = db.get_settings()["api_key"]
        r = c.post("/api/session", json={"key": key})
        assert r.status_code == 200
        cookie = r.cookies.get(security.COOKIE)
        assert cookie and cookie != key  # a derived token, never the key itself
        assert "httponly" in r.headers["set-cookie"].lower() and "samesite=strict" in r.headers["set-cookie"].lower()
        assert c.get("/api/overview").status_code == 200
        assert c.get("/api/session").json()["signed_in"] is True
        c.delete("/api/session")
        c.cookies.clear()
        assert c.get("/api/overview").status_code == 401


def test_wrong_keys_are_rate_limited(monkeypatch):
    from kepler import security
    monkeypatch.setattr(security, "_failures", {})
    with _client() as c:
        codes = [c.post("/api/session", json={"key": f"kp_wrong{i}"}).status_code for i in range(security.MAX_FAILURES + 2)]
    assert codes[:security.MAX_FAILURES] == [401] * security.MAX_FAILURES and codes[-1] == 429


def test_rotating_the_key_signs_browsers_out():
    from kepler import db
    with _client() as c:
        c.post("/api/session", json={"key": db.get_settings()["api_key"]})
        assert c.get("/api/overview").status_code == 200
        c.post("/api/settings/rotate-key")
        assert c.get("/api/overview").status_code == 401


def test_cli_finds_the_key_of_a_local_server(tmp_path, monkeypatch):
    import json as _json
    import sqlite3

    from kepler.cli import client as cl
    dbfile = tmp_path / "k.db"
    with sqlite3.connect(dbfile) as conn:
        conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO settings VALUES ('api_key', 'kp_local123')")
    info = tmp_path / "servers.json"
    info.write_text(_json.dumps({"8123": str(dbfile)}))
    monkeypatch.setattr(cl, "SERVER_INFO", info)
    monkeypatch.delenv("KEPLER_DB", raising=False)
    assert cl.local_key("http://127.0.0.1:8123") == "kp_local123"
    assert cl.local_key("https://kepler.example.com") is None  # never for a remote server
