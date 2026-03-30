# ── Stage 1: Builder ────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools (not carried into runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="harish.gedi@stu.tus.ie"
LABEL org.opencontainers.image.description="NeuroEdge v2 — Edge AI Reliability Monitor"
LABEL org.opencontainers.image.source="https://github.com/harigd77/neuroedge_v2"

WORKDIR /app

# Non-root user — matches K8s runAsUser: 1000
RUN useradd -u 1000 -m -s /bin/sh neuroedge && \
    mkdir -p /data && chown neuroedge:neuroedge /data

# Copy installed packages from builder stage
COPY --from=builder /root/.local /home/neuroedge/.local

# Copy application source
COPY --chown=neuroedge:neuroedge . .

USER neuroedge

ENV PATH=/home/neuroedge/.local/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATABASE_URL=sqlite+aiosqlite:////data/neuroedge.db

EXPOSE 8000

# Lightweight healthcheck using Python stdlib only (no curl needed)
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz', timeout=4)"

CMD ["uvicorn", "backend.api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "info"]
