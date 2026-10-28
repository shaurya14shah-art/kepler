"""The bot's understanding: held-out phrasings (not in the training templates) and slot extraction."""
from kepler.bot import model
from kepler.bot.slots import Context, extract

CTX = Context(
    metrics=["signups", "active_sessions", "api_errors", "p95_latency_ms", "job_failures"],
    slices={"api_errors": ["platform=ios", "platform=android", "region=EU"], "signups": ["platform=android", "region=IN"]},
    tools={"datadog": "datadog", "grafana": "grafana", "new relic": "newrelic", "sentry": "sentry", "aws": "cloudwatch"},
    scenarios=["ios_release_bug", "android_signup_broken", "eu_db_slow", "webhook_queue_stuck", "india_cdn_outage"],
)

HELD_OUT = [
    ("yo kepler", "greet"), ("morning!", "greet"),
    ("cheers mate", "thanks"), ("thank you so much", "thanks"),
    ("what are you able to do", "help"), ("how do i talk to you", "help"),
    ("how's everything doing right now", "status"), ("is prod ok", "status"), ("anything broken at the moment?", "status"),
    ("give me a quick health summary", "status"),
    ("list the open incidents", "list_incidents"), ("what incidents happened this week", "list_incidents"),
    ("show me critical alerts from today", "list_incidents"), ("any incidents on signups recently", "list_incidents"),
    ("tell me everything about #40", "explain_incident"), ("what was incident 12", "explain_incident"),
    ("explain the most recent one", "explain_incident"),
    ("why are api errors spiking", "why_metric"), ("signups fell off a cliff, why", "why_metric"),
    ("whats causing the latency problem", "why_metric"), ("why did job failures go up", "why_metric"),
    ("plot signups over the last 3 days", "metric_detail"), ("show me a graph of api errors", "metric_detail"),
    ("chart latency for 6h", "metric_detail"), ("what does sessions look like this week", "metric_detail"),
    ("is latency normal right now", "decide"), ("are signups okay", "decide"), ("should I be worried about job failures", "decide"),
    ("what's the anomaly probability of api errors", "decide"),
    ("split api errors by platform", "breakdown"), ("which region is off for signups", "breakdown"),
    ("show slices of latency", "breakdown"),
    ("yep that one was real", "label_real"), ("mark incident 40 as a true positive", "label_real"),
    ("that was just noise", "label_false"), ("label #12 a false positive", "label_false"),
    ("please retrain", "train"), ("learn from the labels i gave", "train"),
    ("simulate a broken ios release", "demo_inject"), ("break something for the demo", "demo_inject"),
    ("which integrations do you have", "integrations"), ("what can kepler pull data from", "integrations"),
    ("how do I hook up datadog", "connect_tool"), ("set up grafana annotations", "connect_tool"),
    ("connect to new relic", "connect_tool"),
    ("set the sensitivity to 75%", "set_sensitivity"), ("you're too noisy", "set_sensitivity"),
    ("what are my settings", "settings"), ("is slack set up", "settings"),
    ("how accurate are your models", "models"), ("what have you learned so far", "models"),
    ("what did you send to slack", "alerts_log"), ("show the notification log", "alerts_log"),
    ("open the web dashboard", "open_dashboard"), ("open #40 in my browser", "open_dashboard"),
    ("copy my api key", "copy"), ("copy the json for incident 40", "copy"),
    ("whats wrong with signups", "why_metric"), ("check api errors", "decide"), ("graph p95 latency", "metric_detail"),
    ("how much do the models cost", "tiers"), ("which model is best for me", "tiers"),
    ("switch everything to orbit", "set_tier"), ("upgrade signups to the time model", "set_tier"),
]


def test_held_out_intent_accuracy():
    wrong = []
    for text, want in HELD_OUT:
        _, delex = extract(text, CTX)
        got, p = model.classify(delex)[0]
        if got != want:
            wrong.append((text, want, got, round(p, 2)))
    acc = 1 - len(wrong) / len(HELD_OUT)
    print(f"\nheld-out intent accuracy: {acc:.0%} ({len(HELD_OUT) - len(wrong)}/{len(HELD_OUT)})")
    for w in wrong:
        print("  miss:", w)
    assert acc >= 0.85


def test_slots():
    s, d = extract("why did api errors spike on ios in the last 6 hours?", CTX)
    assert s["metric"] == "api_errors" and s["hours"] == 6 and s["slice"] == "platform=ios"
    assert "metricx" in d and "durx" in d
    s, _ = extract("explain #40", CTX)
    assert s["incident"] == 40
    s, _ = extract("set sensitivity to 75%", CTX)
    assert s["pct"] == 0.75
    s, _ = extract("how do i connect new relic", CTX)
    assert s["tool"] == "newrelic"
    s, _ = extract("show signup trend", CTX)        # singular alias
    assert s["metric"] == "signups"
    s, _ = extract("plot latency", CTX)             # p95_latency_ms -> 'latency'
    assert s["metric"] == "p95_latency_ms"
    s, _ = extract("is jobb_failures ok", CTX)       # typo -> fuzzy match
    assert s["metric"] == "job_failures"
    s, _ = extract("list critical incidents that are still open", CTX)
    assert s["severity"] == "critical" and s["open"]
    s, _ = extract("simulate the webhook queue problem", CTX)
    assert s["scenario"] == "webhook_queue_stuck"


def test_unique_word_aliases():
    s, _ = extract("plot sessions last 6 hours", CTX)
    assert s["metric"] == "active_sessions"
    s, _ = extract("why are failures up", CTX)
    assert s["metric"] == "job_failures"


def test_fuzzy_match_inside_mixed_token_does_not_crash():
    # 'signupz' glued to a digit: the fuzzy matcher finds it, a strict word-boundary search would not
    s, d = extract("x4signupz?", CTX)
    assert s.get("metric") == "signups" and "metricx" in d
