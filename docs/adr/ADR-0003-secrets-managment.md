# ADR-0002: Secrets Management

**Status:** Proposed
**Date:** 2026-05-19

## Context

The application currently relies on a local .env file to supply sensitive configuration values at runtime. At a minimum, these include LLM API keys (GROQ_API_KEY or OPENAI_API_KEY), and as the infrastructure evolves, this will expand to include the PostgreSQL database connection string (which contains credentials).

As we migrate the containerized application to Google Cloud Run, this local approach is no longer viable. The .env file is intentionally and correctly excluded from the container image via .dockerignore to prevent baking secrets into static artifacts. Consequently, Cloud Run requires a secure, automated mechanism to inject these secrets into the running service at request time.

Furthermore, as we introduce a CI/CD pipeline, we must distinguish between secrets needed by the application at runtime and secrets needed by the pipeline at build/deploy time. This decision must also align with our broader security posture, specifically interacting with our upcoming implementation of Workload Identity Federation (to be addressed in ADR-0005), which will establish a "no static credentials anywhere" architecture.

## Options considered

### Option A: GCP Secret Manager
Google Cloud’s native, fully managed secret storage service. It provides a central repository for storing sensitive data with built-in versioning, granular per-secret IAM access controls, and comprehensive audit logging. It integrates natively with Cloud Run, allowing stored secrets to be securely exposed to the container at runtime as either environment variables or volume-mounted files.

### Option B: Cloud Run Plain Environment Variables
Cloud Run allows standard environment variables to be set directly on the service configuration (e.g., via gcloud run deploy --set-env-vars). These variables are stored in plain text within the service definition and are exposed to the container at runtime. They do not offer version history, secret-specific access controls, or audit logging for access.

### Option C: GitHub Actions Secrets
GitHub's native secret storage mechanism for CI/CD workflows. It securely stores sensitive values at the repository or organization level, injecting them as environment variables specifically during the execution of a GitHub Actions runner. It is designed for build-time operations and does not inherently push secrets into the production runtime environment.

### Option D: HashiCorp Vault
An industry-standard, cloud-agnostic secret management platform. It offers advanced features such as dynamic secret generation, leasing, and revocation. It requires provisioning and maintaining dedicated infrastructure (or utilizing the managed HCP Vault cloud offering) and integrating Vault-specific client logic or sidecars into the deployment architecture.

### Option E: Encrypted Cloud Storage with Cloud KMS
A historical pattern where sensitive values are stored in a standard Google Cloud Storage bucket, heavily restricted via IAM, and encrypted/decrypted at rest and in transit using Google Cloud Key Management Service (KMS). The application or deployment pipeline is responsible for fetching and decrypting the payload at runtime.

## Decision

We will use GCP Secret Manager as the exclusive source of truth for runtime application secrets (LLM API keys, database connection strings) and integrate it natively with Cloud Run.

We will use GitHub Actions Secrets strictly for CI/CD pipeline configuration (e.g., providing the pipeline access to GCP, though this will eventually be superseded by Workload Identity Federation in ADR-0005). We explicitly reject plain Cloud Run environment variables for sensitive data, HashiCorp Vault (due to operational complexity), and the legacy Cloud Storage/KMS pattern.

## Consequences

### Positive

- Granular Access Control: We can apply IAM policies on a per-secret basis, ensuring the Cloud Run service identity only has access to the exact secrets it requires to operate.

- Auditability: Every secret access event is logged to Cloud Audit Logs, providing clear visibility into when and by whom (or what service) a secret was read.

- Native Integration: Cloud Run handles the retrieval of secrets from Secret Manager automatically at startup, securely mapping them to standard environment variables (e.g., GROQ_API_KEY) without requiring custom decryption logic in our application code.

- Lifecycle Management: Native support for secret versioning and automated rotation policies.

### Negative

- Increased Infrastructure Footprint: This introduces another GCP service that must be formally modeled and provisioned via our Infrastructure as Code (Terraform).

- Financial Cost: Secret Manager incurs a minor monthly fee based on the number of active secret versions and access operations, adding to our fixed baseline costs.

- Operational Discipline: While Secret Manager supports rotation, actually implementing and testing secret rotation (e.g., rotating the database password without application downtime) requires deliberate operational engineering; the presence of the feature does not guarantee it works in an emergency.

### Trade-offs accepted

- Managed Service Cost over DIY Complexity: We are intentionally paying a premium for a managed secret store rather than rolling our own zero-cost KMS-encrypted Cloud Storage pattern. The engineering time saved far outweighs the nominal monthly fee of Secret Manager.

- Vendor Lock-in over Platform Agnosticism: We are choosing a highly coupled, GCP-native solution over an agnostic tool like HashiCorp Vault. Given our existing commitment to Cloud Run and Cloud SQL, the operational simplicity of the native integration is vastly more valuable to our small team than the theoretical portability of Vault.

## References

GCP Secret Manager

- Secret Manager Overview & Features: https://cloud.google.com/security/products/secret-manager

- Secret Manager Pricing (including active versions and operations costs): https://cloud.google.com/secret-manager/pricing

Cloud Run Secrets Integration

- Configure Secrets for Cloud Run Services (Environment Variables & Volumes): https://cloud.google.com/run/docs/configuring/services/secrets

- Best Practices for Securing Cloud Run Services: https://cloud.google.com/run/docs/securing/managing-access

GitHub Actions Secrets

- Using Secrets in GitHub Actions: https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions

- GitHub Actions Secrets Architecture (Client-side encryption, build-time injection): https://docs.github.com/en/actions/concepts/security/secrets

Security Best Practices (Context for ADR-0005)

- Workload Identity Federation Overview (The "no static credentials" pattern): https://cloud.google.com/iam/docs/workload-identity-federation
