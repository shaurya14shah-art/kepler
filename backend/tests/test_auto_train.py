"""Models retrain on their own (api.retrain_due): a server no longer keeps the models from its first `kepler train`."""
import time

import pytest

from kepler import api, db

NOW = int(time.time())


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "kepler.db")
    db.init_db()
    with db.session(write=True) as c:
        yield c


def _metric(c, name, days):
    mid = db.ensure_metric(c, name, agg="sum", bad_direction="both", source="push")
    db.add_points(c, mid, [(NOW - days * 86400, "", 1.0, 1.0), (NOW, "", 1.0, 1.0)], mode="replace")
    return mid


def test_a_metric_with_a_week_of_data_and_no_model_is_due(conn):
    _metric(conn, "young", 3)
    assert not api.retrain_due(conn, NOW)
    _metric(conn, "ready", 8)
    assert api.retrain_due(conn, NOW)


def test_models_retrain_once_they_are_a_week_old(conn):
    mid = _metric(conn, "signups", 30)
    conn.execute("INSERT INTO models(metric_id, slice, kind, trained_at, n_points, params_json) VALUES (?, '', 'custom', ?, 1, '{}')",
                 (mid, NOW - 3600))
    assert not api.retrain_due(conn, NOW)
    assert api.retrain_due(conn, NOW + api.AUTO_TRAIN_EVERY_S)


def test_the_worker_starts_one_training_when_due(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "worker.db")
    db.init_db()
    with db.session(write=True) as c:  # (committed: the worker reads with its own connection)
        _metric(c, "ready", 8)
    started = []
    monkeypatch.setattr(api.config, "AUTO_TRAIN", True)
    monkeypatch.setattr(api, "train", lambda force=False: started.append(force))
    monkeypatch.setitem(api.state, "auto_train_checked", 0)
    api._auto_train(NOW)
    api._auto_train(NOW + 60)  # checked an hour at most
    for _ in range(50):
        if started:
            break
        time.sleep(0.01)
    assert started == [True]
    monkeypatch.setattr(api.config, "AUTO_TRAIN", False)
    monkeypatch.setitem(api.state, "auto_train_checked", 0)
    api._auto_train(NOW + 7200)
    time.sleep(0.05)
    assert started == [True]
