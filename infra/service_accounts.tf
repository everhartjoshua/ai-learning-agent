# ──────────────────────────────────────────────────────────────
# service_accounts.tf — service accounts + IAM bindings
# ──────────────────────────────────────────────────────────────
# Per ADR-0005: separate SAs per workload concern (CI build, CI
# deploy, backend runtime, frontend runtime), each with the
# minimum IAM roles needed to do its job.
#
# All IAM bindings use the *_iam_member resource type — additive,
# composable, won't accidentally clobber other bindings.

# ── Service account definitions ──────────────────────────────
locals {
  service_accounts = {
    ci-build = {
      display_name = "CI build pipeline"
      description  = "Used by GitHub Actions to build and push container images to Artifact Registry"
    }
    ci-deploy = {
      display_name = "CI deploy pipeline"
      description  = "Used by GitHub Actions to deploy Cloud Run revisions"
    }
    backend-runtime = {
      display_name = "Backend Cloud Run runtime"
      description  = "Identity for the backend FastAPI Cloud Run service"
    }
    frontend-runtime = {
      display_name = "Frontend Cloud Run runtime"
      description  = "Identity for the frontend Streamlit Cloud Run service"
    }
  }
}

resource "google_service_account" "service_accounts" {
  for_each = local.service_accounts

  account_id   = each.key
  display_name = each.value.display_name
  description  = each.value.description
}

# ──────────────────────────────────────────────────────────────
# IAM bindings for ci-build
# ──────────────────────────────────────────────────────────────
# Build SA pushes container images. Scoped to each repo individually
# (resource-level IAM) so it can't write to any future Artifact
# Registry repo it shouldn't.

resource "google_artifact_registry_repository_iam_member" "ci_build_writer" {
  # for_each iterates over the EXISTING repos defined in
  # artifact_registry.tf. This creates one binding per repo
  # (backend + frontend) without having to hardcode names here.
  for_each = google_artifact_registry_repository.service_repos

  project    = each.value.project
  location   = each.value.location
  repository = each.value.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.service_accounts["ci-build"].email}"
}

# ──────────────────────────────────────────────────────────────
# IAM bindings for ci-deploy
# ──────────────────────────────────────────────────────────────
# Deploy SA needs to (1) update Cloud Run services, (2) read
# image references from Artifact Registry to validate them at
# deploy time, and (3) impersonate the runtime SAs so the
# deployed services can run as those identities.

# (1) Cloud Run developer — project-level. Cloud Run doesn't
# support resource-level IAM for the "deploy revisions" verb
# without significant complexity; project-level is the standard
# pattern. Limitation acknowledged.
resource "google_project_iam_member" "ci_deploy_run_developer" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.service_accounts["ci-deploy"].email}"
}

# (2) Artifact Registry reader on each repo — scoped per repo.
resource "google_artifact_registry_repository_iam_member" "ci_deploy_reader" {
  for_each = google_artifact_registry_repository.service_repos

  project    = each.value.project
  location   = each.value.location
  repository = each.value.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.service_accounts["ci-deploy"].email}"
}

# (3) "Act as" the runtime SAs. Grants iam.serviceAccountUser
# on each runtime SA to the deploy SA. Without this, `gcloud
# run deploy --service-account=backend-runtime@...` fails with
# a permission error even though the deploy SA has run.developer.
resource "google_service_account_iam_member" "ci_deploy_acts_as_runtime" {
  for_each = toset(["backend-runtime", "frontend-runtime"])

  service_account_id = google_service_account.service_accounts[each.key].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.service_accounts["ci-deploy"].email}"
}

# ──────────────────────────────────────────────────────────────
# IAM bindings for backend-runtime
# ──────────────────────────────────────────────────────────────
# Backend runtime reads its two secrets and connects to Cloud SQL.
# Everything else is denied by default.

# Secret access — scoped per-secret. Tight: if a new secret is
# added for some other purpose, this SA can't read it without
# adding a new binding.
resource "google_secret_manager_secret_iam_member" "backend_secret_access" {
  for_each = google_secret_manager_secret.app_secrets

  project   = each.value.project
  secret_id = each.value.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.service_accounts["backend-runtime"].email}"
}

# Cloud SQL client — project-level (no per-instance IAM
# available for Cloud SQL — a documented GCP limitation). With
# only one instance in this project, the practical impact is
# nil; if we ever provision a second Cloud SQL instance for an
# unrelated purpose, we'd want to revisit.
resource "google_project_iam_member" "backend_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.service_accounts["backend-runtime"].email}"
}

# ──────────────────────────────────────────────────────────────
# IAM bindings for frontend-runtime
# ──────────────────────────────────────────────────────────────
# DELIBERATELY EMPTY. The frontend runtime will eventually get
# roles/run.invoker on the backend Cloud Run service (Phase 3.7),
# but that resource doesn't exist yet. Until then, this SA has
# ZERO project permissions — the correct least-privilege starting
# point. The temptation to over-grant ("just in case") is real;
# the cost is invisible until something is compromised.

# ──────────────────────────────────────────────────────────────
# Outputs
# ──────────────────────────────────────────────────────────────
output "service_account_emails" {
  description = "Service account email addresses. Used by Cloud Run service config (Phase 3.7) and Workload Identity Federation bindings (Phase 3.6)."
  value = {
    for k, v in google_service_account.service_accounts : k => v.email
  }
}
