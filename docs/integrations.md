# Where Kepler's data lives today, and how Kepler plugs in

Kepler watches time-series metrics: product signals (sign-ups, sessions), reliability signals (errors,
latency, failed jobs) and infrastructure signals. Startups and tech teams record that data in four kinds of tools.

## 1. Observability / monitoring: infra + service metrics

| Tool | Why it matters | Kepler integration |
|---|---|---|
| **Prometheus** (+ Grafana for dashboards) | The open-source default, especially on Kubernetes. Grafana's 2026 survey (1,363 respondents): 77% investing in Prometheus, 59% running it in production. | **Pull**: PromQL `query_range`. Also covers Grafana Mimir, Cortex, Thanos and VictoriaMetrics (same API). |
| **OpenTelemetry** | The fastest-growing standard: 76% investing, 41% in production, and more teams growing their usage of it than of Prometheus (47% vs 42%). | **Push**: OTLP/HTTP JSON receiver at `/v1/metrics` (gauges, delta and cumulative sums, histograms). |
| **Grafana** | The dashboard layer on top of Prometheus, Loki, cloud metrics… | **Write-back**: incidents become annotations on dashboards and are closed when they resolve. |
| **Datadog** | The commercial default for teams that want breadth (about 900 integrations), but expensive. | **Pull**: metric query API. **Write-back**: Datadog Events. |
| **New Relic** | Full-stack, usage-priced, generous free tier, popular with lean teams. | **Pull**: NRQL via NerdGraph (`TIMESERIES 5 minutes`, FACET → dimensions). |
| **AWS CloudWatch** | Wherever the stack runs on AWS (load balancers, Lambda, RDS). | **Pull**: `GetMetricData`, including SEARCH expressions (each series becomes a dimension value). |

## 2. Product analytics: user behaviour

| Tool | Why it matters | Kepler integration |
|---|---|---|
| **PostHog** | Repeatedly named the default for engineering-led startups: open source, generous free tier, SQL (HogQL). | **Pull**: HogQL query endpoint. |
| **Mixpanel** | Mature funnels, 1M free events/month, widely used. | **Pull**: Segmentation API, per-minute data rolled up into 5-minute windows. |
| **Amplitude** | Common as startups grow; real-time 5-minute granularity. | **Pull**: Event Segmentation API (`i=-300000`). |
| **Segment** | Not an analytics tool but the pipe that feeds them. Plugging into Segment covers every event a company tracks. | **Push**: Segment Webhook destination → `/api/v1/hooks/segment`. |

## 3. Error tracking

| Tool | Kepler integration |
|---|---|
| **Sentry**: the default error tracker for web and mobile teams | **Pull**: `events-stats` error counts, optionally split by release / OS / any tag. |

## 4. The product's own database

| Tool | Kepler integration |
|---|---|
| **Postgres** (and Supabase, Neon, Redshift, TimescaleDB) | **Pull**: scheduled read-only SQL (`ts, value, [dims]`). |

## Getting alerts out

Slack (incoming webhook), Grafana annotations, Datadog events, email over SMTP (one email per incident; the
resolution replies in the same thread), and PagerDuty (Events API v2). PagerDuty pages on
trigger, resolves the same alert when the incident resolves, and its "Test" sends a change event that never pages
anyone. There's also a signed generic webhook (`X-Kepler-Signature: sha256=HMAC`) for Opsgenie bridges, Zapier and
internal bots.

## Verification status

- Every connector is unit-tested against a mock of the vendor API: request URL, auth headers and parameters are
  asserted, and the response is the vendor's documented shape. That's 16 tests in `backend/tests/test_integrations.py`.
- Live-tested end to end on a local server: Segment and OTLP receivers, signed webhook delivery, Prometheus error path.
- **Not yet tested against real vendor accounts.** Sentry's `events-stats` response shape in particular comes from
  its public API behaviour, not an official schema page. Run each connector's "Test connection" with real
  credentials before relying on it.

## Not built (yet), roughly by value

1. OTLP protobuf encoding (most SDKs default to protobuf; JSON must be enabled today).
2. Snowflake and BigQuery SQL connectors (common at later-stage companies).
3. Google Analytics 4 (Data API, hourly at best), plus Heap and Firebase.
4. An Opsgenie native destination (the webhook covers it through a bridge today).
5. A Grafana data-source plugin, so Kepler's expected bands draw directly in Grafana panels.

Sources: [Grafana Labs Observability Survey 2026](https://grafana.com/press/2026/03/18/grafana-labs-4th-annual-observability-survey-reveals-a-field-at-a-crossroads-ai-economics-complexity-and-the-enduring-power-of-open-source/),
[Grafana: Open standards in 2026](https://grafana.com/blog/observability-survey-OSS-open-standards-2026),
[Metoro: best observability tools 2026](https://metoro.io/blog/best-observability-tools),
[Dupple: best product analytics tools](https://dupple.com/learn/best-product-analytics-tools),
[Hackceleration: product analytics for startups](https://www.hackceleration.com/labs/best/product-analytics-startups).
Several comparison guides are vendor-published (e.g. Amplitude's), so the product-analytics ranking is directional.
