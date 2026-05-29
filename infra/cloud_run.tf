# ──────────────────────────────────────────────────────────────
# cloud_run.tf — backend and frontend Cloud Run services
# ──────────────────────────────────────────────────────────────
# Per ADR-0001: two separate Cloud Run services. Per ADR-0004:
# images live in Artifact Registry, referenced by SHA in CD.
#
# Terraform owns the service SHELL: the SA, env vars, Cloud SQL
# attachment, IAM policy, scaling. CD owns the IMAGE tag — see
# the lifecycle.ignore_changes blocks below.

# Placeholder image used at Terraform create time. CD will
# overwrite with real images via `gcloud run deploy`. The
# gcr.io/cloudrun/hello image listens on whatever port Cloud
# Run injects via $PORT, so it works with our 8000/8501 settings.
locals {
  placeholder_image = "gcr.io/cloudrun/hello"
}

# ──────────────────────────────────────────────────────────────
# Backend service (FastAPI, authenticated invocation only)
# ──────────────────────────────────────────────────────────────
resource "google_cloud_run_v2_service" "backend" {
  name     = "learning-agent-backend"
  location = var.region

  # INGRESS_TRAFFIC_ALL allows the service to receive traffic from
  # the internet (i.e., from the Cloud Run *.run.app URL). The
  # actual access gate is the IAM policy below — we'll deny all
  # public callers except the frontend SA.
  ingress = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.service_accounts["backend-runtime"].email

    scaling {
      # Scale to zero when idle (cost). Cap at 5 to prevent
      # runaway billing from a stuck request loop.
      min_instance_count = 0
      max_instance_count = 5
    }

    containers {
      image = local.placeholder_image

      ports {
        container_port = 8000 # uvicorn binds here in our Dockerfile
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi" # ChromaDB embedding models need headroom
        }
        startup_cpu_boost = true
      }

      # ── Plain env vars (non-secret config) ──────────────────
      env {
        name  = "LLM_PROVIDER"
        value = "groq"
      }

      env {
        name  = "GROQ_MODEL"
        value = "llama-3.1-8b-instant"
      }

      # ── Env vars from Secret Manager ────────────────────────
      env {
        name = "GROQ_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.app_secrets["groq-api-key"].secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.app_secrets["database-url"].secret_id
            version = "latest"
          }
        }
      }

      # ── Cloud SQL socket mount inside the container ─────────
      # Cloud Run auto-creates this mount server-side when a
      # Cloud SQL volume is attached, but the Terraform Google
      # provider doesn't predict that auto-mount — without
      # declaring it explicitly here, every `terraform plan`
      # would propose removing the auto-created mount (and break
      # the socket on apply). Declaring it explicitly keeps
      # state and reality aligned.
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
    }

    # ── Cloud SQL volume declaration at the template level ──
    # The Cloud SQL Auth Proxy socket is exposed at
    # /cloudsql/<connection_name>/ inside the container via the
    # volume_mount above. SQLAlchemy finds this via the host=
    # part of DATABASE_URL.
    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.main.connection_name]
      }
    }
  }

  lifecycle {
    # CD owns the running image. Terraform sets the placeholder
    # at create time, then steps out of the way. Without this
    # block, every `terraform plan` would try to revert the
    # image to the placeholder and break the actual deployment.
    ignore_changes = [
      template[0].containers[0].image,
      # Cloud Run records the client that performed the last
      # update (e.g., "gcloud", "terraform"). CD updates change
      # these fields; ignoring them prevents drift noise.
      client,
      client_version,
    ]
    prevent_destroy = true
  }
}

# IAM: only the frontend runtime SA can invoke the backend.
# Service-to-service authenticated calls via Google ID tokens.
resource "google_cloud_run_v2_service_iam_member" "backend_frontend_invoker" {
  project  = google_cloud_run_v2_service.backend.project
  location = google_cloud_run_v2_service.backend.location
  name     = google_cloud_run_v2_service.backend.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.service_accounts["frontend-runtime"].email}"
}

# ──────────────────────────────────────────────────────────────
# Frontend service (Streamlit, public)
# ──────────────────────────────────────────────────────────────
resource "google_cloud_run_v2_service" "frontend" {
  name     = "learning-agent-frontend"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.service_accounts["frontend-runtime"].email

    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    containers {
      image = local.placeholder_image

      ports {
        container_port = 8501 # streamlit default
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi" # streamlit session state can spike
        }
        startup_cpu_boost = true
      }

      # API_BASE — where the frontend finds the backend.
      # The backend's .uri attribute is the *.run.app URL, computed
      # by Terraform after the backend resource is created. This
      # implicit dependency means Terraform creates the backend
      # first, then the frontend (which references its URI).
      env {
        name  = "API_BASE"
        value = google_cloud_run_v2_service.backend.uri
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
    ]
    prevent_destroy = true
  }
}

# IAM: allUsers can invoke the frontend (it's the public UI).
# In production we'd typically front this with a Load Balancer
# and Identity-Aware Proxy or some auth layer; for the learning
# project, allowing public access is the explicit choice.
resource "google_cloud_run_v2_service_iam_member" "frontend_public" {
  project  = google_cloud_run_v2_service.frontend.project
  location = google_cloud_run_v2_service.frontend.location
  name     = google_cloud_run_v2_service.frontend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ──────────────────────────────────────────────────────────────
# Outputs
# ──────────────────────────────────────────────────────────────
output "backend_service_url" {
  description = "Backend Cloud Run service URL. Authenticated invocation only — call from the frontend with an ID token."
  value       = google_cloud_run_v2_service.backend.uri
}

output "frontend_service_url" {
  description = "Frontend Cloud Run service URL. Public — open in a browser to see the app."
  value       = google_cloud_run_v2_service.frontend.uri
}
