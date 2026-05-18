# Architecture Decision Records

This folder contains the **Architecture Decision Records (ADRs)** for the AI Learning Agent project. Each ADR captures one significant architectural choice, the alternatives that were considered, and the tradeoffs we accepted in making it.

## Why we keep ADRs

Code answers "what." ADRs answer "why." Six months from now, when someone (often future-you) asks "why are we using Cloud Run instead of GKE?" or "why does the backend talk to Cloud SQL over a private IP?", the answer should not require excavating commit messages or guessing at the author's mindset. It should be a short, dated document explaining what the situation was, what options were on the table, and why one was chosen.

This practice is described in Michael Nygard's original post, [Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions). The format used here is a slight enhancement that adds an explicit *Options Considered* section.

## Conventions

**File naming.** `ADR-NNNN-short-kebab-case-title.md`, where `NNNN` is a zero-padded sequential integer.

**Numbering.** Strictly sequential, in order of acceptance. Never reused. If an ADR is rejected before acceptance, its number is still retired.

**Status.** Every ADR has one of these statuses:

- `Proposed` — drafted, under discussion, not yet authoritative.
- `Accepted` — the decision is in force.
- `Superseded by ADR-MMMM` — a newer decision has replaced this one. The original is **never edited**; the new ADR explains the change.
- `Deprecated` — the decision is no longer relevant, but nothing replaces it.

**Immutability.** Once an ADR is `Accepted`, it is not edited except to change its status. If we change our mind, we write a new ADR that supersedes the old one. The point is to capture *what we thought when we decided*, not what we'd write today.

**Length.** Aim for one printed page. If an ADR is running long, it's probably trying to be two ADRs.

## How to write a new ADR

1. Copy `_template.md` to `ADR-NNNN-your-decision.md`, picking the next available number.
2. Fill in each section. Use the active voice and present tense in the Decision section.
3. Submit as a pull request with status `Proposed`. Reviewers leave comments on options and tradeoffs.
4. After discussion, change status to `Accepted` and merge.

## Index

| #     | Title                                              | Status   |
| ----- | -------------------------------------------------- | -------- |
| 0001  | [Use Cloud Run as the deployment target](./ADR-0001-use-cloud-run-as-deployment-target.md) | Accepted |
