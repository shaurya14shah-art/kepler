"""Benchmark Kepler's chat on a held-out exam: does it understand what people mean, and does it get maths right?

stress/bot_exam.jsonl holds messages written by many different "users" (an on-call SRE, a non-native speaker, a Gen-Z
texter, a polite founder…) and subjects (definitions, physics, finance, puzzles…), each labelled with what a right
reading is: an intent name, "math" (with the expected answer), "define", "chat" or "lookup". None of them is used for
training, so the score measures how well the bot generalises.

    cd backend && .venv/bin/python -I stress/bench_bot.py [--save] [--failures out.jsonl] [--show N]

It runs the built-in bot only: a throwaway home, so your taught examples and library don't count, and offline.
- **Understood:** the message was routed right (the intent, or maths / a definition / small talk / a lookup).
  Greetings, thanks and small talk count as one family: answering "hey, how's it going" with small talk is fine.
- **Solved:** a maths message got an answer that agrees with the exam's (within 1%), or any answer when the exam's
  has no number to compare. The exam keys were written by people/bots too, so a disagreement is a lead, not proof.
--save writes stress/bench_bot_baseline.json; later runs print the change against it.
"""
import argparse
import json
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

os.environ["KEPLER_WEB"] = "off"
HERE = Path(__file__).resolve().parent
EXAM = HERE / "bot_exam.jsonl"
BASELINE = HERE / "bench_bot_baseline.json"
FAMILY = {"greet": {"greet", "chat"}, "thanks": {"thanks", "chat"}, "chat": {"chat", "greet", "thanks"}}
NUM = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?(?:e-?\d+)?")


def _numbers(s: str) -> list[float]:
    out = []
    for m in NUM.findall(s.replace("−", "-")):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


def agrees(expected: str, got: str) -> bool | None:
    """Whether Kepler's answer contains the exam's main number (within 1%); None when the key has no number."""
    want = _numbers(expected)
    if not want:
        return None
    have = _numbers(got)
    target = want[0]
    return any(abs(h - target) <= max(0.01 * abs(target), 0.005) for h in have)


def read(mind, text: str) -> tuple[str, str]:
    """(what Kepler made of it, its answer text): an intent name, "math", "math?" (couldn't solve), "define",
    "chat" or "lookup"."""
    from kepler.bot import model
    from kepler.bot.slots import Context, extract
    th = mind.think(text)
    if th.kind in ("math", "steps"):
        return ("math" if th.solution.ok else "math?"), th.solution.answer
    if th.kind == "knowledge":
        k = th.knowledge
        return ("chat" if k["kind"] == "small_talk" else "define"), k.get("title") or k["text"][:60]
    if th.kind == "lookup":
        return "lookup", ""
    _, delex = extract(th.read_as, Context())
    return model.classify(delex, k=1)[0][0], ""


def run(items: list[dict]) -> dict:
    import kepler.device as device
    device.HOME = Path(tempfile.mkdtemp(prefix="kepler-bench-bot-"))  # the built-in bot, untouched by your lessons
    from kepler.bot import model
    from kepler.bot.mind import Mind
    model.load()
    by = defaultdict(Counter)
    failures = []
    for it in items:
        got, answer = read(Mind(), it["text"])
        want = it["expect"]
        ok = got in FAMILY.get(want, {want})
        solved = None
        if want == "math" and got == "math":
            solved = agrees(it.get("answer", ""), answer)
        cat = want if want in ("math", "define", "chat", "lookup") else "intent"
        by[cat]["n"] += 1
        by[cat]["understood"] += ok
        if want == "math":
            by[cat]["solved"] += solved is not False and got == "math"
            by[cat]["checked"] += solved is not None
            by[cat]["agreed"] += bool(solved)
        if not ok or solved is False:
            failures.append({**it, "got": got, "kepler_answer": answer,
                             "why": "misread" if not ok else "answer differs from the key"})
    total = sum(c["n"] for c in by.values())
    understood = sum(c["understood"] for c in by.values())
    return {"n": total, "understood": understood, "by": {k: dict(v) for k, v in sorted(by.items())}, "failures": failures}


def report(res: dict, base: dict | None) -> None:
    def pct(a, b):
        return f"{a / b:.1%}" if b else "-"

    line = f"understood {res['understood']}/{res['n']} ({pct(res['understood'], res['n'])})"
    if base:
        line += f"   baseline {base['understood']}/{base['n']} ({pct(base['understood'], base['n'])})"
    print(line)
    for cat, c in res["by"].items():
        extra = ""
        if cat == "math":
            extra = (f" · solved {c.get('solved', 0)}/{c['n']} · answer agrees with the key {c.get('agreed', 0)}"
                     f"/{c.get('checked', 0)} checkable")
        b = (base or {}).get("by", {}).get(cat)
        was = f"   (was {pct(b['understood'], b['n'])})" if b else ""
        print(f"  {cat:<8} understood {c['understood']:>4}/{c['n']:<4} {pct(c['understood'], c['n']):>6}{extra}{was}")
    misread = Counter((f["expect"], f["got"]) for f in res["failures"] if f["why"] == "misread")
    if misread:
        print("most common misreadings (wanted → got):")
        for (w, g), n in misread.most_common(12):
            print(f"  {n:>4}  {w} → {g}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--exam", type=Path, default=EXAM)
    ap.add_argument("--save", action="store_true", help=f"save as the baseline ({BASELINE.name})")
    ap.add_argument("--failures", type=Path, help="write every failure here (JSON lines)")
    ap.add_argument("--show", type=int, default=0, help="print this many failures")
    args = ap.parse_args()
    items = [json.loads(line) for line in args.exam.read_text().splitlines() if line.strip()]
    res = run(items)
    base = json.loads(BASELINE.read_text()) if BASELINE.exists() and not args.save else None
    report(res, base)
    if args.failures:
        args.failures.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in res["failures"]))
    for f in res["failures"][:args.show]:
        print(f"  [{f['source']}] {f['text']!r}: wanted {f['expect']} {f.get('answer', '')!r}, got {f['got']} "
              f"{f['kepler_answer']!r}")
    if args.save:
        BASELINE.write_text(json.dumps({k: v for k, v in res.items() if k != "failures"}, indent=1) + "\n")
        print(f"saved {BASELINE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
