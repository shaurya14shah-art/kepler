"""Field problems in plain English (physics, electrical, chemistry, finance, statistics, geometry) and the English layer
that reads indirect questions, comparisons and small talk."""
import pytest

from kepler.bot import fields, knowledge, language
from kepler.bot.mind import Mind

ANSWERS = {
    "a car accelerates from 0 to 27 m/s in 9 seconds, what is its acceleration?": "3 m/s²",
    "a 5 kg box is pushed with 20 N, what's its acceleration": "4 m/s²",
    "how far does an object fall in 3 seconds?": "44.15 m",
    "how long does a stone dropped from 20 m take to hit the ground?": "2.019 s",
    "what is the kinetic energy of a 2 kg ball moving at 3 m/s?": "9 J",
    "what is the weight of a 10 kg bag": "98.1 N",
    "momentum of a 1000 kg car at 20 m/s": "20,000 kg·m/s",
    "what current flows through a 10 ohm resistor at 5 volts?": "0.5 A",
    "power of a 12 V device drawing 2 A": "24 W",
    "power used by a 60 W bulb in 5 hours in kWh": "0.3 kWh",
    "molar mass of H2O": "18.02 g/mol",
    "molar mass of Ca(OH)2": "74.09 g/mol",
    "molar mass of h2so4": "98.07 g/mol",
    "how many moles in 36 g of water": "1.998 mol",
    "what is the pH of a 0.001 M HCl solution": "3",
    "pH of 0.01 M NaOH": "12",
    "monthly payment on a 200000 loan at 6% for 30 years": "1,199.10 a month",
    "if i invest 500 a month at 7% for 20 years how much will i have": "260,463.33",
    "revenue grew from 100 to 200 in 5 years, what is the annual growth rate": "14.87% a year",
    "z score of 85 if mean is 70 and sd is 10": "z = 1.5 (higher than 93.32% of values, for a normal distribution)",
    "probability a value is less than 85 if mean is 70 and sd is 10": "0.9332 (93.32%)",
    "area of a circle with radius 7": "153.9 square units (exactly 49⋅π)",
    "hypotenuse of a right triangle with sides 3 and 4": "5",
    "volume of a sphere with radius 3 cm": "113.1 cm³",
    "sin of 30 degrees": "1/2 ≈ 0.5",
    "cosine of 60 degrees": "1/2 ≈ 0.5",
    "sine of 60 degrees": "√3/2 ≈ 0.866",
    "cos of 45 degrees": "√2/2 ≈ 0.7071",
}


@pytest.mark.parametrize("q", ANSWERS)
def test_field_answers(q):
    s = fields.solve(q)
    assert s is not None and s.ok, q
    assert s.answer == ANSWERS[q]
    assert s.steps[0].startswith("formula:") and any(st.startswith("substitute:") for st in s.steps)


@pytest.mark.parametrize("q", ["what is the current status", "switch to area", "why did signups drop", "power of 2 is 8",
                               "show the density of alerts", "mute signups for 2 hours", "what is the speed of light"])
def test_not_field_problems(q):
    assert fields.solve(q) is None


def test_quantities_are_in_si():
    qs = fields.quantities("a train at 72 km/h for 30 minutes carrying 2 tonnes")
    got = {q.dim: q.value for q in qs}
    assert got["vel"] == pytest.approx(20) and got["time"] == 1800 and got["mass"] == 2000


def test_formula_mass_handles_groups():
    m, parts = fields.formula_mass("Ca(OH)2")
    assert m == pytest.approx(74.09, abs=0.01) and any(p.startswith("O 2") for p in parts)
    assert fields.formula_mass("Xy2") is None


@pytest.mark.parametrize("q", ["a car accelerates from 0 to 27 m/s in 9 seconds, what is its acceleration?",
                               "what is the pH of a 0.001 M HCl solution", "molar mass of H2O",
                               "how long does it take to drive 150 km at 60 km/h"])
def test_chat_solves_field_problems(q):
    th = Mind().think(q)  # through the whole chat path: normalising must not break "m/s", "0.001" or "H2O"
    assert th.kind == "math" and th.solution.ok


def test_normalise_keeps_decimals_and_units():
    assert language.normalise("what is 2.5 + 1.25") == "what is 2.5 + 1.25"
    assert "60 km/h" in language.normalise("drive at 60 km/h")
    assert "9.8 m/s^2" in language.normalise("accelerates at 9.8 m/s^2")


@pytest.mark.parametrize("q,title", [
    ("can u tell me what a median is", "median"),
    ("i don't get what an anomaly is, explain like i'm five", "anomaly"),
    ("could you explain what kinetic energy means", "kinetic energy"),
    ("i want to know what cagr is", "cagr"),
    ("explain like i'm 5 what a mole is", "mole"),
])
def test_indirect_definitions(q, title):
    a = knowledge.answer(language.normalise(q))
    assert a and a["kind"] == "definition" and a["title"] == title


@pytest.mark.parametrize("q,title", [
    ("what's the difference between mean and median", "mean vs median"),
    ("speed vs velocity", "speed vs velocity"),
    ("how is mass different from weight", "mass vs weight"),
    ("is variance the same as standard deviation", "variance vs standard deviation"),
])
def test_comparisons(q, title):
    a = knowledge.answer(language.normalise(q))
    assert a and a["kind"] == "comparison" and a["title"] == title and "The difference:" in a["text"]


@pytest.mark.parametrize("q", ["hey there, how's it going?", "what's your name", "lol", "i have a physics question",
                               "tell me something interesting"])
def test_small_talk(q):
    a = knowledge.answer(language.normalise(q))
    assert a and a["kind"] == "small_talk"


def test_topic_tour():
    a = knowledge.answer("teach me physics")
    assert a["kind"] == "tour" and "acceleration" in a["text"] and a["tries"]


def test_commands_stay_commands():
    for q in ["explain the last incident", "what is the status", "show me the dashboard"]:
        a = knowledge.answer(language.normalise(q))
        assert a is None or a["kind"] != "definition", q


def test_total_and_difference_avoids_the_trap():
    s = fields.solve("a bat and a ball cost 1.10 in total. the bat costs 1.00 more than the ball. how much is the ball?")
    assert s.answer == "0.05" and "1.05 + 0.05 = 1.10" in s.check
    s = fields.solve("a pen and a notebook cost 60 together. the notebook costs 20 more than the pen. how much does the notebook cost?")
    assert s.answer == "40"


def test_spelling_leaves_maths_words_alone(tmp_path, monkeypatch):
    import kepler.device as device
    monkeypatch.setattr(device, "HOME", tmp_path)  # no library: only the built-in vocabulary protects these words
    assert "converge" in language.normalise("does the sum of 1/n^2 converge")
    assert "eigenvalues" in language.normalise("eigenvalues of [[4, 1], [2, 3]]")
    assert language.normalise("staus") == "status"


@pytest.mark.parametrize("q,ours", [("is the website down right now?", True), ("is our checkout working", True),
                                    ("any downtime today", True), ("who brought down the berlin wall", False),
                                    ("when did the website first go online", False), ("what is a website", False)])
def test_outage_questions_stay_with_kepler(q, ours):
    from kepler.bot.mind import OUTAGE
    assert bool(OUTAGE.search(q)) is ours  # never sent to the encyclopedia when it's about your own systems
