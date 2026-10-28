# Kepler real-data lab

Test Kepler against **real tools holding real data**, on your Mac, with no accounts:

| Piece | What it is | Port |
|---|---|---|
| **Postgres 17** (Homebrew) | Orbitly's database; table `users` holds every sign-up | 5433 |
| **Prometheus 3** (Homebrew) | scrapes Orbitly's `/metrics` every 15 s | 9090 |
| **Orbitly** (`orbitly/app.py`) | a small FastAPI web app: feed, search, upload, login, sign-up | 9200 |
| **Traffic** (`orbitly/traffic.py`) | simulated web/iOS/Android users in US/EU/IN with a daily rhythm | – |
| **Kepler (real)** | a separate Kepler with **no demo data** (`KEPLER_DEMO=0`) | 8001 |

Kepler only ever sees the tools: it **queries Prometheus with PromQL** and **reads Postgres with SQL**, the
same way it would at a real company.

## Run it

```bash
cd lab
./setup.sh      # once, ~5 min: creates the database, backfills 21 days of history into Postgres and Prometheus
./start.sh      # starts Postgres, Prometheus, Orbitly, traffic, Kepler-real
./connect.sh    # connects Kepler to Prometheus + Postgres using only `kepler connect …`, imports history
```

Then use the CLI against the real Kepler (or set it once with `kepler config --set-url http://localhost:8001`):

```bash
kepler --url http://localhost:8001 train         # learn baselines from the 21 days of real history
kepler --url http://localhost:8001 status
kepler --url http://localhost:8001                # full-screen app on real data
```

## Break it and watch Kepler catch it

```bash
./break.sh list
./break.sh ios_errors 30        # bad iOS release: 60% of iOS /feed requests return 500   → api_5xx, platform=ios
./break.sh android_signups 30   # Android sign-up form broken                             → signups, platform=android
./break.sh eu_slow 30           # EU database slow: EU latency ~4x                         → p95_latency_s, region=EU
kepler --url http://localhost:8001 watch --notify    # incidents appear within ~5-15 minutes
```

Kepler works in 5-minute buckets and only judges a bucket once it is complete at the source, so the first
alert takes one or two buckets after the breakage starts.

## Verified results (2026-10-19, live run on a MacBook)

| Fault | Injected | Kepler alert opened | Time to detect | Incident |
|---|---|---|---|---|
| `eu_slow` | 19:04:48 | 19:10:01 | **5 min 13 s** | p95_latency_s **+331%**, critical, confidence **1.00**, where **region=EU** |
| `ios_errors` | 19:45:14 | 19:50:36 | **5 min 22 s** | api_5xx **125×**, critical, confidence **1.00**, where **platform=ios** |
| `android_signups` | 20:25:59 | – | not verified | the Mac slept 20:33-20:50 mid-test (sleep stops all traffic); Kepler correctly flagged the resulting all-segment drop instead |

Both verified faults were caught in about one 5-minute bucket, with the right metric and slice, which is the fastest
Kepler's complete-bucket design allows. Detection times come from Kepler's alert log (wall clock when the incident opened).

Open issue found here (not yet fixed): after a metric-wide outage resolves, Kepler's 30-60 min pooled evidence still
contains the outage, which can keep an incident open after recovery or open a duplicate slice incident (#7, signups
platform=ios). To re-run the Android test: keep the Mac awake and plugged in, wait until `kepler incidents --open`
shows no sign-ups incident, then `./break.sh android_signups 30`.

## How Kepler is connected (what `connect.sh` runs)

```bash
kepler connect prometheus url=http://localhost:9090 \
  query='sum by (platform) (increase(http_requests_total{status="500"}[5m]))' \
  labels=platform metric=api_5xx backfill_days=21 --alert-when up --every 1

kepler connect prometheus url=http://localhost:9090 \
  query='histogram_quantile(0.95, sum by (le, region) (rate(http_request_duration_seconds_bucket[5m])))' \
  labels=region metric=p95_latency_s backfill_days=21 --agg mean --alert-when up --every 1

kepler connect postgres dsn=postgresql://kepler_readonly@localhost:5433/orbitly \
  query="SELECT date_bin('5 minutes', created_at, '2000-01-01') AS ts, platform, region, count(*) AS value
         FROM users WHERE created_at > now() - interval '21 days' GROUP BY 1, 2, 3" \
  metric=signups --alert-when down --every 1
```

Point the same commands at your own Prometheus or Postgres (with a read-only user) to watch a real product.

## Stop / clean up

```bash
./stop.sh       # stops every lab process (nothing is installed as a login item or service)
./reset.sh      # stops everything and deletes all lab data
brew uninstall prometheus postgresql@17   # if you want the tools gone too
```

## Things this lab caught that the simulator couldn't

- **Partial buckets**: a pull at 12:03 sees 3 of 5 minutes; Kepler now only judges buckets that were complete at
  the source's last successful pull.
- **Prometheus window alignment**: `increase(x[5m])` at 12:05 describes 12:00-12:05; Kepler now files it there.
- **Multi-process apps**: `prometheus_client` counters are per process; scraping a 2-worker app looks like constant
  counter resets and inflates `increase()`. Orbitly runs as one process (real apps use multiprocess mode).
- **Traffic must match the history**: the first traffic generator sent ~3x the backfilled rate; Kepler rightly
  flagged "5xx +132%" because errors scale with traffic. Fixed (one Poisson draw per tick).
- **Lab scripts**: `start.sh` recorded a wrapper shell's PID, so `stop.sh` never stopped the servers, and uvicorn waits
  forever on keep-alive connections. Both fixed (`exec` in start, TERM then KILL after 5 s in stop).
