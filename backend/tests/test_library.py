"""The library: importing files, answering with confidence and sources, and staying out of Kepler's way."""
import pytest

from kepler.library import answer, index, ingest
from kepler.bot.mind import Mind

ARTICLES = {
    "Albert Einstein": ["Albert Einstein (14 March 1879 – 18 April 1955) was a German-born scientist. He worked on theoretical physics.",
                        "He developed the theory of relativity. He won the Nobel Prize in Physics in 1921."],
    "Canberra": ["Canberra is the capital city of Australia. About 400,000 people live there."],
    "Spider": ["Spiders are arthropods. A spider has eight legs and two body parts."],
    "France": ["France, officially the French Republic, is a country in Western Europe. Its capital is Paris."],
    "Photosynthesis": ["Photosynthesis is the process plants use to make food from sunlight, water and carbon dioxide.",
                       "It happens in the chloroplasts. Oxygen is released as a by-product."],
}


@pytest.fixture
def library():
    with index.session(write=True) as c:
        for title, paras in ARTICLES.items():
            index.add_doc(c, "wikipedia", title, title, paras, f"https://simple.wikipedia.org/wiki/{title}", ingest.WIKI_LICENCE)
        c.executemany("INSERT INTO words(lemma, pos, definition, examples, synonyms) VALUES (?, ?, ?, ?, ?)", [
            ("serendipity", "noun", "good luck in making unexpected and fortunate discoveries", "", ""),
            ("happy", "adjective", "enjoying or showing joy", "a happy smile", "glad, felicitous"),
        ])
    index.set_setting("web", "off")


@pytest.mark.parametrize("q,decision,needle,title", [
    ("who was albert einstein", "answer", "German-born scientist", "Albert Einstein"),
    ("what is photosynthesis", "answer", "make food from sunlight", "Photosynthesis"),
    ("tell me about canberra", "answer", "capital city of Australia", "Canberra"),
    ("what is the capital of australia", "answer", "Canberra", "Canberra"),
    ("how many legs does a spider have", "answer", "eight legs", "Spider"),
    ("when was einstein born", "answer", "1879", "Albert Einstein"),
    ("is france in europe", "answer", "Yes", "France"),
    ("define serendipity", "answer", "fortunate discoveries", "serendipity"),
    ("synonyms for happy", "answer", "glad", "happy"),
])
def test_answers_with_sources(library, q, decision, needle, title):
    a = answer.ask(q)
    assert a.decision == decision, (q, a)
    assert needle in a.text
    assert a.title == title
    assert a.confidence >= answer.ANSWER


def test_says_it_does_not_know(library):
    a = answer.ask("who won the 1987 badminton world championship")
    assert a.decision in ("unknown", "unsure")
    assert a.confidence < answer.ANSWER


def test_tell_me_more_continues_the_article(library):
    m = Mind()
    th = m.think("who was albert einstein")
    assert th.kind == "lookup" and "German-born" in th.lookup["text"]
    th = m.think("tell me more")
    assert th.kind == "lookup" and "relativity" in th.lookup["text"]


@pytest.mark.parametrize("q", ["how are things", "is signups ok", "show the last 5 incidents", "explain incident 40",
                               "what are the open incidents", "why did api errors spike", "status"])
def test_kepler_commands_never_go_to_the_library(library, q):
    assert Mind().think(q, {"signups", "api", "errors"}).kind != "lookup"


def test_maths_and_definitions_still_win(library):
    m = Mind()
    assert m.think("what is 2 + 2").kind == "math"
    assert m.think("what is a median").kind == "knowledge"


def test_import_your_files(tmp_path):
    (tmp_path / "handbook.md").write_text("# On-call\n\nThe on-call engineer this week is Priya. Escalate to Sam after 30 minutes.\n")
    (tmp_path / "notes.txt").write_text("Our deploy window is Tuesday and Thursday afternoons.\n")
    (tmp_path / "team.csv").write_text("name,role\nPriya,SRE\nSam,Engineering manager\n")
    (tmp_path / ".secret.txt").write_text("hidden files are skipped")
    n, problems = ingest.import_files(tmp_path)
    assert n == 3 and not problems
    index.set_setting("web", "off")
    a = answer.ask("who is the on-call engineer")
    assert "Priya" in a.text and a.origin == "your files"
    a = answer.ask("when is our deploy window")
    assert "Tuesday" in a.text
    assert index.forget(f"files:{tmp_path.resolve()}") == 3
    assert answer.ask("when is our deploy window").decision == "unknown"


def test_wiki_markup_is_cleaned():
    paras = ingest.clean_wikitext(
        "'''France''' ({{IPA|fr}} or ; {{lang|fr|République}}) , officially the [[French Republic|French Republic]], "
        "is a [[country]] in [[Western Europe]].<ref>cite</ref>\n\n== References ==\n{{reflist}}\nSome reference text that is long enough.")
    assert paras == ["France, officially the French Republic, is a country in Western Europe."]


def test_queries_are_safe_from_fts_syntax(library):
    for q in ['what is "unterminated', "what is NEAR(a b)", "what is a* OR b", "what is -x AND :y"]:
        answer.ask(q)  # never raises


def test_online_lookup_respects_rate_limits(monkeypatch):
    import httpx

    from kepler.library import web
    calls = []

    class Resp:
        status_code = 429
        headers = {"retry-after": "120"}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None):
            calls.append(params)
            return Resp()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    monkeypatch.setattr(web, "_state", {"last": 0.0, "paused_until": 0.0})
    monkeypatch.setenv("KEPLER_CONTACT", "ops@example.com")
    assert "ops@example.com" in web._headers()["User-Agent"]
    assert web.lookup("who painted the mona lisa", "who painted the mona lisa") == []
    assert len(calls) == 1 and 60 <= web.paused_for() <= 120
    assert web.lookup("anything else", "anything else") == []  # paused: no request at all
    assert len(calls) == 1
