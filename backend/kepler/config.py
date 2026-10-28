"""Deployment configuration, read from environment variables (see .env.example at the repo root).

Billing settings (KEPLER_BILLING, RAZORPAY_*) are read by kepler/billing; billing is disabled (docs/billing.md).
"""
import os


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _flag(name: str, default: str) -> bool:
    return _env(name, default).lower() not in ("0", "off", "false", "no", "")


# Access control: every /api route needs the workspace access key. Turn off only for local development.
AUTH_REQUIRED = _flag("KEPLER_AUTH", "on")
API_KEY = _env("KEPLER_API_KEY")          # optional: pin the access key (deployments, CI); else one is generated
SECURE_COOKIES = _flag("KEPLER_SECURE_COOKIES", "off")   # set 'on' when served over HTTPS
CORS_ORIGINS = [o.strip() for o in _env("KEPLER_CORS_ORIGINS").split(",") if o.strip()]  # default: same-origin only
# Where people reach the dashboard (https://kepler.example.com): alerts then link straight to the incident
PUBLIC_URL = _env("KEPLER_PUBLIC_URL").rstrip("/")
# Retrain the models on their own as data comes in (see api.retrain_due). "off": only `kepler train` / the Train button.
AUTO_TRAIN = _flag("KEPLER_AUTO_TRAIN", "on")
