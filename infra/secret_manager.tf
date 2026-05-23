# ──────────────────────────────────────────────────────────────
# secret_manager.tf — Secret Manager secrets (containers only)
# ──────────────────────────────────────────────────────────────
# Per ADR-0003: Terraform manages the EXISTENCE of secrets but
# NEVER their VALUES. Values are added out-of-band via gcloud:
#
#   echo -n "the-actual-secret" | gcloud secrets versions add `
#     <secret-id> --data-file=-
#
# This pattern keeps secret material out of:
#   • the Terraform state file (encrypted but wider blast radius)
#   • the .tf and .tfvars files (one git accident from disaster)
#   • CI logs (anything Terraform prints could leak)
#
# Cloud Run reads the secrets at startup via IAM-controlled
# Secret Manager references — see Phase 3.7 for the wiring.

# ── Secret definitions ────────────────────────────────────────
# Map of secret-id → human-readable description. Each entry
# becomes one Secret Manager secret via for_each. To add a new
# secret, add a new map entry.
#
# Naming convention: lowercase kebab-case for the Secret Manager
# ID (e.g. groq-api-key), translated to UPPER_SNAKE_CASE for the
# env var name inside the Cloud Run container (e.g. GROQ_API_KEY).
locals {
  application_secrets = {
    groq-api-key = "Groq LLM API key for production runtime"
    database-url = "Cloud SQL Postgres connection string (populated after Phase 3.4)"
  }
}

resource "google_secret_manager_secret" "app_secrets" {
  for_each = local.application_secrets

  secret_id = each.key

  labels = {
    managed-by = "terraform"
    project    = "ai-learning-agent"
    purpose    = "runtime-config"
  }

  # auto replication: Google handles multi-region durability.
  # Free, and right for any workload without a specific
  # geographic-residency requirement.
  replication {
    auto {}
  }

  lifecycle {
    # Per the Phase 3.2 quiz: prevent_destroy on state-bearing
    # resources. A secret with a populated version IS state —
    # destroying it loses the secret material irrecoverably.
    prevent_destroy = true
  }
}

# ── Outputs ──────────────────────────────────────────────────
# Print secret IDs after apply so the next-step gcloud commands
# (to add versions) are obvious from the apply output.
output "secret_ids" {
  description = "Secret Manager secret IDs. Add values via `gcloud secrets versions add <id> --data-file=-`."
  value = {
    for k, v in google_secret_manager_secret.app_secrets : k => v.secret_id
  }
}
