# Lessons Learned

Issues encountered + resolutions + interview-ready framings, surfaced during the build. Two purposes: (a) reference when the same kind of issue resurfaces; (b) source of stories and vocabulary for interviews.

**Entry format:**

> ### Title
> **Surfaced in:** phase or task. **Problem:** what went wrong. **Resolution:** how we fixed it. **Takeaway:** the general principle / interview phrasing.

---

## Git / GitHub

### The `.terraform.lock.hcl` file should be committed, not gitignored
**Surfaced in:** Phase 3.1.
**Problem:** The initial `.gitignore` I wrote in Phase 0 included `.terraform.lock.hcl` in the ignore list. This caused a downstream issue in Phase 3.6 where the lock file got out of sync with the declared providers (the `random` provider was added in Phase 3.4 but its lock entry was never committed), and `terraform plan` later failed with *"Inconsistent dependency lock file."*
**Resolution:** Removed `.terraform.lock.hcl` from `.gitignore`, replaced with a comment explaining *why* it's not ignored. Re-ran `terraform init -upgrade` to regenerate the lock file with the random provider entry, and committed it.
**Takeaway:** Provider lock files are exactly analogous to `package-lock.json` (Node) or `Cargo.lock` (Rust): they pin exact versions and checksums so every developer and CI run gets identical builds. **Always commit them.** Whenever `terraform init` modifies the lock file, the change belongs in the same PR as whatever caused it.

### Squash-merge breaks the ancestry chain back to the feature branch
**Surfaced in:** Phase 0, requirements.txt PR.
**Problem:** After squash-merging a PR on GitHub, `git branch -d feat/branch` locally emitted a warning: *"deleting branch ... that has been merged to refs/remotes/origin/feat/branch, but not yet merged to HEAD."*
**Resolution:** The warning is harmless. Squash-merge doesn't actually merge the feature branch's commits onto main; it creates a *new* commit with a different SHA containing the combined diff. The feature branch's tip commit is therefore not an ancestor of main's new HEAD — git's "safe delete" couldn't prove the work was preserved, so it warned. The work *is* preserved, just under a different hash.
**Takeaway:** **"Squash-merge keeps main's history clean (one commit per PR) at the cost of breaking the ancestry chain back to the feature branch."** Teams that prioritize forensic preservation of every commit prefer merge commits; teams that prioritize readable history prefer squash. There's no universally right answer. Interview phrasing.

### `git checkout -d` vs `git checkout -D` confusion
**Surfaced in:** Phase 3.6 recovery.
**Problem:** User tried `git checkout -D feat/branch` intending to force-delete the branch. The `-D` flag isn't valid on `git checkout`. They retried with lowercase `-d`, which silently *succeeded* — but lowercase `-d` on `git checkout` means *"detach HEAD at named commit"*, not *"delete branch."* Result: detached HEAD state, confused user.
**Resolution:** Branch deletion is `git branch -d` (safe) or `git branch -D` (force). `git checkout -b` creates and switches; lowercase `git checkout -d` detaches. Different subcommands, different flag meanings.
**Takeaway:** Git's subcommands overload flag letters with completely different meanings. When `git checkout` errors with "unknown switch," **don't retry with a different case** — look up the right subcommand. `git switch` (newer) and `git restore` (newer) replace the overloaded behaviors of `git checkout` and are worth migrating to.

### Always `git status` and `git branch` before `git commit`
**Surfaced in:** Phase 3.6, accidental commit to main.
**Problem:** User ran `git checkout -b feat/new-branch` after a previous session had already created that branch. The command errored ("branch already exists") and *did not switch* — the user remained on `main`. The next two commands (`git add`, `git commit`) ran on `main`, putting the commit on the wrong branch. Compounded by: when `git checkout -b` errors, subsequent commands run on whatever branch you were already on.
**Resolution:** Recover via cherry-pick or `git branch -f <branch> <sha>` to move the orphan commit to the right branch, then `git reset --hard origin/main` to rewind main.
**Takeaway:** **The cheap habit that prevents this entire class of mistake: `git status` and `git branch` before every commit.** Three keystrokes each, prints the current branch. Either install a prompt module like `posh-git` that shows the current branch in the prompt, or train yourself to type the two commands before any commit.

### The reflog is the safety net
**Surfaced in:** Phase 3.6 recovery.
**Problem:** User committed work, then `git reset --hard HEAD~1` which appeared to delete the commit.
**Resolution:** `git reflog` shows everything HEAD has pointed at for the last ~30 days, including orphaned commits. `git cherry-pick <orphan-sha>` (or `git reset --hard <orphan-sha>`) brings the work back.
**Takeaway:** **You cannot lose committed work in the 30-day reflog window unless you actively try.** The reflog is the silver lining of every "I screwed up git" story. Reach for it before despair.

### GitHub branch protection prevents pushes to main
**Surfaced in:** Phase 3.6.
**Problem:** Accidental local commit to main + push attempt was prevented by branch protection.
**Resolution:** Branch protection working as designed.
**Takeaway:** Branch protection is the **belt-and-suspenders** counterpart to local discipline. Even when local habits fail (you commit to main by accident), the remote refuses the push and forces you through the PR workflow. The two layers together are why solo-dev branch protection is still worth it.

---

## Shell / OS

### PowerShell `curl` is an alias for `Invoke-WebRequest`
**Surfaced in:** Phase 1, first backend test.
**Problem:** User ran `curl -X POST ... -H "Content-Type: application/json" -d '{...}'` and got *"Cannot bind parameter 'Headers'. Cannot convert string to IDictionary."* PowerShell's built-in `curl` alias points at `Invoke-WebRequest`, which expects `-Headers` as a hashtable, not a `"Key: Value"` string.
**Resolution:** Three options — (1) use `curl.exe` explicitly to bypass the alias and get the real curl binary that ships with modern Windows; (2) use `Invoke-RestMethod` with native PowerShell hashtable syntax; (3) `Remove-Item Alias:curl` in `$PROFILE` to permanently kill the alias.
**Takeaway:** **Your shell can be silently translating commands you think you're running.** When a CLI command behaves unexpectedly on Windows, the alias table is the first place to check. `Get-Alias curl` shows what's resolved.

### PowerShell vs cmd line continuation
**Surfaced in:** Phase 0, `gcloud services enable` failure.
**Problem:** User ran a multi-line `gcloud services enable` command in cmd.exe using backticks for line continuation. cmd.exe treats backticks as literal characters; only PowerShell uses backtick for line continuation. cmd.exe parsed the command as `gcloud services enable '` (a literal single-quote as the service name), which then returned the misleading error *"permission denied for service `'`."*
**Resolution:** Either switch to PowerShell (which honors backticks) or put the whole command on one line.
**Takeaway:** Different shells, different line-continuation characters: `\` in bash/zsh, backtick in PowerShell, `^` in cmd.exe. **Single-line commands work everywhere.** Multi-line commands need the right character for the right shell.

---

## GCP

### GCS bucket names are globally unique
**Surfaced in:** Phase 3.1 state-bucket creation.
**Problem:** First attempt to create `ai-learning-agent-496621-tfstate` failed with HTTP 409 *"The requested bucket name is not available. The bucket namespace is shared by all users of the system."*
**Resolution:** Check if the bucket exists in your own project first (`gcloud storage ls`); if yes, just use it. If no, add a random suffix to the name.
**Takeaway:** **GCS bucket names live in a global namespace across all of GCP.** Same as S3. Defensive pattern: prefix every bucket name with the project ID plus a deterministic suffix (environment, purpose, sometimes a hash). The "name not available" error is also intentionally ambiguous — it doesn't tell you whether the bucket exists in your project or someone else's, to prevent information disclosure.

### GCP errors are intentionally ambiguous to prevent information disclosure
**Surfaced in:** Phase 0, `gcloud services enable '` failure.
**Problem:** GCP returned *"permission denied for service `'`"* when the real cause was that PowerShell mangled the command. The error didn't distinguish "this service doesn't exist" from "you can't see this service."
**Resolution:** Sanity-check what the CLI actually sent (e.g., `gcloud --log-http`) before blaming the service.
**Takeaway:** **GCP (and AWS) use uniform error responses to prevent information disclosure.** If "exists but you can't see it" and "doesn't exist" returned different errors, an attacker could enumerate resources by probing names — even without permissions, they'd learn what exists. Collapsing both into one ambiguous error blocks the enumeration. Interview phrasing: *"The API uses uniform error responses to prevent information disclosure."* When debugging a GCP error, the cure is almost never to focus on the literal error text; it's to sanity-check the input you sent.

### Regions vs zones — the zone must be inside the region
**Surfaced in:** Phase 0, gcloud config check.
**Problem:** User's `gcloud config list` showed `region = us-central1` but `zone = us-south1-a`. These don't match — `us-south1-a` is a zone in `us-south1` (Dallas), not `us-central1` (Iowa).
**Resolution:** `gcloud config set compute/zone us-central1-a`.
**Takeaway:** **Zones are children of regions.** Each region has 3-5 zones named `<region>-<letter>`. Regional services (Cloud Run, Cloud SQL, Artifact Registry, Secret Manager) take a region; zonal services (Compute Engine, single-zone Cloud SQL) take a zone, which *must* be inside the configured region. Cross-region traffic also costs money.

### GCP APIs must be explicitly enabled per project
**Surfaced in:** Phase 0.
**Problem:** Out of the box, almost no APIs are enabled in a new GCP project. Trying to use a service before enabling its API returns *"<service>.googleapis.com has not been used in project X before or it is disabled."*
**Resolution:** `gcloud services enable <api-name>`, e.g., `gcloud services enable run.googleapis.com`.
**Takeaway:** This is a **deliberate design choice for security** — every enabled API is potential attack surface, so projects ship with everything off and you opt in. The cure is in the error message (it names the exact API). For inherited projects, `gcloud services list --enabled` is your first move to understand what's wired up.

### `gcloud auth login` vs `gcloud auth application-default login`
**Surfaced in:** Phase 0.
**Problem:** Two auth commands look similar but do different things.
**Resolution:** `gcloud auth login` stores credentials *only the gcloud CLI itself uses*. `gcloud auth application-default login` stores credentials in the **Application Default Credentials (ADC)** file that *every* GCP client library (Python SDK, Terraform, kubectl auth helpers) looks for. You need both for local dev.
**Takeaway:** Production code doesn't use either — Cloud Run code authenticates via the metadata server (the runtime SA's identity). ADC is *only* for local development. In CI/CD, **Workload Identity Federation** replaces ADC with short-lived federated tokens (no static credentials anywhere). Interview phrasing: *"Service accounts are how you give code an identity that's separately scopeable, auditable, and revocable from the humans who write the code."*

### Cloud Run `volume_mounts` for Cloud SQL — drift detection
**Surfaced in:** Phase 3.8.
**Problem:** After Phase 3.7 apply of Cloud Run with Cloud SQL volume, every subsequent `terraform plan` proposed removing a `volume_mounts` block that the user hadn't declared.
**Resolution:** Cloud Run *auto-creates* a `volume_mounts` server-side when a `cloud_sql_instance` volume is attached, but the Terraform Google provider doesn't predict this. Adding the matching `volume_mounts { name = "cloudsql"; mount_path = "/cloudsql" }` block in the container template makes state and reality align.
**Takeaway:** **Terraform-detected drift on auto-created server-side state is a provider/API impedance.** When `plan` keeps proposing the same removal of something the API created automatically, the fix is to declare it explicitly so state matches reality. Alternative: `lifecycle.ignore_changes = [template[0].containers[0].volume_mounts]` if the auto-creation is reliable.

---

## Docker

### Cloud Run's stateless processes — SQLite in a container doesn't survive restart
**Surfaced in:** Phase 1 docker-compose.
**Problem:** Test workflow — start container, create a record, stop container (`--rm`), start fresh container, query for the record → 404 Not Found.
**Resolution:** This is by design. Containers are ephemeral; any state written to the container's filesystem is destroyed on container removal. To persist data, either bind-mount a host directory (for local dev) or use an external service like Cloud SQL (for prod).
**Takeaway:** **Containers are designed to be cattle, not pets — interchangeable, disposable, anonymous.** Anything that needs to outlive a container has to live in a backing service. This is the twelve-factor "stateless processes" principle. Cloud Run goes further than just ephemeral — it doesn't even *give you* the option of a persistent disk.

### Inside a container, `localhost` means *the container itself*
**Surfaced in:** Phase 1, frontend → backend connection.
**Problem:** Frontend's hardcoded `API_BASE = "http://localhost:8000"` worked on the host (both processes on the same machine) but failed inside a container (localhost is the container's own loopback, no backend running there).
**Resolution:** Make `API_BASE` env-configurable: `API_BASE = os.getenv("API_BASE", "http://localhost:8000")`. In docker-compose, set `API_BASE: http://backend:8000` — the service name resolves via Compose's embedded DNS to the other container.
**Takeaway:** **Twelve-factor "config in env vars"** — same code runs everywhere, only the env differs. Service discovery via name (Compose DNS, Kubernetes Services, Cloud Run service URLs) abstracts away network topology. The interview phrasing: *"Service discovery is the abstraction that decouples application code from infrastructure topology."*

### Docker layer caching — order matters
**Surfaced in:** Phase 1 first build.
**Problem:** Naïve Dockerfile that did `COPY . .` before `pip install` would force pip to reinstall on every code change.
**Resolution:** Copy `requirements.txt` *first*, then `pip install`, then `COPY . .`. Dependency layer stays cached when only code changes.
**Takeaway:** **Cache key for a layer = instruction + its inputs + parent layer's hash.** When any input to an earlier layer changes, every layer below it invalidates and rebuilds. **Put slow-to-recompute, slow-to-change things first; fast-to-recompute, fast-to-change things last.** Interview phrasing: *"Cache invalidation cascades; a single early invalidation rebuilds everything below it."*

### Alpine vs slim base images — musl vs glibc
**Surfaced in:** Phase 1.
**Problem:** Alpine Linux uses musl libc instead of glibc; Python packages with pre-built C extension wheels (ChromaDB, onnxruntime, NumPy) are typically built against glibc and fail to install on Alpine.
**Resolution:** Use `python:3.11-slim` (glibc, Debian-based, ~125 MB) instead of `python:3.11-alpine` (~50 MB).
**Takeaway:** Alpine looks attractive for image-size reasons but has real compatibility costs. **For ML/data-heavy Python apps, slim is the safer default.** Distroless is even smaller and more secure but harder to debug.

---

## Terraform

### State bucket is the recursive base case of IaC
**Surfaced in:** Phase 3.1.
**Problem:** Terraform needs a place to store its state file. The natural place is a cloud bucket. But buckets are normally created by Terraform — chicken-and-egg.
**Resolution:** Create the state bucket manually via `gcloud storage buckets create`. The bucket itself is not managed by Terraform.
**Takeaway:** **"The state bucket is the recursive base case of infrastructure-as-code"** — you can't manage the thing that stores the management metadata. We accept the smallest possible manual bootstrap and document it as a runbook so it's reproducible without being declarative. Alternative patterns exist (two-stage Terraform, `terraform import` after manual creation) — both add complexity that's only worth it at scale.

### Three IAM resource flavors — composability matters
**Surfaced in:** Phase 3.5.
**Problem:** Three resource types: `_iam_member` (additive), `_iam_binding` (authoritative for one role), `_iam_policy` (authoritative for all roles). Choosing wrong can clobber other people's permissions.
**Resolution:** Use `_iam_member` by default. The other two are for deliberately taking exclusive control.
**Takeaway:** **`_iam_member` is composable; `_iam_binding` and `_iam_policy` are not.** Multiple `_iam_member` resources for the same target coexist peacefully. A single `_iam_binding` declares "I own this role on this resource — anyone else's bindings will be silently removed on next apply." This causes the classic **"state thrashing loop"** — two teams' Terraform configurations alternately evict each other's bindings on every apply. Interview phrasing: *"The default choice for almost all IAM provisioning is `_iam_member` because it's purely additive. Reach for `_iam_binding` only in centralized, tightly controlled IAM repositories where you explicitly want to govern a role with strict exclusion."*

### `for_each` vs `count` — stable identity
**Surfaced in:** Phase 3.2.
**Problem:** Choice between `for_each` (string-keyed) and `count` (integer-indexed) for creating multiple similar resources.
**Resolution:** Use `for_each` for sets of distinct things; reserve `count` for true counts of identical things (e.g., "3 NAT IPs for redundancy").
**Takeaway:** **`for_each` keys are stable identifiers.** If you remove an entry from the middle of a `for_each` map, only that one resource is destroyed. If you remove an entry from the middle of a `count`-indexed list, *every item after it shifts indices*, and Terraform plans cascading destroy-and-recreate. Interview phrasing: *"`for_each` gives every instance a stable string identity that survives reordering and middle-removal. `count` gives every instance a positional identity that shifts when the list shifts."*

### Terraform-generated secrets are an accepted exception to no-secrets-in-state
**Surfaced in:** Phase 3.4 (`random_password.db_app_user`).
**Problem:** ADR-0003 said never to put secrets in Terraform state. But the database password has to come from somewhere; if not Terraform-generated, it's a manual step that breaks reproducibility.
**Resolution:** Use `random_password` to generate inside Terraform; accept that the value lives in state (encrypted at rest in GCS bucket, IAM-controlled access).
**Takeaway:** **The test:** *"Did Terraform create 100% of the cryptographic material for this secret?"* If yes (random_password, tls_private_key) → Terraform can manage the version, no new exposure. If no (third-party API key, human-typed password) → must come in out-of-band. Interview phrasing: *"Generated-in-Terraform secrets are an accepted exception to 'no secrets in state' — because the secret never had a life outside Terraform, the state file is the same trust boundary the secret was always going to live in."*

### Two-layer destroy protection — `deletion_protection` + `prevent_destroy`
**Surfaced in:** Phase 3.4 Cloud SQL.
**Problem:** Should you use the GCP-API-level `deletion_protection` or the Terraform-level `prevent_destroy`?
**Resolution:** **Both.** They protect against different things at different layers.
**Takeaway:** `deletion_protection` is a GCP API guard — protects against console clicks, rogue scripts, compromised service accounts. `prevent_destroy` is a Terraform-level guard — protects against accidental `terraform destroy`, accidental rename-induced replace operations. **API guard doesn't stop Terraform from taking down the guardrails and destroying the database.** Legitimate destroy of a doubly-protected resource is a two-apply operation (lower the guards, then destroy) — by design, a forcing function for deliberateness.

### Cloud Run image-tag drift — the lifecycle.ignore_changes pattern
**Surfaced in:** Phase 3.7 Cloud Run.
**Problem:** Terraform creates the Cloud Run service with a placeholder image; CD later pushes a real SHA-tagged image. Without `lifecycle.ignore_changes`, every subsequent `terraform plan` would propose reverting the image to the placeholder.
**Resolution:** `lifecycle { ignore_changes = [template[0].containers[0].image] }` on each Cloud Run resource.
**Takeaway:** **Terraform and CD have different lifecycle units.** Infrastructure changes slowly through PRs; application images change rapidly through CD pushes. The `ignore_changes` block is the *explicit contract* between the two tools: Terraform owns the service shape, CD owns the running image. Without this contract, an innocent infrastructure tweak ("bump max_instance_count from 5 to 10") would cause a catastrophic production rollback to the placeholder image.

### `principal://` vs `principalSet://` in WIF bindings
**Surfaced in:** Phase 3.6.
**Problem:** Two member URI prefixes; using `principal://` instead of `principalSet://` in an IAM binding fails silently — apply succeeds, but the workflow can't actually impersonate the SA.
**Resolution:** `principal://` binds a role to one *exact* federated identity (typically the OIDC `sub` claim). `principalSet://` binds a role to *any identity matching an attribute* (e.g., any workflow from a specific repo). For repo-based federation, `principalSet://` is essentially always right.
**Takeaway:** **GCP doesn't validate that a federated principal exists at IAM binding create-time.** This is the "succeeds at apply, fails at runtime" misconfiguration class — the most insidious because there's no automated validation. **Defense: smoke-test WIF after every infrastructure change** by running a tiny "can the SA auth and call a no-op API?" workflow.

### WIF attribute_condition — the perimeter gate
**Surfaced in:** Phase 3.6.
**Problem:** Without an `attribute_condition` on the OIDC provider, *any* GitHub repo on the internet that uses OIDC can attempt the token exchange.
**Resolution:** `attribute_condition = "attribute.repository == \"everhartjoshua/ai-learning-agent\""`.
**Takeaway:** **Defense in depth at two layers.** Provider `attribute_condition` is the perimeter (token-exchange gate); IAM binding `principalSet://` is the per-resource gate. Both must be tight. Interview phrasing: *"Missing this one line in Terraform transforms WIF from highly secure to dangerously vulnerable."*

### `principalSet` URIs accept one attribute key/value, not boolean combinations
**Surfaced in:** Phase 3.6 hardening discussion.
**Problem:** Wanting to restrict ci-deploy to main-branch workflows only requires combining `repository == X && ref == refs/heads/main`. But the `principalSet://` URI is a static string, not a CEL expression — it accepts one attribute key/value pair.
**Resolution:** Use a **composite attribute mapping** in the provider: `"attribute.repo_and_branch" = "assertion.repository + ':' + assertion.ref"`. Then the IAM binding can use `principalSet://...attribute.repo_and_branch/<owner>/<repo>:refs/heads/main`.
**Takeaway:** The same problem (limited filter expressiveness) appears in many platform APIs. The fix pattern is *"compose attributes at the producer; filter on the composite at the consumer."* Common, worth recognizing.

---

## Cloud Run

### Cloud Run authentication lives at the Google Front End (GFE), not in your app
**Surfaced in:** Phase 3.7.
**Problem:** Understanding where the 403/200 decision actually happens when calling an IAM-protected Cloud Run service.
**Resolution:** Cloud Run services are always reachable at their `*.run.app` URL; whether requests are *accepted* depends on the IAM policy. The check happens at the **Google Front End reverse proxy** in front of all Cloud Run services, *before* the request reaches the container.
**Takeaway:** **Your application code never sees auth.** This is the architectural detail most candidates miss. Interview phrasing: *"The GFE is the bouncer at the network edge — it intercepts every request before the container, validates the identity token, checks IAM, and either forwards or rejects. The container only sees authenticated, authorized traffic."* A nice corollary: **403'd traffic doesn't cost you compute** — the GFE rejects without booting your container. This is the "Cloud Run is DDoS-resistant at the cost layer" angle.

### Cloud Run secret-as-env-var rotation doesn't propagate to running instances
**Surfaced in:** ADR-0003, Phase 3.7.
**Problem:** Secrets loaded via `value_source.secret_key_ref` with `version = "latest"` are resolved *once* at container startup, then pinned in RAM. Rotating the secret in Secret Manager doesn't affect running instances.
**Resolution:** To propagate a rotation, force a new revision (`gcloud run deploy ...` or a Terraform-annotation trigger). Cloud Run then drains old instances and spins up new ones that fetch the fresh secret.
**Takeaway:** **"Split-brain environment during rotation"** — mix of old-key and new-key instances serving traffic simultaneously, causing intermittent failures. Alternative pattern: mount secrets as files (`volume_mounts` + `volumes { secret {...} }`) and have the app re-read on a schedule. Uncommon; redeploy-to-rotate is the dominant pattern.

### Cloud SQL doesn't support per-instance IAM
**Surfaced in:** Phase 3.5.
**Problem:** `roles/cloudsql.client` can only be granted at the *project* level — there's no `google_sql_database_instance_iam_member` resource.
**Resolution:** Grant `cloudsql.client` at the project level via `google_project_iam_member`. With only one instance in the project, the practical impact is nil.
**Takeaway:** **Resource-level IAM is best practice but not always available** — known GCP limitation for some services. When deliberately granting at a broader scope than ideal, document it in the Terraform comments so future readers understand it was a deliberate compromise, not an oversight.

---

## Application

### Streamlit `chat_input` cannot be inside an expander or container
**Surfaced in:** chatbot feature work (pre-cloud).
**Problem:** `st.chat_input` was designed to be page-level (auto-pinned to bottom of viewport). Putting it inside an `expander` or `form` raises an error.
**Resolution:** Use a `st.form` with `st.text_input` + `st.form_submit_button` inside containers; reserve `st.chat_input` for top-level usage.
**Takeaway:** Framework-specific layout constraints aren't always obvious until you trip on them. Worth checking widget docs before composing them in non-default containers.

### SQLAlchemy `connect_args={"check_same_thread": False}` is SQLite-specific
**Surfaced in:** Phase 3.7 prep, surfaced when planning Phase 5 deployment.
**Problem:** The kwarg is for SQLite under FastAPI's threading model; passing it to a Postgres URL would error.
**Resolution:** Conditional on URL scheme — pass `connect_args` only when the URL starts with `sqlite://`. Or remove the kwarg and rely on FastAPI's default async handling.
**Takeaway:** Tracked in `todos.md`; must be fixed before the Phase 5 image is deployed against Cloud SQL.

---

## Observability / SRE

### Alert fatigue — symptoms not causes
**Surfaced in:** ADR-0006, Phase 3.8.
**Problem:** The default reflex is to alert on everything that *might* indicate a problem (CPU, memory, errors, latency, queue depth, ...). Result: alert flood, ignored alerts, real outage missed in the noise.
**Resolution:** **Symptoms-not-causes rule.** Alert only on user-visible problems (5xx rate, latency p95, can't-serve). Put cause-level metrics (CPU, memory, connection counts) on *dashboards* for investigation, not on pagers.
**Takeaway:** Interview phrasing: *"If the user can't tell something is wrong, the on-call shouldn't be told something is wrong."* Adjacent vocabulary: **work metrics vs resource metrics** — work metrics measure what the system produces (requests, errors, latency), resource metrics measure what it consumes (CPU, memory, disk). General rule: *"alert on work metrics, dashboard the resource metrics."*

### Alert lifecycle is edge-triggered, not level-triggered
**Surfaced in:** Phase 3.8.
**Problem:** Understanding when notification emails actually fire vs the continuous state of being "in alarm."
**Resolution:** Cloud Monitoring (and most alerting systems) are **edge-triggered on state transitions** — one email when state transitions OK→FIRING, one email when it transitions FIRING→OK. Not continuous spam while firing.
**Takeaway:** The five phases of any metric→alert→email path: **(1) generation & ingestion** (continuous, raw data flowing in), **(2) shaping** (alignment_period + per_series_aligner converting raw into a uniform time series), **(3) threshold evaluation** (true/false per aligned bucket), **(4) duration requirement** (state accumulation; condition must hold for N consecutive seconds), **(5) notification triggering** (edge-triggered on transitions). Knowing the five stages by name lets you talk about any alerting system (Prometheus, Datadog, CloudWatch) in the same vocabulary.

---

## ADR Writing

### Title-number typos are the most-missed error
**Surfaced in:** ADR-0003 review.
**Problem:** User copied a template and forgot to update the title (`# ADR-0002: Secrets Management` when it should have been ADR-0003).
**Resolution:** **Before declaring any document/PR done, re-read the title, the filename, and the URL bar.** Twenty seconds of friction, catches the entire class of "I forgot to update the boilerplate I set up first."
**Takeaway:** Humans naturally focus their final review on what they just edited, not on the boilerplate they set up first. The reflex of re-reading the top deliberately is the defense.

### `Status: Accepted` before review approval is jumping the gun
**Surfaced in:** ADR-0003 and ADR-0004 review.
**Problem:** User pre-flipped status to `Accepted` before reviewer signed off, twice.
**Resolution:** Status flow is **Proposed → reviewed → revisions made → reviewer approves → status:Accepted set → PR merged.** Treat flipping to Accepted as the equivalent of clicking "merge" on a PR with unresolved comments.
**Takeaway:** Mental check before flipping to Accepted: *"If a reviewer reads this right now, would they hit the green checkmark or request changes?"*

### Production-gotcha paragraphs have a four-part structure
**Surfaced in:** ADR-0005 review.
**Problem:** What makes an ADR's "Negative consequence" paragraph land vs. feel hand-wavy?
**Resolution:** Four parts: **(1) what fails** — the specific failure mode; **(2) why it fails** — the mechanism; **(3) how we prevent it** — the mitigation in our code; **(4) the broader lesson** — the principle. Example structure used in ADR-0005's attribute-condition paragraph.
**Takeaway:** Use this as a checklist when writing the Negative section of any ADR. Interview phrasing: missing any of the four parts makes the paragraph feel either vague (no mechanism) or alarmist (no mitigation).

---

## Interview-Ready Phrasings (compiled)

A running list of one-liners and short framings worth memorizing for interview conversations. Each links back to a context above.

- *"Service discovery is the abstraction that decouples application code from infrastructure topology."* (Phase 1)
- *"Containers are designed to be cattle, not pets — interchangeable, disposable, anonymous."* (Phase 1)
- *"Twelve-factor: config in env vars, stateless processes, port binding, logs to stdout, dev/prod parity."* (Phase 1)
- *"Cache invalidation cascades; a single early invalidation rebuilds everything below it."* (Phase 1, Docker)
- *"The API uses uniform error responses to prevent information disclosure."* (Phase 0, GCP errors)
- *"Plan is the safety net; apply is the trigger; reviewing the plan diff is what keeps the trigger from being pulled accidentally."* (Phase 3.1, Terraform)
- *"The state bucket is the recursive base case of infrastructure-as-code."* (Phase 3.1)
- *"Terraform is opt-in for everything — it manages only what you declare."* (Phase 3.3, Secret Manager)
- *"Generated-in-Terraform secrets are an accepted exception to no-secrets-in-state."* (Phase 3.4)
- *"API guard doesn't stop Terraform from taking down the guardrails."* (Phase 3.4, Cloud SQL)
- *"`_iam_member` is composable; `_iam_binding` causes state thrashing loops."* (Phase 3.5)
- *"For_each gives stable string identity that survives reordering; count gives positional identity that shifts."* (Phase 3.2)
- *"`iam.serviceAccountUser` is the explicit delegation that prevents privilege escalation via launch-as."* (Phase 3.5)
- *"Identity is not authorization — creating a service account doesn't grant capabilities."* (Phase 3.5)
- *"Squash-merge keeps main's history clean at the cost of breaking the ancestry chain back to the feature branch."* (Phase 0)
- *"The reflog is the silver lining of every 'I screwed up git' story."* (Phase 3.6)
- *"Infrastructure and deployment are different lifecycle units; `lifecycle.ignore_changes` is the contract between them."* (Phase 3.7)
- *"The Google Front End is the bouncer at the network edge."* (Phase 3.7, Cloud Run auth)
- *"Cloud Run is DDoS-resistant at the cost layer — rejected traffic doesn't boot containers."* (Phase 3.7)
- *"Secret rotation doesn't propagate to running instances under env-var injection — split-brain environment during rotation."* (Phase 3.7)
- *"WIF eliminates static credentials; missing the attribute_condition transforms it from secure to vulnerable."* (Phase 3.6)
- *"Composite attributes at the provider, filter on the composite at the binding."* (Phase 3.6 hardening)
- *"Alert on work metrics; dashboard the resource metrics."* (Phase 3.8, SRE)
- *"If the user can't tell something is wrong, the on-call shouldn't be told something is wrong."* (Phase 3.8)
- *"Edge-triggered on the OK→FIRING transition."* (Phase 3.8)
- *"Generated images you can pull from Artifact Registry over the internal Google network avoid both cold-start latency and cross-region egress costs."* (Phase 3.2)
- *"Vendor lock-in over platform agnosticism — the operational simplicity of GCP-native integration is worth more than the theoretical portability."* (ADR-0003, ADR-0005)
- *"Paved Road / vending machine pattern — standardized opinionated modules that platform teams provide to application teams."* (Phase 3.5)

---

## Maintenance

Add to this file at the end of every session. Format: surface the issue, name the problem, name the resolution, name the takeaway. New "interview-ready phrasings" go at the bottom of that section.
