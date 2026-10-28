"""`kepler teach`: teaching the bot new sentences and new intents, offline."""
import io
import json

import pytest
from rich.console import Console

from kepler import device
from kepler.bot import model, store
from kepler.bot.teach import Trainer


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(device, "HOME", tmp_path)
    monkeypatch.setattr(model, "_cache", None)
    return tmp_path


def trainer():
    buf = io.StringIO()
    return Trainer(Console(file=buf, width=120, color_system=None)), buf


def test_correcting_a_sentence_changes_the_prediction(home):
    t, buf = trainer()
    odd = "gimme the vibe check on everything"
    t.handle(odd)
    assert t.last["ranked"][0][0] != "settings"
    t.handle("/n settings")
    _, delex = t.last["text"], t.last["delex"]
    assert model.classify(delex, 1)[0][0] == "settings"
    saved = json.loads((home / "bot_training.json").read_text())
    assert saved["examples"][0]["intent"] == "settings"


def test_new_intent_answers_with_its_reply(home):
    t, buf = trainer()
    t.handle("who is on call this week")
    t.handle("/new on_call Priya is on call until Friday")
    assert "on_call" in store.load()["intents"]
    t.handle("who is on call this week")
    out = buf.getvalue()
    assert "◆ on_call" in out and "Priya is on call until Friday" in out
    t.handle("/drop on_call")
    assert store.load() == {"version": 1, "examples": [], "intents": {}, "aliases": {}}


def test_undo_and_unknown_intent(home):
    t, buf = trainer()
    t.handle("/n status")                       # nothing said yet
    t.handle("hello there")
    t.handle("/n not_a_real_intent")
    assert store.load()["examples"] == []
    t.handle("/y")
    assert len(store.load()["examples"]) == 1
    t.handle("/undo")
    assert store.load()["examples"] == []
    assert t.handle("/quit") is False


def test_corrupt_training_file_is_ignored(home):
    (home / "bot_training.json").write_text("{not json")
    assert store.load()["examples"] == []
    (home / "bot_training.json").write_text(json.dumps({"examples": [{"text": 1}], "intents": {"Bad Name": {}}}))
    assert store.load() == {"version": 1, "examples": [], "intents": {}, "aliases": {}}
