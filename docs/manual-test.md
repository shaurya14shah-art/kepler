# Manual test: real data through a real connector

This kit tests Kepler the way a customer would use it. A Postgres database receives live data, Kepler pulls from it
every minute with a SQL query, and alerts go to a signed webhook endpoint. The data is real and comes from the
[Numenta Anomaly Benchmark](https://github.com/numenta/NAB) (MIT licence), which labels the true anomalies, so you
can check what Kepler catches and misses.

No account, password or API key is involved. Postgres runs on this Mac and only accepts local connections.

## What's running

| Piece | Where | Started with |
|-------|-------|--------------|
| Postgres 17 (database `kepler_test`) | `localhost:5432` | `LC_ALL=en_US.UTF-8 pg_ctl -D /opt/homebrew/var/postgresql@17 -l /opt/homebrew/var/log/postgresql@17.log start` |
| Kepler test workspace | http://localhost:8100, data in `backend/data/manual-test/kepler.db` | `backend/.venv/bin/kepler serve --port 8100 --db backend/data/manual-test/kepler.db --demo off` |
| Alert receiver | `http://127.0.0.1:8788/kepler` | `python3 -I scripts/manual_test/webhook_receiver.py` |

The test workspace is separate from your normal one (`~/.kepler/kepler.db`, port 8000), so the demo data is
untouched.

**Opening it:**

- **Terminal app:** `kepler --url http://localhost:8100`
- **Dashboard:** http://localhost:8100. The sign-in key is printed in the test server's terminal, or run
  `kepler key --url http://localhost:8100`.
- **What Kepler caught so far:** `backend/.venv/bin/python -I scripts/manual_test/check.py`

## The data

| Metric | Source | History imported | Alerts on |
|--------|--------|------------------|-----------|
| `tweet_mentions`, by `company` (AAPL, AMZN, GOOG, FB, IBM, KO, PFE, UPS, CVS, CRM) | Tweets mentioning each company, every 5 minutes (2015) | 25 days | spikes |
| `elb_requests` | Requests through a real AWS Elastic Load Balancer, every 5 minutes (2014) | 13 days | spikes |
| `taxi_passengers` | NYC taxi passengers (2014–15). Each 30-minute count is spread evenly over six 5-minute buckets | 28 days | both directions |

**How the replay works:**

- Each dataset is shifted in time so its history ends at setup time, and the rest lies in the future.
- The tables in schema `replay` hold every row.
- The views Kepler reads (`public.tweets`, `public.elb_requests`, `public.taxi_passengers`) only show rows up to
  `now()`. So new rows arrive minute by minute, as they would from a live app.
- The replays run for about a month (tweets), one day (load balancer) and five days (taxi).

Kepler's query for tweets, the same shape a customer would write:

```sql
SELECT date_bin('5 minutes', ts, TIMESTAMPTZ '2000-01-01') AS ts, company, sum(mentions) AS value
FROM tweets WHERE ts > now() - interval '3 hours'
GROUP BY 1, 2
```

## What to watch

`setup.py` printed the schedule of labelled real anomalies, and `check.py` shows it any time. From the first setup
(Mon 26 Oct, 12:04):

| When (local time) | What | The real event |
|-------------------|------|----------------|
| right away (12:05) | `taxi_passengers ▼ -77%`, critical | The January 2015 NYC blizzard. Demand was already collapsing before the storm (3,203 passengers at 9 pm, against 14,245 the Monday before). NAB labels it at midnight, so Kepler's alert came 3 hours before the label. |
| Mon 12:49 | `tweet_mentions · company=IBM` spike | A burst of IBM news: 84 and 72 mentions in two 5-minute buckets, against about 1 normally. **Missed in the first run:** small segments weren't checked on their own then. They are now, see below. |
| Mon 13:44 | `elb_requests` spike | A traffic surge on the load balancer |
| Tue 08:39, Thu 04:29, Thu 09:29, … | more tweet spikes: UPS, CVS, CRM, AAPL, GOOG, AMZN, FB, … | `check.py` lists them all |

**Small segments are screened, not watched.** Kepler watches a segment all the time only when it's at least 5% of
the metric (`MIN_SLICE_SHARE` in `backend/kepler/engine/detector.py`). Smaller segments get a cheap check every 5
minutes instead.
- **Watched all the time:** AAPL (31%), AMZN (30%), FB (14%), GOOG (11%) and KO (8%).
- **Screened:** IBM (2.3%), CRM, PFE, UPS and CVS. Each one is compared with the same time of day over the previous
  week.
  - When one moves by at least 5% of the whole metric in the alert direction, Kepler scores it with its full model.
    5% of the metric is as much as a watched segment's whole volume.
  - That bucket alone is judged, against how much that company's own count varies at that hour. Tweet counts are
    bursty, so an ordinary burst doesn't count.
  - It needs a stricter score than a watched segment: z ≥ 4.37 here instead of 4. All the screened segments together
    get the false-alarm budget of one watched segment.
  - So IBM's 84 and 72 mentions (about +80 on a total of ~210) now open `tweet_mentions · company=IBM`. Re-scored on a
    copy of this workspace: z = 10, 84 against 2.8 expected.
- **Still no alert of their own:**
  - Values that don't recur, like user ids. A value needs data in at least 24 five-minute buckets of the last day.
  - Bursts too small to move the whole metric by 5%, such as 8 tweets in CVS.
  - A small segment going quiet. Losing a 2% segment moves the metric by 2% at most, so drops there only show
    through the total.
- **Expect more tweet alerts.** All 55 days of the benchmark's tweets replayed through Kepler, before and after this
  change:
  - Labelled anomalies caught: 16 of 22 before, 20 of 22 after. The small companies went from 4 of 10 to 8 of 10.
  - Alerts outside the labelled windows: 561 before, 627 after, over 41 days. The extra ones are on the five small
    companies, and they're big bursts the benchmark doesn't label: typically 19× the company's expected count, and
    at least 7× for 9 in 10 of them. Most are UPS, whose tweets come in huge bursts.
- **The running test server still has the old engine.** It loads the engine when it starts, so this applies after
  you restart it (Ctrl-C, then the command at the top).

To catch drops in a small segment, give it its own pull and metric, for example a query with `WHERE company = 'IBM'`.

Each alert shows up in four places:
- the **alert receiver**'s terminal, with "signature ✓"
- the dashboard's Incidents page
- `kepler incidents --url http://localhost:8100`
- tab 3 of the terminal app

The load balancer's traffic is very noisy: 29% of its 5-minute counts are under 20. Kepler staying quiet on those
dips is correct.

## Things to try

1. **Break something yourself.** Multiply Coca-Cola's tweets by 8 for the next half hour, then wait about 10
   minutes:
   ```bash
   psql -h localhost -d kepler_test -c "UPDATE replay.tweets SET mentions = mentions * 8 WHERE company = 'KO' AND ts BETWEEN now() + interval '2 minutes' AND now() + interval '32 minutes'"
   ```
   Or flood the load balancer:
   ```bash
   psql -h localhost -d kepler_test -c "UPDATE replay.elb_requests SET requests = requests * 6 WHERE ts BETWEEN now() + interval '2 minutes' AND now() + interval '32 minutes'"
   ```
2. **Ask why.** Open the terminal app, press `7` (Kepler AI) and ask "why did taxi passengers drop?" or "explain #1".
3. **Teach the filter.** Label incidents real or false (`kepler label 1 real --url http://localhost:8100`, or 👍 / 👎 in
   the dashboard), then `kepler train --url http://localhost:8100`.
4. **Check the signature.** This must answer 401, and the receiver prints "refused":
   ```bash
   curl -s -o /dev/null -w '%{http_code}\n' -X POST -d '{}' http://127.0.0.1:8788/kepler
   ```
5. **Lose the data source.** Stop Postgres:
   ```bash
   LC_ALL=en_US.UTF-8 pg_ctl -D /opt/homebrew/var/postgresql@17 stop
   ```
   Within a minute, `kepler pulls --url http://localhost:8100` and the Integrations page show the error. Start it
   again with the command at the top, and the pulls recover.
6. **Compare the models:** `kepler compare taxi_passengers --url http://localhost:8100`.

## Stopping and starting over

- **Stop:**
  - Press Ctrl-C in the test server's and the receiver's terminals.
  - Stop Postgres with `LC_ALL=en_US.UTF-8 pg_ctl -D /opt/homebrew/var/postgresql@17 stop`.
  - Nothing was set to start at login.
- **Resume later:** start the three pieces again with the commands at the top. Kepler catches up from Postgres on
  its own. Rows missed while it was off for more than 3 hours aren't re-read, because the query only looks back 3
  hours.
- **Start over** with a fresh replay that begins now:
  1. Stop the test server.
  2. Run `rm backend/data/manual-test/kepler.db*`.
  3. Start the server again.
  4. Run `backend/.venv/bin/python -I scripts/manual_test/setup.py`.

  It reloads Postgres and reconfigures Kepler.

## Getting the data again

The files live in `backend/data/manual-test/nab/`, which git ignores, about 8 MB: the 13 used here, plus the other 35 real
NAB series that the benchmark (`backend/stress/bench_nab.py`) also uses. To fetch them on another machine:

```bash
cd backend/data/manual-test/nab && for f in data/realTweets/Twitter_volume_{AAPL,AMZN,GOOG,FB,IBM,KO,PFE,UPS,CVS,CRM}.csv data/realAWSCloudwatch/elb_request_count_8c0756.csv data/realKnownCause/nyc_taxi.csv labels/combined_windows.json; do curl -fsSO "https://raw.githubusercontent.com/numenta/NAB/master/$f"; done
```

The other 35 series, for the benchmark:

```bash
cd backend/data/manual-test/nab && for d in realAdExchange realAWSCloudwatch realKnownCause realTraffic; do curl -s "https://api.github.com/repos/numenta/NAB/contents/data/$d" | python3 -c "import sys, json; print('\n'.join(i['download_url'] for i in json.load(sys.stdin) if i['name'].endswith('.csv')))" | xargs -n1 curl -fsSO; done
```

They're for local testing only. They aren't bundled into Kepler.

## In production

Give Kepler's Postgres connector a read-only role of its own, not your superuser. For example, run this yourself
with a password you choose:

```sql
CREATE ROLE kepler_readonly LOGIN PASSWORD '…';
GRANT CONNECT ON DATABASE app TO kepler_readonly;
GRANT USAGE ON SCHEMA public TO kepler_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO kepler_readonly;
```

Kepler also opens every pull read-only, with a 15-second statement timeout.
