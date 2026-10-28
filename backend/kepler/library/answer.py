"""Question answering over the library, Jev-style: every answer is a typed decision.

  decision   "answer" (confident) · "unsure" (best guess, with alternatives) · "unknown" (says so)
  kind       definition · word · fact · yes_no · more
  confidence 0–1, from how much of the question the evidence covers and how far it beats the runner-up
  source     the article / file / dictionary it came from, with its URL and licence

Pipeline (no language model): read the question type (who / what / when / where / how many / define / yes-no)
and its subject → dictionary lookup for word meanings → exact article for "what is X" / "who is X" → BM25
passage search → split into sentences → score each sentence (idf-weighted term overlap, phrase matches, title
match, answer-type evidence such as years for "when" and numbers for "how many") → pick the best → optionally
look it up on Wikipedia when the library isn't sure.
"""
import math
import re
from dataclasses import asdict, dataclass, field

from . import index, web

ANSWER, UNSURE = 0.6, 0.38


@dataclass
class Answer:
    decision: str                 # answer | unsure | unknown
    kind: str                     # definition | word | fact | yes_no | more
    question: str
    text: str
    confidence: float
    title: str = ""
    url: str = ""
    licence: str = ""
    origin: str = ""              # library · web · files · dictionary
    also: list[str] = field(default_factory=list)
    doc_id: int | None = None
    next_ord: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


QWORDS = r"(?:who|what|when|where|which|why|how|whose|whom)"
SUBJECT = [
    (re.compile(r"^(?:what|who)(?: is| are| was| were|'s)(?: an?| the)? (.+?)\??$"), "what"),
    (re.compile(r"^(?:tell me|teach me|learn) (?:something |all |more )?about (?:an? |the )?(.+?)\??$"), "what"),
    (re.compile(r"^(?:explain|describe|summari[sz]e|what do you know about|do you know|information on|info on|facts about) (?:an? |the )?(.+?)\??$"), "what"),
    (re.compile(r"^where (?:is|are|was|were) (?:an? |the )?(.+?)(?: located| found| from)?\??$"), "where"),
    (re.compile(r"^when (?:is|was|did|were|does) (?:an? |the )?(.+?)(?: (?:born|die|died|founded|built|invented|created|"
                r"discovered|start|started|end|ended|begin|began|happen|happened|made|written|published|released|"
                r"signed|formed|established|launched|opened|elected|crowned))?\??$"), "when"),
]
WORD_Q = [
    re.compile(r"^(?:define|definition of|meaning of|what does|what is the meaning of|what's the meaning of|"
               r"what is the definition of|dictionary|look up)(?: the word)? \"?([a-z][a-z' -]{0,40}?)\"?(?: mean| means)?\??$"),
    re.compile(r"^(?:synonyms?|another word|other words?|similar words?)(?: of| for| to)? \"?([a-z][a-z' -]{0,40}?)\"?\??$"),
]
TYPE_HINTS = {
    "when": re.compile(r"\b(?:1[0-9]{3}|20[0-9]{2}|[1-9][0-9]{0,2} (?:BC|AD|BCE|CE))\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b|\bcentury\b"),
    "how_many": re.compile(r"\b\d[\d,.]*\b|\b(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|"
                           r"forty|fifty|hundred|thousand|million|billion|dozen)\b", re.I),
    "where": re.compile(r"\b(?:in|at|near|on|from) (?:the )?[A-Z][a-z]+"),
    "who": re.compile(r"\b[A-Z][a-z]+(?: (?:da|de|di|del|van|von|der|la|le|bin|ibn|al))? [A-Z][a-z]+\b"),
    "why": re.compile(r"\b(?:because|due to|caused by|causes|cause|result of|results in|so that|reason|scatter\w*|"
                      r"this is why|that is why|which makes|which means|therefore)\b", re.I),
}


UNIT_HINTS = [
    (r"^how (?:hot|cold|warm)\b|temperature|boiling point|melting point", r"°|\bdegrees?\b|\bkelvin\b|\b\d+ ?K\b"),
    (r"^how (?:far|long is|wide|deep|tall|high)\b|\b(?:height|length|distance|depth|diameter|radius)\b",
     r"\b\d[\d,.]* ?(?:km|kilomet|m\b|met(?:er|re)s?|mi\b|miles?|ft\b|feet|foot|light.years?|au\b|cm|mm|inch)"),
    (r"^how fast\b|\bspeed\b", r"\b\d[\d,.]* ?(?:km/h|kilomet\w* per|mph|miles per|m/s|met\w* per|knots?)|\bc\b"),
    (r"^how old\b|\bage of\b", r"\b\d[\d,.]* ?(?:years?|billion|million)\b|\bborn\b|\(\d{4}"),
]


def unit_hint(q: str):
    for qpat, apat in UNIT_HINTS:
        if re.search(qpat, q):
            return re.compile(apat, re.I)
    return None


def question_type(q: str) -> str:
    if re.match(r"^when\b|what (?:year|date|century)|which year", q):
        return "when"
    if re.match(r"^how (?:many|much|long|old|far|big|tall|high|deep|heavy|hot|cold|fast)\b|"
                r"what (?:is|was|are) the (?:population|number|size|height|length|area|boiling point|melting point|"
                r"temperature|speed|distance|weight|mass|age|depth|diameter|radius|value)\b", q):
        return "how_many"
    if re.match(r"^why\b|how (?:does|do|did|is|are|can)\b.*\b(?:work|happen|form|made|make|grow)", q):
        return "why"
    if re.match(r"^where\b|which (?:country|city|continent|place)", q):
        return "where"
    if re.match(r"^who\b|whose\b|which (?:person|man|woman|scientist|president|king|queen)", q):
        return "who"
    if re.match(r"^(?:is|are|was|were|does|do|did|can|has|have) ", q):
        return "yes_no"
    return "what"


def _sentences(text: str) -> list[str]:
    text = re.sub(r"(?<=[a-z][.!?])(?=[A-Z][a-z])", " ", text)  # "Ocean.The largest" (joined in the source)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", text) if len(s.strip()) > 15]


def _terms(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in index.STOP and len(w) > 1]


IRREGULAR = {"wrote": "writ", "written": "writ", "write": "writ", "writes": "writ", "writing": "writ", "built": "build",
             "made": "make", "began": "begin", "begun": "begin", "drew": "draw", "drawn": "draw", "sang": "sing",
             "sung": "sing", "taught": "teach", "found": "found", "founded": "found", "invented": "invent",
             "born": "bear", "bore": "bear", "died": "die", "dead": "die", "death": "die", "ran": "run", "won": "win",
             "fought": "fight", "led": "lead", "spoke": "speak", "spoken": "speak", "chose": "choose", "grew": "grow",
             "grown": "grow", "tallest": "highest", "biggest": "largest", "bigger": "larger", "smallest": "smallest",
             "fastest": "fastest", "people": "people"}


def _stem(w: str) -> str:
    if w in IRREGULAR:
        return IRREGULAR[w]
    for suf in ("ing", "edly", "ed", "es", "s", "ly"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _score_sentence(sent: str, qterms: list[str], qtype: str, title: str, subject: str, df: dict, ndocs: int) -> tuple[float, float]:
    """→ (score, coverage) for one candidate sentence."""
    sw = {_stem(w) for w in _terms(sent)}
    tw = {_stem(w) for w in _terms(title)}
    total = hit = 0.0
    for w in set(qterms):
        idf = math.log(1 + ndocs / (1 + df.get(w, 0)))
        total += idf
        st = _stem(w)
        if st in sw:
            hit += idf
        elif st in tw:
            hit += 0.7 * idf
    coverage = hit / total if total else 0.0
    score = coverage
    low = sent.lower()
    for a, b in zip(qterms, qterms[1:]):
        if f"{a} {b}" in low:
            score += 0.08
    if subject and subject.lower() in (title.lower(), title.lower().rstrip("s")):
        score += 0.25
    elif subject and subject.lower() in low:
        score += 0.1
    hint = TYPE_HINTS.get(qtype)
    if hint:
        score += 0.15 if hint.search(sent) else -0.1
    n = len(sent.split())
    if n < 6:
        score -= 0.15
    elif n > 60:
        score -= 0.1
    return score, coverage


def _subject(q: str) -> tuple[str, str] | None:
    for pat, kind in SUBJECT:
        m = pat.match(q)
        if m:
            s = re.sub(r"\s+(?:in (?:simple )?english|please|for me|in short|briefly)$", "", m.group(1)).strip(" ?.")
            if s and len(s) <= 80:
                return s, kind
    return None


def _title_variants(s: str) -> list[str]:
    s = s.strip()
    out = [s, s.title(), s.capitalize()]
    if s.endswith("s") and not s.endswith("ss"):
        out += [s[:-1], s[:-1].capitalize()]
    if s.endswith("ies"):
        out.append(s[:-3].capitalize() + "y")
    return list(dict.fromkeys(out))


PRONOUN_START = re.compile(r"(?:they|it|he|she|its|their|his|her|this|these)\b", re.I)
SUPERLATIVE_IN = re.compile(r"\b\w+est\b(?:\s+\w+){0,3}?\s+(?:in|of)\s+(?:the\s+)?([A-Z][a-z]+(?: [A-Z][a-z]+)?)")
ORDINALS = re.compile(r"\b(?:second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|\d+(?:st|nd|rd|th))\b")
GENERIC = {"world", "people", "person", "thing", "things", "time", "year", "years", "day", "number", "part", "way", "name"}


def _entities(q: str, limit: int = 4) -> list:
    """Article titles mentioned in the question ("spider", "Romeo and Juliet", "Australia"), longest first."""
    toks = re.findall(r"[a-z0-9']+", q)
    grams = []
    for n in range(min(6, len(toks)), 0, -1):
        for i in range(len(toks) - n + 1):
            g = toks[i:i + n]
            if g[0] in index.STOP or g[-1] in index.STOP or re.fullmatch(QWORDS, g[0]):
                continue
            if n == 1 and (g[0] in GENERIC or len(g[0]) < 3):
                continue
            grams.append(" ".join(g))
    if not grams or not index.exists():
        return []
    variants = set()
    for g in grams:
        variants.add(g)
        if g.endswith("s") and not g.endswith("ss"):
            variants.add(g[:-1])
    with index.session() as c:
        marks = ",".join("?" * len(variants))
        rows = c.execute(f"SELECT * FROM docs WHERE lower(title) IN ({marks})", list(variants)).fetchall()
    rows.sort(key=lambda r: (-len(r["title"].split()), 0 if r["source"] == "wikipedia" else 1))
    found, seen = [], set()
    for r in rows:
        if r["title"].lower() in seen:
            continue
        seen.add(r["title"].lower())
        found.append(r)
        if len(found) >= limit:
            break
    return found


def _doc_rows(doc, n: int = 14) -> list:
    with index.session() as c:
        return [{"id": r["id"], "doc_id": doc["id"], "ord": r["ord"], "text": r["text"], "title": doc["title"],
                 "source": doc["source"], "url": doc["url"], "licence": doc["licence"], "score": -50.0, "entity": True}
                for r in c.execute("SELECT * FROM passages WHERE doc_id = ? ORDER BY ord LIMIT ?", (doc["id"], n))]


def _phrase(sent: str, qterms: list) -> float:
    """Share of adjacent question-word pairs that appear close together (at most 2 words apart) in the sentence."""
    pairs = list(zip(qterms, qterms[1:]))
    if not pairs:
        return 0.0
    low = sent.lower()
    hit = sum(1 for a, b in pairs
              if re.search(r"\b" + re.escape(_stem(a)) + r"\w*\W+(?:\w+\W+){0,2}?" + re.escape(_stem(b)) + r"\w*", low))
    return hit / len(pairs)


def _first_sentences(text: str, n: int = 2) -> str:
    return " ".join(_sentences(text)[:n]) or text


def _origin(source: str) -> str:
    if source.startswith("files"):
        return "your files"
    return {"wikipedia": "Simple Wikipedia (offline)", "web-wikipedia": "Wikipedia (looked up online)"}.get(source, source)


# ---------------------------------------------------------------- the dictionary

def define_word(q: str) -> Answer | None:
    for pat in WORD_Q:
        m = pat.match(q)
        if m:
            w = m.group(1).strip()
            rows = index.word(w) or (index.word(w.rstrip("s")) if w.endswith("s") else [])
            if not rows:
                return None
            if pat is WORD_Q[1]:
                syn = []
                for r in rows:
                    syn += [s for s in r["synonyms"].split(", ") if s and s not in syn]
                if not syn:
                    return Answer("unknown", "word", q, f"I don't know synonyms for '{w}'.", 0.3, w, origin="Open English WordNet")
                return Answer("answer", "word", q, f"Synonyms of '{w}': " + ", ".join(syn[:15]) + ".", 0.95, w,
                              licence="CC BY 4.0 (Open English WordNet)", origin="Open English WordNet")
            lines = []
            for i, r in enumerate(rows[:4], 1):
                ex = f' (e.g. "{r["examples"].split(" | ")[0]}")' if r["examples"] else ""
                syn = f" Similar: {r['synonyms']}." if r["synonyms"] else ""
                lines.append(f"{i}. ({r['pos']}) {r['definition']}{ex}.{syn}")
            return Answer("answer", "word", q, "\n".join(lines), 0.95, w,
                          licence="CC BY 4.0 (Open English WordNet)", origin="Open English WordNet",
                          also=[f"{len(rows)} meanings in total"] if len(rows) > 4 else [])
    return None


# ---------------------------------------------------------------- articles and passages

def _from_rows(q: str, qtype: str, subject: str, rows, origin_hint: str = "") -> Answer | None:
    if not rows:
        return None
    qterms = _terms(q)
    if subject:
        qterms += [t for t in _terms(subject) if t not in qterms]
    if not qterms:
        return None
    # document frequency of each query term among the candidates (cheap idf)
    df: dict[str, int] = {}
    for r in rows:
        words = {_stem(w) for w in _terms(r["text"] + " " + r["title"])}
        for t in set(qterms):
            if _stem(t) in words:
                df[t] = df.get(t, 0) + 1
    q_ordinal = bool(ORDINALS.search(q))
    cands = []
    for rank, r in enumerate(rows):
        is_entity = bool(r["entity"]) if "entity" in r.keys() else False
        for i, s in enumerate(_sentences(r["text"])[:12]):
            seen_as = f"{r['title']} {s}" if is_entity and PRONOUN_START.match(s) else s
            sc, cov = _score_sentence(seen_as, qterms, qtype, r["title"], subject, df, len(rows))
            ph = _phrase(s, qterms)
            sc += 0.2 * ph + (0.2 if is_entity else max(0.0, 0.1 - 0.005 * rank)) + (0.05 if r["ord"] == 0 and i == 0 else 0)
            if not q_ordinal and ORDINALS.search(s):
                sc -= 0.25  # "the second largest ocean" doesn't answer "the largest ocean"
            if qtype == "who" and re.search(r"\bby (?:\w+ ){0,3}?[A-Z][a-z]+ [A-Z][a-z]+", s):
                sc += 0.2
            m_sup = SUPERLATIVE_IN.search(s)
            if m_sup and re.search(r"\w+est\b", q) and m_sup.group(1).lower() not in q:
                sc -= 0.25  # "the tallest mountain in New Hampshire" doesn't answer "the tallest mountain"
            if is_entity and r["title"].lower() in (subject.lower(), *[t for t in qterms]):
                sc += 0.15  # the question's own subject
            cands.append((sc, cov, s, r, ph, is_entity))
    if not cands:
        return None
    cands.sort(key=lambda c: -c[0])
    best_sc, best_cov, best_s, best_r, best_ph, best_ent = cands[0]
    runner = next((c for c in cands[1:] if c[3]["doc_id"] != best_r["doc_id"]), None)
    margin = best_sc - (runner[0] if runner else 0)
    conf = 0.1 + 0.4 * best_cov + 0.25 * best_ph + 0.15 * min(margin, 0.5) / 0.5 + (0.12 if best_ent else 0)
    conf = max(0.0, min(0.9, conf))
    if best_cov < 0.75:
        conf = min(conf, 0.5)   # most of the question isn't in the evidence: a guess at best
    if not best_ent and best_ph < 0.5:
        conf = min(conf, 0.55)  # found by keyword search only, words scattered: not sure
    hint = unit_hint(q) or TYPE_HINTS.get(qtype)
    if qtype == "who":
        names = [m.group(0) for m in TYPE_HINTS["who"].finditer(best_s)
                 if not set(_terms(m.group(0))) <= set(qterms) and not m.group(0).startswith(("The ", "This ", "In ", "On "))]  # "Mona Lisa" doesn't answer "who painted the Mona Lisa"
        if not names:
            conf = min(conf, 0.55)
        hint = None
    if hint and not hint.search(best_s):
        conf = min(conf, 0.55)  # a "when" answer without a date, "how many" without a number, "why" without a reason
    title_stems = {_stem(w) for w in _terms(best_r["title"])}
    detail = [t for t in qterms if _stem(t) not in title_stems]
    if detail:
        sent_stems = {_stem(w) for w in _terms(best_s)}
        if sum(1 for t in detail if _stem(t) in sent_stems) / len(detail) < 0.99:
            conf = min(conf, 0.58)  # the topic matched, but not the detail asked about ("largest", "water")
    if subject and not set(_terms(subject)) <= {w for w in _terms(best_s + " " + best_r["title"])}:
        conf = min(conf, 0.5)   # the thing asked about isn't even mentioned
    decision = "answer" if conf >= ANSWER else "unsure" if conf >= UNSURE else "unknown"
    # one sentence of context after the best one, from the same passage
    sents = _sentences(best_r["text"])
    idx = sents.index(best_s) if best_s in sents else 0
    text = " ".join(sents[idx: idx + 2]) if qtype == "what" and len(best_s.split()) < 25 else best_s
    also = []
    for c in cands[1:]:
        if c[3]["title"] not in also and c[3]["title"] != best_r["title"] and c[0] > best_sc - 0.5:
            also.append(c[3]["title"])
        if len(also) >= 3:
            break
    return Answer(decision, "fact", q, text, round(conf, 2), best_r["title"], best_r["url"], best_r["licence"],
                  origin_hint or _origin(best_r["source"]), also, best_r["doc_id"], best_r["ord"] + 1)


def _by_surname(name: str):
    """'einstein' → 'Albert Einstein': a one-word subject that ends a (short) article title."""
    if " " in name or len(name) < 4:
        return None
    with index.session() as c:
        return c.execute("SELECT * FROM docs WHERE lower(title) LIKE ? AND source = 'wikipedia' "
                         "AND length(title) - length(replace(title, ' ', '')) <= 3 ORDER BY length(title) LIMIT 1",
                         (f"% {name.lower()}",)).fetchone()


def _article(q: str, subject: str, kind: str) -> Answer | None:
    docs = [index.doc_by_title(t) for t in _title_variants(subject)] + [_by_surname(subject)]
    for doc in docs:
        if doc:
            paras = index.passages_of(doc["id"], 0, 4)
            if not paras:
                continue
            if kind in ("where", "when"):
                hint = TYPE_HINTS[kind]
                for p in paras:
                    for s in _sentences(p):
                        if hint.search(s):
                            return Answer("answer", "fact", q, s, 0.82, doc["title"], doc["url"], doc["licence"],
                                          _origin(doc["source"]), [], doc["id"], 1)
                return None  # the article doesn't state a date / place up front: search for it instead
            return Answer("answer", "definition", q, _first_sentences(paras[0], 2), 0.9, doc["title"], doc["url"],
                          doc["licence"], _origin(doc["source"]), [], doc["id"], 1)
    return None


def _yes_no(q: str) -> Answer | None:
    m = re.match(r"^(?:is|are|was|were) (?:an? |the )?([a-z0-9' -]+?) (?:an? |the )?((?:in|on|part of|a|an|the|located in|made of|capital of) .+|[a-z0-9' -]+?)\??$", q)
    if not m:
        return None
    subj, claim = m.group(1).strip(), m.group(2).strip()
    doc = next((index.doc_by_title(t) for t in _title_variants(subj) if index.doc_by_title(t)), None)
    if not doc:
        return None
    cterms = [_stem(t) for t in _terms(claim)]
    sterms = {_stem(t) for t in _terms(subj)}
    if not cterms:
        return None
    best, best_cov, negated, definition = "", 0.0, False, ""
    subj_re = "|".join(re.escape(_stem(t)) for t in sterms) or "x^"
    last = re.escape(_stem(cterms[-1]))
    stated = re.compile(rf"\b(?:(?:{subj_re})\w*|they|it|he|she)\b[^.]{{0,40}}?\b(?:is|are|was|were)\b[^.]{{0,60}}?\b{last}\w*", re.I)
    for i, p in enumerate(index.passages_of(doc["id"], 0, 8)):
        for j, s in enumerate(_sentences(p)):
            if not definition and re.search(r"\b(?:is|are|was|were)\b", s) and (sterms & {_stem(w) for w in _terms(s)}):
                definition = s
            m = stated.search(s)
            if not m:
                continue
            sw = {_stem(w) for w in _terms(s)}
            cov = sum(1 for t in cterms if t in sw) / len(cterms)
            if cov > best_cov:
                best, best_cov = s, cov
                negated = bool(re.search(r"\b(?:not|no|never|neither|nor|isn't|aren't|wasn't|weren't)\b", m.group(0).lower()))
    if best_cov >= 0.99 and negated:
        return Answer("answer", "yes_no", q, f"No. {best}", 0.8, doc["title"], doc["url"], doc["licence"], _origin(doc["source"]))
    if best_cov >= 0.99:
        return Answer("answer", "yes_no", q, f"Yes. {best}", 0.85, doc["title"], doc["url"], doc["licence"], _origin(doc["source"]))
    if best_cov >= 0.5:
        return Answer("unsure", "yes_no", q, f"Probably, but I'm not certain. Closest evidence: {best}", 0.5,
                      doc["title"], doc["url"], doc["licence"], _origin(doc["source"]))
    known = f" What I do know: {definition}" if definition else ""
    return Answer("unsure", "yes_no", q, f"I can't confirm that.{known}", 0.4,
                  doc["title"], doc["url"], doc["licence"], _origin(doc["source"]))


def ask(question: str, allow_web: bool = True) -> Answer:
    """Answer a general-knowledge question. Never raises; returns decision 'unknown' when it can't."""
    q = re.sub(r"\s+", " ", question.lower().strip()).rstrip("?!. ")
    q = re.sub(r"^(?:hey |ok |so |kepler,? |please |can you |could you |do you know |i want to know |i wonder )+", "", q)
    q = re.sub(r"\b(world war) (?:1|one|i)\b", r"\1 i", q)
    q = re.sub(r"\b(world war) (?:2|two|ii)\b", r"\1 ii", q)
    if not q:
        return Answer("unknown", "fact", question, "Ask me something.", 0.0)
    a = define_word(q) if index.exists() else None
    if a:
        return a
    qtype = question_type(q)
    if qtype == "yes_no" and index.exists():
        a = _yes_no(q)
        if a:
            return a  # yes / no / "can't confirm, but here's what I know": never a random fact
    subj = _subject(q)
    subject = subj[0] if subj else ""
    if subj and index.exists():
        a = _article(q, subj[0], subj[1])
        if a:
            return a
    best = None
    if index.exists():
        ent_rows = [row for doc in _entities(q) for row in _doc_rows(doc)]
        rows = ent_rows + list(index.search(q + (" " + subject if subject else ""), limit=25))
        best = _from_rows(q, qtype, subject, rows)
        if best and best.decision == "answer":
            return best
    if allow_web and web.enabled():
        pages = web.lookup(q, q)
        if pages:
            if subj:
                a = _article(q, subj[0], subj[1])
                if a:
                    return a
            rows = [{**row, "entity": False} for pg in pages for doc in [index.doc_by_title(pg["title"], "web-wikipedia")]
                    if doc for row in _doc_rows(doc, 40)]
            rows += list(index.search(q, limit=25, sources=("web-wikipedia",)))
            online = _from_rows(q, qtype, subject, rows, "Wikipedia (looked up online)")
            if online and (not best or online.confidence > best.confidence + 0.05):
                best = online
    if best:
        return best
    return Answer("unknown", "fact", question, "I don't know that yet. Teach me with `kepler learn PATH` (your files), "
                  "or turn on the Wikipedia lookup with `kepler learn --web on`.", 0.0)


def more(doc_id: int, start: int) -> Answer | None:
    paras = index.passages_of(doc_id, start, 1)
    if not paras:
        return None
    with index.session() as c:
        d = c.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone()
    return Answer("answer", "more", "tell me more", paras[0], 0.9, d["title"], d["url"], d["licence"], _origin(d["source"]),
                  [], doc_id, start + 1)


def render(a: dict):
    from rich.console import Group
    from rich.text import Text
    from ..cli import render as R
    style = {"answer": "white", "unsure": "yellow", "unknown": "grey62"}[a["decision"]]
    parts = []
    if a["decision"] == "unsure":
        parts.append(Text("Best guess (not sure):", style="yellow"))
    parts.append(Text(a["text"], style=style))
    if a["title"]:
        src = Text.assemble(("Source   ", "grey50"), (a["title"], f"bold {R.ACCENT}"), (f"  · {a['origin']}", "grey50"))
        if a["url"]:
            src.append(f"\n         {a['url']}", style="grey42")
        if a["licence"]:
            src.append(f"  ({a['licence']})", style="grey42")
        parts.append(src)
    if a.get("supporting"):
        from ..bot.knowledge import supporting_lines
        parts += supporting_lines(a)
    if a["also"]:
        parts.append(Text.assemble(("Related  ", "grey50"), (" · ".join(a["also"]), "grey70")))
    if a.get("doc_id") and a["decision"] != "unknown":
        parts.append(Text("say 'tell me more' to keep reading", style="grey42"))
    return Group(*parts)
