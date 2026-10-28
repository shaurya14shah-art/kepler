"""Access control for the HTTP API.

Every /api route needs the workspace access key, sent as `X-Kepler-Key` or `Authorization: Bearer <key>` (CLI,
SDK, integrations), or the dashboard's sign-in cookie. The cookie holds a token derived from the key (never the key
itself), is HttpOnly and SameSite=Strict (so other websites can't act as a signed-in browser), and stops working
the moment the key is rotated. Wrong sign-in attempts are rate-limited per address.
"""
import hashlib
import hmac
import threading
import time

from . import config, db

COOKIE = "kepler_session"
SESSION_DAYS = 30
# Public, or they check a secret themselves (machine endpoints; the billing webhook is 404 while billing is off).
OPEN_PATHS = ("/api/health", "/api/session", "/api/v1/ingest", "/api/v1/decision/", "/api/v1/hooks/",
              "/api/billing/webhook/")
MAX_FAILURES, WINDOW_S = 10, 300
_failures: dict[str, list[float]] = {}
_lock = threading.Lock()


def current_key() -> str:
    return db.get_settings().get("api_key", "")


def key_matches(candidate: str | None) -> bool:
    expected = current_key()
    return bool(candidate and expected) and hmac.compare_digest(candidate.encode(), expected.encode())


def session_token(key: str) -> str:
    return hmac.new(key.encode(), b"kepler-dashboard-session", hashlib.sha256).hexdigest()


def presented_key(headers) -> str | None:
    auth = headers.get("authorization", "")
    return headers.get("x-kepler-key") or (auth[7:].strip() if auth.lower().startswith("bearer ") else None)


def authorized(headers, cookies) -> bool:
    if key_matches(presented_key(headers)):
        return True
    cookie, key = cookies.get(COOKIE), current_key()
    return bool(cookie and key) and hmac.compare_digest(cookie.encode(), session_token(key).encode())


def needs_key(path: str) -> bool:
    if not config.AUTH_REQUIRED or not path.startswith("/api/"):
        return False
    return not any(path == p or (p.endswith("/") and path.startswith(p)) for p in OPEN_PATHS)


def too_many_attempts(addr: str) -> bool:
    now = time.time()
    with _lock:
        recent = [t for t in _failures.get(addr, []) if now - t < WINDOW_S]
        _failures[addr] = recent
        return len(recent) >= MAX_FAILURES


def record_failure(addr: str) -> None:
    with _lock:
        _failures.setdefault(addr, []).append(time.time())
