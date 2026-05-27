# SOURCES.md — Real-World Format Research

# 1. SAP Fuel & Procurement

## Format researched

SAP MM flat-file CSV exports generated from:
- ME2N (Purchase Orders)
- MB51 (Material Document List / Goods Movements)

## What I learned

SAP data can be extracted through several approaches:
- IDoc integrations
- OData APIs
- BAPIs
- flat-file report exports

The prototype intentionally focuses on CSV exports because they are operationally realistic for sustainability reporting workflows.

In many organizations:
- procurement teams already export SAP reports manually
- API integrations require Basis team involvement
- onboarding timelines are short

I also learned that:
- MSEG stores actual goods movement records
- EKKO/EKPO represent purchase order structures
- SAP exports may contain locale-specific date formats
- `MEINS` uses SAP-specific unit abbreviations
- plant codes (`WERKS`) are opaque without master data mappings

Some enterprise SAP environments also export:
- semicolon-delimited CSVs
- localized column names
- decimal-comma number formats

## What my sample data includes

The sample dataset intentionally contains:
- fuel and non-fuel material groups
- multiple plant codes
- mixed units
- suspicious quantity outliers

This allows the prototype to demonstrate:
- normalization
- scope assignment
- suspicious record detection
- ingestion robustness

## Real-world limitations

A real deployment would likely require:
- client-specific material group mappings
- handling totals rows
- broader Unicode support
- return-delivery handling
- negative quantity reconciliation

---

# 2. Utility / Electricity Data

## Format researched

Green Button-style utility CSV exports.

## What I learned

Utility exports vary heavily across providers.

However, many enterprise workflows still revolve around:
- downloadable CSV exports
- billing-period summaries
- manually shared utility data

Green Button-style CSVs were chosen because they provide:
- predictable structure
- easier normalization
- no OCR dependency

I also learned that:
- billing periods rarely align with calendar months
- unit casing varies significantly (`kWh`, `KWH`, `kwh`)
- some files contain reactive power or demand metrics
- utility metadata often appears above the actual table

The parser therefore detects where the actual tabular data begins instead of assuming a fixed row structure.

## What my sample data includes

The utility sample intentionally contains:
- realistic billing periods
- non-calendar-aligned dates
- tariff metadata
- one extremely high usage anomaly

The anomaly exists specifically to test:
- suspicious flagging
- analyst review workflows

## Real-world limitations

A production deployment would likely require:
- multi-meter handling
- OCR pipelines for PDF bills
- utility-specific normalization rules
- timezone-aware billing logic

---

# 3. Corporate Travel

## Formats researched

Travel exports inspired by:
- Navan
- SAP Concur
- business travel expense workflows

## What I learned

Enterprise travel platforms frequently expose data through CSV exports rather than APIs.

Trip records often contain:
- flight segments
- hotels
- ground transport

as separate rows.

I also learned that:
- flight distance is not always included
- airport codes are more reliable than route distances
- hotel emissions are commonly estimated using average room-night factors
- rail data is inconsistent across providers

The prototype therefore uses lightweight distance estimation instead of a full aviation dataset.

## Flight distance estimation

When travel exports omit distance:
- airport codes are used
- approximate great-circle distance is estimated

This is sufficiently realistic for a prototype ingestion workflow.

Unknown airport codes intentionally trigger suspicion flags for analyst review.

## What my sample data includes

The travel sample intentionally contains:
- domestic and international routes
- flights without distances
- hotel stays
- ground transport
- unsupported rail rows
- unknown airport codes

This allows the prototype to demonstrate:
- parser branching
- emission estimation
- suspicious record handling
- unsupported-record behavior

## Real-world limitations

A production system would likely require:
- a complete airport database
- cabin-class differentiation
- multi-leg itinerary handling
- reimbursement ingestion
- regional rail emission factors

---

# Emission Factors

## Source used

DEFRA 2023 conversion factors.

## Why DEFRA

DEFRA provides:
- publicly accessible conversion data
- broad activity coverage
- realistic business-travel categories
- fuel and electricity factors

The prototype stores factor descriptions directly on each record to preserve transparency during review workflows.

A production implementation would likely introduce:
- factor versioning
- annual imports
- recalculation pipelines
- source traceability tables