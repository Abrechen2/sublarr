# ═══════════════════════════════════════════════════════════════
# Sublarr — Multi-Stage Docker Build
# Stage 1: Build React Frontend (native platform for speed)
# Stage 2: Python Backend + Frontend Bundle
# ═══════════════════════════════════════════════════════════════

# Stage 1: Build React Frontend
FROM --platform=$BUILDPLATFORM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Python Backend + Frontend Bundle
FROM python:3.11-slim

LABEL org.opencontainers.image.title="Sublarr"
LABEL org.opencontainers.image.description="Standalone Subtitle Manager & Translator for Anime/Media"
LABEL org.opencontainers.image.source="https://github.com/denniswittke/sublarr"
LABEL org.opencontainers.image.licenses="GPL-3.0"

# Install system dependencies
# postgresql-client provides pg_dump/pg_restore for optional PostgreSQL backup support
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl unrar-free postgresql-client && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
# Includes psycopg2-binary (PostgreSQL) and redis/rq (Redis) for optional backends
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend
COPY backend/ .

# Copy built frontend
COPY --from=frontend /build/dist ./static

# Create non-root user with configurable UID/GID
ARG PUID=1000
ARG PGID=1000
RUN groupadd -g ${PGID} sublarr && \
    useradd -u ${PUID} -g ${PGID} -m -s /bin/bash sublarr

# Create config and backups directory
RUN mkdir -p /config/backups && \
    chown -R sublarr:sublarr /app /config

USER sublarr

EXPOSE 5765

VOLUME ["/config", "/media"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5765/api/v1/health || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5765", "--worker-class", "gthread", "--workers", "1", "--threads", "4", "--timeout", "300", "app:create_app()"]
