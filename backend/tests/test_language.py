"""The English layer, the knowledge base and conversation follow-ups."""
import pytest

from kepler.bot import knowledge, store
from kepler.bot.language import normalise
from kepler.bot.mind import Mind

READ_AS = {
    "wats 2  plus   2": "what is 2 plus 2",
    "plz tell me wat is 15 percent of 200": "please tell me what is 15 percent of 200",
    "how much is fifteen percent of two hundred": "how much is 15 percent of 200",
    "sum of 1st 10 natural numbers": "sum of the first 10 natural numbers",
    "add up first n numbers": "sum of the first n numbers",
    "sum first 5 odd nums": "sum of the first 5 odd numbers",
    "anythign broken?": "anything broken?",
    "shw me api erors": "show me api errors",
    "hw r things": "how are things",
    "add 5 and 7": "5 + 7",
    "multiply 12 and 7": "12 * 7",
    "subtract 3 from 10": "10 - 3",
    "divide 100 by 4": "100 / 4",
    "difference between 50 and 20": "50 - 20",
    "wat comes after 2 4 8 16": "what comes after 2, 4, 8, 16",
    "x squared minus 4 equals 0": "x squared minus 4 = 0",
}


@pytest.mark.parametrize("text", list(READ_AS))
def test_read_as(text):
    assert normalise(text) == READ_AS[text]


@pytest.mark.parametrize("text", ["is there space for one more", "show api_errors last 6h", "explain #40",
                                  "is p95_latency_ms ok", "Tom is twice as old as Jerry", "connect datadog",
                                  "show me the farm", "break down signups by platform", "f(x) = 2x + 3, find f(5)"])
def test_never_corrupts_normal_words_names_or_metrics(text):
    out = normalise(text)
    for word in ("space", "there", "api_errors", "#40", "p95_latency_ms", "jerry", "datadog", "farm", "signups", "f(x)"):
        if word in text.lower():
            assert word in out, (text, out)


def test_aliases_teach_new_words():
    store.add_alias("sigs", "signups")
    assert normalise("is sigs ok") == "is signups ok"


ANSWERS = [
    ("wats 2  plus   2", "math", "4"),
    ("how much is fifteen percent of two hundred", "math", "30"),
    ("is there any prime between 20 and 30", "math", "23, 29"),
    ("x squared minus 4 equals 0", "math", "x = -2, x = 2"),
    ("what is a prime number", "knowledge", "only divisors"),
    ("what does anomaly mean", "knowledge", "far from what Kepler expected"),
    ("define median", "knowledge", "middle value"),
    ("who are you", "knowledge", "I'm Kepler"),
    ("are u an ai", "knowledge", "not a language model"),
    ("how r u", "knowledge", ""),  # small talk: one of several replies
    ("show the last five incidents", "intent", ""),
    ("explain incident 40", "intent", ""),
    ("explain the latest incident", "intent", ""),
    ("what are the open incidents", "intent", ""),
]


@pytest.mark.parametrize("text,kind,expect", ANSWERS)
def test_pipeline(text, kind, expect):
    th = Mind().think(text)
    assert th.kind == kind, (text, th)
    if kind == "math":
        assert th.solution.answer == expect
    elif kind == "knowledge":
        assert expect in th.knowledge["text"]


def test_follow_ups_keep_the_conversation():
    m = Mind()
    steps = [("sum of first 10 cubes", "3025"), ("and for 20?", "44,100"), ("what about squares", "2870"),
             ("double it", "5740"), ("is it even", "yes"), ("why?", "yes")]
    for text, answer in steps:
        th = m.think(text)
        assert th.kind in ("math", "steps"), text
        assert th.solution.answer == answer, (text, th.solution.answer)
    assert m.think("why?").kind == "steps"
    m.think("is signups ok")  # a Kepler question ends the maths thread …
    assert m.think("why").kind == "intent"  # … so "why" is about the metric again


def test_follow_up_number_words_and_conversions():
    m = Mind()
    assert m.think("15% of 200").solution.answer == "30"
    assert m.think("what about 300?").solution.answer == "45"
    assert m.think("in binary").solution.answer == "101101"


def test_knowledge_does_not_take_kepler_commands():
    for text in ("explain incident", "what is the status", "what are the open incidents", "describe the latest incident"):
        assert knowledge.answer(text) is None, text


def test_lessons_beat_maths_and_knowledge():
    store.add_example("what is a median", "what is a median", "help")
    assert Mind().think("what is a median").kind == "intent"
