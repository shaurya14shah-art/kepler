"""The general request-size limit (api.BodyLimit): too-large bodies get a 413 before anything parses them."""
from fastapi.testclient import TestClient

from kepler import api


def test_a_declared_oversize_body_is_refused_up_front(monkeypatch):
    monkeypatch.setattr(api, "MAX_BODY_BYTES", 1000)
    with TestClient(api.app) as c:
        r = c.post("/api/session", json={"key": "x" * 2000})
        assert r.status_code == 413
        assert "larger than" in r.json()["detail"]


def test_an_undeclared_oversize_body_is_counted_and_refused(monkeypatch):
    monkeypatch.setattr(api, "MAX_BODY_BYTES", 1000)

    def chunks():  # no Content-Length: sent chunked, 1,600 bytes in all
        for _ in range(4):
            yield b"x" * 400
    with TestClient(api.app) as c:
        r = c.post("/api/session", content=chunks(), headers={"content-type": "application/json"})
        assert r.status_code == 413


def test_normal_bodies_are_untouched(monkeypatch):
    monkeypatch.setattr(api, "MAX_BODY_BYTES", 1000)
    with TestClient(api.app) as c:
        r = c.post("/api/session", json={"key": "kp_wrong"})
        assert r.status_code in (401, 429)  # judged on the key, not the size


def test_csv_uploads_have_their_own_larger_limit(monkeypatch):
    monkeypatch.setattr(api, "MAX_BODY_BYTES", 1000)
    with TestClient(api.app) as c:
        key = _key()
        body = "timestamp,metric,value\n" + "".join(f"{1790000000 + i * 300},limit_test,1\n" for i in range(200))
        r = c.post("/api/import/csv", headers={"X-Kepler-Key": key}, files={"file": ("h.csv", body, "text/csv")})
        assert len(body) > 1000 and r.status_code == 200


def _key() -> str:
    from kepler import db
    return db.get_settings()["api_key"]
