# ADR-0005: Workload Identity Federation vs. Service Account Keys for CI/CD authentication

**Status:** Accepted
**Date:** 2026-05-20

## Context

As the application transitions to a production-ready Cloud Run environment, we will automate deployments using GitHub Actions. This CI/CD deployment workflow requires privileged access to Google Cloud to perform operations such as pushing container images to Artifact Registry, deploying new service revisions, and reading infrastructure state. 

CI/CD pipelines are inherently high-value targets; supply chain attacks frequently exploit static credentials stored in continuous integration systems. Accidental exposure can easily occur through verbose CI logs, misconfigured debug outputs, or downstream dependency compromises. To establish a zero-trust, enterprise-grade security posture from day one, we must select an authentication mechanism that minimizes the blast radius of potential exposure and enforces the principle of least privilege. 

This decision addresses the security posture of our CI/CD pipeline identity. It serves as the infrastructure counterpart to ADR-0003 (which addressed runtime application secrets). Together, these decisions aim to establish a comprehensive "no static credentials in long-term storage" architecture across both the application runtime and the deployment infrastructure, ensuring that security scales safely as the project and team grow.

## Options considered

### Option A: Workload Identity Federation (WIF)

The modern industry best practice. Instead of storing long-lived credentials, the GitHub Actions runner receives a short-lived OpenID Connect (OIDC) token from GitHub at the start of a workflow. This token is presented to Google Cloud's Security Token Service, validated, and exchanged for a short-lived GCP access token (typically valid for 1 hour). 

### Option B: Service Account JSON Keys

The classic, legacy approach. A service account is created in GCP, a long-lived JSON key file is generated, and its contents are pasted into a GitHub Actions Secret. Setup is dramatically simpler than WIF. However, the operational and security costs are exceedingly high: the key file never expires by default, rotation is a painful manual process requiring pipeline downtime, and any accidental leak results in a permanent infrastructure breach until the key is discovered and manually revoked.

### Option C: Self-hosted runners with attached Service Accounts

Running GitHub Actions on our own Compute Engine VMs within Google Cloud. Because each VM has a GCP Service Account natively attached, workflows authenticate automatically via the internal metadata server without requiring credential management. While this eliminates the cross-cloud authentication problem entirely, the operational overhead of managing VM lifecycles, network security, OS patching, and auto-scaling makes it massively over-engineered for a project of this scale.

### Option D: User credentials (PATs / gcloud auth login)

Authenticating the pipeline using a developer's Personal Access Token or local user account credentials. This pattern violates the principle of non-repudiation, masks machine actions as human actions in audit logs, and tightly couples pipeline success to a single human's account state. It is never appropriate for CI/CD and is mentioned here only to formally dismiss it.

## Decision

We will implement Workload Identity Federation (WIF) for all GitHub Actions authentication to Google Cloud.

To ensure the Terraform implementation does not have to re-derive the architectural design, the setup will strictly enforce the following configuration:

### Workload Identity Pool:

Provision exactly one pool dedicated to GitHub Actions workflows.

### OIDC Provider:

Provision one provider within the pool, configured to trust the GitHub Actions token issuer (`https://token.actions.githubusercontent.com`).

### Strict Attribute Condition:

The provider *must* be configured with an attribute condition that restricts token exchange exclusively to our repository (e.g., `assertion.repository == 'everhartjoshua/ai-learning-agent'`).

### Least-Privilege Service Accounts:

Workflows will not use a single "god mode" service account. We will provision specific service accounts scoped to their pipeline jobs (e.g., a build account that can only push to Artifact Registry; a deploy account that can only update Cloud Run).

### IAM Bindings:

We will grant the `roles/iam.workloadIdentityUser` role using `principalSet://` references that match our repository's attribute mapping, allowing the GitHub workflows to impersonate the target service accounts.

## Consequences

### Positive

- Zero Static Credentials: No JSON keys are generated, stored, or managed. There is nothing in the GitHub Secrets store that an attacker could exfiltrate to gain permanent GCP access.
- Automatic Rotation & Expiration: The exchanged GCP access tokens expire automatically after roughly one hour. Even in the highly unlikely event of a token leak via CI logs, the window of vulnerability is drastically minimized and resolves itself.
- Auditable Identity: Access is logged in Cloud Audit Logs with granular metadata detailing exactly which federated identity (which GitHub repository, environment, and workflow run) requested the token and performed the actions.
- Architectural Alignment: This decision completes the "no static credentials anywhere" pattern, aligning the project with modern DevSecOps best practices.

### Negative

- The Attribute Condition Trap (Production Gotcha): By default, if an explicit attribute condition is omitted when creating the OIDC provider, the Workload Identity Pool will happily accept valid OIDC tokens from *any* GitHub repository on the internet. A malicious actor with knowledge of the Pool ID could use their own public GitHub repo to exchange tokens for access to our GCP service accounts. We mitigate this by mandating the `assertion.repository` condition, but it requires strict vigilance—missing this one line in Terraform transforms WIF from highly secure to dangerously vulnerable.
- Principal vs. PrincipalSet Subtlety: Properly configuring the IAM bindings requires understanding the distinction between `principal://` (which targets one specific federated identity or workflow run) and `principalSet://` (which targets a set defined by attribute matching, such as "all workflows in this repo"). Misunderstanding this often leads to broken pipeline authentications during setup.
- Terraform Footprint: The infrastructure-as-code required to provision Pools, Providers, Service Accounts, and IAM bindings is significantly larger and more complex than simply generating a single JSON key. 
- External Dependencies: Deployment capability is now strictly dependent on the uptime of both GitHub's OIDC issuer and Google's Security Token Service. An outage in either endpoint will break our ability to deploy.

### Trade-offs accepted

- Initial Complexity over Setup Speed: We accept a steeper learning curve and a more complex Terraform configuration in exchange for eliminating the catastrophic risk of long-lived, leaked service account keys.
- Debugging Friction over Accessibility: Troubleshooting an OIDC token exchange failure requires inspecting JWT claims and GCP audit logs, which is significantly harder than simply testing a downloaded JSON key locally. We accept this debugging friction as the cost of zero-trust security.
- Provider Coupling over CI Portability: Tying authentication to GitHub's specific OIDC issuer means migrating to another CI provider (e.g., GitLab CI) would require provisioning new Identity Pools and Providers. We accept this coupling because a JSON key, while inherently portable, is universally insecure.

## References

- [Workload Identity Federation Overview](https://cloud.google.com/iam/docs/workload-identity-federation)
- [Best practices for securing service accounts](https://cloud.google.com/iam/docs/best-practices-for-securing-service-accounts)
- [About security hardening with OpenID Connect (GitHub Actions)](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect)
- [Google GitHub Actions Auth Action Documentation](https://github.com/google-github-actions/auth)