"""Compare (all three models on one metric, side by side): the same answer as when it was computed inside the request,
reused only while nothing it depends on has changed, and still answered when the child process is unavailable."""
import json
import threading
import time
from concurrent.futures import Future
from concurrent.futures.process import BrokenProcessPool

import pytest

from kepler import api, db, simulator
from kepler.db import BUCKET, DAY
from kepler.engine import compare, detector, tiers
from kepler.engine.classifier import FeedbackModel

NOW = 1792508400 // BUCKET * BUCKET - BUCKET  # Tuesday 15:00 UTC (as in test_engine): normal traffic


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    old, db.DB_PATH = db.DB_PATH, tmp_path_factory.mktemp("compare") / "kepler.db"
    db.init_db()
    simulator.seed(now=NOW + BUCKET)
    with db.session(write=True) as c:  # a bad iOS release: 10x the 5xx errors for 30 min, so some models answer "anomaly"
        mid = c.execute("SELECT id FROM metrics WHERE name = 'api_errors'").fetchone()["id"]
        rows = c.execute("SELECT ts, segment, value_sum, n FROM points WHERE metric_id = ? AND ts > ? AND segment LIKE "
                         "'%platform=ios%'", (mid, NOW - 6 * BUCKET)).fetchall()
        db.add_points(c, mid, [(r["ts"], r["segment"], 10 * r["value_sum"], r["n"]) for r in rows], mode="replace")
    compare._MEMO.clear()
    yield
    compare.shutdown()
    compare._MEMO.clear()
    db.DB_PATH = old


def _reference(metric_id: int) -> dict:
    """The comparison exactly as the endpoint computed it before it moved to engine/compare (in the request thread)."""
    with db.session() as c:
        m = api._metric(c, metric_id)
        last_ts = c.execute("SELECT MAX(ts) t FROM points WHERE metric_id = ?", (m["id"],)).fetchone()["t"]
        end = min(db.bucket_of(time.time()) - BUCKET, last_ts)
        st = db.get_settings(c)
        fm = FeedbackModel.load(c)
        out = []
        for t in tiers.TIERS.values():
            t0 = time.perf_counter()
            best = None
            series = detector.watched_slices(c, m, end, t)
            for s in series:
                sc = detector._score_window(c, m, end, t.history_days, s, t)
                i = len(sc["ts"]) - 1
                v, e, z = float(sc["v"][i]), float(sc["expected"][i]), float(sc["z"][i])
                run = detector.run_length(sc["z"], i)
                anom, conf, rel, _ = detector.evaluate(m, s, end, v, e, z, lambda sc=sc, i=i: float(sc["base_z"][i]),
                                                       max(run, 1), fm, st, t)
                if best is None or conf > best["confidence"]:
                    best = {"series": s or "(whole metric)", "anomaly": bool(anom), "confidence": round(conf, 3),
                            "observed": api._clean(v), "expected": api._clean(e), "z": api._clean(z)}
            ms = (time.perf_counter() - t0) * 1000
            out.append({"tier": t.id, "name": t.name, "series_watched": len(series), "ms": round(ms, 1),
                        "verdict": "anomaly" if best and best["anomaly"] else "normal", "top": best,
                        "learned_filter": t.learned_filter, "reasoning": t.reasoning,
                        **({"price_preview": t.price_preview} if tiers.PAYMENTS_ENABLED else {})})
        return {"metric": m["name"], "at": end, "current": detector.tier_for(c, m).id, "tiers": out,
                "paywall": tiers.PAYWALL}


def _shown(res: dict) -> dict:
    """The response as a client reads it, without the timings and the reused flag."""
    res = json.loads(json.dumps(res))
    res.pop("reused", None)
    for t in res["tiers"]:
        t.pop("ms")
    return res


@pytest.fixture(scope="module")
def references(seeded) -> dict:
    return {mid: _reference(mid) for mid in _metric_ids()}


def _metric_ids() -> list[int]:
    with db.session() as c:
        return [r["id"] for r in c.execute("SELECT id FROM metrics WHERE source = 'demo' ORDER BY id")]


def _signups() -> int:
    with db.session() as c:
        return c.execute("SELECT id FROM metrics WHERE name = 'signups'").fetchone()["id"]


@pytest.mark.parametrize("isolate", [True, False], ids=["child-process", "in-process"])
def test_compare_output_is_unchanged(references, monkeypatch, isolate):
    monkeypatch.setattr(compare, "ISOLATE", isolate)
    if not isolate:
        monkeypatch.setattr(compare, "_pool", lambda: pytest.fail("in-process comparison started a child process"))
    verdicts = set()
    for mid, ref in references.items():
        compare._MEMO.clear()
        new = api.compare_tiers(mid)
        assert "reused" not in new
        assert _shown(new) == _shown(ref)
        assert list(new) == list(ref) and [list(t) for t in new["tiers"]] == [list(t) for t in ref["tiers"]]
        assert all(t["ms"] > 0 for t in new["tiers"])
        verdicts |= {t["verdict"] for t in new["tiers"]}
    assert verdicts == {"anomaly", "normal"}
    assert compare._POOL is not None or not isolate  # the models really ran in the child process


def test_compare_marks_the_model_in_use(references):
    mid = _signups()
    ref = _shown(references[mid])
    try:
        for tier in ("orbit", "time", "area"):
            with db.session(write=True) as c:
                c.execute("UPDATE metrics SET tier = ? WHERE id = ?", (tier, mid))
            res = _shown(api.compare_tiers(mid))
            assert res["current"] == tier and {**res, "current": ref["current"]} == ref
    finally:
        with db.session(write=True) as c:
            c.execute("UPDATE metrics SET tier = NULL WHERE id = ?", (mid,))


def _touch(mid: int, ts: int):
    """A write that bumps the metric's data version without changing any value."""
    with db.session(write=True) as c:
        seg = c.execute("SELECT segment FROM points WHERE metric_id = ? AND ts = ? LIMIT 1", (mid, ts)).fetchone()
        db.add_points(c, mid, [(ts, seg["segment"] if seg else "", 0.0, 0.0)], mode="add")


def _set(sql: str, *params):
    with db.session(write=True) as c:
        c.execute(sql, params)


def test_compare_is_reused_until_something_it_depends_on_changes(seeded, monkeypatch):
    mid = _signups()
    with db.session() as c:
        st, bad = db.get_settings(c), api._metric(c, mid)["bad_direction"]
    compare._MEMO.clear()
    first = api.compare_tiers(mid)
    end = first["at"]
    again = api.compare_tiers(mid)
    assert "reused" not in first and again["reused"] is True and again["tiers"] == first["tiers"]

    def reused_after(change) -> bool:
        change()
        res = api.compare_tiers(mid)
        assert api.compare_tiers(mid)["reused"] is True  # (and it is kept again)
        return res.get("reused", False)

    try:
        assert reused_after(lambda: _touch(mid, end - 20 * DAY * BUCKET))  # older than every model's window
        assert not reused_after(lambda: _touch(mid, end - DAY * BUCKET))   # inside it
        assert not reused_after(detector.bump_models)                       # a retrain
        assert not reused_after(lambda: _set("UPDATE settings SET value = '0.6' WHERE key = 'sensitivity'"))
        assert not reused_after(lambda: _set("UPDATE settings SET value = '25' WHERE key = 'min_change_pct'"))
        assert not reused_after(lambda: _set("UPDATE metrics SET bad_direction = 'both' WHERE id = ?", mid))
        assert _shown(api.compare_tiers(mid)) == _shown(_reference(mid))  # what it computed again is right
        monkeypatch.setattr(compare, "MAX_AGE_S", 0)
        assert not compare.latest(*_inputs(mid, end))[1]                   # never older than MAX_AGE_S
    finally:
        for k in ("sensitivity", "min_change_pct"):
            _set("UPDATE settings SET value = ? WHERE key = ?", st[k], k)
        _set("UPDATE metrics SET bad_direction = ? WHERE id = ?", bad, mid)


def _inputs(mid: int, end: int):
    with db.session() as c:
        return dict(api._metric(c, mid)), end, db.get_settings(c)


def test_compare_counts_points_after_its_bucket(seeded):
    """Slices are chosen from every point of the last day, also those after the compared bucket."""
    mid = _signups()
    end = _reference(mid)["at"] - BUCKET
    compare._MEMO.clear()
    assert not compare.latest(*_inputs(mid, end))[1]
    assert compare.latest(*_inputs(mid, end))[1]
    _touch(mid, end + BUCKET)
    assert not compare.latest(*_inputs(mid, end))[1]


def test_concurrent_compares_share_one_run(seeded, monkeypatch):
    mid = _metric_ids()[1]
    compare._MEMO.clear()
    calls, release, real = [], threading.Event(), compare._run

    def slow_run(*a):
        calls.append(a)
        release.wait(10)
        return real(*a)

    monkeypatch.setattr(compare, "_run", slow_run)
    results = [None] * 6

    def ask(k):
        results[k] = api.compare_tiers(mid)

    threads = [threading.Thread(target=ask, args=(k,)) for k in range(len(results))]
    for t in threads:
        t.start()
    time.sleep(0.3)
    release.set()
    for t in threads:
        t.join(60)
    assert len(calls) == 1
    assert all(r is not None and r["tiers"] == results[0]["tiers"] for r in results)


class _NoProcesses:
    def submit(self, *a, **k):
        raise OSError("can't start new processes here")


class _DeadChild:
    def submit(self, *a, **k):
        f = Future()
        f.set_exception(BrokenProcessPool("the child process died"))
        return f

    def shutdown(self, **k):
        pass


@pytest.mark.parametrize("pool", [_NoProcesses, _DeadChild])
def test_compare_answers_in_process_when_the_child_cannot(seeded, monkeypatch, pool):
    monkeypatch.setattr(compare, "_POOL", pool())
    mid = _metric_ids()[2]
    compare._MEMO.clear()
    assert _shown(api.compare_tiers(mid)) == _shown(_reference(mid))
