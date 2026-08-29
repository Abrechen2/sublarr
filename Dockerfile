# ═══════════════════════════════════════════════════════════════
# Sublarr — Multi-Stage Docker Build
# Stage 1: Build React Frontend (native platform for speed)
# Stage 2: Python Backend + Frontend Bundle
# ═══════════════════════════════════════════════════════════════

# Stage 1: Build React Frontend
FROM --platform=$BUILDPLATFORM node:26-alpine AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm install --legacy-peer-deps
COPY frontend/ .
# Pre-compress the bundle (brotli+gzip) after the vite build so the backend can
# serve .br/.gz with Content-Encoding — big first-load win on low-power hosts.
# (Kept as vite build + compress rather than `npm run build` to skip the tsc
# type-check in the image; typecheck runs in CI/pre-deploy instead.)
RUN npx vite build && node scripts/compress-dist.mjs

# Stage 2: Python Backend + Frontend Bundle
FROM python:3.12-slim

# Pass from build: docker build --build-arg VERSION=$(cat backend/VERSION) ...
# Or use scripts/docker-build.sh to get version suggestions and build.
ARG VERSION=
LABEL org.opencontainers.image.title="Sublarr"
LABEL org.opencontainers.image.description="Standalone Subtitle Manager & Translator for Anime/Media"
LABEL org.opencontainers.image.source="https://github.com/Abrechen2/sublarr"
LABEL org.opencontainers.image.licenses="GPL-3.0"
LABEL org.opencontainers.image.version="${VERSION}"
# Also expose it to the running app (backend/version.py) so an RC-tagged
# build (e.g. "1.6.5-rc.2") reports its actual tag instead of the plain
# backend/VERSION content, which never carries the -rc.N suffix.
ENV SUBLARR_VERSION="${VERSION}"
# The repo default is the relative "log/sublarr.log", which is right for a
# source checkout and wrong for a container: it resolves under WORKDIR, so the
# log lives inside the container layer and is gone on the next recreate — and
# both the Logs page and the support export then read a file that resets on
# every update. /config is the persistent volume, same as the database default.
ENV SUBLARR_LOG_FILE="/config/sublarr.log"

# Install system dependencies
# postgresql-client provides pg_dump/pg_restore for optional PostgreSQL backup support
# tesseract-ocr for OCR functionality, hunspell for spell checking
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        mkvtoolnix \
        curl \
        gosu \
        unrar-free \
        postgresql-client \
        tesseract-ocr \
        tesseract-ocr-deu \
        tesseract-ocr-eng \
        hunspell \
        hunspell-de-de \
        hunspell-en-us \
        libenchant-2-2 \
        fonts-liberation && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
# Includes psycopg2-binary (PostgreSQL) and redis/rq (Redis) for optional backends
# ffsubsync pulls webrtcvad which has no prebuilt wheels → gcc + python3-dev
# required during install. Build tools are purged afterwards to keep the
# runtime image slim.
COPY backend/requirements.txt .
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ python3-dev && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get purge -y --auto-remove gcc g++ python3-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy backend
COPY backend/ .

# Copy built frontend
COPY --from=frontend /build/dist ./static

# Provide fallback font for libass-wasm subtitle renderer.
# Liberation Sans (metric-compatible Arial replacement, SIL OFL licence) is
# installed via fonts-liberation above. The worker loads /default.woff2 at
# startup; a 404 here crashes the worker before any subtitle renders.
RUN cp /usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf ./static/default.woff2

# Create non-root user with configurable UID/GID
ARG PUID=1000
ARG PGID=1000
RUN groupadd -g ${PGID} sublarr && \
    useradd -u ${PUID} -g ${PGID} -m -s /bin/bash sublarr

# Create config and backups directory
RUN mkdir -p /config/backups && \
    chown -R sublarr:sublarr /app /config

# Runtime entrypoint: remaps the sublarr user to PUID/PGID, fixes /config
# ownership on the bind-mounted volume, then drops privileges via gosu.
# Runs as root so it can chown /config and remap the user; gunicorn itself
# runs unprivileged as the requested PUID/PGID.
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh && \
    chmod +x /usr/local/bin/docker-entrypoint.sh

# NOTE: container starts as root so the entrypoint can chown /config and
# remap the user. The application process is dropped to PUID:PGID via gosu.
USER root

EXPOSE 5765

VOLUME ["/config", "/media"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:5765/api/v1/health || exit 1

STOPSIGNAL SIGTERM

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
# --timeout is gunicorn's worker LIVENESS ceiling, not a per-request limit. The
# APScheduler ticks run inside this worker, and the longest of them (`cleanup`,
# JobSpec.timeout_s=7200) walks the whole media library — on a ~750-season
# library that is routinely 18-51 min. At the old 300s the arbiter SIGKILLed the
# worker mid-tick (prod, 2026-08-04 03:56, 11 min into the cleanup run): the tick
# died before _tick_wrapper could write its scheduler_job_runs row, so the run
# left no history entry, no timeout row and no traceback -- it simply vanished.
# Keep this >= the largest JobSpec.timeout_s so the app's own timeout fires
# first and gets recorded properly.
CMD ["gunicorn", "--bind", "0.0.0.0:5765", "--worker-class", "gthread", "--workers", "1", "--threads", "4", "--timeout", "7200", "--graceful-timeout", "15", "app:create_app()"]
