"""`kepler teach`: a plain terminal chat box for testing and training the Kepler bot.

You type, Kepler shows the typed decision it made (intent, probability, slots, runners-up). If it got it right,
`/y` saves the sentence as a training example; if not, `/n <intent>` (or `/n 2` for the runner-up) corrects it.
`/new <name> <reply>` invents a brand-new intent. The bot retrains after every lesson (under a second) and the
lessons are used everywhere: `kepler chat`, `kepler ask` and the full-screen app.

Runs offline by default (no server, nothing leaves this machine). `--live` also runs real answers against a
running Kepler server.
"""
import random
from contextlib import nullcontext

from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.text import Text

from ..cli import render as R
from . import knowledge, language, latex, model, reasoning, store
from .mind import Mind
from .intents import INTENTS
from .slots import Context, extract

HELP = """[bold]Talk normally[/] and Kepler shows what it understood:  ◆ intent  p=probability  slots   then the runners-up.
[bold]Write how you like[/]: slang, typos and number words are fine (wats 2 plus 2 · shw me api erors · fifteen percent of 200).
[bold]Ask what words mean[/]: what is a median · what does anomaly mean · who are you · tell me a joke
[bold]Follow up[/] on a maths answer: and for 20? · what about cubes? · double it · is it prime? · in binary · why?
[bold]Ask maths[/] and the reasoning engine works it out step by step and checks it:
  12 * (3 + 4)^2 · 15% of 200 · average of 4, 8, 15 · is 97 prime · solve 2x + 3 = 7 · x^2 - 5x + 6 = 0
  solve x + y = 10, x - y = 2 · derivative of x^2 sin x · integrate x^2 from 0 to 3 · factor x^2 - 1
  sum of first n natural numbers · next number in 2, 6, 12, 20 · 10 choose 3 · 5 km to miles
  5 more than twice a number is 17 · if a + b = 10 and a - b = 4, what is ab · 30 heads and 74 legs, chickens and cows

[bold]Teach[/]
  /y                     that was right: save the last message as an example
  /n INTENT  or  /n 2    that was wrong: it meant INTENT (or runner-up number 2 / 3)
  /new NAME REPLY…       create your own intent from the last message; Kepler answers it with REPLY
  /reply NAME REPLY…     change what your own intent answers
  /drop NAME             delete one of your own intents and its examples
  /alias WORD = MEANING  teach a word or shorthand (/alias sigs = signups); /alias lists them
[bold]Write-ups[/] (LaTeX → PDF in ~/Documents/Kepler)
  /pdf                   the last answer as a formal PDF      /pdf all   every answer this session
  /pdf QUESTION          write up a new question              /tex       LaTeX source only
  /open                  open the last document  ·  or just say: write a formal proof that 1 + 2 + ... + n = n(n+1)/2 as a pdf
[bold]Inspect[/]
  /intents               every intent (built-in and yours) with your example counts
  /examples [INTENT]     what you've taught, numbered
  /test                  accuracy on held-out phrasings and on your examples
[bold]Undo[/]
  /undo                  forget the last example you taught      /forget N   forget example N
  /reset                 forget everything you taught (asks first)
[bold]Other[/]
  /help   /quit"""


def offline_context() -> Context:
    from ..integrations import REGISTRY
    from ..simulator import METRICS, SCENARIOS
    slices = {m: [f"{k}={v}" for k, vals in spec["dims"].items() for v in vals] for m, spec in METRICS.items()}
    tools = {}
    for t, integ in REGISTRY.items():
        tools[integ.public()["label"].lower()] = t
        tools[t.replace("_", " ")] = t
    tools.update({"aws": "cloudwatch", "otel": "otlp", "open telemetry": "otlp", "slack": "slack",
                  "newrelic": "newrelic", "pg": "postgres", "postgresql": "postgres"})
    return Context(list(METRICS), slices, tools, list(SCENARIOS))


class Trainer:
    def __init__(self, console: Console, bot=None, spinners: bool = True):
        self.out = console
        self.bot = bot                    # a live brain.Bot, or None for offline
        self.ctx = None if bot else offline_context()
        self.mind = Mind()
        self.spinners = spinners
        self.last: dict | None = None     # {"text", "delex", "ranked", "kind", "read_as", "note"}
        self.history: list[str] = []      # questions answered by maths / knowledge / library, for /pdf all
        self.last_doc = None

    def busy(self, msg: str):
        return self.out.status(msg, spinner="dots") if self.spinners else nullcontext()

    # ---------------------------------------------------------------- one message

    def context(self) -> Context:
        return self.bot.context() if self.bot else self.ctx

    def _classify(self, text: str) -> tuple[str, float]:
        _, delex = extract(text, self.context())
        return model.classify(delex, 1)[0]

    def _protect(self) -> set:
        words = set()
        for m in self.context().metrics:
            words.update(m.lower().replace("_", " ").split())
        return words

    def _header(self, intent: str, p: float, extra: str = "", read_as: str = "", note: str = "", text: str = "") -> None:
        line = Text("◆ ", style=R.ACCENT)
        line.append(intent, style=f"bold {R.ACCENT}")
        line.append(f"  p={p:.2f}", style="bold")
        if extra:
            line.append("  " + extra, style="grey62")
        self.out.print(line)
        if note:
            self.out.print(Text(f"  ↳ {note}", style="grey50"))
        elif read_as and language.changed(text, read_as):
            self.out.print(Text(f"  ↳ read as: {read_as}", style="grey50"))

    def _document(self, questions: list[str], pdf: bool = True, title: str = "") -> None:
        with self.busy("typesetting…"):
            w, items = latex.write_answers(questions, self.mind, self._protect(), self._classify, pdf=pdf, title=title)
        self.last_doc = w
        self.history += [q for q in questions if q not in self.history]
        kinds = ", ".join(sorted({i.kind for i in items}))
        head = "PDF ready" if w.pdf else "LaTeX written"
        self.out.print(Text.assemble((f"◆ document  p=1.00  ", f"bold {R.ACCENT}"), (f"{len(items)} section(s) · {kinds}", "grey62")))
        self.out.print(Text.assemble((f"  {head}: ", "bold green" if w.pdf else "bold"), str(w.pdf or w.tex)))
        if w.pdf:
            self.out.print(Text(f"  source: {w.tex}", style="grey50"))
        if w.note:
            self.out.print(Text(f"  note: {w.note}", style="yellow"))
        self.out.print(Text("  /open shows it", style="grey42"))

    def cmd_pdf(self, arg: str) -> None:
        """/pdf (last answer) · /pdf all (this session) · /pdf QUESTION"""
        arg = arg.strip()
        if arg == "all":
            if not self.history:
                self.out.print("[yellow]nothing to write up yet: ask a maths question first[/]")
                return
            self._document(list(self.history), title="Kepler session: solutions and proofs")
        elif arg:
            self._document([arg])
        elif self.history:
            self._document([self.history[-1]])
        else:
            self.out.print("[yellow]ask something first, or /pdf QUESTION[/]")

    def cmd_tex(self, arg: str) -> None:
        q = [arg.strip()] if arg.strip() else self.history[-1:]
        if not q:
            self.out.print("[yellow]ask something first, or /tex QUESTION[/]")
            return
        self._document(q, pdf=False)

    def cmd_open(self, arg: str) -> None:
        if not self.last_doc:
            self.out.print("[yellow]no document yet: /pdf makes one[/]")
            return
        latex.open_file(self.last_doc.pdf or self.last_doc.tex)
        self.out.print(f"  opened {self.last_doc.pdf or self.last_doc.tex}")

    def say(self, text: str) -> None:
        req = latex.request(text)
        if req:
            question, pdf = req
            self._document([question], pdf=pdf)
            return None
        parts = self.mind.parts(text)
        if len(parts) == 1:
            return self._say_one(text)
        self.out.print(Text(f"{len(parts)} questions, answering each with the stream that knows it:", style="grey62"))
        for i, p in enumerate(parts, 1):
            self.out.print(Text.assemble((f"{i}/{len(parts)} ", f"bold {R.ACCENT}"), (p, "bold")))
            self._say_one(p)
        return None

    def _say_one(self, text: str) -> None:
        th = self.mind.think(text, self._protect(), self._classify)
        if th.kind in ("math", "knowledge", "lookup", "steps") and (th.kind != "math" or th.solution.ok):
            self.history.append(text)
        if th.kind in ("math", "steps"):
            sol = th.solution
            self.last = {"text": text, "delex": th.read_as, "ranked": [("math", sol.confidence)], "kind": "math",
                         "read_as": th.read_as, "note": th.note, "answer": sol.answer}
            self._header("math", sol.confidence, f"kind={sol.kind}", th.read_as, th.note, text)
            self.out.print(reasoning.render(sol))
            return
        if th.kind == "lookup":
            from ..library import answer as library_answer
            a = th.lookup
            self.last = {"text": text, "delex": th.read_as, "ranked": [("lookup", a["confidence"])], "kind": "lookup",
                         "read_as": th.read_as, "note": "", "answer": a["text"], "source": a["title"]}
            extra = f"decision={a['decision']}" + (f" source={a['title']}" if a["title"] else "")
            self._header("lookup", a["confidence"], extra, th.read_as, "", text)
            self.out.print(library_answer.render(a))
            return
        if th.kind == "knowledge":
            k = th.knowledge
            self.last = {"text": text, "delex": th.read_as, "ranked": [("knowledge", 0.97)], "kind": "knowledge",
                         "read_as": th.read_as, "note": "", "answer": k["text"]}
            self._header("knowledge", 0.97, f"topic={k['topic']}", th.read_as, "", text)
            self.out.print(knowledge.render(k))
            return
        slots, delex = extract(th.read_as, self.context())
        ranked = [(th.taught, 1.0)] + [r for r in model.classify(delex, k=3) if r[0] != th.taught][:2] if th.taught \
            else model.classify(delex, k=3)
        intent, p = ranked[0]
        self.last = {"text": text, "delex": delex, "ranked": ranked, "kind": "intent", "read_as": th.read_as,
                     "note": "you taught me this one" if th.taught else "", "answer": ""}
        if intent != "demo_inject":
            slots.pop("scenario", None)
        shown = {k: v for k, v in slots.items() if k != "metric_guess"}
        self._header(intent, p, " ".join(f"{k}={v}" for k, v in shown.items()), th.read_as, self.last["note"], text)
        alts = Text("   ", style="grey50")
        for n, (i, q) in enumerate(ranked[1:], start=2):
            alts.append(f"{n} {i} {q:.2f}   ")
        self.out.print(alts)
        if self.bot:
            self.out.print(self.bot.handle(th.read_as).renderable(show_decision=False))
        elif p < 0.22 and not th.taught:
            self.out.print(Text.assemble(("  I'm not sure what you mean. ", "yellow"),
                                         ("If it's one of the guesses above, say /n 1, /n 2 or /n 3; or teach me a new intent with /new NAME REPLY.", "grey62")))
            return
        else:
            self.last["answer"] = self._offline_answer(intent)
            self.out.print(Text("  " + self.last["answer"], style="white"))
        if p < 0.6:
            self.out.print("  [grey50]not sure: [bold]/y[/] if right, [bold]/n INTENT[/] or [bold]/n 2[/] to correct[/]")

    def _offline_answer(self, intent: str) -> str:
        mine = store.load()["intents"]
        if intent in mine:
            return mine[intent]["reply"] or "(no reply set; use /reply)"
        return f"→ would: {model.describe(intent)}   [offline; --live gives the real answer]"

    # ---------------------------------------------------------------- teaching

    def _known(self) -> set[str]:
        return set(INTENTS) | set(store.load()["intents"])

    def _teach(self, intent: str) -> None:
        if not self.last:
            self.out.print("[yellow]say something first, then teach me what it meant[/]")
            return
        if intent in ("knowledge", "lookup") or (intent == self.last["ranked"][0][0] and intent in ("knowledge", "lookup")):
            self.out.print("  [green]✓[/] that answer comes from my knowledge / library, so there's nothing to learn here "
                           "(add sources with `kepler learn`)")
            return
        if intent == "math":
            if self.last["ranked"][0][0] == "math":
                self.out.print("  [green]✓[/] maths is worked out by the reasoning engine (rules + exact algebra), "
                               "so there's nothing to learn here")
            else:
                self.out.print("  [yellow]the reasoning engine couldn't read that as maths; try '12 * (3 + 4)', "
                               "'15% of 200', 'solve 2x + 3 = 7'[/]")
            return
        store.add_example(self.last["text"], self.last["delex"], intent)
        if self.bot:
            self.bot.memory["pending"] = None  # the lesson answers any "did you mean 1 or 2?" question
        with self.busy("retraining…"):
            ranked = model.classify(self.last["delex"], k=1)
        i, p = ranked[0]
        mark = "[green]✓[/]" if i == intent else "[yellow]~[/]"
        self.out.print(f"  {mark} learned [bold]{escape(self.last['text'])}[/] → [bold]{intent}[/]   "
                       f"[grey50](now: {i} p={p:.2f})[/]")

    def cmd_y(self, arg: str) -> None:
        if self.last:
            self._teach(self.last["ranked"][0][0])
        else:
            self._teach("")

    def cmd_n(self, arg: str) -> None:
        arg = arg.strip()
        if not arg:
            self.out.print("usage: /n INTENT   or   /n 2   (see /intents)")
            return
        if arg.isdigit() and self.last:
            n = int(arg)
            if not 1 <= n <= len(self.last["ranked"]):
                self.out.print(f"[yellow]pick 1–{len(self.last['ranked'])}[/]")
                return
            arg = self.last["ranked"][n - 1][0]
        if arg not in self._known() and arg != "math":
            close = [i for i in sorted(self._known()) if arg in i]
            hint = f" did you mean: {', '.join(close[:4])}?" if close else " (see /intents, or /new to create it)"
            self.out.print(f"[yellow]no intent called '{escape(arg)}'.{hint}[/]")
            return
        self._teach(arg)

    def cmd_new(self, arg: str) -> None:
        name, _, reply = arg.strip().partition(" ")
        name = name.lower()
        if not store.NAME.match(name):
            self.out.print("usage: /new NAME REPLY…   (NAME: lowercase letters, digits, _; 2–40 chars)")
            return
        if name in INTENTS:
            self.out.print(f"[yellow]'{name}' is built in; use /n {name} to teach it[/]")
            return
        if not self.last:
            self.out.print("[yellow]say an example message first, then /new NAME REPLY[/]")
            return
        store.add_intent(name, reply.strip())
        self.out.print(f"  [green]+[/] new intent [bold]{name}[/]" + (f" → \"{escape(reply.strip())}\"" if reply.strip() else ""))
        self._teach(name)

    def cmd_reply(self, arg: str) -> None:
        name, _, reply = arg.strip().partition(" ")
        mine = store.load()["intents"]
        if name not in mine:
            self.out.print(f"[yellow]'{escape(name)}' isn't one of your intents[/]")
            return
        store.add_intent(name, reply.strip(), mine[name]["desc"])
        self.out.print(f"  [green]✓[/] {name} now answers: {escape(reply.strip())}")

    def cmd_drop(self, arg: str) -> None:
        name = arg.strip()
        if name not in store.load()["intents"]:
            self.out.print(f"[yellow]'{escape(name)}' isn't one of your intents (built-in ones can't be dropped)[/]")
            return
        store.remove_intent(name)
        self.out.print(f"  [green]✓[/] dropped {name}")

    # ---------------------------------------------------------------- inspecting

    def cmd_intents(self, arg: str) -> None:
        data = store.load()
        counts: dict[str, int] = {}
        for e in data["examples"]:
            counts[e["intent"]] = counts.get(e["intent"], 0) + 1
        t = Table(box=None, pad_edge=False, header_style="bold")
        t.add_column("intent")
        t.add_column("what it does")
        t.add_column("yours", justify="right")
        for name, spec in INTENTS.items():
            t.add_row(name, spec["desc"], str(counts.get(name, "")))
        for name, spec in data["intents"].items():
            t.add_row(f"[{R.ACCENT}]{name}[/]", f"answers: {escape(spec['reply'][:50])}", str(counts.get(name, 0)))
        self.out.print(t)

    def cmd_examples(self, arg: str) -> None:
        exs = store.load()["examples"]
        rows = [(n, e) for n, e in enumerate(exs, 1) if not arg.strip() or e["intent"] == arg.strip()]
        if not rows:
            self.out.print("[grey50]nothing taught yet[/]")
            return
        for n, e in rows:
            self.out.print(f"  [grey50]{n:>3}[/]  {escape(e['text'])}  [grey50]→[/] [bold]{e['intent']}[/]")

    def cmd_test(self, arg: str) -> None:
        with self.busy("testing…"):
            pipe = model.load()
            X, y = model.dataset(seed=7, per_template=2)  # fresh random phrasings of the built-in templates
            rng = random.Random(7)
            idx = rng.sample(range(len(X)), min(400, len(X)))
            held = sum(pipe.predict([X[i]])[0] == y[i] for i in idx) / len(idx)
            exs = store.load()["examples"]
            mine = (sum(model.classify(e["delex"], 1)[0][0] == e["intent"] for e in exs) / len(exs)) if exs else None
        self.out.print(f"  built-in phrasings: [bold]{held:.0%}[/] of {len(idx)}")
        if mine is not None:
            self.out.print(f"  your examples:      [bold]{mine:.0%}[/] of {len(exs)}")

    # ---------------------------------------------------------------- undo

    def cmd_undo(self, arg: str) -> None:
        n = len(store.load()["examples"])
        self.cmd_forget(str(n)) if n else self.out.print("[grey50]nothing to undo[/]")

    def cmd_forget(self, arg: str) -> None:
        if not arg.strip().isdigit():
            self.out.print("usage: /forget N   (numbers from /examples)")
            return
        gone = store.remove_example(int(arg) - 1)
        if gone:
            self.out.print(f"  [green]✓[/] forgot {escape(gone['text'])} → {gone['intent']}")
        else:
            self.out.print("[yellow]no example with that number[/]")

    def cmd_alias(self, arg: str) -> None:
        """/alias WORD = MEANING  ·  /alias (list)  ·  /alias WORD = (remove)"""
        if not arg.strip():
            aliases = store.load()["aliases"]
            if not aliases:
                self.out.print("[grey50]no aliases yet: /alias brb = be right back[/]")
            for w, m in aliases.items():
                self.out.print(f"  {escape(w)} [grey50]→[/] {escape(m)}")
            return
        word, eq, means = arg.partition("=")
        word, means = word.strip().lower(), means.strip().lower()
        if not eq or not word:
            self.out.print("usage: /alias WORD = MEANING   (e.g. /alias sigs = signups)")
            return
        if not means:
            gone = store.remove_alias(word)
            self.out.print(f"  [green]✓[/] removed {escape(word)}" if gone else f"[yellow]no alias '{escape(word)}'[/]")
            return
        store.add_alias(word, means)
        self.out.print(f"  [green]✓[/] '{escape(word)}' now means '{escape(means)}' everywhere")

    def cmd_reset(self, arg: str) -> None:
        if arg.strip().lower() == "yes":
            store.reset()
            self.out.print("  [green]✓[/] back to the built-in training")
            return
        if not self.spinners:
            self.out.print("  type [bold]/reset yes[/] to forget everything you taught")
            return
        sure = self.out.input("  forget [bold]everything[/] you taught? type yes: ").strip().lower()
        if sure == "yes":
            store.reset()
            self.out.print("  [green]✓[/] back to the built-in training")
        else:
            self.out.print("  kept")

    def cmd_help(self, arg: str) -> None:
        self.out.print(HELP)

    # ---------------------------------------------------------------- loop

    def handle(self, line: str) -> bool:
        """Process one line. Returns False to quit."""
        line = line.strip()
        if not line:
            return True
        if line.lower() in ("/quit", "/q", "/exit", "exit", "quit"):
            return False
        if line.startswith("/"):
            cmd, _, arg = line[1:].partition(" ")
            fn = getattr(self, f"cmd_{cmd.lower()}", None)
            if fn is None:
                self.out.print(f"[yellow]unknown command /{escape(cmd)}; /help lists them[/]")
            else:
                fn(arg)
            return True
        self.say(line)
        return True


def run(console: Console, bot=None) -> int:
    t = Trainer(console, bot)
    data = store.load()
    from .chat_app import mode_line
    mode = mode_line(bot is not None)
    console.print(Text.assemble(("◆ Kepler teach", f"bold {R.ACCENT}"), (f"  ·  {mode}", "grey50")))
    console.print(f"[grey50]{len(data['examples'])} example(s) and {len(data['intents'])} intent(s) of yours "
                  f"in {store.path()}  ·  /help for commands[/]\n")
    with console.status("loading the bot…", spinner="dots"):
        model.load()
    while True:
        try:
            line = console.input(f"[bold {R.ACCENT}]you ›[/] ")
        except (EOFError, KeyboardInterrupt):
            console.print("")
            return 0
        if not t.handle(line):
            return 0
        console.print("")
