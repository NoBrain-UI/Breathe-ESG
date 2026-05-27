# TRADEOFFS.md — Deliberate Omissions

# 1. Emission Factor Versioning

## What was not implemented

A fully versioned emission factor system.

The prototype currently stores:
- calculated CO₂e
- factor description used

as simple record fields.

## Why this matters

Real ESG platforms must track:
- which factor library was used
- which year/version was active
- how recalculations are performed over time

Emission factors change annually.

An auditor may require historical recalculation using updated standards.

## Why it was deferred

Building:
- a complete factor library
- category mappings
- unit conversion rules
- recalculation pipelines

would significantly increase system complexity relative to the prototype scope.

The current implementation prioritizes:
- ingestion realism
- transparency
- audit traceability

over factor governance infrastructure.

## Future direction

A future implementation would likely introduce:
- `EmissionFactor` table
- annual factor imports
- factor version references
- recalculation jobs

---

# 2. Asynchronous Ingestion Processing

## What was not implemented

Background ingestion workers.

Uploads are currently processed synchronously during the HTTP request lifecycle.

## Why this matters

Large enterprise exports can contain:
- tens of thousands of rows
- long parsing times
- expensive normalization logic

Synchronous ingestion does not scale well for large files.

## Why it was deferred

Adding:
- Celery
- Redis
- worker infrastructure
- deployment orchestration

would substantially increase operational complexity for a short prototype timeline.

The current model structure already supports future async expansion through:
- ingestion status tracking
- timestamps
- ingestion job records

## Future direction

A production implementation would likely:
- enqueue uploads
- process ingestion asynchronously
- expose job progress endpoints
- notify analysts when processing completes

---

# 3. Advanced Scope 2 Accounting

## What was not implemented

Market-based Scope 2 adjustments:
- renewable energy certificates
- PPAs
- contractual instruments

## Why this matters

Many enterprises report:
- location-based Scope 2
- market-based Scope 2

simultaneously under GHG Protocol guidance.

## Why it was deferred

Market-based accounting requires:
- additional external datasets
- contractual validity tracking
- matching logic against utility periods

This significantly expands both:
- the data model
- reconciliation complexity

The prototype intentionally focuses on:
- ingestion
- normalization
- review workflows

instead of full carbon accounting coverage.

## Future direction

Future versions could introduce:
- renewable contract models
- certificate tracking
- dual-calculation outputs
- reconciliation pipelines

---

# 4. Immutable Audit Snapshots

## What was not implemented

Immutable reporting snapshots after approval.

Approved records remain editable in the current prototype.

## Why this matters

Production ESG systems often require:
- locked reporting periods
- historical snapshots
- audit-safe submissions

to support external assurance workflows.

## Why it was deferred

Snapshotting introduces:
- record versioning
- storage duplication
- rollback logic
- approval state management

The prototype instead focuses on:
- lightweight review workflows
- reviewer attribution
- approval timestamps

## Future direction

A production system would likely:
- freeze approved reporting periods
- generate immutable submission snapshots
- preserve historical revisions

---

# 5. Fine-Grained User Permissions

## What was not implemented

Granular role-based access control.

The prototype currently assumes a small internal analyst workflow with administrator-provisioned users.

## Why this matters

Enterprise deployments often require:
- facility-level access
- reviewer roles
- approval hierarchies
- regional separation

## Why it was deferred

The assignment prioritized:
- ingestion workflows
- normalization logic
- auditability

rather than enterprise identity management complexity.

## Future direction

A future implementation would likely introduce:
- tenant-aware user profiles
- role-based permissions
- approval chains
- organization hierarchies