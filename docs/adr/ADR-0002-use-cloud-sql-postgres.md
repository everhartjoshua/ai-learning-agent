# ADR-0002: Use Cloud SQL Postgres

**Status:** Accepted
**Date:** 2026-05-18

## Context

We are migrating an existing educational application to a production-ready environment in Google Cloud Platform (GCP). The application has been containerized and is currently deployed on Google Cloud Run. As part of this migration, we must select a primary operational database that aligns with our current architecture, expected scaling needs, and financial constraints.

The decision is driven by the following architectural and operational realities:

Relational Data Model: The application's core schema is inherently relational, consisting of entities such as Students, Curricula, Enrollments, LearningSessions, ExerciseAttempts, and ChatMessages. The data model relies heavily on foreign keys, joins, and strict referential integrity.

Database Agnosticism: The backend interacts with the database exclusively through the SQLAlchemy ORM. There are no hand-written SQL queries, raw executions, or dependencies on specific database extensions (e.g., PostgreSQL-specific features). Consequently, swapping database dialects (such as moving from SQLite to PostgreSQL) requires minimal effort, essentially a one-line modification to the DATABASE_URL.

Straightforward Query Patterns: Database interactions consist entirely of standard CRUD operations with occasional joins. There are no requirements for analytical processing (OLAP), time-series tracking, graph traversals, or full-text search, as vector search capabilities are already handled independently by ChromaDB.

Low Scale & Throughput: For the foreseeable future, expected traffic is minimal (typically one learner at a time). Table sizes will range from dozens to hundreds of records, and write throughput will peak at a handful of operations per second. Complex scaling architectures—such as horizontal sharding, multi-region replication, or high-availability read replicas—are entirely unnecessary at this stage.

Strict Cost Discipline: The infrastructure is currently operating within the constraints of a $300 GCP trial credit. Minimizing fixed monthly compute and storage costs is a critical priority for this environment.

We need to evaluate our GCP-compatible database options (e.g., Cloud SQL, managed Serverless options) to find the most cost-effective solution that satisfies our relational data requirements without over-provisioning infrastructure.


## Options considered

### Option A: Cloud SQL Postgres

Cloud SQL is Google Cloud’s fully managed relational database service, supporting standard database engines including PostgreSQL, MySQL, and SQL Server. 

It operates on a traditional instance-based infrastructure model, allowing configurations to scale down to the smallest shared-core machine types available for Postgres at deployment.

 It natively supports standard SQL dialects, relational schemas, foreign keys, and ACID transactions. 
 
 Fully compatible with our existing SQLAlchemy ORM. Swapping to Cloud SQL requires no code refactoring, only a simple DATABASE_URL update. 
 
 Natively supports our established schema, including foreign keys, joins, and strict data relationships.
 
 The instance incurs a monthly cost regardless of application usage, lacking true scale-to-zero capabilities.

### Option B: AlloyDB for PostgreSQL

Google’s premium, high-performance, fully managed PostgreSQL-compatible database, engineered for intensive transactional and analytical (HTAP) workloads. Supports our PostgreSQL driver and SQLAlchemy setup without requiring code modifications. Offers unparalleled performance and availability features.  Designed for enterprise scale, AlloyDB has a high baseline entry cost. Operating even a minimal cluster would rapidly drain the $300 trial credit. Advanced features like columnar analytics and immense read pools are completely unnecessary for simple CRUD operations and a highly constrained user base.

### Option C: Firestore

GCP’s serverless, highly scalable NoSQL document database. Features a generous free tier and scales to zero, meaning it would likely cost nothing to run under our expected load. Fully serverless with no infrastructure to provision or manage. As a document store, Firestore does not support relational schemas, complex joins, or referential integrity. Adopting this option would force us to completely abandon SQLAlchemy and entirely rewrite the application's data access layer (backend/db/models.py) to fit a denormalized model.

## Dismissals

### Dismissal A: Cloud Spanner

Globally-distributed strong consistency at petabyte scale — vastly overprovisioned for an app with a few hundred rows and one learner at a time

### Dismissal B: Bigtable

Wide-column NoSQL designed for analytics and time-series at huge scale; wrong category entirely for a relational OLTP workload

## Decision

We will deploy Cloud SQL (specifically configured with a minimal PostgreSQL instance, such as a shared-core the smallest shared-core machine type available for Postgres at the time of deployment) as the primary relational database for the application.


## Consequences

### Positive

Immediate Architectural Compatibility: Cloud SQL natively supports our relational data model, ensuring all existing foreign keys, joins, and referential integrity constraints function perfectly without modifications to backend/db/models.py.

Zero Code Refactoring: Because the application interacts with the database exclusively through the SQLAlchemy ORM and avoids dialect-specific extensions, migrating to Cloud SQL only requires updating the single DATABASE_URL environment variable.

Highly Cost Effective: Utilizing a shared-core, single-zone instance fits well within our strict $300 GCP trial credit constraint, incurring a low, predictable monthly cost while easily handling our expected peak throughput of a handful of writes per second.

Managed Operational Overhead: GCP handles routine maintenance, automated backups, and patching, allowing us to maintain a production-ready posture without manual database administration.

### Negative

Fixed Baseline Cost: Unlike true serverless options, Cloud SQL does not scale down to zero. A baseline monthly cost will be billed against the trial credits continuously, regardless of whether the application is actively receiving traffic.

Manual Scaling Required: If application traffic or storage requirements grow significantly beyond our current forecast, we will eventually need to manually scale up the machine type or disk size, as it does not auto-scale compute resource tiers out of the box.

Cloud Run's per-request horizontal autoscaling can multiply database connections faster than Postgres expects. Each container instance maintains its own SQLAlchemy connection pool; under bursty load, total connections can quickly exceed Cloud SQL's max_connections limit (typically 100 on a shared-core instance). A connection pooler — pgbouncer, the Cloud SQL Auth Proxy in pooling mode, or PgBouncer-backed Cloud SQL connections — will be required before going to production. Tracked as a Phase 3 follow-up.

Network round-trip latency: going from in-process SQLite reads (microseconds) to network-hop Postgres reads (a few milliseconds per query, sometimes more on shared-core instances) compounds across a request that runs multiple queries.

Maintenance Windows: Cloud SQL instances have weekly maintenance windows during which the instance may be briefly unavailable (usually under a minute, but possible). For a learning app, fine; for a 24/7 enterprise system this would shape the choice differently.

### Trade-offs accepted

Fixed Baseline Cost over True Serverless Scaling: We are intentionally accepting a fixed, continuous monthly compute charge from Cloud SQL instead of a scale-to-zero serverless model (like Firestore). This is an acceptable trade-off because rewriting our entire relational database layer and data schema to support a NoSQL paradigm would require significant engineering effort, introducing severe project delays that outweigh the minor monthly cost of a shared-core instance.

Manual Upgrades over Automated Vertical Scaling: We accept that scaling compute resources or storage beyond our initial configuration will require manual intervention rather than happening automatically. Given our current scale of one learner at a time and a maximum of a few hundred rows per table, the risk of hitting these resource ceilings is extremely low for the foreseeable future, making manual oversight a reasonable compromise.

## References

Option A: Cloud SQL

Google Cloud SQL Documentation: https://cloud.google.com/sql/docs

PostgreSQL on Cloud SQL Overview: https://cloud.google.com/sql/docs/postgres

Pricing Documentation: https://cloud.google.com/sql/docs/postgres/pricing

Option B: AlloyDB for PostgreSQL

Google Cloud AlloyDB Documentation: https://cloud.google.com/alloydb/docs

AlloyDB Architectural Overview: https://cloud.google.com/alloydb/docs/overview

Pricing Documentation: https://cloud.google.com/alloydb/pricing

Option C: Firestore

Google Cloud Firestore Documentation: https://cloud.google.com/firestore/docs

Firestore Data Model & Architectural Overview: https://cloud.google.com/firestore/docs/data-model

Pricing and Free Tier Documentation: https://cloud.google.com/firestore/pricing
