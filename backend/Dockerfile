# ──────────────────────────────────────────────────────────────
# Backend Dockerfile — FastAPI service (uvicorn)
# ──────────────────────────────────────────────────────────────
# Built from the project root:
#   docker build -f backend/Dockerfile -t learning-agent-backend .
# Run with:
#   docker run --rm -p 8000:8000 --env-file .env learning-agent-backend

# ── Base image ────────────────────────────────────────────────
# python:3.11-slim — Debian-based, glibc, ~125 MB. The right
# balance between size and compatibility for apps with C
# extensions like ChromaDB.
FROM python:3.11-slim

# ── Build-time environment ────────────────────────────────────
# PYTHONDONTWRITEBYTECODE — skip writing .pyc files. They take
#   space and aren't useful inside an immutable container.
# PYTHONUNBUFFERED — disable Python's stdout/stderr buffering.
#   Critical for cloud deployment so logs stream to Cloud
#   Logging in real time instead of being held in a buffer.
# PIP_NO_CACHE_DIR — don't store the pip download cache after
#   install. Saves ~50 MB on the final image.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# ── Working directory ─────────────────────────────────────────
# /app is the conventional location for application code in a
# container. WORKDIR creates the directory if it doesn't exist
# and `cd`s into it for subsequent instructions.
WORKDIR /app

# ── Dependencies (cached layer) ───────────────────────────────
# Copy ONLY requirements.txt first, then install. This is the
# layer-caching trick: when you change a .py file later, this
# install step is reused from cache (saves 30–90 seconds per
# rebuild). The pip install layer only rebuilds when requirements
# themselves change.
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# ── Application code ──────────────────────────────────────────
# Copy everything not excluded by .dockerignore. Because this is
# AFTER the dependency install, the dep layer stays cached when
# only your code changes.
COPY . .

# ── Security: non-root user ───────────────────────────────────
# Running as root inside a container is a security smell — if an
# attacker compromises the app, they'd have root inside the
# container, increasing blast radius. Create a dedicated
# unprivileged user. (Cloud Run also enforces non-root at the
# platform level, but baking it in is the right habit.)
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# ── Network ───────────────────────────────────────────────────
# EXPOSE is DOCUMENTATION ONLY — it tells humans and some tools
# which port the container listens on. It does NOT publish the
# port to the host; the -p flag on `docker run` does that.
EXPOSE 8000

# ── Startup command ───────────────────────────────────────────
# --host 0.0.0.0  → bind to all interfaces. By default uvicorn
#                   binds to 127.0.0.1, which inside a container
#                   means "only inside this container" — not what
#                   you want when traffic comes from outside.
# --port 8000     → the listening port (matches EXPOSE above).
# No --reload     → containers are immutable; code changes
#                   trigger image rebuilds, not in-place reloads.
CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
