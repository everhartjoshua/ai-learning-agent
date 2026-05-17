# AI Learning Agent

A personalized learning application that builds a curriculum from a job description, assesses a student's knowledge, generates ground-up lessons tied to practice exercises, and adaptively re-teaches concepts when the student struggles. Includes an in-lesson chatbot that answers questions about the material (and gives Socratic hints during practice without revealing answers).

> This repo is also being used as a personal learning project for migrating a real application onto GCP using Infrastructure-as-Code, GitHub Actions CI/CD, and Cloud Monitoring — preparing for an IT Infrastructure Engineer II role.

---

## Architecture (local development)

```
┌──────────────────┐     HTTP     ┌─────────────────────┐
│  Streamlit UI    │ ───────────▶ │  FastAPI backend    │
│  (frontend/)     │              │  (backend/api/)     │
└──────────────────┘              └──────────┬──────────┘
                                             │
                              ┌──────────────┼──────────────┐
                              ▼              ▼              ▼
                       ┌────────────┐ ┌────────────┐ ┌────────────┐
                       │  SQLite    │ │  ChromaDB  │ │  LLM API   │
                       │  (data/)   │ │  (data/)   │ │  (Groq/    │
                       │            │ │            │ │   Ollama)  │
                       └────────────┘ └────────────┘ └────────────┘
```

Cloud architecture lives in `docs/adr/` (added in Phase 2).

---

## Repository structure

```
ai-learning-agent/
├── backend/          # FastAPI service + agent modules
│   ├── agents/       # curriculum, assessment, tutor agents (LLM calls)
│   ├── api/          # FastAPI routes
│   └── db/           # SQLAlchemy models + ChromaDB store
├── frontend/         # Streamlit UI
├── scripts/          # Smoke tests, utilities
├── docs/             # ADRs, runbooks, architecture diagrams  (Phase 2+)
├── infra/            # Terraform infrastructure-as-code        (Phase 3+)
├── .github/
│   └── workflows/    # GitHub Actions CI/CD                    (Phase 4+)
├── .env.example      # Environment variable template
├── .gitignore
└── README.md
```

---

## Local development

### Prerequisites

- Python 3.10+
- An API key from [Groq](https://console.groq.com/) (free tier — recommended) or [OpenAI](https://platform.openai.com/), **or** a local [Ollama](https://ollama.com/) install.

### Setup

```bash
# Clone and enter
git clone <your-repo-url> ai-learning-agent
cd ai-learning-agent

# Create a virtual environment
python -m venv .venv
.venv\Scripts\activate            # Windows PowerShell
# source .venv/bin/activate       # macOS / Linux

# Install dependencies
pip install fastapi uvicorn streamlit httpx sqlalchemy python-dotenv \
            openai chromadb sentence-transformers

# Configure environment
copy .env.example .env            # Windows
# cp .env.example .env            # macOS / Linux
# then edit .env and fill in your LLM API key
```

### Run

In two terminals:

```bash
# Terminal 1 — backend
uvicorn backend.api.main:app --reload

# Terminal 2 — frontend
streamlit run frontend/app.py
```

Open <http://localhost:8501>.

---

## Roadmap (cloud migration)

This project is being incrementally moved to GCP. Each phase has its own branch and PR for review.

| Phase | Status | Description |
| ----- | ------ | ----------- |
| 0     | 🟡 in progress | GitHub repo setup, gcloud/Terraform/Docker install, GCP project verification |
| 1     | ⚪ pending     | Dockerize backend + frontend |
| 2     | ⚪ pending     | Architecture decision records (ADRs) for GCP service choices |
| 3     | ⚪ pending     | Terraform: Artifact Registry, Cloud SQL, Secret Manager, Cloud Run, IAM |
| 4     | ⚪ pending     | GitHub Actions CI (lint + test on PR) |
| 5     | ⚪ pending     | GitHub Actions CD (build, push, deploy with previews) |
| 6     | ⚪ pending     | Cloud Monitoring dashboard, alert policies, audit trail |
| 7     | ⚪ pending     | Runbook, architecture diagram, interview-ready write-up |

---

## License

Personal / educational project.
