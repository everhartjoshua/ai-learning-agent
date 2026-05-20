# ADR-0004: Container Image Registry Layout

**Status:** Accepted
**Date:** 2026-05-19

## Context

To deploy our containerized application to Google Cloud Run, we require a container image registry. While Google’s legacy Container Registry (gcr.io) still exists, it is in maintenance mode and deprecated for new projects. Similarly, while Docker Hub is an industry standard, utilizing it for a GCP-deployed service introduces an external network dependency, exposes us to public pull rate limits (which degrade cold-start reliability), and lacks native integration with GCP IAM. Of the available platforms — Artifact Registry, Container Registry, Docker Hub — only Artifact Registry meets the criteria for a GCP-native, IAM-integrated, modern container registry. The remaining decisions concern how to organize and operate it.

The actual architectural decisions revolve around how we organize and operate the Artifact Registry. We must establish conventions for repository layout, tagging strategies, retention policies, regional placement, and vulnerability scanning. These choices sit at the intersection of developer velocity, production reliability, and cost control—particularly given our constraint of operating within a $300 GCP trial credit.

## Options considered

### Option A: Artifact Registry — per-service repositories

Google Cloud's modern, fully managed container image registry. It integrates natively with GCP IAM, supports fine-grained access control, allows regional co-location, and is the official standard for all new GCP infrastructure.

Provides granular IAM controls and per-service lifecycle policies, aligning with enterprise standards. Requires provisioning more infrastructure resources via Terraform.

### Option B: Artifact Registry — single shared repository

Same Artifact Registry product as Option A, but with a single shared repository instead of per-service repos.

Simplifies Terraform state and provides a single location for all project images, but limits the ability to apply different IAM or retention rules per service.

### Option C: Legacy Container Registry (gcr.io)

Google's previous generation container registry. It is currently in maintenance mode and deprecated for new deployments. Google's official documentation explicitly steers all new projects away from this service, making it non-viable for our architecture.

### Option D: Docker Hub

The industry-standard public container registry. While ubiquitous, utilizing Docker Hub for a GCP-deployed application introduces an external network dependency, subjects deployments to public image pull rate limits (which can severely impact Cloud Run cold-start reliability), and entirely bypasses GCP's native IAM security controls.

## Decision

We will use Google Artifact Registry with the following operational configurations:

### Repository layout

We will adopt a per-service repository layout (e.g., learning-agent-backend). Per-service repositories let us apply different IAM policies and retention rules to backend versus frontend as those services diverge in sensitivity, which a single shared repo cannot do without coarse workarounds.

### Tagging strategy

We will use immutable, Git commit SHA-based tags (e.g., :e464079) as the exclusive reference for Cloud Run deployments. We will still push a :latest tag alongside the SHA purely as a convenience pointer for local developer inspection, but it will never be referenced in production infrastructure.

### Retention policy

We will implement a strict retention policy to delete any image older than 14 days that is not actively pinned to a deployed Cloud Run revision. Cloud Run revisions pin images that must never be deleted; the 14-day window for unpinned images balances debug-ability of recent failed deployments against storage cost growth.

### Region

The registry will be created in the same specific region as our Cloud Run instances (e.g., us-central1). Co-locating the registry with the runtime avoids cross-region egress fees on every image pull during cold-start, and keeps pull latency in the single-digit-millisecond range.

### Vulnerability scanning

We will enable automated Artifact Registry vulnerability scanning to ensure container safety from day one.

## Consequences

### Positive

- Safe rollback semantics. Because Cloud Run deployments reference images by immutable SHA digest rather than mutable tags, rolling back to a known-good prior revision is a one-command operation. We avoid the classic mutable-tag failure mode where :latest gets overwritten by a broken deployment and the previous image becomes effectively orphaned.
- Automated Security Insights: Enabling native scanning ensures that every image pushed to the registry is automatically evaluated for known OS and package CVEs, giving us immediate visibility into our security posture before code runs in staging or production.
- Cost Containment via Storage Management: Aggressive retention policies prevent storage bloat ($0.10/GB-month), and co-locating the registry avoids cross-region network egress fees.
- Cold-Start Performance: Pulling images from a co-located Artifact Registry over GCP's internal network minimizes image pull times during Cloud Run scale-out events.
- Granular Security: Per-service repositories allow us to heavily lock down IAM push/pull permissions per component as the team scales.

### Negative

- Retention Policy Blind Spots: Artifact Registry's cleanup policies do not natively integrate with Cloud Run to know if an image is currently pinned to an active revision. Because the rules are strictly heuristic (e.g., "delete older than X days"), we must configure the retention window conservatively to avoid the catastrophic failure mode of deleting an image currently in use, which would render that Cloud Run revision unservable.
- Trial Credit Consumption: Automatic scanning introduces a fixed charge of roughly $0.26 per image scan. Under an active development lifecycle with frequent pushes, this will consume a portion of our $300 trial credit.
- Deployment-time verbosity and friction. SHA-based tags require dynamically computing and passing the commit SHA at deployment time, which is more verbose than semantic tags like :v1.2.3 and provides less at-a-glance information to humans reading deployment logs. CI must be configured to inject the SHA correctly; manual gcloud run deploy commands are unwieldy.
- More Terraform Overhead: Managing a repository per service requires more boilerplate code in our infrastructure definitions than a single shared bucket.

### Trade-offs accepted

- Deployment Verbosity over Convenience: We accept that developers and CI pipelines must dynamically calculate and pass Git SHAs into deployment commands, prioritizing the safety of guaranteed rollbacks over the ease of simply typing gcloud run deploy --image backend:latest.
- Scanning Cost over Maximum Trial-Credit Stretching. We accept the recurring per-image-scan cost (roughly $0.26 each) against the trial credit budget in exchange for security visibility from day one. The alternative — disabling native scanning to defer cost — would have created an undocumented future-work obligation to integrate an open-source scanner, and would have signaled that security posture is something we'll address later rather than from the start.

## References

- [Google Cloud Artifact Registry Documentation](https://cloud.google.com/artifact-registry/docs)
- [Transitioning from Container Registry to Artifact Registry (Deprecation Notice)](https://cloud.google.com/artifact-registry/docs/transition/setup-gcr-repo)
- [Artifact Registry Pricing](https://cloud.google.com/artifact-registry/pricing)
- [Container Analysis & Vulnerability Scanning Pricing](https://cloud.google.com/container-analysis/pricing)
- [Manage image lifecycle with cleanup policies](https://cloud.google.com/artifact-registry/docs/repositories/cleanup-policy)
- [Understanding Docker Hub Rate Limiting](https://docs.docker.com/docker-hub/download-rate-limit/)
- [Best practices for building containers: Image Versioning](https://cloud.google.com/architecture/best-practices-for-building-containers#image-versioning)
- [Deploying to Cloud Run using digest (SHA)](https://cloud.google.com/run/docs/deploying#revision)