# ═══════════════════════════════════════════════════════════════
# Sublarr — Multi-Stage Docker Build
# Stage 1: Build React Frontend
# Stage 2: Python Backend + Frontend Bundle
# ═══════════════════════════════════════════════════════════════

# Stage 1: Build React Frontend
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Python Backend + Frontend Bundle
FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend
COPY backend/ .

# Copy built frontend
COPY --from=frontend /build/dist ./static

# Create config directory
RUN mkdir -p /config

EXPOSE 5765

VOLUME ["/config", "/media"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5765/api/v1/health || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5765", "--worker-class", "gthread", "--workers", "2", "--threads", "4", "--timeout", "300", "server:app"]
