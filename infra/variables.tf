# ──────────────────────────────────────────────────────────────
# variables.tf — input variables for this Terraform config
# ──────────────────────────────────────────────────────────────
# Variables declare WHAT inputs this config accepts. Values are
# provided separately, via:
#   1. defaults declared here (lowest priority)
#   2. a terraform.tfvars file in this directory
#   3. -var or -var-file command-line flags (highest priority)
#   4. TF_VAR_<name> environment variables
#
# Sensitive values (passwords, API keys) should NEVER be defaulted
# here. They should come from environment variables or Secret
# Manager references at runtime. The variables in this file are
# all non-sensitive configuration values.

variable "project_id" {
  description = "The GCP project ID where all resources will be created."
  type        = string
  default     = "ai-learning-agent-496621"
}

variable "region" {
  description = "The GCP region for regional resources (Cloud Run, Cloud SQL, Artifact Registry)."
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "The GCP zone for zonal resources. Must be inside var.region."
  type        = string
  default     = "us-central1-a"

  # Validation: enforce that the zone is in the configured region.
  # This catches the kind of mismatch we accidentally hit in Phase 0
  # (region=us-central1 with zone=us-south1-a) before it becomes a
  # resource-creation failure.
  validation {
    condition     = startswith(var.zone, var.region)
    error_message = "var.zone must be a zone within var.region (e.g., us-central1-a for us-central1)."
  }
}
