# ──────────────────────────────────────────────────────────────
# Frontend Dockerfile — Streamlit UI
# ──────────────────────────────────────────────────────────────
# Built from the project root:
#   docker build -f frontend/Dockerfile -t learning-agent-frontend:dev .
# In the next phase we'll launch this alongside the backend with
# docker-compose so the two containers can find each other.

# ── Base image ────────────────────────────────────────────────
# Same base as the backend on purpose — identical OS across
# services keeps the mental model simple AND lets Docker's layer
# cache share work across both builds.
FROM python:3.11-slim

# ── Build-time environment ────────────────────────────────────
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# ── Working directory ─────────────────────────────────────────
WORKDIR /app

# ── Dependencies (cached layer) ───────────────────────────────
# Same requirements.txt as the backend. The frontend doesn't
# actually need chromadb, sqlalchemy, or fastapi — a future
# optimization pass would split into backend-requirements.txt
# and frontend-requirements.txt to keep each image lean.
# For Phase 1, simplicity wins.
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# ── Application code ──────────────────────────────────────────
COPY . .

# ── Security: non-root user ───────────────────────────────────
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# ── Network ───────────────────────────────────────────────────
EXPOSE 8501

# ── Startup command ───────────────────────────────────────────
# Streamlit-specific flags (each fixes a real container gotcha):
#
#   --server.address=0.0.0.0
#     Bind to all interfaces. Default is 127.0.0.1 which means
#     "only inside this container" — same gotcha as uvicorn.
#
#   --server.port=8501
#     Streamlit's conventional port; matches EXPOSE above.
#
#   --server.headless=true
#     Don't try to open a browser on startup. Streamlit's default
#     is to launch one; there's no display device in a container,
#     so without this flag startup logs noise about being unable
#     to open a browser. Cloud Run would also reject the attempt.
#
#   --browser.gatherUsageStats=false
#     Disable Streamlit's anonymous-usage telemetry phone-home.
#     Best practice for any production deployment.
CMD ["streamlit", "run", "frontend/app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
