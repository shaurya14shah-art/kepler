"""A local endpoint for Kepler's signed webhook alerts (manual test kit): prints each alert and logs it.

    python3 -I scripts/manual_test/webhook_receiver.py          # listens on http://127.0.0.1:8788/kepler

It checks every request the way a customer's endpoint should. The X-Kepler-Signature header must be
sha256=HMAC-SHA256(raw body, secret), where the secret is in backend/data/manual-test/webhook.secret (setup.py creates
it). Unsigned or wrongly signed requests get a 401. Alerts are appended to backend/data/manual-test/alerts.jsonl.
"""
import hashlib
import hmac
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "backend" / "data" / "manual-test"
SECRET, LOG = DATA / "webhook.secret", DATA / "alerts.jsonl"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8788
COLOR = {"incident.opened": "\033[1;31m", "incident.resolved": "\033[32m", "incident.updated": "\033[33m"}


class Receiver(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - http.server's naming
        raw = self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 1_000_000))
        secret = SECRET.read_text().strip().encode() if SECRET.exists() else b""
        given = self.headers.get("X-Kepler-Signature", "")
        expected = "sha256=" + hmac.new(secret, raw, hashlib.sha256).hexdigest()
        if not secret or not hmac.compare_digest(given, expected):
            print(f"{time.strftime('%H:%M:%S')}  \033[33mrefused: missing or wrong signature\033[0m", flush=True)
            self.send_response(401)
            self.end_headers()
            return
        body = json.loads(raw)
        d = body.get("decision", {})
        event = body.get("event", "?")
        print(f"{time.strftime('%H:%M:%S')}  {COLOR.get(event, '')}{event:<18}\033[0m {body.get('summary', '')}"
              f"  \033[2m(#{d.get('incident_id')}, {d.get('confidence', 0):.0%} sure, signature ✓)\033[0m", flush=True)
        with open(LOG, "a") as f:
            f.write(json.dumps({"received": int(time.time()), **body}) + "\n")
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):  # quiet: one line per alert is enough
        pass


if __name__ == "__main__":
    DATA.mkdir(parents=True, exist_ok=True)
    print(f"Kepler alert receiver on http://127.0.0.1:{PORT}/kepler (checks signatures; log: {LOG})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Receiver).serve_forever()
