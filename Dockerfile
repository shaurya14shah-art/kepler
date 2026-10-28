# Kepler: one image with the API, dashboard and background worker.
#   docker build -t kepler .        docker compose up

# ---- 1. build the dashboard
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. the Python app, with the dashboard bundled inside the package
FROM python:3.12-slim
ARG VERSION=dev
LABEL org.opencontainers.image.title="Kepler" \
      org.opencontainers.image.description="Self-hosted metric watchdog: what broke, how sure, and where." \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.licenses="LicenseRef-Proprietary" \
      org.opencontainers.image.vendor="Shaurya Shah"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    KEPLER_DB=/data/kepler.db KEPLER_HOME=/data/home KEPLER_AUTH=on KEPLER_BILLING=off
WORKDIR /app
COPY backend/ ./
COPY LICENSE THIRD_PARTY_NOTICES.md ./
COPY --from=web /web/dist ./kepler/web
RUN pip install . && useradd --create-home --uid 10001 kepler && mkdir -p /data && chown kepler /data
USER kepler
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["kepler", "serve", "--host", "0.0.0.0", "--port", "8000"]
