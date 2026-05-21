# ADR-0006: Monitoring, Logging, and Alerting Stack

**Status:** Proposed
**Date:** 2026-05-20

## Context

As our application transitions to a production-ready state in Google Cloud Platform, we must establish a comprehensive observability strategy. The project's requirements explicitly mandate failure alerting, pipeline observability, and a deployment audit trail. Because the application runs entirely on managed serverless infrastructure (Cloud Run and Cloud SQL), we require an observability suite that integrates seamlessly with these services without reintroducing the operational burden we specifically sought to avoid.

Furthermore, this infrastructure must operate within the strict confines of a $300 GCP trial credit. Observability tooling that is too eager or too noisy carries a real financial cost—ingesting excessive metrics or logs can rapidly drain a constrained budget. This is the final architectural decision of Phase 2, establishing the foundation upon which subsequent implementation phases will build.

## Options considered

### Option A: GCP Native Observability (Cloud Logging & Cloud Monitoring)

The native Google Cloud observability suite (formerly Stackdriver). It automatically ingests Cloud Run stdout/stderr logs and infrastructure metrics without any agent configuration. It provides a generous free tier (50 GiB/month for logging) and natively integrates with Cloud Audit Logs for tracking deployment events.

### Option B: Third-Party SaaS (Datadog, New Relic, Honeycomb)

Premium, industry-standard observability platforms offering superior user experiences, advanced APM capabilities, and out-of-the-box integrations. While highly effective, they introduce significant baseline monetary costs and are vastly over-engineered for a solo learning project operating on limited traffic.

### Option C: Self-Hosted (Prometheus + Grafana + Loki)

Deploying and managing our own open-source observability stack. While this provides ultimate control and avoids vendor lock-in, the operational overhead of provisioning, patching, and securing the infrastructure to monitor our infrastructure completely defeats the purpose of choosing managed serverless platforms in the first place.

## Decision

We will use the native **Cloud Logging** and **Cloud Monitoring** suite. To ensure operational effectiveness and budget containment, we will implement the following specific configurations:

### Logging

We will use the default Cloud Logging destination. The auto-provisioned `_Default` log bucket will capture Cloud Run application logs (`stdout`/`stderr`). We will retain the default 30-day retention policy, which is entirely sufficient for our current scale and debugging needs without incurring long-term storage fees.

### Metrics

We will rely exclusively on auto-collected Cloud Monitoring metrics. The built-in metrics for Cloud Run (request count, latency, container CPU/memory) and Cloud SQL (CPU, memory, active connections) cover our immediate needs. We will not emit custom application-level metrics (e.g., via OpenTelemetry) at this stage to keep architecture and costs minimal.

### Dashboards

We will create a single, centralized "Production Overview" custom dashboard in Cloud Monitoring. This dashboard will track the Four Golden Signals defined by Google SRE (Latency, Traffic, Errors, Saturation) for both the backend application and the database, providing a unified pane of glass for system health.

### Alerting policies

We will strictly follow the SRE principle of alerting on *symptoms, not causes*. We will configure exactly five critical alert policies:
1. Cloud Run 5xx error rate exceeds threshold (User impact).
2. Cloud Run request latency (p95) breaches acceptable SLO (User impact).
3. Cloud Run availability drops to zero instances while receiving traffic (Service down).
4. Cloud SQL active connections approach maximum capacity (Imminent failure).
5. Monthly billing spend approaches $250 trial credit threshold (Financial limit).

### Notification channels

We will configure standard Email as the baseline notification channel. We will explicitly separate the billing-spend notification channel from operational service-down alerts, ensuring that financial warnings are routed and prioritized correctly without being muted during an operational incident.

### Audit-trail story

We will rely on Google Cloud Audit Logs, which are enabled by default for Admin Activity, to fulfill the "deployment audit trail" requirement. This will automatically record immutable logs detailing exactly when a Cloud Run revision is deployed, who (or which GitHub Actions service account) deployed it, and when infrastructure changes occur.

## Consequences

### Positive

- Zero Operational Overhead: Using the native suite requires deploying zero agents, sidecars, or collector infrastructure.
- Budget Compliance: By sticking to default retentions and auto-collected metrics, we remain comfortably within the generous free tiers (50 GiB/month logging, 150 MiB/month metrics), protecting our trial credits.
- Audit Readiness: Cloud Audit Logs natively and automatically satisfy the requirement for a verifiable deployment trail without writing custom log-emission code.

### Negative

- Alert Fatigue (Production Gotcha): If we deviate from the "symptoms-not-causes" alerting strategy, we risk the canonical SRE failure mode: alert fatigue. If we alert on high CPU or memory spikes that don't actually degrade the user experience, engineers quickly learn to ignore the notifications. When a real outage occurs, the critical alert gets lost in the noise. We must rigidly enforce that cause-level metrics only belong on dashboards, not pagers.
- Log Volume Cost Surprise (Production Gotcha): While Cloud Logging is free up to 50 GiB per project per month, it aggressively charges $0.50 per GiB beyond that limit. If a developer accidentally deploys the application with verbose `DEBUG`-level Python logging, or a chatty third-party library begins spewing stack traces, the application can quietly blow through the free tier and produce a massive billing surprise. 
- Suboptimal UX: The Cloud Monitoring user interface and query language (MQL) are notoriously less intuitive and slower to navigate than premium third-party tools like Datadog.

### Trade-offs accepted

- Basic Analytics over Premium APM: We accept the clunkier interface and basic tracing capabilities of the native GCP suite in exchange for paying zero licensing fees.
- Vendor Lock-in over Portability: Our dashboards, metric queries, and alerting policies will be tightly coupled to GCP's proprietary definitions. Migrating away from GCP in the future would require completely rewriting our observability configuration.

## References

- [Cloud Monitoring Documentation](https://cloud.google.com/monitoring)
- [Google Cloud Observability Pricing](https://cloud.google.com/products/observability/pricing)
- [The Four Golden Signals (Google SRE Book)](https://sre.google/sre-book/monitoring-distributed-systems/#xref_monitoring_golden-signals)
- [Cloud Audit Logs Documentation](https://cloud.google.com/logging/docs/audit)
