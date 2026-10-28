# Deploying Kepler

Kepler is one process (API, dashboard and background worker) with one SQLite database. A small server is enough
for most teams. By default it listens on `127.0.0.1` only. To reach it from other machines, put an HTTPS reverse
proxy in front; don't expose port 8000 directly.

## 1. Run it

**Docker** (recommended):

```bash
cp .env.example .env              # adjust; never commit .env
docker compose up -d              # http://127.0.0.1:8000, data in the kepler-data volume
docker compose logs kepler        # shows the dashboard sign-in key
```

**Python package** (Python 3.11+):

```bash
pip install kepler_watchdog-1.0.0-py3-none-any.whl
KEPLER_DB=/var/lib/kepler/kepler.db kepler serve --host 127.0.0.1 --port 8000
```

To run it as a service, use systemd or your platform's process manager with that same command. Run it as an
ordinary user, never as root.

## 2. The access key

Every `/api` route and the dashboard need the workspace access key (`KEPLER_AUTH=on`, the default).

- **Getting it**: it's printed on start. On the server, `kepler key` reads it from the local database. In Docker,
  use `docker compose exec kepler kepler key`.
- **Signing in**: the dashboard asks for the key once. After that the browser holds an HttpOnly session cookie
  for 30 days. The cookie is not the key and can't be turned back into it.
- **CLI and SDK from another machine**: run `kepler config --set-url https://kepler.example.com --set-key kp_…`, or send the
  `X-Kepler-Key` header.
- **Pinning it**: set `KEPLER_API_KEY` to choose the key yourself, which is useful for infrastructure as code and CI.
  Otherwise Kepler generates one on first start.
- **Rotating it**: use Settings → Rotate key, or `kepler key --rotate`. This signs out every browser session, and
  every client needs the new key.
- **Failed sign-ins**: after 10 failures from one address within 5 minutes, sign-in is refused for that address
  for a while (HTTP 429).

Only set `KEPLER_AUTH=off` on a machine and network you trust, for local development.

## 3. HTTPS in front

Terminate HTTPS at a reverse proxy and forward to `127.0.0.1:8000`. Then set **`KEPLER_SECURE_COOKIES=on`**, so the
sign-in cookie is only ever sent over HTTPS.

**Caddy** (gets and renews certificates automatically):

```
kepler.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

**nginx**:

```nginx
server {
    listen 443 ssl http2;
    server_name kepler.example.com;
    ssl_certificate     /etc/letsencrypt/live/kepler.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/kepler.example.com/privkey.pem;
    client_max_body_size 50m;                       # CSV history imports (Kepler caps them at 50 MB)

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 90s;
    }
}
```

**Client addresses**: Kepler trusts `X-Forwarded-For` only from `127.0.0.1` by default. That's what lets the
sign-in limit count each visitor separately. If your proxy runs elsewhere (another container, a load balancer),
set `FORWARDED_ALLOW_IPS` to the proxy's address. Never set it to `*` on a server that's reachable directly.

**Links in alerts**: set `KEPLER_PUBLIC_URL=https://kepler.example.com`. Slack messages, emails, PagerDuty alerts,
webhooks and Grafana and Datadog annotations then include an "Open in Kepler" link to the incident, and the weekly
report links to the dashboard.

**Retraining**: models retrain on their own once a week, and as soon as a new metric has the 7 days of data a
custom model needs. `kepler doctor` shows when they last trained. Set `KEPLER_AUTO_TRAIN=off` to train only by hand
(`kepler train`).

**Other origins**: by default only the dashboard's own origin can call the API from a browser. Add others with
`KEPLER_CORS_ORIGINS` (comma-separated).

## 4. Data, backups and upgrades

- **Where the data lives**: everything is in the SQLite database. That's `KEPLER_DB`, by default
  `~/.kepler/kepler.db`, or `/data/kepler.db` in Docker.
- **Backups**: take a consistent copy while Kepler is running:
  ```bash
  sqlite3 /var/lib/kepler/kepler.db ".backup /backups/kepler-$(date +%F).db"
  ```
  In Docker, back up the `kepler-data` volume, or run the same command in the container.
- **Kepler AI's library** is separate (`KEPLER_LIBRARY`, by default `~/.kepler/library.db`) and can always be
  rebuilt with `kepler learn`.
- **Upgrading**:
  1. Take a backup.
  2. Install the new wheel or image, and restart.
  3. Kepler updates the database schema itself on start.
  4. Check `kepler --version` and `curl https://kepler.example.com/api/health`.

## 5. A weekly report for the team

`kepler report --send` posts a summary of the last 7 days to Slack and every email destination. Cron it on the
server, for example every Monday at 09:00:

```
0 9 * * 1  KEPLER_URL=http://127.0.0.1:8000 /path/to/kepler report --send
```

## 6. Checklist before you expose it

- [ ] HTTPS in front, and `KEPLER_SECURE_COOKIES=on`
- [ ] `KEPLER_AUTH=on` (the default), and the key kept somewhere safe
- [ ] Port 8000 not reachable from outside: the compose file binds `127.0.0.1:8000`
- [ ] Backups scheduled, and one restore tried
- [ ] `kepler doctor` reports no problems
- [ ] `KEPLER_BILLING=off`, unless you've followed [billing.md](billing.md)
- [ ] `KEPLER_DEMO=0` for a workspace with real data only
- [ ] For Kepler AI's optional Wikipedia lookups, `KEPLER_CONTACT` set to your email or URL, as Wikimedia asks.
      Or set `KEPLER_WEB=off`.
