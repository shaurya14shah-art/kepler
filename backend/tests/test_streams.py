"""Several streams of knowledge in one message: splitting, fact → maths chains, comparisons, blended sources."""
import io

import pytest
from rich.console import Console

from kepler.bot import streams
from kepler.bot.mind import Mind
from kepler.bot.teach import Trainer
from kepler.library import index, ingest

ARTICLES = {
    "India": ["India is a country in South Asia. About 1.4 billion people live in India, more than any other country."],
    "China": ["China is a country in East Asia. Its population is about 1,410,000,000 people."],
    "Mount Everest": ["Mount Everest is the highest mountain on Earth. Its peak is 8,849 m above sea level."],
    "K2": ["K2 is the second-highest mountain in the world, standing at 8611 m tall."],
    "Nile": ["The Nile is a river in Africa. It is about 6,650 km long."],
    "Albert Einstein": ["Albert Einstein (14 March 1879 – 18 April 1955) was a German-born scientist."],
    "Prime number": ["A prime number is a natural number that has exactly two divisors: one and itself."],
}


@pytest.fixture
def library():
    with index.session(write=True) as c:
        for title, paras in ARTICLES.items():
            index.add_doc(c, "wikipedia", title, title, paras, f"https://simple.wikipedia.org/wiki/{title}", ingest.WIKI_LICENCE)
        c.execute("INSERT INTO words(lemma, pos, definition, examples, synonyms) VALUES (?, ?, ?, ?, ?)",
                  ("prime number", "noun", "an integer that has no integral factors but itself and 1", "", "prime"))
    index.set_setting("web", "off")


@pytest.mark.parametrize("text,parts", [
    ("is signups ok and what does anomaly mean?", ["is signups ok", "what does anomaly mean?"]),
    ("who was einstein? what is 2+2; and how are things", ["who was einstein", "what is 2+2", "how are things"]),
    ("add 5 and 7", ["add 5 and 7"]),
    ("who wrote romeo and juliet", ["who wrote romeo and juliet"]),
    ("how many chickens and cows are there", ["how many chickens and cows are there"]),
])
def test_split(text, parts):
    assert streams.split(text) == parts


def test_word_problem_sentences_stay_together():
    text = "tom is twice as old as jerry. the sum of their ages is 36? how old is jerry?"
    assert Mind().parts(text) == [text]


@pytest.mark.parametrize("q,answer", [
    ("population of india divided by 2", "700,000,000"),
    ("what is the height of mount everest in feet", "29,032 feet"),
    ("the length of the nile in miles", "4,132 miles"),
    ("which is more populous, india or china", "China (more populous than India)"),
    ("which is taller, mount everest or k2", "Mount Everest (taller than K2)"),
])
def test_chains_use_library_then_maths(library, q, answer):
    sol = streams.chain(q)
    assert sol is not None and sol.ok, (q, sol)
    assert sol.answer == answer
    assert any(s.startswith("[library]") for s in sol.steps) and any("[maths]" in s for s in sol.steps)


def test_years_ago_uses_todays_date(library):
    import datetime
    sol = streams.chain("how many years ago was albert einstein born")
    assert sol.ok and sol.answer == f"{datetime.date.today().year - 1879} years ago"


def test_missing_fact_is_said_plainly(library):
    sol = streams.chain("population of atlantis divided by 2")
    assert sol is not None and not sol.ok and "atlantis" in sol.answer


def test_definitions_blend_several_sources(library):
    th = Mind().think("what is a prime number")
    d = th.knowledge or th.lookup
    origins = {s["origin"] for s in d["supporting"]}
    assert "Open English WordNet" in origins and "Simple Wikipedia (offline)" in origins
    assert d["agreement"] >= 0.3


def test_one_message_many_streams_in_teach(library):
    buf = io.StringIO()
    t = Trainer(Console(file=buf, width=140, color_system=None))
    t.handle("what is 12 * 3 and who was albert einstein and is api_errors ok")
    out = buf.getvalue()
    assert "3 questions" in out
    assert "36" in out and "German-born" in out and "◆ decide" in out


def test_infobox_facts_become_sentences():
    wt = """{{Infobox country
| capital = [[Canberra]]
| largest_city = capital
| official_languages = {{nowrap|None at [[Government of Australia|federal level]]}}
| population_estimate = {{IncreaseNeutral}} {{formatnum:27204809}}<ref>census</ref>
| area_km2 = 7,688,287
| birth_date = {{birth date|1879|3|14}}
}}
'''Australia''' is a country."""
    facts = ingest.infobox_facts("Australia", wt)
    assert facts == ("Australia's population is 27204809. Australia's area is 7,688,287 km2. Australia's capital is Canberra. "
                     "Australia's language is None at federal level. Australia's birth date is 14 March 1879.")


def test_area_conversion_and_units_carried(library):
    with index.session(write=True) as c:
        index.add_doc(c, "wikipedia", "France", "France", ["France is a country in Europe.", "France's area is 640,679 km2."])
    sol = streams.chain("what is the area of france in square miles")
    assert sol.ok and sol.answer == "247,368 square miles"
    sol = streams.chain("the height of mount everest times 2")
    assert sol.ok and sol.answer == "17,698 m"
