"""Kepler's English layer: turn casual, misspelt, texting-style English into plain English before anything else.

Deterministic rules (no language model):
  1. tidy: spacing, curly quotes, repeated punctuation
  2. slang & contractions: wats → what is, u → you, plz → please, rn → right now, dont → do not, …
  3. spelling: unknown words are corrected to the closest known word (same first letter, ≥ 82 % similar),
     never touching metric names, numbers, or words you taught it
  4. number words: "fifteen percent of two hundred" → "15 percent of 200"
  5. maths phrasing: "add 5 and 7" → "5 + 7", "subtract 3 from 10" → "10 - 3", "2 4 8 16" after "next" → "2, 4, 8, 16"
  6. your own aliases from `kepler teach` (/alias brb = be right back)

`normalise()` returns the new text; `explain_changes()` lists what was changed, so the chat can show "read as: …".
"""
import difflib
import re
from functools import lru_cache

SLANG = {
    "u": "you", "ya": "you", "yu": "you", "r": "are", "ur": "your", "urs": "yours", "wat": "what", "wht": "what",
    "wut": "what", "wot": "what", "wats": "what is", "whats": "what is", "wat's": "what is", "what's": "what is",
    "whatre": "what are", "what're": "what are", "hw": "how", "hows": "how is", "how's": "how is", "whos": "who is",
    "who's": "who is", "wheres": "where is", "where's": "where is", "thats": "that is", "that's": "that is",
    "theres": "there is", "there's": "there is", "heres": "here is", "here's": "here is", "im": "i am", "i'm": "i am",
    "ive": "i have", "i've": "i have", "id": "i would", "i'd": "i would", "ill": "i will", "i'll": "i will",
    "youre": "you are", "you're": "you are", "dont": "do not", "don't": "do not", "doesnt": "does not",
    "doesn't": "does not", "didnt": "did not", "didn't": "did not", "isnt": "is not", "isn't": "is not",
    "arent": "are not", "aren't": "are not", "wasnt": "was not", "wasn't": "was not", "cant": "cannot",
    "can't": "cannot", "wont": "will not", "won't": "will not", "shouldnt": "should not", "couldnt": "could not",
    "wouldnt": "would not", "lets": "let us", "let's": "let us", "gonna": "going to", "wanna": "want to",
    "gimme": "give me", "lemme": "let me", "dunno": "do not know", "kinda": "kind of", "sorta": "sort of",
    "pls": "please", "plz": "please", "plez": "please", "pleas": "please", "thx": "thanks", "thnx": "thanks",
    "thanx": "thanks", "ty": "thanks", "tysm": "thank you so much", "rn": "right now", "atm": "at the moment",
    "b4": "before", "2day": "today", "tmrw": "tomorrow", "tmr": "tomorrow", "pic": "picture", "msg": "message",
    "shw": "show", "sho": "show", "nums": "numbers", "numbs": "numbers", "num": "number", "nos": "numbers",
    "avg": "average", "sq": "square", "sqr": "square", "tot": "total", "approx": "approximately", "abt": "about",
    "bc": "because", "cuz": "because", "coz": "because", "w/": "with", "w/o": "without", "btw": "by the way",
    "idk": "i do not know", "imo": "in my opinion", "k": "ok", "kk": "ok", "okay": "ok", "okey": "ok", "yep": "yes",
    "yeah": "yes", "ya'll": "you all", "yall": "you all", "nope": "no", "nah": "no", "hii": "hi", "hiii": "hi",
    "helo": "hello", "hellow": "hello", "hey there": "hey", "sup": "what is up", "wassup": "what is up",
    "whatsup": "what is up", "info": "information", "stat": "status", "stats": "statistics", "calc": "calculate",
    "eqn": "equation", "eq": "equation", "diff": "difference", "prod": "product", "xplain": "explain",
}

CORE_WORDS = """a about above add added after again against all almost along also always am among amount an and another
answer any anyone anything are area around as ask at average away back bad be because been before being below best
better between big both break broken but by calculate can change chart check choose come comes compare compute
connect consecutive convert copy cost could count cube cubes current dashboard data day days decide define definition
describe detail details did difference different digit digits divide divided do does doing done double down drop
during each easy either else empty end enough equal equals error errors even ever every everything example explain
false far fast few find fine first fix for from full get give go going good graph greater half happen happened has
have health healthy hello help her here high him his history hour hours how hundred i if in incident incidents
inject instead integer integers into is issue it its just keep know label large last latency latest less let level
like list little long look looking looks low lower make many mark maths mean meaning median metric metrics minus minute
minutes mode model models more most much multiply must my natural need never new next no normal not nothing now number
numbers odd of off ok on once one only open or order other our out over percent percentage plot plus please prime
primes probability problem product question quick quickly rate ratio real reason recent region remove result right
same say second see segment sequence series set settings should show since size slice slow small so some something
spike square squares start status still subtract sum sure take tell than thanks that the their them then there these
they thing things think third this those three through time times to today together too total train trend true try
twice two under understand until up use value very wait want was watch way we week well were what when where which
while who why will with without work worry would wrong year years yes yesterday you your zero
squared cubed equals multiplied divided plus minus percent subtracted increased decreased doubled tripled halved dozen
about above across actually again agree ahead allow alone along already although among another anyone appear apply
around arrive aside asked avoid aware basic became become begin behind believe beside beyond bring broke brought build
built business called cannot cause certain chance cheap child choice claim class clear close coming common company
course cover create crowd daily death degree depend design develop difficult dinner doctor early earth eight empty
enjoy enter entire equal event exact except expect extra family father field fight figure final floor focus follow
force forget forty found frame friend front funny given glass great green group guess happy heart heavy house human
idea image inside issue items known large later laugh layer learn least leave light limit local longer lucky major
maybe means might million minor money month morning mother mouth moved movie music night noise north often paper
party peace phone piece place plain plane plant point power press price print prior proof proud prove quiet quite
radio raise reach ready really reply river round route rules scale scene score sense serve seven shall shape share
sharp short shown sides sixty skill sleep smart smile solid sorry sound south space speak spend split staff stage
stand state steps stock stone store story study stuff style sugar table taken teach teeth thank theme there thick
throw tight timer title touch tough tower track trade treat trial tried truck truly trust truth union upper usual
valid video visit voice waste water wheel where white whole whose woman women world worse worst worth write young
yours information question questions answer answers meaning simple english words sentence understand""".split()


@lru_cache(maxsize=1)
def _base_vocab() -> frozenset:
    words = set(CORE_WORDS)
    try:
        from .intents import FILL, INTENTS
        for spec in INTENTS.values():
            for tpl in spec["t"]:
                words.update(re.findall(r"[a-z]+", re.sub(r"\{\w+\}", " ", tpl.lower())))
        for vals in FILL.values():
            for v in vals:
                words.update(re.findall(r"[a-z]+", str(v).lower()))
    except ImportError:
        pass
    try:
        from .knowledge import vocabulary
        words.update(vocabulary())
    except ImportError:
        pass
    words.update("""natural whole counting positive negative fibonacci divisor divisors factor factors factorial binary hex
    hexadecimal octal roman decimal fraction fractions equation equations solve solution derivative integral integrate
    differentiate limit simplify expand quadratic polynomial root roots sqrt logarithm log sine cosine tangent degrees
    radians percent discount interest compound simple profit loss speed distance travel travels kilometers miles meters
    feet inches celsius fahrenheit kelvin seconds weeks months heads legs chickens cows workers pencils older younger
    ages average mean probability dice coin coins tosses cards deck arrange arrangements combinations permutations choose
    handshakes ratio divide share consecutive digits term terms pattern comes kepler anomaly anomalies baseline confidence
    orbit area tiers tier sensitivity slack datadog grafana prometheus sentry posthog mixpanel amplitude cloudwatch
    postgres segment webhook signups sessions latency failures joke meaning life robot human""".split())
    # maths and science words the spell checker must leave alone ("converge" is not a typo for "convert")
    words.update("""converge converges convergent diverge diverges divergent series sum sums summation infinite infinity
    matrix matrices determinant eigenvalue eigenvalues eigenvector inverse transpose rank vector vectors
    prove proof proved induction identity irrational rational theorem conjecture hypothesis lemma modulo congruent
    differential ode velocity acceleration accelerates accelerating force forces mass weight kinetic potential energy
    momentum friction gravity density pressure wavelength frequency resistor resistance voltage volts current amps
    ampere ohm ohms watt watts kilowatt joules newton newtons hertz circuit dropped falls falling thrown stone
    molar molarity moles mole molecule molecules atom atoms compound acid acids base bases ph solution grams
    loan mortgage payment payments invest investment monthly annual annually growth cagr inflation principal
    deviation variance standard median mode zscore normal distribution hypotenuse triangle rectangle circle sphere
    cylinder cone radius diameter circumference perimeter volume trigonometry sin cos tan""".split())
    # everyday words of small talk ("off to lunch" is not "off to launch")
    words.update("""lunch dinner breakfast coffee tea bed sleep nap meeting meetings weekend holiday vacation tomorrow tonight
    morning afternoon evening night later soon bye goodbye cheers mate buddy dude bro lol haha joke jokes funny bored
    tired lonely busy day week weather hungry gym home office team boss friend family kids son daughter wife husband
    smart clever helpful useless awesome amazing robot human alive feel feeling fine okay alright sorry please""".split())
    try:
        from .fields import UNITS
        words.update(w for u in UNITS for w in re.findall(r"[a-z]+", u))
    except ImportError:
        pass
    return frozenset(w for w in words if len(w) > 1)


_LIB_CACHE: dict = {}


def _library_words() -> frozenset:
    """Every word the library knows (dictionary lemmas + article title words): never 'corrected'.
    Cached per library file version."""
    try:
        from ..library import index
        p = index.path()
        if not p.exists():
            return frozenset()
        key = (str(p), int(p.stat().st_mtime // 300))  # refresh at most every 5 minutes while importing
        if _LIB_CACHE.get("key") != key:
            words = set()
            with index.session() as c:
                for (lemma,) in c.execute("SELECT DISTINCT lemma FROM words"):
                    words.update(lemma.split())
                for (title,) in c.execute("SELECT title FROM docs"):
                    words.update(re.findall(r"[a-z]+", title.lower()))
            _LIB_CACHE.update(key=key, words=frozenset(words))
        return _LIB_CACHE["words"]
    except Exception:  # noqa: BLE001 - a missing / busy library must never break understanding
        return frozenset()


def _user_aliases() -> dict:
    try:
        from . import store
        return store.load().get("aliases", {})
    except Exception:  # noqa: BLE001 - a broken training file must never break understanding
        return {}


def _user_words() -> set:
    try:
        from . import store
        data = store.load()
        out = set()
        for e in data["examples"]:
            out.update(re.findall(r"[a-z]+", e["text"].lower()))
        out.update(data["intents"])
        return out
    except Exception:  # noqa: BLE001
        return set()


def spell(word: str, vocab) -> str:
    """Closest known word, or the word itself. Conservative on purpose: same first letter, high similarity."""
    if len(word) < 5 or word in vocab or not word.isalpha():
        return word
    pool = [w for w in vocab if w[0] == word[0] and abs(len(w) - len(word)) <= 2]
    best = difflib.get_close_matches(word, pool, n=1, cutoff=0.84 if len(word) <= 6 else 0.8)
    return best[0] if best else word


N = r"-?\d+(?:\.\d+)?"


def _maths_phrasing(t: str) -> str:
    t = re.sub(rf"\badd (?:up )?({N}) (?:and|to|with|plus) ({N})\b", r"\1 + \2", t)
    t = re.sub(rf"\b(?:multiply|times) ({N}) (?:and|by|with|times|x) ({N})\b", r"\1 * \2", t)
    t = re.sub(rf"\bsubtract ({N}) from ({N})\b", r"\2 - \1", t)
    t = re.sub(rf"\btake (?:away )?({N}) from ({N})\b", r"\2 - \1", t)
    t = re.sub(rf"\bdivide ({N}) by ({N})\b", r"\1 / \2", t)
    t = re.sub(rf"\b(?:the )?difference (?:between|of) ({N}) and ({N})\b", r"\1 - \2", t)
    t = re.sub(rf"\b(?:the )?product of ({N}) and ({N})$", r"\1 * \2", t)
    t = re.sub(rf"\b(?:the )?quotient of ({N}) and ({N})\b", r"\1 / \2", t)
    t = re.sub(rf"\b({N}) (?:multiplied|times) by ({N})\b", r"\1 * \2", t)
    t = re.sub(r"\b(?:add up|total(?: up)?|sum up|sum|addition of)(?: of)? (?:all )?(?:the )?first\b", "sum of the first", t)
    t = re.sub(r"\bsum of the first first\b", "sum of the first", t)
    # "what comes after 2 4 8 16" → "2, 4, 8, 16"
    t = re.sub(rf"(?<![\d,.])((?:{N}\s+){{2,}}{N})(?![\d.])",
               lambda m: ", ".join(m.group(1).split()) if re.search(r"next|after|comes|sequence|series|pattern|term|continue|average|mean|median|sum of|mode|std|gcd|lcm", t) else m.group(1), t)
    t = re.sub(r"\s+(?:equals|is equal to|is the same as)\s+(?=-?[\d(a-z])", " = ", t) if re.search(r"\d|\b[a-z]\b", t) else t
    t = re.sub(r"\bis there (?:a |any )?primes? (?:numbers? )?between\b", "primes between", t)
    t = re.sub(r"\bare there (?:any )?primes? (?:numbers? )?between\b", "primes between", t)
    return t


def normalise(text: str, protect: set | None = None) -> str:
    from .wordmath import words_to_numbers
    t = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("…", "...")
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r'"([^"]{1,30})"', r"\1", t)  # quoted words / numbers: 'sum of "x" digits'
    t = re.sub(r"([?!])\1+", r"\1", t)
    t = re.sub(r"\.{4,}", "...", t)  # keep "..." (1 + 2 + ... + n); squash longer runs
    t = re.sub(r"\b1st (?=\d|n\b|few\b)", "first ", t)
    low = t.lower()
    aliases = _user_aliases()
    # capitalised words mid-sentence are names (Tom, Jerry, Datadog): never spell-correct them
    names = {w.lower() for w in re.findall(r"(?<=[a-z,] )[A-Z][a-z]+", t)}
    protect = set(protect or ()) | names
    known = _library_words()
    protect = protect | {w for w in re.findall(r"[a-z]+", low) if w in known}
    vocab = _base_vocab() | _user_words() | protect | set(aliases)
    out = []
    for tok in re.findall(r"[\w'/]+|[^\w\s]", low):
        if tok in aliases:
            out.append(aliases[tok])
        elif tok in SLANG:
            out.append(SLANG[tok])
        elif tok.isalpha() and tok in protect:
            out.append(tok)
        elif tok.isalpha():
            out.append(spell(tok, vocab))
        else:
            out.append(tok)
    t = " ".join(out)
    t = re.sub(r" ([?!.,;:%)])", r"\1", t)
    t = re.sub(r"([(#$£€₹]) ", r"\1", t)
    t = re.sub(r"(\d) ?\. ?(\d)", r"\1.\2", t)  # decimals the tokeniser split ("2. 5" → "2.5")
    t = re.sub(r"(\w)' (\w)", r"\1'\2", t)
    t = re.sub(r"\s*([+*/^=])\s*", r" \1 ", t)
    t = re.sub(r"(?<=\d )(km|m|cm|mi|g|kg|mol|kj|j) / (m \^ [23]|cm \^ 3|s \^ 2|h|hr|sec|s|min|mol|ml|l|kg)\b",
               lambda m: f"{m.group(1)}/{m.group(2).replace(' ', '')}", t)  # units stay whole: "60 km/h", "9.8 m/s^2"
    t = re.sub(r"(\d)\s*-\s*(\d)", r"\1 - \2", t)
    t = re.sub(r"(^|[(=,]\s?|[a-z] )- (\d)", r"\1-\2", t)  # a minus sign ("is - 3 even"), not subtraction ("127 - 1")
    t = re.sub(r"([<>!=]) = ", r"\1= ", t)                   # ">=", "<=", "!=", "==" stay one operator
    t = re.sub(r"\s*\. \. \.\s*|\s*\.\s*\.\s*\.\s*", " ... ", t)  # "+ . . . +" → "+ ... +"
    t = re.sub(r"\s*,\s*", ", ", t)
    t = re.sub(r"\b([a-z])\s*\(\s*([a-z0-9]+)\s*\)", r"\1(\2)", t)
    t = re.sub(r"(\d)\s+%", r"\1%", t)
    for phrase, rep in aliases.items():
        if " " in phrase:
            t = re.sub(rf"\b{re.escape(phrase)}\b", rep, t)
    t = words_to_numbers(t)
    t = _maths_phrasing(t)
    return re.sub(r"\s+", " ", t).strip()


def changed(original: str, new: str) -> bool:
    """Whether the rewrite is worth showing ("read as: …"): more than spacing, case and punctuation."""
    def key(s):
        return re.sub(r"[^a-z0-9+\-*/=%]", "", s.lower())
    return key(original) != key(new)
