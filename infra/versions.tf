# ──────────────────────────────────────────────────────────────
# versions.tf — Terraform & provider version pins, backend config
# ──────────────────────────────────────────────────────────────
# This is the foundational file: it tells Terraform which version
# of itself to use, which providers to download, and where to
# store its state. It rarely changes after initial setup.

terraform {
  # Pin the Terraform binary version. Patch-version drift within
  # 1.x is safe; major version changes (a future 2.x) could break
  # this config and should be a deliberate upgrade.
  required_version = ">= 1.5.0, < 2.0.0"

  # Declare which providers this config uses and what versions
  # are acceptable. The "~>" operator means "compatible release"
  # — ~> 5.0 allows 5.x but not 6.x. This protects against
  # breaking changes from accidental upgrades while still letting
  # us pick up patches.
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    # random — used to generate strong random values that live
    # only inside Terraform's lifecycle (e.g., database passwords).
    # See Phase 3.4 / cloud_sql.tf for the rationale.
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Backend configuration — where Terraform stores its state.
  # ──────────────────────────────────────────────────────────
  # IMPORTANT: backend config CANNOT use variables or expressions
  # because it's evaluated before the rest of the config. The
  # bucket name must be a literal string here. If you ever need
  # to change buckets, you do it manually or via -backend-config
  # flags at init time, not by editing a variable.
  #
  # The "prefix" lets you store multiple state files in one
  # bucket. We use "infra" for this main config; if we ever add
  # a second config (e.g., for a different environment), it
  # would use a different prefix.
  backend "gcs" {
    bucket = "ai-learning-agent-496621-tfstate"
    prefix = "infra"
  }
}
