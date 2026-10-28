"""Reading what people mean: concepts named anywhere in a question, general-knowledge questions behind chatter,
small talk, and messages about your own systems that must stay Kepler commands."""
import pytest

from kepler.bot import knowledge, language
from kepler.bot.mind import LEAD_IN, WORLD, Mind


def ask(q):
    return knowledge.answer(language.normalise(q))


@pytest.mark.parametrize("q,title", [
    ("Can you tell me what a standard deviation is measuring?", "standard deviation"),
    ("z-score meaning??", "z-score"),
    ("voltage?", "voltage"),
    ("what's the point of variance in stats anyway", "variance"),
    ("so what makes a number prime? my son keeps asking me", "prime"),
    ("Explain what a factorial is in math and why they blow up so fast", "factorial"),
    ("logarithms. the word alone makes me panic. what are they actually for", "logarithm"),
])
def test_concepts_found_in_any_wording(q, title):
    a = ask(q)
    assert a and a["kind"] == "definition" and a["title"] == title


def test_comparison_picks_the_pair_joined_by_or():
    a = ask("which is better to report when there are big outliers, mean or median")
    assert a["kind"] == "comparison" and a["title"] == "mean vs median"


@pytest.mark.parametrize("q", [
    "why is latency so high", "what's wrong with latency", "latency", "set sensitivity to 80%", "is signups ok",
    "standard deviation of 2, 4, 4, 4, 5", "explain incident 40", "compare orbit area and time", "what is 2+2",
    "how is checkout_errors looking", "which model should i use", "mute latency for an hour", "hiya kepler",
    "can you split the payments number by country for me", "time model for logins only pls",
    "did u ping slack about anything overnight",
])
def test_commands_and_calculations_are_not_definitions(q):
    a = ask(q)
    assert a is None or a["kind"] not in ("definition", "comparison"), (q, a)


@pytest.mark.parametrize("q,core", [
    ("quick one before my meeting, what's the longest river in south america?", "what is the longest river in south america?"),
    ("while i have you, could you possibly tell me which river runs through cairo?", "which river runs through cairo?"),
    ("lol what's the capital of australia again", "what is the capital of australia again"),
])
def test_world_questions_behind_chatter(q, core):
    got = LEAD_IN.sub("", language.normalise(q), count=1)
    assert got == core and WORLD.match(got)


@pytest.mark.parametrize("q", ["how's your day going", "ok I'm off to lunch, catch you later", "never mind, forget I asked",
                               "you're pretty smart for a watchdog tool", "who tf came up with u lol", "wassup kepler"])
def test_small_talk(q):
    a = ask(q)
    assert a and a["kind"] == "small_talk", q


@pytest.mark.parametrize("q", ["walk me through incident 142, why'd it page", "why's checkout_errors climbing since 02:10"])
def test_failed_maths_about_your_systems_stays_a_command(q, tmp_path, monkeypatch):
    import kepler.device as device
    monkeypatch.setattr(device, "HOME", tmp_path)
    assert Mind().think(q).kind == "intent"
