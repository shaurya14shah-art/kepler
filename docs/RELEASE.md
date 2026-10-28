# Releasing Kepler

## Build and check a release

```bash
make release
```

`make release` runs every step in order, and stops at the first failure:

| Step | What it does |
|------|--------------|
| `make lint` | Static checks: syntax errors, undefined names, unused imports and variables |
| `make test` | The full test suite, including billing staying disabled and the access gate |
| `make build` | Builds the dashboard, writes `THIRD_PARTY_NOTICES.md`, and bundles both into the wheel and source archive in `dist/` |
| `make smoke` | Installs the wheel into a fresh virtualenv, starts it with the access gate on, and checks sign-in, the CLI, the dashboard, Kepler AI, and that billing refuses to charge |
| `make site` | Builds the website's legal pages from `legal/*.md` and lists any placeholders still to fill |

Also worth running before a release:

```bash
make stress                       # ~2 min: concurrent clients, hostile input, every CLI command, the terminal app
uvx twine check dist/*            # package metadata renders correctly
make docker                       # kepler:<version> and kepler:latest images
```

## Version bump

1. Change `__version__` in `backend/kepler/__init__.py`. That's the only place the version is set: the package,
   `kepler --version`, the Makefile and the Docker image tag all read it.
2. Add a section to `CHANGELOG.md`.
3. Update the version in the install lines: `README.md`, `backend/README.md`, `site/index.html`, `docs/deploy.md`.
4. Run `make release`, then commit and tag `vX.Y.Z`.

## Distributing it

Kepler is proprietary. The package carries the `Private :: Do Not Upload` classifier, so PyPI refuses it even if
someone runs `twine upload` by mistake. Pick one or more of these instead:

- **Direct download**: give customers the wheel, or the Docker image as `docker save` output, from a private link.
  If you charge for self-hosted copies, take the payment first with a Razorpay Payment Page or Payment Link, then
  send the link. **Never** put your Razorpay keys into a build you ship: see [billing.md](billing.md).
- **Private container registry**: push `kepler:<version>` to a private registry (GitHub Container Registry,
  Docker Hub private repos, ECR, …) and give each customer pull access.
- **Private package index**: a private index (for example a cloud provider's artifact registry) serves the wheel to
  `pip install --index-url …`.

Each copy includes `LICENSE`, the EULA reference and `THIRD_PARTY_NOTICES.md`.

## The website

`site/` is plain HTML and CSS with no build step beyond `make site` (for the legal pages). It runs on any static
host: GitHub Pages, Netlify, Cloudflare Pages, S3, or your own nginx.

Before you publish it:

- [ ] Fill every placeholder in `legal/*.md`: company name, address, email, jurisdiction, dates, refund window,
      support hours. `legal/README.md` lists them. `make site` reports any that remain.
- [ ] Replace `{{COMPANY}}` in the footer of `site/index.html`.
- [ ] Have a lawyer review the EULA, terms, privacy policy and refund policy. They're drafts, written to match what
      Kepler actually does, but they aren't legal advice.
- [ ] Decide where people get Kepler, and point the site's install section at it.
- [ ] Preview it locally: `python3 -m http.server 8790 --directory site`.

## Before charging money

Billing stays disabled until you change code and configuration yourself. That's deliberate.
[billing.md](billing.md) walks through the order of steps:

1. Legal pages published.
2. Razorpay account activated. Razorpay collects your bank details in its own dashboard, never in Kepler.
3. Test keys, and the whole flow tested in test mode.
4. Prices set.
5. The code switch flipped.
6. Live keys, with `KEPLER_BILLING_LIVE=yes`.

Until then, `kepler billing` says *disabled*, every checkout returns 403, and nothing can be charged.
