# Kepler: metric watchdog for startups

Kepler watches your product and engineering metrics (signups, errors, latency, job failures…),
learns what "normal" looks like for **your** data, and when something breaks it tells you
**what** broke, **how sure** it is and **where**: `api_errors ▲ +940% · where: platform=ios · 96% confidence`.

No LLMs. Every alert is a **typed decision** produced by purpose-trained statistical and ML models,
so it is cheap to run, deterministic and explainable.

## Install and run

**From source (development)**

```bash
make setup      # Python venv + dashboard dependencies (needs uv and Node 20+)
make dev        # http://localhost:8000 with demo data
```

**As a package**

```bash
make build                                   # → dist/kepler_watchdog-1.0.0-py3-none-any.whl (+ source archive)
pip install dist/kepler_watchdog-1.0.0-py3-none-any.whl
kepler serve                                 # http://127.0.0.1:8000, data in ~/.kepler/kepler.db; prints the sign-in key
```

**With Docker**

```bash
docker compose up --build                    # http://localhost:8000, data in the kepler-data volume
docker compose logs kepler                   # the dashboard sign-in key
```

On first start with demo data, Kepler generates 21 days of a simulated startup ("Orbitly"), detects past
incidents, auto-labels them and trains the models (about 15 s). On the Overview page, use
**Demo: break something** to inject a live incident.

Settings come from environment variables; see [.env.example](.env.example).

**Access.** Every `/api` route and the dashboard need the workspace access key (`KEPLER_AUTH=on`, the default).
`kepler serve` prints it, and `kepler key` shows it. The dashboard asks for it once, then keeps an HttpOnly session
cookie for 30 days. The `kepler` CLI on the same machine finds the key of a local server by itself. Rotating the key
(`kepler key --rotate`, or Settings) signs everyone out. Before exposing Kepler beyond `127.0.0.1`, put HTTPS in
front and set `KEPLER_SECURE_COOKIES=on`: see [docs/deploy.md](docs/deploy.md).

Other tasks: `make test` (test suite), `make lint`, `make stress` (stress test), `make release` (everything, see
[docs/RELEASE.md](docs/RELEASE.md)), `make help`. For hot reload, run `cd frontend && npm run dev` (port 5173,
proxies `/api` to 8000) together with `KEPLER_AUTH=off backend/.venv/bin/uvicorn kepler.api:app --app-dir backend --reload`.

## Plans and billing

Kepler is **free during early access**: every feature is included, and **nothing can be charged**. A Razorpay billing
integration is built in but **disabled**. Five separate locks must all be opened before any payment can happen, and
the first is `CHARGING_ALLOWED = False` in the code. No Razorpay account, keys or bank details are set up anywhere in
this repository. While billing is off:

- every checkout returns 403
- the webhook returns 404
- no request ever reaches Razorpay
- no price is shown

You can see this with `kepler billing`, in **Settings → Plan & billing**, or at `GET /api/billing`.
[docs/billing.md](docs/billing.md) explains the design, and the steps to follow if you decide to charge later.

## Shipping it

| Path | What it is |
|------|-----------|
| `make release` | Lint, tests, the wheel and source archive, a smoke test of the installed wheel, and the website |
| `site/` | The product website: landing page and pricing ("no charge during early access"); plain HTML on any static host |
| `legal/` | Draft EULA, terms, privacy, refund, delivery and contact pages, with `{{PLACEHOLDERS}}` to fill. Have a lawyer review them |
| `LICENSE`, `THIRD_PARTY_NOTICES.md` | Proprietary licence, and the open-source components with their licences (`make notices`) |
| [docs/RELEASE.md](docs/RELEASE.md) | Version bump, private distribution, publishing the site |

## Stress test

```bash
cd backend && .venv/bin/python stress/stress.py            # ~2 min, exit code 0 only with zero errors
```

It starts its own server on a throwaway database and attacks every surface at once: 24 concurrent clients on
every API endpoint (valid and hostile input: bad JSON, NaN, huge values, unicode names, ancient timestamps, forged
keys), engine edge cases (all-zero, constant, negative, 1e15, sparse, single-point and high-cardinality metrics),
300+ random and adversarial messages to the Kepler bot, every CLI command, and a random key-mashing session in
the terminal app. Errors are 5xx responses, timeouts, crashes, tracebacks, NaN in responses, out-of-range
confidences, and an API p95 above 3 s. Rejecting bad input with a 4xx is correct behaviour and counted separately.

Current result: 0 errors on 4 consecutive seeds, about 3,300 successful actions per run, p50 ≈ 30 ms and
p95 ≈ 1.9 s under 24 concurrent clients.

**Manual test with real data:** [docs/manual-test.md](docs/manual-test.md) replays real datasets with labelled anomalies
(Numenta Anomaly Benchmark) through a local Postgres. Kepler watches it with a scheduled SQL pull and sends signed
webhook alerts, and `scripts/manual_test/check.py` scores what it caught.

**Real-data benchmark:** `cd backend && .venv/bin/python -I stress/bench_nab.py --tier all` replays the 47 real series of
the Numenta Anomaly Benchmark (counts and gauges, 98 labelled anomalies) the way production sees them: it trains on the past, scores forward and retrains weekly.
It counts labelled anomalies caught (within NAB's windows and, stricter, within 3 hours of the label) and false
alarms, and compares them with the saved baseline
(`stress/bench_nab_baseline.json`). A model change is kept only if it catches more without more false alarms.

## Models: Orbit, Area, Time

Three detection models, named after Kepler's three laws of planetary motion. Pick a workspace default
(Models page, `kepler tier time`, or "switch to time" in chat); any metric can override it
(`kepler metric signups --tier orbit`). `kepler compare <metric>` runs all three on the same data.

| | ◯ **Orbit**: 1st law (every orbit is an ellipse) | ◐ **Area**: 2nd law (equal areas in equal times) | ◉ **Time**: 3rd law (T² ∝ a³) |
|---|---|---|---|
| Idea | the shape of normal | steady, consistent sweep | relates everything to everything |
| Baseline | shared 7-day model, no training | trained per metric **and** slice | trained per metric, slice **and exact segment** (ios × EU) |
| Evidence | 15 min | 15 min – 1 h | 15 min – 4 h (slow burns) |
| Alert filter | statistics only | + learns from your 👍/👎 | + learns from your 👍/👎 |
| Explanation | where (best dimension) | where it broke | + impact in real units, incidents linked across metrics, numbered reasoning chain |
| Caught: 8 real incidents | 5/8 | 8/8 | 8/8 |
| Caught: 3 hard cases (2 slow burns, 1 iOS × EU-only) | 1/3 | 2/3 | **3/3** |
| Noise alerts / week | 3 | 0 | 0 |
| Compute per metric per 5-min check | **32 ms** | 333 ms | 714 ms |

**Every model is free, and no prices are shown anywhere**: billing is disabled (see
[Plans and billing](#plans-and-billing)). The numbers come from `backend/stress/bench_tiers.py --write`, run on the
simulator.

## How it decides

| Layer | Shared (works on day 1) | Custom (trained per customer) |
|---|---|---|
| **Baseline**: what should the value be? | trimmed mean of the same time-of-day on similar days (weekday/weekend) over 14 days, robust MAD noise, exact Poisson tests for counts, 3/6/12-bucket evidence pooling | per metric **and per slice**: learned weekly profile + time-of-day noise profile, past incidents excluded from training |
| **Filter**: is it worth an alert? | statistical prior on z-score and % change | logistic regression trained on the team's 👍/👎 labels, blended in as labels grow (weight n/(n+40), max 60%) |
| **Drilldown**: where? | Adtributor-style attribution: explanatory power + Jensen-Shannon surprise per dimension value | |

Every metric is watched as a whole and per slice (each dimension value), so a broken Android signup
form is caught even when the total barely moves. Each 5-minute window opens at most one new incident per metric
and direction (the strongest candidate), so one outage produces one alert.

Measured on the simulator (14 days, 5 metrics, ~35 watched series): 13/14 real incidents caught by the
shared base model; with trained models, last week shows 8/8 caught, 0 noise alerts and 2 minor blips.
These numbers are in-sample on synthetic data; expect real data to be noisier.

## Integrations

Kepler plugs into the tools teams already use (see [docs/integrations.md](docs/integrations.md) for the market analysis):

| | Tools |
|---|---|
| **Pull metrics from** | Prometheus (and Mimir/Thanos/VictoriaMetrics), Datadog, New Relic, AWS CloudWatch, PostHog, Mixpanel, Amplitude, Sentry, Postgres |
| **Receive data from** | Kepler push API + Python SDK, Segment (Webhook destination), OpenTelemetry (OTLP/HTTP JSON at `/v1/metrics`), CSV upload |
| **Send incidents to** | Slack, PagerDuty, email (SMTP), Grafana annotations, Datadog Events, signed webhook |

Each integration is one entry in a registry (`backend/kepler/integrations/`) that declares its form fields,
so the dashboard's Integrations page and `kepler integrations` pick up new ones automatically.

## Terminal app & CLI

```bash
cd backend && uv pip install -e .      # or: ./run.sh once, then use backend/.venv/bin/kepler
kepler                                  # full-screen app
```

**`kepler` (no arguments)** opens the full-screen terminal app (`docs/screenshots/`):

- **Opening screen**: server status, metrics watched, open incidents, alert filter, background agent, tips.
- **Kepler AI tab (`7`)**: the full Kepler AI chat inside the app, with the conversation on the left and a live panel on the
  right (what it understood, memory, library, your training, clickable examples). It does maths and proofs,
  general knowledge, PDF write-ups (`/pdf`, `/pdf all`, `/open`) and teaching (`/y`, `/n`, `/new`, `/alias`), and it
  can act on your metrics. The small side chat hides while you're on this tab. `kepler bot` opens the same panel
  directly.
- **No server running?** `kepler` starts one on this machine for as long as the app is open, so you always get every
  tab. Its log goes to `~/.kepler/server.log`. For a server that keeps running (web dashboard, alerts), use
  `kepler serve`. Kepler AI opens on its own only when the server can't be reached and Kepler can't start one
  (it's on another machine, or something else is using the port).
- **Six tabs, same as the web dashboard**: Overview, Metrics (braille chart, ranges, slices), Incidents,
  Models, Integrations (forms generated from each tool's fields, with Test / Save), Settings (alerting, Slack,
  API key, this device).
- **Chat with Kepler** (`/` to focus, Ctrl+K to hide). It's the same bot as `kepler bot`: your metrics, maths and
  proofs, general knowledge, write-ups (`/pdf`, `/pdf all`, `/open`) and teaching (`/y`, `/n`, `/new`, `/alias`). Kepler is a Jev-style bot, not an LLM. A trained intent
  model (TF-IDF + logistic regression over 22 intents, 97% on held-out phrasings) plus slot extractors turn
  each message into a typed decision (`◆ why_metric p=0.99 metric=api_errors`) that Kepler then acts on.
  It remembers context ("why did signups drop?" → "label it real"), asks which metric you meant when one is
  missing, and offers the top two choices when it isn't sure.
- **Keys**: `1`-`6` tabs · `/` chat · `Ctrl+P` command palette · `t` train · `d` demo · `o` web · `?` help · `q` quit.

**Maths, worked out step by step.** Kepler answers maths questions with a deterministic reasoning engine
(`backend/kepler/bot/reasoning.py`): no language model. It parses the question, solves it exactly with sympy,
shows numbered reasoning steps, and checks the answer. Equations are substituted back, integrals differentiated
back, and percentages recomputed.

```
you › solve x^2 - 5x + 6 = 0
◆ math  p=0.99  kind=solve
Problem  x^2 - 5·x + 6 = 0
Reasoning
  1. Equation: x^2 - 5·x + 6 = 0
  2. Quadratic: a = 1, b = -5, c = 6
  3. Discriminant b² − 4ac = (-5)² − 4·1·6 = 1 > 0 → two real roots
  4. x = (−b ± √disc) ÷ 2a = (5 ± √1) ÷ 2
Answer   x = 2, x = 3
Check    check: x = 2: 0 = 0 ✓; x = 3: 0 = 0 ✓
```

**Word problems and textual maths** (`backend/kepler/bot/wordmath.py`) are read with rules too: English becomes
equations ("5 more than twice a number is 17" → 2x + 5 = 17), which are solved and checked the same way. Number
words ("three hundred and forty-two") are understood. It handles:

- series: sum of the first n natural / odd / even numbers, squares and cubes (a formula when n is a letter, with
  the derivation), integer ranges, multiples of 3 or 5 below 1000, Σ notation, digit sums
- sequences: next term, nth term formula, kth term and partial sums (arithmetic, geometric, Fibonacci-style, polynomial)
- number facts: nth prime, prime counts, Fibonacci, divisors, perfect / square / divisible, binary, hex and Roman numerals
- counting and probability: combinations, arrangements (including letters of a word), handshakes, dice, coins, cards
- unit conversion: length, mass, time, volume, data, speed, temperature
- algebra with conditions: `if a + b = 10 and a - b = 4, what is ab`, `f(x) = 2x + 3, find f(5)`, `find x if …`
- word problems: "a number" sentences and step chains, two numbers, consecutive integers, ages (now, in N years,
  N years ago, with he/she), heads and legs, speed / distance / time (including round-trip average speed),
  discount, tax, profit, simple and compound interest, unitary and inverse proportion, working together and pipes,
  missing values for an average, and dividing in a ratio.

It covers arithmetic (with word operators, `5!`, `mod`, `sqrt`, trig in radians or `30 degrees`, `log` base 10
and `ln`), percentages (`15% of 200`, `30 is what percent of 120`, `change from 120 to 150`, `increase 80 by 25%`),
statistics (mean, median, mode, std, variance, …), gcd/lcm, primes and prime factors, equations and systems,
factor/expand/simplify, derivatives, integrals and limits. Input is checked against a whitelist and sizes are
estimated before computing, so `9^9^9` or code-like input is refused instantly. Kepler commands like
"show the last 5 incidents" still go to the bot.

**Chat in full screen: `kepler bot`** (or `make chat`). The conversation sits on the left. On the right you see
what Kepler understood (intent, confidence bars for the top 3, and how it read your English), what it remembers,
and what you've taught it. Click an example to ask it. Ctrl+Y confirms an answer, F1 shows help, Ctrl+B hides
the panel and ↑/↓ recalls earlier messages. Every `kepler teach` command works here too. It runs offline;
`--live` adds real answers from your server.

**It understands everyday English.** Before anything else, an English layer rewrites the message and shows
"↳ read as: …" when it changed something:
- slang and contractions: `wats`, `u`, `plz`, `rn`, `dont`
- typos, corrected to known words: `shw me api erors` → `show me api errors`. Names, metric names and ordinary
  words like "space" or "there" are never changed.
- number words: `fifteen percent of two hundred`
- arithmetic phrasing: `add 5 and 7`, `subtract 3 from 10`
- number lists without commas: `what comes after 2 4 8 16`

It also has a **knowledge base** (`what is a prime number`, `what does anomaly mean`, `define median`,
`who are you`, small talk) and **conversation memory** for maths. After `sum of first 10 cubes`, you can say
`and for 20?`, `what about squares?`, `double it`, `is it prime?`, `in binary` or `why?`. When it really
doesn't understand, it says so and offers its two best guesses. Answer 1 or 2 and it **learns that sentence**.
`/alias sigs = signups` teaches it your own words.

**General knowledge: Kepler's library.** Kepler answers general questions from datasets you feed it, still without
a language model. Each answer is a typed decision: **answer**, **unsure** (a best guess, labelled as one) or
**unknown** (it says so). It comes with a confidence and its source, with link and licence.

```bash
kepler learn wikipedia        # Simple English Wikipedia: ~276k articles (358 MB download, ~6 min to index, ~530 MB)
kepler learn wordnet          # Open English WordNet: ~212k word meanings and synonyms (13 MB)
kepler learn ~/notes          # your own .md .txt .html .csv .json .docx .pdf files (PDF needs: pip install pypdf)
kepler learn --web on|off     # look up Wikipedia online when the library isn't sure (on by default)
kepler learn --status         # what it knows
kepler learn --ask "who wrote romeo and juliet"
```

How it answers:
1. Read the question type (who / what / when / where / how many / why / yes-no) and find the article titles it
   mentions.
2. Search 820k passages (SQLite FTS5, BM25) and score every sentence. Scoring looks at idf-weighted coverage of
   the question, phrase matches, and whether the sentence holds the right kind of answer: a date for "when", a
   number with units for "how hot / far / fast", a reason for "why", a person who isn't the subject for "who".
3. Pick the best sentence and calibrate the confidence from the evidence.
4. When the library isn't sure, look the question up on Wikipedia online. Only the question words are sent, at
   most one request a second, and lookups pause if Wikipedia asks. The pages it fetches are saved, so next time it
   answers offline.

Ask "tell me more" to keep reading the article. On a 40-question general-knowledge check it answered most
correctly with sources. When it can't find good evidence, it says "unsure" or "I can't confirm" instead of
inventing an answer. It is a retrieval engine, not a reasoning AI. It finds and quotes what its sources say, so
questions that need combining several facts, opinions or very recent events are beyond it.

**Advanced reasoning** (`backend/kepler/bot/advanced.py`):
- **Proofs**: induction for sums (`prove that 1 + 2 + ... + n = n(n+1)/2`), identities (`prove sin(x)^2 + cos(x)^2 = 1`),
  inequalities by rewriting as squares (`prove x + 1/x >= 2 for positive x`), and classic proofs (infinitely many
  primes, √p irrational, Cantor's diagonal, halting problem, 0.999… = 1, Pythagoras). False claims get a
  counterexample instead (`prove x^2 >= x` → false at x ≈ 0.72).
- **Advanced maths**:
  - matrices: determinant, inverse, eigenvalues and eigenvectors, rank, rref and products
  - differential equations, each solution checked by substitution
  - number theory: big primality (`is 2^127 - 1 prime`), factoring, `7^222 mod 13`, totient, integer equations, the
    Chinese remainder theorem
  - series convergence, with the test that decides it and the sum when known
- **Conjecture lab**: Goldbach and Collatz up to 2 million, twin primes, Fermat's Last Theorem for small cases, and
  the Riemann hypothesis. For Riemann it counts every zero in the critical strip up to height T with the
  Riemann–von Mangoldt formula and checks that all of them lie on the critical line. Results are always labelled
  "evidence, not a proof".
- **Open problems**: all seven Millennium Prize Problems with their statement, status and why they're hard. Kepler
  never claims to solve one. It says plainly that they're unsolved (except Poincaré, proved by Perelman in 2003)
  and offers experiments instead.

**Formal write-ups: LaTeX and PDF** (`backend/kepler/bot/latex.py`). Kepler typesets its answers as a paper:
a title block, a table of contents, and one section per question. Proofs use theorem and proof environments, with
induction laid out formally: base case, inductive hypothesis, then the inductive step in aligned equations.
Solutions get numbered steps or display maths, and every section has a boxed answer, a verification paragraph,
and sources for any library facts.

```bash
brew install tectonic                       # the LaTeX engine (pdflatex, xelatex or lualatex also work)
kepler write "prove that 1 + 2 + ... + n = n(n+1)/2" "solve y'' + y = 0" --open
kepler write "integrate x^2 from 0 to 3" --tex     # LaTeX source only
```

In `kepler teach` and `kepler bot`, use `/pdf` (last answer), `/pdf all` (the whole session), `/tex` and `/open`, or
just ask: "write a formal proof that there are infinitely many primes as a pdf". Documents are saved to
`~/Documents/Kepler` (or `KEPLER_DOCS`), as `.tex` plus `.pdf`.

How it's built:
- The maths engine provides exact LaTeX (from sympy) for proofs, equations, integrals, matrices and ODEs, and a
  converter turns everything else (√, Σ, ≥, π, x^2, C1, matrices) into LaTeX.
- Compiling is sandboxed: Tectonic `--untrusted`, or `-no-shell-escape` for the others, with a time limit.
- If the formal layout ever fails to compile, a plain layout is compiled instead, so you always get a PDF.
- The first Tectonic run downloads the LaTeX packages it needs (a few minutes, once); after that a document
  compiles in about a second.

**Several streams of knowledge at once.** One message can use several engines together
(`backend/kepler/bot/streams.py`):
- **Several questions:** `is api_errors ok and what does anomaly mean?` gets one answer per part, each from the
  engine that knows it. Word problems that span several sentences stay together.
- **Facts feeding maths:** `population of india divided by 2`, `height of mount everest in feet`,
  `how many years ago was einstein born`, `how old would einstein be today`. The library finds the number (with
  the quoted sentence and its source), then maths or unit conversion uses it. Every step is labelled `[library]`
  or `[maths]`.
- **Comparisons:** `which is more populous, india or china?`, `which is taller, everest or k2?`. Two lookups,
  both converted to the same unit, then compared.
- **Blended sources:** definitions come from every source that knows the word (Kepler's knowledge base, the
  dictionary, Wikipedia). Kepler shows how much they agree and is more confident when they do. Unrelated sources
  are left out.

**Train the bot yourself: `kepler teach`** (or `make teach`) is a plain chat box just for you. It runs offline:
no server, and nothing leaves your machine (`--live` adds real answers from your server). Type anything and
Kepler shows the typed decision it made, with the two runners-up:

```
you › gimme the vibe check
◆ decide  p=0.34
   2 status 0.30   3 tiers 0.03
you › /n status
  ✓ learned gimme the vibe check → status   (now: status p=0.98)
you › who is on call this week
you › /new on_call Priya is on call until Friday
  + new intent on_call → "Priya is on call until Friday"
```

`/y` confirms a correct answer, `/n INTENT` (or `/n 2`) corrects a wrong one, and `/new NAME REPLY` creates your own
intent. `/test` scores the bot, and `/examples`, `/undo` and `/reset` manage what you taught. The bot retrains in
under a second after each lesson. Lessons are saved as plain JSON in `~/.kepler/bot_training.json` and used
everywhere: `kepler chat`, `kepler ask` and the full-screen app.

**Every dashboard feature is also a one-shot command** (all take `--json`):

| | |
|---|---|
| Models | `tiers` · `tier orbit\|area\|time` · `compare M` · `metric M --tier orbit\|area\|time\|default` |
| Look | `status` · `decide M [--exit-code]` · `metrics` · `metric M [--hours 6 --slice platform=ios]` · `incidents [--open]` · `explain ID` · `watch [--notify]` · `models` · `alerts` |
| Write | `write "QUESTION" … [--open] [--tex] [--out FILE.pdf] [--title T]` · in chat: `/pdf` `/pdf all` `/tex` `/open` |
| Know | `learn wikipedia\|wordnet\|PATH` · `learn --web on\|off` · `learn --status` · `learn --ask "…"` · `learn --forget SOURCE` |
| Talk | `ask "why did signups drop?"` · `chat` (conversation without full screen) · `bot [--live]` (full-screen chat, test and train) · `teach [--live]` (plain chat box to train) |
| Act | `label ID real\|false` · `train` · `send M 1 --dim k=v` · `demo [scenario\|reset]` · `metric M --alert-when up --unit ms` · `metric M --delete` |
| Configure | `settings --sensitivity 70 --min-change 15 --slack URL --demo off` · `key [--copy\|--rotate]` · `config --set-url URL` |
| Integrate | `integrations` · `connect datadog api_key=… app_key=… query=… metric=… [--test]` · `pulls [run\|rm ID]` · `destinations [rm ID]` · `import file.csv` · `analyze file.csv` (offline, no server) |
| Device | `open [incident 40\|metric signups]` · `copy key\|decision 40` · `agent install\|uninstall\|status` · `completion zsh\|bash` |

**Device integration**
- **Desktop notifications** (macOS Notification Center via `osascript`, `notify-send` on Linux): from the app while
  it's open, from `kepler watch --notify`, and from the **background agent**.
- **Background agent**: `kepler agent install` registers a launchd agent (systemd user service on Linux) that starts
  at login and notifies you of new incidents with no terminal open. Use `kepler agent install --print` to inspect it first.
- **Clipboard and browser**: copy keys or decision JSON; open the dashboard at a specific incident (`#/incident/40`).
- **Incident notes**: `kepler note 40 "rolled back deploy 4.2"` (or the Notes card in the dashboard) keeps what the
  team found with the incident; `kepler explain 40` shows them.
- **Weekly report**: `kepler report` sums up the last 7 days (incidents, trend, how long they lasted, labels,
  outages); `kepler report --send` posts it to Slack and email, so a weekly cron gives the team a digest.
- **Health check**: `kepler doctor` checks the server, access key, worker, data, models, pulls and alert routing,
  says what's wrong and how to fix it, and exits with code 1 on a problem.
- **No data alerts**: a metric that stops reporting for longer than is usual for it raises a "no data" incident,
  and resolves when readings return.
- **Maintenance mode**: `kepler maintenance 2h` pauses every alert during planned work (`off` ends it); detection
  and incidents go on.
- **Mute alerts**: during a deploy or maintenance, `kepler metric checkout_errors --mute 2h` pauses that metric's
  alerts (`--mute off` ends it; or 🔕 Mute on its dashboard page). Incidents are still detected and recorded.
- **Shell completion**: `kepler completion zsh > "${fpath[1]}/_kepler"` completes commands, flags, and live metric
  names and incident IDs from your server.

Machine-readable decision over HTTP: `GET /api/v1/decision/{metric}` returns `normal | watch | anomaly`
with `anomaly_probability` (or the typed incident).

## Layout

```
backend/kepler/engine/   seasonal.py (baselines) · classifier.py (feedback filter) · drilldown.py · detector.py (lifecycle)
backend/kepler/integrations/   base.py (registry) · pull.py · inbound.py (Segment, OTLP) · outbound.py (Grafana, Datadog, PagerDuty, email, webhook)
backend/kepler/cli/      commands.py (every command) · client.py · render.py (shared rich views)
backend/kepler/bot/      intents.py · model.py (intent classifier) · slots.py · brain.py (dialogue + actions) · reasoning.py + wordmath.py (maths) · language.py (English) · knowledge.py · dialogue.py · mind.py (pipeline) · streams.py (several streams at once) · advanced.py (proofs, lab, open problems) · latex.py (LaTeX/PDF write-ups) · chat_app.py (`kepler bot`) ·
backend/kepler/library/  index.py (SQLite FTS5) · ingest.py (Wikipedia, WordNet, your files) · answer.py (question answering) · web.py (online lookup) · teach.py + store.py (your training)
backend/kepler/tui/      app.py (Textual full-screen app)
backend/kepler/billing/  __init__.py (the locks, status) · plans.py (plan catalog) · razorpay.py (orders, subscriptions, signatures, webhooks)
backend/kepler/          api.py (FastAPI + worker) · config.py · security.py (access key, sign-in sessions) · device.py (notify, clipboard, agent) · connectors.py · notify.py · simulator.py · db.py
frontend/src/            React + Recharts dashboard (Overview, Metric, Incidents, Models, Integrations, Settings)
```

## Not built yet

- **Multi-tenant workspaces** and per-user accounts: one server is one workspace with one access key, and one plan.
- **Remaining hardening:** encrypted connector secrets, and an optional block on internal addresses for
  connector/webhook URLs.
- **Charging:** the Razorpay integration is built and tested but switched off on purpose
  ([docs/billing.md](docs/billing.md)).
- Postgres instead of SQLite, and a hosted deployment.
