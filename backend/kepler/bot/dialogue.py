"""Conversation memory for maths: follow-ups that only make sense after the previous question.

  "sum of first 10 cubes" → "and for 20?" / "what about 50"   → same question, new number
                          → "what about squares?"              → same question, swapped word
  "15% of 200" → "double it" / "add 5" / "is it prime?" / "in binary?" / "square root of that" → use the last answer
  anything → "why?" / "how?" / "show the steps"                → show the last working again

Rules only. `rewrite()` returns the full question to answer instead (or STEPS), with a note on how it was read.
"""
import re
from dataclasses import dataclass

STEPS = "__steps__"
N = r"-?\d+(?:\.\d+)?"

SWAPS = [
    ["natural numbers", "odd numbers", "even numbers", "whole numbers", "squares", "cubes", "primes", "prime numbers",
     "fibonacci numbers", "digits", "integers", "numbers"],
    ["km", "miles", "meters", "feet", "inches", "yards", "cm", "mm"], ["kg", "pounds", "lb", "grams", "ounces"],
    ["binary", "hex", "octal", "roman numerals"], ["celsius", "fahrenheit", "kelvin"],
    ["sum", "product", "average", "mean", "median", "mode", "range", "variance", "std"],
    ["derivative", "integral"], ["seconds", "minutes", "hours", "days", "weeks", "years"],
    ["heads", "tails"], ["simple", "compound"],
]


@dataclass
class Memory:
    question: str = ""      # the last maths question, as solved
    answer: str = ""        # its answer text
    solution: object = None

    @property
    def value(self) -> str | None:
        """The main number in the last answer ("x = 2" → 2, "$30" → 30, "5,050" → 5050)."""
        m = re.search(r"-?\d[\d,]*(?:\.\d+)?(?:/\d+)?", self.answer)
        return m.group(0).replace(",", "") if m else None


def _replace_parameter(q: str, new: str) -> str | None:
    m = re.search(r"\bfirst (\d+|[a-z])\b", q)
    if m:
        return q[:m.start(1)] + new + q[m.end(1):]
    nums = list(re.finditer(N, q))
    if not nums:
        m = re.search(r"\b(n)\b", q)
        return q[:m.start(1)] + new + q[m.end(1):] if m else None
    last = nums[-1]
    return q[:last.start()] + new + q[last.end():]


def rewrite(text: str, mem: Memory) -> tuple[str, str] | None:
    """→ (question to answer, how it was read) for a follow-up, else None."""
    if not mem.question:
        return None
    t = text.lower().strip().rstrip("?!. ")
    if re.fullmatch(r"(?:why|how|how so|how come|explain|explain (?:it|that|this|again)|show (?:me )?(?:the )?(?:steps|working|work|reasoning)|"
                    r"how did you get (?:that|it|this)|can you explain(?: that| it)?|walk me through it|steps|working)", t):
        return STEPS, "showing the working again"
    v = mem.value
    # operations on the last answer
    if v is not None:
        ops = [
            (r"(?:now )?double (?:it|that|the answer|the result)|(?:it|that) times 2|multiply (?:it|that) by 2", f"2 * {v}"),
            (r"(?:now )?triple (?:it|that|the answer|the result)", f"3 * {v}"),
            (r"(?:now )?(?:halve|half of) (?:it|that|the answer|the result)|(?:it|that) divided by 2", f"{v} / 2"),
            (r"(?:now )?square (?:it|that|the answer|the result)|(?:it|that) squared", f"{v}^2"),
            (r"(?:now )?cube (?:it|that|the answer|the result)|(?:it|that) cubed", f"{v}^3"),
            (r"(?:what is |what's )?(?:the )?square root of (?:it|that|the answer|the result)|(?:root|sqrt) (?:it|that)", f"sqrt({v})"),
            (rf"(?:now |and )?(?:add|plus) ({N})(?: to (?:it|that|the answer|the result))?", "{v} + {0}"),
            (rf"(?:now |and )?(?:subtract|minus|take away) ({N})(?: from (?:it|that|the answer|the result))?", "{v} - {0}"),
            (rf"(?:now |and )?(?:multiply (?:it|that|the answer|the result) by|times|multiplied by) ({N})", "{v} * {0}"),
            (rf"(?:now |and )?(?:divide (?:it|that|the answer|the result) by|divided by) ({N})", "{v} / {0}"),
            (r"(?:is|was) (?:it|that|the answer|the result|this) (?:a )?prime(?: number)?", f"is {v} prime"),
            (r"(?:is|was) (?:it|that|the answer|the result|this) (even|odd)", "is {v} {0}"),
            (r"(?:is|was) (?:it|that|the answer|the result|this) (?:a )?perfect (square|cube)", "is {v} a perfect {0}"),
            (r"(?:what is |what's |show |convert )?(?:it|that|the answer|the result|this)? ?(?:in|to|into|as) (binary|hex|hexadecimal|octal|roman numerals?|roman)",
             "{v} in {0}"),
            (r"(?:what are )?(?:the )?(divisors|factors|prime factors) of (?:it|that|the answer|the result)", "{0} of {v}"),
            (r"(?:what is |what's )?(\d+)% of (?:it|that|the answer|the result)", "{0}% of {v}"),
        ]
        if "." in v or "/" in v:
            ops = [o for o in ops if not re.search(r"prime|even|odd|perfect|binary|divisors", o[0])]
        for pat, tpl in ops:
            m = re.fullmatch(pat, t)
            if m:
                q = tpl.format(*m.groups(), v=v) if "{" in tpl else tpl
                return q, f"using the last answer ({v}): {q}"
    # same question, new number: "and for 20", "what about 50", "now n", "with 100", "if it was 7"
    m = re.fullmatch(rf"(?:and |ok |so |now |then )*(?:what about|how about|for|with|and for|if (?:it was|it is|n is|n was|n =)|n =|try|same for|same with|do)?\s*({N}|n)%?", t)
    if m and (not re.fullmatch(N, t) or re.match(r"(?:and|what|how|for|with|now|same|if|try|do)\b", text.strip().lower())):
        new = m.group(1)
        if "%" in t and re.search(rf"{N}%", mem.question):
            q = re.sub(rf"{N}%", new + "%", mem.question, count=1)
        else:
            q = _replace_parameter(mem.question, new)
        if q and q != mem.question:
            return q, f"same question with {new}: {q}"
    # same question, swapped word: "what about cubes", "and in miles", "now the median"
    m = re.fullmatch(r"(?:and |ok |so |now |then )*(?:what about|how about|and|now|same (?:for|with)|in|for|the|with)\s+(?:the |in )?(.+)", t)
    if m:
        word = m.group(1).strip()
        for group in SWAPS:
            if word in group or word.rstrip("s") in group or word + "s" in group:
                target = word if word in group else (word.rstrip("s") if word.rstrip("s") in group else word + "s")
                for other in sorted(group, key=len, reverse=True):
                    if other != target and re.search(rf"\b{re.escape(other)}\b", mem.question):
                        q = re.sub(rf"\b{re.escape(other)}\b", target, mem.question, count=1)
                        return q, f"same question with {target}: {q}"
    return None
