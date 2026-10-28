"""Kepler AI: the chat panel (`ChatPanel`) shared by the main `kepler` UI ("Kepler AI" tab) and `kepler bot`.

Left: the conversation. Right: what Kepler understood (intent, confidence, runners-up, how it read your English),
what it remembers, and what you've taught it. Every `kepler teach` command works here (/y, /n, /new, /alias, …).
Offline by default; --live also answers from a running Kepler server.
"""
from contextlib import nullcontext

from rich.console import Group
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Input, Label, ListItem, ListView, RichLog, Static

from ..cli import render as R
from . import store
from .teach import Trainer

TRIES = ["prove that 1 + 2 + ... + n = n(n+1)/2", "prove x + 1/x >= 2 for positive x",
         "verify the riemann hypothesis up to height 100", "what are the millennium prize problems",
         "is api_errors ok and what is an anomaly?", "population of india divided by 2",
         "which is taller, mount everest or k2", "how old would albert einstein be today",
         "who was albert einstein", "tell me more", "how does photosynthesis work", "define serendipity",
         "sum of first n natural numbers", "wats 15 percent of two hundred", "and for 300?", "what is a median",
         "5 more than twice a number is 17", "next number in 2, 6, 12, 20", "solve x^2 - 5x + 6 = 0",
         "a car travels 120 km in 2 hours, what is its speed?", "is api_errors ok", "status", "tell me a joke", "/help"]

PANEL_CSS = f"""
ChatPanel {{ height: 1fr; layout: vertical; }}
ChatPanel #ai-body {{ height: 1fr; }}
ChatPanel #ai-log {{ width: 1fr; padding: 0 1; border: none; scrollbar-size-vertical: 1; }}
ChatPanel #ai-side {{ width: 40; min-width: 32; border-left: tall {R.ACCENT} 60%; padding: 0 1; }}
ChatPanel #ai-side.hidden {{ display: none; }}
ChatPanel .side-title {{ color: {R.ACCENT}; text-style: bold; margin-top: 1; }}
ChatPanel #ai-tries {{ height: auto; max-height: 14; background: transparent; }}
ChatPanel #ai-tries > ListItem {{ padding: 0 1; background: transparent; }}
ChatPanel #ai-tries > ListItem.--highlight {{ background: {R.ACCENT} 30%; }}
ChatPanel #ai-input {{ border: tall {R.ACCENT}; margin: 0 0; }}
"""
APP_CSS = f"""
Screen {{ layout: vertical; }}
#ai-title {{ height: 1; padding: 0 1; background: {R.ACCENT} 20%; color: {R.ACCENT}; text-style: bold; }}
"""
PLACEHOLDER = "ask anything · maths · proofs · what is a median · /pdf · /help"


class Collector:
    """Stands in for a rich Console: keeps what the trainer prints as renderables, so the chat log lays them out
    at its own width (no double wrapping)."""

    def __init__(self):
        self.items: list = []

    def print(self, *objs, **_):
        for o in objs:
            self.items.append(Text.from_markup(o) if isinstance(o, str) else o)

    def status(self, *_a, **_k):
        return nullcontext()

    def input(self, *_a, **_k):
        return ""


def _bar(p: float, width: int = 14) -> str:
    n = max(0, min(width, round(p * width)))
    return "█" * n + "░" * (width - n)


class HistoryInput(Input):
    """Input with ↑/↓ history."""

    BINDINGS = [Binding("up", "older", show=False), Binding("down", "newer", show=False)]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.history: list[str] = []
        self.pos = 0

    def remember(self, line: str) -> None:
        if line and (not self.history or self.history[-1] != line):
            self.history.append(line)
        self.pos = len(self.history)

    def action_older(self) -> None:
        if self.history and self.pos > 0:
            self.pos -= 1
            self.value = self.history[self.pos]
            self.cursor_position = len(self.value)

    def action_newer(self) -> None:
        if self.pos < len(self.history) - 1:
            self.pos += 1
            self.value = self.history[self.pos]
        else:
            self.pos = len(self.history)
            self.value = ""
        self.cursor_position = len(self.value)


class ChatPanel(Vertical):
    """The Kepler AI chat: conversation, insight panel (understood / memory / library / training), clickable
    examples, and every teach command. Used on its own by `kepler bot` and as the "Kepler AI" tab of the main UI."""

    DEFAULT_CSS = PANEL_CSS
    BINDINGS = [
        Binding("ctrl+y", "say('/y')", "That's right"),
        Binding("f1", "say('/help')", "Bot help"),
        Binding("ctrl+t", "say('/test')", "Test bot"),
        Binding("ctrl+b", "toggle_side", "Panel"),
        Binding("ctrl+l", "clear", "Clear"),
        Binding("escape", "focus_input", show=False),
    ]

    def __init__(self, bot=None, on_reply=None, **kw):
        super().__init__(**kw)
        self.bot = bot                    # a live brain.Bot (main UI / --live), or None for offline
        self.on_reply = on_reply          # optional callback(trainer.last) for the host app
        self.trainer: Trainer | None = None
        self.busy = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="ai-body"):
            yield RichLog(id="ai-log", wrap=True, markup=False, highlight=False, min_width=30)
            with Vertical(id="ai-side"):
                yield Label("Understood", classes="side-title")
                yield Static(Text("say something…", style="grey50"), id="ai-decision")
                yield Label("Memory", classes="side-title")
                yield Static(Text("nothing yet", style="grey50"), id="ai-memory")
                yield Label("Library", classes="side-title")
                yield Static("", id="ai-library")
                yield Label("Your training", classes="side-title")
                yield Static("", id="ai-training")
                yield Label("Try (click or ↵)", classes="side-title")
                yield ListView(*[ListItem(Label(Text(t)), name=t) for t in TRIES], id="ai-tries")
        yield HistoryInput(placeholder=PLACEHOLDER, id="ai-input")

    def on_mount(self) -> None:
        self.trainer = Trainer(Collector(), self.bot, spinners=False)
        log = self.query_one("#ai-log", RichLog)
        log.write(Text.assemble(("Hi, I'm Kepler. ", f"bold {R.ACCENT}"),
                                "Ask about your metrics, maths and proofs of any kind, or anything you'd look up. "
                                "Write however you like: slang, typos and number words are fine."))
        log.write(Text.assemble(("Write-ups: ", "bold"), ("/pdf", "bold"), " (last answer) · ", ("/pdf all", "bold"), " · ",
                                ("/open", "bold"), "   ", ("Teach me: ", "bold"), ("/y", "bold"), " right · ",
                                ("/n INTENT", "bold"), " fix · ", ("/new NAME REPLY", "bold"), " · ",
                                ("/alias word = meaning", "bold"), style="grey62"))
        log.write(Text(""))
        self._refresh_training()

    def focus_input(self) -> None:
        self.query_one("#ai-input", HistoryInput).focus()

    # ---------------------------------------------------------------- input

    @on(Input.Submitted, "#ai-input")
    def submitted(self, event: Input.Submitted) -> None:
        event.stop()
        line = event.value.strip()
        inp = self.query_one("#ai-input", HistoryInput)
        inp.remember(line)
        inp.value = ""
        self.send(line)

    @on(ListView.Selected, "#ai-tries")
    def picked(self, event: ListView.Selected) -> None:
        event.stop()
        text = event.item.name or str(event.item.query_one(Label).render())  # the raw text, never markup
        self.send(text)
        self.focus_input()

    def action_say(self, line: str) -> None:
        self.send(line)

    def action_clear(self) -> None:
        self.query_one("#ai-log", RichLog).clear()

    def action_toggle_side(self) -> None:
        self.query_one("#ai-side").toggle_class("hidden")

    def action_focus_input(self) -> None:
        self.focus_input()

    def send(self, line: str) -> None:
        if not line or self.busy:
            return
        if line.lower() in ("/quit", "/q", "/exit", "exit", "quit"):
            self.app.exit()
            return
        if line.lower() == "/clear":
            self.action_clear()
            return
        log = self.query_one("#ai-log", RichLog)
        log.write(Text.assemble(("you › ", f"bold {R.ACCENT}"), (line, "bold")))
        self.busy = True
        self.query_one("#ai-input", HistoryInput).placeholder = "thinking…"
        self.think(line)

    @work(thread=True, exclusive=True, group="kepler-ai")
    def think(self, line: str) -> None:
        t = self.trainer
        t.out = Collector()
        try:
            t.handle(line)
            out = list(t.out.items)
        except Exception as e:  # noqa: BLE001 - the chat must survive anything
            out = [Text(f"✗ something went wrong: {type(e).__name__}: {e}", style="red")]
        self.app.call_from_thread(self._show, out)

    def _show(self, out: list) -> None:
        log = self.query_one("#ai-log", RichLog)
        for item in out:
            log.write(item)
        log.write(Text(""))
        self.busy = False
        self.query_one("#ai-input", HistoryInput).placeholder = PLACEHOLDER
        self._refresh_side()
        if self.on_reply and self.trainer and self.trainer.last:
            self.on_reply(self.trainer.last)

    # ---------------------------------------------------------------- side panel

    def _refresh_side(self) -> None:
        last = self.trainer.last if self.trainer else None
        if last:
            parts = []
            for n, (intent, p) in enumerate(last["ranked"][:3], start=1):
                style = f"bold {R.ACCENT}" if n == 1 else "grey62"
                parts.append(Text.assemble((f"{intent[:16]:<16} ", style), (_bar(p), style), f" {p:.2f}"))
            if last.get("source"):
                parts.append(Text.assemble(("source ", "grey50"), (last["source"], R.ACCENT)))
            if last.get("note"):
                parts.append(Text(f"↳ {last['note']}", style="grey50"))
            elif last.get("read_as") and last["read_as"] != last["text"].lower().strip():
                parts.append(Text(f"↳ read as: {last['read_as']}", style="grey50"))
            self.query_one("#ai-decision", Static).update(Group(*parts))
        mem = self.trainer.mind.mem if self.trainer else None
        lines = []
        if mem and mem.question:
            lines.append(Text.assemble(("last maths  ", "grey50"), mem.question[:60]))
            lines.append(Text.assemble(("answer      ", "grey50"), (mem.answer[:60], "green")))
            lines.append(Text("follow up: 'and for 20?', 'double it', 'why?'", style="grey42"))
        if self.bot:
            if self.bot.memory.get("metric"):
                lines.append(Text.assemble(("metric      ", "grey50"), self.bot.memory["metric"]))
            if self.bot.memory.get("incident"):
                lines.append(Text.assemble(("incident    ", "grey50"), f"#{self.bot.memory['incident']}"))
        self.query_one("#ai-memory", Static).update(Group(*lines) if lines else Text("nothing yet", style="grey50"))
        self._refresh_training()

    def _refresh_library(self) -> None:
        try:
            from ..library import index, web
            st = index.stats()
        except Exception:  # noqa: BLE001
            return
        docs = st["docs"]
        lines = [Text.assemble((f"{docs.get('wikipedia', 0):,}", "bold"), " Wikipedia articles"),
                 Text.assemble((f"{st['words']:,}", "bold"), " dictionary senses"),
                 Text.assemble((f"{docs.get('files', 0):,}", "bold"), " of your files · ",
                               (f"{docs.get('web-wikipedia', 0):,}", "bold"), " looked up"),
                 Text(f"online lookup: {'on' if web.enabled() else 'off'}"
                      + (f" (paused {web.paused_for()}s)" if web.paused_for() else ""), style="grey50")]
        self.query_one("#ai-library", Static).update(Group(*lines))

    def _refresh_training(self) -> None:
        self._refresh_library()
        data = store.load()
        self.query_one("#ai-training", Static).update(Text.assemble(
            (str(len(data["examples"])), "bold"), " examples · ", (str(len(data["intents"])), "bold"), " intents · ",
            (str(len(data["aliases"])), "bold"), " aliases", ("\nCtrl+Y confirms the last answer", "grey42")))


class ChatApp(App):
    """`kepler bot`: the Kepler AI panel on its own (also the "Kepler AI" tab of the main `kepler` UI)."""

    CSS = APP_CSS
    TITLE = "Kepler AI"
    BINDINGS = [Binding("ctrl+q", "quit", "Quit")]

    def __init__(self, bot=None, note: str = ""):
        super().__init__()
        self.bot = bot
        self.note = note

    def compose(self) -> ComposeResult:
        yield Static(f"◆ Kepler AI  ·  {mode_line(self.bot is not None)}" + (f"  ·  {self.note}" if self.note else ""), id="ai-title")
        yield ChatPanel(self.bot, id="ai-panel")
        yield Footer()

    def on_mount(self) -> None:
        self.panel.focus_input()

    @property
    def panel(self) -> "ChatPanel":
        return self.query_one(ChatPanel)

    @property
    def busy(self) -> bool:
        return self.panel.busy

    @property
    def trainer(self):
        return self.panel.trainer


def mode_line(live: bool) -> str:
    try:
        from ..library import web
        online = web.enabled()
    except Exception:  # noqa: BLE001
        online = False
    base = "live: Kepler server answers" if live else "offline"
    return f"{base} · Wikipedia lookup on (only search words are sent)" if online else f"{base} · nothing leaves this machine"


def run(bot=None, note: str = "") -> int:
    ChatApp(bot, note).run()
    return 0
