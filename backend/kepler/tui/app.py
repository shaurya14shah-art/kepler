"""Kepler full-screen terminal app: opening screen, every dashboard tab, and a chat panel with the Kepler bot."""
import json
import time
from functools import partial

from rich.console import Group
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import DiscoveryHit, Hit, Hits, Provider
from textual.containers import Center, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (Button, DataTable, Footer, Input, Label, ListItem, ListView, RichLog, Select, Static,
                             Switch, TabbedContent, TabPane, TextArea)
from textual_plotext import PlotextPlot

from .. import device
from ..bot.brain import Bot
from ..bot.chat_app import ChatPanel
from ..cli import render as R
from ..cli.client import Client, KeplerError

from .. import __version__ as VERSION
REFRESH_S = 10
TABS = ["overview", "metrics", "incidents", "models", "integrations", "settings", "ai"]

CSS = f"""
Screen {{ background: $background; }}
#topbar {{ height: 1; padding: 0 1; background: $panel; color: $text; }}
#body {{ height: 1fr; }}
#tabs {{ width: 1fr; }}
#chat {{ width: 46%; min-width: 44; border-left: tall {R.ACCENT}; padding: 0 1; }}
#chat.hidden {{ display: none; }}
#chat-title {{ height: 1; color: {R.ACCENT}; text-style: bold; }}
#chat-log {{ height: 1fr; background: $surface; padding: 0 1; }}
#chat-input {{ margin-top: 1; border: tall {R.ACCENT}; }}
.section {{ margin: 1 0 0 0; color: $text-muted; text-style: bold; }}
.row {{ height: auto; margin: 1 0 0 0; }}
.row Button {{ margin-right: 1; }}
.stat {{ width: 1fr; height: 5; border: round $panel-lighten-2; padding: 0 1; margin-right: 1; }}
#metric-list {{ width: 30; border-right: solid $panel-lighten-2; }}
#chart {{ height: 18; }}
#metric-main {{ padding: 0 1; }}
DataTable {{ height: auto; max-height: 24; }}
#inc-table {{ max-height: 100%; height: 1fr; }}
.field {{ height: auto; margin-bottom: 1; }}
.field Label {{ color: $text-muted; }}
.field Input, .field Select {{ width: 100%; }}
.modal {{ width: 92%; max-width: 130; height: 90%; border: thick {R.ACCENT}; background: $surface; padding: 1 2; }}
.modal-buttons {{ height: auto; dock: bottom; padding-top: 1; }}
.modal-buttons Button {{ margin-right: 1; }}
#welcome {{ align: center middle; }}
#welcome-box {{ width: auto; max-width: 110; height: auto; }}
#welcome-hint {{ margin-top: 1; color: $text-muted; text-align: center; width: 100%; }}
TextArea {{ height: 6; }}
#demo-buttons {{ layout: grid; grid-size: 3; grid-gutter: 1 1; height: auto; }}
#demo-buttons Button {{ width: 100%; }}
"""


# ---------------------------------------------------------------- opening screen

class WelcomeScreen(Screen):
    BINDINGS = [Binding("enter", "go('overview')", "Start"), Binding("c", "go('chat')", "Chat with Kepler"),
                Binding("q", "app.quit", "Quit")]

    def compose(self) -> ComposeResult:
        with Vertical(id="welcome"):
            with Center():
                yield Static(R.welcome(self.app.client.url, False, {"status": Text("connecting…", style="grey50")}),
                             id="welcome-box")
            yield Static("Enter  start   ·   c  chat with Kepler   ·   q  quit", id="welcome-hint")
        yield Footer()

    def on_mount(self):
        self.load()

    @work(thread=True)
    def load(self):
        c = self.app.client
        try:
            ov = c.get("/api/overview")
            st = c.get("/api/settings")
            mm = c.get("/api/models")
            ok = True
        except KeplerError as e:
            self.app.call_from_thread(self.query_one("#welcome-box", Static).update,
                                      R.welcome(c.url, False, {"error": Text(str(e), style="red"),
                                                               "fix": "start the server with ./run.sh, or kepler config --set-url …"}))
            return
        n_open = ov["stats"]["open"]
        custom = sum(1 for m in mm["metrics"] if m["kind"] == "custom")
        ag = device.agent_status()
        info = {
            "version": f"kepler {VERSION}",
            "watching": f"{len(ov['metrics'])} metrics · {custom} on custom-trained models",
            "incidents": Text(f"{n_open} open" if n_open else "none open · all clear", style="bold red" if n_open else "green"),
            "alert filter": f"{'learned from ' + str(mm['feedback'].get('n_labels', 0)) + ' labels' if mm['feedback'].get('active') else 'statistical prior only'}",
            "alerts to": "Slack" if st["slack_webhook_url"] else "nowhere yet (Settings tab)",
            "agent": "running in background" if ag["running"] else "not installed · kepler agent install",
            "mode": "demo data" if st["demo_mode"] else "live data",
            "tips": Text("Ctrl+P commands · / chat · 1-6 tabs · ? help", style="grey62"),
        }
        self.app.call_from_thread(self.query_one("#welcome-box", Static).update, R.welcome(c.url, ok, info))

    def action_go(self, where: str):
        self.app.switch_to_main(ai=where == "chat")


# ---------------------------------------------------------------- modals

class Modal(ModalScreen):
    """A modal that closes once. Textual's dismiss() pops whatever screen is on top, so a second Esc (or Esc plus a
    click) while the modal was closing used to pop the main screen as well and leave the app blank."""

    def dismiss(self, result=None):
        if self.app.screen is not self:
            return None  # already closing
        return super().dismiss(result)


class IncidentScreen(Modal):
    BINDINGS = [Binding("escape", "dismiss", "Close"), Binding("r", "label(1)", "👍 Real"), Binding("f", "label(0)", "👎 False"),
                Binding("c", "copy", "Copy JSON"), Binding("o", "open", "Open in browser")]

    def __init__(self, incident_id: int):
        super().__init__()
        self.iid = incident_id
        self.data = None

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal"):
            with VerticalScroll():
                yield Static("loading…", id="inc-detail")
            with Horizontal(classes="modal-buttons"):
                yield Button("👍 Real (r)", id="real", variant="success")
                yield Button("👎 False alarm (f)", id="false", variant="error")
                yield Button("Copy JSON (c)", id="copy")
                yield Button("Open in browser (o)", id="open")
                yield Button("Close (esc)", id="close")

    def on_mount(self):
        self.load()

    @work(thread=True)
    def load(self):
        try:
            self.data = self.app.client.get(f"/api/incidents/{self.iid}")
        except KeplerError as e:
            self.app.call_from_thread(self.query_one("#inc-detail", Static).update, Text(str(e), style="red"))
            return
        d, pts = self.data["decision"], self.data["points"]
        body = Group(R.incident_panel(d, pts, 100), R.metric_chart(pts, 100, 14, f"{d['metric']}{' · ' + d['slice'] if d.get('slice') else ''}"))
        self.app.call_from_thread(self.query_one("#inc-detail", Static).update, body)

    @on(Button.Pressed)
    def pressed(self, ev: Button.Pressed):
        {"real": partial(self.action_label, 1), "false": partial(self.action_label, 0), "copy": self.action_copy,
         "open": self.action_open, "close": self.dismiss}[ev.button.id]()

    def action_label(self, value: int):
        try:
            r = self.app.client.post(f"/api/incidents/{self.iid}/feedback", {"label": value})
            self.app.notify(f"#{self.iid} labelled {'real 👍' if value else 'false alarm 👎'} · {r['labels']} labels", title="Kepler")
            self.load()
            self.app.refresh_data()
        except KeplerError as e:
            self.app.notify(str(e), severity="error")

    def action_copy(self):
        if self.data:
            ok = device.copy(json.dumps(self.data["decision"], indent=2))
            self.app.notify("decision JSON copied" if ok else "no clipboard available")

    def action_open(self):
        device.open_url(self.app.client.dashboard_url(f"incident/{self.iid}"))


class ConnectScreen(Modal):
    BINDINGS = [Binding("escape", "dismiss", "Close")]

    def __init__(self, integ: dict):
        super().__init__()
        self.integ = integ

    def compose(self) -> ComposeResult:
        i = self.integ
        with Vertical(classes="modal"):
            yield Static(Text.assemble((i["label"], f"bold {R.ACCENT}"), f"  {i['direction']} · {i['category']}\n", (i["summary"], "grey70")))
            with VerticalScroll():
                if i["direction"] == "push":
                    yield Static(self._push_help(), id="push-help")
                else:
                    for f in i["fields"]:
                        with Vertical(classes="field"):
                            yield Label(f"{f['label']}{'' if f['required'] else ' (optional)'}" + (f" · {f['help']}" if f["help"] else ""))
                            if f["kind"] == "select":
                                yield Select([(o, o) for o in f["options"]], value=f["default"] or f["options"][0], allow_blank=False,
                                             id=f"f-{f['name']}")
                            elif f["kind"] == "textarea":
                                yield TextArea(f["default"], id=f"f-{f['name']}")
                            else:
                                yield Input(f["default"], password=f["kind"] == "password", id=f"f-{f['name']}")
                    if i["direction"] == "pull":
                        with Vertical(classes="field"):
                            yield Label("Aggregation")
                            yield Select([("sum (counts)", "sum"), ("mean (measurements)", "mean")], value=i["default_agg"], allow_blank=False, id="x-agg")
                        with Vertical(classes="field"):
                            yield Label("Alert when it goes")
                            yield Select([("up", "up"), ("down", "down"), ("either way", "both")], value=i["default_bad"], allow_blank=False, id="x-bad")
                        with Vertical(classes="field"):
                            yield Label("Pull every (minutes)")
                            yield Input("5", id="x-every")
                    else:
                        with Vertical(classes="field"):
                            yield Label("Send incidents of severity")
                            yield Select([("medium and above", "medium"), ("high and above", "high"), ("critical only", "critical")],
                                         value="high", allow_blank=False, id="x-sev")
                yield Static("", id="connect-msg")
            with Horizontal(classes="modal-buttons"):
                if i["direction"] == "push":
                    yield Button("Copy URL", id="copy-url", variant="primary")
                else:
                    yield Button("Test", id="test")
                    yield Button("Save", id="save", variant="primary")
                yield Button("Close (esc)", id="close")

    def _push_url(self) -> str:
        c = self.app.client
        return f"{c.url}/api/v1/hooks/segment?key={c.key}&dims=plan,context.os.name" if self.integ["type"] == "segment" else f"{c.url}/v1/metrics"

    def _push_help(self):
        if self.integ["type"] == "segment":
            return Text.assemble("In Segment: Connections → Destinations → Webhooks (Actions) → POST to:\n\n", (self._push_url(), "bold"),
                                 "\n\nEach track event becomes a metric ('Signed Up' → signed_up).")
        return Text.assemble("Add to your OpenTelemetry Collector:\n\n",
                             (f"exporters:\n  otlphttp/kepler:\n    endpoint: {self.app.client.url}\n    encoding: json\n"
                              f"    headers:\n      X-Kepler-Key: {self.app.client.key}", "bold"))

    def _values(self) -> dict:
        cfg = {}
        for f in self.integ["fields"]:
            w = self.query_one(f"#f-{f['name']}")
            cfg[f["name"]] = w.text if isinstance(w, TextArea) else (w.value if not isinstance(w, Select) else str(w.value))
        return cfg

    def _body(self) -> dict:
        cfg = self._values()
        i = self.integ
        if i["direction"] == "pull":
            every = int(self.query_one("#x-every", Input).value or 5)
            return {"type": i["type"], "name": f"{i['label']}: {cfg.get('metric', '')}", "interval_s": every * 60,
                    "config": {**cfg, "agg": self.query_one("#x-agg", Select).value, "bad_direction": self.query_one("#x-bad", Select).value}}
        return {"type": i["type"], "name": i["label"], "config": cfg, "min_severity": self.query_one("#x-sev", Select).value}

    @on(Button.Pressed)
    def pressed(self, ev: Button.Pressed):
        if ev.button.id == "close":
            self.dismiss()
        elif ev.button.id == "copy-url":
            self.app.notify("copied" if device.copy(self._push_url()) else "no clipboard available")
        else:
            self.query_one("#connect-msg", Static).update(Text("working…", style="grey50"))
            self.submit(ev.button.id)

    @work(thread=True)
    def submit(self, action: str):
        c = self.app.client
        kind = "connectors" if self.integ["direction"] == "pull" else "destinations"
        try:
            body = self._body()
            r = c.post(f"/api/{kind}/test", body)
            msg = Text(("✓ " if r["ok"] else "✗ ") + r["message"], style="green" if r["ok"] else "red")
            if action == "save" and r["ok"]:
                c.post(f"/api/{kind}", body)
                msg.append("  · saved", style="bold green")
                self.app.call_from_thread(self.app.refresh_data)
            elif action == "save":
                msg.append("  · not saved (fix the test first)", style="yellow")
        except (KeplerError, ValueError) as e:
            msg = Text(f"✗ {e}", style="red")
        self.app.call_from_thread(self.query_one("#connect-msg", Static).update, msg)


class HelpScreen(Modal):
    BINDINGS = [Binding("escape", "dismiss", "Close"), Binding("question_mark", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        from ..bot.intents import INTENTS
        keys = R.table(["key", "does"], [["1-6", "switch tabs"], ["7", "Kepler AI: maths, proofs, knowledge, PDFs, training"],
                                         ["/", "focus the chat"], ["ctrl+k", "show / hide the chat"],
                                         ["ctrl+p", "command palette"], ["enter", "open the selected incident / metric / integration"],
                                         ["r", "refresh"], ["t", "retrain models"], ["d", "inject a demo incident"],
                                         ["o", "open the web dashboard"], ["n", "toggle desktop notifications"], ["q", "quit"]],
                       "Keys")
        intents = R.table(["Kepler understands", "e.g."], [[v["desc"], v["t"][0].replace("{metric}", "signups").replace("{id}", "40")
                                                          .replace("{tool}", "datadog").replace("{dur}", "6h").replace("{pct}", "70%")
                                                          .replace("{scenario}", "ios").replace("{slice}", "ios").replace("{sev}", "critical")
                                                          .replace("{n}", "5")] for v in INTENTS.values()], "Chat")
        with Vertical(classes="modal"):
            with VerticalScroll():
                yield Static(Group(keys, Text(""), intents))
            with Horizontal(classes="modal-buttons"):
                yield Button("Close (esc)", id="close")

    @on(Button.Pressed)
    def close(self):
        self.dismiss()


# ---------------------------------------------------------------- command palette

class KeplerCommands(Provider):
    def _commands(self):
        app = self.app
        cmds = [(f"Go to {t.title()}", partial(app.action_tab, t), f"Switch to the {t} tab") for t in TABS]
        cmds += [("Retrain models", app.action_train, "Fit baselines + the feedback filter on the latest data"),
                 ("Open web dashboard", app.action_open_web, "In your browser"),
                 ("Copy API key", app.action_copy_key, "To the clipboard"),
                 ("Toggle chat panel", app.action_toggle_chat, "Show or hide Kepler chat"),
                 ("Toggle desktop notifications", app.action_toggle_notify, "Native notifications for new incidents"),
                 ("Install background agent", app.action_agent_install, "Notifications at login, without the terminal open"),
                 ("Send test notification", app.action_test_notify, "Check desktop notifications work")]
        for t, law in (("orbit", "1st law: cheapest, fastest"), ("area", "2nd law: balanced"), ("time", "3rd law: deepest reasoning")):
            cmds.append((f"Model: use {t.title()} as default", partial(app.action_set_tier, t), f"Kepler's {law}"))
        for sc in app.scenarios:
            cmds.append((f"Demo: {sc['label']}", partial(app.action_inject, sc["id"]), "Inject a live incident into the demo startup"))
        return cmds

    async def discover(self) -> Hits:
        for name, cb, help_ in self._commands():
            yield DiscoveryHit(name, cb, help=help_)

    async def search(self, query: str) -> Hits:
        m = self.matcher(query)
        for name, cb, help_ in self._commands():
            score = m.match(name)
            if score > 0:
                yield Hit(score, m.highlight(name), cb, help=help_)


# ---------------------------------------------------------------- main screen

class MainScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Static("", id="topbar")
        with Horizontal(id="body"):
            with TabbedContent(id="tabs", initial="overview"):
                with TabPane("1 Overview", id="overview"):
                    with VerticalScroll():
                        with Horizontal(classes="row", id="stats"):
                            for k in ("open", "last24", "watched", "precision"):
                                yield Static("", classes="stat", id=f"stat-{k}")
                        yield Static("", id="ov-status")
                        yield Static("", id="ov-open")
                        yield Label("Demo: break something", classes="section")
                        yield Horizontal(classes="row", id="demo-buttons")
                with TabPane("2 Metrics", id="metrics"):
                    with Horizontal():
                        yield ListView(id="metric-list")
                        with VerticalScroll(id="metric-main"):
                            yield Static("", id="metric-head")
                            with Horizontal(classes="row"):
                                for h in (6, 24, 72, 168):
                                    yield Button(f"{h} h" if h < 72 else f"{h // 24} d", id=f"range-{h}", compact=True)
                                yield Select([], prompt="slice: all", id="slice-select", allow_blank=True)
                            yield PlotextPlot(id="chart")
                            yield Label("Slices right now", classes="section")
                            yield DataTable(id="slice-table", cursor_type="row")
                            yield Label("Incidents in range (enter to open)", classes="section")
                            yield DataTable(id="metric-incidents", cursor_type="row")
                with TabPane("3 Incidents", id="incidents"):
                    with Vertical():
                        with Horizontal(classes="row"):
                            yield Button("all", id="filter-all", compact=True)
                            yield Button("open", id="filter-open", compact=True)
                            yield Button("unlabelled", id="filter-unlabelled", compact=True)
                            yield Static("  enter: details · r/f label inside", id="inc-hint")
                        yield DataTable(id="inc-table", cursor_type="row")
                with TabPane("4 Models", id="models"):
                    with VerticalScroll():
                        yield Static("", id="models-info")
                        yield Label("Choose a model (named after Kepler's laws)", classes="section")
                        yield Static("", id="tiers-table")
                        with Horizontal(classes="row"):
                            yield Button("◯ Use Orbit", id="tier-orbit", compact=True)
                            yield Button("◐ Use Area", id="tier-area", compact=True)
                            yield Button("◉ Use Time", id="tier-time", compact=True)
                        with Horizontal(classes="row"):
                            yield Button("Retrain now (t)", id="train", variant="primary")
                        yield Static("", id="models-table")
                with TabPane("5 Integrations", id="integrations"):
                    with VerticalScroll():
                        yield Label("Tools (enter to connect)", classes="section")
                        yield DataTable(id="integ-table", cursor_type="row")
                        yield Static("", id="integ-active")
                with TabPane("6 Settings", id="settings"):
                    with VerticalScroll():
                        yield Label("Alerting", classes="section")
                        with Vertical(classes="field"):
                            yield Label("Minimum confidence to alert (%)")
                            yield Input("", id="set-sens")
                        with Vertical(classes="field"):
                            yield Label("Ignore changes smaller than (%)")
                            yield Input("", id="set-minchg")
                        with Vertical(classes="field"):
                            yield Label("Slack incoming webhook URL")
                            yield Input("", id="set-slack", password=True)
                        with Horizontal(classes="row"):
                            yield Label("Demo data  ")
                            yield Switch(id="set-demo")
                        with Horizontal(classes="row"):
                            yield Button("Save", id="save-settings", variant="primary")
                            yield Button("Test Slack", id="test-slack")
                        yield Label("API key", classes="section")
                        yield Static("", id="api-key")
                        with Horizontal(classes="row"):
                            yield Button("Copy key", id="copy-key")
                            yield Button("Rotate key", id="rotate-key", variant="error")
                        yield Label("This device", classes="section")
                        with Horizontal(classes="row"):
                            yield Label("Desktop notifications while open  ")
                            yield Switch(value=True, id="set-notify")
                        yield Static("", id="agent-status")
                        with Horizontal(classes="row"):
                            yield Button("Install background agent", id="agent-install")
                            yield Button("Uninstall agent", id="agent-uninstall")
                            yield Button("Test notification", id="test-notify")
                            yield Button("Open web dashboard", id="open-web")
                        yield Label("Alert log", classes="section")
                        yield Static("", id="alert-log")
                with TabPane("7 Kepler AI", id="ai"):
                    yield ChatPanel(self.app.bot, on_reply=self.app.ai_reply, id="ai-panel")
            with Vertical(id="chat"):
                yield Static("◆ Kepler · quick chat  (full Kepler AI: tab 7)", id="chat-title")
                yield RichLog(id="chat-log", wrap=True, min_width=30, markup=False)
                yield Input(placeholder="why did signups drop?  ·  is latency ok?  ·  help", id="chat-input")
        yield Footer()


class KeplerApp(App):
    TITLE = "Kepler"
    CSS = CSS
    COMMANDS = App.COMMANDS | {KeplerCommands}
    BINDINGS = [
        Binding("q", "quit", "Quit"), Binding("question_mark", "help", "Help"),
        Binding("slash", "focus_chat", "Chat"), Binding("ctrl+k", "toggle_chat", "Hide chat"),
        Binding("r", "refresh", "Refresh"), Binding("t", "train", "Train"), Binding("d", "demo", "Demo"),
        Binding("o", "open_web", "Web"), Binding("n", "toggle_notify", "Notify", show=False),
        *[Binding(str(i + 1), f"tab('{t}')", t.title(), show=False) for i, t in enumerate(TABS)],
    ]

    def __init__(self, client: Client, skip_welcome: bool = False, note: str = ""):
        super().__init__()
        self.client = client
        self.start_note = note  # shown once the app is up (e.g. "started a server for you")
        self.bot = Bot(Client(client.url, client._key))
        self._trainer = None  # /pdf, /y, /n, /new, /alias … (the kepler bot / teach commands), made on first use
        self.skip_welcome = skip_welcome
        self.scenarios: list[dict] = []
        self.metrics: list[dict] = []
        self.integrations: list[dict] = []
        self.incidents: list[dict] = []
        self.inc_filter = "all"
        self.sel_metric: str | None = None
        self.hours = 24
        self.slice = ""
        self.notify_desktop = True
        self.seen_open: set[int] | None = None
        self.main: MainScreen | None = None

    # ---------------------------------------------------------------- lifecycle

    def on_mount(self):
        self.theme = "tokyo-night"
        if self.start_note:
            self.notify(self.start_note, title="Kepler", timeout=12)
        if self.skip_welcome:
            self.switch_to_main()
        else:
            self.push_screen(WelcomeScreen())

    def switch_to_main(self, chat: bool = False, ai: bool = False):
        if self.main is None:
            self.main = MainScreen()
            self.switch_screen(self.main) if self.screen_stack and isinstance(self.screen, WelcomeScreen) else self.push_screen(self.main)
            self.call_after_refresh(self._after_main, chat, ai)
        elif ai:
            self.action_tab("ai")
        elif chat:
            self.action_focus_chat()

    def _after_main(self, chat: bool, ai: bool = False):
        log = self.chat_log
        log.write(Text.assemble(("◆ Kepler  ", f"bold {R.ACCENT}"), "Hi! Ask me about your metrics (",
                                ("'status'", "bold"), ", ", ("'why did signups drop?'", "bold"), "), maths (",
                                ("'solve y'' + y = 0'", "bold"), ", ", ("'prove x + 1/x >= 2 for positive x'", "bold"),
                                "), or anything (", ("'who was einstein'", "bold"), ")."))
        log.write(Text.assemble(("Commands: ", "grey62"), ("/pdf", "bold"), (" write up the last answer · ", "grey62"),
                                ("/pdf all", "bold"), (" · ", "grey62"), ("/open", "bold"), (" · teach me with ", "grey62"),
                                ("/y /n /new /alias", "bold"), (" · ", "grey62"), ("/help", "bold")))
        for t in self.main.query(DataTable):
            t.zebra_stripes = True
        self.main.query_one("#inc-table", DataTable).add_columns("#", "", "severity", "metric", "change", "confidence", "started", "for", "where", "label")
        self.main.query_one("#metric-incidents", DataTable).add_columns("#", "severity", "change", "started", "for", "where")
        self.main.query_one("#slice-table", DataTable).add_columns("slice", "now", "expected", "change", "z")
        self.main.query_one("#integ-table", DataTable).add_columns("tool", "direction", "category", "summary")
        self.refresh_data()
        self.set_interval(REFRESH_S, self.refresh_data)
        self.set_interval(1, self._tick)
        if ai:
            self.action_tab("ai")
        elif chat:
            self.action_focus_chat()

    # ---------------------------------------------------------------- Kepler AI tab

    @on(TabbedContent.TabActivated, "#tabs")
    def _tab_changed(self, ev: TabbedContent.TabActivated):
        chat = self.main.query_one("#chat")
        if ev.pane.id == "ai":
            self._side_chat_was_hidden = chat.has_class("hidden")
            chat.add_class("hidden")  # the AI tab has its own, bigger chat
            self.call_after_refresh(self.main.query_one(ChatPanel).focus_input)
        elif not getattr(self, "_side_chat_was_hidden", False):
            chat.remove_class("hidden")

    def ai_reply(self, last: dict):
        """After a Kepler AI answer: refresh the dashboard when the answer changed something."""
        intent = (last.get("ranked") or [("", 0)])[0][0]
        if intent in ("label_real", "label_false", "train", "demo_inject", "set_sensitivity", "set_tier"):
            self.refresh_data()

    @property
    def chat_log(self) -> RichLog:
        return self.main.query_one("#chat-log", RichLog)

    def _tick(self):
        n = sum(1 for i in self.incidents if i["status"] == "open")
        bar = Text.assemble(("◉ Kepler ", f"bold {R.ACCENT}"), (f"{self.client.url}  ", "grey62"), ("● live  ", "green"),
                            (f"{n} open incident{'s' if n != 1 else ''}", "bold red" if n else "green"),
                            ("   🔔" if self.notify_desktop else "   🔕", ""), (f"   {time.strftime('%H:%M:%S')}", "grey50"))
        self.main.query_one("#topbar", Static).update(bar)

    # ---------------------------------------------------------------- data

    @work(thread=True, exclusive=True, group="refresh")
    def refresh_data(self):
        c = self.client
        try:
            ov = c.get("/api/overview")
            incs = c.get("/api/incidents", limit=200)
            if not self.scenarios:
                self.scenarios = c.get("/api/demo/scenarios")
            if not self.integrations:
                self.integrations = c.get("/api/integrations")
            rows = []
            for m in ov["metrics"]:
                d = c.get_auth(f"/api/v1/decision/{m['name']}")
                if d["decision"] == "anomaly":
                    top = d["incidents"][0]
                    rows.append({"metric": m["name"], "decision": "anomaly", "p": top["confidence"], "observed": top["observed"],
                                 "expected": top["expected"], "change_pct": top["change_pct"], "where": top["where"]})
                else:
                    rows.append({"metric": m["name"], "decision": d["decision"], "p": d.get("anomaly_probability"),
                                 "observed": d.get("observed"), "expected": d.get("expected"), "change_pct": d.get("change_pct")})
            models = c.get("/api/models")
            self.tiers = c.get("/api/tiers")
            settings = c.get("/api/settings")
            pulls, dests, log = c.get("/api/connectors"), c.get("/api/destinations"), c.get("/api/notifications")
        except KeplerError as e:
            self.call_from_thread(self.notify, str(e), severity="error", title="Kepler")
            return
        self.call_from_thread(self._apply, ov, incs, rows, models, settings, pulls, dests, log)

    def _apply(self, ov, incs, rows, models, settings, pulls, dests, log):
        s = self.main
        self.metrics, self.incidents = ov["metrics"], incs
        st = ov["stats"]
        lab = st["tp"] + st["fp"]
        for k, title, val, sub in (("open", "Open incidents", st["open"], "needs attention" if st["open"] else "all clear"),
                                   ("last24", "Incidents, 24 h", st["last24"], f"{st['total']} all-time"),
                                   ("watched", "Metrics watched", len(ov["metrics"]), f"{sum(1 for m in ov['metrics'] if m['model'] == 'custom')} custom-trained"),
                                   ("precision", "Alert precision", f"{st['tp'] / lab:.0%}" if lab else "–", f"{st['tp']} real · {st['fp']} false")):
            s.query_one(f"#stat-{k}", Static).update(Text.assemble((title + "\n", "grey62"), (str(val), "bold red" if k == "open" and st["open"] else "bold"),
                                                                   ("\n" + sub, "grey50")))
        s.query_one("#ov-status", Static).update(R.status_table(rows, compact=True))
        open_incs = [i for i in incs if i["status"] == "open"]
        s.query_one("#ov-open", Static).update(Group(*[R.incident_panel(i) for i in open_incs[:3]]) if open_incs
                                               else Text("No open incidents. 🎉", style="green"))
        demo = s.query_one("#demo-buttons", Horizontal)
        if settings["demo_mode"] and not demo.children and self.scenarios:
            demo.mount_all([Button(sc["label"].split(":")[0], id=f"inject-{sc['id']}", compact=True) for sc in self.scenarios])
        self._notify_new(open_incs)

        # metrics list
        lv = s.query_one("#metric-list", ListView)
        names = [m["name"] for m in ov["metrics"]]
        if [getattr(i, "metric_name", None) for i in lv.children] != names:
            lv.clear()
            for m in ov["metrics"]:
                item = ListItem(Label(Text.assemble(("● " if m["status"] == "anomaly" else "○ ", "red" if m["status"] == "anomaly" else "grey50"), m["name"])))
                item.metric_name = m["name"]
                lv.append(item)
            if self.sel_metric is None and names:
                self.sel_metric = names[0]
        if self.sel_metric:
            self.load_metric()

        self._fill_incidents()

        # models
        if getattr(self, "tiers", None):
            s.query_one("#tiers-table", Static).update(Group(
                R.tiers_table(self.tiers),
                Text(self.tiers["paywall"]["note"] + (
                    f"  Estimated bill ${self.tiers['monthly_preview']['amount']:.0f}/month → $0 charged."
                    if self.tiers.get("monthly_preview") else ""), style="grey62")))
            for t in ("orbit", "area", "time"):
                s.query_one(f"#tier-{t}", Button).variant = "primary" if self.tiers["default"] == t else "default"
        fb = models["feedback"]
        s.query_one("#models-info", Static).update(Text.assemble(
            ("Baseline: ", "bold"), "shared base model on day 1, then a custom weekly profile per metric and slice.\n",
            ("Filter: ", "bold"), f"{'learned from ' + str(fb.get('n_labels', 0)) + ' labels' if fb.get('active') else 'statistical prior only'}",
            f" · weight {fb.get('weight', 0):.0%}" + (f" · cross-validated accuracy {fb['cv_accuracy']:.0%}" if fb.get("cv_accuracy") is not None else ""),
            f"\nLabels: {models['labels']['pos']} 👍  {models['labels']['neg']} 👎  {models['labels']['unl']} unlabelled"))
        s.query_one("#models-table", Static).update(R.table(["metric", "baseline", "slices", "trained on", "updated", "learned weekly shape"], [
            [x["metric"], f"custom · {x['period']}" if x["kind"] == "custom" else "base (shared)",
             str(max(0, x["slices_trained"] - 1)) if x["slices_trained"] else "–", f"{x['trained_days']} d" if x["trained_days"] else "–",
             R.ago(x["trained_at"]) if x["trained_at"] else "never", R.spark(x["profile"] or [], 40)] for x in models["metrics"]]))

        # integrations
        it = s.query_one("#integ-table", DataTable)
        if it.row_count != len(self.integrations):
            it.clear()
            for i in self.integrations:
                it.add_row(Text(i["label"], style="bold"), {"pull": "pull from", "push": "receive from", "destination": "send to"}[i["direction"]],
                           i["category"], i["summary"][:70], key=i["type"])
        s.query_one("#integ-active", Static).update(Group(
            R.table(["#", "scheduled pull", "metric", "every", "status"], [[p["id"], p["name"], p["config"].get("metric", ""),
                    f"{p['interval_s'] // 60} min", p["last_status"] or "–"] for p in pulls] or [["", "none yet", "", "", ""]]),
            R.table(["#", "incident destination", "sends", "status"], [[d["id"], d["name"], f"{d['min_severity']}+", d["last_status"] or "waiting"]
                    for d in dests] + [["", "Slack", "all", "connected" if settings["slack_webhook_url"] else "not set (Settings)"]])))

        # settings (don't overwrite what the user is typing)
        for wid, val in (("#set-sens", f"{settings['sensitivity'] * 100:.0f}"), ("#set-minchg", f"{settings['min_change_pct']:.0f}"),
                         ("#set-slack", settings["slack_webhook_url"])):
            w = s.query_one(wid, Input)
            if not w.has_focus and not getattr(w, "_touched", False):
                w.value = val
        sw = s.query_one("#set-demo", Switch)
        if not sw.has_focus:
            sw.value = settings["demo_mode"]
        s.query_one("#api-key", Static).update(Text(settings["api_key"], style=f"bold {R.ACCENT}"))
        ag = device.agent_status()
        s.query_one("#agent-status", Static).update(Text(
            f"Background agent: {'running' if ag['running'] else 'installed, not running' if ag['installed'] else 'not installed'}"
            f" · notifies you of new incidents even when this app is closed · log {ag['log']}", style="grey62"))
        s.query_one("#alert-log", Static).update(R.table(["kind", "message", "slack", "when"], [
            [n["kind"], n["payload"]["text"], "✓" if n["delivered"] else (n["error"] or ""), R.ago(n["created_at"])] for n in log[:12]])
            if log else Text("No alerts sent yet.", style="grey50"))

    def _fill_incidents(self):
        t = self.main.query_one("#inc-table", DataTable)
        incs = self.incidents
        if self.inc_filter == "open":
            incs = [i for i in incs if i["status"] == "open"]
        elif self.inc_filter == "unlabelled":
            incs = [i for i in incs if i.get("feedback") is None]
        cursor = t.cursor_row
        t.clear()
        for d in incs:
            t.add_row(str(d["incident_id"]), Text("●", style="red") if d["status"] == "open" else Text("○", style="grey50"),
                      Text(d["severity"], style=R.SEV[d["severity"]]), d["metric"], R.change_text(d),
                      R.bar(d["confidence"], 10) + Text(f" {d['confidence']:.2f}"), R.hhmm(d["started_at"]),
                      R.mins(d["started_at"], d["last_seen_at"]), Text(R.where_text(d["where"]), style=R.ACCENT),
                      {1: "👍", 0: "👎"}.get(d.get("feedback"), ""), key=str(d["incident_id"]))
        if incs and cursor is not None:
            t.move_cursor(row=min(cursor, len(incs) - 1))

    def _notify_new(self, open_incs):
        ids = {i["incident_id"] for i in open_incs}
        if self.seen_open is not None:
            for d in open_incs:
                if d["incident_id"] not in self.seen_open:
                    msg = f"{d['metric']} {R.change_text(d)} · {R.where_text(d['where'])}"
                    self.notify(msg, title=f"Kepler · {d['severity'].upper()} #{d['incident_id']}", severity="error", timeout=8)
                    if self.notify_desktop:
                        device.notify(f"Kepler · {d['severity'].upper()}", msg, f"{d['confidence']:.0%} confidence · #{d['incident_id']}")
        self.seen_open = ids

    @work(thread=True, exclusive=True, group="metric")
    def load_metric(self):
        m = next((x for x in self.metrics if x["name"] == self.sel_metric), None)
        if not m:
            return
        try:
            data = self.client.get(f"/api/metrics/{m['id']}/series", hours=self.hours, slice=self.slice)
            br = self.client.get(f"/api/metrics/{m['id']}/breakdown")["slices"]
        except KeplerError as e:
            self.call_from_thread(self.notify, str(e), severity="error")
            return
        self.call_from_thread(self._apply_metric, m, data, br)

    def _apply_metric(self, m, data, br):
        s = self.main
        last = next((p for p in reversed(data["points"]) if p.get("value") is not None), {})
        s.query_one("#metric-head", Static).update(Text.assemble(
            (m["name"], "bold"), f"  {m['description'] or ''}\n", "now ", (R.num(last.get("value")), "bold"),
            f"  expected {R.num(last.get('expected'))}  normal {R.num(last.get('lower'))}–{R.num(last.get('upper'))}",
            (f"   {data['model']} · alerts when it goes {m['bad_direction']}", "grey50")))
        sel = s.query_one("#slice-select", Select)
        opts = [(x, x) for x in data["slices"]]
        if [o[1] for o in getattr(sel, "_kepler_opts", [])] != [o[1] for o in opts]:
            sel._kepler_opts = opts
            sel.set_options(opts)
        plot = s.query_one("#chart", PlotextPlot)
        plt = plot.plt
        plt.clear_data()
        plt.clear_figure()
        pts = data["points"]
        xs = list(range(len(pts)))
        nan = float("nan")
        plt.plot(xs, [p["upper"] if p.get("upper") is not None else nan for p in pts], color="gray", marker="braille")
        plt.plot(xs, [p["expected"] if p.get("expected") is not None else nan for p in pts], color="magenta", marker="braille", label="expected")
        plt.plot(xs, [p["value"] if p.get("value") is not None else nan for p in pts], color="cyan", marker="braille", label="actual")
        if pts:
            n = 6
            idx = [int(i * (len(pts) - 1) / (n - 1)) for i in range(n)]
            fmt = "%a %H:%M" if self.hours > 30 else "%H:%M"
            plt.xticks(idx, [time.strftime(fmt, time.localtime(pts[i]["ts"])) for i in idx])
        plt.title(f"{m['name']}{' · ' + self.slice if self.slice else ''} · last {self.hours} h")
        plot.refresh()
        st = s.query_one("#slice-table", DataTable)
        st.clear()
        for x in sorted(br, key=lambda x: -abs(x["z"] or 0)):
            hot = x["z"] is not None and abs(x["z"]) >= 3
            st.add_row(x["slice"], R.num(x["observed"]), R.num(x["expected"]), Text(R.pct(x["change_pct"]), style="bold red" if hot else ""),
                       "–" if x["z"] is None else f"{x['z']:.1f}", key=x["slice"])
        mi = s.query_one("#metric-incidents", DataTable)
        mi.clear()
        for d in reversed(data["incidents"]):
            mi.add_row(str(d["incident_id"]), Text(d["severity"], style=R.SEV[d["severity"]]), R.change_text(d), R.hhmm(d["started_at"]),
                       R.mins(d["started_at"], d["last_seen_at"]), R.where_text(d["where"]), key=str(d["incident_id"]))

    # ---------------------------------------------------------------- events

    @on(ListView.Selected, "#metric-list")
    def metric_picked(self, ev: ListView.Selected):
        self.sel_metric, self.slice = ev.item.metric_name, ""
        self.load_metric()

    @on(Select.Changed, "#slice-select")
    def slice_picked(self, ev: Select.Changed):
        self.slice = "" if ev.value is Select.NULL else str(ev.value)
        self.load_metric()

    @on(DataTable.RowSelected, "#inc-table")
    @on(DataTable.RowSelected, "#metric-incidents")
    def incident_picked(self, ev: DataTable.RowSelected):
        self.push_screen(IncidentScreen(int(ev.row_key.value)))

    @on(DataTable.RowSelected, "#slice-table")
    def slice_row(self, ev: DataTable.RowSelected):
        self.slice = ev.row_key.value
        self.load_metric()

    @on(DataTable.RowSelected, "#integ-table")
    def integ_picked(self, ev: DataTable.RowSelected):
        integ = next(i for i in self.integrations if i["type"] == ev.row_key.value)
        self.push_screen(ConnectScreen(integ), lambda _: self.refresh_data())

    @on(Input.Changed, "#set-sens, #set-minchg, #set-slack")
    def touched(self, ev: Input.Changed):
        ev.input._touched = True

    @on(Switch.Changed, "#set-notify")
    def notify_switch(self, ev: Switch.Changed):
        self.notify_desktop = ev.value

    @on(Button.Pressed)
    def button(self, ev: Button.Pressed):
        bid = ev.button.id or ""
        if bid.startswith("range-"):
            self.hours = int(bid.split("-")[1])
            self.load_metric()
        elif bid.startswith("filter-"):
            self.inc_filter = bid.split("-")[1]
            self._fill_incidents()
        elif bid.startswith("inject-"):
            self.action_inject(bid[len("inject-"):])
        elif bid == "train":
            self.action_train()
        elif bid.startswith("tier-"):
            tier = bid.split("-", 1)[1]
            self.run_bg(lambda: self.client.put("/api/settings", {"model_tier": tier}),
                        lambda r: (self.notify(f"Default model → {tier.title()}", title="Kepler"), self.refresh_data()))
        elif bid == "save-settings":
            self.save_settings()
        elif bid == "test-slack":
            self.run_bg(lambda: self.client.post("/api/settings/test-slack"), lambda r: self.notify(r["message"], severity="information" if r["ok"] else "error"))
        elif bid == "copy-key":
            self.action_copy_key()
        elif bid == "rotate-key":
            self.run_bg(lambda: self.client.post("/api/settings/rotate-key"), lambda r: (self.notify("New API key generated"), self.refresh_data()))
        elif bid == "agent-install":
            self.action_agent_install()
        elif bid == "agent-uninstall":
            self.run_bg(device.agent_uninstall, lambda r: (self.notify(r), self.refresh_data()))
        elif bid == "test-notify":
            self.action_test_notify()
        elif bid == "open-web":
            self.action_open_web()

    def save_settings(self):
        s = self.main
        try:
            body = {"sensitivity": float(s.query_one("#set-sens", Input).value) / 100,
                    "min_change_pct": float(s.query_one("#set-minchg", Input).value),
                    "slack_webhook_url": s.query_one("#set-slack", Input).value.strip(),
                    "demo_mode": s.query_one("#set-demo", Switch).value}
        except ValueError:
            self.notify("sensitivity and min change must be numbers", severity="error")
            return
        for wid in ("#set-sens", "#set-minchg", "#set-slack"):
            s.query_one(wid, Input)._touched = False
        self.run_bg(lambda: self.client.put("/api/settings", body), lambda r: (self.notify("Settings saved"), self.refresh_data()))

    @work(thread=True)
    def run_bg(self, fn, done=None):
        try:
            r = fn()
            if done:
                self.call_from_thread(done, r)
        except Exception as e:  # surface any server/device error as a toast
            self.call_from_thread(self.notify, str(e), severity="error")

    # ---------------------------------------------------------------- chat

    @on(Input.Submitted, "#chat-input")
    def chat_submit(self, ev: Input.Submitted):
        text = ev.value.strip()
        ev.input.value = ""
        if not text:
            return
        self.chat_log.write(Text.assemble(("you › ", f"bold {R.ACCENT}"), text))
        self.ask(text)

    @work(thread=True, exclusive=False, group="chat")
    def ask(self, text: str):
        if text.startswith("/"):
            self.call_from_thread(self._show_items, self._command(text))
            return
        reply = self.bot.handle(text)
        if reply.decision.get("intent") in ("math", "knowledge", "lookup") and self.trainer:
            self.trainer.history.append(text)  # so /pdf can write it up
        self.call_from_thread(self._show_reply, reply)

    @property
    def trainer(self):
        if self._trainer is None:
            from ..bot.chat_app import Collector
            from ..bot.teach import Trainer
            self._trainer = Trainer(Collector(), self.bot, spinners=False)
        return self._trainer

    def _command(self, line: str) -> list:
        """The kepler bot / teach slash commands (/pdf, /tex, /open, /y, /n, /new, /alias, /test, /help …)."""
        from ..bot.chat_app import Collector
        t = self.trainer
        t.out = Collector()
        if line.strip().lower() in ("/quit", "/q", "/exit"):
            return [Text("(use q or ctrl+c to quit the app)", style="grey50")]
        try:
            t.handle(line)
        except Exception as e:  # noqa: BLE001 - the chat must survive anything
            return [Text(f"✗ {type(e).__name__}: {e}", style="red")]
        return list(t.out.items)

    def _show_items(self, items: list):
        for it in items:
            self.chat_log.write(it)
        self.chat_log.write(Text(""))

    def _show_reply(self, reply):
        self.chat_log.write(reply.renderable())
        self.chat_log.write(Text(""))
        intent = reply.decision.get("intent")
        if intent in ("label_real", "label_false", "train", "demo_inject", "set_sensitivity"):
            self.refresh_data()
        if intent in ("metric_detail", "breakdown") and reply.decision["slots"].get("metric"):
            self.sel_metric = reply.decision["slots"]["metric"]
            self.hours = reply.decision["slots"].get("hours", self.hours)
            self.slice = reply.decision["slots"].get("slice", "")
            self.load_metric()

    # ---------------------------------------------------------------- actions

    def action_tab(self, tab: str):
        if self.main:
            self.main.query_one("#tabs", TabbedContent).active = tab

    def action_focus_chat(self):
        if self.main.query_one("#tabs", TabbedContent).active == "ai":
            self.main.query_one(ChatPanel).focus_input()
            return
        chat = self.main.query_one("#chat")
        chat.remove_class("hidden")
        self.main.query_one("#chat-input", Input).focus()

    def action_toggle_chat(self):
        chat = self.main.query_one("#chat")
        chat.toggle_class("hidden")
        if not chat.has_class("hidden"):
            self.main.query_one("#chat-input", Input).focus()

    def action_refresh(self):
        self.refresh_data()
        self.notify("refreshed", timeout=1.5)

    def action_help(self):
        self.push_screen(HelpScreen())

    def action_train(self):
        self.notify("training…", timeout=2)
        self.run_bg(lambda: self.client.post("/api/models/train"),
                    lambda r: (self.notify(f"Retrained · feedback filter {r['feedback'].get('status')}", title="Kepler"), self.refresh_data()))

    def action_demo(self):
        if self.scenarios:
            sc = self.scenarios[int(time.time()) % len(self.scenarios)]
            self.action_inject(sc["id"])

    def action_inject(self, scenario: str):
        self.notify(f"injecting {scenario}…", timeout=2)

        def done(r):
            self.refresh_data()
            if r.get("incident_id"):
                self.push_screen(IncidentScreen(r["incident_id"]))
            else:
                self.notify("Injected; not confident enough to alert yet.")
        self.run_bg(lambda: self.client.post("/api/demo/inject", {"scenario": scenario}), done)

    def action_open_web(self):
        device.open_url(self.client.dashboard_url())

    def action_copy_key(self):
        self.run_bg(lambda: device.copy(self.client.key), lambda ok: self.notify("API key copied" if ok else "no clipboard available"))

    def action_toggle_notify(self):
        self.notify_desktop = not self.notify_desktop
        self.main.query_one("#set-notify", Switch).value = self.notify_desktop
        self.notify(f"desktop notifications {'on' if self.notify_desktop else 'off'}")

    def action_test_notify(self):
        ok = device.notify("Kepler", "Desktop notifications work.", "test")
        self.notify("test notification sent" if ok else "no desktop notifier available on this system")

    def action_set_tier(self, tier: str):
        self.run_bg(lambda: self.client.put("/api/settings", {"model_tier": tier}),
                    lambda r: (self.notify(f"Default model → {tier.title()}", title="Kepler"), self.refresh_data()))

    def action_agent_install(self):
        self.run_bg(lambda: device.agent_install(self.client.url), lambda r: (self.notify(r, timeout=8), self.refresh_data()))


def run(client: Client, skip_welcome: bool = False, note: str = "") -> int:
    KeplerApp(client, skip_welcome, note).run()
    return 0
