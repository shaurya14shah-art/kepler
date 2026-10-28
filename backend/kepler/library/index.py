"""The local library: SQLite with an FTS5 full-text index, in ~/.kepler/library.db (override: KEPLER_LIBRARY).

docs      one row per article / file / dictionary word (source, title, url, licence)
passages  paragraphs of each doc (the unit we search), with an FTS5 index over title + text (BM25 ranking)
words     the dictionary: lemma, part of speech, definition, examples, synonyms
settings  e.g. whether live Wikipedia lookup is on
"""
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from .. import device

SCHEMA = """
CREATE TABLE IF NOT EXISTS docs (
  id INTEGER PRIMARY KEY, source TEXT NOT NULL, key TEXT NOT NULL, title TEXT NOT NULL, url TEXT DEFAULT '',
  licence TEXT DEFAULT '', added INTEGER DEFAULT (strftime('%s','now')), UNIQUE(source, key));
CREATE INDEX IF NOT EXISTS docs_title ON docs(title COLLATE NOCASE);
CREATE TABLE IF NOT EXISTS passages (id INTEGER PRIMARY KEY, doc_id INTEGER NOT NULL, ord INTEGER NOT NULL, text TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS passages_doc ON passages(doc_id, ord);
CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(title, text, content='', tokenize='porter unicode61');
CREATE TABLE IF NOT EXISTS words (
  id INTEGER PRIMARY KEY, lemma TEXT NOT NULL, pos TEXT, definition TEXT NOT NULL, examples TEXT DEFAULT '',
  synonyms TEXT DEFAULT '', source TEXT DEFAULT 'wordnet');
CREATE INDEX IF NOT EXISTS words_lemma ON words(lemma);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
"""
_lock = threading.Lock()


def path() -> Path:
    return Path(os.environ.get("KEPLER_LIBRARY") or device.HOME / "library.db")


def connect(write: bool = False) -> sqlite3.Connection:
    p = path()
    if not write and not p.exists():
        raise FileNotFoundError(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p, timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    if write:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.executescript(SCHEMA)
    return c


@contextmanager
def session(write: bool = False):
    c = connect(write)
    try:
        if write:
            with _lock:
                yield c
                c.commit()
        else:
            yield c
    finally:
        c.close()


def exists() -> bool:
    return path().exists()


def setting(key: str, default: str = "") -> str:
    try:
        with session() as c:
            row = c.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default
    except (FileNotFoundError, sqlite3.Error):
        return default


def set_setting(key: str, value: str) -> None:
    with session(write=True) as c:
        c.execute("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                  (key, value))


def add_doc(c: sqlite3.Connection, source: str, key: str, title: str, paragraphs: list[str], url: str = "",
            licence: str = "") -> int | None:
    """Insert or replace one document and its passages. Returns the doc id (None when there's no text)."""
    paragraphs = [p.strip() for p in paragraphs if p and p.strip()]
    if not paragraphs:
        return None
    old = c.execute("SELECT id FROM docs WHERE source = ? AND key = ?", (source, key)).fetchone()
    if old:
        remove_doc(c, old["id"])
    cur = c.execute("INSERT INTO docs(source, key, title, url, licence) VALUES (?, ?, ?, ?, ?)", (source, key, title, url, licence))
    doc_id = cur.lastrowid
    for i, text in enumerate(paragraphs):
        pid = c.execute("INSERT INTO passages(doc_id, ord, text) VALUES (?, ?, ?)", (doc_id, i, text)).lastrowid
        c.execute("INSERT INTO passages_fts(rowid, title, text) VALUES (?, ?, ?)", (pid, title, text))
    return doc_id


def remove_doc(c: sqlite3.Connection, doc_id: int) -> None:
    for row in c.execute("SELECT p.id, p.text, d.title FROM passages p JOIN docs d ON d.id = p.doc_id WHERE p.doc_id = ?",
                         (doc_id,)).fetchall():
        c.execute("INSERT INTO passages_fts(passages_fts, rowid, title, text) VALUES ('delete', ?, ?, ?)",
                  (row["id"], row["title"], row["text"]))
    c.execute("DELETE FROM passages WHERE doc_id = ?", (doc_id,))
    c.execute("DELETE FROM docs WHERE id = ?", (doc_id,))


def forget(source: str) -> int:
    """Remove everything learned from one source ('wikipedia', 'wordnet', 'files:/path', or a prefix 'files')."""
    with session(write=True) as c:
        if source == "wordnet":
            n = c.execute("DELETE FROM words WHERE source = 'wordnet'").rowcount
            return n
        ids = [r["id"] for r in c.execute("SELECT id FROM docs WHERE source = ? OR source LIKE ?", (source, source + ":%"))]
        if len(ids) > 5000:  # big sources: rebuild the index instead of deleting row by row
            c.execute("DELETE FROM passages WHERE doc_id IN (SELECT id FROM docs WHERE source = ? OR source LIKE ?)", (source, source + ":%"))
            c.execute("DELETE FROM docs WHERE source = ? OR source LIKE ?", (source, source + ":%"))
            c.execute("INSERT INTO passages_fts(passages_fts) VALUES ('delete-all')")
            for row in c.execute("SELECT p.id, p.text, d.title FROM passages p JOIN docs d ON d.id = p.doc_id"):
                c.execute("INSERT INTO passages_fts(rowid, title, text) VALUES (?, ?, ?)", (row["id"], row["title"], row["text"]))
        else:
            for i in ids:
                remove_doc(c, i)
        return len(ids)


def stats() -> dict:
    if not exists():
        return {"docs": {}, "passages": 0, "words": 0, "size_mb": 0.0, "web": setting("web", "on")}
    with session() as c:
        docs = {r["s"]: r["n"] for r in c.execute(
            "SELECT CASE WHEN source LIKE 'files:%' THEN 'files' ELSE source END AS s, COUNT(*) AS n FROM docs GROUP BY s")}
        return {"docs": docs, "passages": c.execute("SELECT COUNT(*) FROM passages").fetchone()[0],
                "words": c.execute("SELECT COUNT(*) FROM words").fetchone()[0],
                "size_mb": round(path().stat().st_size / 1e6, 1), "web": setting("web", "on")}


STOP = set("""a an the is are was were be been being am do does did of in on at to for from by with about as into
like through over after before between under above up down out off than then so such this that these those it its
they them their there here what which who whom whose when where why how i you he she we me my your his her our
and or but if not no yes can could would should will shall may might must also just only very more most some any
all each every much many tell please explain describe define know give show find me us call called name named
has have had having get gets got getting make makes made doing done does go goes went say says said one ones
use used using way ways thing things kind type many""".split())


def fts_query(text: str, mode: str = "or") -> str:
    """Words → a safe FTS5 query (quoted terms; no operators from user input)."""
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP and len(w) > 1][:12]
    if not words:
        return ""
    joiner = " OR " if mode == "or" else " AND "
    return joiner.join(f'"{w}"' for w in words)


def search(text: str, limit: int = 20, sources: tuple | None = None) -> list[sqlite3.Row]:
    """Best passages for a question (BM25 over title + text, title weighted)."""
    q = fts_query(text)
    if not q or not exists():
        return []
    with session() as c:
        rows = c.execute(
            "SELECT p.id, p.doc_id, p.ord, p.text, d.title, d.source, d.url, d.licence, bm25(passages_fts, 4.0, 1.0) AS score "
            "FROM passages_fts JOIN passages p ON p.id = passages_fts.rowid JOIN docs d ON d.id = p.doc_id "
            "WHERE passages_fts MATCH ? ORDER BY score LIMIT ?", (q, limit * 3 if sources else limit)).fetchall()
    if sources:
        rows = [r for r in rows if any(r["source"] == s or r["source"].startswith(s + ":") for s in sources)][:limit]
    return rows


def doc_by_title(title: str, source: str | None = None):
    if not exists():
        return None
    with session() as c:
        sql = "SELECT * FROM docs WHERE title = ? COLLATE NOCASE"
        args: tuple = (title,)
        if source:
            sql += " AND source = ?"
            args += (source,)
        return c.execute(sql + " ORDER BY CASE source WHEN 'wikipedia' THEN 1 ELSE 0 END LIMIT 1", args).fetchone()


def passages_of(doc_id: int, start: int = 0, n: int = 3) -> list[str]:
    with session() as c:
        return [r["text"] for r in c.execute("SELECT text FROM passages WHERE doc_id = ? AND ord >= ? ORDER BY ord LIMIT ?",
                                             (doc_id, start, n))]


def word(lemma: str) -> list[sqlite3.Row]:
    if not exists():
        return []
    with session() as c:
        return c.execute("SELECT * FROM words WHERE lemma = ? COLLATE NOCASE ORDER BY id LIMIT 12", (lemma.lower(),)).fetchall()
