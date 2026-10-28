"""Several streams of knowledge at once.

Kepler's engines each know one thing: maths (reasoning), definitions (knowledge base), the library (Wikipedia,
dictionary, your files, live lookup) and your metrics (intents). This module lets one message use several of them:

  split      "is signups ok and what does anomaly mean?"      → two questions, two engines, one reply
  chain      "population of india divided by 2"               → library finds the number → maths uses it
             "height of mount everest in feet"                → library → unit conversion
             "how many years ago was einstein born"           → library finds the year → date maths
  compare    "which is bigger, the population of india or china" → two lookups → comparison
  blend      "what is a prime number"                         → knowledge base + dictionary + Wikipedia together,
                                                                 more confident when they agree

Rules only, no language model. Every step in a chain says which engine produced it and from which source.
"""
import datetime
import re

import sympy as sp

from . import reasoning

N = r"\d[\d,]*(?:\.\d+)?"
SCALE = {"thousand": 10 ** 3, "million": 10 ** 6, "billion": 10 ** 9, "trillion": 10 ** 12}

# ---------------------------------------------------------------- splitting a message into questions

QSTART = (r"(?:what|who|whom|whose|when|where|which|why|how|is|are|was|were|can|could|do|does|did|tell|show|define|"
          r"explain|give|list|convert|calculate|solve|find|whats|plot|chart|break|label|train|open|copy)")
SPLIT = re.compile(rf"\s*(?:\?+\s*(?=\S)|;\s*|,?\s+(?:and also|and then|and|also|plus|then)\s+(?={QSTART}\b))", re.I)


def split(text: str) -> list[str]:
    """Separate questions joined by '?', ';' or 'and what / and is / also how …'. Sentences of one word
    problem ('Tom is twice as old as Jerry. The sum of their ages is 36.') are never split here."""
    parts = [re.sub(r"^(?:and also|and then|and|also|plus|then)\s+", "", p.strip(" ,"), flags=re.I)
             for p in SPLIT.split(text.strip()) if p and p.strip(" ,?")]
    return parts if len(parts) > 1 else [text.strip()]


# ---------------------------------------------------------------- finding numeric facts in the library

ATTRS = {
    "population": (r"population|people|inhabitants|residents|citizens|populous", "count"),
    "height": (r"height|high|tall|elevation|above sea level|peak|summit", "len"),
    "length": (r"length|long", "len"),
    "depth": (r"depth|deep", "len"),
    "distance": (r"distance|away|far", "len"),
    "diameter": (r"diameter|across|wide", "len"),
    "area": (r"area|square|size", "area"),
    "speed": (r"speed|fast|velocity|travels at", "speed"),
    "mass": (r"mass|weigh|weight", "mass"),
    "weight": (r"mass|weigh|weight", "mass"),
    "temperature": (r"temperature|hot|cold|degrees", "temp"),
    "boiling point": (r"boil", "temp"),
    "melting point": (r"melt", "temp"),
    "age": (r"years old|old|age", "years"),
}
UNIT_RE = {
    "len": r"(km|kilomet(?:er|re)s?|m|met(?:er|re)s?|mi|miles?|ft|feet|foot|cm|centimet(?:er|re)s?|light[- ]years?)\b",
    "area": r"(km2|km²|square kilomet(?:er|re)s?|sq\.? ?km|square miles?|sq\.? ?mi|m2|m²|hectares?|acres?)",
    "speed": r"(km/s|kilomet(?:er|re)s? per second|km/h|kilomet(?:er|re)s? per hour|m/s|met(?:er|re)s? per second|mph|miles per hour)",
    "mass": r"(kg|kilograms?|tonnes?|tons?|g\b|grams?|lb|pounds?)",
    "temp": r"(°\s?[CF]|degrees? (?:celsius|fahrenheit|C|F)|K\b|kelvin)",
    "years": r"(years?)",
    "count": r"(people|inhabitants|residents|citizens|persons)?",
}
UNIT_NAME = {"kilometer": "km", "kilometre": "km", "kilometers": "km", "kilometres": "km", "meter": "m", "metre": "m",
             "meters": "m", "metres": "m", "mile": "mile", "miles": "mile", "mi": "mile", "feet": "ft", "foot": "ft",
             "centimeter": "cm", "centimetre": "cm", "kilogram": "kg", "kilograms": "kg", "tonne": "tonne", "tonnes": "tonne",
             "pound": "lb", "pounds": "lb", "km/h": "km/h", "mph": "mph", "m/s": "m/s", "km/s": "km/s",
             "meters per second": "m/s", "metres per second": "m/s", "meter per second": "m/s",
             "kilometers per second": "km/s", "kilometres per second": "km/s", "kilometers per hour": "km/h",
             "kilometres per hour": "km/h", "miles per hour": "mph", "degrees celsius": "c", "degrees fahrenheit": "f",
             "square kilometres": "km2", "square kilometers": "km2", "square kilometre": "km2", "square kilometer": "km2",
             "km²": "km2", "sq km": "km2", "sq. km": "km2", "square miles": "square mile", "square mile": "square mile",
             "sq mi": "square mile", "hectares": "hectare", "acres": "acre"}


def _value(num: str, scale: str | None):
    v = sp.Rational(num.replace(",", ""))
    return v * SCALE[scale.lower()] if scale and scale.lower() in SCALE else v


def _quantities(sentence: str, dim: str) -> list[tuple]:
    """→ [(value, unit, matched text)] for numbers in the sentence with the right kind of unit."""
    out = []
    unit = UNIT_RE[dim]
    for m in re.finditer(rf"(?<![\w.])({N})\s*(thousand|million|billion|trillion)?\s*{unit}", sentence, re.I):
        num, scale, u = m.group(1), m.group(2), (m.group(3) or "")
        if dim == "count" and not scale and not u and len(num.replace(",", "").split(".")[0]) < 5:
            continue  # "3 people" isn't a population; "1,428,000,000" or "1.4 billion" is
        if dim == "years" and not u:
            continue
        key = u.lower().strip()
        if dim == "temp":
            key = "c" if "c" in key.lower() and "f" not in key.lower() else ("f" if "f" in key.lower() else "k")
        out.append((_value(num, scale), UNIT_NAME.get(key, key), m.group(0)))
    return out


def find_quantity(attr: str, entity: str, allow_web: bool = True) -> dict | None:
    """'height', 'mount everest' → {value, unit, sentence, title, url, origin, confidence} or None."""
    from ..library import answer, index, web
    attr_pat, dim = ATTRS[attr]
    docs = []
    for t in answer._title_variants(entity):
        d = index.doc_by_title(t)
        if d:
            docs.append(d)
            break
    if not docs:
        d = answer._by_surname(entity)
        if d:
            docs.append(d)
    best = _scan(docs, attr_pat, dim, entity, f"{attr} of {entity}")
    if best and best["confidence"] >= 0.7:
        return best
    if best and best["confidence"] < 0.6:
        best = None
    if allow_web and web.enabled():
        pages = web.lookup(f"{attr} of {entity}", f"{entity} {attr}")
        wdocs = [d for p in pages for d in [index.doc_by_title(p["title"], "web-wikipedia")] if d]
        online = _scan(wdocs, attr_pat, dim, entity, f"{attr} of {entity}")
        if online and (not best or online["confidence"] > best["confidence"]):
            best = online
    return best


def _scan(docs, attr_pat: str, dim: str, entity: str, query: str) -> dict | None:
    from ..library import answer, index
    rows = []
    with index.session() as c:
        for d in docs:
            rows += [(d, r["text"], True) for r in c.execute("SELECT text FROM passages WHERE doc_id = ? ORDER BY ord LIMIT 80", (d["id"],))]
    for r in index.search(query, limit=15):
        rows.append((r, r["text"], False))
    ent_words = set(answer._terms(entity))
    cands = []
    for doc, text, own in rows:
        for s in answer._sentences(text):
            if not re.search(rf"\b(?:{attr_pat})", s, re.I):
                continue
            qs = _quantities(s, dim)
            if not qs:
                continue
            mentions = bool(ent_words & set(answer._terms(s)))
            if not own and not mentions:
                continue  # a number about something else ("population of atlantis" must not borrow India's)
            score = (0.45 if own else 0.0) + (0.25 if mentions else 0.0) + 0.2 + (0.05 if own and text is rows[0][1] else 0)
            if re.search(r"\b(?:about|around|approximately|roughly|estimated|over|nearly)\b", s, re.I):
                score += 0.02
            cands.append((score, qs[0], s, doc))
    if not cands:
        return None
    cands.sort(key=lambda c: -c[0])
    score, (value, unit, matched), s, doc = cands[0]
    return {"value": value, "unit": unit, "matched": matched, "sentence": s, "title": doc["title"], "url": doc["url"],
            "origin": answer._origin(doc["source"]), "confidence": round(min(0.92, 0.3 + score), 2)}


# ---------------------------------------------------------------- chains: facts feeding maths

FACT = re.compile(r"(?:the |a |an )?(population|height|length|depth|distance|diameter|area|speed|mass|weight|temperature|"
                  r"boiling point|melting point|age) of (?:the |a |an )?([a-z][a-z .'-]*?)(?=\s+(?:divided by|times|plus|minus|"
                  r"multiplied by|over|in|into|to|as|and|or|squared|cubed|is|was|compared)\b|\s*[*/+^\-]|\s*[?,.]|$)")
OPS = re.compile(r"[*/+^]|\s-\s|\b(?:divided by|times|plus|minus|multiplied by|over|squared|cubed|percent of|% of|half of|"
                 r"double|twice)\b|\bin (?:feet|ft|miles|meters|metres|km|kilometers|kilometres|cm|kg|pounds|lb|mph|km/h|"
                 r"fahrenheit|celsius|kelvin|square miles|square kilomet(?:er|re)s|km2|acres|hectares|square feet)\b")
CONVERSION = re.compile(r"\b(?:in|to|into)\s+(?:feet|ft|miles|meters|metres|km|kilometers|kilometres|cm|kg|pounds|lb|mph|"
                        r"km/h|fahrenheit|celsius|kelvin|square miles|square kilomet(?:er|re)s|km2|acres|hectares|square feet)\s*$")


def _fmt_q(value, unit: str) -> str:
    v = sp.nsimplify(value)
    s = f"{int(v):,}" if v.is_Integer else f"{float(v):,.6g}"
    return f"{s} {unit}".strip()


def _plain(value) -> str:
    v = sp.nsimplify(value)
    return str(int(v)) if v.is_Integer else repr(float(v))


def chain(text: str) -> "reasoning.Solution | None":
    """Questions that need a fact from the library and then maths."""
    t = text.lower().strip().rstrip("?!. ")
    sol = _years_ago(t) or _compare(t)
    if sol:
        return sol
    facts = list(FACT.finditer(t))
    if not facts or not OPS.search(t):
        return None
    steps, rewritten, conf, sources, carry_unit = [], t, 0.95, [], ""
    for i, m in enumerate(facts, 1):
        q = find_quantity(m.group(1), m.group(2).strip())
        if not q:
            return reasoning.Solution("chain", t, f"I couldn't find the {m.group(1)} of {m.group(2).strip()} in my library.",
                                      ok=False, confidence=0.6)
        conf = min(conf, q["confidence"])
        steps.append(f"[library] {m.group(1)} of {m.group(2).strip()} = {_fmt_q(q['value'], q['unit'])}   "
                     f"(“{q['matched']}”, {q['title']} · {q['origin']})")
        sources.append(q)
        unit = q["unit"] if q["unit"] not in ("people", "inhabitants", "residents", "citizens", "persons", "") else ""
        keep = unit and CONVERSION.search(t)  # "… in feet": the unit is needed; for arithmetic it's carried separately
        rewritten = rewritten.replace(m.group(0), f"{_plain(q['value'])}{' ' + unit if keep else ''}", 1)
        carry_unit = "" if keep else unit
    rewritten = re.sub(r"^(?:what is|what's|whats|calculate|compute|find)\s+", "", rewritten)
    sol = reasoning.solve_text(rewritten)
    if not sol or not sol.ok:
        # "8848 m in feet" style: try without the unit on the left for pure arithmetic
        bare = re.sub(r"(\d)\s+(?:km|m|mile|ft|cm|kg|tonne|lb|km/h|mph|m/s|c|f|k)\b(?!\s*(?:in|to)\b)", r"\1", rewritten)
        sol = reasoning.solve_text(bare)
        rewritten = bare
    if not sol or not sol.ok:
        return reasoning.Solution("chain", t, f"I found the facts but couldn't compute '{rewritten}'.", steps, ok=False, confidence=0.6)
    answer_text = sol.answer
    if len(facts) == 1 and carry_unit and re.search(r"\b(?:times|divided by|over|multiplied by|half of|double|twice)\b|[*/]", t):
        answer_text = f"{sol.answer} {carry_unit}"  # scaling a quantity keeps its unit
    steps.append(f"[maths] {rewritten} → {answer_text}")
    steps += [f"  {s}" for s in sol.steps[:6]]
    return reasoning.Solution("chain", t, answer_text, steps,
                              "the facts come from the sources above; the arithmetic is exact" + (f" · {sol.check}" if sol.check else ""),
                              confidence=round(conf, 2))


EVENT = r"(born|die|died|start|started|begin|began|end|ended|happen|happened|founded|built|invented|discovered|written|published|signed)"


def _years_ago(t: str):
    m = (re.search(rf"how (?:many years ago|long ago) (?:was|did|were) (?:the )?(.+?) {EVENT}$", t)
         or re.search(rf"how many years (?:has it been )?since (?:the )?(.+?) (?:was |were )?{EVENT}$", t))
    old = re.search(r"how old (?:would|will|is) (?:the )?(.+?) (?:be )?(?:now|today|this year)$", t)
    if not m and not old:
        return None
    from ..library import answer
    subject, event = (m.group(1), m.group(2)) if m else (old.group(1), "born")
    verb = "did" if event in ("start", "begin", "end", "happen", "die") else "was"
    a = answer.ask(f"when {verb} {subject} {event}")
    years = [int(y) for y in re.findall(r"(?<!\d)(1\d{3}|20\d{2})(?!\d)", a.text)]
    if a.decision == "unknown" or not years:
        return reasoning.Solution("chain", t, f"I couldn't find when {subject} {event}.", ok=False, confidence=0.6)
    year = years[-1] if event in ("die", "died", "end", "ended") and len(years) > 1 else years[0]
    now = datetime.date.today().year
    diff = now - year
    label = "would be" if old else "ago"
    steps = [f"[library] {subject} {event}: {year}   (“{a.text[:90]}…”, {a.title} · {a.origin})",
             f"[maths] {now} − {year} = {diff}"]
    if old and len(years) > 1:
        steps.append(f"(they died in {years[1]}, at about {years[1] - year})")
    ans = f"{diff} years {label}" if not old else f"about {diff} years old (born {year})"
    return reasoning.Solution("chain", t, ans, steps, f"this year is {now} (your computer's clock)", confidence=round(min(a.confidence, 0.9), 2))


BIGGER = {"bigger": "area", "larger": "area", "greater": None, "higher": "height", "taller": "height", "longer": "length",
          "deeper": "depth", "heavier": "mass", "hotter": "temperature", "faster": "speed", "more populous": "population",
          "smaller": "area", "shorter": "length", "lower": "height", "lighter": "mass", "colder": "temperature",
          "slower": "speed", "less populous": "population", "older": "age"}
LESS = {"smaller", "shorter", "lower", "lighter", "colder", "slower", "less populous"}


def _compare(t: str):
    m = re.search(r"(?:which|what|who) (?:is|has|was|are) (?:the )?(more populous|less populous|bigger|larger|greater|higher|"
                  r"taller|longer|deeper|heavier|hotter|faster|smaller|shorter|lower|lighter|colder|slower)\b[,:]?\s*"
                  r"(?:between )?(.+?)\s+(?:or|and|vs\.?|versus)\s+(.+)$", t)
    if not m:
        return None
    adj, a_txt, b_txt = m.group(1), m.group(2).strip(), m.group(3).strip()
    fa = FACT.fullmatch(a_txt) or re.fullmatch(r"(?:the )?(population|height|length|area|depth|speed|mass) of (?:the )?(.+)", a_txt)
    attr = fa.group(1) if fa else BIGGER.get(adj)
    if not attr:
        return None
    ent_a = fa.group(2) if fa else re.sub(r"^the ", "", a_txt)
    fb = re.fullmatch(r"(?:the )?(?:population|height|length|area|depth|speed|mass) of (?:the )?(.+)", b_txt)
    ent_b = fb.group(1) if fb else re.sub(r"^the ", "", b_txt)
    qa, qb = find_quantity(attr, ent_a), find_quantity(attr, ent_b)
    if not qa or not qb:
        missing = ent_a if not qa else ent_b
        return reasoning.Solution("chain", t, f"I couldn't find the {attr} of {missing}.", ok=False, confidence=0.6)
    va, vb = _to_common(qa), _to_common(qb)
    if va is None or vb is None:
        return reasoning.Solution("chain", t, f"I found both but in units I can't compare ({qa['unit']} vs {qb['unit']}).",
                                  ok=False, confidence=0.6)
    a_wins = (va < vb) if adj in LESS else (va > vb)
    winner, loser = (ent_a, ent_b) if a_wins else (ent_b, ent_a)
    ratio = (max(va, vb) / min(va, vb)) if min(va, vb) > 0 else None
    steps = [f"[library] {attr} of {ent_a} = {_fmt_q(qa['value'], qa['unit'])}   ({qa['title']} · {qa['origin']})",
             f"[library] {attr} of {ent_b} = {_fmt_q(qb['value'], qb['unit'])}   ({qb['title']} · {qb['origin']})",
             f"[maths] compare: {_fmt_q(qa['value'], qa['unit'])} {'>' if va > vb else '<' if va < vb else '='} {_fmt_q(qb['value'], qb['unit'])}"]
    if ratio and ratio != 1:
        steps.append(f"[maths] ratio ≈ {float(ratio):.3g}×")
    return reasoning.Solution("chain", t, f"{winner.title()} ({adj} than {loser.title()})", steps,
                              "both figures quoted from their sources above", confidence=round(min(qa["confidence"], qb["confidence"]), 2))


TO_BASE = {"km": 1000, "m": 1, "cm": sp.Rational(1, 100), "mile": sp.Rational("1609.344"), "ft": sp.Rational("0.3048"),
           "kg": 1, "tonne": 1000, "lb": sp.Rational("0.45359237"), "g": sp.Rational(1, 1000), "km/h": sp.Rational(5, 18),
           "mph": sp.Rational("0.44704"), "m/s": 1, "km/s": 1000}


def _to_common(q: dict):
    u = q["unit"]
    if u in TO_BASE:
        return q["value"] * TO_BASE[u]
    if u in ("", "people", "inhabitants", "residents", "citizens", "persons", "years", "year", "c", "f", "k"):
        return q["value"]
    if u.startswith(("km2", "km²", "square kilomet", "sq km", "sq. km")):
        return q["value"]
    if u.startswith(("square mile", "sq mi", "sq. mi")):
        return q["value"] * sp.Rational("2.589988")
    return None


# ---------------------------------------------------------------- blending sources for one question

DEF_TERM = re.compile(r"^(?:what(?: is| are)|what's|whats|define|definition of|meaning of|what does|who is|who was|explain|"
                      r"tell me about)\s+(?:a |an |the )?([a-z][a-z' -]{1,40}?)(?:\s+mean|\s+means)?\??$")


def blend(text: str, main: dict, main_kind: str) -> list[dict]:
    """Other streams' answers to the same definitional question, each {origin, title, text, url}."""
    m = DEF_TERM.match(text.lower().strip())
    if not m:
        return []
    term = re.sub(r"\s+(?:number|numbers)$", " number", m.group(1).strip())
    out = []
    try:
        from ..library import answer, index
    except ImportError:
        return out
    if main_kind != "knowledge":
        from . import knowledge
        k = knowledge.answer(f"what is {term}")
        if k and k["kind"] == "definition":
            out.append({"origin": "Kepler knowledge base", "title": k["title"], "text": k["text"], "url": ""})
    if index.exists():
        if not (main_kind == "lookup" and main.get("kind") == "word"):
            w = answer.define_word(f"define {term}")
            if w and w.decision == "answer":
                first = w.text.split("\n")[0]
                out.append({"origin": "Open English WordNet", "title": w.title, "text": first, "url": ""})
        if not (main_kind == "lookup" and main.get("kind") in ("definition", "fact")):
            a = answer._article(f"what is {term}", term, "what")
            if a:
                out.append({"origin": a.origin, "title": a.title, "text": a.text, "url": a.url})
    # keep only sources that are about the same thing (some shared words with the main answer)
    return [o for o in out if agreement(main.get("text", ""), [o], ignore=term) >= 0.1]


def agreement(main_text: str, others: list[dict], ignore: str = "") -> float:
    """How much the other sources agree with the main answer (shared content words besides the term itself), 0–1."""
    from ..library.answer import _stem, _terms
    if not others:
        return 0.0
    skip = {_stem(w) for w in _terms(ignore)}
    base = {_stem(w) for w in _terms(main_text)} - skip
    scores = []
    for o in others:
        words = {_stem(w) for w in _terms(o["text"])} - skip
        scores.append(len(base & words) / max(1, min(len(base), len(words))))
    return round(sum(scores) / len(scores), 2)
