# Kepler

A self-hosted metric watchdog. Kepler learns what "normal" looks like for your product and engineering metrics,
and when something breaks it tells you **what** broke, **how sure** it is and **where**:

    api_errors ▲ +940% · where: platform=ios · 96% confidence

No language model: every alert is a typed decision from purpose-trained statistical models, so it's cheap to run,
deterministic and explainable. Kepler AI, the built-in assistant, answers questions about your metrics, does maths
and proofs, looks things up in a local knowledge library, and writes formal PDF reports.

## Quick start

```bash
pip install kepler_watchdog-1.0.0-py3-none-any.whl
kepler serve                      # http://127.0.0.1:8000: prints the dashboard sign-in key
kepler                            # the terminal app, every tab (starts a server if none is running)
```

Or with Docker: `docker compose up`, then `docker compose logs kepler` for the sign-in key.

## Plans

Free during early access: every feature is included and nothing is charged. Billing is disabled (`kepler billing`
shows its status).

## Licence

Proprietary: you may use Kepler under the Kepler End-User Licence Agreement. Open-source components are listed in
THIRD_PARTY_NOTICES.md. Full documentation: the project README and `docs/`.
