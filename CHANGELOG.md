# Changelog

## Unreleased

**Detection**
- Strong anomalies in small segments are caught. A segment under 5% of its metric still isn't watched all the time,
  but every recurring one is now screened each bucket against the same time of day over the previous week.
  - When its change is at least 5% of the whole metric in the alert direction, Kepler scores it with the full model.
  - That bucket alone is judged, by the exact tail of an over-dispersed count (negative binomial), with the spread the
    segment itself shows at that time of day. Ordinary bursts of a noisy segment don't count.
  - It must pass a stricter bar: all screened segments together get one watched segment's false-alarm rate
    (Bonferroni).
  - Example: the manual test's IBM spike (2.3% of tweets, from about 1 mention per 5 minutes to 84) is now an
    incident on `company=IBM`. Before, it was missed.
  - Values that don't recur (user ids), bursts too small to move the metric by 5%, and drops in small segments still
    don't alert on their own.
  - Replaying the benchmark's 55 days of tweets: labelled anomalies caught 16 → 20 of 22. Alerts outside the labelled
    windows 561 → 627: large bursts in the small companies that the benchmark doesn't label (typically 19× expected).
  - On 9 simulated weeks of bursty, anomaly-free traffic with 50 mostly tiny segments and one-off user ids: 732
    alerts against 730 before.
  - Unchanged on the demo simulator, where every segment is at least 15% of its metric.
- Learned tail calibration: training now measures how much burstier each series is than the model assumes, up and
  down separately. That's the median over training days of each day's most extreme scores, so a real incident on
  one day can't make the model deaf. Scores and expected ranges are scaled by it. On the real-data benchmark (12
  Numenta Anomaly Benchmark series, 94 weeks), false alarms fell by 53% for Area (2,646 → 1,233) and 58% for Time
  (2,649 → 1,178), and all 32 labelled anomalies are still caught. Models trained before this score exactly as
  before until they retrain.
- `stress/bench_nab.py`: a walk-forward benchmark on real labelled data, with a saved baseline to compare against.
  It now covers all 47 real NAB series: 98 labelled anomalies over 255 weeks. That's 12 counts (tweets, requests,
  taxi) plus 35 gauges (EC2 and RDS CPU, network and disk bytes, latency, machine and ambient temperature, road
  traffic, ad-exchange prices), with each file's own reporting interval detected. Counts and gauges are reported
  separately.
  - It also counts anomalies caught near the label (an incident within 3 hours of the labelled moment). NAB's windows
    are 1.5 days wide, so a false alarm can land in one and count as caught.
  - That stricter measure showed the first three changes above had cost timely detections (30 → 27 of 32, on
    whether an incident was open within 3 hours). The tail calibration was responsible, on Christmas Day taxi demand
    and two tweet spikes. Fixed below.
  - `BENCH_SET="module.CONSTANT=value"` switches parts of the engine off for comparisons like this.
- Training no longer throws away most of a high-volume series. Points the untrained model scores |z| > 4 are still
  dropped, but at most the 2% most extreme. For NYC taxi (about 2,000 per bucket) it had been dropping 34% of the
  training data, and estimating the noise from the few points that happened to fit. Timely detections are back to
  29 of 32 (all 32 still caught within NAB's windows), at the cost of a few more false alarms (998 → 1,045 for
  Area). One factor per kind of evidence, single buckets and each pooling window apart, was also tried and dropped:
  more false alarms and no more timely catches.
- Metrics that report every 10, 15, 30 or 60 minutes are handled properly. Kepler works in 5-minute buckets, so
  such a metric repeats one reading over several buckets, held for a gauge or spread for a count, and pooled
  windows counted every bucket as independent evidence.
  - Kepler now detects a metric's reporting interval: nearly all its value changes fall on one regular grid, which
    noisy 5-minute data, even mostly zeros, never does.
  - It counts evidence per reading: a window of w buckets is worth about w/k readings, and an incident's duration
    counts readings.
  - On the 47-series benchmark, false alarms fell 43% for Area (3,731 → 2,112), 35% for Time and 21% for Orbit. The
    hourly ad-exchange series went from 224–326 false alarms each to 21–67, and NYC taxi from 416 to 209. Every
    anomaly caught within its NAB window still is.
  - On the 3-hour measure, Area shows two fewer: NYC taxi's Thanksgiving and Christmas. Both are still caught, by
    critical drop incidents starting around 02:00–02:30 on the holiday morning, 13 hours before NAB's mid-afternoon
    label, so they close before the 3-hour mark around it.
  - Pooling over 3/6/12 readings instead of buckets was also tried: more false alarms, no more timely catches.
  - The metric page shows "reports every N min" for such metrics, and the series API returns `reports_every_s`.
- "No data" incidents: a metric that stops reporting now raises an incident, which most dashboards miss.
  - It opens when the silence is unusual for that metric: 3× its typical longest gap of a day (the median over
    days, so one past outage can't make it deaf), and at least 3 readings and 30 minutes.
  - A sensor that routinely goes quiet for two hours isn't flagged at two hours, while a 5-minute metric is
    flagged after 30 minutes.
  - It pages through every channel ("NO DATA: cpu_pct has sent nothing since 14:05"), resolves when readings
    return ("cpu_pct is reporting again"), and shows as "no data since 14:05" in the dashboard, terminal app and
    CLI. Decisions carry `kind: "no_data"` and `silent_since`.
  - Pushed counts already read as zeros when they stop, and are judged as drops.
  - On the 47-series benchmark it catches the ambient-temperature sensor failure, which is a long gap in the data.
    That's one more anomaly caught for every model (Area 91/98) and one more timely catch. Value false alarms are
    unchanged (2,110), and 26 data outages that NAB doesn't label are now counted in their own column.
  - Using the 99th-percentile gap between readings as the yardstick was tried first: it flagged routine daily gaps.
- Tried and dropped: judging a gauge's change against its typical range (5th to 95th percentile) instead of its
  level, which would make temperature in °F and °C behave the same. Every mapping of the 15% minimum-change setting
  onto the range traded catches against false alarms on the benchmark: at 1× and 2× the range, one more catch for
  65–167 more false alarms; at 3×, 150 fewer false alarms but 4 fewer timely catches. Picking a value in between would
  have been tuning to the benchmark.
- The benchmark can simulate a team labelling incidents: `--labels 0.3` labels 30% of each week's incidents the
  way a person would (👍 within 6 hours of a labelled anomaly, 👎 otherwise), and the learned filter retrains every
  week. Measured on Area:
  - 30% labelled: false alarms fell 5% (2,110 → 2,013).
  - 60% labelled: false alarms fell 14% (→ 1,822).
  - The cost: 1–3 timely catches, where a real event resembled past false alarms.
  - Tried and dropped: letting the filter quieten only alerts no stronger than a labelled false alarm. It was neutral
    on timely catches and slightly noisier.
- Tried and dropped: trusting the learned filter by balanced evidence (2× the rarer of 👍/👎) instead of all labels.
  With simulated labels it bought back at most one timely catch for 80–150 more false alarms.
- Models now retrain on their own. A live server used to keep the models from its first `kepler train` forever, while
  the benchmark assumed weekly retraining. The worker now retrains once a week, and as soon as a metric reaches the
  7 days of data a custom model needs. Training runs in its own thread, like the Train button. `KEPLER_AUTO_TRAIN=off`
  turns it off.
  - Daily retraining was measured too, and was worse: it let models absorb slow-building anomalies, giving 4 fewer
    timely catches and 5% more false alarms than weekly.
  - `kepler doctor` shows when models last trained, and warns when they're stale with retraining off.
- Tried and dropped: choosing each metric's seasonality (weekly, daily, or flat for a metric with no rhythm) by
  which one best predicts held-out days. It cut false alarms by 3–6% and caught one more anomaly, but cost 1–2 timely
  catches, whether an alternative had to be 5% or 15% better to replace the default.
- Where the benchmark stands. Of the 17 labelled anomalies with no incident within 3 hours of the label (Area), about
  6 are out of reach or already caught earlier:
  - a GOOG tweet *drop* on a series set to alert on rises only
  - a load-balancer label inside the 3-day warm-up
  - two travel-time labels with no data at all
  - taxi's Thanksgiving and Christmas, caught on the holiday morning

  About 10 are precursor labels on AWS CPU, disk and keystroke series, with no visible change in level or
  variability near the label. Five rounds of model changes (seasonality, gauge range, label trust, filter range, base
  tail) found nothing that adds catches without cost. Further gains need new evidence, such as your own labelled
  incidents, not more tuning to these 98 labels.
- Known miss: UPS tweets on 29 Mar 2015 went to about 30× normal for four hours. UPS is so bursty in training that its
  upward tail factor sits at the cap, which keeps the rise just under the alert bar. Two fixes were tried and
  dropped, because each cost more than it gained elsewhere on the benchmark: a 3-hour pooling window, and other
  values for the tail cap (3, 4, 5, 8).
- Tried and dropped: tail calibration for the untrained shared model, which Orbit uses all the time and every metric
  uses in its first week. It learned on the fly from the previous days of the same window, with no look-ahead. It
  cut Orbit's false alarms by 69% (1,461 → 454), but cost 3 of its 29 timely detections at any cap tried (2 to 6).
  Real detections come first. If you'd rather have fewer alerts on Orbit, lower the sensitivity setting.
- Proportional recovery hold: an incident now resolves after as many normal buckets as it lasted, from 3 for a blip
  up to an hour. Brief dips inside one long episode no longer split it into several incidents and alerts. On the
  benchmark, false alarms fell a further 8–12% for every model (Area 1,233 → 1,083), and the NYC taxi series fell
  most (496 → 390, where 160 of its 581 incidents used to start within 30 minutes of the previous one ending). Every
  labelled anomaly is still caught.
- A lone anomalous bucket needs a bigger surprise, about one more unit of z, than a run of two or more. A strong
  spike still alerts at once. A moderate real problem confirms itself 5 minutes later, while the lone blips that
  ordinary bursty traffic produces no longer alert. On the benchmark, about half of all false alarms were single
  buckets, against few real catches. False alarms fell by another 8% (Area 1,083 → 998), with all 32 labelled
  anomalies still caught.
- An incident's figures now always describe its strongest bucket. A later, smaller bucket with more evidence behind
  it raises the confidence, but no longer replaces the peak's observed and expected values.

**Alerts**
- Maintenance mode: pause every alert in the workspace for planned work. Incidents are still detected and recorded,
  but nothing goes to Slack, PagerDuty, email or webhooks. It ends on its own, after at most 30 days.
  - CLI: `kepler maintenance 2h`, `kepler maintenance off`, or `kepler maintenance` alone to see the state.
  - Dashboard: Settings → Maintenance mode (1 h, 4 h or 24 h), and a banner on the Overview with "End now".
  - `kepler doctor` warns while it's on.
  - API: `PUT /api/settings {"muted_until": epoch}`.
- Mute a metric's alerts for a while, for deploys, migrations or known maintenance. Incidents are still detected
  and recorded, but nothing is sent to Slack, PagerDuty or other destinations. A "resolved" message is never sent
  for an alert that went out muted. A mute ends on its own, after at most 30 days.
  - Dashboard: 🔕 Mute on a metric's page (1 h, 4 h or 24 h), and a "muted" chip on the Overview.
  - CLI: `kepler metric checkout_errors --mute 2h`, and `--mute off` to undo it.
  - API: `PATCH /api/metrics/{id}` with `{"muted_until": epoch}`, or 0 to unmute.

**Incidents**
- Notes on incidents: write what the team found or did ("rolled back deploy 4.2"), and it stays with the incident.
  - Dashboard: a Notes card in the incident drawer (Ctrl/⌘+Enter adds a note).
  - CLI: `kepler note 40 "…"` adds a note, `kepler note 40` lists them, `--delete N` removes one, and `kepler explain`
    shows them.
  - API: `POST` and `DELETE /api/incidents/{id}/notes`, and `GET /api/incidents/{id}` includes them.
  - Notes are shown as plain text everywhere, never as markup.

**Operations**
- Integrations page: the scheduled pulls and destinations tables are full width again. Side by side, at common
  window sizes, they hid their Status column and Run/Remove buttons.
- Related incidents: each incident lists the others, on any metric, that started within 15 minutes of it. An
  api_errors spike and a sign-ups drop in the same minute are usually one outage.
  - Dashboard: "At the same time" in the incident drawer (click to open one), and "+N at the same time" in the
    Incidents table.
  - CLI: `kepler explain` lists them.
  - Slack: the opening alert says "Also now: signups ▼ -60%, …".
  - API: decisions carry `related`.
- Alerts link to the incident: with `KEPLER_PUBLIC_URL` set (where people reach the dashboard), every channel
  carries an "Open in Kepler" link to that incident's page:
  - Slack: in the message.
  - Email: in the body.
  - PagerDuty: its own links field.
  - Webhooks: a `url` field.
  - Grafana and Datadog: in the annotation.
  The weekly report links to the dashboard too.
- Label incidents in one click: 👍/👎 right in the Incidents table, without opening the incident (clicking the
  active one clears it). The page shows the learned filter's state: how many labels it has and how much it's
  trusted, or how many more it needs before it switches on.
- Weekly report. It covers what Kepler saw over a period: incidents by severity, the trend against the period
  before, the metrics with most incidents, how long incidents typically lasted, open ones, data outages, your
  labels and precision, unlabelled incidents (with a nudge to label them), muted metrics and notes.
  - `kepler report [--days 7]` prints it, and `GET /api/report` returns it with the text.
  - `kepler report --send` (or `POST /api/report/send`) posts it to Slack and every email destination. It exits with
    code 1 if there was nowhere to send it, or a channel failed. Cron it for a weekly digest (docs/deploy.md).
- `kepler doctor`: one command to check a setup. It covers the server, the access key, the background worker (last
  run, last error), data freshness, trained models, open incidents, muted metrics, every pull, every alert
  destination plus Slack, and billing. It explains anything wrong, and exits with code 1 on a problem, for cron and CI.

**Integrations**
- Email destination over SMTP: one email when an incident opens, and its resolution replies in the same thread. It
  works with STARTTLS (587), SSL (465) or a plain relay on your own network, and any provider (Gmail and Google
  Workspace, Microsoft 365, SES, Postmark, your own server). The password is stored and redacted like other secrets.
- PagerDuty destination (Events API v2, US or EU service region). It triggers on an incident, deduplicated on the
  Kepler incident, and resolves the alert when the incident resolves. Its "Test" sends a change event, which shows
  on the service but never pages anyone. Set it up in Integrations, or with `kepler connect pagerduty routing_key=…`.

**Security**
- A general request-size limit: request bodies over 10 MB get a 413 before anything parses them. The size is
  checked from Content-Length, or counted as it arrives for chunked uploads. CSV imports keep their 50 MB limit.

## 1.0.0 (2026-10-25)

First packaged release. Kepler is free during early access, and nothing can be charged.

**Billing (built, disabled)**
- Razorpay integration in `kepler/billing`: a plan catalog, one-off orders, or subscriptions when a Razorpay plan ID
  is set. Checkout and webhook signature checks; idempotent webhooks (`X-Razorpay-Event-Id`).
- **Disabled behind five locks:**
  1. `CHARGING_ALLOWED = False` in the code
  2. `KEPLER_BILLING=off`
  3. no Razorpay keys
  4. live keys need `KEPLER_BILLING_LIVE=yes`
  5. no paid plan has a price
- While disabled, no request is sent to Razorpay. Checkout and verify return 403, the webhook returns 404, and
  prices stay hidden. No account, keys or bank details are set up. See `docs/billing.md`.
- `kepler billing`, `GET /api/billing`, and Settings → Plan & billing show the plan and why charging is off.
- No upgrade button appears in the dashboard while billing is disabled.

**Access**
- Dashboard sign-in with the workspace access key. The browser gets an HttpOnly, SameSite=Strict session cookie for
  30 days. The cookie is not the key, and rotating the key signs everyone out. Set `KEPLER_SECURE_COOKIES=on`
  behind HTTPS.
- Failed sign-ins are limited to 10 per address in 5 minutes. After that, sign-in answers 429.
- The access gate is on by default everywhere: `kepler serve`, Docker and Compose. `kepler serve` prints the
  sign-in key.
- The `kepler` CLI finds the key of a server on the same machine by itself, by reading its database as you.
  `~/.kepler/servers.json` maps port → database.
- `KEPLER_API_KEY` pins the access key, for deployments and CI.

**Packaging**
- Version 1.0.0. The wheel and source archive carry PEP 639 licence metadata and bundle the dashboard, `LICENSE`
  and `THIRD_PARTY_NOTICES.md`. The `Private :: Do Not Upload` classifier means PyPI refuses the package.
- `make release` runs lint, tests, build, a smoke test of the installed wheel in a fresh virtualenv, and the
  website. Also new: `make notices`, `make site`, `make smoke`.
- The product website (`site/`): landing page, pricing ("no charge during early access"), and legal pages built
  from `legal/`.
- Draft legal documents (`legal/`), with placeholders to fill and a lawyer to review: EULA, terms, privacy,
  refund, delivery, contact.
- Docker image: OCI labels, a version build argument, access gate on and billing off by default.
- New docs: `docs/billing.md`, `docs/deploy.md` (HTTPS, cookies, backups, a checklist), `docs/RELEASE.md`.
- Manual test kit (`scripts/manual_test/`, `docs/manual-test.md`): real labelled datasets replayed through a local
  Postgres, a signed webhook receiver, and a checker that scores Kepler's catches against the labels.

**Fixes**
- `kepler` opens the whole app (dashboard tabs and Kepler AI) even when no server is running: it starts one on this
  machine for as long as the app is open, and stops it when you quit. Before, it opened only the chat.
- The server now serves the newest dashboard build: whichever of the bundled copy and `frontend/dist` is newer.
  Before, an old bundled copy could win.
- `index.html` is sent with `Cache-Control: no-cache`, so browsers pick up a new release straight away.
- Terminal app: pressing Esc twice quickly in a pop-up (help, incident, connect) no longer closes the main screen
  too. Before, the app went blank and then crashed.
- Kepler AI: a message starting with `!` (such as "!5") gets "that doesn't look like a complete expression"
  instead of an internal error.
- The background worker stops when the app shuts down. Before, it ran on in the process after the app had stopped.
- Detection: a segment that is still broken after the incident that reported it closes now raises a new alert on
  its new data. Before, it could be held back for up to an hour as the old incident's "tail".
- The engine tests use a fixed simulated clock and their own database, so `make test` gives the same result at any
  hour. `KEPLER_TEST_NOW=now` runs them against the real clock. The live-injection test now follows each incident
  until it's found in the right place, and passes at every time of day sampled (every 30 minutes over three days).

**Performance**
- Model comparison (`kepler compare`, `GET /api/metrics/{id}/compare`) runs in a helper process with its own Python
  interpreter. A result is reused until its data, models or settings change. Under the stress test's 24 concurrent
  clients, its p95 dropped from about 17 s to about 1 s, with identical results. If the helper can't start, compare
  runs in the server as before.

## 0.5.0 (2026-10-21)

**Bot**
- Trained in bulk. Fleets of Haiku and Opus bots wrote a training corpus, subject solvers and a held-out exam.
  Every batch was cross-checked by a second bot.
  - Corpus (`kepler/bot/corpus/`): 1,136 phrasings across the 24 intents and 315 fact-checked definitions with
    107 "X vs Y" contrasts. The classifier retrains when the corpus changes.
  - Subject solvers (`kepler/bot/solvers/`): puzzles, chemistry, electrical, physics, finance, statistics, geometry,
    calculus, algebra and arithmetic. Each handles chatty word problems with worked steps and has its own tests.
    Haiku testers each tried 56 fresh problems per subject; the reported failures were then fixed. The solvers run
    only when the exact engine can't answer.
  - Understanding: concepts are found anywhere in a question ("z-score meaning??"), world-fact questions are found
    behind lead-ins, there is more small talk, and failed maths no longer swallows ops questions.
  - `stress/bench_bot.py` scores the built-in bot on exams. On a fresh, sealed exam of 507 questions
    (`stress/bot_exam_b.jsonl`), understanding went from 48.5% to 81.1%:

    | Category | Before | After |
    |---|---|---|
    | Intents | 68% | 90% |
    | Maths | 34% | 79% |
    | Definitions | 0% | 63% |
    | Lookups | 30% | 41% |
- Field problems in plain English, solved with the formula, the knowns in SI units, the substitution, the result
  and a check. Quantities are read with their units (km/h, m/s², kWh, Ω, g/mol, mol/L, °…).
  - Physics: acceleration, free fall, force, weight, kinetic and potential energy, momentum, work, power, density,
    pressure, wavelength.
  - Electrical: Ohm's law, power, energy in kWh and its cost.
  - Chemistry: molar mass from any formula (Ca(OH)2, C6H12O6) or common name (water, glucose), moles, mass,
    molarity, pH of strong acids and bases.
  - Finance: loan payments, savings with monthly contributions, CAGR.
  - Statistics: z-scores, normal probabilities.
  - Geometry and trigonometry: circles, spheres, cylinders, cones, rectangles, triangles, Pythagoras, and
    "sine of 60 degrees" in exact form.
  - The bat-and-ball puzzle and other total-and-difference problems, with the tempting wrong answer explained.
- The chat understands indirect questions: "can you tell me what a median is", "explain like I'm five what a mole
  is" and "I don't get what an anomaly is" all become "what is …".
  - It compares terms ("difference between mean and median", "speed vs velocity", "how is mass different from
    weight").
  - "Teach me physics" lists the terms it can explain in that field.
  - It knows 29 more physics, electrical, chemistry and finance terms.
  - More small talk: its name, "lol", "I have a question", "tell me something interesting".
- `scripts/train_kepler_live.py`: a training session you can watch in the terminal. It runs basic English lessons:
  ask a sentence Kepler gets wrong, correct it with /n, and check whether a new phrasing generalised. If one example
  isn't enough, it teaches a second. Then it shows understanding, field problems and harder maths, and ends with an
  exam of unseen questions. `--dry` trains a throwaway copy, `--exam` runs only the exam.
- The lessons from the first live session are built into Kepler's own training, so every install understands
  them. Examples: "is the site down", "show me the dashboard", "stop bugging me so much", "nice to meet you" and
  "good job". Before, "show me the dashboard" was read as status and "is the site down" as settings.
- Fixes: decimals survived the chat's normaliser as "2. 5" and units as "km / h", so "0.001 M HCl" and
  "60 km/h" questions failed in the chat. Without a library loaded, "converge" was spell-corrected to "convert".
  Word titles like "Ohm's law" were shown as "Ohm'S Law". With Wikipedia loaded, "is the website down right now?"
  got an encyclopedia article about websites; questions about your own site, app or service being down now stay
  with Kepler.
- The main `kepler` UI has a **7 Kepler AI** tab: the full chat panel (insight sidebar, examples, write-ups,
  training) shared with `kepler bot`. With no server running, `kepler` opens Kepler AI on its own.
- The main `kepler` app's chat has every bot feature: maths, general knowledge, write-ups and the
  teaching commands (`/pdf`, `/tex`, `/open`, `/y`, `/n`, `/new`, `/alias`, `/test`).
- Formal write-ups: `kepler write`, `/pdf`, `/tex` and "write a proof … as a pdf" typeset answers as LaTeX
  (theorem and proof environments, aligned induction steps, boxed answers, verification, sources) and compile them
  to PDF with Tectonic (sandboxed, with a plain-layout fallback).
- Advanced reasoning: proofs by induction, identities and inequalities (or counterexamples), classic proofs,
  matrices, ODEs, big-number number theory, series convergence, a conjecture lab (Goldbach, Collatz, twin primes,
  Riemann zeros counted with Riemann–von Mangoldt), and honest explanations of the Millennium Prize Problems.
- Digits of constants: sums, products, averages, listings, the nth digit and digit counts for π, e, φ, √2, √3,
  √5, ln 2, γ and τ (exact, up to 100,000 digits), plus digit sums of any whole-number expression (100!, 2^1000).
- Several streams at once: multi-question messages, library → maths chains (population ÷ 2, height in feet,
  years since), comparisons of two facts, and definitions blended from several sources with an agreement score.
- Wikipedia import keeps measurements from `{{convert}}` templates (heights, lengths, areas were lost before).
- Kepler's library: general-knowledge answers from Simple English Wikipedia, Open English WordNet and your own
  files (`kepler learn`), with optional live Wikipedia lookup. Typed decisions (answer / unsure / unknown) with
  confidence and source; "tell me more". Retrieval and extraction only, no language model.
- `kepler bot`: full-screen chat app with a live "understood / memory / your training" panel and clickable examples.
- English layer: slang, contractions, typo correction (names and metric names protected), number words and
  arithmetic phrasing, shown as "read as: …". Your own words via `/alias`.
- Knowledge base of maths, statistics, monitoring and Kepler terms, plus small talk.
- Conversation memory for maths follow-ups ("and for 20?", "double it", "why?"). When it doesn't understand,
  it says so, offers two guesses, and learns from your 1/2 answer.
- Maths reasoning engine: arithmetic, percentages, statistics, primes, equations and systems, algebra, derivatives,
  integrals and limits, answered exactly with numbered steps and a check (`solve 2x + 3 = 7`, `15% of 200`).
  Deterministic (sympy), no language model; new dependency `sympy`.
- Word problems and textual maths: series (sum of the first n …), sequences, number facts, counting, probability,
  unit conversion, algebra with conditions, "a number" problems, ages, motion, money, interest, work and ratios.
- `kepler teach`: an offline chat box to test the bot and train it: confirm (`/y`), correct (`/n INTENT`), or
  create your own intents (`/new NAME REPLY`). Lessons live in `~/.kepler/bot_training.json` and apply everywhere.

## 0.4.0 (2026-10-20)

**Packaging**
- Installable wheel with the dashboard bundled inside (`make build` → `dist/`).
- `kepler serve`: one command runs the API, dashboard and background worker.
- Docker image (`Dockerfile`, `docker-compose.yml`), running as a non-root user with data in a `/data` volume.
- Data now lives in `~/.kepler/kepler.db` by default (override with `KEPLER_DB`); `run.sh` keeps using `backend/data`.
- One version number everywhere (`kepler/__init__.py`).
- CI on GitHub Actions: lint + tests, dashboard type-check/build, wheel artifact.

**Security**
- CORS is same-origin by default (was: any website).
- Demo controls (inject incident, reset data) only work while demo mode is on.
- CSV uploads are read only up to their 50 MB limit.
- The feedback model is stored as JSON instead of pickle; old pickled models are ignored, never loaded.
- New access gate for `/api` routes (`KEPLER_AUTH`). The dashboard sign-in is not built yet, so local setups run
  with `KEPLER_AUTH=off`.

**Fixes**
- Unknown `/api/...` paths return a JSON 404 instead of the dashboard page.

**Detection**
- Kepler no longer re-uses evidence from an outage it already reported (no duplicate alerts after recovery).

**Payments**
- All payment features disabled: no prices, bills or checkout anywhere (`PAYMENTS_ENABLED = False`).

## 0.3.0
- Three detection models named after Kepler's laws: Orbit, Area, Time.
- Full-screen terminal app, chat bot, device integrations (notifications, background agent, completions).

## 0.2.0
- Integrations: Prometheus, Datadog, New Relic, CloudWatch, PostHog, Mixpanel, Amplitude, Sentry, Postgres,
  Segment, OpenTelemetry; incidents to Grafana, Datadog Events and webhooks.

## 0.1.0
- First version: anomaly detection engine, dashboard, CLI, demo simulator.
