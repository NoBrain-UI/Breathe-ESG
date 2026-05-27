# MODEL.md — Data Model

## Core Philosophy

The hard problem in ESG data systems is not carbon math — it is provenance and auditability.

An auditor does not only want to know a Scope 2 total. They want to know:
- which uploaded file produced the value
- which row in that file created the record
- which parser normalized it
- who reviewed it
- when it was approved

This data model was designed around traceability first.

---

# Entity Map

Tenant
└── IngestionJob (one per uploaded file)
└── EmissionRecord (one per normalized activity row)

PlantLookup (SAP plant code → human-readable facility name)

---

# Tenant

Represents one client company.

Every operational model contains a `tenant` foreign key to isolate data between companies.

A simpler explicit tenant foreign key was chosen instead of Django Sites because this application models data isolation, not multi-domain hosting.

In the current prototype, tenant isolation is enforced using request-level tenant filtering. In production, tenant identity would come from the authenticated user's tenant relationship.

---

# IngestionJob

Tracks one upload lifecycle from start to finish.

## Key fields

### file_hash
SHA-256 hash of uploaded content.

Used to detect duplicate uploads without silently overwriting historical ingestion events.

### status
Lifecycle state:

- PENDING
- PROCESSING
- COMPLETED
- FAILED

The prototype processes uploads synchronously, but the model is designed to support asynchronous queue workers later.

### error_log
JSON array of parsing failures.

Each error contains:
- row number
- raw row data
- parser error message

Only a preview subset is stored for performance reasons.

---

# EmissionRecord

Central normalized activity table.

All ingestion sources normalize into this single structure:
- SAP procurement
- Utility electricity
- Corporate travel

## Why one table instead of three?

The analyst workflow queries records across all ingestion types simultaneously.

Examples:
- "show all pending reviews"
- "show suspicious records"
- "show all Scope 3 activities"

Using one normalized table simplifies filtering, pagination, auditing, and review workflows.

The tradeoff is nullable source-specific columns, which was considered acceptable for a prototype because fields remain clearly namespaced by source type.

---

# Scope Assignment

| Source Type | Logic | Scope |
|---|---|---|
| SAP fuel procurement | direct fuel purchase | Scope 1 |
| SAP non-fuel procurement | upstream purchased goods | Scope 3 |
| Utility electricity | purchased electricity | Scope 2 |
| Travel | business travel | Scope 3 |

Scope is initially assigned during parsing but remains editable during analyst review.

---

# Source-of-Truth Tracking

Three fields form the audit trail.

## raw_row

Stores the original parsed row as immutable JSON.

This allows:
- parser debugging
- future reprocessing
- audit reconstruction

without requiring the client to re-upload the original source file.

## source_row_number

Stores the original line number from the uploaded document.

## ingestion_job

Links each activity record back to the upload event that created it.

---

# Unit Normalization

Source systems use inconsistent units.

The model stores BOTH:
- original units
- normalized units

Example:

| Original | Normalized |
|---|---|
| G | kg |
| T | kg |
| GAL | L |

This preserves auditability while enabling consistent CO₂e calculations.

---

# Suspicion Flags

Certain records are automatically flagged during parsing.

Examples:
- unusually large fuel quantities
- invalid billing periods
- impossible tariff values
- unknown airport codes

Suspicious records are visually highlighted for analyst review before approval.

---

# Review Workflow

Each record supports analyst review actions:
- APPROVED
- FLAGGED
- REJECTED

The system stores:
- review status
- review notes
- reviewer identity
- review timestamp

This creates a lightweight audit trail suitable for prototype ESG assurance workflows.

---

# PlantLookup

SAP plant codes are opaque identifiers.

Example:
- `1001`
- `2004`

These codes are mapped to human-readable facility names using `PlantLookup`.

In a real enterprise deployment this data would likely originate from SAP master data tables.

---

# Multi-Tenancy

Every operational model includes a tenant foreign key.

The current prototype accepts tenant identifiers through request parameters for simplicity.

In production:
- users would belong to tenants
- tenant filtering would be automatic
- row-level security policies would likely be added

---

# What This Model Does NOT Yet Handle

The prototype intentionally omits several production concerns:

- emission factor versioning
- currency normalization
- facility hierarchies
- asynchronous ingestion workers
- advanced approval chains
- immutable submission snapshots
- REC / market-based Scope 2 adjustments

These omissions were intentional to prioritize:
- ingestion realism
- auditability
- analyst workflows
- normalization logic