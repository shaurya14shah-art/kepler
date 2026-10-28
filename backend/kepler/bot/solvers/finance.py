"""Personal finance and business maths in plain English, answered with worked steps and a check.

Compound interest (any compounding, continuous too), present value, doubling time (exact and the rule of 72), loan and
mortgage payments, total interest, affordability, payoff time, savings plans (the deposit a goal needs, the future value
of regular deposits), simple interest (days on a 365-day year, months), effective annual rate, inflation and real
returns, depreciation, profit/loss and markup, discount and tax chains, successive percentage changes, tips split
between people, break-even, gross/operating/net margins, progressive tax brackets, geometric average return, ROI and
hourly <-> annual pay. Amounts may be written $5,000, 250k, 1.2m or ten thousand; chatter around the problem
("quick one:", "pls", "4 sig figs", "show me the steps") is ignored.

Exact decimal arithmetic (50 digits, half-up rounding to the cent), deterministic, no network. Returns None for anything
that is not one of these problems, Kepler commands ("set sensitivity to 80%") and definitions ("what is APR") included.
"""
import math
import re
from decimal import ROUND_HALF_UP, Decimal as D, localcontext
from fractions import Fraction

from ..fields import fmt as _fmt4
from ..reasoning import Solution

ONE, ZERO, HUNDRED = D(1), D(0), D(100)
INF = D("Infinity")

# ---------------------------------------------------------------- reading the message

TRANS = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", "−": "-", " ": " ", "×": "x"})

FORMAT_SIG = re.compile(r"(?:\b(?:to|in|with|at|give (?:it|me|the answer) (?:to|in))\s+)?\b(\d+)\s*(?:sig(?:nificant)?\.?\s*"
                        r"(?:fig(?:ure)?s?|digits?)\b|s\.?f\.?(?![a-z])|sig\b)")
FORMAT_DP = re.compile(r"(?:\b(?:to|in|rounded to|round to)\s+)?\b(\d+)\s*(?:decimal places?|decimals?|dp|d\.p\.)(?![a-z])")
FORMAT_NEAREST = re.compile(r"(?:\b(?:to|rounded to|round(?: it)? to)\s+)?\bthe nearest (cent|penny|dollar|euro|pound|rupee|"
                            r"whole (?:number|dollar)|integer|tenth|hundredth|thousandth|percent)\b")
FORMAT_FRAC = re.compile(r"\b(?:give (?:it|the answer|me the answer) )?(?:as an? |in )?(?:exact(?:ly)?(?: form| value| answer)?"
                         r"(?: if (?:you|u) can)?|(?:simplified |simplest )?fraction(?:al)?(?: form)?|simplest form)\b")
CHATTER = re.compile(
    r"\bshow (?:me )?(?:the |all |your |all the )?(?:steps?|working|work(?:ings?)?|method|calculations?|maths?)\b|"
    r"\bstep[- ]by[- ]step\b|\bwith (?:the )?(?:steps|working)\b|\bwork(?:ing)? shown\b|"
    r"\bfor (?:my|a|our) (?:homework|class|assignment|exam|test|quiz|course|worksheet|[a-z]+ class)\b|\bhomework\b|"
    r"\b(?:pls|plz|please|thanks?(?: you| so much)?|thx|ty)\b|\bquick (?:one|q|question)\b|\breal quick\b|\bquickly\b|"
    r"\bhelp me(?: out)?(?: with)?\b|\bi need help(?: with)?\b|\bneed help(?: with)?\b|\bany idea\b|\blol\b|\bhaha\b|"
    r"\bcan (?:you|u) (?:help(?: me)?(?: with)?|tell me|work out|figure out|calculate|compute|solve|find)\b|"
    r"\b(?:could|would) (?:you|u)\b|\bhey\b|\bhi\b|\bhello\b|\bkepler\b|\bum+\b|\buh+\b")
REMARK = re.compile(r"^\s*(?:i\b|i'm\b|im\b|my\b|we\b|we're\b|this\b|it's\b|its\b|that's\b|confused\b|not sure\b|idk\b|"
                    r"lol\b|thanks?\b|thx\b|cheers\b|been\b|stuck\b|always\b|never\b|ugh\b|also not\b|no rush\b|"
                    r"(?:just )?(?:checking|wondering)\b)")

UNIT_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
              "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
              "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
TENS_WORDS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
              "ninety": 90}
SCALE_WORDS = {"thousand": 1000, "million": 10 ** 6, "billion": 10 ** 9}
_NW = "|".join(list(UNIT_WORDS) + list(TENS_WORDS) + ["hundred"] + list(SCALE_WORDS))
NUMBER_WORDS = re.compile(rf"\b(?:(?:{_NW})|a(?= (?:hundred|thousand|million|billion)\b))"
                          rf"(?:(?:[ -]+|\s+and\s+(?=(?:{_NW})\b))(?:{_NW}))*\b")


def _words_to_number(phrase: str) -> str:
    words = [w for w in re.split(r"[\s-]+", phrase) if w]
    out, total, cur, last = [], 0, 0, None
    for w in words:
        if w == "and":
            continue
        if w == "a":
            cur, last = 1, "a"
        elif w in UNIT_WORDS or w in TENS_WORDS:
            v = UNIT_WORDS.get(w, TENS_WORDS.get(w))
            if last in UNIT_WORDS or (last in TENS_WORDS and (w in TENS_WORDS or v >= 10)):
                out.append(total + cur)  # "five six": two numbers
                total = cur = 0
            cur += v
            last = w
        elif w == "hundred":
            cur, last = (cur or 1) * 100, w
        else:
            total, cur, last = total + (cur or 1) * SCALE_WORDS[w], 0, w
    out.append(total + cur)
    return " ".join(str(n) for n in out)


def _rewrite(t: str) -> str:
    t = re.sub(r"\b40[13]\s?\(?[kb]\)?|\b457\s?\(?b\)?", " retirement account ", t)
    t = re.sub(r"\bp\.\s?a\.?(?![a-z])|\bp/a\b", " per annum ", t)
    t = re.sub(r"\ba\.p\.r\.?", "apr", t)
    t = re.sub(r"\ba\.p\.y\.?", "apy", t)
    t = re.sub(r"\bper cent\b", "percent", t)
    t = re.sub(r"/\s?(?:yr|year|annum)\b", " per year ", t)
    t = re.sub(r"/\s?(?:mo|mth|month)\b", " per month ", t)
    t = re.sub(r"/\s?(?:hr|hour|h)\b", " per hour ", t)
    t = re.sub(r"/\s?(?:wk|week)\b", " per week ", t)
    t = re.sub(r"/\s?day\b", " per day ", t)
    t = re.sub(r"/\s?(?:unit|item|piece)\b", " per unit ", t)
    t = re.sub(r"([$€£₹¥])\s+(?=\d)", r"\1", t)
    t = NUMBER_WORDS.sub(lambda m: m.group(0) if (m.group(0) in SCALE_WORDS and re.search(r"\d\s?$", t[:m.start()]))
                         else _words_to_number(m.group(0)), t)
    t = re.sub(r"\ba year and a half\b", "1.5 years", t)
    t = re.sub(r"\b(\d+) and a half\b", r"\1.5", t)
    t = re.sub(r"\bhalf an? (year|month)\b", r"0.5 \1", t)
    t = re.sub(r"\b(\d+(?:\.\d+)?) decades?\b", lambda m: f"{D(m.group(1)) * 10} years", t)
    t = re.sub(r"\ba decade\b", "10 years", t)
    t = re.sub(r"\b(in|for|after|over|within|of|about) (?:a|one) (year|month|week|day|quarter)\b", r"\1 1 \2", t)
    t = re.sub(r"\btwice\b", "2 times", t)
    return t


# ---------------------------------------------------------------- numbers in the text

MULT = {"k": 10 ** 3, "thousand": 10 ** 3, "grand": 10 ** 3, "m": 10 ** 6, "mm": 10 ** 6, "mn": 10 ** 6, "mil": 10 ** 6,
        "million": 10 ** 6, "b": 10 ** 9, "bn": 10 ** 9, "billion": 10 ** 9, "lakh": 10 ** 5, "lakhs": 10 ** 5,
        "crore": 10 ** 7, "crores": 10 ** 7}
CURRENCY = {"$": "$", "us$": "$", "usd": "$", "€": "€", "eur": "€", "£": "£", "gbp": "£", "₹": "₹", "rs": "₹", "rs.": "₹",
            "inr": "₹", "¥": "¥", "dollar": "$", "dollars": "$", "bucks": "$", "euro": "€", "euros": "€", "pound": "£",
            "pounds": "£", "quid": "£", "rupee": "₹", "rupees": "₹", "yen": "¥"}
NUMTOK = re.compile(
    r"(?<![\w.])(?P<sign>[-+](?=(?:[$€£₹¥]|us\$)?\.?\d))?(?P<cur>(?:[$€£₹¥]|us\$|(?:rs\.?|inr|usd|eur|gbp)\s?))?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)"
    r"(?P<mult>\s?(?:thousand|grand|million|billion|lakhs?|crores?)\b|(?:k|mm|mn|mil|m|bn|b)(?![a-z0-9]))?")
SUFFIX = [
    ("pct", re.compile(r"\s?(?:%|percent\b|pct\b|percentage points?\b)")),
    ("year", re.compile(r"\s?-?\s?(?:years?|yrs?|yr)\b(?!\s?-?\s?olds?)")),
    ("month", re.compile(r"\s?-?\s?(?:months?|mos?|mths?)\b")),
    ("week", re.compile(r"\s?-?\s?(?:weeks?|wks?)\b")),
    ("day", re.compile(r"\s?-?\s?days?\b")),
    ("hour", re.compile(r"\s?-?\s?(?:hours?|hrs?|h)\b")),
    ("quarter", re.compile(r"\s?-?\s?quarters?\b")),
    ("cents", re.compile(r"\s?cents?\b")),
    ("money", re.compile(r"\s?(?:dollars?|bucks|usd|euros?|eur|pounds?|gbp|quid|rupees?|inr|rs\b|yen)\b")),
    ("count", re.compile(r"\s?(?:units?|items?|people|persons?|friends|ways|guests|diners|of us|widgets|products|pieces|"
                         r"pcs|shares|customers|tickets|members|roommates|room-mates|employees|adults|kids|children|"
                         r"players|gadgets|boxes|bags|meals|cups|guys|colleagues|coworkers|co-workers|others)\b")),
]
INDEX_BEFORE = re.compile(r"(?:\byears?|\byr|\bmonth|\bweek|\bday|\bquarter|#|\bno\.|\bnumber|\brule of|\btop|\blevel|"
                          r"\bgrade|\btier|\bbracket|\boption|\bstep|\bpart|\bphase|\bq|\bchapter|\bquestion|\bproblem)\s*$")
CAL_BEFORE = re.compile(r"\b(?:in|from|since|to|by|of|until|till|between|and|back in|during|year)\s*$")
PER_AFTER = re.compile(r"^\s?(?:(?:at the (?:end|start|beginning) of\s)?(?:/|per|an?|each|every)\s?(month|year|annum|week|hour|day|quarter|unit|person|head|item|"
                       r"piece|share)\b|(monthly|yearly|annually|weekly|hourly|daily|quarterly|biweekly|fortnightly)\b)")
PER_BEFORE = re.compile(r"\b(monthly|yearly|annual|weekly|hourly|daily|quarterly|biweekly|fortnightly)\s+(?:[a-z]+\s+){0,2}"
                        r"(?:of|is|=|:|at)?\s*$")
PER_NAME = {"annum": "year", "monthly": "month", "yearly": "year", "annually": "year", "annual": "year",
            "weekly": "week", "hourly": "hour", "daily": "day", "quarterly": "quarter", "biweekly": "biweek",
            "fortnightly": "biweek", "head": "person", "item": "unit", "piece": "unit", "share": "unit"}
# clause boundaries: a keyword describes the number in its own clause
BOUND = re.compile(r"[,;!?()]|\.(?!\d)|\band\b|\bbut\b|\bwhile\b|\bwhereas\b|\bthen\b|\balso\b")


class Tok:
    __slots__ = ("v", "kind", "cur", "start", "end", "per", "pre", "post", "neg", "s", "raw_post")

    def __repr__(self):
        return f"Tok({self.kind} {self.v} per={self.per})"


class P:
    """The message, read: its numbers with what they are, the currency and what format the answer should take."""

    def __init__(self, text: str, t: str, toks: list, cur: str, sig, dp, frac: bool):
        self.text, self.t, self.toks, self.cur, self.sig, self.dp, self.frac = text, t, toks, cur, sig, dp, frac

    def kind(self, *kinds) -> list:
        return [k for k in self.toks if k.kind in kinds]

    @property
    def pcts(self) -> list:
        return self.kind("pct")

    @property
    def monies(self) -> list:
        return self.kind("money", "bare")

    def has(self, rx: str) -> bool:
        return re.search(rx, self.t) is not None

    # ---- formatting
    def m(self, x) -> str:
        """Money in the working: 2 decimals, the user's currency."""
        q = D(x).quantize(D("0.01"), ROUND_HALF_UP)
        return f"{'-' if q < 0 else ''}{self.cur}{abs(q):,.2f}"

    def ma(self, x) -> str:
        """Money in the answer: 2 decimals unless the user asked for sig figs or decimal places."""
        x = D(x)
        if self.sig:
            return f"{'-' if x < 0 else ''}{self.cur}{_sig(abs(x), self.sig)}"
        if self.dp is not None:
            q = x.quantize(D(1).scaleb(-self.dp), ROUND_HALF_UP)
            return f"{'-' if q < 0 else ''}{self.cur}{abs(q):,.{self.dp}f}"
        return self.m(x)

    def na(self, x) -> str:
        """A plain number in the answer: 4 significant figures unless asked otherwise."""
        x = D(x)
        if self.sig:
            return _sig(x, self.sig)
        if self.dp is not None:
            return f"{x.quantize(D(1).scaleb(-self.dp), ROUND_HALF_UP):,.{self.dp}f}"
        return _n(x)

    def pa(self, x) -> str:
        """A rate in the answer as a percentage (0.1956 → 19.56%), with the exact fraction when asked."""
        s = self.na(D(x) * HUNDRED) + "%"
        if self.frac:
            fr = Fraction(str(D(x))).limit_denominator(10 ** 6)
            if D(fr.numerator) / D(fr.denominator) == D(x) and fr.denominator != 1:
                s += f" (= {fr.numerator}/{fr.denominator})"
        return s


def _sig(x: D, n: int) -> str:
    if x == 0:
        return "0"
    e = math.floor(math.log10(abs(float(x))))
    digits = n - 1 - e
    q = x.quantize(D(1).scaleb(-digits), ROUND_HALF_UP) if digits > 0 else x.quantize(D(1).scaleb(-digits), ROUND_HALF_UP)
    return f"{q:,.{max(digits, 0)}f}"


def _n(x) -> str:
    """4 significant figures (fields.fmt), from a Decimal."""
    return _fmt4(float(x))


def _q(x, nd: int = 6) -> str:
    """A number in the working: whole numbers as they are, otherwise up to nd decimals, no trailing zeros."""
    x = D(x)
    if x == x.to_integral_value():
        return f"{int(x):,}"
    s = f"{x.quantize(D(1).scaleb(-nd), ROUND_HALF_UP):,.{nd}f}".rstrip("0").rstrip(".")
    return s if s not in ("0", "-0") else f"{float(x):.3g}"


def _ds(x) -> str:
    """A Decimal as plain digits: 0.065, 1.08, 360."""
    s = format(D(x).normalize(), "f")
    return s


def _pct(x) -> str:
    """A rate in the working: 0.065 → 6.5%."""
    return f"{_ds(D(x) * HUNDRED)}%" if (D(x) * HUNDRED).as_tuple().exponent >= -6 else f"{_q(D(x) * HUNDRED)}%"


def _dec(s: str) -> D:
    return D(s.replace(",", ""))


def _clean(text: str):
    t = " " + text.lower().translate(TRANS) + " "
    t = re.sub(r"\s+", " ", t)
    sig = dp = None
    frac = False
    m = FORMAT_SIG.search(t)
    if m:
        sig = max(1, min(int(m.group(1)), 12))
        t = t[:m.start()] + " " + t[m.end():]
    m = FORMAT_DP.search(t)
    if m:
        dp = min(int(m.group(1)), 10)
        t = t[:m.start()] + " " + t[m.end():]
    m = FORMAT_NEAREST.search(t)
    if m:
        dp = {"tenth": 1, "hundredth": 2, "thousandth": 3, "cent": 2, "penny": 2}.get(m.group(1), 0)
        t = t[:m.start()] + " " + t[m.end():]
    m = FORMAT_FRAC.search(t)
    if m:
        frac = True
        t = t[:m.start()] + " " + t[m.end():]
    t = CHATTER.sub(" ", t)
    # a remark after the question ("? i keep mixing up the product rule") is not part of the problem
    parts = t.split("?")
    if len(parts) > 1:
        keep = [parts[0]]
        for seg in parts[1:]:
            if seg.strip() and not re.search(r"\d", seg) and REMARK.match(seg):
                break
            keep.append(seg)
        t = "?".join(keep)
    t = re.sub(r"^[\s,:;.!\-]+", " ", t)
    return t, sig, dp, frac


def _tokens(t: str) -> list:
    toks = []
    for m in NUMTOK.finditer(t):
        k = Tok()
        k.start, k.end = m.start(), m.end()
        k.s = m.group("num")
        v = _dec(k.s)
        mult = (m.group("mult") or "").strip()
        if mult:
            v *= MULT[mult]
        k.neg = m.group("sign") == "-"
        cur = (m.group("cur") or "").strip()
        k.cur = CURRENCY.get(cur, "") if cur else ""
        k.kind = "bare"
        after = t[m.end():m.end() + 40]
        for kind, rx in SUFFIX:
            s = rx.match(after)
            if s:
                if kind == "count" and (k.cur or mult):
                    break  # "$60 item": money, not a count
                k.kind = kind
                k.end = m.end() + s.end()
                if kind == "money":
                    word = s.group(0).strip()
                    k.cur = k.cur or CURRENCY.get(word, "")
                break
        if k.kind == "cents":
            v, k.kind = v / 100, "money"
        if k.kind == "pct":
            v = v / HUNDRED
        if k.kind == "bare":
            if k.cur or mult:
                k.kind = "money"
            elif INDEX_BEFORE.search(t[max(0, m.start() - 14):m.start()]):
                k.kind = "index"
            elif "." not in k.s and "," not in k.s and 1900 <= v <= 2100 and CAL_BEFORE.search(t[max(0, m.start() - 10):m.start()]):
                k.kind = "cal"
        if k.neg:
            v = -v
        k.v = v
        k.per = None
        pm = PER_AFTER.match(after)
        if pm:
            k.per = PER_NAME.get(pm.group(1) or pm.group(2), pm.group(1) or pm.group(2))
        else:
            bm = PER_BEFORE.search(t[max(0, m.start() - 40):m.start()])
            if bm and k.kind in ("money", "bare") and not re.search(
                    r"\b(?:to|reach|hit|goal|target|accumulate|have|get)\b", bm.group(0)):
                k.per = PER_NAME.get(bm.group(1), bm.group(1))
        toks.append(k)
    for i, k in enumerate(toks):
        prev_end = toks[i - 1].end if i else 0
        nxt = toks[i + 1].start if i + 1 < len(toks) else len(t)
        k.pre = BOUND.split(t[prev_end:k.start])[-1][-48:]
        k.raw_post = t[k.end:nxt]
        k.post = BOUND.split(k.raw_post)[0][:40]
    return toks


COMMAND = re.compile(r"^\s*(?:why\b|chart\b|plot\b|graph\b|mute\b|unmute\b|silence\b|snooze\b|connect\b|disconnect\b|switch\b|"
                     r"mark\b(?!\s*(?:it|them|the price|up|down)\b)|break down\b|set\b(?! aside)|list\b|watch\b|alert\b|"
                     r"is\s+\w+\s+(?:ok|okay|fine|healthy|normal|up|down)\b)")
NOT_FINANCE = re.compile(r"\b(?:incidents?|false alarm|sensitivity|anomal\w*|datadog|grafana|prometheus|dashboard|"
                         r"latency|p9[59]|uptime|threshold|alerts?)\b|\b[a-z]+_[a-z_]+\b")
DEFINITION = re.compile(r"^\s*(?:what|whats|what's|who|define|meaning of)\b(?:'s| is| are| was| were| does| do)?\b")


def _parse(text: str) -> P | None:
    t, sig, dp, frac = _clean(text)
    if not re.search(r"\d", t) and not NUMBER_WORDS.search(t):
        return None
    if COMMAND.match(t) or NOT_FINANCE.search(t):
        return None
    t = _rewrite(t)
    toks = _tokens(t)
    nums = [k for k in toks if k.kind not in ("index",)]
    if not nums:
        return None
    if DEFINITION.match(t) and len(nums) < 2 and not re.search(r"\b(?:compounded|apr|nominal|apy)\b", t):
        return None
    cur = next((k.cur for k in toks if k.cur), "")
    return P(text, t, toks, cur, sig, dp, frac)


# ---------------------------------------------------------------- labels: what a number is, from the words around it

def _label(k: Tok, table) -> str | None:
    """The label whose keyword sits nearest the number in its own clause; 'strong' keywords win wherever they are."""
    best = None
    near = len(re.sub(r"(?:\s|\b(?:for|at|of|is|was|were|it|them)\b|[=:])+$", "", k.pre))
    for label, rx, strong in table:
        for m in re.finditer(rx, k.pre):
            d = max(0, near - m.end())
            cand = (0 if strong else 1, d, label)
            best = cand if best is None or cand < best else best
        m = re.search(rx, k.post)
        if m:
            cand = (0 if strong else 1, m.start() + 0.5, label)
            best = cand if best is None or cand < best else best
    return best[2] if best else None


PCT_POST = [
    ("down", r"^\s*(?:down\b(?! to)|deposit\b|down payment)"),
    ("off", r"^\s*(?:off\b|discount|markdown|reduction in price|cheaper|sale\b|coupon)"),
    ("tip", r"^\s*(?:tip|gratuity)"),
    ("service", r"^\s*service"),
    ("tax", r"^\s*(?:[a-z]+\s+)?(?:tax|vat|gst|hst|pst)\b"),
    ("inflation", r"^\s*(?:[a-z]+\s+)?inflation"),
    ("markup", r"^\s*mark-?\s?up"),
    ("margin", r"^\s*(?:[a-z]+\s+)?margin"),
    ("profit", r"^\s*(?:profit|gain)\b"),
    ("loss", r"^\s*loss\b"),
    ("up", r"^\s*(?:increase|rise|raise|hike|jump|growth|higher|more\b|up\b)"),
    ("down_chg", r"^\s*(?:decrease|decline|drop|fall|cut|lower|less\b|reduction|depreciation|down\b)"),
    ("rate", r"^\s*(?:apr|apy|interest|a year|per year|annual|per annum|compound|rate|nominal|fixed|yearly|return|"
             r"per month|a month|monthly|p\.?a\b|ear\b|effective|yield)"),
]
PCT_PRE = [
    ("down", r"(?:down payment|down-payment|put(?:ting)? down|deposit)\s*(?:of|is|=|:)?\s*(?:an?\s+)?(?:about\s+)?$"),
    ("off", r"(?:discount(?:ed)?|marked down|markdown|knock(?:ed|s)? off|take|taking|coupon|sale|off|rebate|"
            r"reduced(?: in price)?)\s*(?:of|by|at|is|for)?\s*(?:an?\s+)?(?:extra|additional|another|further|more)?\s*$"),
    ("tip", r"(?:tip(?:ping)?|gratuity|leave|leaving|leaves)\s*(?:of|is|at|=|:)?\s*(?:an?\s+)?$"),
    ("tax", r"(?:tax(?:es|ed)?(?: rate)?|vat|gst|hst|pst|taxed at)\s*(?:of|is|at|=|:)?\s*(?:an?\s+)?$"),
    ("inflation", r"inflation(?: rate)?\s*(?:of|is|at|=|:|averag\w*|runs?|running|was|will be|stays?|rate)?\s*(?:at\s+)?"
                  r"(?:about|around|roughly)?\s*$"),
    ("markup", r"mark(?:s|ed|ing)?[- ]?(?:it |them |[a-z]+ )?up\s*(?:by|of|at)?\s*$|markup\s*(?:of|is|=|:)?\s*(?:an?\s+)?$"),
    ("margin", r"margin\s*(?:of|is|=|:)?\s*(?:an?\s+)?$"),
    ("profit", r"(?:profit|gain)\s*(?:of|is|=|:)?\s*(?:an?\s+)?$"),
    ("loss", r"loss\s*(?:of|is|=|:)?\s*(?:an?\s+)?$"),
    ("up", r"(?:increase[sd]?|rais(?:e|es|ed)|ris(?:e|es|en)|rose|grow(?:s|n)?|grew|gain(?:s|ed)?|jump(?:s|ed)?|"
           r"climb(?:s|ed)?|\bup|hike[sd]?|appreciat\w*|soar(?:s|ed)?|boost(?:s|ed)?|plus|\+|returned|returns?|made|"
           r"earned|went up)\s*(?:by|of)?\s*(?:another|a further|an(?:other)? extra|an?)?\s*$"),
    ("down_chg", r"(?:decrease[sd]?|fall(?:s|en)?|fell|drop(?:s|ped)?|declin(?:e|es|ed)|los(?:e|es|t)|down|cut(?:s)?|"
                 r"reduc(?:e|es|ed)|slash(?:es|ed)?|depreciat\w*|shrink(?:s)?|shrank|plung(?:e|es|ed)|tumbl(?:e|es|ed)|"
                 r"sink(?:s)?|sank|dip(?:s|ped)?|minus|-)\s*(?:by|of)?\s*(?:another|a further|an?)?\s*$"),
    ("rate", r"(?:\bat|@|rate(?: of| is)?|interest(?: rate)?(?: of| is| at)?|earn(?:s|ing)?|yield(?:s|ing)?|"
             r"return(?:s|ing)?(?: of)?|apr(?: of| is)?|apy(?: of| is)?|growth(?: rate)?(?: of| is)?|charges?|pays?|"
             r"paying|offers?|offering|nominal|ear(?: of| is)?)\s*(?:an?\s+)?(?:annual\s+|nominal\s+|fixed\s+|yearly\s+)?"
             r"(?:(?:interest\s+)?rate of\s+)?$"),
]


def _role(k: Tok) -> str | None:
    """What a percentage is: a rate, a discount, tax, tip, inflation, a markup, an increase or decrease…"""
    for role, rx in PCT_POST:
        if re.search(rx, k.post):
            return role
    for role, rx in PCT_PRE:
        if re.search(rx, k.pre):
            return role
    if k.neg:
        return "down_chg"
    return None


def _rate_tok(p: P, exclude=("down", "off", "tip", "service", "tax", "inflation", "markup", "margin", "profit", "loss")):
    for k in p.pcts:
        if _role(k) not in exclude:
            return k
    return None


# ---------------------------------------------------------------- time and compounding

def _years_of(k: Tok, t: str) -> Fraction:
    v = Fraction(str(k.v))
    if k.kind == "year":
        return v
    if k.kind == "month":
        return v / 12
    if k.kind == "quarter":
        return v / 4
    if k.kind == "week":
        return v / 52
    if k.kind == "day":
        return v / (360 if re.search(r"\b360[- ]day|\bbanker'?s|\bordinary (?:simple )?interest", t) else 365)
    raise ValueError(k.kind)


TIME_KINDS = ("year", "month", "quarter", "week", "day")


def _term(p: P, skip=()) -> tuple | None:
    """The time span: (years as a Fraction, how it reads, the token). '2 years and 6 months' adds up."""
    toks = [k for k in p.toks if k.kind in TIME_KINDS and k not in skip and not k.per
            and not re.search(r"(?:hours?|days?)\s*(?:a|per|each)\s*$", k.pre)]
    toks = [k for k in toks if not re.match(r"^\s*(?:a|per|each|every|/)\s*(?:year|week|month)\b", k.raw_post)
            or k.kind == "year"]
    if not toks:
        cal = [k for k in p.toks if k.kind == "cal"]
        if len(cal) >= 2:
            yrs = Fraction(str(abs(cal[1].v - cal[0].v)))
            return (yrs, f"{_q(cal[1].v)} − {_q(cal[0].v)} = {_q(yrs)} years", cal[1]) if yrs else None
        return None
    k = toks[0]
    yrs = _years_of(k, p.t)
    words = {"year": "years", "month": "months", "quarter": "quarters", "week": "weeks", "day": "days"}[k.kind]
    desc = f"{_q(k.v)} {words}"
    i = p.toks.index(k)
    if k.kind == "year" and i + 1 < len(p.toks):
        nxt = p.toks[i + 1]
        if nxt.kind == "month" and re.fullmatch(r"\s*(?:-|,|and)?\s*", p.t[k.end:nxt.start]):
            yrs += _years_of(nxt, p.t)
            desc += f" {_q(nxt.v)} months"
    if k.kind == "day":
        desc += f" = {_q(k.v)}/{365 if yrs * 365 == Fraction(str(k.v)) else 360} year"
    elif k.kind != "year":
        desc += f" = {_q(_fd(yrs))} years"
    return yrs, desc, k


def _fd(f: Fraction) -> D:
    return D(f.numerator) / D(f.denominator)


FREQS = [
    (0, "continuously", r"continuous(?:ly)?|continual(?:ly)?|constantly|instantaneous(?:ly)?"),
    (2, "semi-annually", r"semi-?annual(?:ly)?|half-?year(?:ly)?|half-?annual(?:ly)?|bi-?annual(?:ly)?|"
                         r"2 times (?:a|per|each|every) year|every 6 months"),
    (4, "quarterly", r"quarterly|every quarter|each quarter|4 times (?:a|per) year|every 3 months"),
    (12, "monthly", r"monthly|every month|each month|per month|a month|12 times (?:a|per) year"),
    (26, "every two weeks", r"bi-?weekly|fortnightly|every 2 weeks"),
    (52, "weekly", r"weekly|every week|each week|per week|a week"),
    (365, "daily", r"daily|every day|each day|per day|a day"),
    (1, "annually", r"annual(?:ly)?|yearly|every year|each year|once (?:a|per) year|per year|a year|per annum"),
]
FREQ_NAME = {m: name for m, name, _ in FREQS}
FREQ_NAME[1] = "annually"


def _compounding(t: str) -> int | None:
    """Compounding periods a year (0 = continuous), from 'compounded quarterly', 'monthly compounding'…"""
    marks = [m for m in re.finditer(r"compound\w*", t)]
    best = None
    for c in marks:
        for m_, _, rx in FREQS:
            for f in re.finditer(rf"\b(?:{rx})\b", t):
                gap = f.start() - c.end() if f.start() >= c.end() else c.start() - f.end()
                if 0 <= gap <= 22 and not re.search(r"\b(?:deposit|payment|contribution|for|over)", t[min(c.end(), f.end()):max(c.start(), f.start())]):
                    noun = re.match(r"compounding|compounds?\b", c.group(0)) is not None
                    side = 0 if (f.start() >= c.end()) != noun else 1
                    cand = (side, gap, m_)
                    best = cand if best is None or cand < best else best
    if best:
        return best[2]
    if re.search(r"\bcontinuous(?:ly)?\b|\bcontinual(?:ly)?\b", t):
        return 0
    return None


def _period_rate(r: D, m: int, pay: int) -> tuple:
    """The interest rate per payment period, and how it reads, for nominal annual rate r compounded m times a year."""
    if m == 0:
        i = (r / pay).exp() - 1
        return i, f"e^({_ds(r)}/{pay}) − 1 = {_q(i, 8)}"
    if m == pay:
        i = r / pay
        return i, (f"{_pct(r)}/{pay} = {_ds(r)}/{pay}" if pay != 1 else f"{_pct(r)} = {_ds(r)}")
    i = (1 + r / m) ** (D(m) / D(pay)) - 1
    return i, f"(1 + {_ds(r)}/{m})^({m}/{pay}) − 1 = {_q(i, 8)}"


def _grow(r: D, m: int, yrs: Fraction) -> tuple:
    """Growth factor over yrs years at nominal r compounded m times a year (0 = continuously), and how it reads."""
    if m == 0:
        f = (r * _fd(yrs)).exp()
        return f, f"e^({_ds(r)} × {_q(_fd(yrs))})"
    n = yrs * m
    if n.denominator == 1:
        f = (1 + r / m) ** int(n)
    else:
        f = (1 + r / m) ** _fd(n)
    base = f"(1 + {_ds(r)}/{m})" if m != 1 else f"{_ds(1 + r)}"
    expo = f"{m} × {_q(_fd(yrs))}" if m != 1 else _q(_fd(yrs))
    return f, f"{base}^({expo})" if m != 1 else f"{base}^{expo}"


def _sol(p: P, kind: str, formula: str, knowns: list, sub: str, answer: str, check: str = "", extra=()) -> Solution:
    steps = [f"formula: {formula}", "known: " + ", ".join(knowns), f"substitute: {sub}", *extra, f"result: {answer}"]
    return Solution(kind, p.text, answer, steps, check=check, confidence=0.97)


def _rule(p: P, kind: str, rule: str, lines: list, answer: str, check: str = "") -> Solution:
    steps = [f"rule: {rule}", *lines, f"result: {answer}"]
    return Solution(kind, p.text, answer, steps, check=check, confidence=0.97)


# ---------------------------------------------------------------- hourly <-> annual pay

PAY_UNITS = {"hour": "an hour", "year": "a year", "month": "a month", "week": "a week", "day": "a day", "biweek": "every two weeks"}


def _h_salary(p: P) -> Solution | None:
    t = p.t
    if not p.has(r"\b(?:hours?|hourly|hrs?)\b"):
        return None
    if p.has(r"\b(?:loan|mortgage|borrow\w*|interest|invest\w*|deposit\w*|compound\w*|tip|bill|break[- ]?even|price)\b"):
        return None
    if not p.has(r"\b(?:salary|salaried|wages?|pay|paid|earn\w*|make|making|makes|income|job|annual\w*|yearly|a year|per year|"
                 r"per annum|monthly|a month|per month|weekly|a week|per week|full[- ]time|gross|hourly)\b"):
        return None
    given = None
    for k in p.monies:
        unit = k.per
        if unit is None:
            if re.search(r"(?:hourly (?:rate|wage|pay)?|an hour)\s*(?:of|is|=|:)?\s*$", k.pre):
                unit = "hour"
            elif re.search(r"(?:annual|yearly)?\s*(?:salary|income|pay)\s*(?:of|is|=|:)?\s*(?:about\s+)?$", k.pre) or \
                    re.match(r"^\s*(?:salary|a year|annual salary|per annum)", k.post):
                unit = "year"
        if unit in PAY_UNITS:
            given = (k, unit)
            break
    if not given:
        return None
    k, unit = given
    hours = D(40)
    weeks = D(52)
    h_note = "40 hours a week (full time)"
    w_note = "52 weeks a year"
    for h in p.kind("hour"):
        if h.per == "week" or re.match(r"^\s*(?:a|per|each|every)\s*week", h.raw_post):
            hours, h_note = h.v, f"{_q(h.v)} hours a week"
        elif h.per == "day" or re.match(r"^\s*(?:a|per|each|every)\s*day", h.raw_post):
            days = next((d.v for d in p.kind("day") if re.match(r"^\s*(?:a|per|each|every)\s*week", d.raw_post)), D(5))
            hours, h_note = h.v * days, f"{_q(h.v)} hours a day × {_q(days)} days = {_q(h.v * days)} hours a week"
    for w in p.kind("week"):
        if w.per == "year" or re.match(r"^\s*(?:a|per|each|every)\s*year", w.raw_post):
            weeks, w_note = w.v, f"{_q(w.v)} weeks a year"
        elif re.match(r"^\s*(?:of\s+)?(?:unpaid|off without pay)", w.raw_post):
            weeks, w_note = 52 - w.v, f"52 − {_q(w.v)} unpaid weeks = {_q(52 - w.v)} weeks a year"
    # what is asked: the other unit, named somewhere outside the given amount's own phrase
    rest = t[:k.start] + " " + t[k.end + len(k.raw_post) - len(k.raw_post.lstrip()):]
    rest = re.sub(r"\d+(?:\.\d+)?\s*(?:hours?|hrs?|days?|weeks?)\s*(?:a|per|each|every)\s*(?:week|day|year)", " ", rest)
    rest = re.sub(r"^.*?" + re.escape(t[k.start:k.end]) + r"\S*\s*(?:(?:/|per|an?|each|every)\s?\w+)?", " ", t)
    asks = []
    for u, rx in (("hour", r"\b(?:hourly|per hour|an hour|by the hour|each hour|hour rate|hours?)\b"),
                  ("year", r"\b(?:annual(?:ly)?|yearly|per year|a year|per annum|salary|year)\b"),
                  ("month", r"\b(?:monthly|per month|a month|month)\b"),
                  ("biweek", r"\b(?:bi-?weekly|every (?:2|two) weeks|fortnightly|paycheck)\b"),
                  ("week", r"\b(?:weekly|per week|a week|week)\b"),
                  ("day", r"\b(?:daily|per day|a day|day)\b")):
        mm = re.search(rx, rest)
        if mm and u != unit:
            asks.append((mm.start(), u))
    rest_nohours = re.sub(r"\d+(?:\.\d+)?\s*(?:hours?|hrs?|days?|weeks?)\s*(?:a|per|each|every)?\s*(?:week|day|year)?", " ", rest)
    asks = [(pos, u) for pos, u in asks if re.search({"hour": r"hour", "year": r"annual|year|salary|annum",
                                                       "month": r"month", "biweek": r"bi-?weekly|2 weeks|two weeks|fortnight|paycheck",
                                                       "week": r"week", "day": r"daily|day"}[u], rest_nohours)]
    if not asks:
        target = "year" if unit == "hour" else "hour"
    else:
        prefer = [u for _, u in sorted(asks)]
        target = prefer[0]
    per_year = {"hour": hours * weeks, "week": weeks, "biweek": weeks / 2, "month": D(12), "year": ONE, "day": weeks * 5}
    annual = k.v * per_year[unit]
    result = annual / per_year[target]
    hours_year = hours * weeks
    knowns = [f"pay = {p.m(k.v)} {PAY_UNITS[unit]}", h_note, w_note, f"{_q(hours_year)} working hours a year"]
    if unit == "hour":
        sub = f"annual = {_q(k.v)} × {_q(hours)} × {_q(weeks)} = {p.m(annual)}"
    else:
        sub = f"annual = {_q(k.v)} × {_q(per_year[unit])} = {p.m(annual)}" if unit != "year" else f"annual = {p.m(annual)}"
    if target != "year":
        sub += f"; {PAY_UNITS[target].split()[-1]}ly = {p.m(annual)} / {_q(per_year[target])}" if target not in ("day", "biweek") \
            else f"; per {target} = {p.m(annual)} / {_q(per_year[target])}"
    formula = "annual pay = hourly rate × hours a week × weeks a year"
    answer = f"{p.ma(result)} {PAY_UNITS[target]}"
    check = f"{p.m(result)} × {_q(per_year[target])} = {p.m(result * per_year[target])} a year ✓" if target != "year" else \
        f"{p.m(result)} / {_q(hours_year)} hours = {p.m(result / hours_year)} an hour ✓"
    return _sol(p, "finance", formula, knowns, sub, answer, check)


# ---------------------------------------------------------------- progressive tax brackets

def _h_brackets(p: P) -> Solution | None:
    t = p.t
    if not p.has(r"\btax") or len(p.pcts) < 2:
        return None
    if not p.has(r"\b(?:brackets?|first|next|above|over|up to|upto|between|remaining|rest|bands?|tiers?|marginal|"
                 r"progressive|exceeding|excess|beyond)\b"):
        return None
    if p.has(r"\b(?:off|discount|tip|loan|mortgage|compound\w*|invest\w*)\b"):
        return None
    income_tab = [("income", r"income|salary|earn\w*|makes?|making|made|taxable|gross|wages|tax(?:es)? (?:owed |due |payable )?on|"
                             r"pays? on|someone (?:on|with)", True)]
    income = None
    for k in p.monies:
        if _label(k, income_tab) and not re.search(r"(?:first|next|up to|over|above|between|from|beyond|exceeding)\s*$", k.pre):
            income = k
    if income is None:
        return None
    seg_t = re.sub(r"between\s+([$€£₹¥]?[\d.,]+\s?[kmb]?)\s+and\s+", r"from \1 to ", t)
    clauses = [c for c in re.split(r";|,(?!\d{3})|\.(?!\d)|\band\b|\bthen\b|\n", seg_t) if c.strip()]
    inc_s = t[income.start:income.end]
    brackets = []  # (lo, hi, rate) with hi None for "and above"
    prev_hi = ZERO
    for c in clauses:
        ct = _tokens(c)
        pc = [k for k in ct if k.kind == "pct"]
        zero = re.search(r"\b(?:no tax|tax[- ]free|exempt|untaxed|isn't taxed|is not taxed|not taxed)\b", c)
        if not pc and not zero:
            continue
        rate = pc[0].v if pc else ZERO
        amts = [k.v for k in ct if k.kind in ("money", "bare") and c[k.start:k.end] != inc_s]
        if pc and len(pc) > 1:
            return None
        lo = hi = None
        mr = re.search(r"\bfrom\s*\S*?(\d[\d,.]*\s?[kmb]?)\s*(?:to|-|until|through)\s*\S*?(\d[\d,.]*\s?[kmb]?)", c)
        if len(amts) >= 2 and (mr or re.search(r"\d\s*(?:-|to)\s*[$€£₹¥]?\d", c)):
            lo, hi = amts[0], amts[1]
            if prev_hi and abs(lo - prev_hi) <= 1:
                lo = prev_hi
        elif amts and re.search(r"\bfirst\b", c):
            lo, hi = ZERO, amts[0]
        elif amts and re.search(r"\bnext\b", c):
            lo, hi = prev_hi, prev_hi + amts[0]
        elif amts and re.search(r"\b(?:up to|upto|to|under|below|till|until|not over|not exceeding|less than|at most)\b|<", c):
            lo, hi = prev_hi, amts[0]
        elif amts and re.search(r"\b(?:over|above|more than|beyond|exceeding|in excess of|after|greater than|starting at|from)\b|>|\d\s?\+", c):
            lo, hi = amts[0], None
        elif not amts and re.search(r"\b(?:rest|remaining|remainder|everything|anything|beyond|above|over|after|excess|higher|more)\b", c) and brackets:
            lo, hi = prev_hi, None
        else:
            return None
        brackets.append([lo, hi, rate])
        prev_hi = hi if hi is not None else lo
    if len(brackets) < 2:
        return None
    brackets.sort(key=lambda b: b[0])
    for i, b in enumerate(brackets):
        if b[1] is None:
            b[1] = brackets[i + 1][0] if i + 1 < len(brackets) else INF
    if brackets[0][0] > 0:
        brackets.insert(0, [ZERO, brackets[0][0], ZERO])
    for a, b in zip(brackets, brackets[1:]):
        if b[0] < a[1]:
            return None
    inc = income.v
    tax = ZERO
    lines = []
    for lo, hi, rate in brackets:
        if inc <= lo:
            break
        part = min(inc, hi) - lo
        tax += part * rate
        top = p.m(hi)[len(p.cur):] if hi != INF else "∞"
        lines.append(f"{_pct(rate)} on {p.m(lo)[len(p.cur):]}–{top}: {_pct(rate)} × {_q(part)} = {p.m(part * rate)}")
    eff = tax / inc if inc else ZERO
    marginal = next(r for lo, hi, r in brackets if lo < inc <= hi) if inc > 0 else brackets[0][2]
    formula = "tax = Σ rate × (the part of the income inside each bracket)"
    knowns = [f"income = {p.m(inc)}"] + [f"{_pct(r)} from {_q(lo)}" + (f" to {_q(hi)}" if hi != INF else " up") for lo, hi, r in brackets]
    if p.has(r"\beffective\b|\baverage (?:tax )?rate|\bpercent(?:age)? of (?:my |his |her |their |the )?income|\boverall rate"):
        answer = p.pa(eff)
    elif p.has(r"take[- ]home|after[- ]tax|\bnet (?:income|pay)|\bkeep\b|\bleft\b"):
        answer = p.ma(inc - tax)
        lines.append(f"after tax: {p.m(inc)} − {p.m(tax)} = {p.m(inc - tax)}")
    else:
        answer = p.ma(tax)
    lines.append(f"total tax = {p.m(tax)}; effective rate = {p.m(tax)} / {p.m(inc)} = {_n(eff * 100)}%")
    check = f"marginal rate {_pct(marginal)}, effective {_n(eff * 100)}% — below the top bracket, as it should be ✓"
    return Solution("finance", p.text, answer, [f"formula: {formula}", "known: " + ", ".join(knowns)] + lines +
                    [f"result: {answer}"], check=check, confidence=0.95)


# ---------------------------------------------------------------- break-even

BE_TAB = [
    ("target", r"target(?: profit)?|desired profit|profit (?:of|target|goal)|make a profit|earn a profit|"
               r"(?:to |a )?profit of|(?:want|wants|like) to (?:make|earn|net)", True),
    ("cm", r"contribution margin|margin per unit|profit per unit|contribution per unit", True),
    ("fixed", r"fixed|overheads?|\brent\b|set[- ]?up|start[- ]?up|one[- ]time|upfront|initial (?:investment|cost)|"
              r"tooling|equipment", True),
    ("var", r"variable|to (?:make|produce|build|manufacture|print|bake)|production cost|materials?|unit cost|"
            r"cost per unit|per-unit cost|marginal cost|(?<!fixed )costs?\b|costing|cogs|labou?r", False),
    ("price", r"sell(?:s|ing)?|sold|prices?d?|charges?|charging|retails?|revenue per unit|goes for|\bfor\b", False),
]


def _h_breakeven(p: P) -> Solution | None:
    be = p.has(r"break[- ]?even")
    target_q = p.has(r"how many (?:units|items|products|widgets|\w+s)\b.*\b(?:profit|to make|to earn)") and p.has(r"\bfixed\b")
    if not (be or target_q):
        return None
    lab = {}
    loose = []
    for k in p.monies:
        lb = _label(k, BE_TAB)
        if lb and lb not in lab:
            lab[lb] = k.v
        else:
            loose.append(k.v)
    if "cm" not in lab:
        need = [x for x in ("fixed", "price", "var") if x not in lab]
        if len(loose) < len(need):
            return None
        loose.sort(reverse=True)
        for x in need:  # unlabelled amounts: fixed costs are the biggest, the price beats the unit cost
            lab[x] = loose.pop(0)
        if "fixed" not in lab:
            return None
        cm = lab["price"] - lab["var"]
        cm_s = f"{_q(lab['price'])} − {_q(lab['var'])}"
    else:
        if "fixed" not in lab:
            return None
        cm, cm_s = lab["cm"], _q(lab["cm"])
    fixed = lab["fixed"]
    target = lab.get("target", ZERO)
    if cm <= 0:
        return _rule(p, "finance", "break-even units = fixed costs / (price − variable cost)",
                     [f"price − variable cost = {cm_s} = {_q(cm)} per unit"],
                     "never: each unit loses money (price ≤ variable cost), so sales can't cover fixed costs")
    units = (fixed + target) / cm
    whole = units.to_integral_value(rounding="ROUND_CEILING")
    knowns = [f"fixed costs = {p.m(fixed)}"]
    if "price" in lab:
        knowns += [f"price = {p.m(lab['price'])} per unit", f"variable cost = {p.m(lab['var'])} per unit"]
    knowns.append(f"contribution margin = {cm_s} = {p.m(cm)} per unit")
    if target:
        knowns.append(f"target profit = {p.m(target)}")
        formula = "units = (fixed costs + target profit) / (price − variable cost)"
        sub = f"units = ({_q(fixed)} + {_q(target)}) / {_q(cm)} = {_q(units, 4)}"
    else:
        formula = "break-even units = fixed costs / (price − variable cost)"
        sub = f"units = {_q(fixed)} / {_q(cm)} = {_q(units, 4)}"
    extra = []
    if whole != units:
        extra.append(f"round up: {_q(units, 4)} units isn't enough, so {_q(whole)} units")
    rev = whole * lab["price"] if "price" in lab else None
    if rev is not None:
        extra.append(f"break-even revenue = {_q(whole)} × {p.m(lab['price'])} = {p.m(rev)}" if not target else
                     f"revenue = {_q(whole)} × {p.m(lab['price'])} = {p.m(rev)}")
    if rev is not None and p.has(r"(?:break[- ]?even|in) (?:revenue|sales(?! price)|dollars)|how much (?:revenue|in sales)|"
                                 r"sales revenue|revenue (?:needed|required|to break)|dollar sales"):
        answer = p.ma(rev)
    else:
        answer = f"{_q(whole)} units"
    check = f"{_q(whole)} × {p.m(cm)} = {p.m(whole * cm)} ≥ {p.m(fixed + target)} ✓" if whole != units else \
        f"{_q(whole)} × {p.m(cm)} = {p.m(whole * cm)} = {'fixed costs + target' if target else 'fixed costs'} ✓"
    return _sol(p, "finance", formula, knowns, sub, answer, check, extra)


# ---------------------------------------------------------------- margins

MARGIN_TAB = [
    ("net", r"net (?:income|profit|earnings)|bottom line|profit after tax|net\b", True),
    ("gp", r"gross profit", True),
    ("op", r"operating (?:income|profit)|ebit\b", True),
    ("cogs", r"\bcogs\b|cost of (?:goods|sales|revenue|products)|direct (?:costs?|materials)|production costs?|"
             r"cost of (?:the )?goods", True),
    ("opex", r"operating (?:expenses|costs)|opex|overheads?|expenses|admin\w*|sg&a|salaries|wages|\brent\b|marketing|"
             r"other costs", True),
    ("interest", r"interest", True),
    ("taxes", r"\btax(?:es)?\b", True),
    ("rev", r"revenue|sales|turnover|top line|takings|receipts", True),
    ("rev", r"brought in|sold|sells?|selling|price", False),
    ("cost", r"costs?|spent|spend|paid|bought|cost price", False),
]


def _h_margin(p: P) -> Solution | None:
    if not p.has(r"\bmargins?\b") or p.has(r"\bcontribution margin\b"):
        return None
    lab = {}
    for k in p.monies:
        lb = _label(k, MARGIN_TAB)
        if lb and lb not in lab:
            lab[lb] = k.v
        elif lb is None:
            return None
    tax_rate = next((k.v for k in p.pcts if _role(k) == "tax"), None)
    if "rev" not in lab:
        return None
    rev = lab["rev"]
    if rev <= 0:
        return None
    if "cost" in lab and "cogs" not in lab and "opex" not in lab:
        lab["cogs"] = lab.pop("cost")
        single = True
    else:
        single = False
    lines = []
    gross = lab.get("gp")
    if gross is None and "cogs" in lab:
        gross = rev - lab["cogs"]
        lines.append(f"gross profit = revenue − COGS = {_q(rev)} − {_q(lab['cogs'])} = {p.m(gross)}")
    op = lab.get("op")
    if op is None and gross is not None and "opex" in lab:
        op = gross - lab["opex"]
        lines.append(f"operating profit = gross profit − operating expenses = {_q(gross)} − {_q(lab['opex'])} = {p.m(op)}")
    net = lab.get("net")
    if net is None:
        base = op if op is not None else gross
        if base is not None and ("interest" in lab or "taxes" in lab or tax_rate is not None or "opex" in lab):
            net = base - lab.get("interest", ZERO)
            if "interest" in lab:
                lines.append(f"pre-tax profit = {_q(base)} − interest {_q(lab['interest'])} = {p.m(net)}")
            if "taxes" in lab:
                lines.append(f"net profit = {_q(net)} − tax {_q(lab['taxes'])} = {p.m(net - lab['taxes'])}")
                net -= lab["taxes"]
            elif tax_rate is not None:
                tx = net * tax_rate
                lines.append(f"tax = {_pct(tax_rate)} × {_q(net)} = {p.m(tx)}; net profit = {p.m(net - tx)}")
                net -= tx
    want = []
    if p.has(r"\bgross\b"):
        want.append("gross")
    if p.has(r"\boperating\b") and op is not None:
        want.append("operating")
    if p.has(r"\bnet\b|\bprofit margin\b|\bbottom line\b") and net is not None and not single:
        want.append("net")
    if not want:
        want = ["net"] if net is not None and not single else ["gross"]
    vals = {"gross": gross, "operating": op, "net": net if net is not None else (gross if single else None)}
    if any(vals.get(w) is None for w in want):
        if want == ["net"] and gross is not None:
            want = ["gross"]
        else:
            return None
    knowns = [f"revenue = {p.m(rev)}"] + [f"{n} = {p.m(lab[k])}" for k, n in (("cogs", "COGS" if not single else "cost"), ("opex", "operating expenses"),
                                                                               ("interest", "interest"), ("taxes", "taxes"), ("gp", "gross profit"),
                                                                               ("op", "operating profit"), ("net", "net profit")) if k in lab]
    if tax_rate is not None:
        knowns.append(f"tax rate = {_pct(tax_rate)}")
    parts, subs = [], []
    for w in want:
        v = vals[w]
        parts.append(f"{w} margin {p.pa(v / rev)}" if len(want) > 1 else p.pa(v / rev))
        subs.append(f"{w} margin = {_q(v)} / {_q(rev)} = {_n(v / rev * 100)}%")
    answer = ", ".join(parts)
    formula = "margin = profit / revenue  (gross: revenue − COGS; net: after every cost)"
    check = f"{_n(vals[want[0]] / rev * 100)}% × {p.m(rev)} = {p.m(vals[want[0]] / rev * rev)} of {want[0]} profit ✓"
    return Solution("finance", p.text, answer, [f"formula: {formula}", "known: " + ", ".join(knowns), *lines,
                                                 "substitute: " + "; ".join(subs), f"result: {answer}"],
                    check=check, confidence=0.95)


# ---------------------------------------------------------------- ROI

ROI_TAB = [
    ("income", r"dividends?|distributions?|coupons?|rental income|in rent", True),
    ("gain", r"profit|gain(?:ed|s)?|\bnet\b|earned|made a profit|returned a profit", True),
    ("cost", r"invest(?:ed|ing|ment)?|spent|spend(?:ing)?|cost|paid|put (?:in|into)|initial|bought|purchased?|outlay|"
             r"budget|stake|ad spend|on ads", False),
    ("final", r"worth|sold|sell|value|grew to|became|got back|returned|\bnow\b|ended|final|ending|current|cashed out|"
              r"revenue|generated|brought in|sales|received|paid out|turned into|made", False),
]


def _h_roi(p: P) -> Solution | None:
    if not p.has(r"\broi\b|return on (?:\w+ )?(?:investment|ad spend|spend)|\broas\b|(?:percent(?:age)?|%) (?:return|gain)|"
                 r"total return|what(?:'s| is| was) (?:my|our|the|his|her|their) return|return (?:did|do|would|will|was) "):
        return None
    if len([k for k in p.pcts if _role(k) not in ("tax",)]) >= 2:
        return None
    lab = {}
    for k in p.monies:
        if k.per:
            continue
        lb = _label(k, ROI_TAB)
        if lb and lb not in lab:
            lab[lb] = k.v
    if "cost" not in lab:
        ms = [k.v for k in p.monies if not k.per]
        if len(ms) == 2 and ("final" in lab or "gain" in lab):
            lab["cost"] = next(v for v in ms if v not in lab.values())
        elif len(ms) == 2 and not lab:
            lab["cost"], lab["final"] = ms
        else:
            return None
    cost = lab["cost"]
    if cost <= 0:
        return None
    if "gain" in lab:
        gain = lab["gain"]
        sub = f"ROI = {_q(gain)} / {_q(cost)}"
        knowns = [f"cost = {p.m(cost)}", f"net gain = {p.m(gain)}"]
    elif "final" in lab:
        inc = lab.get("income", ZERO)
        gain = lab["final"] + inc - cost
        plus = f" + {_q(inc)}" if inc else ""
        sub = f"ROI = ({_q(lab['final'])}{plus} − {_q(cost)}) / {_q(cost)} = {_q(gain)} / {_q(cost)}"
        knowns = [f"cost = {p.m(cost)}", f"return = {p.m(lab['final'])}"] + ([f"income received = {p.m(inc)}"] if inc else [])
    else:
        return None
    roi = gain / cost
    extra = []
    term = _term(p)
    answer = p.pa(roi)
    if term and term[0] > 0:
        yrs = term[0]
        ann = (1 + roi) ** (1 / _fd(yrs)) - 1 if 1 + roi > 0 else None
        if ann is not None:
            extra.append(f"annualised over {term[1]}: (1 + {_q(roi)})^(1/{_q(_fd(yrs))}) − 1 = {_n(ann * 100)}% a year")
            if p.has(r"annuali[sz]ed|per year|a year|annual|each year|yearly"):
                answer = f"{p.pa(ann)} a year"
    formula = ("ROI = (return + income − cost) / cost" if lab.get("income") else "ROI = (return − cost) / cost") \
        if "final" in lab else "ROI = net gain / cost"
    check = f"{p.m(cost)} × (1 + {_q(roi)}) = {p.m(cost * (1 + roi))} ✓"
    if roi < 0:
        answer += " (a loss)"
    return _sol(p, "finance", formula, knowns, sub, answer, check, extra)


# ---------------------------------------------------------------- geometric average return

def _signed_returns(p: P) -> list | None:
    out = []
    for k in p.pcts:
        role = _role(k)
        if role in ("tax", "off", "tip", "inflation", "down", "markup", "margin", "service"):
            return None
        neg = k.neg or role in ("down_chg", "loss") or re.search(r"(?:\(|\bnegative|\bminus)\s*$", k.pre)
        out.append(-abs(k.v) if neg else abs(k.v))
    return out


def _h_geo_return(p: P) -> Solution | None:
    if len(p.pcts) < 2:
        return None
    if not p.has(r"\baverage|\bmean\b|\bgeometric|\bannuali[sz]ed|\bcompound(?:ed)? annual|\bcagr\b|\bper year\b|"
                 r"\bannual (?:rate of )?(?:return|growth)|\ba year\b|\beach year\b|\bper annum"):
        return None
    if not p.has(r"return|gain|grew|growth|yield|rose|fell|lost|went|stock|fund|portfolio|invest\w*|year|index|"
                 r"shares?|up\b|down\b|performance|increase|decrease"):
        return None
    if p.has(r"\b(?:tax|off|discount|tip|inflation|loan|mortgage|compounded|interest)\b"):
        return None
    rs = _signed_returns(p)
    if rs is None:
        return None
    n = len(rs)
    prod = ONE
    for r in rs:
        prod *= 1 + r
    if prod <= 0:
        return None
    shown = ", ".join(_pct(r) for r in rs)
    factors = " × ".join(_ds(1 + r) for r in rs)
    arith = sum(rs) / n
    if p.has(r"\barithmetic"):
        answer = f"{p.pa(arith)} a year (arithmetic mean)"
        return _sol(p, "finance", "arithmetic mean = Σ rᵢ / n", [f"returns = {shown}", f"n = {n}"],
                    f"({' + '.join(_ds(r) for r in rs)}) / {n} = {_q(arith, 6)}", answer,
                    "the arithmetic mean overstates what you earned; the geometric mean gives the real growth rate")
    g = prod ** (ONE / n) - 1
    sub = f"({factors})^(1/{n}) − 1 = {_q(prod, 8)}^(1/{n}) − 1"
    answer = f"{p.pa(g)} a year"
    extra = [f"arithmetic mean would be {_n(arith * 100)}%, which overstates the growth"]
    base = next((k for k in p.monies if not k.per), None)
    if base is not None:
        extra.append(f"{p.m(base.v)} × {_q(prod, 8)} = {p.m(base.v * prod)} at the end")
    check = f"(1 + {_q(g, 6)})^{n} = {_q((1 + g) ** n, 6)} = {factors} ✓"
    return _sol(p, "finance", "geometric average return = (Π (1 + rᵢ))^(1/n) − 1", [f"returns = {shown}", f"n = {n} years"],
                sub, answer, check, extra)


# ---------------------------------------------------------------- profit, loss and markup

PL_TAB = [
    ("cost", r"cost price|\bcp\b|bought|\bbuys?\b|buying|purchased?|paid|\bpay\b|wholesale|to (?:make|produce|build)|"
             r"cost(?:s|ing)?\b|costs? (?:me|us|him|her|them|the (?:shop|store|retailer|dealer))|acquired|got (?:it |them )?for|"
             r"\bfrom\s*$|cost of", False),
    ("sale", r"selling price|sale price|\bsp\b|\bsold\b|\bsells?\b|selling|resold|resell|retails?|list(?:ed)? (?:at|for)|"
             r"charges?|charging|\bto\s*$|\bat\s*$|priced at", False),
]


def _h_markup(p: P) -> Solution | None:
    if not p.has(r"mark-?\s?up|marked up|marks? (?:it |them |\w+ )?up|\bprofit|\bloss\b|\bgain\b|cost price|selling price|"
                 r"\bbought|\bbuys?\b|purchased|\bsold\b|\bsells?\b|resell|\bmargin\b"):
        return None
    if p.has(r"\b(?:interest|loan|invest\w*|break[- ]?even|tip|tax|off|discount|roi|revenue|sales|fixed)\b"):
        return None
    roles = [(k, _role(k)) for k in p.pcts]
    if len(roles) > 1:
        return None
    want_markup_early = p.has(r"mark-?\s?up|marked up|marks? (?:it |them |\w+ )?up")
    lab = {}
    for k in p.monies:
        if k.per and k.per != "unit":
            return None
        lb = _label(k, PL_TAB)
        if lb is None and not lab and len(p.monies) == 1 and want_markup_early:
            lb = "cost"  # "marked up a $60 item by 40%"
        if lb is None or lb in lab:
            return None
        lab[lb] = k.v
    qty = next((k.v for k in p.kind("count")), None)
    want_markup = p.has(r"mark-?\s?up|marked up|marks? (?:it |them |\w+ )?up")
    want_margin = p.has(r"\bmargin\b")
    if roles:
        k, role = roles[0]
        r = k.v
        if role not in ("markup", "margin", "profit", "loss", "up", "down_chg", None):
            return None
        if role is None:
            role = "markup" if want_markup else "margin" if want_margin else "loss" if p.has(r"\bloss\b") else "profit"
        if role == "up":
            role = "markup" if want_markup else "profit"
        if role == "down_chg":
            role = "loss"
        if not lab:
            if role == "markup" and want_margin:
                mg = r / (1 + r)
                return _sol(p, "finance", "margin = markup / (1 + markup)", [f"markup = {_pct(r)}"],
                            f"margin = {_ds(r)} / {_ds(1 + r)}", p.pa(mg), f"on a cost of 100 the price is {_q(100 * (1 + r))}: "
                            f"{_q(100 * r)} / {_q(100 * (1 + r))} = {_n(mg * 100)}% ✓")
            if role == "margin" and want_markup:
                if r >= 1:
                    return None
                mk = r / (1 - r)
                return _sol(p, "finance", "markup = margin / (1 − margin)", [f"margin = {_pct(r)}"],
                            f"markup = {_ds(r)} / {_ds(1 - r)}", p.pa(mk), f"on a price of 100 the cost is {_q(100 * (1 - r))}: "
                            f"{_q(100 * r)} / {_q(100 * (1 - r))} = {_n(mk * 100)}% ✓")
            return None
        if len(lab) != 1:
            return None
        sign = -1 if role == "loss" else 1
        name = {"markup": "markup", "margin": "margin", "profit": "profit", "loss": "loss"}[role]
        if "cost" in lab:
            c = lab["cost"]
            if role == "margin":
                if r >= 1:
                    return None
                s = c / (1 - r)
                f, sub = "price = cost / (1 − margin)", f"price = {_q(c)} / (1 − {_ds(r)}) = {_q(c)} / {_ds(1 - r)}"
            else:
                s = c * (1 + sign * r)
                f = f"price = cost × (1 {'−' if sign < 0 else '+'} {name} %)"
                sub = f"price = {_q(c)} × {_ds(1 + sign * r)}"
            answer = f"selling price {p.ma(s)}"
            check = f"({_q(s)} − {_q(c)}) / {_q(s if role == 'margin' else c)} = {_n(abs(s - c) / (s if role == 'margin' else c) * 100)}% ✓"
            return _sol(p, "finance", f, [f"cost = {p.m(c)}", f"{name} = {_pct(r)}"], sub, answer, check)
        if "sale" in lab:
            s = lab["sale"]
            if role == "margin":
                c = s * (1 - r)
                f, sub = "cost = price × (1 − margin)", f"cost = {_q(s)} × {_ds(1 - r)}"
            else:
                c = s / (1 + sign * r)
                f = f"cost = price / (1 {'−' if sign < 0 else '+'} {name} %)"
                sub = f"cost = {_q(s)} / {_ds(1 + sign * r)}"
            answer = f"cost {p.ma(c)}"
            check = f"{_q(c)} × {_ds(1 + sign * r)} = {_q(c * (1 + sign * r))} ✓" if role != "margin" else \
                f"({_q(s)} − {_q(c)}) / {_q(s)} = {_n((s - c) / s * 100)}% ✓"
            return _sol(p, "finance", f, [f"selling price = {p.m(s)}", f"{name} = {_pct(r)}"], sub, answer, check)
        return None
    if set(lab) != {"cost", "sale"}:
        return None
    c, s = lab["cost"], lab["sale"]
    if c <= 0 or s <= 0:
        return None
    diff = s - c
    each = ""
    if qty and qty > 1 and p.has(r"\beach\b|per (?:unit|share|item)|a (?:share|piece|unit)|apiece"):
        each = f" per unit; × {_q(qty)} = {p.m(diff * qty)} in all"
    knowns = [f"cost = {p.m(c)}", f"selling price = {p.m(s)}"]
    if want_margin and not want_markup:
        mg = diff / s
        return _sol(p, "finance", "margin = (price − cost) / price", knowns, f"margin = ({_q(s)} − {_q(c)}) / {_q(s)} = {_q(diff)} / {_q(s)}",
                    p.pa(mg), f"{_q(s)} × (1 − {_q(mg, 6)}) = {_q(s * (1 - mg))} = cost ✓",
                    [f"(markup on cost would be {_n(diff / c * 100)}%)"])
    pct = diff / c
    word = "markup" if want_markup else ("profit" if diff >= 0 else "loss")
    if want_markup:
        answer = p.pa(pct) + " markup"
    else:
        answer = f"{p.pa(abs(pct))} {word} ({p.m(abs(diff))}{each})"
    f = f"{word} % = ({'price − cost' if diff >= 0 or want_markup else 'cost − price'}) / cost × 100"
    sub = f"({_q(s)} − {_q(c)}) / {_q(c)} = {_q(diff)} / {_q(c)}" if diff >= 0 or want_markup else \
        f"({_q(c)} − {_q(s)}) / {_q(c)} = {_q(-diff)} / {_q(c)}"
    check = f"{_q(c)} × {_q(1 + pct, 6)} = {_q(c * (1 + pct))} = selling price ✓"
    return _sol(p, "finance", f, knowns, sub, answer, check)


# ---------------------------------------------------------------- tip, tax and splitting the bill

def _people(p: P) -> tuple | None:
    t = p.t
    for k in p.kind("count", "bare"):
        if k.v != k.v.to_integral_value() or not 1 <= k.v <= 1000:
            continue
        post, pre = k.raw_post[:30], k.pre[-30:]
        n = int(k.v)
        if k.kind == "count" or re.search(r"(?:split|divide[d]?|shared?)\s*(?:it |the bill |the check |the tab |the total |this |that |evenly |equally )*"
                                          r"(?:between|among|by|with|across|into|for)?\s*(?:the\s+)?$|\bparty of\s*$|\bfor\s*$|"
                                          r"\bamong\s*$|\bbetween\s*$", pre):
            if not (k.kind == "count" or re.match(r"^\s*(?:ways|people|persons|friends|of us|guys|diners|guests)\b|^\s*(?:[,.?!]|$)", post)
                    or re.search(r"(?:split|divide[d]?|shared?|between|among|party of)", pre)):
                continue
            plus = 1 if (re.search(r"\b(?:me and|myself and|i and)\s*$", pre)
                         or re.match(r"^\s*(?:friends|others|colleagues|coworkers|co-workers|roommates|guys)\s+and\s+(?:me|i|myself)\b", post)
                         or (re.search(r"\bwith\s*(?:my\s+)?$", pre) and re.match(r"^\s*(?:friends|others|colleagues|coworkers|co-workers|roommates|guys)", post))) else 0
            if n + plus < 1 or (n == 1 and not plus):
                continue
            return n + plus, k
    m = re.search(r"\b(?:split|divide[d]?)\s*(?:it\s+)?in (?:half|two)\b", t)
    if m:
        return 2, None
    return None


def _h_tip(p: P) -> Solution | None:
    tip_words = p.has(r"\btip(?:s|ping|ped)?\b|\bgratuity\b")
    split_words = p.has(r"\bsplit|\bper person|\beach (?:person|pay|owe|share|of us|one)|\bper head|\bdivide|"
                        r"\bshare (?:it|the bill|the cost)|\bways\b|\bhow much (?:does|do|should) each|\beach\b")
    if not (tip_words or split_words):
        return None
    if p.has(r"\b(?:loan|mortgage|interest|invest\w*|salary|break[- ]?even)\b"):
        return None
    roles = [(k, _role(k)) for k in p.pcts]
    tip = [k for k, r in roles if r in ("tip", "service")]
    tax = [k for k, r in roles if r == "tax"]
    other = [k for k, r in roles if r not in ("tip", "service", "tax")]
    if other:
        if tip_words and len(other) == 1 and not tip:
            tip = other  # "leave 15% on a $40 bill, tip?"
        else:
            return None
    bills = [k for k in p.monies if not k.per]
    if not bills:
        return None
    bill = bills[0]
    ppl = _people(p)
    if ppl and ppl[1] is bill:
        return None
    if not tip and not tax and not ppl:
        return None
    if not tip and not (split_words and ppl):
        return None
    if len(bills) > 1 and not (ppl and ppl[1] is not None and ppl[1] in bills):
        return None
    b = bill.v
    tax_amt = sum((b * k.v for k in tax), ZERO)
    tip_after_tax = bool(tax) and (p.has(r"tip (?:on|of) (?:the )?(?:total|whole|full|post-?tax|taxed)|after[- ]tax|"
                                         r"(?:on|of) the (?:bill|total|amount) after (?:the )?tax|"
                                         r"including (?:the )?tax|tax included|on top of (?:the )?tax|post-?tax")
                                   or (tip and tax and tax[0].start < tip[0].start and
                                       re.search(r"\bthen\b|\bafter that\b|\bon top\b", p.t[tax[0].end:tip[0].start])))
    if re.search(r"before[- ]tax|pre-?tax|on the subtotal|on the bill amount|on the food",
                 re.sub(r"\d\s*(?:before|pre)[- ]?tax", " ", p.t)):
        tip_after_tax = False
    tip_base = b + tax_amt if tip_after_tax else b
    tip_amt = sum((tip_base * k.v for k in tip), ZERO)
    total = b + tax_amt + tip_amt
    knowns = [f"bill = {p.m(b)}"]
    lines = []
    if tax:
        knowns.append("tax = " + " + ".join(_pct(k.v) for k in tax))
        lines.append(f"tax: {_q(b)} × {' + '.join(_ds(k.v) for k in tax)} = {p.m(tax_amt)}")
    if tip:
        knowns.append("tip = " + " + ".join(_pct(k.v) for k in tip) + (" (on the bill after tax)" if tip_after_tax else
                                                                       " (on the pre-tax bill)" if tax else ""))
        lines.append(f"tip: {_q(tip_base)} × {' + '.join(_ds(k.v) for k in tip)} = {p.m(tip_amt)}")
    lines.append(f"total: {_q(b)}" + (f" + {_q(tax_amt.quantize(D('0.0001')))}" if tax else "") +
                 (f" + {_q(tip_amt.quantize(D('0.0001')))}" if tip else "") + f" = {p.m(total)}")
    tot_cents = total.quantize(D("0.01"), ROUND_HALF_UP)
    if ppl:
        n = ppl[0]
        knowns.append(f"people = {n}")
        each = tot_cents / n
        each_r = each.quantize(D("0.01"), ROUND_HALF_UP)
        lines.append(f"each: {p.m(tot_cents)} / {n} = {_q(each, 4)}")
        answer = f"{p.ma(each_r)} per person"
        diff = (tot_cents - each_r * n).quantize(D("0.01"))
        check = f"{n} × {p.m(each_r)} = {p.m(each_r * n)}" + (" ✓" if diff == 0 else
                                                             f" ({p.m(abs(diff))} {'short' if diff > 0 else 'over'}: someone rounds {'up' if diff > 0 else 'down'} a cent)")
        formula = "per person = (bill + tax + tip) / people"
    else:
        asked_tip = p.has(r"how much (?:should (?:i|we) |do (?:i|we) |to |would (?:i|we) )?(?:leave as a )?tip\b|what(?:'s| is| should| would) "
                          r"(?:the |a |my |our )?tip\b|\btip amount\b|how much is (?:the |a )?\d+(?:\.\d+)?% tip|how big (?:a|of a) tip")
        if asked_tip and tip and not tax:
            answer = f"{p.ma(tip_amt)} tip"
            check = f"{p.m(tip_amt)} / {p.m(b)} = {_n(tip_amt / b * 100)}% ✓ (total {p.m(total)})"
        else:
            answer = f"{p.ma(total)} total"
            check = f"{p.m(b)} × {_q(total / b, 6)} = {p.m(total)} ✓"
        formula = "total = bill + tax + tip"
    return Solution("finance", p.text, answer, [f"formula: {formula}", "known: " + ", ".join(knowns), *lines,
                                                 f"result: {answer}"], check=check, confidence=0.96)


# ---------------------------------------------------------------- inflation and real returns

def _h_inflation(p: P) -> Solution | None:
    t = p.t
    if not p.has(r"\binflation|purchasing power|buying power|today's (?:dollars|money|terms|prices)|in real terms|"
                 r"real (?:value|terms|rate|return|interest|yield|growth)|cost of living|inflation-adjusted"):
        return None
    infl = [k for k in p.pcts if _role(k) == "inflation"]
    others = [k for k in p.pcts if _role(k) != "inflation"]
    if not infl and len(p.pcts) == 2 and p.has(r"\binflation"):
        a, b = p.pcts
        if p.t.find("inflation") > b.start or p.t.find("inflation") < a.start:
            pass
        infl, others = ([b], [a]) if abs(p.t.find("inflation") - b.start) < abs(p.t.find("inflation") - a.start) else ([a], [b])
    if not infl and len(p.pcts) == 1:
        infl = p.pcts
        others = []
    term = _term(p)
    monies = [k for k in p.monies if not k.per]
    # real rate of return: (1 + nominal) / (1 + inflation) − 1
    if infl and others and not monies:
        i, n = infl[0].v, others[0].v
        real = (1 + n) / (1 + i) - 1
        return _sol(p, "finance", "real rate = (1 + nominal) / (1 + inflation) − 1  (Fisher)",
                    [f"nominal = {_pct(n)}", f"inflation = {_pct(i)}"], f"real = {_ds(1 + n)} / {_ds(1 + i)} − 1",
                    p.pa(real), f"{_ds(1 + i)} × {_q(1 + real, 8)} = {_q((1 + i) * (1 + real), 6)} ✓",
                    [f"(the quick estimate {_pct(n)} − {_pct(i)} = {_pct(n - i)} is close but slightly high)"])
    # average inflation from two prices
    if not infl and len(monies) == 2 and term and p.has(r"inflation rate|rate of inflation|average (?:annual )?inflation|annual inflation"):
        a, b = monies[0].v, monies[1].v
        yrs = _fd(term[0])
        r = (b / a) ** (1 / yrs) - 1
        return _sol(p, "finance", "inflation rate = (later price / earlier price)^(1/years) − 1",
                    [f"earlier = {p.m(a)}", f"later = {p.m(b)}", f"years = {term[1]}"],
                    f"({_q(b)} / {_q(a)})^(1/{_q(yrs)}) − 1", f"{p.pa(r)} a year",
                    f"{_q(a)} × {_q(1 + r, 8)}^{_q(yrs)} = {_q(a * (1 + r) ** yrs, 4)} ✓")
    if not infl or not monies or not term:
        return None
    i = infl[0].v
    x = monies[0].v
    yrs = _fd(term[0])
    defl = (1 + i) ** (int(yrs) if yrs == int(yrs) else yrs)
    if others:  # an investment growing at a nominal rate, in today's money
        n = others[0].v
        m = _compounding(t) or 1
        g, gs = _grow(n, m, term[0])
        fv = x * g
        real = fv / defl
        lines = [f"nominal value: {_q(x)} × {gs} = {p.m(fv)}", f"in today's money: {p.m(fv)} / {_ds(1 + i)}^{_q(yrs)} = {p.m(real)}"]
        answer = f"{p.ma(real)} in today's money"
        return Solution("finance", p.text, answer, [f"formula: real value = P × growth / (1 + inflation)^t",
                                                     "known: " + ", ".join([f"P = {p.m(x)}", f"rate = {_pct(n)}", f"inflation = {_pct(i)}",
                                                                            f"t = {term[1]}"]), *lines, f"result: {answer}"],
                        check=f"{p.m(real)} × {_ds(1 + i)}^{_q(yrs)} = {p.m(real * defl)} ✓ (nominal {p.m(fv)})", confidence=0.95)
    future = p.has(r"\bcost\b|\bcosts\b|\bprice\b|\bneed\b|\bequivalent\b|\bmatch\b|same (?:buying|purchasing) power|keep up|"
                   r"how much (?:money )?(?:will|would) (?:i|we|you) need|will (?:it|this|that|they) cost|be priced") \
        and not p.has(r"\bworth\b|purchasing power of|buying power of|\breal value\b|in today's (?:dollars|money|terms)|"
                      r"\bonly buy\b|\bbuy as much\b|what (?:will|would) (?:that|it|this|\S+) buy")
    if p.has(r"today's (?:dollars|money)|in today's") and p.has(r"\bneed\b|\bequivalent\b|\bmatch\b|same (?:buying|purchasing)"):
        future = True
    if future:
        fut = x * defl
        answer = p.ma(fut)
        return _sol(p, "finance", "future price = today's price × (1 + inflation)^t",
                    [f"today = {p.m(x)}", f"inflation = {_pct(i)} a year", f"t = {term[1]}"],
                    f"{_q(x)} × {_ds(1 + i)}^{_q(yrs)} = {_q(x)} × {_q(defl, 6)}", answer,
                    f"{p.m(fut)} / {_q(defl, 6)} = {p.m(fut / defl)} ✓")
    real = x / defl
    answer = f"{p.ma(real)} in today's money"
    return _sol(p, "finance", "real value = amount / (1 + inflation)^t",
                [f"amount = {p.m(x)}", f"inflation = {_pct(i)} a year", f"t = {term[1]}"],
                f"{_q(x)} / {_ds(1 + i)}^{_q(yrs)} = {_q(x)} / {_q(defl, 6)}", answer,
                f"{p.m(real)} × {_q(defl, 6)} = {p.m(real * defl)} ✓ (it buys {_n(real / x * 100)}% of what it does today)")


# ---------------------------------------------------------------- effective annual rate

def _h_ear(p: P) -> Solution | None:
    t = p.t
    if not p.has(r"\beffective (?:annual|interest|yearly|rate)|\bear\b|\bapy\b|annual percentage yield|effective yield|"
                 r"true annual|annual equivalent rate|\baer\b|effective rate"):
        return None
    if len(p.pcts) != 1 or p.monies and not p.has(r"\bear\b|\bapy\b|effective"):
        return None
    k = p.pcts[0]
    r = k.v
    m = _compounding(t)
    monthly_rate = re.match(r"^\s*(?:a|per|each|every)\s*month|^\s*monthly (?:interest|rate)", k.raw_post) or \
        re.search(r"monthly (?:interest )?rate (?:of|is)?\s*$", k.pre)
    if monthly_rate:
        ear = (1 + r) ** 12 - 1
        return _sol(p, "finance", "EAR = (1 + monthly rate)^12 − 1", [f"monthly rate = {_pct(r)}"],
                    f"EAR = {_ds(1 + r)}^12 − 1 = {_q(ear + 1, 8)} − 1", p.pa(ear),
                    f"compounding beats 12 × {_pct(r)} = {_pct(12 * r)} simple ✓")
    given_ear = re.search(r"\b(?:apy|ear|effective(?: annual)?(?: rate| yield)?|annual percentage yield)\s*(?:of|is|=|:)?\s*(?:an?\s+)?$", k.pre) \
        or re.match(r"^\s*(?:apy|ear|effective|annual percentage yield)", k.post)
    if re.match(r"^\s*(?:%|percent)?\s*(?:apr|nominal|annual percentage rate)\b", k.post) or \
            re.search(r"\b(?:apr|nominal(?: annual)?(?: rate)?)\s*(?:of|is|=|:)?\s*(?:an?\s+)?$", k.pre):
        given_ear = None
    wants_nominal = p.has(r"\b(?:apr|nominal)\b") and given_ear
    note = []
    if m is None:
        m = 12
        note = ["(no compounding given: monthly assumed)"]
    if wants_nominal:
        if m == 0:
            nom = (1 + r).ln()
            return _sol(p, "finance", "nominal = ln(1 + EAR)  (continuous)", [f"EAR = {_pct(r)}"],
                        f"ln({_ds(1 + r)})", p.pa(nom), f"e^{_q(nom, 6)} − 1 = {_q(nom.exp() - 1, 6)} ✓", note)
        nom = m * ((1 + r) ** (ONE / m) - 1)
        return _sol(p, "finance", "APR = n × ((1 + EAR)^(1/n) − 1)", [f"EAR = {_pct(r)}", f"n = {m} ({FREQ_NAME[m]})"],
                    f"APR = {m} × ({_ds(1 + r)}^(1/{m}) − 1)", p.pa(nom),
                    f"(1 + {_q(nom, 8)}/{m})^{m} − 1 = {_q((1 + nom / m) ** m - 1, 6)} ✓", note)
    if m == 0:
        ear = r.exp() - 1
        return _sol(p, "finance", "EAR = e^r − 1  (continuous compounding)", [f"r = {_pct(r)}"], f"EAR = e^{_ds(r)} − 1",
                    p.pa(ear), f"higher than the nominal {_pct(r)} ✓", note)
    ear = (1 + r / m) ** m - 1
    return _sol(p, "finance", "EAR = (1 + r/n)^n − 1", [f"r = {_pct(r)} nominal", f"n = {m} ({FREQ_NAME[m]})"],
                f"EAR = (1 + {_ds(r)}/{m})^{m} − 1 = {_q(ear + 1, 8)} − 1", p.pa(ear),
                f"{'higher than' if m > 1 else 'equal to'} the nominal {_pct(r)} ✓", note)


# ---------------------------------------------------------------- doubling time

def _h_double(p: P) -> Solution | None:
    t = p.t
    mm = re.search(r"\b(doubl\w*|tripl\w*|quadrupl\w*|rule of (72|70|69(?:\.3)?))\b|\b(\d+) times\b", t)
    if not mm:
        return None
    if mm.group(1) and mm.group(1).startswith("doubl") or mm.group(2):
        k, _kname = 2, "double"
    elif mm.group(1) and mm.group(1).startswith("tripl"):
        k, _kname = 3, "triple"
    elif mm.group(1) and mm.group(1).startswith("quadrupl"):
        k, _kname = 4, "quadruple"
    else:
        if not p.has(r"\b(?:grow|grows|become|turn into|multiply|money|investment)\b"):
            return None
        k = int(mm.group(3))
        if k < 2 or k > 100:
            return None
    if not p.has(r"how long|how many years|when|time|years? (?:will|would|does|to)|how fast|rule of|doubling|tripling|"
                 r"what (?:rate|interest)|rate (?:needed|required|do|would)|how quickly"):
        return None
    m = _compounding(t)
    rate = _rate_tok(p)
    rule = mm.group(2) or ("72" if k == 2 else None)
    if rate is None:
        term = _term(p)
        if not term or not p.has(r"\brate|\binterest|\breturn|\bwhat (?:percent|%)"):
            return None
        yrs = _fd(term[0])
        mc = m if m is not None else 1
        if mc == 0:
            r = D(k).ln() / yrs
            sub = f"r = ln {k} / {_q(yrs)}"
        else:
            r = mc * (D(k) ** (ONE / (yrs * mc)) - 1)
            sub = f"r = {mc} × ({k}^(1/({mc} × {_q(yrs)})) − 1)" if mc != 1 else f"r = {k}^(1/{_q(yrs)}) − 1"
        extra = [f"rule of 72: 72 / {_q(yrs)} = {_n(72 / yrs)}%"] if k == 2 else []
        return _sol(p, "finance", f"{k} = (1 + r/n)^(n·t), solved for r", [f"t = {term[1]}", f"compounding {FREQ_NAME[mc]}"],
                    sub, f"{p.pa(r)} a year", f"{_grow(r, mc, term[0])[1]} = {_q(_grow(r, mc, term[0])[0], 6)} ✓", extra)
    r = rate.v
    if r <= 0:
        return None
    mc = m if m is not None else 1
    if mc == 0:
        yrs = D(k).ln() / r
        exact = f"ln {k} / {_ds(r)}"
        formula = f"t = ln {k} / r  (continuous)"
    else:
        yrs = D(k).ln() / (mc * (1 + r / mc).ln())
        exact = f"ln {k} / ln {_ds(1 + r)}" if mc == 1 else f"ln {k} / ({mc} · ln(1 + {_ds(r)}/{mc}))"
        formula = f"t = ln {k} / (n · ln(1 + r/n))"
    rule72 = D(rule) / (r * 100) if rule else None
    knowns = [f"r = {_pct(r)}", f"compounding {FREQ_NAME[mc]}" + ("" if m is not None else " (assumed)")]
    extra = []
    if rule72 is not None:
        extra.append(f"rule of {rule}: {rule} / {_ds(r * 100)} = {_n(rule72)} years")
    if mc not in (0,) and mc <= 12:
        periods = (yrs * mc).to_integral_value(rounding="ROUND_CEILING")
        extra.append(f"in whole compounding periods: {_q(periods)} {'years' if mc == 1 else 'periods'} "
                     f"({'balance first reaches ' + str(k) + '× then' if mc == 1 else _n(periods / mc) + ' years'})")
    if mm.group(2):
        answer = f"{p.na(rule72)} years by the rule of {rule} (exactly {exact} = {_n(yrs)} years)"
    else:
        answer = f"{exact} ≈ {p.na(yrs)} years" + (f" (rule of 72: {_n(rule72)} years)" if rule72 is not None else "")
    check = f"{_grow(r, mc, Fraction(str(yrs)))[1]} = {_q(_grow(r, mc, Fraction(str(yrs.quantize(D('1e-12')))))[0], 4)} ✓"
    return _sol(p, "finance", formula, knowns, f"t = {exact} = {_q(yrs, 6)}", answer, check, extra)


# ---------------------------------------------------------------- loans and mortgages

LOAN_TAB = [
    ("down", r"down(?: payment)?\b|deposit|put(?:ting)? down|downpayment", True),
    ("payment", r"afford|payments? (?:of|is)|payments? (?:can|could|should|must|would|will)?\s*(?:be\s+)?"
                r"(?:no more than|at most|up to|under|less than|max(?:imum)?(?: of)?)|pay(?:ing)? (?:back )?(?:only )?|budget|instal?lment|\bemi\b|repayments?", False),
    ("loan", r"loan|borrow(?:ed|ing|s)?|mortgage|financ(?:e|ed|ing)|principal|balance|\bowe|debt|lend|lent|credit card|"
             r"amount of", False),
    ("price", r"house|home|car|price|costs?|worth|purchase|buy(?:ing)?|property|condo|apartment|flat|truck|vehicle|boat", False),
]


def _h_loan(p: P) -> Solution | None:
    t = p.t
    if not p.has(r"\b(?:loan|mortgage|borrow\w*|financ\w*|car payment|repay\w*|amorti[sz]\w*|emi|instal?lments?|"
                 r"credit card|debt|monthly payments?|pay (?:it )?off|payoff|lend\w*|lent|afford)\b"):
        return None
    if p.has(r"\bsimple interest\b"):
        return None
    rate = _rate_tok(p)
    if rate is None:
        return None
    r = rate.v
    monthly_rate = re.match(r"^\s*(?:a|per|each|every)\s*month|^\s*monthly (?:interest|rate)", rate.raw_post)
    pay = 12
    for rx, f in ((r"(?:annual|yearly) (?:payments?|instal?lments?|repayments?)|pa(?:y|id|yments?)\s*(?:made\s+)?(?:annually|yearly|once a year|each year|every year)", 1),
                  (r"quarterly (?:payments?|instal?lments?)|pa(?:y|id|yments?)\s*(?:made\s+)?quarterly", 4),
                  (r"semi-?annual (?:payments?|instal?lments?)|pa(?:y|id|yments?)\s*(?:made\s+)?semi-?annually", 2),
                  (r"bi-?weekly|fortnightly|every (?:2|two) weeks", 26),
                  (r"weekly (?:payments?|instal?lments?)|pa(?:y|id|yments?)\s*(?:made\s+)?weekly", 52)):
        if p.has(rx):
            pay = f
            break
    m = _compounding(t)
    if monthly_rate:
        r, m = r * 12, 12
    m = pay if m is None else m
    i, i_s = _period_rate(r, m, pay)
    npay_tok = next((k for k in p.toks if k.kind == "bare" and re.match(
        r"^\s*(?:(?:monthly|annual|yearly|quarterly|weekly|equal|level)\s+)*(?:payments|instal?lments|repayments|emis)\b", k.raw_post)), None)
    lab, monies = {}, []
    for k in p.monies:
        if k is npay_tok:
            continue
        lb = "payment" if k.per in ("month", "year", "week", "biweek", "quarter") else _label(k, LOAN_TAB)
        monies.append((k, lb))
        if lb and lb not in lab:
            lab[lb] = k
    down = None
    for k in p.pcts:
        if _role(k) == "down":
            down = ("pct", k.v)
    if "down" in lab:
        down = ("amt", lab["down"].v)
    principal = None
    pdesc = ""
    if "loan" in lab:
        principal = lab["loan"].v
    elif "price" in lab:
        principal = lab["price"].v
    unl = [k for k, lb in monies if lb is None]
    if principal is None and "payment" not in lab and len(unl) == 1:
        principal = unl[0].v
    if principal is not None and down and ("price" in lab or "loan" not in lab):
        dv = principal * down[1] if down[0] == "pct" else down[1]
        pdesc = f" ({p.m(principal)} − {(_pct(down[1]) + ' ') if down[0] == 'pct' else ''}down {p.m(dv)})"
        principal -= dv
    payment = lab["payment"].v if "payment" in lab else None
    pay_name = {12: "a month", 1: "a year", 4: "a quarter", 2: "every six months", 26: "every two weeks", 52: "a week"}[pay]
    per_name = {12: "month", 1: "year", 4: "quarter", 2: "half-year", 26: "fortnight", 52: "week"}[pay]
    term_skip = []
    elapsed = None
    for k in p.toks:
        if k.kind in TIME_KINDS and re.search(r"\b(?:after|in the first|first|after making|once)\s*(?:\d+\s*)?$", k.pre) and \
                p.has(r"balance|remaining|left|still owe|owe after|outstanding|pay ?off|principal remaining"):
            elapsed = k
            term_skip.append(k)
    term = _term(p, skip=term_skip)
    if term is None and npay_tok is not None and npay_tok.v == npay_tok.v.to_integral_value() and npay_tok.v > 0:
        term = (Fraction(int(npay_tok.v), pay), f"{_q(npay_tok.v)} payments", npay_tok)
    knowns_i = f"i = {i_s} per {per_name}" + (" (compounded " + FREQ_NAME[m] + ")" if m != pay else "")
    afford = p.has(r"how much (?:can|could|would) (?:i|we|you|they|he|she) (?:borrow|afford|get)|largest|biggest|maximum|max\b|"
                   r"how (?:big|large|much) (?:a |of a )?(?:loan|mortgage)|what (?:loan|mortgage)(?: amount| size)?|"
                   r"how expensive|how much house|what (?:price|size of) (?:house|home|car)|afford to borrow|loan amount")
    # affordability: the loan a payment supports
    if payment is not None and (principal is None or afford) and term:
        n = term[0] * pay
        if n.denominator != 1:
            return None
        n = int(n)
        pv = payment * (1 - (1 + i) ** -n) / i if i else payment * n
        knowns = [f"PMT = {p.m(payment)} {pay_name}", knowns_i, f"n = {term[1]} × {pay} = {n} payments"]
        answer = p.ma(pv)
        extra = []
        if down and down[0] == "amt" and p.has(r"house|home|car|price|property"):
            extra.append(f"with {p.m(down[1])} down the price could be {p.m(pv + down[1])}")
            if p.has(r"house|home|car|price|property") and p.has(r"how expensive|how much house|what (?:price|size)|afford"):
                answer = p.ma(pv + down[1])
        return _sol(p, "finance", "PV = PMT × (1 − (1 + i)^−n) / i  (the loan a payment repays)", knowns,
                    f"PV = {_q(payment)} × (1 − (1 + {_q(i, 8)})^−{n}) / {_q(i, 8)}", answer,
                    f"a {p.m(pv)} loan at this rate costs {p.m(pv * i / (1 - (1 + i) ** -n) if i else pv / n)} {pay_name} ✓", extra)
    if principal is None or principal <= 0:
        return None
    knowns_p = f"P = {p.m(principal)}{pdesc}"
    # payoff time: payments given, no term
    if payment is not None and not afford:
        if not p.has(r"how long|how many (?:months|years|payments|weeks)|when will|pay (?:it )?off|payoff|time to"):
            return None
        if payment <= principal * i:
            return _rule(p, "finance", "a payment must beat the interest to shrink the balance",
                         [f"interest each {per_name}: {_q(principal)} × {_q(i, 8)} = {p.m(principal * i)}"],
                         f"never: {p.m(payment)} {pay_name} doesn't cover the interest")
        n = -(1 - principal * i / payment).ln() / (1 + i).ln() if i else principal / payment
        whole = n.to_integral_value(rounding="ROUND_CEILING")
        knowns = [knowns_p, knowns_i, f"PMT = {p.m(payment)} {pay_name}"]
        bal_before_last = principal * (1 + i) ** (int(whole) - 1) - payment * (((1 + i) ** (int(whole) - 1) - 1) / i if i else int(whole) - 1)
        last = bal_before_last * (1 + i)
        answer = f"{_q(whole)} {per_name}s" + (f" ({_n(whole / pay)} years)" if pay != 1 else "")
        return _sol(p, "finance", "n = −ln(1 − P·i / PMT) / ln(1 + i)", knowns,
                    f"n = −ln(1 − {_q(principal)} × {_q(i, 8)} / {_q(payment)}) / ln(1 + {_q(i, 8)}) = {_q(n, 4)}",
                    answer, f"after {_q(whole - 1)} payments {p.m(bal_before_last)} is left; the last payment is {p.m(last)} ✓",
                    [f"round up: {_q(whole)} payments, the last one smaller"] if whole != n else [])
    if not term:
        return None
    n = term[0] * pay
    if n.denominator != 1 or n <= 0:
        return None
    n = int(n)
    if not p.has(r"payments?|\bpay\b|\bemi\b|instal?lments?|interest|total|cost|repay\w*|monthly|each month|per month|"
                 r"a month|balance|\bowe\b|remaining|left|outstanding|amorti[sz]\w*|how much (?:will|would|do|does|is)"):
        return None
    pmt = principal * i / (1 - (1 + i) ** -n) if i else principal / n
    pmt_c = pmt.quantize(D("0.01"), ROUND_HALF_UP)
    knowns = [knowns_p, knowns_i, f"n = {term[1]} × {pay} = {n} payments" if term[2].kind == "year" else f"n = {n} payments"]
    formula = "PMT = P × i / (1 − (1 + i)^−n)"
    sub = f"PMT = {_q(principal)} × {_q(i, 8)} / (1 − (1 + {_q(i, 8)})^−{n})"
    total = pmt_c * n
    interest = total - principal
    extra = [f"payment: {p.m(pmt_c)} {pay_name}"]
    if elapsed is not None:
        kel = elapsed
        k_n = _years_of(kel, t) * pay if kel.kind != "bare" else Fraction(str(kel.v))
        if k_n.denominator != 1:
            return None
        kk = int(k_n)
        bal = principal * (1 + i) ** kk - pmt * (((1 + i) ** kk - 1) / i if i else kk)
        extra.append(f"balance after {kk} payments: {_q(principal)} × (1 + i)^{kk} − PMT × ((1 + i)^{kk} − 1) / i")
        answer = f"{p.ma(bal)} still owed"
        return _sol(p, "finance", formula, knowns, sub, answer,
                    f"PV of the remaining {n - kk} payments = {p.m(pmt * (1 - (1 + i) ** -(n - kk)) / i if i else pmt * (n - kk))} ✓", extra)
    asked_interest = p.has(r"interest (?:paid|will|would|do|does|is|over|in total|altogether|charged|cost)|total interest|"
                           r"how much interest|in interest|interest (?:i|we|you) (?:will |would )?pay|cost of (?:the )?(?:loan|mortgage|borrowing)|"
                           r"total cost of (?:interest|borrowing)")
    asked_total = p.has(r"total (?:amount )?(?:paid|repaid|cost|payments?|of (?:all )?(?:the )?payments)|pay (?:back )?in total|"
                         r"total (?:i|we|you) (?:will )?pay|altogether|how much (?:will|would) (?:i|we|you) (?:end up )?pay(?: back)?(?! (?:each|per|a|every) )")
    extra.append(f"total paid: {n} × {p.m(pmt_c)} = {p.m(total)}")
    if asked_interest:
        answer = f"{p.ma(interest)} total interest"
        if p.has(r"\b(?:monthly )?payments? (?:and|&|plus|as well)|\bmonthly payment\b.*\binterest|\bemi\b.*\binterest"):
            answer = f"{p.ma(pmt)} {pay_name}; {answer}"
        check = f"{p.m(total)} paid − {p.m(principal)} borrowed = {p.m(interest)} ✓"
    elif asked_total and not p.has(r"\b(?:monthly|each month|per month|a month)\b.*\?|^\s*(?:what|how much) (?:is|are|will be) (?:the |my )?monthly"):
        answer = f"{p.ma(total)} in total"
        check = f"principal {p.m(principal)} + interest {p.m(interest)} = {p.m(total)} ✓"
    else:
        answer = f"{p.ma(pmt)} {pay_name}"
        check = f"{n} × {p.m(pmt_c)} = {p.m(total)} paid: {p.m(principal)} principal + {p.m(interest)} interest"
    return _sol(p, "finance", formula, knowns, sub, answer, check, extra)


# ---------------------------------------------------------------- saving: deposits and goals

SAVE_TAB = [
    ("initial", r"start(?:ing|s)? (?:with|off with|out with)|already (?:have|has|got|saved)|initial|lump sum|currently (?:have|has)|"
                r"existing|opening (?:balance|deposit)|right now|have saved|has saved|today", True),
    ("goal", r"\bhave\b|reach|\bget\b|accumulate|save up|goal|target|total of|end up with|grow to|retire with|need|needs|"
             r"worth|for an?|million|save\s*$|saving\s*$|amass|to hit|by then", False),
]


def _deposit_tok(p: P):
    for k in p.monies:
        if k.per in ("month", "year", "week", "quarter", "biweek", "day"):
            if re.search(r"(?:afford|loan|mortgage|rent|salary|earn|make)\w*\s*(?:of|is)?\s*$", k.pre):
                continue
            return k
    return None


def _h_annuity(p: P) -> Solution | None:
    t = p.t
    if not p.has(r"\b(?:deposit\w*|sav(?:e|es|ed|ing|ings)|contribut\w*|invest\w*|put(?:ting)?|"
                 r"set(?:ting)? aside|sock(?:ing)? away|stash\w*|annuity|retirement|retire|sip|recurring|add(?:ing|s)?|pay(?:ing|s)? in)\b"):
        return None
    if p.has(r"\b(?:loan|mortgage|borrow\w*|salary|break[- ]?even)\b"):
        return None
    rate = _rate_tok(p)
    if rate is None:
        return None
    r = rate.v
    dep = _deposit_tok(p)
    if dep is None and p.has(r"(?:invest|deposit|put|set aside|place|save)\w*\s+(?:in\s+|away\s+)?(?:today|now|right now)\b|"
                             r"\blump sum\b|\bpresent value\b"):
        return None
    if dep is None and not re.search(r"\b(?:each|every|per|a) (?:month|year|week|quarter)\b|\b(?:monthly|annual(?:ly)?|yearly|"
                                      r"weekly|quarterly|regular(?:ly)?|recurring|annuity|sip)\b",
                                      re.sub(r"compound\w*\s+\S+|\S+\s+compounding|%\s*(?:(?:per|a|an|each)\s+)?"
                                             r"(?:year|annum|annual(?:ly)?|yearly)\b|\b(?:annual|yearly)\s+(?:rate|interest|return)",
                                             " ", t)):
        return None  # one lump sum, not a savings plan
    per_word = {"month": 12, "year": 1, "week": 52, "quarter": 4, "biweek": 26, "day": 365}
    lab = {}
    for k in p.monies:
        if k is dep:
            continue
        lb = _label(k, SAVE_TAB)
        if lb and lb not in lab:
            lab[lb] = k.v
        elif lb is None and "goal" not in lab:
            lab["goal"] = k.v
    asks_dep = p.has(r"how much (?:do|should|must|would|will|can|does) (?:i|we|you|he|she|they) (?:need to |have to |got to )?"
                     r"(?:save|deposit|invest|put|set aside|contribute|sock away|add)|"
                     r"(?:monthly|annual|weekly|quarterly|yearly) (?:deposit|contribution|saving|savings|amount|payment|investment)s? "
                     r"(?:needed|required|necessary|would|will|do|should)|what (?:monthly |annual |weekly |yearly |quarterly )?"
                     r"(?:deposit|contribution|payment|amount|investment)|how much (?:per|a|each|every) (?:month|year|week|quarter)|"
                     r"need to (?:save|deposit|invest|put away|set aside)|required (?:monthly |annual )?(?:deposit|contribution)|"
                     r"how much (?:money )?to (?:save|deposit|invest|put)")
    m = _compounding(t)
    due = p.has(r"(?:at the )?(?:beginning|start) of (?:each|every|the) (?:month|year|week|quarter|period)|annuity due|in advance")
    term = _term(p)
    if dep is None:
        if not asks_dep or "goal" not in lab or not term:
            return None
        per = None
        for u, rx in (("month", r"month"), ("year", r"\byear|annual"), ("week", r"week"), ("quarter", r"quarter")):
            if re.search(rf"(?:per|a|each|every|monthly|weekly|yearly|annual|quarterly)\s*{rx}|{rx}ly", t):
                per = u
                break
        if per is None:
            per = "month" if p.has(r"\bmonth") else "year"
        pay = per_word[per]
        m = pay if m is None else m
        i, i_s = _period_rate(r, m, pay)
        n = term[0] * pay
        if n.denominator != 1:
            return None
        n = int(n)
        goal = lab["goal"]
        init = lab.get("initial", ZERO)
        g = (1 + i) ** n
        need = goal - init * g
        if need <= 0:
            return _rule(p, "finance", "a lump sum grows on its own",
                         [f"{p.m(init)} × (1 + {_q(i, 8)})^{n} = {p.m(init * g)} ≥ {p.m(goal)}"], f"{p.ma(0)}: the starting amount already gets there")
        fac = (g - 1) / i if i else D(n)
        if due:
            fac *= 1 + i
        pmt = need / fac
        knowns = [f"goal FV = {p.m(goal)}"] + ([f"starting with {p.m(init)}"] if init else []) + \
            [f"i = {i_s} per {per}" + (f" (compounded {FREQ_NAME[m]})" if m != pay else ""), f"n = {n} deposits"]
        sub = f"PMT = {_q(need) if not init else '(' + _q(goal) + ' − ' + _q(init) + ' × ' + _q(g, 6) + ')'} × {_q(i, 8)} / ((1 + {_q(i, 8)})^{n} − 1)"
        if due:
            sub += f" / (1 + {_q(i, 8)})  (deposits at the start of each {per})"
        answer = f"{p.ma(pmt)} a {per}"
        fv_chk = pmt * fac + init * g
        return _sol(p, "finance", "PMT = FV × i / ((1 + i)^n − 1)" + ("  (after the starting amount's growth)" if init else ""),
                    knowns, sub, answer, f"{n} × {p.m(pmt)} grows to {p.m(fv_chk)} ✓ (you put in {p.m(pmt * n + init)})")
    pay = per_word[dep.per]
    m = pay if m is None else m
    i, i_s = _period_rate(r, m, pay)
    d = dep.v
    init = lab.get("initial", ZERO)
    goal = lab.get("goal")
    if not term:
        if goal is None or not p.has(r"how long|how many (?:months|years|weeks|deposits)|when (?:will|would)"):
            return None
        if goal <= init:
            return None
        # (init·i + d)·(1+i)^n = goal·i + d
        if i:
            n = ((goal * i + d) / (init * i + d)).ln() / (1 + i).ln()
        else:
            n = (goal - init) / d
        whole = n.to_integral_value(rounding="ROUND_CEILING")
        answer = f"{_q(whole)} {dep.per}s" + (f" ({_n(whole / pay)} years)" if pay != 1 else "")
        return _sol(p, "finance", "FV = PMT × ((1 + i)^n − 1) / i, solved for n", [f"PMT = {p.m(d)} a {dep.per}", f"goal = {p.m(goal)}",
                                                                                   f"i = {i_s}"],
                    f"n = ln((FV·i + PMT) / (PMT{' + P·i' if init else ''})) / ln(1 + i) = {_q(n, 4)}", answer,
                    f"after {_q(whole)} deposits the balance is {p.m(d * (((1 + i) ** int(whole) - 1) / i if i else whole) + init * (1 + i) ** int(whole))} ≥ {p.m(goal)} ✓")
    if asks_dep:
        return None
    n = term[0] * pay
    if n.denominator != 1:
        return None
    n = int(n)
    fac = ((1 + i) ** n - 1) / i if i else D(n)
    if due:
        fac *= 1 + i
    fv = d * fac
    g = (1 + i) ** n
    lines = [f"deposits: {_q(d)} × ((1 + {_q(i, 8)})^{n} − 1) / {_q(i, 8)}" + (f" × (1 + {_q(i, 8)})" if due else "") + f" = {p.m(fv)}"]
    if init:
        lines.append(f"starting amount: {_q(init)} × (1 + {_q(i, 8)})^{n} = {p.m(init * g)}")
    total = fv + init * g
    put_in = d * n + init
    asked_interest = p.has(r"how much interest|interest (?:earned|will|would)|in interest|how much (?:of it )?(?:is|will be) (?:interest|growth)")
    answer = p.ma(total - put_in) + " interest" if asked_interest else p.ma(total)
    knowns = [f"PMT = {p.m(d)} a {dep.per}" + (" (at the start of each)" if due else "")] + ([f"starting amount = {p.m(init)}"] if init else []) + \
        [f"i = {i_s} per {dep.per}" + (f" (compounded {FREQ_NAME[m]})" if m != pay else ""), f"n = {term[1]} × {pay} = {n} deposits" if term[2].kind == "year" else f"n = {n} deposits"]
    return Solution("finance", p.text, answer,
                    [f"formula: FV = PMT × ((1 + i)^n − 1) / i" + (" × (1 + i)" if due else "") + (" + P × (1 + i)^n" if init else ""),
                     "known: " + ", ".join(knowns), *lines, f"result: {answer}"],
                    check=f"you put in {p.m(put_in)}; interest {p.m(total - put_in)}; total {p.m(total)} ✓", confidence=0.96)


# ---------------------------------------------------------------- present value

def _h_pv(p: P) -> Solution | None:
    pv_words = p.has(r"present value|\bpv\b|\btoday\b|right now|\bnow\b|lump sum|discount(?:ed)? (?:back|at|rate)|worth today|value today|"
                     r"how much (?:money )?(?:should|must|do|would|will|to|does|did|need) (?:i |we |you |he |she |they )?(?:need to |have to )?"
                     r"(?:invest|deposit|put|set aside|start with|save|place)")
    if not pv_words:
        return None
    if p.has(r"\b(?:inflation|loan|mortgage|borrow\w*)\b"):
        return None
    if p.has(r"\bat the end\b|future value|grows? to|end up with|will (?:it|i|we) have|be worth (?:after|in)") and \
            not p.has(r"present value|\bpv\b|worth today|value today|\btoday\b|\bnow\b"):
        return None
    rate = _rate_tok(p)
    term = _term(p)
    if rate is None or not term:
        return None
    r = rate.v
    m = _compounding(p.t)
    dep = _deposit_tok(p)
    monies = [k for k in p.monies if k is not dep]
    if dep is not None:
        if not p.has(r"present value|\bpv\b|worth today|value today|lump sum|today"):
            return None
        pay = {"month": 12, "year": 1, "week": 52, "quarter": 4, "biweek": 26, "day": 365}[dep.per]
        mc = pay if m is None else m
        i, i_s = _period_rate(r, mc, pay)
        n = term[0] * pay
        if n.denominator != 1:
            return None
        n = int(n)
        pv = dep.v * (1 - (1 + i) ** -n) / i if i else dep.v * n
        return _sol(p, "finance", "PV = PMT × (1 − (1 + i)^−n) / i", [f"PMT = {p.m(dep.v)} a {dep.per}", f"i = {i_s}", f"n = {n} payments"],
                    f"PV = {_q(dep.v)} × (1 − (1 + {_q(i, 8)})^−{n}) / {_q(i, 8)}", p.ma(pv),
                    f"{p.m(pv)} invested at this rate pays out exactly {p.m(dep.v)} a {dep.per} for {n} {dep.per}s ✓")
    if len(monies) != 1:
        return None
    fv = monies[0].v
    mc = 1 if m is None else m
    g, gs = _grow(r, mc, term[0])
    pv = fv / g
    knowns = [f"FV = {p.m(fv)}", f"r = {_pct(r)}", f"compounding {FREQ_NAME[mc]}" + (" (assumed)" if m is None else ""), f"t = {term[1]}"]
    formula = "PV = FV / (1 + r/n)^(n·t)" if mc else "PV = FV × e^(−r·t)"
    return _sol(p, "finance", formula, knowns, f"PV = {_q(fv)} / {gs} = {_q(fv)} / {_q(g, 8)}", p.ma(pv),
                f"{p.m(pv)} × {_q(g, 8)} = {p.m(pv * g)} ✓")


# ---------------------------------------------------------------- simple interest

SI_TAB = [
    ("interest", r"interest of|in interest|earn(?:s|ed|ing)?|(?<!simple )(?<!flat )\binterest\b(?!\s*:)|gains?|yields?", False),
    ("amount", r"grow(?:s|n)? to|amounts? to|total|becomes?|worth|maturity|matures? (?:to|at)|accumulated? to|owe|repay|turns? into", False),
    ("principal", r"principal|invest(?:ed|s|ing)?|deposit(?:ed|s)?|borrow(?:ed|s)?|loan(?: of)?|lend|lent|put|\bon\b|\bof\b|sum", False),
]


def _h_simple(p: P, explicit: bool) -> Solution | None:
    t = p.t
    simple = p.has(r"\bsimple\b") or p.has(r"\bflat (?:rate|interest)\b")
    if explicit != simple:
        return None
    if not p.has(r"\binterest\b"):
        return None
    term = _term(p)
    rate = _rate_tok(p)
    if not simple:  # short-term "interest on $2,000 at 5% for 90 days" with no compounding named is simple interest
        if _compounding(t) is not None or not term or term[2].kind not in ("day", "month", "week") or term[0] >= 1:
            return None
        if p.has(r"\b(?:loan|mortgage)\b.*\b(?:payment|monthly)|\bdeposit\w* \S+ (?:a|per|each|every) ") or _deposit_tok(p):
            return None
    lab = {}
    for k in p.monies:
        if k.per:
            return None
        lb = _label(k, SI_TAB) or "principal"
        if lb in lab:
            lb = "amount" if "amount" not in lab else lb
        if lb in lab:
            return None
        lab[lb] = k.v
    if "principal" not in lab and "interest" in lab and "amount" in lab:
        lab["principal"] = lab["amount"] - lab["interest"]
    if "interest" not in lab and "amount" in lab and "principal" in lab:
        lab["interest"] = lab["amount"] - lab["principal"]
    unit = ""
    if term:
        unit = term[1]
    P_, I_ = lab.get("principal"), lab.get("interest")
    r = rate.v if rate else None
    yrs = _fd(term[0]) if term else None
    known_vals = sum(x is not None for x in (P_, I_, r, yrs))
    if known_vals < 3:
        return None
    formula = "I = P × r × t  (simple interest)"
    if P_ is not None and r is not None and yrs is not None:
        I = P_ * r * yrs
        knowns = [f"P = {p.m(P_)}", f"r = {_pct(r)} a year", f"t = {unit}"]
        tt = f"({_q(term[2].v)}/{365 if term[2].kind == 'day' and _years_of(term[2], t) * 365 == Fraction(str(term[2].v)) else 360})" \
            if term[2].kind == "day" else (f"({_q(term[2].v)}/12)" if term[2].kind == "month" else _q(yrs))
        sub = f"I = {_q(P_)} × {_ds(r)} × {tt}"
        total = P_ + I
        if p.has(r"\btotal|\bamount|\bowe\b|\brepay|\bmaturity|how much (?:will|would) (?:i|you|we|it|they|he|she) (?:have|owe|get|be)|balance|worth|altogether|in all|"
                 r"pay back|future value|accumulated value|grow to"):
            answer = p.ma(total)
            check = f"interest {p.m(I)} + principal {p.m(P_)} = {p.m(total)} ✓"
        else:
            answer = p.ma(I)
            check = f"{p.m(I)} / ({_q(P_)} × {_ds(r)}) = {_q(I / (P_ * r), 6)} years = {unit.split(' = ')[0]} ✓" if r else ""
        return _sol(p, "finance", formula, knowns, sub, answer, check, [f"total = {p.m(P_)} + {p.m(I)} = {p.m(total)}"])
    if I_ is None:
        return None
    if P_ is None and r and yrs:
        P_ = I_ / (r * yrs)
        return _sol(p, "finance", "P = I / (r × t)", [f"I = {p.m(I_)}", f"r = {_pct(r)}", f"t = {unit}"],
                    f"P = {_q(I_)} / ({_ds(r)} × {_q(yrs)})", p.ma(P_), f"{_q(P_)} × {_ds(r)} × {_q(yrs)} = {_q(P_ * r * yrs)} ✓")
    if r is None and P_ and yrs:
        rr = I_ / (P_ * yrs)
        return _sol(p, "finance", "r = I / (P × t)", [f"I = {p.m(I_)}", f"P = {p.m(P_)}", f"t = {unit}"],
                    f"r = {_q(I_)} / ({_q(P_)} × {_q(yrs)})", f"{p.pa(rr)} a year", f"{_q(P_)} × {_q(rr, 6)} × {_q(yrs)} = {_q(P_ * rr * yrs)} ✓")
    if yrs is None and P_ and r:
        ty = I_ / (P_ * r)
        return _sol(p, "finance", "t = I / (P × r)", [f"I = {p.m(I_)}", f"P = {p.m(P_)}", f"r = {_pct(r)}"],
                    f"t = {_q(I_)} / ({_q(P_)} × {_ds(r)})", f"{p.na(ty)} years", f"{_q(P_)} × {_ds(r)} × {_q(ty, 6)} = {_q(P_ * r * ty)} ✓")
    return None


# ---------------------------------------------------------------- compound interest, growth and depreciation

CI_TAB = [
    ("target", r"grow(?:s|n)? to|reach(?:es)?|becomes?|turn(?:s)? into|to have|\bget to\b|\bgoal\b|end up with|be worth|amount to|"
               r"\bto\s*$|double to|hit", False),
    ("principal", r"invest(?:ed|s|ing)?|deposit(?:ed|s)?|principal|put|starts?|start(?:ing)? with|initial|lump sum|\bof\b|worth|"
                  r"account|balance|\bon\b|borrow(?:ed|s)?|loan|owe|bought|buy|costs?|car|house|price", False),
]
SHRINK = r"depreciat\w*|los(?:e|es|ing|t)\b|declin\w*|decreas\w*|shrink\w*|falls?|fell|drops?|dropped|devalu\w*|wear"


def _h_compound(p: P) -> Solution | None:
    t = p.t
    if not p.has(r"interest|invest\w*|deposit\w*|compound\w*|grow\w*|growth|grew|apprec\w*|savings?|account|balance|\bcd\b|"
                 r"certificate|bond|yield\w*|earn\w*|return\w*|worth|value|principal|lump sum|\bput\b|bank|fund|portfolio|"
                 r"stock|increas\w*|rises?|owe|loan|debt|" + SHRINK):
        return None
    if p.has(r"\bpopulation|bacteria|\bcells\b|residents|followers|subscribers|\busers\b|\bviews\b|half-life|radioactive") and not p.cur:
        return None
    if _deposit_tok(p) is not None or p.has(r"\b(?:tax|tip|off|discount|inflation)\b"):
        return None
    rate = _rate_tok(p)
    term = _term(p)
    m = _compounding(t)
    mc = 1 if m is None else m
    monies = [k for k in p.monies if not k.per]
    if len(monies) not in (1, 2) or len(p.pcts) > 1:
        return None
    shrink = rate is not None and (re.search(rf"(?:{SHRINK})\w*\s*(?:by|at|of)?\s*(?:an?\s+)?(?:about\s+)?$", rate.pre)
                                   or re.match(rf"^\s*(?:a year |per year |annually |each year |every year )?(?:{SHRINK})", rate.post)
                                   or _role(rate) == "down_chg")
    if shrink and not p.has(SHRINK):
        shrink = False
    sign = -1 if shrink else 1
    asked_interest = p.has(r"how much interest|interest (?:earned|will|would|does|do|is|accrued|accumulated|gained|paid|owed|made)|"
                           r"compound interest (?:on|earned|for|is|will|would)|(?:find|what(?:'s| is)) the (?:compound )?interest|"
                           r"earn in interest|\bin interest\b|interest amount|amount of interest|how much (?:will|would) (?:it|i|you|we) earn")
    asked_amount = p.has(r"total amount|final amount|\bamount\b|balance|how much (?:will|would) (?:i|it|you|we|they|he|she) (?:have|be|owe|get)|"
                         r"\bworth\b|future value|\bvalue\b|maturity")
    if len(monies) == 2:
        lab = {}
        for k in monies:
            lb = _label(k, CI_TAB)
            if lb in lab or lb is None:
                lb = "target" if "target" not in lab else "principal"
            if lb in lab:
                return None
            lab[lb] = k.v
        P_, A = lab["principal"], lab["target"]
        if P_ <= 0 or A <= 0:
            return None
        if rate is not None and not term:  # how long
            if not p.has(r"how long|how many (?:years|months)|when|time|take"):
                return None
            r = rate.v * sign
            if (A > P_) != (r > 0):
                return None
            if mc == 0:
                yrs = (A / P_).ln() / r
                exact = f"ln({_q(A)}/{_q(P_)}) / {_ds(r)}"
            else:
                yrs = (A / P_).ln() / (mc * (1 + r / mc).ln())
                exact = f"ln({_q(A)}/{_q(P_)}) / ({mc} · ln(1 + {_ds(r)}/{mc}))" if mc != 1 else f"ln({_q(A)}/{_q(P_)}) / ln {_ds(1 + r)}"
            extra = []
            if mc in (1, 2, 4, 12):
                whole = (yrs * mc).to_integral_value(rounding="ROUND_CEILING")
                extra.append(f"in whole compounding periods: {_q(whole)} ({_n(whole / mc)} years), when the balance is "
                             f"{p.m(P_ * (1 + r / mc) ** int(whole))}")
            return _sol(p, "finance", "t = ln(A/P) / (n · ln(1 + r/n))" if mc else "t = ln(A/P) / r",
                        [f"P = {p.m(P_)}", f"A = {p.m(A)}", f"r = {_pct(r)}", f"compounding {FREQ_NAME[mc]}" + (" (assumed)" if m is None else "")],
                        f"t = {exact}", f"{p.na(yrs)} years", f"{_q(P_)} × {_grow(r, mc, Fraction(str(yrs.quantize(D('1e-12')))))[1]} ≈ {_q(A)} ✓", extra)
        if rate is None and term:  # what rate
            if not p.has(r"rate|percent|%|interest|return|cagr|growth|how fast|what (?:annual|yearly)"):
                return None
            yrs = _fd(term[0])
            if mc == 0:
                r = (A / P_).ln() / yrs
                sub = f"r = ln({_q(A)}/{_q(P_)}) / {_q(yrs)}"
            else:
                r = mc * ((A / P_) ** (ONE / (yrs * mc)) - 1)
                sub = f"r = ({_q(A)}/{_q(P_)})^(1/{_q(yrs)}) − 1" if mc == 1 else f"r = {mc} × (({_q(A)}/{_q(P_)})^(1/({mc} × {_q(yrs)})) − 1)"
            g = _grow(r, mc, term[0])
            word = "a year (compound annual growth rate)" if mc == 1 else f"a year, compounded {FREQ_NAME[mc]}"
            return _sol(p, "finance", "r = n × ((A/P)^(1/(n·t)) − 1)" if mc else "r = ln(A/P) / t",
                        [f"P = {p.m(P_)}", f"A = {p.m(A)}", f"t = {term[1]}"], sub, f"{p.pa(r)} {word}",
                        f"{_q(P_)} × {g[1].replace(_ds(r), _q(r, 6))} = {_q(P_ * g[0], 2)} ✓")
        return None
    if rate is None or not term:
        return None
    if not (p.has(r"compound\w*|interest|invest\w*|deposit\w*|grow\w*|savings?|account|\bcd\b|bond|apprec\w*|"
                  r"increas\w*|rises?|portfolio|fund|" + SHRINK)
            or (p.has(r"\bat\s*[$€£₹¥]?\d|@") and p.has(r"how much|worth|value|total|amount|have|balance"))):
        return None
    P_ = monies[0].v
    r = rate.v * sign
    g, gs = _grow(r, mc, term[0])
    A = P_ * g
    I = A - P_
    knowns = [f"P = {p.m(P_)}", f"r = {'−' if sign < 0 else ''}{_pct(rate.v)}" + (" a year" if mc != 1 else ""),
              f"n = {mc} ({FREQ_NAME[mc]})" + (" (assumed)" if m is None else "") if mc else "continuous compounding", f"t = {term[1]}"]
    formula = "A = P × (1 + r/n)^(n·t)" if mc else "A = P × e^(r·t)"
    if shrink:
        formula = "V = P × (1 − r)^t  (depreciating by a fixed percentage)" if mc == 1 else formula
    sub = f"A = {_q(P_)} × {gs} = {_q(P_)} × {_q(g, 8)}"
    extra = []
    if mc == 0:
        extra.append(f"exact: {_q(P_)}·e^{_q(r * _fd(term[0]))}")
    if asked_interest and not shrink:
        answer = f"{p.ma(I)} interest" + (f" (balance {p.m(A)})" if asked_amount else "")
        extra.append(f"interest = A − P = {p.m(A)} − {p.m(P_)} = {p.m(I)}")
    elif shrink:
        answer = p.ma(A)
        extra.append(f"lost {p.m(-I)} of value")
    else:
        answer = p.ma(A)
        extra.append(f"interest = {p.m(A)} − {p.m(P_)} = {p.m(I)}")
    check = f"{p.m(A)} / {_q(g, 8)} = {p.m(A / g)} ✓"
    if not shrink and r > 0:
        check += f" (simple interest would give only {p.m(P_ * (1 + r * _fd(term[0])))})"
    return _sol(p, "finance", formula, knowns, sub, answer, check, extra)


# ---------------------------------------------------------------- discounts, tax and successive percentage changes

def _h_chain(p: P) -> Solution | None:
    if not p.pcts:
        return None
    timed = bool([k for k in p.toks if k.kind in TIME_KINDS])
    if timed and (p.monies or len(p.pcts) < 2 or any(_role(k) not in ("up", "down_chg") for k in p.pcts)):
        return None
    if p.has(r"\b(?:interest|loan|invest\w*|tip|split|apr|compound\w*|inflation|salary|wage)\b"):
        return None
    steps_ = []  # (kind, value, token)
    for k in p.pcts:
        role = _role(k)
        if role in ("off",):
            steps_.append(("off", k.v, k))
        elif role == "tax":
            steps_.append(("tax", k.v, k))
        elif role in ("up", "markup", "service"):
            steps_.append(("up", abs(k.v), k))
        elif role in ("down_chg", "loss"):
            steps_.append(("down", abs(k.v), k))
        elif role == "profit":
            steps_.append(("up", k.v, k))
        elif role is None and steps_ and steps_[-1][0] in ("up", "down") and \
                re.fullmatch(r"\s*(?:(?:by|another|a further|again|and|,)\s*)*", k.pre):
            steps_.append((steps_[-1][0], abs(k.v), k))  # "up 10% then by 10% again"
        else:
            return None
    fixed = []
    base = None
    for k in p.monies:
        if k.per:
            return None
        if re.match(r"^\s*(?:off|coupon|discount|rebate|voucher|cheaper|less)\b", k.post) or \
                re.search(r"(?:coupon|voucher|rebate|minus|less|subtract|another|extra|additional)\s*(?:of|for)?\s*$", k.pre) and base is not None:
            fixed.append((k.start, "minus", k.v))
        elif re.match(r"^\s*(?:shipping|delivery|fee|handling|surcharge|postage)", k.post) or \
                (re.search(r"(?:plus|\+|add|and)\s*$", k.pre) and base is not None and re.search(r"shipping|delivery|fee|handling", k.raw_post[:30])):
            fixed.append((k.start, "plus", k.v))
        elif base is None:
            base = k
        else:
            return None
    kinds = {s[0] for s in steps_}
    finance_role = bool(kinds & {"off", "tax"}) or p.cur or fixed
    if len(steps_) < 2 and not finance_role:
        return None
    if base is None and not (len(steps_) >= 2 or kinds & {"off"}):
        return None
    if base is None and len(steps_) < 2:
        return None
    seq = sorted([(k.start, kind, v) for kind, v, k in steps_] + fixed)
    lines = []
    factor = ONE
    for _, kind, v in seq:
        if kind in ("minus", "plus"):
            if base is None:
                return None
    reverse = base is not None and p.has(r"original(?:ly)?|regular price|full price|list price|pre-?tax|before (?:the )?(?:tax|discount|sale|"
                                         r"markdown|increase|decrease|drop|cut|rise|change)|marked price|starting price|initial price|"
                                         r"price before|what was the price|what did it (?:cost|sell for) before|what was it before|"
                                         r"what was the (?:value|amount) before")
    names = {"off": "off", "tax": "tax", "up": "increase", "down": "decrease"}
    if base is None:
        for _, kind, v in seq:
            f = 1 - v if kind in ("off", "down") else 1 + v
            factor *= f
            lines.append(f"{_pct(v)} {names[kind]}: × {_ds(f)}")
        change = factor - 1
        if kinds == {"off"}:
            answer = f"{p.pa(-change)} off in total"
            note = f"(not {_pct(sum(v for _, _, v in seq))}: each discount applies to an already reduced price)"
        elif p.has(r"\bprofit|\bloss\b|\bgain\b"):
            answer = f"{p.pa(abs(change))} {'profit' if change >= 0 else 'loss'}"
            note = "(multiply the factors; the percentages don't simply add)"
        else:
            answer = f"{'+' if change > 0 else ''}{p.pa(change)} overall" + (" (a net decrease)" if change < 0 else " (a net increase)" if change > 0 else " (back to the start)")
            note = "(changes multiply, they don't add: a % of a bigger or smaller number)"
        return _rule(p, "finance", "successive percentage changes multiply: overall factor = Π (1 ± pᵢ)",
                     lines + [f"overall factor = {' × '.join(_ds(1 - v if kd in ('off', 'down') else 1 + v) for _, kd, v in seq)} = {_ds(factor)}", note],
                     answer, f"on 100: {_q(100 * factor, 6)}, a change of {_q(100 * change, 6)} ✓")
    x = base.v
    if reverse:
        if fixed:
            return None
        for _, kind, v in seq:
            factor *= 1 - v if kind in ("off", "down") else 1 + v
        orig = x / factor
        lines = [f"{_pct(v)} {names[kind]}: × {_ds(1 - v if kind in ('off', 'down') else 1 + v)}" for _, kind, v in seq]
        return _sol(p, "finance", "original = final / Π (1 ± pᵢ)", [f"final = {p.m(x)}"] + [f"{_pct(v)} {names[kind]}" for _, kind, v in seq],
                    f"original = {_q(x)} / {_ds(factor)}", p.ma(orig), f"{p.m(orig)} × {_ds(factor)} = {p.m(orig * factor)} ✓", lines)
    cur = x
    saved_at = None
    for _, kind, v in seq:
        before = cur
        if kind == "minus":
            cur = cur - v
            lines.append(f"{p.m(v)} off: {_q(before)} − {_q(v)} = {_q(cur)}")
        elif kind == "plus":
            cur = cur + v
            lines.append(f"plus {p.m(v)}: {_q(before)} + {_q(v)} = {_q(cur)}")
        else:
            f = 1 - v if kind in ("off", "down") else 1 + v
            cur = cur * f
            label = {"off": f"{_pct(v)} off", "tax": f"{_pct(v)} tax", "up": f"+{_pct(v)}", "down": f"−{_pct(v)}"}[kind]
            lines.append(f"{label}: {_q(before)} × {_ds(f)} = {_q(cur, 4)}")
        if kind != "tax" and kind != "plus":
            saved_at = cur
    if p.has(r"how much (?:do|did|will|would) (?:i|we|you) save|\bsav(?:e|ing|ings)\b") and saved_at is not None and kinds & {"off"}:
        answer = f"{p.ma(x - saved_at)} saved"
        check = f"{p.m(x)} − {p.m(saved_at)} = {p.m(x - saved_at)} ✓"
    else:
        answer = p.ma(cur)
        overall = cur / x - 1 if x else ZERO
        check = f"overall {'+' if overall > 0 else ''}{_n(overall * 100)}%: {_q(x)} × {_q(cur / x, 8)} = {p.m(cur)} ✓" if not fixed else \
            f"{' then '.join(l.split(':')[0] for l in lines)} ✓"
    return _rule(p, "finance", "apply each change in order to the running price (percentages multiply)", [f"start: {p.m(x)}"] + lines,
                 answer, check)


# ---------------------------------------------------------------- entry point

HANDLERS = [
    _h_salary, _h_brackets, _h_breakeven, _h_margin, _h_roi, _h_geo_return, _h_markup, _h_tip, _h_inflation, _h_ear,
    _h_double, lambda p: _h_simple(p, True), _h_loan, _h_annuity, _h_pv, lambda p: _h_simple(p, False), _h_compound,
    _h_chain,
]


def solve(text: str) -> Solution | None:
    """A personal finance or business maths problem in plain English, solved with steps; None when it isn't one."""
    if not text or len(text) > 600:
        return None
    with localcontext() as ctx:
        ctx.prec = 50
        try:
            p = _parse(text)
            if p is None:
                return None
            for h in HANDLERS:
                sol = h(p)
                if sol is not None:
                    return sol
        except (ArithmeticError, ValueError, TypeError, IndexError, KeyError, AttributeError, StopIteration):
            return None
    return None
