from django.contrib import admin
from .models import Tenant, IngestionJob, EmissionRecord, PlantLookup

admin.site.register(Tenant)
admin.site.register(IngestionJob)
admin.site.register(EmissionRecord)
admin.site.register(PlantLookup)