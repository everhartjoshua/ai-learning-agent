# ADR-0004: Container Image Registry Layout

**Status:** Proposed
**Date:** 2026-05-19

## Context

To deploy our containerized application to Google Cloud Run, we require a container image registry. While Google’s legacy Container Registry (gcr.io) still exists, it is in maintenance mode and deprecated for new projects, making Artifact Registry the mandatory native choice. Similarly, while Docker Hub is an industry standard, utilizing it for a GCP-deployed service introduces an external network dependency, exposes us to public pull rate limits (which degrade cold-start reliability), and lacks native integration with GCP IAM. Therefore, Artifact Registry is the undisputed platform choice.

The actual architectural decisions revolve around how we organize and operate the Artifact Registry. We must establish conventions for repository layout, tagging strategies, retention policies, regional placement, and vulnerability scanning. These choices sit at the intersection of developer velocity, production reliability, and cost control—particularly given our constraint of operating within a $300 GCP trial credit.

## Options considered

### Option A: Artifact Registry

Google Cloud's modern, fully managed container image registry. It integrates natively with GCP IAM, supports fine-grained access control, allows regional co-location, and is the official standard for all new GCP infrastructure.

### Option B: Legacy Container Registry (gcr.io)

Google's previous generation container registry. It is currently in maintenance mode and deprecated for new deployments. Google's official documentation explicitly steers all new projects away from this service, making it non-viable for our architecture.

### Option C: Docker Hub

The industry-standard public container registry. While ubiquitous, utilizing Docker Hub for a GCP-deployed application introduces an external network dependency, subjects deployments to public image pull rate limits (which can severely impact Cloud Run cold-start reliability), and entirely bypasses GCP's native IAM security controls.


## Decision

We will use Google Artifact Registry with the following operational configurations:

### Repository layout

We will adopt a per-service repository layout (e.g., learning-agent-backend).

### Tagging strategy

We will use immutable, Git commit SHA-based tags (e.g., :e464079) as the exclusive reference for Cloud Run deployments. We will still push a :latest tag alongside the SHA purely as a convenience pointer for local developer inspection, but it will never be referenced in production infrastructure.

### Retention policy

We will implement a strict retention policy to delete any image older than 14 days that is not actively pinned to a deployed Cloud Run revision.

### Region

The registry will be created in the same specific region as our Cloud Run instances (e.g., us-central1).

### Vulnerability scanning

We will disable automated Artifact Registry vulnerability scanning.

## Consequences

### Positive

- Cost Containment: Aggressive retention policies prevent storage bloat ($0.10/GB-month), disabling automated scanning saves $0.26 per CI build, and co-locating the registry avoids cross-region network egress fees.
- Cold-Start Performance: Pulling images from a co-located Artifact Registry over GCP's internal network minimizes image pull times during Cloud Run scale-out events.
- Granular Security: Per-service repositories allow us to heavily lock down IAM push/pull permissions per component as the team scales.

### Negative

- The Mutable-Tag Rollback Failure (Production Gotcha): By mandating SHA tags, we avoid a critical trap. If a team deploys backend:latest, discovers a fatal bug, and attempts to "roll back," they quickly realize the previous stable image's :latest tag was overwritten by the broken deployment. The old image still exists in storage, but without its tag, it is effectively orphaned and must be painstakingly hunted down by its raw SHA digest. We avoid this trap, but at the cost of typing and passing around verbose, non-human-readable SHA strings during deployments.
- More Terraform Overhead: Managing a repository per service requires more boilerplate code in our infrastructure definitions than a single shared bucket.

### Trade-offs accepted

- Deployment Verbosity over Convenience: We accept that developers and CI pipelines must dynamically calculate and pass Git SHAs into deployment commands, prioritizing the safety of guaranteed rollbacks over the ease of simply typing gcloud run deploy --image backend:latest.
- Pipeline Complexity over Managed Scanning: We accept the trade-off of saving $0.26 per build by disabling GCP's native vulnerability scanner, which requires us to eventually integrate and maintain our own open-source scanning tool within the GitHub Actions CI pipeline to maintain a secure posture.

## References

- [Google Cloud Artifact Registry Documentation](https://cloud.google.com/artifact-registry/docs)
- [Transitioning from Container Registry to Artifact Registry (Deprecation Notice)](https://cloud.google.com/artifact-registry/docs/transition/setup-gcr-repo)
- [Artifact Registry Pricing](https://cloud.google.com/artifact-registry/pricing)
- [Container Analysis & Vulnerability Scanning Pricing](https://cloud.google.com/container-analysis/pricing)
- [Manage image lifecycle with cleanup policies](https://cloud.google.com/artifact-registry/docs/repositories/cleanup-policy)
- [Understanding Docker Hub Rate Limiting](https://docs.docker.com/docker-hub/download-rate-limit/)
- [Best practices for building containers: Image Versioning](https://cloud.google.com/architecture/best-practices-for-building-containers#image-versioning)
- [Deploying to Cloud Run using digest (SHA)](https://cloud.google.com/run/docs/deploying#revision)