"""
URL Configuration
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token

from emissions.views import IngestView, EmissionRecordViewSet
from emissions.parsers.sap_parser import SAPIngestionParser
from emissions.parsers.utility_parser import UtilityIngestionParser
from emissions.parsers.travel_parser import TravelIngestionParser
from rest_framework.views import APIView


class SAPIngestView(IngestView, APIView):
    SOURCE_TYPE = 'SAP'
    PARSER_CLASS = SAPIngestionParser


class UtilityIngestView(IngestView, APIView):
    SOURCE_TYPE = 'UTILITY'
    PARSER_CLASS = UtilityIngestionParser


class TravelIngestView(IngestView, APIView):
    SOURCE_TYPE = 'TRAVEL'
    PARSER_CLASS = TravelIngestionParser


router = DefaultRouter()
router.register(r'records', EmissionRecordViewSet, basename='record')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    path('api/ingest/sap/', SAPIngestView.as_view()),
    path('api/ingest/utility/', UtilityIngestView.as_view()),
    path('api/ingest/travel/', TravelIngestView.as_view()),
    path('api/auth/token/', obtain_auth_token),
    path('api-auth/', include('rest_framework.urls')),
]