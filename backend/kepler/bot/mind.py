"""How Kepler reads a message, in order (shared by the bot, `kepler teach` and the chat app):

  1. language   casual / misspelt English → plain English ("wats 2 plus 2" → "what is 2 + 2")
  2. lessons    a sentence you labelled in `kepler teach` always means what you said
  3. dialogue   follow-ups to the last maths answer ("and for 20?", "double it", "why?")
  4. reasoning  maths, series, word problems (exact, with worked steps)
  5. knowledge  what words mean, small talk
  6. library    general knowledge from datasets (Wikipedia, WordNet, your files, live lookup), only for questions
                that aren't confidently Kepler commands
  7. intents    everything else goes to the trained intent classifier (Kepler actions)

Several streams at once (streams.py): a message with several questions is split and each part is read on its
own; a question that needs a fact *and* maths ("population of india divided by 2") is chained library → maths;
definitions are answered from every source that knows the word, and agreement raises the confidence.
"""
import re
from dataclasses import dataclass

from . import dialogue, fields, knowledge, language, model, reasoning, solvers, store, streams

QUESTION = re.compile(r"^(?:who|what|when|where|which|why|how|whose|whom|define|definition|meaning|synonyms?|another word|"
                      r"tell me (?:about|something about)|teach me about|explain|describe|summari[sz]e|is|are|was|were|does|"
                      r"do|did|can|has|have|name|list|give me facts|facts about|information on|info on|look up)\b")
# "quick one before my meeting, what's the longest river…", "while I have you, could you tell me which river…"
LEAD_IN = re.compile(r"^(?:.{0,60}?(?:,|:|;|\.\.\.|-)\s+|(?:lol|lmao|wait|ok|okay|so|hey|random (?:one|question)|"
                     r"quick (?:one|question)|btw|oh)\s+)?(?:(?:could|can|would) you (?:possibly |please )?tell me |"
                     r"do you (?:happen to )?know |i (?:was )?wonder(?:ing)? |tell me )?")
WORLD = re.compile(r"^(?:who (?:wrote|invented|discovered|painted|founded|built|composed|directed|came up with|was|is)|"
                   r"when (?:did|was|were|is)|(?:in )?(?:what|which) year|how (?:many|much|tall|far|old|long|big|deep|high|"
                   r"heavy|fast|hot|cold) (?:is|are|was|were|does|do|did)|what(?: is|'s| was) the (?:capital|population|"
                   r"largest|longest|tallest|smallest|biggest|highest|deepest|fastest|oldest|boiling|freezing|speed of|"
                   r"distance|name of|currency|language)|which (?:is the )?(?:river|country|city|planet|ocean|sea|mountain|"
                   r"continent|language|element|animal|state|desert|lake|war|king|queen|president)|where (?:is|was|are|"
                   r"were|did|do)|what (?:language|currency) )")
MORE = re.compile(r"^(?:tell me more|more|go on|continue|keep going|read more|and then|what else|anything else|more please)\??$")
# Words that make a question about Kepler (your metrics, incidents, settings) rather than general knowledge. The
# intent classifier alone can't tell: it is confidently wrong on topics it never saw ("why is the sky blue").
KEPLER_WORDS = set("""incident incidents alert alerts alerting metric metrics status dashboard model models tier tiers
orbit sensitivity threshold slack integration integrations connector connectors connect datadog grafana prometheus
sentry posthog mixpanel amplitude cloudwatch newrelic segment webhook otlp opentelemetry train training label labels
anomaly anomalies spike spiked spikes drop dropped drops broken healthy health production prod demo inject settings
decision decisions kepler slice slices segment segments breakdown chart plot graph trend overview things everything
anything fire latency errors error signups sessions failures notifications key api agent""".split())
# "is the site down", "is our app working": about your own systems, never an encyclopedia question
OUTAGE = re.compile(r"^(?:is|are|why is|why are|check (?:if|whether)|is it just me or is) (?:the |my |our |your )?"
                    r"(?:site|website|web site|app|service|server|servers|system|platform|checkout|backend|frontend|"
                    r"database|db|page|login|payments?)s? (?:\w+ )?(?:down|up|offline|online|working|broken|slow|out)\b|"
                    r"\b(?:outage|outages|downtime|pinging|pestering|bugging)\b")


@dataclass
class Thought:
    kind: str                  # "math" | "steps" | "knowledge" | "intent"
    text: str                  # what you typed
    read_as: str               # after the English layer (and any follow-up rewrite)
    note: str = ""             # how a follow-up was read
    solution: object = None    # reasoning.Solution for math / steps
    knowledge: dict | None = None
    lookup: dict | None = None # library answer (kepler.library.answer.Answer as a dict)
    taught: str | None = None  # the intent you taught for this exact sentence

    @property
    def rewritten(self) -> bool:
        return bool(self.note) or language.changed(self.text, self.read_as)


class Mind:
    def __init__(self):
        self.mem = dialogue.Memory()
        self.last_kind = ""
        self.last_lookup: dict | None = None

    def _library(self, norm: str, protect: set | None, classify) -> dict | None:
        try:
            from ..library import answer, index, web
        except ImportError:
            return None
        core = LEAD_IN.sub("", norm, count=1) or norm
        if WORLD.match(core):
            norm = core  # the question itself, without the chatter in front of it
        if not (QUESTION.match(norm) or norm.endswith("?")):
            return None
        words = set(re.findall(r"[a-z0-9_]+", norm))
        if words & (KEPLER_WORDS | set(protect or ())) or "#" in norm or OUTAGE.search(norm):
            return None  # about your metrics / incidents / Kepler: a Kepler command
        if not (index.exists() or web.enabled()):
            if re.match(r"(?:who|when|where|define|tell me about|what (?:is|are|was|were) (?:a |an |the )?[a-z])", norm) \
                    or WORLD.match(norm):
                return answer.Answer("unknown", "fact", norm, "I don't have general knowledge loaded yet. Feed me with "
                                     "`kepler learn wikipedia` and `kepler learn wordnet`, or turn on the lookup with "
                                     "`kepler learn --web on`.", 0.0).as_dict()
            return None
        a = answer.ask(norm)
        if a.decision == "unknown":
            intent, p = classify(norm) if classify else model.classify(norm, 1)[0]
            if p >= 0.45 and intent not in ("help", "greet", "thanks"):
                return None  # the library doesn't know, and it might be a command after all
        return a.as_dict()

    def parts(self, text: str) -> list[str]:
        """The questions in a message. One word problem across several sentences stays whole."""
        pieces = streams.split(text)
        if len(pieces) == 1:
            return pieces
        whole = reasoning.solve_text(language.normalise(text))
        return [text] if whole and whole.ok else pieces

    @staticmethod
    def _about_kepler(norm: str) -> bool:
        words = set(re.findall(r"[a-z0-9_]+", norm))
        return bool(words & KEPLER_WORDS) or bool(re.search(r"#\d|\bincident \d|\b[a-z]+_[a-z0-9_]+\b", norm)) \
            or bool(OUTAGE.search(norm))

    def think(self, text: str, protect: set | None = None, classify=None) -> Thought:
        norm = language.normalise(text, protect)
        taught = store.taught_intent(text) or store.taught_intent(norm)
        if taught and taught not in ("math", "knowledge"):
            self.last_kind = "intent"
            return Thought("intent", text, norm, taught=taught)
        question, note = norm, ""
        if self.last_kind == "math":
            follow = dialogue.rewrite(norm, self.mem)
            if follow:
                question, note = follow
                if question == dialogue.STEPS and self.mem.solution is not None:
                    return Thought("steps", text, norm, note, self.mem.solution)
        # field problems read best before normalising: "m/s", "H2O", "0.001 M"
        sol = fields.solve(text) if not note else None
        if sol is None and not note:
            sol = streams.chain(question)
        if sol is None or (not sol.ok and reasoning.solve_text(question)):
            sol = reasoning.solve_text(question)
        if (sol is None or not sol.ok) and not note:
            # the subject solvers read chatty word problems the exact engine can't ("…? i keep mixing up the product rule")
            sol = solvers.solve(text) or sol
        if sol is not None and not sol.ok and not note and self._about_kepler(norm):
            sol = None  # "walk me through incident 142", "why's checkout_errors climbing since 02:10"
        k = knowledge.answer(norm) if not note else None
        if sol and (sol.ok or not k):
            if sol.ok:
                self.mem = dialogue.Memory(question, sol.answer, sol)
            self.last_kind = "math"
            return Thought("math", text, question, note, sol)
        if k:
            self.last_kind = "knowledge"
            if k["kind"] == "definition":
                k = {**k, "supporting": streams.blend(norm, k, "knowledge")}
                k["agreement"] = streams.agreement(k["text"], k["supporting"], ignore=k["title"])
            return Thought("knowledge", text, norm, knowledge=k)
        if self.last_kind == "lookup" and self.last_lookup and MORE.match(norm):
            from ..library import answer
            nxt = answer.more(self.last_lookup["doc_id"], self.last_lookup["next_ord"])
            if nxt:
                self.last_lookup = nxt.as_dict()
                return Thought("lookup", text, norm, lookup=self.last_lookup)
        found = self._library(norm, protect, classify)
        if found:
            if found["decision"] != "unknown":
                sup = streams.blend(norm, found, "lookup")
                if sup:
                    agree = streams.agreement(found["text"], sup, ignore=found.get("title", ""))
                    found = {**found, "supporting": sup, "agreement": agree,
                             "confidence": round(min(0.97, found["confidence"] + 0.08 * agree * len(sup)), 2)}
            self.last_kind = "lookup"
            self.last_lookup = found if found.get("doc_id") else self.last_lookup
            return Thought("lookup", text, norm, lookup=found)
        self.last_kind = "intent"
        return Thought("intent", text, norm)
