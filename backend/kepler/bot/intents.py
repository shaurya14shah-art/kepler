"""What Kepler-the-bot understands. Each intent: templates used to synthesise training data.

Placeholders are filled with sample values during training only; at runtime slots are extracted separately.
"""

INTENTS: dict[str, dict] = {
    "greet": {"desc": "say hello", "t": [
        "hi", "hello", "hey", "hey kepler", "good morning", "yo", "hello there", "hi kepler how are you", "sup",
        "good evening kepler", "hiya", "nice to meet you"]},
    "thanks": {"desc": "say thanks", "t": [
        "thanks", "thank you", "thx", "cheers", "great thanks", "awesome thank you kepler", "nice one", "perfect thanks",
        "ty", "much appreciated", "good job"]},
    "help": {"desc": "what can you do", "t": [
        "help", "what can you do", "what can i ask you", "how do i use this", "commands", "show me what you can do",
        "what do you understand", "how does this work", "list your abilities", "what are your features", "?", "usage",
        "how do i use you", "what should i ask", "how do i talk to kepler", "teach me the commands"]},
    "status": {"desc": "overall health of every metric", "t": [
        "status", "how are things", "is everything ok", "how is everything looking", "give me an overview",
        "what's the status", "any problems right now", "how are my metrics", "health check", "summary",
        "is anything broken", "dashboard", "what's going on", "are we healthy", "overview please", "everything fine?",
        "show me all metrics", "how's production", "anything on fire", "is production ok", "are we ok", "is the system ok",
        "are things okay", "status report", "is the site down", "is the website down right now?"]},
    "list_incidents": {"desc": "list incidents", "t": [
        "show incidents", "list incidents", "open incidents", "what incidents are open", "any open incidents",
        "show me the last {n} incidents", "incidents today", "what broke today", "show critical incidents",
        "list {sev} incidents", "recent incidents", "what happened in the last {dur}", "show alerts",
        "incident history", "which incidents are still open", "what went wrong this week", "past incidents for {metric}",
        "show me incidents on {metric}", "all alerts", "were there any incidents yesterday"]},
    "explain_incident": {"desc": "explain one incident", "t": [
        "explain incident {id}", "explain #{id}", "tell me about incident {id}", "what happened in #{id}",
        "details for incident {id}", "why did incident {id} fire", "show #{id}", "explain it", "more details",
        "what is incident {id} about", "dig into #{id}", "open incident {id}", "break down incident {id}",
        "explain the latest incident", "tell me more about that", "show the last incident"]},
    "why_metric": {"desc": "why a metric moved", "t": [
        "why did {metric} spike", "why did {metric} drop", "why is {metric} so high", "why is {metric} down",
        "what's wrong with {metric}", "why are {metric} up", "{metric} looks weird why", "why", "why did it drop",
        "what caused the {metric} spike", "where did {metric} break", "root cause of {metric}", "why is {metric} low",
        "what's happening with {metric}", "where is the {metric} problem", "{metric} dropped why", "why did it spike",
        "what broke {metric}", "why the jump in {metric}"]},
    "metric_detail": {"desc": "show a metric chart", "t": [
        "show {metric}", "chart {metric}", "plot {metric}", "graph {metric} for the last {dur}", "show me {metric} over {dur}",
        "how does {metric} look", "{metric} chart", "open {metric}", "show {metric} last {dur}", "plot {metric} on {slice}",
        "visualise {metric}", "{metric} trend", "draw {metric}", "show {metric} for {slice}", "{metric} over time",
        "trend of {metric} this week"]},
    "decide": {"desc": "is a metric normal right now", "t": [
        "is {metric} ok", "is {metric} normal", "is {metric} healthy", "decide {metric}", "should i worry about {metric}",
        "is {metric} anomalous", "check {metric}", "is something wrong with {metric}", "{metric} ok?",
        "is {metric} fine right now", "anomaly probability for {metric}", "is {metric} behaving", "verdict on {metric}",
        "give me a decision for {metric}", "how likely is {metric} broken", "is {metric} okay", "are {metric} ok",
        "{metric} healthy?"]},
    "breakdown": {"desc": "split a metric by slice", "t": [
        "break down {metric} by slice", "{metric} by platform", "{metric} by region", "split {metric}",
        "which segment of {metric} is off", "slices for {metric}", "segment breakdown of {metric}",
        "where is {metric} different", "compare segments of {metric}", "{metric} per region", "breakdown {metric}",
        "which platform has the most {metric}", "dimensions of {metric}"]},
    "label_real": {"desc": "mark an incident as real", "t": [
        "that was real", "mark #{id} as real", "label {id} real", "yes that was a real incident", "true positive",
        "good catch", "mark it as a real incident", "this one was real", "confirm incident {id}", "real",
        "👍", "yes real problem", "that alert was correct", "label it real"]},
    "label_false": {"desc": "mark an incident as a false alarm", "t": [
        "that was a false alarm", "false positive", "mark #{id} as false", "label {id} false alarm", "not real",
        "ignore that one it was noise", "this was noise", "bad alert", "👎", "mark it as false alarm",
        "that alert was wrong", "label it false", "wasn't a real incident", "nothing was actually broken"]},
    "train": {"desc": "retrain the models", "t": [
        "train", "retrain", "retrain the models", "learn from my labels", "update the models", "train the filter",
        "refit models", "train on new data", "relearn baselines", "start training", "train now please"]},
    "demo_inject": {"desc": "inject a demo incident", "t": [
        "break something", "inject an incident", "simulate an outage", "demo {scenario}", "run the {scenario} scenario",
        "trigger a fake incident", "simulate {scenario}", "cause a demo incident", "test an incident", "break {scenario}",
        "show me a demo", "simulate a bad release", "inject {scenario}"]},
    "integrations": {"desc": "list supported tools", "t": [
        "what can you connect to", "list integrations", "which tools do you support", "integrations",
        "supported data sources", "what integrations are there", "can you pull from other tools",
        "where can you send alerts", "show connectors", "what tools work with kepler"]},
    "connect_tool": {"desc": "how to connect a tool", "t": [
        "connect {tool}", "how do i connect {tool}", "set up {tool}", "add {tool}", "integrate with {tool}",
        "pull metrics from {tool}", "send alerts to {tool}", "hook up {tool}", "{tool} integration",
        "can you read from {tool}", "configure {tool}", "link my {tool} account"]},
    "set_sensitivity": {"desc": "change alert sensitivity", "t": [
        "set sensitivity to {pct}", "make alerts less noisy", "be more sensitive", "only alert when {pct} sure",
        "change sensitivity {pct}", "fewer alerts please", "alert more often", "sensitivity {pct}",
        "raise the alert threshold", "lower the threshold to {pct}", "too many alerts", "i'm missing incidents",
        "stop bugging me so much"]},
    "settings": {"desc": "show settings", "t": [
        "show settings", "settings", "what's my configuration", "current config", "what is the sensitivity",
        "is slack connected", "show my setup", "config", "what are my alert settings", "is demo mode on",
        "is slack configured", "where do alerts go", "is the agent running"]},
    "models": {"desc": "describe the models", "t": [
        "how good are the models", "model status", "show models", "how accurate are you", "what did you learn",
        "which models are trained", "what does the filter know", "model accuracy", "how do you decide",
        "explain your models", "how do you work", "how many labels do we have"]},
    "tiers": {"desc": "compare the Orbit / Area / Time models", "t": [
        "which models are there", "show the models", "compare orbit area and time", "what does time cost",
        "orbit vs time", "which model should i use", "what is the area model", "pricing", "how much does it cost",
        "what's the difference between the models", "which model am i on", "compare models for {metric}",
        "run all models on {metric}", "is time worth it", "what model is {metric} using"]},
    "set_tier": {"desc": "switch the detection model", "t": [
        "switch to {tier}", "use {tier}", "use the {tier} model", "set the model to {tier}", "use {tier} for {metric}",
        "put {metric} on {tier}", "upgrade to {tier}", "downgrade to {tier}", "switch {metric} to {tier}",
        "make {tier} the default", "change model to {tier}", "{tier} model please"]},
    "alerts_log": {"desc": "recent alerts sent", "t": [
        "what alerts did you send", "alert log", "show notifications", "what did you post to slack",
        "recent alerts sent", "notification history", "did you notify anyone", "messages sent"]},
    "open_dashboard": {"desc": "open the web dashboard", "t": [
        "open the dashboard", "open in browser", "show this in the browser", "open web ui", "launch dashboard",
        "open #{id} in the browser", "open {metric} in browser", "take me to the website", "open the web app",
        "show me the dashboard", "where's the dashboard"]},
    "copy": {"desc": "copy something to the clipboard", "t": [
        "copy the api key", "copy key", "copy that", "copy the decision", "copy json", "copy incident {id}",
        "put the key on my clipboard", "copy it", "copy the ingest snippet", "copy decision json for #{id}"]},
}

# samples for placeholders (training only)
FILL = {
    "metric": ["signups", "api errors", "api_errors", "latency", "p95 latency", "job failures", "sessions",
               "active_sessions", "checkout clicks", "uploads", "error rate", "trial starts", "logins", "queue depth"],
    "id": ["12", "40", "7", "128", "3"],
    "n": ["5", "10", "3", "20"],
    "dur": ["6 hours", "24h", "3 days", "week", "hour", "2 days", "30 minutes", "day"],
    "sev": ["critical", "high", "medium"],
    "pct": ["70%", "80 percent", "0.6", "90%", "50%"],
    "tool": ["datadog", "grafana", "prometheus", "posthog", "mixpanel", "amplitude", "sentry", "new relic", "cloudwatch",
             "segment", "opentelemetry", "postgres", "slack", "webhook"],
    "scenario": ["ios release bug", "android signup", "eu database", "webhook queue", "india cdn outage", "ios"],
    "slice": ["ios", "android", "EU", "region=IN", "platform=web", "webhooks queue"],
    "tier": ["orbit", "area", "time"],
}
