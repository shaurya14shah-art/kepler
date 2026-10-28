"""The bot's training corpus (kepler/bot/corpus): phrasings per intent and extra knowledge, written in bulk and
cross-checked. These guard its shape, so a bad merge can't break training or the knowledge base."""
import json
import re
from pathlib import Path

from kepler.bot import knowledge, model
from kepler.bot.intents import INTENTS

CORPUS = Path(model.__file__).with_name("corpus")


def test_phrasings_are_valid_training_data():
    data = json.loads((CORPUS / "phrasings.json").read_text())
    for intent, phrasings in data.items():
        assert intent in INTENTS, intent
        allowed = set(re.findall(r"\{(\w+)\}", " ".join(INTENTS[intent]["t"])))
        for p in phrasings:
            assert p == p.strip().lower() and p, (intent, p)
            assert set(re.findall(r"\{(\w+)\}", p)) <= allowed, (intent, p)


def test_no_phrasing_belongs_to_two_intents():
    data = json.loads((CORPUS / "phrasings.json").read_text())
    owner = {}
    for intent, phrasings in data.items():
        for p in phrasings:
            assert owner.setdefault(p, intent) == intent, (p, owner[p], intent)


def test_corpus_phrasings_reach_the_training_set():
    data = model.corpus()
    X, y = model.dataset()
    for intent, phrasings in list(data.items())[:3]:
        if phrasings:
            assert y.count(intent) >= len(INTENTS[intent]["t"]) * 6 + len(phrasings) * model.CORPUS_PER_PHRASING


def test_knowledge_corpus_never_overrides_hand_written_terms():
    data = json.loads((CORPUS / "knowledge.json").read_text())
    for d in data["entries"]:
        assert d["terms"] and d["text"].strip(), d
        e = knowledge._lookup(d["terms"][0])
        assert e is not None and e.text == d["text"], d["terms"][0]  # loaded, and the term was new
    for c in data["contrasts"]:
        assert knowledge._lookup(c["a"]) and knowledge._lookup(c["b"]), c


def test_corpus_definitions_answer_questions():
    data = json.loads((CORPUS / "knowledge.json").read_text())
    for d in data["entries"][:20]:
        a = knowledge.answer(f"what is {d['terms'][0]}")
        assert a and a["kind"] == "definition" and a["title"] == d["terms"][0], d["terms"][0]
