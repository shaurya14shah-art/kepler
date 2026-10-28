"""What you taught the bot: your own example messages and your own intents, kept in ~/.kepler/bot_training.json.

Plain JSON (never pickle), so the file is safe to read, edit by hand, back up or share.
"""
import hashlib
import json
import re
import time

from .. import device

NAME = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


def path():
    return device.HOME / "bot_training.json"


def empty() -> dict:
    return {"version": 1, "examples": [], "intents": {}, "aliases": {}}


def load() -> dict:
    try:
        data = json.loads(path().read_text())
    except (OSError, ValueError):
        return empty()
    if not isinstance(data, dict):
        return empty()
    out = empty()
    for ex in data.get("examples") or []:
        if isinstance(ex, dict) and isinstance(ex.get("text"), str) and isinstance(ex.get("intent"), str):
            out["examples"].append({"text": ex["text"], "delex": str(ex.get("delex") or ex["text"]),
                                    "intent": ex["intent"], "at": ex.get("at", 0)})
    for name, spec in (data.get("intents") or {}).items():
        if isinstance(name, str) and NAME.match(name) and isinstance(spec, dict):
            out["intents"][name] = {"desc": str(spec.get("desc") or name.replace("_", " ")),
                                    "reply": str(spec.get("reply") or "")}
    for word, means in (data.get("aliases") or {}).items():
        if isinstance(word, str) and isinstance(means, str) and 0 < len(word) <= 40 and 0 < len(means) <= 120:
            out["aliases"][word.lower().strip()] = means.lower().strip()
    return out


def save(data: dict) -> None:
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(p)


def fingerprint() -> str:
    try:
        raw = path().read_bytes()
    except OSError:
        raw = b""
    return hashlib.sha1(raw, usedforsecurity=False).hexdigest()[:12]


def add_example(text: str, delex: str, intent: str) -> dict:
    data = load()
    # one label per sentence: re-teaching the same message replaces the old label
    key = delex.strip().lower()
    data["examples"] = [e for e in data["examples"] if e["delex"].strip().lower() != key]
    data["examples"].append({"text": text, "delex": delex, "intent": intent, "at": int(time.time())})
    save(data)
    return data


def taught_intent(text: str) -> str | None:
    """The label you gave this exact sentence, if any (lets a lesson override the maths engine too)."""
    key = " ".join(text.lower().split())
    for e in reversed(load()["examples"]):
        if " ".join(e["text"].lower().split()) == key:
            return e["intent"]
    return None


def add_intent(name: str, reply: str, desc: str = "") -> dict:
    data = load()
    data["intents"][name] = {"desc": desc or name.replace("_", " "), "reply": reply}
    save(data)
    return data


def add_alias(word: str, means: str) -> dict:
    data = load()
    data["aliases"][word.lower().strip()] = means.lower().strip()
    save(data)
    return data


def remove_alias(word: str) -> bool:
    data = load()
    gone = data["aliases"].pop(word.lower().strip(), None)
    save(data)
    return gone is not None


def remove_intent(name: str) -> dict:
    data = load()
    data["intents"].pop(name, None)
    data["examples"] = [e for e in data["examples"] if e["intent"] != name]
    save(data)
    return data


def remove_example(index: int) -> dict | None:
    data = load()
    if not 0 <= index < len(data["examples"]):
        return None
    gone = data["examples"].pop(index)
    save(data)
    return gone


def reset() -> None:
    save(empty())
