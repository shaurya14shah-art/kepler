# Legal documents (DRAFTS)

**These are starting drafts, not legal advice.** Have a lawyer review them for your country and business before you
publish them or take payments. Replace every `{{PLACEHOLDER}}`:

| placeholder | what to put there |
|---|---|
| `{{COMPANY}}` | your legal name, or your company's registered name |
| `{{ADDRESS}}` | your registered business address |
| `{{EMAIL}}` | the support/legal email customers should write to |
| `{{JURISDICTION}}` | the country/state whose law governs the agreement, and its courts |
| `{{EFFECTIVE_DATE}}` | the date the document takes effect |
| `{{REFUND_DAYS}}` | how many days after a first payment you'll refund in full (e.g. 14) |
| `{{SUPPORT_HOURS}}` / `{{RESPONSE_TIME}}` | when you answer support, and how quickly (e.g. "2 working days") |

| file | what it is | needed for |
|---|---|---|
| [EULA.md](EULA.md) | the licence customers get to install and use Kepler | everyone who downloads it |
| [TERMS.md](TERMS.md) | terms for your website and any paid plans | the website; Razorpay activation |
| [PRIVACY.md](PRIVACY.md) | what personal data you handle, and why | the website; Razorpay; privacy laws |
| [REFUND.md](REFUND.md) | cancellation and refund policy | Razorpay activation (required) |
| [SHIPPING.md](SHIPPING.md) | delivery policy (digital: instant download) | Razorpay activation (asks for one) |
| [CONTACT.md](CONTACT.md) | how to reach you | Razorpay activation (required) |

The documents describe Kepler as it actually works: it is self-hosted, your customers' metric data stays on their
servers, Kepler AI runs locally, Wikipedia lookups send only the words of a question (and can be turned off), and
payments (if you ever enable them) are handled by Razorpay so card and bank details never reach Kepler. If you change
how the product handles data (for example, a hosted version), update PRIVACY.md first.

`make site` turns these Markdown files into the legal pages of the product website (`site/legal/*.html`).

Open-source components and their licences are listed in [../THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)
(all permissive, except certifi under MPL-2.0 and psycopg under LGPL-3.0, both used unmodified as separate packages;
point your lawyer at these two).
