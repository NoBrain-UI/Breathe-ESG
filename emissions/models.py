"""
CORE DATA MODELS — Breathe ESG Ingestion Platform

Design decisions (defend these in review):

1. Tenant model is simple — each client = one Tenant row. All other models FK to it.
   We don't use Django's built-in Sites framework because it's overkill for this use case.

2. EmissionRecord is the single "normalized" table. SAP, utility, travel all land here
   after parsing. This avoids 3 separate query paths in the analyst dashboard.

3. raw_row (JSONField) stores the original parsed row as-is. This is the source-of-truth
   for audit — if our parser had a bug, we can re-parse from raw_row without re-uploading.

4. quantity_normalized is always in kg (mass) or kWh (energy) or km (distance).
   unit_original preserves what SAP/utility/travel platform sent us.

5. scope is nullable — ingestion sets it by source_type, but analyst can override.
   locked rows cannot be edited (post-approval state for auditors).
"""

import uuid
from django.db import models
from django.contrib.auth.models import User


class Tenant(models.Model):
    """One row per client company."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)  # used in URLs, e.g. "acme-corp"
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class IngestionJob(models.Model):
    """
    Tracks one file upload / ingestion run.
    One job can produce many EmissionRecords.
    If a file is re-uploaded, we create a new job — old records are NOT deleted,
    analyst must resolve duplicates manually. This is intentional: we never silently
    overwrite data that may have already been reviewed.
    """
    class SourceType(models.TextChoices):
        SAP_FUEL_PROCUREMENT = 'SAP', 'SAP Fuel & Procurement'
        UTILITY_ELECTRICITY = 'UTILITY', 'Utility Electricity'
        CORPORATE_TRAVEL = 'TRAVEL', 'Corporate Travel'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PROCESSING = 'PROCESSING', 'Processing'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='ingestion_jobs')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    original_filename = models.CharField(max_length=500)
    file_hash = models.CharField(max_length=64, blank=True)  # SHA-256, for dedup detection
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    row_count_total = models.IntegerField(default=0)
    row_count_success = models.IntegerField(default=0)
    row_count_failed = models.IntegerField(default=0)
    error_log = models.JSONField(default=list)  # list of {row, error} dicts
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.source_type} — {self.original_filename} ({self.status})"


class EmissionRecord(models.Model):
    """
    Normalized emission record — one row per activity event.

    Every SAP line item, utility billing period, or travel segment lands here.
    Scope 1 = direct (SAP fuel combustion)
    Scope 2 = indirect, purchased energy (utility electricity)
    Scope 3 = value chain (SAP procurement, business travel)
    """
    class Scope(models.TextChoices):
        SCOPE_1 = 'S1', 'Scope 1'
        SCOPE_2 = 'S2', 'Scope 2'
        SCOPE_3 = 'S3', 'Scope 3'
        UNKNOWN = 'UK', 'Unknown'

    class ReviewStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending Review'
        FLAGGED = 'FLAGGED', 'Flagged — Needs Attention'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    # Identity
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='emission_records')
    ingestion_job = models.ForeignKey(IngestionJob, on_delete=models.CASCADE, related_name='records')

    # Source traceability — never changes after ingestion
    source_type = models.CharField(max_length=20, choices=IngestionJob.SourceType.choices)
    raw_row = models.JSONField()  # original parsed row, immutable
    source_row_number = models.IntegerField(null=True)  # line number in uploaded file

    # Normalized activity data
    activity_date = models.DateField()
    activity_description = models.CharField(max_length=500)  # human-readable label
    scope = models.CharField(max_length=2, choices=Scope.choices, default=Scope.UNKNOWN)

    # Quantity — original and normalized
    quantity_original = models.DecimalField(max_digits=18, decimal_places=6)
    unit_original = models.CharField(max_length=50)  # e.g. "L", "KG", "kWh", "GAL"
    quantity_normalized = models.DecimalField(max_digits=18, decimal_places=6, null=True)
    unit_normalized = models.CharField(max_length=50, blank=True)  # e.g. "kg", "kWh", "km"

    # CO2e (calculated or estimated)
    co2e_kg = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    emission_factor_used = models.CharField(max_length=200, blank=True)  # e.g. "DEFRA 2023 diesel"

    # SAP-specific fields (null for non-SAP rows)
    sap_plant_code = models.CharField(max_length=20, blank=True)
    sap_material_group = models.CharField(max_length=20, blank=True)
    sap_vendor = models.CharField(max_length=50, blank=True)
    sap_po_number = models.CharField(max_length=20, blank=True)

    # Utility-specific fields
    utility_meter_id = models.CharField(max_length=100, blank=True)
    utility_tariff = models.CharField(max_length=100, blank=True)
    utility_billing_start = models.DateField(null=True, blank=True)
    utility_billing_end = models.DateField(null=True, blank=True)

    # Travel-specific fields
    travel_segment_type = models.CharField(max_length=20, blank=True)  # FLIGHT, HOTEL, GROUND
    travel_origin = models.CharField(max_length=10, blank=True)  # airport code or city
    travel_destination = models.CharField(max_length=10, blank=True)
    travel_traveler_email = models.CharField(max_length=200, blank=True)
    travel_distance_km = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Analyst review
    review_status = models.CharField(
        max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.PENDING
    )
    review_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_records'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    # Audit lock — once locked, no edits allowed (for auditor submission)
    locked = models.BooleanField(default=False)
    locked_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='locked_records'
    )
    locked_at = models.DateTimeField(null=True, blank=True)

    # Suspicion flags — set by ingestion parser, cleared by analyst on approval
    is_suspicious = models.BooleanField(default=False)
    suspicion_reasons = models.JSONField(default=list)  # e.g. ["quantity > 3 std devs", "unit mismatch"]

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-activity_date']
        indexes = [
            models.Index(fields=['tenant', 'scope', 'review_status']),
            models.Index(fields=['tenant', 'source_type', 'activity_date']),
            models.Index(fields=['ingestion_job', 'is_suspicious']),
        ]

    def __str__(self):
        return f"{self.source_type} | {self.activity_date} | {self.quantity_original} {self.unit_original}"

    def can_edit(self):
        """Locked rows cannot be modified. Checked in serializer save()."""
        return not self.locked


class PlantLookup(models.Model):
    """
    SAP plant codes (WERKS) are meaningless without this table.
    e.g. WERKS='1027' maps to 'Mumbai Refinery, India'.
    In a real deployment, this would be seeded from the client's SAP master data.
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    plant_code = models.CharField(max_length=20)
    plant_name = models.CharField(max_length=255)
    country = models.CharField(max_length=100, blank=True)
    region = models.CharField(max_length=100, blank=True)

    class Meta:
        unique_together = ['tenant', 'plant_code']

    def __str__(self):
        return f"{self.plant_code} — {self.plant_name}"