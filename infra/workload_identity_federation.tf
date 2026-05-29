# ──────────────────────────────────────────────────────────────
# workload_identity_federation.tf
# ──────────────────────────────────────────────────────────────
# Per ADR-0005: Implements Workload Identity Federation (WIF)
# for GitHub Actions, avoiding static long-lived JSON keys.

# 1. The Workload Identity Pool (The Namespace)
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-actions"
  display_name              = "GitHub Actions Pool"
  description               = "Identity pool for GitHub Actions CI/CD deployments"
}

# 2. The OIDC Provider (The Security Gate)
resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub Actions Provider"
  description                        = "OIDC provider for GitHub Actions"

  # The canonical GitHub Actions token issuer
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }

  # Map GitHub's OIDC token claims to Google Cloud attributes
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  # DEFENSE LAYER 1: The Token Exchange Gate
  # Restricts token exchange exclusively to your repository. 
  attribute_condition = "attribute.repository == \"everhartjoshua/ai-learning-agent\""
}

# ──────────────────────────────────────────────────────────────
# IAM Bindings (DEFENSE LAYER 2: The Per-SA Gate)
# ──────────────────────────────────────────────────────────────

# 3. Allow the GitHub pool to impersonate the CI Build service account
resource "google_service_account_iam_member" "ci_build_wif" {
  # Updated to match the for_each map in service_accounts.tf
  service_account_id = google_service_account.service_accounts["ci-build"].name
  role               = "roles/iam.workloadIdentityUser"

  # Scopes the binding strictly to workflows from your specific repository
  member = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/everhartjoshua/ai-learning-agent"
}

# 4. Allow the GitHub pool to impersonate the CI Deploy service account
resource "google_service_account_iam_member" "ci_deploy_wif" {
  # Updated to match the for_each map in service_accounts.tf
  service_account_id = google_service_account.service_accounts["ci-deploy"].name
  role               = "roles/iam.workloadIdentityUser"

  member = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/everhartjoshua/ai-learning-agent"
}

# ──────────────────────────────────────────────────────────────
# Outputs (Identifiers for GitHub Actions Workflows)
# ──────────────────────────────────────────────────────────────

output "github_actions_wif_provider_name" {
  description = "The Workload Identity Provider resource name. Use as 'workload_identity_provider' in the GitHub Actions auth step."
  value       = google_iam_workload_identity_pool_provider.github.name
}

# We can omit the Service Account emails here since you already 
# have an elegant output block for them in service_accounts.tf!