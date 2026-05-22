# ──────────────────────────────────────────────────────────────
# main.tf — root module configuration
# ──────────────────────────────────────────────────────────────
# This file configures the Google provider with our project ID
# and region defaults. Resource declarations will be added here
# (or split into separate .tf files) in subsequent Phase 3 sub-steps.

# Configure the Google provider with our defaults. Every resource
# we create that doesn't explicitly override project/region/zone
# will use these values.
provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}
