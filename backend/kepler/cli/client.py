"""HTTP client for a Kepler server, shared by the CLI, the bot and the TUI."""
import json
import os
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

import httpx

CONFIG = Path(os.environ.get("KEPLER_CONFIG", Path.home() / ".kepler" / "config.json"))
DEFAULT_URL = "http://localhost:8000"


class KeplerError(Exception):
    pass


def load_config() -> dict:
    try:
        return json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=2))
    CONFIG.chmod(0o600)


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
SERVER_INFO = CONFIG.parent / "servers.json"  # written by `kepler serve`: port → its database file (never a secret)


def local_key(url: str) -> str | None:
    """A server on this machine: read its access key from its database file (same user only, no request needed)."""
    u = urlparse(url)
    if (u.hostname or "") not in LOCAL_HOSTS:
        return None
    paths = []
    try:  # the database of the server on exactly this port
        paths.append(json.loads(SERVER_INFO.read_text()).get(str(u.port or 80)))
    except (OSError, ValueError, AttributeError):
        pass
    paths += [os.environ.get("KEPLER_DB"), str(Path.home() / ".kepler" / "kepler.db")]
    for p in [p for p in paths if p]:
        if not Path(p).exists():
            continue
        try:
            with sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=5) as conn:
                row = conn.execute("SELECT value FROM settings WHERE key = 'api_key'").fetchone()
        except sqlite3.Error:
            continue
        if row and row[0]:
            return row[0]
    return None


def resolve(url: str | None = None, key: str | None = None) -> tuple[str, str | None]:
    cfg = load_config()
    return (url or os.environ.get("KEPLER_URL") or cfg.get("url") or DEFAULT_URL,
            key or os.environ.get("KEPLER_KEY") or cfg.get("key"))


class Client:
    def __init__(self, url: str | None = None, key: str | None = None, timeout: float = 30):
        self.url, self._key = resolve(url, key)
        self.url = self.url.rstrip("/")
        self.http = httpx.Client(base_url=self.url, timeout=timeout)

    @property
    def key(self) -> str:
        if not self._key:
            self._key = self._find_key()
        return self._key

    def _find_key(self) -> str:
        key = local_key(self.url)  # a server on this machine
        if key:
            return key
        try:  # a server with the access gate off hands it out
            return self._request("GET", "/api/settings", auth=False)["api_key"]
        except KeplerError as e:
            if "HTTP 401" in str(e):
                raise KeplerError(f"the Kepler server at {self.url} needs its access key: run `kepler key` on the server, "
                                  "then `kepler config --set-key KEY` here (or set KEPLER_KEY)") from None
            raise

    def _do(self, method, path, **kw):
        try:
            return self._request(method, path, **kw)
        except KeplerError as e:
            if "HTTP 401" in str(e) and not self._key:  # the gate is on and we haven't found the key yet
                self.key  # noqa: B018 - finds it (or raises a helpful error)
                return self._request(method, path, **kw)
            raise

    def _request(self, method, path, auth: bool = True, **kw):
        if auth and self._key:
            kw["headers"] = {"X-Kepler-Key": self._key, **(kw.get("headers") or {})}
        try:
            r = self.http.request(method, path, **kw)
        except httpx.ConnectError:
            raise KeplerError(f"can't reach Kepler at {self.url}. Start it with ./run.sh, or set --url / KEPLER_URL.") from None
        except httpx.TimeoutException:
            raise KeplerError(f"Kepler at {self.url} timed out on {path}") from None
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail")
            except ValueError:
                detail = r.text[:200]
            raise KeplerError(f"{method} {path} → HTTP {r.status_code}: {detail}")
        if "json" not in r.headers.get("content-type", ""):
            raise KeplerError(f"{self.url}{path} didn't return JSON: is this a Kepler server, and is it up to date?")
        return r.json()

    def get(self, path, **params):
        return self._do("GET", path, params={k: v for k, v in params.items() if v is not None})

    def post(self, path, body=None):
        return self._do("POST", path, json=body)

    def put(self, path, body):
        return self._do("PUT", path, json=body)

    def patch(self, path, body):
        return self._do("PATCH", path, json=body)

    def delete(self, path):
        return self._do("DELETE", path)

    def get_auth(self, path, **params):
        return self._do("GET", path, params=params, headers={"X-Kepler-Key": self.key})

    def post_auth(self, path, body):
        return self._do("POST", path, json=body, headers={"X-Kepler-Key": self.key})

    def upload_csv(self, path: Path, metric: str = "", agg: str = "sum", bad: str = "both"):
        with open(path, "rb") as f:
            return self._do("POST", "/api/import/csv", files={"file": (path.name, f, "text/csv")},
                            data={"metric": metric, "agg": agg, "bad_direction": bad})

    # convenience
    def metrics(self) -> list[dict]:
        return self.get("/api/overview")["metrics"]

    def metric_by_name(self, name: str) -> dict:
        for m in self.metrics():
            if m["name"] == name:
                return m
        raise KeplerError(f"no metric named '{name}'")

    def dashboard_url(self, path: str = "") -> str:
        return f"{self.url}/#/{path.lstrip('/')}"
