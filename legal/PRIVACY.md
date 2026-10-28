# Privacy Policy

*DRAFT. Effective {{EFFECTIVE_DATE}}.*

{{COMPANY}} ("we", "us") makes Kepler, self-hosted software for monitoring metrics. This policy explains what
personal data we handle and why. Contact: {{EMAIL}}, {{ADDRESS}}.

## 1. Kepler runs on your servers

Kepler is self-hosted. **The data you put into Kepler (metrics, incidents, settings, files you index, questions you
ask Kepler AI, and what you teach it) stays on the servers where you install it. We don't receive it.** You control
it, including backups and deletion; in that respect you are the controller of any personal data it contains.

Kepler only contacts third parties when you turn on a feature that needs to:

| feature | what is sent | where | how to turn it off |
|---|---|---|---|
| Alert destinations you configure (Slack, PagerDuty, email, Grafana, Datadog, webhooks) | incident summaries | the service you configured | remove the destination |
| Data sources you connect (Prometheus, Datadog, PostHog, …) | queries for your metrics | the service you connected | remove the connector |
| Wikipedia lookup in Kepler AI (on by default) | the words of a general-knowledge question | en.wikipedia.org | `kepler learn --web off` or `KEPLER_WEB=off` |
| Dataset downloads (`kepler learn wikipedia` / `wordnet`) | a download request | Wikimedia, GitHub | don't run the command |
| Paid plans, if offered | checkout details you type into Razorpay's window | Razorpay | don't buy a plan |

Kepler has no telemetry: it doesn't report usage to us.

## 2. Data we handle ourselves

- **When you contact us** (email, support): your name, email address and what you write, to answer you.
- **When you buy a paid plan** (if offered): your name, email, billing address, plan and payment status, to provide
  the plan, issue invoices and meet tax and accounting obligations. Razorpay processes the payment; we receive a
  payment reference and status, never your full card number or bank details. See Razorpay's privacy policy.
- **Our website**: standard server logs (IP address, browser, pages requested) kept for up to 30 days for security.
  We don't use advertising or tracking cookies.

## 3. Legal bases (where the GDPR or similar laws apply)

Contract (to provide a plan you bought), legal obligation (tax and accounting records), and legitimate interests
(security of our website, answering your messages).

## 4. Sharing

We share personal data only with service providers that help us run the business (payment processing by Razorpay,
email and hosting providers), under contracts that protect it, or when the law requires. We don't sell personal data.

## 5. Retention

Support messages: up to 2 years. Billing records: as long as tax law requires (often 8 years). Website logs: 30 days.

## 6. Your rights

Depending on where you live, you may have rights to access, correct, delete, restrict or port your personal data, to
object to processing, and to complain to a data-protection authority. Write to {{EMAIL}}; we'll answer within 30 days.

## 7. Children

Kepler is a business product and is not directed at children.

## 8. Changes

We'll post updates here with a new effective date, and notify customers of material changes by email.
