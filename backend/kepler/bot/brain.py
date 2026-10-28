"""Kepler the bot: message → typed decision {intent, confidence, slots} → action → rich reply.

No language model. A trained intent classifier + slot extractors + a small dialogue state (last metric, last
incident, pending question) — the same "typed decision with a probability" idea as the rest of Kepler.
"""
import json
import time
from dataclasses import asdict, dataclass, field

from rich.console import Group
from rich.text import Text

from .. import device
from ..cli import render as R
from ..cli.client import Client, KeplerError
from . import knowledge, language, latex, model, reasoning, store
from ..library import answer as library_answer
from .mind import Mind
from .intents import INTENTS
from .slots import Context, extract

CONFIDENT = 0.45          # below this, ask which of the top two was meant
LOST = 0.22               # below this, say it wasn't understood (and suggest things) instead of guessing
NEEDS = {"why_metric": "metric", "metric_detail": "metric", "decide": "metric", "breakdown": "metric",
         "connect_tool": "tool", "set_tier": "tier"}
USES_INCIDENT = {"explain_incident", "label_real", "label_false"}
CHAT_INTENTS = {"greet", "thanks", "help"}


@dataclass
class Reply:
    decision: dict
    blocks: list = field(default_factory=list)   # rich renderables
    text: str = ""                               # one-line plain summary (for notifications / logs)

    def renderable(self, show_decision: bool = True):
        parts = [decision_line(self.decision)] if show_decision else []
        note = read_as_line(self.decision)
        if show_decision and note is not None:
            parts.append(note)
        return Group(*parts, *self.blocks)


def read_as_line(d: dict) -> Text | None:
    """'↳ read as: what is 2 + 2' when the English layer or a follow-up rewrote the message."""
    if d.get("note"):
        return Text(f"  ↳ {d['note']}", style="grey50")
    if d.get("read_as") and d.get("text") and language.changed(d["text"], d["read_as"]):
        return Text(f"  ↳ read as: {d['read_as']}", style="grey50")
    return None


def decision_line(d: dict) -> Text:
    t = Text("◆ ", style=R.ACCENT)
    t.append(d["intent"], style=f"bold {R.ACCENT}")
    t.append(f"  p={d['confidence']:.2f}", style="bold")
    slots = {k: v for k, v in d["slots"].items() if k not in ("metric_guess",)}
    if slots:
        t.append("  " + " ".join(f"{k}={v}" for k, v in slots.items()), style="grey62")
    if d.get("alternatives"):
        t.append("   alt " + ", ".join(f"{i} {p:.2f}" for i, p in d["alternatives"]), style="grey42")
    if d.get("resumed"):
        t.append("  (continuing)", style="grey42")
    return t


class Bot:
    def __init__(self, client: Client):
        self.c = client
        self.memory: dict = {"metric": None, "incident": None, "last": None, "pending": None}
        self.mind = Mind()
        self._ctx: Context | None = None
        self._ctx_at = 0.0

    # ---------------------------------------------------------------- understanding

    def context(self) -> Context:
        if self._ctx is None or time.time() - self._ctx_at > 30:
            ov = self.c.get("/api/overview")
            metrics = [m["name"] for m in ov["metrics"]]
            slices = {}
            for m in ov["metrics"]:
                try:
                    slices[m["name"]] = [s["slice"] for s in self.c.get(f"/api/metrics/{m['id']}/breakdown")["slices"]]
                except KeplerError:
                    slices[m["name"]] = []
            tools = {}
            for i in self.c.get("/api/integrations"):
                tools[i["label"].lower()] = i["type"]
                tools[i["type"].replace("_", " ")] = i["type"]
            tools.update({"aws": "cloudwatch", "otel": "otlp", "open telemetry": "otlp", "slack": "slack",
                          "newrelic": "newrelic", "pg": "postgres", "postgresql": "postgres"})
            scenarios = [s["id"] for s in self.c.get("/api/demo/scenarios")]
            self._ctx, self._ctx_at = Context(metrics, slices, tools, scenarios), time.time()
        return self._ctx

    def _protect(self) -> set:
        try:
            ctx = self.context()
        except KeplerError:
            return set()
        words = set()
        for m in ctx.metrics:
            words.update(m.lower().replace("_", " ").split())
        return words

    def _classify(self, text: str) -> tuple[str, float]:
        try:
            _, delex = extract(text, self.context())
        except KeplerError:
            delex = text
        return model.classify(delex, 1)[0]

    def understand(self, text: str) -> dict:
        pending = self.memory.get("pending")
        choice = text.strip().lower().rstrip(".")
        if pending and pending["kind"] == "choose" and choice in ("1", "2", "first", "second", "the first one", "the second one"):
            chosen = pending["options"][0 if choice in ("1", "first", "the first one") else 1]
            if pending.get("text"):
                store.add_example(pending["text"], pending["delex"], chosen)  # learn from the answer
            self.memory["pending"] = None
            return {"decision": "intent", "intent": chosen, "confidence": 1.0, "slots": dict(pending["slots"]),
                    "text": text, "delexicalised": text, "alternatives": [], "resumed": True,
                    "note": f"learned: '{pending['text']}' means {chosen}" if pending.get("text") else ""}
        th = self.mind.think(text, self._protect(), self._classify)
        if th.kind in ("math", "steps"):
            self.memory["pending"] = None
            sol = th.solution
            return {**sol.decision(), "text": text, "read_as": th.read_as, "note": th.note,
                    "delexicalised": th.read_as, "solution": asdict(sol), "steps_again": th.kind == "steps"}
        if th.kind == "lookup":
            self.memory["pending"] = None
            a = th.lookup
            return {"decision": "intent", "intent": "lookup", "confidence": a["confidence"],
                    "slots": {"decision": a["decision"], **({"source": a["title"]} if a["title"] else {})},
                    "text": text, "read_as": th.read_as, "delexicalised": th.read_as, "alternatives": [], "lookup": a}
        if th.kind == "knowledge":
            self.memory["pending"] = None
            return {"decision": "intent", "intent": "knowledge", "confidence": 0.97, "slots": {"topic": th.knowledge["topic"]},
                    "text": text, "read_as": th.read_as, "delexicalised": th.read_as, "alternatives": [],
                    "knowledge": th.knowledge}
        if th.taught:
            slots, delex = extract(th.read_as, self.context())
            return {"decision": "intent", "intent": th.taught, "confidence": 1.0, "slots": slots, "text": text,
                    "read_as": th.read_as, "delexicalised": delex, "alternatives": [], "note": "you taught me this one"}
        text_in = th.read_as
        slots, delex = extract(text_in, self.context())
        ranked = model.classify(delex)
        intent, p = ranked[0]
        if intent != "demo_inject":
            slots.pop("scenario", None)  # scenario words ("ios", "latency") only matter when asking for a demo
        d = {"decision": "intent", "intent": intent, "confidence": round(p, 3), "slots": slots, "text": text,
             "read_as": text_in, "delexicalised": delex,
             "alternatives": [(i, round(q, 3)) for i, q in ranked[1:3] if q >= 0.08]}
        if pending:
            # a short follow-up that just supplies what we asked for ("signups")
            if pending["kind"] == "slot" and pending["slot"] in slots and (p < 0.75 or len(text.split()) <= 3):
                d.update(intent=pending["intent"], resumed=True, slots={**pending["slots"], **slots})
            self.memory["pending"] = None
        if d["intent"] != "demo_inject":
            d["slots"].pop("scenario", None)
        return d

    # ---------------------------------------------------------------- dispatch

    def handle(self, text: str) -> Reply:
        parts = self.mind.parts(text) if text.strip() else [text]
        if len(parts) == 1:
            return self._handle_one(text)
        replies = [self._handle_one(p) for p in parts]
        blocks = []
        for i, (p, r) in enumerate(zip(parts, replies), 1):
            blocks.append(Text.assemble((f"{i}/{len(parts)} ", f"bold {R.ACCENT}"), (p, "bold")))
            blocks.append(r.renderable())
            blocks.append(Text(""))
        d = {"decision": "multi", "intent": "multi", "confidence": round(min(r.decision.get("confidence", 0) for r in replies), 3),
             "slots": {"questions": len(parts)}, "alternatives": [], "text": text,
             "parts": [{"text": p, **{k: v for k, v in r.decision.items() if k in ("intent", "confidence", "slots")}}
                       for p, r in zip(parts, replies)]}
        return Reply(d, blocks, " · ".join(r.text for r in replies if r.text))

    def _handle_one(self, text: str) -> Reply:
        req = latex.request(text) if text.strip() else None
        if req:
            question, pdf = req
            w, items = latex.write_answers([question], self.mind, self._protect(), self._classify, pdf=pdf)
            d = {"decision": "intent", "intent": "document", "confidence": 1.0, "slots": {"pdf": bool(w.pdf)},
                 "text": text, "alternatives": [], "document": {"pdf": str(w.pdf) if w.pdf else None, "tex": str(w.tex), "note": w.note}}
            return Reply(d, [Text(latex.summary(w))], str(w.pdf or w.tex))
        if not text.strip():
            return Reply({"intent": "none", "confidence": 0, "slots": {}}, [])
        try:
            d = self.understand(text)
            if d["intent"] not in ("math", "knowledge", "lookup") and not d.get("resumed") and d["confidence"] < LOST:
                return self._lost(d)
            if d["confidence"] < CONFIDENT and not d.get("resumed") and d["alternatives"]:
                return self._clarify(d)
            slots = d["slots"]
            need = NEEDS.get(d["intent"])
            if need == "metric" and "metric" not in slots and self.memory["metric"]:
                slots["metric"] = self.memory["metric"]
            if need and need not in slots:
                return self._ask_slot(d, need)
            if d["intent"] in USES_INCIDENT and "incident" not in slots:
                inc = self.memory["incident"] or self._latest_incident()
                if inc:
                    slots["incident"] = inc
            if "metric" in slots:
                self.memory["metric"] = slots["metric"]
            action = getattr(self, f"do_{d['intent']}", None)
            reply = action(d, slots) if action else self._taught_reply(d)
            if "incident" in slots and d["intent"] in USES_INCIDENT:
                self.memory["incident"] = slots["incident"]
            return reply
        except KeplerError as e:
            return Reply({"intent": "error", "confidence": 1.0, "slots": {}}, [Text(f"✗ {e}", style="red")], str(e))

    def _taught_reply(self, d) -> Reply:
        """An intent you created with `kepler teach`: answer with the reply you gave it."""
        spec = store.load()["intents"].get(d["intent"], {})
        text = spec.get("reply") or f"(you taught me '{d['intent']}' but gave it no reply yet)"
        return Reply(d, [Text(text)], text)

    def _lost(self, d) -> Reply:
        """Not understood: say so, suggest the closest things, and let a 1/2 answer teach it."""
        opts = [d["intent"]] + [i for i, _ in d["alternatives"]][:1]
        self.memory["pending"] = {"kind": "choose", "options": opts if len(opts) == 2 else opts * 2, "slots": d["slots"],
                                  "text": d["text"], "delex": d["delexicalised"]}
        lines = [Text.assemble("I'm not sure what you mean by ", (f"'{d['text']}'", "bold"), ".")]
        lines.append(Text.assemble(("  1 ", "bold"), model.describe(opts[0]), ("   2 ", "bold"), model.describe(opts[-1]),
                                   ("   (reply 1 or 2 and I'll remember)", "grey50")))
        lines.append(Text("I can also do maths ('sum of first n numbers', '15% of 200') and explain words ('what is a median'). "
                          "Say 'help' for everything.", style="grey62"))
        return Reply({**d, "intent": "unknown"}, lines, "not understood")

    def _clarify(self, d) -> Reply:
        a, b = d["intent"], d["alternatives"][0][0]
        self.memory["pending"] = {"kind": "choose", "options": [a, b], "slots": d["slots"],
                                  "text": d["text"], "delex": d["delexicalised"]}
        msg = Text.assemble("I'm not sure what you meant. Did you want to:\n",
                            ("  1 ", "bold"), f"{model.describe(a)}  ", (f"(p={d['confidence']:.2f})\n", "grey50"),
                            ("  2 ", "bold"), f"{model.describe(b)}  ", (f"(p={d['alternatives'][0][1]:.2f})", "grey50"),
                            ("\nReply 1 or 2 (I'll remember), or rephrase.", "grey62"))
        return Reply(d, [msg], "clarifying")

    def do_tiers(self, d, s):
        if s.get("metric"):
            m = self._metric(s["metric"])
            res = self.c.get(f"/api/metrics/{m['id']}/compare")
            lead = Text.assemble("Ran all three models on ", (m["name"], "bold"), " just now:")
            return Reply(d, [lead, R.compare_table(res), Text(res["paywall"]["note"], style="grey62")])
        data = self.c.get("/api/tiers")
        lead = Text.assemble("Three models, named after Kepler's laws. You're on ", (data["default"].title(), f"bold {R.ACCENT}"),
                             " by default. ", ("Say 'use time for signups' or 'switch to orbit'.", "grey62"))
        return Reply(d, [lead, R.tiers_table(data), Text(data["paywall"]["note"], style="grey62")])

    def do_set_tier(self, d, s):
        tier = s["tier"]
        if s.get("metric"):
            m = self._metric(s["metric"])
            self.c.patch(f"/api/metrics/{m['id']}", {"tier": tier})
            return Reply(d, [Text.assemble((m["name"], "bold"), " now uses ", (tier.title(), f"bold {R.ACCENT}"),
                                           ". Other metrics keep the workspace default.")])
        self.c.put("/api/settings", {"model_tier": tier})
        return Reply(d, [Text.assemble("Default model → ", (tier.title(), f"bold {R.ACCENT}"),
                                       ". Metrics with their own model keep it. ", ("Free during the beta.", "grey62"))])

    def _ask_slot(self, d, slot) -> Reply:
        self.memory["pending"] = {"kind": "slot", "slot": slot, "intent": d["intent"], "slots": d["slots"]}
        if slot == "metric":
            options = ", ".join(self.context().metrics)
            guess = d["slots"].get("metric_guess")
            msg = f"Which metric? {options}" if not guess else f"I don't know a metric called '{guess}'. Which one? {options}"
        elif slot == "tier":
            msg = "Which model: Orbit (cheapest, fastest), Area (balanced) or Time (deepest reasoning)?"
        else:
            msg = "Which tool? " + ", ".join(sorted({v for v in self.context().tools.values()}))
        return Reply(d, [Text(msg)], msg)

    def _latest_incident(self) -> int | None:
        incs = self.c.get("/api/incidents", limit=1, status="open") or self.c.get("/api/incidents", limit=1)
        return incs[0]["incident_id"] if incs else None

    def _metric(self, name) -> dict:
        return self.c.metric_by_name(name)

    # ---------------------------------------------------------------- small talk

    def do_greet(self, d, s):
        ov = self.c.get("/api/overview")
        n = ov["stats"]["open"]
        state = Text(f"{n} open incident{'s' if n != 1 else ''}.", style="red bold") if n else Text("All metrics look normal.", style="green")
        return Reply(d, [Text.assemble("Hi, I'm Kepler. I watch ", (str(len(ov["metrics"])), "bold"), " metrics. ", state,
                                       ("  Ask me anything: 'status', 'why did signups drop?', 'show api_errors last 6h'.", "grey62"))])

    def do_thanks(self, d, s):
        return Reply(d, [Text("Anytime. I'll keep watching.")])

    def do_math(self, d, s):
        sol = reasoning.Solution(**d["solution"])
        return Reply(d, [reasoning.render(sol)], sol.answer)

    def do_lookup(self, d, s):
        return Reply(d, [library_answer.render(d["lookup"])], d["lookup"]["text"])

    def do_knowledge(self, d, s):
        return Reply(d, [knowledge.render(d["knowledge"])], d["knowledge"]["text"])

    def do_help(self, d, s):
        rows = [[name, spec["desc"], spec["t"][min(2, len(spec["t"]) - 1)].replace("{metric}", "signups")
                 .replace("{id}", "40").replace("{dur}", "6h").replace("{tool}", "datadog").replace("{pct}", "70%")
                 .replace("{scenario}", "ios").replace("{slice}", "ios").replace("{sev}", "critical").replace("{n}", "5")]
                for name, spec in INTENTS.items()]
        rows.append(["math", "maths, worked step by step", "solve 2x + 3 = 7 · 15% of 200 · derivative of x^3"])
        return Reply(d, [Text("Here's what I understand (say it any way you like):"), R.table(["intent", "does", "e.g."], rows)])

    # ---------------------------------------------------------------- reading

    def _status_rows(self):
        rows = []
        for m in self.c.get("/api/overview")["metrics"]:
            r = self.c.get_auth(f"/api/v1/decision/{m['name']}")
            if r["decision"] == "anomaly":
                top = r["incidents"][0]
                rows.append({"metric": m["name"], "decision": "anomaly", "p": top["confidence"], "observed": top["observed"],
                             "expected": top["expected"], "change_pct": top["change_pct"], "where": top["where"]})
            else:
                rows.append({"metric": m["name"], "decision": r["decision"], "p": r.get("anomaly_probability"),
                             "observed": r.get("observed"), "expected": r.get("expected"), "change_pct": r.get("change_pct")})
        return rows

    def do_status(self, d, s):
        rows = self._status_rows()
        bad = [r for r in rows if r["decision"] == "anomaly"]
        head = (Text(f"{len(bad)} metric(s) anomalous: " + ", ".join(r["metric"] for r in bad), style="red bold") if bad
                else Text(f"All {len(rows)} metrics normal.", style="green bold"))
        return Reply(d, [head, R.status_table(rows, compact=True)], head.plain)

    def do_list_incidents(self, d, s):
        incs = self.c.get("/api/incidents", limit=200, status="open" if s.get("open") else None)
        if s.get("metric"):
            incs = [i for i in incs if i["metric"] == s["metric"]]
        if s.get("severity"):
            incs = [i for i in incs if i["severity"] == s["severity"]]
        if s.get("hours"):
            incs = [i for i in incs if i["started_at"] >= time.time() - s["hours"] * 3600]
        incs = incs[: s.get("n", 10)]
        if not incs:
            return Reply(d, [Text("No incidents match.", style="green")], "no incidents")
        self.memory["incident"] = incs[0]["incident_id"]
        return Reply(d, [Text(f"{len(incs)} incident(s), newest first. Say 'explain #{incs[0]['incident_id']}' for details."),
                         R.incidents_table(incs)])

    def do_explain_incident(self, d, s):
        if "incident" not in s:
            return Reply(d, [Text("There are no incidents yet.")])
        res = self.c.get(f"/api/incidents/{s['incident']}")
        self.memory["last"] = res["decision"]
        dd = res["decision"]
        lead = Text.assemble(f"#{dd['incident_id']}: ", (dd["metric"], "bold"), f" {'spiked' if dd['direction'] == 'spike' else 'dropped'} ",
                             (R.pct(dd["change_pct"]), R.SEV[dd["severity"]]), " where ", (R.where_text(dd["where"]), f"bold {R.ACCENT}"),
                             f", and I'm {dd['confidence']:.0%} sure it's real.")
        return Reply(d, [lead, R.incident_panel(dd, res["points"])], lead.plain)

    def do_why_metric(self, d, s):
        name = s["metric"]
        res = self.c.get_auth(f"/api/v1/decision/{name}")
        if res["decision"] == "anomaly":
            inc = res["incidents"][0]
            s["incident"] = inc["incident_id"]
            self.memory["incident"] = inc["incident_id"]
            return self.do_explain_incident(d, s)
        recent = [i for i in self.c.get("/api/incidents", limit=50) if i["metric"] == name][:1]
        if recent and recent[0]["started_at"] > time.time() - 86400:
            s["incident"] = recent[0]["incident_id"]
            self.memory["incident"] = s["incident"]
            r = self.do_explain_incident(d, s)
            r.blocks.insert(0, Text(f"{name} is normal right now; the most recent incident was {R.ago(recent[0]['started_at'])}:", style="grey62"))
            return r
        return Reply(d, [Text(f"{name} looks normal: nothing to explain. Here's the current decision:"), R.decision_panel(res)])

    def do_metric_detail(self, d, s):
        m = self._metric(s["metric"])
        hours = s.get("hours", 24)
        data = self.c.get(f"/api/metrics/{m['id']}/series", hours=hours, slice=s.get("slice", ""))
        title = f"{m['name']}{' · ' + s['slice'] if s.get('slice') else ''} · last {hours} h · {data['model']}"
        pts = data["points"]
        last = next((p for p in reversed(pts) if p.get("value") is not None), {})
        summary = Text.assemble("now ", (R.num(last.get("value")), "bold"), f"  expected {R.num(last.get('expected'))}",
                                (f"   {len(data['incidents'])} incident(s) in range", "red" if data["incidents"] else "grey50"))
        return Reply(d, [summary, R.metric_chart(pts, 76, 14, title)], summary.plain)

    def do_decide(self, d, s):
        res = self.c.get_auth(f"/api/v1/decision/{s['metric']}")
        self.memory["last"] = res
        word = res["decision"]
        p = res["incidents"][0]["confidence"] if word == "anomaly" else res.get("anomaly_probability")
        lead = Text.assemble((s["metric"], "bold"), " → ", (word.upper(), R.VERDICT[word][1]),
                             f"  (p(anomaly) = {'–' if p is None else f'{p:.2f}'})")
        return Reply(d, [lead, R.decision_panel(res)], lead.plain)

    def do_breakdown(self, d, s):
        m = self._metric(s["metric"])
        sl = self.c.get(f"/api/metrics/{m['id']}/breakdown")["slices"]
        if not sl:
            return Reply(d, [Text(f"{m['name']} has no dimensions to break down.")])
        sl.sort(key=lambda x: -abs(x["z"] or 0))
        rows = [[x["slice"], R.num(x["observed"]), R.num(x["expected"]), Text(R.pct(x["change_pct"]), style="bold red" if abs(x["z"] or 0) >= 3 else ""),
                 f"{x['z']:.1f}" if x["z"] is not None else "–"] for x in sl]
        top = sl[0]
        lead = Text.assemble("Most unusual slice right now: ", (top["slice"], f"bold {R.ACCENT}"), f" (z {top['z']:.1f}).")
        return Reply(d, [lead, R.table(["slice", "now", "expected", "change", "z"], rows)], lead.plain)

    def do_models(self, d, s):
        mm = self.c.get("/api/models")
        fb = mm["feedback"]
        rows = [[x["metric"], f"custom · {x['period']}" if x["kind"] == "custom" else "base (shared)",
                 str(max(0, x["slices_trained"] - 1)) if x["slices_trained"] else "–", f"{x['trained_days']} d" if x["trained_days"] else "–"]
                for x in mm["metrics"]]
        acc = f", cross-validated accuracy {fb['cv_accuracy']:.0%}" if fb.get("cv_accuracy") is not None else ""
        lead = Text(f"Feedback filter: {'active' if fb.get('active') else 'prior only'} · {mm['labels']['pos']} 👍 / "
                    f"{mm['labels']['neg']} 👎 labels{acc}, weight {fb.get('weight', 0):.0%}.")
        return Reply(d, [lead, R.table(["metric", "baseline", "slices", "trained on"], rows)], lead.plain)

    def do_settings(self, d, s):
        st = self.c.get("/api/settings")
        rows = [["sensitivity", f"{st['sensitivity']:.0%} minimum confidence to alert"],
                ["ignore changes under", f"{st['min_change_pct']:.0f}%"],
                ["slack", "connected" if st["slack_webhook_url"] else "not connected"],
                ["demo mode", "on" if st["demo_mode"] else "off"],
                ["destinations", ", ".join(x["name"] for x in self.c.get("/api/destinations")) or "none"],
                ["background agent", "running" if device.agent_status()["running"] else "not running"]]
        return Reply(d, [R.table(["setting", "value"], rows)])

    def do_alerts_log(self, d, s):
        log = self.c.get("/api/notifications")[:10]
        if not log:
            return Reply(d, [Text("I haven't sent any alerts yet.")])
        rows = [[n["kind"], n["payload"]["text"], "✓ delivered" if n["delivered"] else (n["error"] or ""), R.ago(n["created_at"])] for n in log]
        return Reply(d, [R.table(["kind", "message", "slack", "when"], rows)])

    def do_integrations(self, d, s):
        items = self.c.get("/api/integrations")
        rows = [[{"pull": "pull from", "push": "receive from", "destination": "send to"}[i["direction"]], i["label"], i["summary"][:70]]
                for i in items]
        return Reply(d, [R.table(["", "tool", "what"], rows), Text("Say 'connect datadog' to see what a tool needs.", style="grey62")])

    def do_connect_tool(self, d, s):
        tool = s["tool"]
        if tool == "slack":
            return Reply(d, [Text("Slack: paste an incoming-webhook URL with `kepler settings --slack https://hooks.slack.com/…` or in Settings.")])
        integ = next((i for i in self.c.get("/api/integrations") if i["type"] == tool), None)
        if not integ:
            return Reply(d, [Text(f"I don't have an integration for {tool} yet.")])
        if integ["direction"] == "push":
            hint = {"segment": f"Add a Webhook destination in Segment → {self.c.url}/api/v1/hooks/segment?key=<your key>",
                    "otlp": f"Point an OTLP/HTTP exporter (encoding: json) at {self.c.url} with header X-Kepler-Key."}[tool]
            return Reply(d, [Text(integ["summary"]), Text(hint, style="bold")])
        rows = [[f["name"], f["label"], "required" if f["required"] else "optional", f["default"][:50]] for f in integ["fields"]]
        cmd = (f"kepler connect {tool} " + " ".join(f"{f['name']}=…" for f in integ["fields"] if f["required"]))
        return Reply(d, [Text.assemble((integ["label"], "bold"), f": {integ['summary']}"), R.table(["field", "label", "", "default"], rows),
                         Text.assemble("Run ", (cmd, "bold"), " or use the Integrations tab.")])

    # ---------------------------------------------------------------- acting

    def _label(self, d, s, value):
        if "incident" not in s:
            return Reply(d, [Text("Which incident? Say e.g. 'mark #40 as real'.")])
        r = self.c.post(f"/api/incidents/{s['incident']}/feedback", {"label": value})
        word = "a real incident 👍" if value == 1 else "a false alarm 👎"
        return Reply(d, [Text(f"Labelled #{s['incident']} as {word}. {r['labels']} labels so far; say 'train' to learn from them.")])

    def do_label_real(self, d, s):
        return self._label(d, s, 1)

    def do_label_false(self, d, s):
        return self._label(d, s, 0)

    def do_train(self, d, s):
        r = self.c.post("/api/models/train")
        ok = [m for m in r["metrics"] if m["status"] == "trained"]
        fb = r["feedback"]
        acc = f" (cross-validated accuracy {fb['cv_accuracy']:.0%})" if fb.get("cv_accuracy") is not None else ""
        return Reply(d, [Text(f"Retrained {len(ok)}/{len(r['metrics'])} metric baselines and the feedback filter: {fb.get('status')}{acc}.", style="green")])

    def do_demo_inject(self, d, s):
        sc = s.get("scenario") or "ios_release_bug"
        r = self.c.post("/api/demo/inject", {"scenario": sc})
        if not r.get("incident_id"):
            return Reply(d, [Text(f"Injected '{sc}'. Not confident enough to alert yet; watch the Incidents tab.")])
        s["incident"] = r["incident_id"]
        self.memory["incident"] = r["incident_id"]
        rep = self.do_explain_incident(d, s)
        rep.blocks.insert(0, Text(f"Injected '{sc}' into the demo startup, and caught it:", style="grey62"))
        return rep

    def do_set_sensitivity(self, d, s):
        cur = self.c.get("/api/settings")["sensitivity"]
        text = d["text"].lower()
        if "pct" in s:
            new = s["pct"]
        elif any(w in text for w in ("less noisy", "fewer", "too many", "raise", "only alert")):
            new = min(0.95, cur + 0.1)
        else:
            new = max(0.2, cur - 0.1)
        new = round(min(0.95, max(0.2, new)), 2)
        self.c.put("/api/settings", {"sensitivity": new})
        more = "fewer, more certain" if new > cur else "more" if new < cur else "the same"
        return Reply(d, [Text(f"Sensitivity {cur:.0%} → {new:.0%}: you'll get {more} alerts.")])

    def do_open_dashboard(self, d, s):
        path = f"incident/{s['incident']}" if s.get("incident") else (f"metric/{self._metric(s['metric'])['id']}" if s.get("metric") else "")
        url = self.c.dashboard_url(path)
        ok = device.open_url(url)
        return Reply(d, [Text(f"{'Opened' if ok else 'Open'} {url}")])

    def do_copy(self, d, s):
        text = d["text"].lower()
        if "key" in text:
            payload, what = self.c.get("/api/settings")["api_key"], "API key"
        elif "snippet" in text:
            key = self.c.get("/api/settings")["api_key"]
            payload = f'curl -X POST {self.c.url}/api/v1/ingest -H "X-Kepler-Key: {key}" -H "Content-Type: application/json" -d \'{{"metrics":[{{"name":"signups","value":1}}]}}\''
            what = "ingest snippet"
        else:
            inc = s.get("incident") or self.memory["incident"]
            obj = self.c.get(f"/api/incidents/{inc}")["decision"] if inc else self.memory.get("last")
            if not obj:
                return Reply(d, [Text("Nothing to copy yet. Ask me about an incident first.")])
            payload, what = json.dumps(obj, indent=2), f"decision JSON{f' for #{inc}' if inc else ''}"
        ok = device.copy(payload)
        return Reply(d, [Text(f"Copied the {what} to your clipboard." if ok else f"No clipboard available. Here it is:\n{payload}")])
