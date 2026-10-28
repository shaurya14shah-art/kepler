"""Intent classifier: TF-IDF (word 1-2 grams + character 2-5 grams) → logistic regression.

Trained on synthetic utterances generated from intents.py, plus the phrasings corpus (corpus/phrasings.json: real-user
wordings per intent, written and cross-checked in bulk). Inputs are delexicalised first (metric names →
'metricx', incident ids → 'numx', …) so the model learns sentence *shapes*, not specific names.
"""
import hashlib
import json
import pickle
import random
import re
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, make_pipeline

from .. import device
from . import store
from .intents import FILL, INTENTS

PHRASINGS = Path(__file__).with_name("corpus") / "phrasings.json"
CORPUS_PER_PHRASING = 2  # a corpus phrasing counts less than a hand-written template (6), there are many more of them
TOKENS = {"metric": "metricx", "id": "numx", "n": "numx", "dur": "durx", "pct": "pctx", "tool": "toolx",
          "scenario": "scenx", "slice": "slicex", "tier": "tierx"}
PREFIXES = ["", "", "", "kepler ", "hey kepler ", "can you ", "please ", "could you ", "quick question ", "ok "]
SUFFIXES = ["", "", "", "?", " please", " now", "!", " thanks", " for me"]
TAUGHT_WEIGHT = 8   # each sentence you teach counts as 8 synthetic ones, so it wins over the built-in templates
_cache: tuple[str, object] | None = None


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def _fill(template: str, rng: random.Random, delex: bool) -> str:
    def sub(m):
        key = m.group(1)
        if key == "sev":
            return rng.choice(FILL["sev"])
        return TOKENS[key] if delex else rng.choice(FILL[key])
    return re.sub(r"\{(\w+)\}", sub, template)


def dataset(seed: int = 0, per_template: int = 6) -> tuple[list[str], list[str]]:
    rng = random.Random(seed)
    X, y = [], []
    for intent, spec in INTENTS.items():
        for tpl in spec["t"]:
            for k in range(per_template):
                s = _fill(tpl, rng, delex=k % 3 != 2)  # mostly delexicalised, some with raw values
                if k:
                    s = rng.choice(PREFIXES) + s + rng.choice(SUFFIXES)
                X.append(normalise(s))
                y.append(intent)
    for intent, phrasings in corpus().items():
        if intent not in INTENTS:
            continue
        for tpl in phrasings:
            for k in range(CORPUS_PER_PHRASING):
                X.append(normalise(_fill(tpl, rng, delex=k == 0)))
                y.append(intent)
    return X, y


def corpus() -> dict[str, list[str]]:
    """intent → phrasings from corpus/phrasings.json ({} when it's missing or unreadable)."""
    try:
        data = json.loads(PHRASINGS.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def taught(data: dict | None = None, seed: int = 0) -> tuple[list[str], list[str]]:
    """Your examples from bot_training.json, each repeated with polite prefixes/suffixes."""
    data = store.load() if data is None else data
    known = set(INTENTS) | set(data["intents"])
    rng = random.Random(seed)
    X, y = [], []
    for ex in data["examples"]:
        if ex["intent"] not in known:
            continue
        base = normalise(ex["delex"])
        X.append(base)
        y.append(ex["intent"])
        for _ in range(TAUGHT_WEIGHT - 1):
            X.append(normalise(rng.choice(PREFIXES) + base + rng.choice(SUFFIXES)))
            y.append(ex["intent"])
    return X, y


def describe(intent: str) -> str:
    if intent == "math":
        return "answer a maths question (reasoning engine)"
    if intent in INTENTS:
        return INTENTS[intent]["desc"]
    return store.load()["intents"].get(intent, {}).get("desc", intent.replace("_", " "))


def _fingerprint() -> str:
    src = Path(__file__).with_name("intents.py").read_bytes() + Path(__file__).read_bytes()
    try:
        src += PHRASINGS.read_bytes()
    except OSError:
        pass
    return hashlib.sha1(src, usedforsecurity=False).hexdigest()[:12] + "-" + store.fingerprint()


def train(data: dict | None = None):
    X, y = dataset()
    tx, ty = taught(data)
    X, y = X + tx, y + ty
    feats = FeatureUnion([
        ("w", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True, token_pattern=r"[^\s]+")),
        ("c", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True)),
    ])
    pipe = make_pipeline(feats, LogisticRegression(C=12, max_iter=3000))
    pipe.fit(X, y)
    return pipe


def load():
    """Train once per intent-catalog + taught-examples version and cache it under ~/.kepler."""
    global _cache
    key = _fingerprint()
    if _cache is not None and _cache[0] == key:
        return _cache[1]
    home = device.HOME
    path = home / f"bot-{key}.pkl"
    try:
        pipe = pickle.loads(path.read_bytes())  # only ever a file this module wrote itself
    except (OSError, pickle.UnpicklingError, EOFError, AttributeError):
        pipe = train()
        try:
            home.mkdir(parents=True, exist_ok=True)
            for old in home.glob("bot-*.pkl"):
                old.unlink()
            path.write_bytes(pickle.dumps(pipe))
        except OSError:
            pass
    _cache = (key, pipe)
    return pipe


def classify(delexicalised: str, k: int = 3) -> list[tuple[str, float]]:
    pipe = load()
    probs = pipe.predict_proba([normalise(delexicalised)])[0]
    ranked = sorted(zip(pipe.classes_, probs), key=lambda x: -x[1])
    return [(str(i), float(p)) for i, p in ranked[:k]]
