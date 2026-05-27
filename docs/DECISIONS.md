# DECISIONS.md — Ambiguities & Tradeoffs

# SAP Format Choice: CSV Export Instead of IDoc or OData

## Options considered

- SAP IDoc integration
- SAP OData APIs
- Flat CSV export from SAP reports

## Chosen approach

CSV export from SAP transaction reports.

Examples:
- ME2N
- MB51

## Why?

This is the most realistic workflow for a short ESG onboarding process.

In many enterprises:
- sustainability teams do not have SAP integration access
- Basis teams are overloaded
- firewall and authentication setup delays API integrations

CSV exports already exist operationally because procurement and finance teams regularly export these reports for reconciliation and reporting.

The prototype prioritizes ingestion realism over deep ERP integration.

---

# SAP Scope 1 vs Scope 3 Classification

SAP procurement data mixes:
- fuel procurement
- general procurement

The only available signal in many exports is `MATKL` (Material Group).

## Chosen logic

Fuel-related material groups:
- 001–006
- FUEL
- ENRG

→ Scope 1

Everything else:
→ Scope 3

## Why this is imperfect

SAP material group definitions vary by client organization.

The same material group code may represent different business meanings across companies.

## Mitigation

The analyst review workflow allows manual override before approval.

---

# Utility Format Choice: Green Button CSV

## Options considered

- Utility PDF bills
- Green Button CSV exports
- Utility APIs

## Chosen approach

Green Button CSV.

## Why?

Benefits:
- standardized structure
- no OCR required
- realistic operational workflow
- easier ingestion reliability

PDF parsing was intentionally avoided because:
- layouts vary heavily
- OCR introduces avoidable ingestion risk
- the prototype prioritizes normalization logic over document extraction

---

# Billing Period Handling

Utility billing periods rarely align to calendar months.

Example:
- Nov 9 → Dec 10

The model stores:
- billing_start
- billing_end

explicitly.

## Why not prorate?

Proration introduces derived calculations that may complicate auditing.

The prototype preserves original utility reporting periods and leaves downstream aggregation to reporting layers.

---

# Travel Format Choice

## Options considered

- Navan API
- Concur API
- CSV exports

## Chosen approach

CSV export ingestion.

## Why?

Enterprise APIs often require:
- OAuth setup
- enterprise contracts
- IT approvals

CSV exports are operationally common and sufficiently realistic for the prototype.

---

# Flight Distance Estimation

Travel exports do not always include flight distance.

## Chosen approach

Great-circle estimation using airport coordinates.

## Why?

This approach aligns reasonably well with:
- DEFRA guidance
- GHG Protocol business travel estimation approaches

The prototype intentionally uses a lightweight airport lookup instead of a complete aviation database.

Unknown airport codes trigger suspicion flags for analyst review.

---

# Emission Factor Source

## Chosen source

DEFRA 2023 conversion factors.

## Why?

DEFRA:
- is publicly available
- covers relevant activity categories
- is commonly referenced in ESG workflows

The model stores the factor description used for each calculation to preserve transparency.

---

# Tenant Handling

The prototype currently accepts `tenant_id` from request parameters.

## Why?

This simplified frontend integration and reduced authentication complexity during rapid prototyping.

## Production approach

In production:
- users would belong to tenants
- tenant filtering would happen automatically
- request parameters would not control tenant access

---

# Authentication Scope

The prototype implements:
- token authentication
- analyst login
- protected review actions

Self-service signup was intentionally omitted because the application models an internal analyst workflow system rather than a public SaaS platform.

Users are assumed to be administrator-provisioned.

---

# Single Normalized EmissionRecord Table

## Options considered

- separate tables per source
- unified normalized table

## Chosen approach

Single normalized table.

## Why?

The analyst workflow needs unified querying across all ingestion types.

Examples:
- all pending reviews
- all suspicious records
- all Scope 3 activities

A single table simplified:
- filtering
- pagination
- audit review
- dashboard rendering

The tradeoff is nullable source-specific fields, which was considered acceptable for the prototype.

---

# What Was Intentionally Deferred

The prototype intentionally does NOT yet handle:

- emission factor version history
- interval utility meter data
- currency normalization
- advanced approval chains
- immutable audit snapshots
- asynchronous ingestion workers
- facility hierarchy modeling
- market-based Scope 2 adjustments

These were intentionally deferred to prioritize:
- ingestion realism
- normalization
- analyst workflows
- auditability

---

# Questions I Would Ask Before Production Expansion

1. Does the client use multiple ERP systems?
2. Can we access SAP master data tables during onboarding?
3. Does the client use location-based or market-based Scope 2 accounting?
4. What assurance framework is being targeted?
5. Are uploads manual operational workflows or scheduled integrations?