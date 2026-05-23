# ──────────────────────────────────────────────────────────────
# cloud_sql.tf — Cloud SQL Postgres instance, database, user
# ──────────────────────────────────────────────────────────────
# Per ADR-0002: smallest shared-core Postgres instance in
# us-central1, single zone (no HA), 10 GB SSD with auto-resize,
# daily backups, no public access (Cloud Run connects via the
# Cloud SQL Auth Proxy socket, not via IP).

# ── Database user password ────────────────────────────────────
# Terraform-generated random password. Lives in Terraform state
# but is never seen by humans. This is the accepted exception
# to "no secrets in state" — see ADR-0002 / cloud_sql.tf comments.
#
# 32 chars of alphanumeric is roughly 190 bits of entropy. We
# avoid special chars to sidestep URL-encoding edge cases in the
# Postgres connection string (the password becomes part of a URL).
resource "random_password" "db_app_user" {
  length  = 32
  special = false

  # keepers: when these values change, regenerate the password.
  # Right now there's nothing to key off — we only want the
  # password to regenerate if we explicitly taint it. Leaving
  # keepers empty makes the password permanent until manually
  # rotated via `terraform taint`.
  keepers = {}
}

# ── Postgres instance ────────────────────────────────────────
# Long-running: ~5-10 minutes to create. Terraform will sit on
# "Still creating..." lines — that's normal.
resource "google_sql_database_instance" "main" {
  name             = "learning-agent-postgres"
  database_version = "POSTGRES_15"
  region           = var.region

  settings {
    # Smallest shared-core tier — costs roughly $7/month. Per
    # ADR-0002, sufficient for our scale (one learner, a few
    # hundred rows per table, dozens of req/s peak).
    tier              = "db-f1-micro"
    availability_type = "ZONAL"     # single-zone; not HA
    disk_type         = "PD_SSD"
    disk_size         = 10          # GB
    disk_autoresize   = true        # grow automatically; never manually resize

    # Daily automated backups, retained per Cloud SQL defaults
    # (typically 7 days). Point-in-time recovery is OFF — it
    # adds noticeable cost and isn't needed at our scale.
    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = false
      start_time                     = "03:00"   # nightly @ 3 AM UTC
    }

    # IP configuration: public IPv4 is enabled so the Cloud SQL
    # Auth Proxy can reach the instance, but we don't configure
    # any authorized_networks — there's no IP-based access. All
    # connections go through IAM-authenticated proxy.
    ip_configuration {
      ipv4_enabled = true
    }

    # Predictable weekly maintenance window. Sunday 4 AM UTC
    # is low-traffic for most schedules. (day: 1=Mon ... 7=Sun)
    maintenance_window {
      day  = 7
      hour = 4
    }
  }

  # Two layers of "don't accidentally destroy this":
  # - deletion_protection is enforced by the GCP API. To delete,
  #   you must first set it to false in a separate apply.
  # - prevent_destroy is enforced by Terraform itself. To delete,
  #   you must first remove this block in a separate apply.
  # Belt and suspenders: a destroy requires two deliberate steps.
  deletion_protection = true

  lifecycle {
    prevent_destroy = true
  }
}

# ── Application database (logical DB inside the instance) ────
resource "google_sql_database" "app_database" {
  name     = "learning_agent"
  instance = google_sql_database_instance.main.name
  # Implicit dependency on the instance via the .name reference
  # above — Terraform won't try to create the database until the
  # instance is fully provisioned.
}

# ── Application user ─────────────────────────────────────────
resource "google_sql_user" "app_user" {
  name     = "app_user"
  instance = google_sql_database_instance.main.name
  password = random_password.db_app_user.result
  # Implicit dependencies on the instance AND the password.
}

# ── Database connection URL → Secret Manager ─────────────────
# This is the ONE secret version we manage in Terraform — see
# the Phase 3.4 concept primer for why this exception is OK.
# The URL is constructed from Terraform-known values; no humans
# touched the password material.
resource "google_secret_manager_secret_version" "database_url" {
  secret = google_secret_manager_secret.app_secrets["database-url"].id

  # SQLAlchemy + psycopg URL using the Cloud SQL Unix-socket
  # connection pattern. Cloud Run will mount the socket at
  # /cloudsql/<connection_name>/ automatically when configured
  # with the Cloud SQL instance in Phase 3.7.
  secret_data = format(
    "postgresql+psycopg://%s:%s@/%s?host=/cloudsql/%s",
    google_sql_user.app_user.name,
    random_password.db_app_user.result,
    google_sql_database.app_database.name,
    google_sql_database_instance.main.connection_name,
  )
}

# ── Outputs (no sensitive values) ────────────────────────────
output "sql_instance_connection_name" {
  description = "Cloud SQL connection name (PROJECT:REGION:INSTANCE). Needed for Cloud Run socket mount in Phase 3.7."
  value       = google_sql_database_instance.main.connection_name
}

output "sql_database_name" {
  description = "Application database name."
  value       = google_sql_database.app_database.name
}

output "sql_instance_name" {
  description = "Cloud SQL instance name."
  value       = google_sql_database_instance.main.name
}
