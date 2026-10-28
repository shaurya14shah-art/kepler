"""Live Wikipedia lookup for questions the local library can't answer. Results are saved into the library
(source 'web-wikipedia'), so Kepler learns as you ask and can answer offline next time.

Only the search words of the question are sent to en.wikipedia.org. Turn it off with `kepler learn --web off`.
"""
import os
import re
import threading
import time

from .. import __version__
from . import index

API = "https://en.wikipedia.org/w/api.php"
MIN_GAP = 1.0          # seconds between requests (Wikimedia API etiquette)
_state = {"last": 0.0, "paused_until": 0.0}
_gate = threading.Lock()


def _headers() -> dict:
    # Wikimedia asks for a descriptive User-Agent with a way to contact you: set KEPLER_CONTACT (email or URL).
    contact = os.environ.get("KEPLER_CONTACT", "").strip()
    return {"User-Agent": f"Kepler/{__version__} (self-hosted metric watchdog{'; ' + contact if contact else ''}) python-httpx"}


def paused_for() -> int:
    """Seconds left on a rate-limit pause (0 when lookups are allowed)."""
    return max(0, int(_state["paused_until"] - time.time()))


def _get(client, params: dict):
    with _gate:
        wait = _state["last"] + MIN_GAP - time.time()
        if wait > 0:
            time.sleep(wait)
        _state["last"] = time.time()
    r = client.get(API, params=params)
    if r.status_code == 429:
        try:
            pause = int(r.headers.get("retry-after", "300"))
        except ValueError:
            pause = 300
        _state["paused_until"] = time.time() + max(60, min(pause, 3600))
        return None
    r.raise_for_status()
    return r.json()
LICENCE = "CC BY-SA 4.0 (Wikipedia contributors)"
TIMEOUT = 8.0


def enabled() -> bool:
    import os
    if os.environ.get("KEPLER_WEB", "").lower() in ("off", "0", "false", "no"):
        return False
    return index.setting("web", "on") == "on"


def lookup(question: str, terms: str, max_pages: int = 2) -> list[dict]:
    """Search Wikipedia and return [{title, url, paragraphs}] for the best pages (saved to the library)."""
    import httpx
    q = re.sub(r"\s+", " ", terms).strip()[:200]
    if not q or paused_for():
        return []
    out = []
    try:
        with httpx.Client(headers=_headers(), timeout=TIMEOUT, follow_redirects=True) as c:
            found = _get(c, {"action": "query", "list": "search", "srsearch": q, "srlimit": max_pages,
                             "format": "json", "srprop": ""})
            if not found:
                return []
            titles = [h["title"] for h in found.get("query", {}).get("search", [])][:max_pages]
            if not titles:
                return []
            got = _get(c, {"action": "query", "prop": "extracts", "explaintext": 1, "exsectionformat": "plain",
                           "titles": "|".join(titles), "format": "json", "redirects": 1})
            if not got:
                return []
            pages = got.get("query", {}).get("pages", {})
    except (httpx.HTTPError, ValueError, KeyError):
        return []
    from .ingest import SKIP_SECTION, _chunk
    by_title = {p.get("title"): p.get("extract", "") for p in pages.values()}
    conn = index.connect(write=True)
    try:
        for title in titles:
            text = by_title.get(title) or next((v for k, v in by_title.items() if k and k.lower() == title.lower()), "")
            if not text:
                continue
            paras, skipping = [], False
            for block in re.split(r"\n\s*\n|\n(?==)", text):
                b = block.strip()
                head = re.fullmatch(r"=+\s*(.*?)\s*=+", b) or (re.fullmatch(r"[A-Z][\w ]{2,40}", b) if len(b) < 42 else None)
                if head:
                    skipping = bool(SKIP_SECTION.match(head.group(1) if head.re.groups else b))
                    continue
                if skipping or len(b) < 40:
                    continue
                paras.extend(_chunk(re.sub(r"\s+", " ", b)))
            if not paras:
                continue
            url = "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")
            index.add_doc(conn, "web-wikipedia", title, title, paras[:120], url, LICENCE)
            out.append({"title": title, "url": url, "paragraphs": paras[:120]})
        conn.commit()
    finally:
        conn.close()
    return out
