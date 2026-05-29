# ──────────────────────────────────────────────────────────────
# monitoring.tf — observability stack
# ──────────────────────────────────────────────────────────────
# Per ADR-0006: native Cloud Monitoring + Cloud Logging, one
# Production Overview dashboard (Four Golden Signals), and five
# symptom-not-cause alert policies routed to a single
# operational notification channel.
#
# Billing budget is set up out-of-band via the GCP console — see
# the Phase 7 runbook. Budgets attach to the billing account
# (parent of the project), and one-time console setup is simpler
# than threading billing-account-scoped Terraform for a learning
# project.

# ──────────────────────────────────────────────────────────────
# Notification channel
# ──────────────────────────────────────────────────────────────
# One channel for all operational alerts. To add a Slack webhook
# or SMS later, declare another channel and add its .name to
# the notification_channels list on each alert policy.
resource "google_monitoring_notification_channel" "ops_email" {
  display_name = "Operational alerts (email)"
  type         = "email"
  description  = "Service errors, latency, saturation — symptoms requiring attention."

  labels = {
    email_address = "everhart.joshua@gmail.com"
  }
}

# ──────────────────────────────────────────────────────────────
# Alert policies (5) — symptoms, not causes
# ──────────────────────────────────────────────────────────────

# Alert 1 — Backend 5xx rate elevated.
# Symptom: users hitting the backend are getting server errors.
resource "google_monitoring_alert_policy" "backend_5xx" {
  display_name = "Backend: 5xx error rate elevated"
  combiner     = "OR"

  conditions {
    display_name = "Backend 5xx > 0.1 req/s for 5 min"

    condition_threshold {
      # request_count is a counter; ALIGN_RATE converts it to
      # requests-per-second per minute. Filtering by
      # response_code_class = "5xx" narrows to server errors only.
      filter = <<-EOT
        resource.type = "cloud_run_revision"
        AND resource.labels.service_name = "learning-agent-backend"
        AND metric.type = "run.googleapis.com/request_count"
        AND metric.labels.response_code_class = "5xx"
      EOT

      comparison      = "COMPARISON_GT"
      threshold_value = 0.1 # > 0.1 requests/second = > 6 requests/minute
      duration        = "300s"

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.ops_email.name]

  alert_strategy {
    auto_close = "1800s" # auto-close 30 min after metric recovers
  }

  documentation {
    content   = "Backend service is returning 5xx errors at an elevated rate. Check Cloud Logging for stack traces and Cloud SQL connectivity."
    mime_type = "text/markdown"
  }
}

# Alert 2 — Backend latency p95 elevated.
# Symptom: backend is slow enough that users notice.
resource "google_monitoring_alert_policy" "backend_latency_p95" {
  display_name = "Backend: p95 request latency > 2s"
  combiner     = "OR"

  conditions {
    display_name = "Backend p95 latency > 2000ms for 5 min"

    condition_threshold {
      filter = <<-EOT
        resource.type = "cloud_run_revision"
        AND resource.labels.service_name = "learning-agent-backend"
        AND metric.type = "run.googleapis.com/request_latencies"
      EOT

      comparison      = "COMPARISON_GT"
      threshold_value = 2000 # milliseconds
      duration        = "300s"

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_PERCENTILE_95"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.ops_email.name]
  alert_strategy { auto_close = "1800s" }

  documentation {
    content   = "Backend p95 latency exceeded 2s. LLM API may be slow, Cloud SQL may be saturated, or cold-start storms may be in progress."
    mime_type = "text/markdown"
  }
}

# Alert 3 — Frontend 5xx rate elevated.
# Symptom: the user-facing UI is broken.
resource "google_monitoring_alert_policy" "frontend_5xx" {
  display_name = "Frontend: 5xx error rate elevated"
  combiner     = "OR"

  conditions {
    display_name = "Frontend 5xx > 0.1 req/s for 5 min"

    condition_threshold {
      filter = <<-EOT
        resource.type = "cloud_run_revision"
        AND resource.labels.service_name = "learning-agent-frontend"
        AND metric.type = "run.googleapis.com/request_count"
        AND metric.labels.response_code_class = "5xx"
      EOT

      comparison      = "COMPARISON_GT"
      threshold_value = 0.1
      duration        = "300s"

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.ops_email.name]
  alert_strategy { auto_close = "1800s" }

  documentation {
    content   = "Frontend service is returning 5xx errors. Streamlit may have crashed, or the backend service URL may be unreachable."
    mime_type = "text/markdown"
  }
}

# Alert 4 — Cloud SQL connection saturation.
# Imminent failure: ADR-0002 named this as the production gotcha.
# db-f1-micro defaults to max_connections=25; we alert at 20.
resource "google_monitoring_alert_policy" "cloudsql_connections" {
  display_name = "Cloud SQL: connection count approaching max"
  combiner     = "OR"

  conditions {
    display_name = "Postgres active connections > 20 for 5 min"

    condition_threshold {
      filter = <<-EOT
        resource.type = "cloudsql_database"
        AND resource.labels.database_id = "${var.project_id}:${google_sql_database_instance.main.name}"
        AND metric.type = "cloudsql.googleapis.com/database/postgresql/num_backends"
      EOT

      comparison      = "COMPARISON_GT"
      threshold_value = 20
      duration        = "300s"

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.ops_email.name]
  alert_strategy { auto_close = "1800s" }

  documentation {
    content   = "Cloud SQL active connections approaching max_connections. This is the connection-pooling gotcha named in ADR-0002 — Cloud Run autoscaling may be multiplying connections faster than Postgres expects. Consider deploying a pooler (PgBouncer) or reducing per-instance pool size."
    mime_type = "text/markdown"
  }
}

# Alert 5 — Cloud SQL CPU saturation.
# Imminent failure: instance is running hot.
resource "google_monitoring_alert_policy" "cloudsql_cpu" {
  display_name = "Cloud SQL: CPU utilization > 80%"
  combiner     = "OR"

  conditions {
    display_name = "Postgres CPU > 80% for 10 min"

    condition_threshold {
      filter = <<-EOT
        resource.type = "cloudsql_database"
        AND resource.labels.database_id = "${var.project_id}:${google_sql_database_instance.main.name}"
        AND metric.type = "cloudsql.googleapis.com/database/cpu/utilization"
      EOT

      comparison      = "COMPARISON_GT"
      threshold_value = 0.8    # 80% as a fraction
      duration        = "600s" # 10 min — CPU spikes are noisier; want sustained

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.ops_email.name]
  alert_strategy { auto_close = "1800s" }

  documentation {
    content   = "Cloud SQL CPU sustained above 80%. db-f1-micro shared core may be hitting its compute ceiling — consider upgrading the tier per ADR-0002's manual-scaling acceptance."
    mime_type = "text/markdown"
  }
}

# ──────────────────────────────────────────────────────────────
# Production Overview dashboard
# ──────────────────────────────────────────────────────────────
# Four Golden Signals (latency, traffic, errors, saturation) per
# the Google SRE book, in a 2x2 mosaic layout. Each tile shows
# both Cloud Run services overlaid where applicable.
resource "google_monitoring_dashboard" "production_overview" {
  dashboard_json = jsonencode({
    displayName = "Learning Agent — Production Overview"

    mosaicLayout = {
      columns = 12
      tiles = [
        # ── Tile: Latency (top-left) ─────────────────────────
        {
          xPos   = 0
          yPos   = 0
          width  = 6
          height = 4
          widget = {
            title = "Latency — p50 / p95 / p99 (both services)"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "resource.type=\"cloud_run_revision\" AND metric.type=\"run.googleapis.com/request_latencies\""
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_PERCENTILE_95"
                        crossSeriesReducer = "REDUCE_MEAN"
                        groupByFields      = ["resource.label.service_name"]
                      }
                    }
                  }
                  plotType   = "LINE"
                  targetAxis = "Y1"
                }
              ]
              yAxis = { label = "ms", scale = "LINEAR" }
            }
          }
        },

        # ── Tile: Traffic (top-right) ────────────────────────
        {
          xPos   = 6
          yPos   = 0
          width  = 6
          height = 4
          widget = {
            title = "Traffic — request rate (both services)"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "resource.type=\"cloud_run_revision\" AND metric.type=\"run.googleapis.com/request_count\""
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_RATE"
                        crossSeriesReducer = "REDUCE_SUM"
                        groupByFields      = ["resource.label.service_name"]
                      }
                    }
                  }
                  plotType   = "LINE"
                  targetAxis = "Y1"
                }
              ]
              yAxis = { label = "req/s", scale = "LINEAR" }
            }
          }
        },

        # ── Tile: Errors (bottom-left) ───────────────────────
        {
          xPos   = 0
          yPos   = 4
          width  = 6
          height = 4
          widget = {
            title = "Errors — 5xx rate (both services)"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "resource.type=\"cloud_run_revision\" AND metric.type=\"run.googleapis.com/request_count\" AND metric.labels.response_code_class=\"5xx\""
                      aggregation = {
                        alignmentPeriod    = "60s"
                        perSeriesAligner   = "ALIGN_RATE"
                        crossSeriesReducer = "REDUCE_SUM"
                        groupByFields      = ["resource.label.service_name"]
                      }
                    }
                  }
                  plotType   = "LINE"
                  targetAxis = "Y1"
                }
              ]
              yAxis = { label = "5xx/s", scale = "LINEAR" }
            }
          }
        },

        # ── Tile: Saturation — Cloud SQL CPU + connections ───
        {
          xPos   = 6
          yPos   = 4
          width  = 6
          height = 4
          widget = {
            title = "Saturation — Cloud SQL CPU %"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "resource.type=\"cloudsql_database\" AND metric.type=\"cloudsql.googleapis.com/database/cpu/utilization\""
                      aggregation = {
                        alignmentPeriod  = "60s"
                        perSeriesAligner = "ALIGN_MEAN"
                      }
                    }
                  }
                  plotType   = "LINE"
                  targetAxis = "Y1"
                }
              ]
              yAxis = { label = "fraction (0-1)", scale = "LINEAR" }
            }
          }
        }
      ]
    }
  })
}

# ──────────────────────────────────────────────────────────────
# Outputs
# ──────────────────────────────────────────────────────────────
output "dashboard_url" {
  description = "Direct link to the Production Overview dashboard"
  value       = "https://console.cloud.google.com/monitoring/dashboards/custom/${reverse(split("/", google_monitoring_dashboard.production_overview.id))[0]}?project=${var.project_id}"
}

output "alert_policy_names" {
  description = "Display names of provisioned alert policies"
  value = [
    google_monitoring_alert_policy.backend_5xx.display_name,
    google_monitoring_alert_policy.backend_latency_p95.display_name,
    google_monitoring_alert_policy.frontend_5xx.display_name,
    google_monitoring_alert_policy.cloudsql_connections.display_name,
    google_monitoring_alert_policy.cloudsql_cpu.display_name,
  ]
}
