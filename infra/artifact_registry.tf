# ──────────────────────────────────────────────────────────────
# artifact_registry.tf — container image repositories
# ──────────────────────────────────────────────────────────────
# Per ADR-0004: per-service Artifact Registry repositories with
# SHA-based tagging, 14-day retention window, 30-most-recent
# protection floor, and native vulnerability scanning.
#
# Vulnerability scanning is gated by the Container Scanning API
# at the project level (enabled via gcloud — see Phase 0 runbook).

# ── Repository definitions ────────────────────────────────────
# Map of service name → human-readable description. Each entry
# below becomes one Artifact Registry repository via for_each.
# To add a new service, add a new entry — no need to duplicate
# the resource block.
locals {
  artifact_repositories = {
    backend  = "Backend FastAPI service container images"
    frontend = "Frontend Streamlit service container images"
  }
}

# ── The resource itself ──────────────────────────────────────
# One Docker-format Artifact Registry repository per entry in
# locals.artifact_repositories.
resource "google_artifact_registry_repository" "service_repos" {
  # for_each iterates the map. each.key = "backend" or "frontend";
  # each.value = the corresponding description string.
  for_each = local.artifact_repositories

  repository_id = "learning-agent-${each.key}"
  description   = each.value
  format        = "DOCKER"
  location      = var.region

  # ── Cleanup policies ────────────────────────────────────────
  # Applied in order on Artifact Registry's scheduled cleanup
  # runs. When multiple policies match the same image version,
  # a KEEP policy wins over a DELETE policy — so the keep-recent
  # policy below ALWAYS protects the last 30 images, even when
  # they're older than the 14-day delete cutoff.

  # Policy 1 (KEEP): keep the 30 most recent versions, regardless
  # of age. Protects active rollback targets and current
  # production from age-based deletion.
  cleanup_policies {
    id     = "keep-30-most-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 30
    }
  }

  # Policy 2 (DELETE): everything older than 14 days that wasn't
  # kept by Policy 1. Per ADR-0004 retention window.
  # "1209600s" = 14 days expressed as the Google duration format
  # (seconds with "s" suffix).
  cleanup_policies {
    id     = "delete-after-14-days"
    action = "DELETE"
    condition {
      older_than = "1209600s"
    }
  }

  # ── Safety: prevent accidental destroy ─────────────────────
  # If someone removes this resource from code and runs apply,
  # Terraform would normally destroy the repo (and all its
  # images). prevent_destroy halts the apply with an error so a
  # human has to deliberately remove the lifecycle block first.
  # Cheap insurance against typos and bad merges.
  lifecycle {
    prevent_destroy = true
  }
}

# ── Outputs ──────────────────────────────────────────────────
# Print the repository URLs after apply. The full image URL for
# pushing/pulling is "<region>-docker.pkg.dev/<project>/<repo>".
# We'll consume these URLs in Phase 5 when CI builds and pushes
# images.
output "artifact_registry_urls" {
  description = "URLs of the per-service Artifact Registry repositories"
  value = {
    for k, v in google_artifact_registry_repository.service_repos :
    k => "${var.region}-docker.pkg.dev/${var.project_id}/${v.repository_id}"
  }
}
