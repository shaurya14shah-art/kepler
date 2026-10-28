# Kepler: common tasks.  `make help` lists them.
PY      := backend/.venv/bin/python
VERSION := $(shell sed -n 's/^__version__ = "\(.*\)"/\1/p' backend/kepler/__init__.py)

.PHONY: help setup dev chat teach test lint stress web build notices site smoke release docker clean

help:
	@echo "make setup   install Python + dashboard dependencies"
	@echo "make dev     run Kepler locally on http://localhost:8000 (demo data)"
	@echo "make chat    full-screen chat with the Kepler bot (offline)"
	@echo "make teach   plain chat box to test and train the bot (offline)"
	@echo "make test    run the test suite"
	@echo "make lint    check for syntax errors and undefined names"
	@echo "make stress  run the stress test (~2 min)"
	@echo "make build   build the dashboard, wheel and source package (dist/)"
	@echo "make notices regenerate THIRD_PARTY_NOTICES.md from the installed packages"
	@echo "make site    build the product website's legal pages (site/)"
	@echo "make smoke   install the built wheel in a fresh virtualenv and check it works"
	@echo "make release everything above, in order: lint, test, build, smoke (see docs/RELEASE.md)"
	@echo "make docker  build the Docker image kepler:$(VERSION)"
	@echo "make clean   remove build outputs"

setup:
	cd backend && uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[dev]"
	cd frontend && npm ci

dev:
	./run.sh

chat:
	backend/.venv/bin/kepler bot

teach:
	backend/.venv/bin/kepler teach

test:
	cd backend && .venv/bin/python -m pytest -q tests

lint:
	cd backend && .venv/bin/ruff check kepler tests stress --select E9,F821,F401,F841

stress:
	cd backend && .venv/bin/python stress/stress.py

web:
	cd frontend && npm run build

build: web notices
	rm -rf backend/kepler/web && cp -R frontend/dist backend/kepler/web
	cp LICENSE backend/LICENSE
	rm -f dist/kepler_watchdog-$(VERSION)*
	cd backend && uv build --out-dir ../dist
	@ls -lh dist/kepler_watchdog-$(VERSION)*

notices:
	$(PY) scripts/third_party_notices.py

site:
	python3 scripts/build_site.py

smoke:
	scripts/smoke_test.sh dist/kepler_watchdog-$(VERSION)-py3-none-any.whl

release: lint test build smoke site
	@echo "Kepler $(VERSION) is built and checked: dist/ (wheel + source), site/. Next steps: docs/RELEASE.md"

docker:
	docker build --build-arg VERSION=$(VERSION) -t kepler:$(VERSION) -t kepler:latest .

clean:
	rm -rf dist backend/build backend/*.egg-info backend/kepler/web frontend/dist
