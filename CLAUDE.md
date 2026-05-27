# CLAUDE.md — Session Context

Pre-load this file at the start of every session to skip the cold-start cost of re-deriving project context. Maintain it at the end of every session.

---

## Project

**AI Learning Agent → GCP Migration.** A personalized-learning Streamlit + FastAPI application originally built as a Python project; being migrated onto GCP using Infrastructure-as-Code, GitHub Actions CI/CD, and Cloud Monitoring — explicitly as a learning project that will become an interview portfolio piece for the **IT Infrastructure Engineer II** role.

The application logic itself (lesson generation, exercise evaluation, Socratic chatbot) is stable and not the primary focus. The *infrastructure* and *deployment pipeline* are the focus.

---

## User Context

- **Name:** Joshua Everhart
- **Email:** everhart.joshua@gmail.com
- **Background:** 15+ years of enterprise infrastructure experience. **CI/CD, GitHub Actions, and Terraform are new** — treat as a first-time learner for those specifically.
- **Target role:** IT Infrastructure Engineer II (JD shared in conversation; covers GitHub administration, GitHub Actions CI/CD, IaC, AI-augmented engineering, Vercel/GCP deployment).
- **Local environment:** Windows 11 + PowerShell + WSL2 (Ubuntu) + Docker Desktop + git + gcloud + Terraform.
- **GCP project:** `ai-learning-agent-496621` in `us-central1` (zone `us-central1-a`), project number `619438002312`. Free trial credits ($300).
- **GitHub:** `everhartjoshua/ai-learning-agent` (public repo, branch protection on `main`, squash-merge workflow).

---

## Working Style Preferences

- **Pacing pattern:** concept → hands-on → quiz. User explicitly chose this in Phase 0 and again at Phase 3 start.
- **Explanations:** ground every concept in interview-relevant framing. User saves phrases for interview conversations.
- **Prose over bullets.** User prefers explanations in prose; lists OK for genuine enumerations (commands, options).
- **Workflow discipline:** every change goes through a feature branch + PR + squash-merge + delete branch. Even solo. The discipline is the point.
- **Tone:** treat as a peer; honest critique with empathetic framing; no condescension, no over-praise.
- **Review style:** when user posts work for review, do it like a senior engineer reviewing a teammate's PR — specific, line-numbered, with both affirmations and refinements.

---

## Current State (end of Phase 3)

### Architecture deployed in GCP

```
                                ┌─────────────────────┐
                                │   GitHub Actions    │  (Phase 4 — pending)
                                │   (CI/CD pipelines) │
                                └──────────┬──────────┘
                                           │ WIF (no static keys)
                                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                          GCP Project                              │
│                                                                   │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────────────────┐ │
│  │  Frontend   │──▶│   Backend   │──▶│  Cloud SQL Postgres     │ │
│  │ (Streamlit, │   │  (FastAPI,  │   │  (db-f1-micro, ZONAL)   │ │
│  │  public)    │   │  IAM-only)  │   └─────────────────────────┘ │
│  │  Cloud Run  │   │  Cloud Run  │   ┌─────────────────────────┐ │
│  └─────────────┘   └──────┬──────┘──▶│   Secret Manager        │ │
│         ▲                 │           │  (GROQ_API_KEY, DB_URL) │ │
│         │                 │           └─────────────────────────┘ │
│         │                 ▼           ┌─────────────────────────┐ │
│         │           ┌─────────┐       │   Artifact Registry     │ │
│         └───────────│  Groq   │       │   (backend + frontend)  │ │
│                     │   LLM   │       └─────────────────────────┘ │
│                     └─────────┘                                   │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  Cloud Monitoring: dashboard + 5 alert policies          │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

### Phase status

| Phase | Status      | Output                                                                  |
| ----- | ----------- | ----------------------------------------------------------------------- |
| 0     | ✅ complete | GitHub repo + branch protection, gcloud/Terraform/Docker installed     |
| 1     | ✅ complete | Backend + frontend Dockerfiles + docker-compose for local dev          |
| 2     | ✅ complete | Six ADRs in `docs/adr/`                                                |
| 3     | ✅ complete | Nine .tf files in `infra/` — full GCP environment provisioned via IaC  |
| 4     | ⚪ next     | GitHub Actions CI workflows (lint, test, terraform plan on PR)         |
| 5     | ⚪ pending  | CD pipeline — build, push, deploy to Cloud Run                         |
| 6     | ⚪ pending  | Monitoring dashboard + alerting + audit trail (Terraform part done)    |
| 7     | ⚪ pending  | Runbooks, ADR catalog, architecture diagram, interview write-up        |

### Six accepted ADRs in `docs/adr/`

1. **ADR-0001** — Use Cloud Run as the deployment target
2. **ADR-0002** — Use Cloud SQL for PostgreSQL
3. **ADR-0003** — Secrets Management (Secret Manager, never values in Terraform)
4. **ADR-0004** — Container Image Registry Layout (Artifact Registry, per-service repos, SHA tags)
5. **ADR-0005** — Workload Identity Federation for CI/CD authentication
6. **ADR-0006** — Monitoring, Logging, and Alerting Stack (native GCP suite)

### Terraform resources in `infra/`

- `versions.tf` — Terraform version + Google + random providers + GCS backend
- `main.tf` — provider configuration
- `variables.tf` — `project_id`, `region`, `zone` with zone-in-region validation
- `artifact_registry.tf` — 2 Docker repos with cleanup policies
- `secret_manager.tf` — 2 secret containers (values out-of-band)
- `cloud_sql.tf` — Postgres instance, db, user, generated password → secret version
- `service_accounts.tf` — 4 SAs (ci-build, ci-deploy, backend-runtime, frontend-runtime) + per-resource IAM
- `workload_identity_federation.tf` — pool + OIDC provider + attribute-conditional bindings
- `cloud_run.tf` — backend + frontend services (placeholder images, lifecycle.ignore_changes on image)
- `monitoring.tf` — 1 notification channel + 5 alert policies + 1 dashboard

State lives in GCS bucket `ai-learning-agent-496621-tfstate` (versioning enabled, public access prevented). The bucket itself is **not** managed by Terraform — chicken-and-egg.

### Application code in `backend/` and `frontend/`

Containerized; runs locally via `docker compose up`. Per Phase 1, both services use python:3.11-slim base, run as non-root `appuser`, expose ports 8000 and 8501. SQLite locally; Cloud SQL Postgres in production (DATABASE_URL is env-driven via `os.getenv`).

---

## Key Conventions Established

### Repo / git hygiene

- `main` is protected — every change goes through a PR
- Squash-merge for PR closure (clean history at cost of feature-branch ancestry)
- `.terraform.lock.hcl` **is committed** (was wrongly in `.gitignore` initially; corrected)
- `.env` is **never** committed; `.env.example` is the template
- `data/`, `__pycache__/`, `.venv/`, `.terraform/` are gitignored
- Feature branch naming: `feat/short-description`, `fix/short-description`, `docs/short-description`

### Terraform discipline

- One concern per file (artifact_registry.tf, secret_manager.tf, etc.)
- `prevent_destroy = true` on state-bearing or critical-path resources
- `for_each` over a map for sets of similar resources (never `count` for distinct things)
- IAM via `_iam_member` (additive); never `_iam_binding` unless deliberately taking exclusive role ownership
- Resource-level IAM scopes wherever the provider supports it
- Terraform manages secret *containers*, never *values* (one exception: Terraform-generated passwords)

### ADR format

- Title, Status, Date, Context, Options Considered, Decision, Consequences (Positive/Negative/Trade-offs), References
- Active voice + present tense in Decision section
- Production gotcha named in Negative section using the four-part structure: *what fails / why / how we prevent it / broader lesson*
- Immutable once Accepted — supersede with a new ADR, never edit

### PR descriptions

Substantive, three sections roughly: *what changed*, *why the choices*, *what's known to be out-of-scope / deferred*. The PR description itself becomes the audit-trail artifact an interviewer can read later.

---

## Active Reminders / Pitfalls

- **Always `git status` and `git branch` before `git commit`.** Catches "I'm on main" and "the lock file is floating" simultaneously.
- **Re-read the top of any document before declaring it done.** Titles, filenames, dates, status fields are the most-forgotten because attention is on the body.
- **PowerShell `curl` is an alias for `Invoke-WebRequest`** — use `curl.exe` for Unix-style invocation.
- **PowerShell line continuation is backtick** (`` ` ``); cmd.exe uses `^`. Single-line commands work in both.
- **When `terraform init` modifies the lock file, commit it in the same PR** as the change that caused it.
- **GCS bucket names are globally unique** across all of Google Cloud, not project-scoped.
- **Cloud Run + Cloud SQL volume_mounts** drift detection: declare `volume_mounts { name = "cloudsql"; mount_path = "/cloudsql" }` explicitly in the container to match Cloud Run's auto-created mount, otherwise plan keeps proposing removal.
- **Don't pre-flip ADR status to `Accepted`** — wait for review approval. Same with merging PRs that have unresolved feedback.

---

## Files to maintain alongside this one

- `todos.md` — deferred items, nice-to-haves, follow-up work surfaced during sessions
- `lessons_learned.md` — issues we hit + resolutions, interview-ready phrasings
- `docs/adr/` — Architecture Decision Records
- `docs/runbooks/` — operational runbooks (Phase 7+)

---

## How to use this file at the start of a session

1. Read this file in full to refresh project context
2. Skim `todos.md` for known deferred items (in case the user wants to address one)
3. Skim recent `lessons_learned.md` entries to recall conventions
4. Check current phase status in the table above

## How to maintain this file at the end of a session

1. Update the Phase status table
2. Update the Architecture section if anything material changed
3. Add to Active Reminders if a new pitfall emerged
4. Update Key Conventions if a new pattern was established
