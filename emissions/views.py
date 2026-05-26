"""
Django REST Framework — API Views

Design decisions:
- File upload goes to /api/ingest/<source_type>/ — single endpoint per source
- Review dashboard data comes from /api/records/ with query filters
- Analyst approve/reject/flag via PATCH /api/records/<id>/review/
- Lock endpoint separate: POST /api/records/<id>/lock/ — requires superuser
- We use DRF's built-in pagination (PageNumberPagination) — no custom cursor needed
  at this data scale for a prototype
- Authentication: Token auth for API, Session auth for browser dashboard
"""

from rest_framework import serializers, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db import transaction
from django.db.models import Count, Sum, Q
import hashlib

from .models import Tenant, IngestionJob, EmissionRecord
from .parsers.sap_parser import SAPIngestionParser
from .parsers.utility_parser import UtilityIngestionParser
from .parsers.travel_parser import TravelIngestionParser


# ─────────────────────────────────────────
# Serializers
# ─────────────────────────────────────────

class EmissionRecordSerializer(serializers.ModelSerializer):
    reviewed_by_email = serializers.SerializerMethodField()

    class Meta:
        model = EmissionRecord
        fields = [
            'id', 'source_type', 'activity_date', 'activity_description',
            'scope', 'quantity_original', 'unit_original',
            'quantity_normalized', 'unit_normalized', 'co2e_kg',
            'emission_factor_used',
            # Source-specific
            'sap_plant_code', 'sap_material_group', 'sap_vendor', 'sap_po_number',
            'utility_meter_id', 'utility_tariff', 'utility_billing_start', 'utility_billing_end',
            'travel_segment_type', 'travel_origin', 'travel_destination',
            'travel_traveler_email', 'travel_distance_km',
            # Review
            'review_status', 'review_note', 'reviewed_by_email', 'reviewed_at',
            'is_suspicious', 'suspicion_reasons',
            'locked', 'locked_at',
            'created_at',
        ]
        read_only_fields = [
            'id', 'source_type', 'raw_row', 'source_row_number',
            'locked', 'locked_by', 'locked_at', 'created_at',
        ]

    def get_reviewed_by_email(self, obj):
        return obj.reviewed_by.email if obj.reviewed_by else None

    def validate(self, data):
        if self.instance and self.instance.locked:
            raise serializers.ValidationError(
                "This record is locked for audit. Contact your admin to unlock."
            )
        return data


class IngestionJobSerializer(serializers.ModelSerializer):
    uploaded_by_email = serializers.SerializerMethodField()

    class Meta:
        model = IngestionJob
        fields = [
            'id', 'source_type', 'original_filename', 'status',
            'row_count_total', 'row_count_success', 'row_count_failed',
            'error_log', 'created_at', 'completed_at', 'uploaded_by_email',
        ]
        read_only_fields = fields

    def get_uploaded_by_email(self, obj):
        return obj.uploaded_by.email if obj.uploaded_by else None


class DashboardSummarySerializer(serializers.Serializer):
    """Aggregated summary for the analyst dashboard header."""
    total_records = serializers.IntegerField()
    pending_review = serializers.IntegerField()
    flagged = serializers.IntegerField()
    approved = serializers.IntegerField()
    suspicious = serializers.IntegerField()
    scope_breakdown = serializers.DictField()
    source_breakdown = serializers.DictField()
    total_co2e_kg = serializers.DecimalField(max_digits=20, decimal_places=2, allow_null=True)


# ─────────────────────────────────────────
# Ingestion View
# ─────────────────────────────────────────

class IngestView:
    """
    Mixin: handles file upload, runs parser, bulk creates records.
    Used by the three source-specific views below.
    """
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = []

    SOURCE_TYPE = None  # set in subclass
    PARSER_CLASS = None  # set in subclass

    def post(self, request, *args, **kwargs):
        tenant_id = request.data.get('tenant_id')
        if not tenant_id:
            return Response({'error': 'tenant_id required'}, status=400)

        try:
            tenant = Tenant.objects.get(id=tenant_id)
        except Tenant.DoesNotExist:
            return Response({'error': 'Tenant not found'}, status=404)

        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'No file uploaded'}, status=400)

        file_bytes = file_obj.read()
        file_hash = hashlib.sha256(file_bytes).hexdigest()

        # Create ingestion job
        job = IngestionJob.objects.create(
            tenant=tenant,
            uploaded_by=None,
            source_type=self.SOURCE_TYPE,
            original_filename=file_obj.name,
            file_hash=file_hash,
            status=IngestionJob.Status.PROCESSING,
        )

        try:
            # Run parser
            kwargs = {'tenant_id': str(tenant.id), 'job_id': str(job.id)}
            if self.SOURCE_TYPE == 'SAP':
                from .models import PlantLookup
                plant_lookup = {
                    p.plant_code: {'name': p.plant_name, 'country': p.country}
                    for p in PlantLookup.objects.filter(tenant=tenant)
                }
                kwargs['plant_lookup'] = plant_lookup

            parser = self.PARSER_CLASS(**kwargs)
            records_data, errors = parser.parse(file_bytes)

            # Bulk create records
            with transaction.atomic():
                record_objs = [EmissionRecord(**r) for r in records_data]
                EmissionRecord.objects.bulk_create(record_objs, batch_size=500)

            job.row_count_total = len(records_data) + len(errors)
            job.row_count_success = len(records_data)
            job.row_count_failed = len(errors)
            job.error_log = errors[:50]  # cap stored errors at 50
            job.status = IngestionJob.Status.COMPLETED
            job.completed_at = timezone.now()
            job.save()

            return Response({
                'job_id': str(job.id),
                'status': 'completed',
                'rows_ingested': len(records_data),
                'rows_failed': len(errors),
                'errors_preview': errors[:5],
            }, status=201)

        except Exception as e:
            job.status = IngestionJob.Status.FAILED
            job.error_log = [{'error': str(e)}]
            job.save()
            return Response({'error': str(e), 'job_id': str(job.id)}, status=400)


# ─────────────────────────────────────────
# EmissionRecord ViewSet
# ─────────────────────────────────────────

class EmissionRecordViewSet(viewsets.ModelViewSet):
    serializer_class = EmissionRecordSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'patch', 'delete']

    def get_queryset(self):
        qs = EmissionRecord.objects.select_related('reviewed_by', 'locked_by', 'ingestion_job')

        # Required: filter by tenant
        tenant_id = self.request.query_params.get('tenant_id')
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)

        # Optional filters
        source_type = self.request.query_params.get('source_type')
        if source_type:
            qs = qs.filter(source_type=source_type)

        scope = self.request.query_params.get('scope')
        if scope:
            qs = qs.filter(scope=scope)

        review_status = self.request.query_params.get('review_status')
        if review_status:
            qs = qs.filter(review_status=review_status)

        suspicious = self.request.query_params.get('suspicious')
        if suspicious == 'true':
            qs = qs.filter(is_suspicious=True)

        date_from = self.request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(activity_date__gte=date_from)

        date_to = self.request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(activity_date__lte=date_to)

        return qs

    @action(detail=True, methods=['patch'], url_path='review')
    def review(self, request, pk=None):
        """
        Analyst approves, rejects, or flags a record.
        PATCH /api/records/<id>/review/
        Body: { "review_status": "APPROVED", "review_note": "..." }
        """
        record = self.get_object()
        if record.locked:
            return Response({'error': 'Record is locked for audit.'}, status=400)

        new_status = request.data.get('review_status')
        valid_statuses = [s[0] for s in EmissionRecord.ReviewStatus.choices]
        if new_status not in valid_statuses:
            return Response({'error': f'Invalid status. Choose: {valid_statuses}'}, status=400)

        record.review_status = new_status
        record.review_note = request.data.get('review_note', record.review_note)
        record.reviewed_by = request.user
        record.reviewed_at = timezone.now()

        # Approving clears suspicious flag
        if new_status == 'APPROVED':
            record.is_suspicious = False

        record.save()
        return Response(EmissionRecordSerializer(record).data)

    @action(detail=True, methods=['post'], url_path='lock')
    def lock(self, request, pk=None):
        """
        Locks a record for audit submission. Requires superuser.
        POST /api/records/<id>/lock/
        """
        if not request.user.is_superuser:
            return Response({'error': 'Only admins can lock records.'}, status=403)

        record = self.get_object()
        if record.review_status != 'APPROVED':
            return Response({'error': 'Only approved records can be locked.'}, status=400)

        record.locked = True
        record.locked_by = request.user
        record.locked_at = timezone.now()
        record.save()
        return Response({'locked': True, 'locked_at': record.locked_at})

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        """
        Dashboard summary stats.
        GET /api/records/summary/?tenant_id=<id>
        """
        qs = self.get_queryset()
        total = qs.count()

        scope_raw = qs.values('scope').annotate(count=Count('id'), co2e=Sum('co2e_kg'))
        source_raw = qs.values('source_type').annotate(count=Count('id'))

        return Response({
            'total_records': total,
            'pending_review': qs.filter(review_status='PENDING').count(),
            'flagged': qs.filter(review_status='FLAGGED').count(),
            'approved': qs.filter(review_status='APPROVED').count(),
            'suspicious': qs.filter(is_suspicious=True).count(),
            'scope_breakdown': {
                row['scope']: {'count': row['count'], 'co2e_kg': str(row['co2e'] or 0)}
                for row in scope_raw
            },
            'source_breakdown': {row['source_type']: row['count'] for row in source_raw},
            'total_co2e_kg': str(qs.aggregate(total=Sum('co2e_kg'))['total'] or 0),
        })