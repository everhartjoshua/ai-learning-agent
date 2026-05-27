# TODOs

Deferred items, known gotchas to address later, and nice-to-haves identified during the build. Items are grouped by domain.

**Format per item:** `[ ] **Title** — Surfaced in: <phase>. <Description>. Why deferred: <reason>.`

When an item is addressed, change `[ ]` to `[x]` and append `→ Resolved in <phase/PR>` rather than deleting — the history is useful.

---

## Application code

- [ ] **Split requirements.txt by service.** Surfaced in: Phase 1. Currently one `requirements.txt` is used for both backend and frontend container builds, so the frontend image installs ChromaDB / SQLAlchemy / FastAPI it doesn't need (~50-80 MB unnecessary). Splitting to `backend/requirements.txt` and `frontend/requirements.txt` would shrink images and reduce attack surface. Why deferred: simplicity wins early; revisit when cold-start size matters.

- [ ] **Multi-stage Dockerfile builds.** Surfaced in: Phase 1. Both images currently build in a single stage. A multi-stage build (builder stage with pip + a slim runtime stage that copies only the resolved site-packages) would shrink the final images further and remove pip itself from the runtime. Why deferred: pedagogical clarity of single-stage was higher than the image-size optimization.

- [ ] **Consider distroless or scratch base images.** Surfaced in: Phase 1. python:3.11-slim is ~125 MB; distroless Python is ~50 MB. Distroless has no shell, which is more secure but harder to debug. Why deferred: debuggability matters more during the learning phase.

- [ ] **Add health checks to docker-compose.yml.** Surfaced in: Phase 1. The `depends_on: backend` clause only waits for the container to *start*, not for uvicorn to be *ready*. A `healthcheck:` block on the backend service plus `depends_on: { backend: { condition: service_healthy } }` on the frontend would tighten startup ordering. Why deferred: works well enough; refresh handles the brief startup gap.

- [ ] **Run Postgres locally via docker-compose for dev/prod parity.** Surfaced in: Phase 1. Local dev uses SQLite; production uses Cloud SQL Postgres. The dialect difference (and SQLAlchemy's `connect_args={"check_same_thread": False}` SQLite-specific kwarg) means there are paths that work locally but fail in production. Why deferred: SQLite is friction-free for solo learning; revisit when adding tests.

- [ ] **Fix SQLAlchemy `connect_args` to handle both SQLite and Postgres.** Surfaced in: Phase 3.7 prep. `backend/db/models.py` passes `connect_args={"check_same_thread": False}` unconditionally — this argument is SQLite-specific and will error on Postgres. Conditional on the URL scheme or removing the argument entirely (it's only needed for SQLite under FastAPI's threading model). Must be fixed before Phase 5 image is deployed against Cloud SQL.

- [ ] **Wire service-to-service auth in the frontend HTTP client.** Surfaced in: Phase 3.7. Frontend currently calls backend with no `Authorization` header. In production, frontend must fetch an ID token from the metadata server (`http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=<backend_url>` with header `Metadata-Flavor: Google`) and attach it to outbound requests. Use the `google.auth` Python library: `id_token.fetch_id_token(request, audience)`. Must be done before Phase 5 deploy.

- [ ] **Streamlit Dockerfile should use `$PORT` env var.** Surfaced in: Phase 3.7. Streamlit Dockerfile hardcodes `--server.port=8501`. Cloud Run injects `PORT` env var based on `container_port`. Using `--server.port=$PORT` would be more portable. Currently works because we explicitly set `container_port = 8501` in Terraform, but tighter coupling is fragile.

- [ ] **Add structured logging.** Surfaced in: Phase 3.8. The app uses Python `print()` and default `logging`. Structured JSON logs (via `python-json-logger` or `structlog`) would let Cloud Logging extract fields automatically, enabling much better filtering and dashboarding.

- [ ] **Add a minimal pytest smoke test.** Surfaced in: Phase 4 prep. Currently no automated tests; Phase 4's CI workflow will need *something* to run. A few endpoint-level tests against the FastAPI test client would be a sensible starting point.

---

## Infrastructure

- [ ] **WIF: tighten ci-deploy to main-branch only via composite attribute.** Surfaced in: ADR-0005, Phase 3.6. Currently both `ci-build` and `ci-deploy` bindings allow *any* workflow from the repo to impersonate them. Hardened version: add `attribute.repo_and_branch = assertion.repository + ":" + assertion.ref` to the provider's `attribute_mapping`, then bind `ci-deploy` to `principalSet://...attribute.repo_and_branch/<owner>/<repo>:refs/heads/main`. Build SA stays loose so PR builds can still push images. Why deferred: the current scope is acceptable for a learning project; tightening is the "next-step hardening" mentioned in the ADR.

- [ ] **Deploy a Postgres connection pooler (PgBouncer or Cloud SQL Auth Proxy in pooling mode).** Surfaced in: ADR-0002, Phase 3.4. The named ADR gotcha: Cloud Run's per-request horizontal autoscaling can multiply DB connections faster than Postgres' `max_connections` (typically 100 on a shared-core instance). Without a pooler, bursty load can exhaust connections. Why deferred: not blocking for trial-scale traffic; required before any real-user deployment.

- [ ] **Bring API enablement under Terraform management.** Surfaced in: Phase 3.2. Currently the 13+ enabled GCP APIs (run, sqladmin, secretmanager, etc.) were enabled manually via `gcloud services enable` in Phase 0. Bringing them under `google_project_service` resources in Terraform would make the DR rebuild step shorter. Why deferred: they're enabled and stable; not urgent.

- [ ] **Cross-project Terraform state replication for disaster recovery.** Surfaced in: Phase 3.8 capstone discussion. The state bucket lives in the same project as the resources it tracks; if the project is deleted, state is gone (versioning included). Mature DR pattern: separate "infra-management" GCP project that hosts the state bucket with stricter access controls. Why deferred: significant additional setup for a learning project; documented in DR runbook (Phase 7) as a known gap.

- [ ] **Custom application-level metrics via OpenTelemetry.** Surfaced in: Phase 3.8. Currently only auto-collected Cloud Run/Cloud SQL metrics. Custom metrics like "exercises completed per minute," "LLM API call duration," "lesson generation success rate" would enable richer dashboards and SLO tracking. Why deferred: out of scope for ADR-0006's minimum; revisit if the app sees real users.

- [ ] **Extended log retention for audit trail.** Surfaced in: Phase 3.8. Default Cloud Logging retention is 30 days. For audit compliance, route relevant logs (deployment events, admin operations) to a longer-retention log bucket via a Logging sink. Why deferred: not required at this scale.

- [ ] **Health checks / startup probes on Cloud Run services.** Surfaced in: Phase 3.7. `google_cloud_run_v2_service` supports `template.containers.startup_probe` and `liveness_probe`. Currently using Cloud Run defaults. Explicit probes would catch slow-starting containers (the deep-lesson generator initialization) more precisely. Why deferred: defaults are reasonable; tune if cold-start failures become a problem.

- [ ] **Billing budget — set up via GCP console.** Surfaced in: Phase 3.8. ADR-0006 committed to a billing-spend alert as the fifth required alert; this is set up manually because `google_billing_budget` requires billing-account-scoped IAM. Console path: Billing → Budgets & alerts → Create budget → $200/month, alerts at 50/75/90/100%, notify everhart.joshua@gmail.com. **Set up before any real-cost-bearing traffic.**

- [ ] **HTTPS Load Balancer + Domain Mappings for pretty URLs.** Surfaced in: ADR-0001, Phase 3.7. Currently both Cloud Run services are reachable at auto-generated `*.run.app` URLs (e.g., `https://learning-agent-backend-619438002312.us-central1.run.app`). A custom domain via Cloud Run Domain Mapping (limited) or a Global HTTPS Load Balancer (more capable, more cost) would give cleaner URLs. Why deferred: cosmetic for now.

- [ ] **VPC connector for private service-to-service communication.** Surfaced in: ADR-0001, Phase 3.7. Frontend currently calls backend over the public internet (with auth). For lower latency and reduced public attack surface, a VPC connector + private Cloud Run ingress would keep traffic on Google's internal network. Why deferred: latency is acceptable; security is bounded by the IAM auth requirement.

- [ ] **Vulnerability scanning beyond Artifact Registry's native scanner.** Surfaced in: ADR-0004, Phase 3.2. Native AR scanning is enabled and catches CVEs in image layers; consider integrating supplemental scanning in CI (e.g., `trivy` or `grype` action) for application-dependency CVEs before push. Why deferred: native scanning is sufficient as a starting point.

---

## Cleanup from the build

- [x] **Stray `{backend` directory from a shell brace-expansion mishap.** Surfaced in: Phase 0. Removed manually. → Resolved in Phase 0.

- [x] **`.write_test` artifact in project root.** Surfaced in: Phase 0. Removed manually; gitignored going forward. → Resolved in Phase 0.

- [x] **`.terraform.lock.hcl` was wrongly in `.gitignore`.** Surfaced in: Phase 3.1. The original `.gitignore` I wrote in Phase 0 included `.terraform.lock.hcl`, which was wrong — the lock file should be committed for reproducible provider versions. → Resolved in Phase 3.1.

- [x] **Cloud Run `volume_mounts` drift detection.** Surfaced in: Phase 3.8. After Phase 3.7 apply, `terraform plan` kept proposing removal of the Cloud SQL `volume_mounts` block because Cloud Run auto-creates the mount but the Terraform provider couldn't predict it. Fix: explicitly declare `volume_mounts { name = "cloudsql"; mount_path = "/cloudsql" }` inside the container, matching the auto-created shape. → Resolved by user during Phase 3.8.

---

## Documentation (Phase 7 deliverables)

- [ ] **Runbook: bootstrap state bucket.** How to manually create the GCS state bucket when starting a new GCP project (chicken-and-egg recovery procedure). Reference: `infra/versions.tf` backend config.

- [ ] **Runbook: git workflow.** Save the cheat-sheet I drafted in the Phase 3 "git frustration" exchange to `docs/runbooks/git-workflow.md`. Includes: branching, committing, pushing, PR creation, merge, branch cleanup, and the "I committed to main" recovery procedure.

- [ ] **Runbook: legitimate Cloud SQL destroy.** Two-step process (lower `deletion_protection`, then destroy) because the API enforces the protection in real time, so single-apply destroy will fail mid-stream.

- [ ] **Runbook: secret rotation.** `gcloud secrets versions add ... --data-file=-` to add a new version, then `gcloud run deploy ...` (or a Terraform-annotation hack) to force a Cloud Run redeploy so running instances pick up the rotated value.

- [ ] **Runbook: PR review checklist for `infra/` changes.** What reviewers should look for in a Terraform PR (unexpected destroys, IAM resource-flavor choice, `prevent_destroy` on state-bearing resources, etc.).

- [ ] **Runbook: disaster recovery.** From the Phase 3.8 capstone walkthrough — what's in Terraform vs. what needs manual recreation, with realistic time estimates.

- [ ] **Architecture diagram.** A visual version of the architecture in `CLAUDE.md` — separate file at `docs/architecture.png` or `docs/architecture.svg`. Suitable for showing to an interviewer.

- [ ] **Interview write-up: map every JD bullet to project work.** A document at `docs/interview-prep.md` that lists each bullet from the target JD and points at the specific PR / file / ADR / runbook that demonstrates it. Concrete portfolio artifact.

- [ ] **ADR index `README.md` in `docs/adr/`.** Already exists but should be auto-updated as new ADRs land.
