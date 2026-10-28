"""A live training session for Kepler's chat, typed out in the terminal so you can watch it learn.

    backend/.venv/bin/python -I scripts/train_kepler_live.py            # teaches your real Kepler (~/.kepler)
    backend/.venv/bin/python -I scripts/train_kepler_live.py --dry      # a throwaway copy; nothing is kept
    backend/.venv/bin/python -I scripts/train_kepler_live.py --fast     # no typing delay
    backend/.venv/bin/python -I scripts/train_kepler_live.py --exam     # only the final exam: is it still learned?

It drives the same trainer as `kepler teach`. Each English lesson asks a sentence Kepler gets wrong, corrects it
(/n INTENT, exactly what you'd type), then asks a different sentence with the same meaning to show the lesson
generalised. The other lessons ask indirect questions, field problems and harder maths, which the rules and the
reasoning engine answer with worked steps. It ends with an exam of questions it hasn't seen in this session.
Lessons go into ~/.kepler/bot_training.json; undo one with /undo in `kepler teach`, or all of them with /reset.
"""
import argparse
import os
import random
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("KEPLER_WEB", "off")  # offline: nothing leaves this machine

from rich.console import Console
from rich.rule import Rule
from rich.text import Text

# (asked, correct intent, a different phrasing to check it generalised)
ENGLISH = [  # sentences the built-in model gets wrong (earlier lessons, like "is the site down", are now built in)
    ("is our checkout working", "status", "is the login page working"),
    ("brilliant work", "thanks", "excellent work"),
    ("i'm new here", "help", "first time using kepler"),
    ("that one was legit", "label_real", "that alert was legit"),
]
UNDERSTANDING = [
    "hey there, how's it going?",
    "can u tell me what a median is",
    "i don't get what an anomaly is, explain like i'm five",
    "what's the difference between mean and median",
    "speed vs velocity",
    "teach me physics",
]
FIELDS = [
    ("physics", "a car accelerates from 0 to 27 m/s in 9 seconds, what is its acceleration?"),
    ("physics", "how long does a stone dropped from 20 m take to hit the ground?"),
    ("physics", "what is the kinetic energy of a 2 kg ball moving at 3 m/s?"),
    ("electrical", "what current flows through a 10 ohm resistor at 5 volts?"),
    ("electrical", "power used by a 60 W bulb in 5 hours in kWh"),
    ("chemistry", "molar mass of C6H12O6"),
    ("chemistry", "what is the pH of a 0.001 M HCl solution"),
    ("finance", "monthly payment on a 200000 loan at 6% for 30 years"),
    ("finance", "if i invest 500 a month at 7% for 20 years how much will i have"),
    ("statistics", "probability a value is less than 85 if mean is 70 and sd is 10"),
    ("geometry", "hypotenuse of a right triangle with sides 5 and 12"),
    ("trigonometry", "sine of 60 degrees"),
]
MATHS = [
    "derivative of x^3 * sin(x)",
    "integrate x * e^x",
    "solve x^2 - 5x + 6 = 0",
    "eigenvalues of [[4, 1], [2, 3]]",
    "solve y'' + y = 0",
    "prove that 1 + 2 + ... + n = n(n+1)/2",
    "does the sum of 1/n^2 converge",
    "a bat and a ball cost 1.10 in total. the bat costs 1.00 more than the ball. how much is the ball?",
]
# (question, what a right answer is: an intent name, or "math" / "knowledge")
EXAM = [
    ("is the payments page working", "status"),
    ("fantastic work", "thanks"),
    ("i'm brand new to this", "help"),
    ("is the app down?", "status"),
    ("bring up the dashboard", "open_dashboard"),
    ("stop pestering me", "set_sensitivity"),
    ("lovely to meet you", "greet"),
    ("nice work", "thanks"),
    ("could you tell me what a mole is", "knowledge"),
    ("how is acid different from base", "knowledge"),
    ("a 1200 kg car accelerates at 3 m/s^2, what force is needed?", "math"),
    ("what resistance draws 3 A from 12 V?", "math"),
    ("how many grams in 2 moles of NaCl", "math"),
    ("cos of 45 degrees", "math"),
    ("integrate cos(x)^2", "math"),
]


class Session:
    def __init__(self, console: Console, fast: bool):
        from kepler.bot import model
        from kepler.bot.teach import Trainer
        self.c, self.fast = console, fast
        self.t = Trainer(console, spinners=not fast)
        with console.status("loading Kepler's classifier…", spinner="dots"):
            model.load()

    def pause(self, s: float) -> None:
        if not self.fast:
            time.sleep(s)

    def type(self, line: str) -> None:
        """Types the line like a person would, then hands it to the trainer."""
        from kepler.cli import render as R
        self.c.print(Text("you › ", style=f"bold {R.ACCENT}"), end="")
        for ch in line:
            self.c.print(ch, end="", highlight=False)
            self.pause(random.uniform(0.015, 0.05))
        self.c.print()
        self.pause(0.3)
        self.t.handle(line)
        self.c.print()
        self.pause(1.1)

    def lesson(self, title: str, note: str) -> None:
        self.c.print()
        self.c.print(Rule(f"[bold]{title}[/]", style="grey50"))
        self.c.print(Text(note, style="grey62"))
        self.c.print()
        self.pause(1.5)

    def read(self, text: str) -> tuple[str, float]:
        """What Kepler makes of a message now, without printing: (intent or kind, confidence)."""
        from kepler.bot import model
        from kepler.bot.mind import Mind
        th = Mind().think(text)
        if th.kind == "math":
            return ("math", 1.0) if th.solution.ok else ("math?", 0.0)
        if th.kind in ("knowledge", "lookup"):
            return th.kind, 1.0
        if th.taught:
            return th.taught, 1.0
        from kepler.bot.slots import extract
        _, delex = extract(th.read_as, self.t.context())
        return model.classify(delex, k=1)[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry", action="store_true", help="train a throwaway copy; nothing is kept")
    ap.add_argument("--fast", action="store_true", help="no typing delay")
    ap.add_argument("--exam", action="store_true", help="only the final exam (teaches nothing)")
    args = ap.parse_args()
    import kepler.device as device
    if args.dry:
        device.HOME = Path(tempfile.mkdtemp(prefix="kepler-train-"))
    from kepler.bot import store
    c = Console(highlight=False)
    random.seed(7)

    c.print(Text.assemble(("◆ Kepler · live training", "bold"), ("  ·  offline, no language model", "grey50")))
    c.print(Text(f"lessons are saved in {store.path()}" + ("  (dry run: a throwaway copy)" if args.dry else ""), style="grey50"))
    s = Session(c, args.fast)

    if not args.exam:
        lessons(s, c)
    return exam(s, c, args)


def lessons(s: Session, c: Console) -> None:
    s.lesson("Lesson 1 · basic English",
             "Kepler reads each message with a trained intent classifier. Here are sentences it gets wrong. For each one: "
             "ask it, correct it with /n, then ask a different sentence with the same meaning to see whether the lesson "
             "generalised.")
    before = {}
    for asked, intent, check in ENGLISH:
        before[check] = s.read(check)
        s.type(asked)
        s.type(f"/n {intent}")
        s.type(check)
        got, p = s.read(check)
        b = before[check]
        if got != intent:
            mark = f"[yellow]~ still reads it as {got}[/]"
        elif b[0] != intent:
            mark = "[green]✓ generalised[/]"
        else:
            mark = "[green]↑ already right, now surer[/]" if p > b[1] else "[green]✓ still right[/]"
        c.print(f"  {mark}   [grey50]'{check}': before {b[0]} p={b[1]:.2f} → after {got} p={p:.2f}[/]\n")
        s.pause(1.2)
        if got != intent:  # one example wasn't enough: teach this one too, as you would
            c.print(Text("  one example wasn't enough, so teach it this sentence as well", style="grey62"))
            s.type(f"/n {intent}")

    s.lesson("Lesson 2 · understanding what you mean",
             "People rarely ask directly. Kepler rewrites indirect questions ('can you tell me what…', 'explain like I'm "
             "five', 'X vs Y') into one direct form before looking anything up, and recognises small talk.")
    for q in UNDERSTANDING:
        s.type(q)

    s.lesson("Lesson 3 · reasoning across fields",
             "Kepler reads quantities with their units, converts them to SI, works out what is being asked, picks the formula "
             "and solves it step by step, with a check. Physics, electrical, chemistry, finance, statistics, geometry.")
    for field, q in FIELDS:
        c.print(Text(f"  [{field}]", style="grey50"))
        s.type(q)

    s.lesson("Lesson 4 · harder maths",
             "Calculus, algebra, matrices, differential equations, proofs and series go to the exact reasoning engine "
             "(sympy): the answer is computed, never guessed.")
    for q in MATHS:
        s.type(q)



def exam(s: Session, c: Console, args) -> int:
    s.lesson("Final exam · questions it hasn't seen in this session",
             "New phrasings of everything above. A pass means it understood what was asked and, for maths, solved it.")
    passed = 0
    for q, want in EXAM:
        got, p = s.read(q)
        ok = got == want or (want == "knowledge" and got in ("knowledge", "lookup"))
        passed += ok
        mark = "[green]✓[/]" if ok else "[red]✗[/]"
        c.print(f"  {mark} {q:<62} [grey50]{got} p={p:.2f}  (wanted {want})[/]")
        s.pause(0.5)
    c.print()
    c.print(Text.assemble(("Score  ", "bold"), (f"{passed}/{len(EXAM)}", "bold green" if passed == len(EXAM) else "bold yellow")))
    s.type("/test")
    if not args.dry:
        c.print(Text("Kepler kept these lessons. Keep teaching it: `kepler teach` (offline) or `kepler` → chat.", style="grey62"))
    return 0 if passed == len(EXAM) else 1


if __name__ == "__main__":
    sys.exit(main())
