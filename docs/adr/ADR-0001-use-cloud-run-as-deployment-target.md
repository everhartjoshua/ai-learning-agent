# ADR-0001: Use Cloud Run as the deployment target

**Status:** Accepted
**Date:** 2026-05-17

## Context

The AI Learning Agent consists of two stateless web services — a FastAPI backend and a Streamlit frontend — both already packaged as Docker images (see ADR-0000-pending and the `Dockerfile`s in `backend/` and `frontend/`). We need to choose a runtime on Google Cloud Platform to host both services in production.

Constraints and goals that bear on this decision:

- **Traffic is bursty and unpredictable.** A student may run an interactive learning session for an hour, then nothing for two days. Cost should scale with usage, not with uptime.
- **The project runs on free-tier credits ($300 trial).** Idle cost should be near zero.
- **One operator.** The application is being built by a single person preparing for the *IT Infrastructure Engineer II* role. The target JD explicitly emphasizes "improving deployment reliability and reducing time to production," which argues against runtimes that demand significant operational care.
- **The deployment story should map to industry-standard patterns** discussable in interviews. The target JD references Vercel's serverless container model as the primary deployment target; Cloud Run is the closest GCP analogue.
- **Both services are already containerized.** Whatever runtime we choose must accept Docker images as the deployable unit.
- **State lives elsewhere.** Both services are designed to be stateless; persistent state will go to Cloud SQL (covered in a separate ADR).

## Options considered

### Option A: Cloud Run (fully managed serverless containers)

Google's serverless container runtime. Accepts any Docker image, scales from zero to many instances based on request volume, terminates HTTPS, and bills per request and per second of compute. Native integrations with Artifact Registry, Cloud SQL, Secret Manager, and Cloud Logging. Free tier covers approximately 2 million requests per service per month.

### Option B: Google Kubernetes Engine (GKE)

Google's managed Kubernetes service. Provides the full Kubernetes API and ecosystem — operators, Helm charts, service meshes, custom controllers. Best when an application needs fine-grained networking control, complex multi-service topologies, batch or stateful workloads, or features unavailable in serverless runtimes. Carries a baseline cost (control-plane fee plus node-pool VMs) regardless of traffic in standard mode; Autopilot mode is closer to serverless billing but still pricier than Cloud Run for low-traffic applications.

### Option C: Compute Engine (VMs)

Traditional virtual machines. Maximum control over the operating system, networking, and process supervision, at the cost of taking on full ownership of those concerns: OS patching, systemd unit files, restart logic, security baseline, log shipping. Always-on cost, even when the application is idle.

### Option D: App Engine Standard / Flex

GCP's original platform-as-a-service offering. Still supported. Standard environment runs in a sandbox with language-specific runtimes; Flex environment runs containers similarly to Cloud Run. App Engine predates Cloud Run and has been largely displaced by it for new projects; it is less commonly referenced in modern job postings.

## Decision

We will deploy both services as separate **Cloud Run services** (one for the FastAPI backend, one for the Streamlit frontend) in `us-central1`, sourced from container images stored in Artifact Registry.

## Consequences

### Positive

- **Near-zero idle cost.** Scale-to-zero means a long quiet period costs nothing. The free tier covers expected traffic for this project comfortably.
- **No infrastructure operations.** No clusters to upgrade, no nodes to patch, no init systems to manage, no host security baseline to maintain. The platform absorbs that work.
- **Stateless discipline is enforced by the platform.** Cloud Run does not offer persistent disks. This makes it impossible to ship a service that depends on local filesystem persistence — a class of bugs that often only surfaces in production with VM-based deployments.
- **HTTPS, IAM, and audit logging are included by default.** No configuration required to get TLS termination, per-service IAM policies, or Cloud Audit Logs for administrative actions.
- **Revision-based deployment with traffic splitting.** Each deploy creates a new revision; traffic can be split between revisions for canary and blue/green patterns. This will be the foundation of Phase 5's deployment workflow.
- **Direct mapping to the target JD's vocabulary.** "Serverless containers, deployed from GitHub Actions, with preview environments" is exactly the pattern the target role describes (over Vercel rather than Cloud Run, but the mental model transfers).

### Negative

- **Per-request time limit (60 minutes maximum as of writing).** Not a constraint for the current workload — every endpoint resolves in well under a minute — but a future feature involving long-running work (e.g., batch curriculum regeneration) would need to move that work to Cloud Tasks, Cloud Run Jobs, or Cloud Workflows.
- **Cold-start latency on the first request after scale-to-zero.** Typically 1–3 seconds for an image of our size. Acceptable for an interactive learning app where the first request after idle is the student opening the page; unacceptable for high-frequency low-latency APIs (which we are not).
- **Auto-generated service URLs.** Cloud Run services are reachable at `https://<service>-<hash>-<region>.a.run.app` by default. Pretty URLs require either Cloud Run Domain Mappings (limited) or fronting the services with a Global HTTPS Load Balancer (more configuration, more cost). Out of scope for this phase; revisit when needed.
- **Inter-service communication uses public HTTPS by default.** The frontend will reach the backend via the backend's public Cloud Run URL. This adds a small latency overhead versus private-network communication and means the backend must accept (and authenticate) public traffic. We mitigate by requiring authenticated invocation on the backend service — the frontend's runtime service account will be granted `roles/run.invoker`. A future optimization could move both services behind a VPC connector for fully private networking.

### Trade-offs accepted

- We lose Kubernetes-native features — operators, custom resources, service meshes, Helm charts, sidecars. For two stateless web services, these are options we don't need and complexity we don't want. If the application grows into something that needs them, ADR-0001 can be superseded by a future ADR proposing a migration to GKE.
- Image size affects cold-start time directly. We accept this and will revisit if cold starts degrade the user experience. (A multi-stage Dockerfile or moving to `distroless` images are both options in our back pocket.)
- We commit to using Artifact Registry as the image source, paying its (small) storage cost rather than using a free public registry. This is also the recommended pattern for IAM-controlled image pulls.

## References

- [Cloud Run documentation](https://cloud.google.com/run/docs)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Cloud Run quotas and limits](https://cloud.google.com/run/quotas)
- [Container best practices for Cloud Run](https://cloud.google.com/run/docs/tips/general)
