from django.contrib import admin

from .models import AvailabilityRule, Blackout, Quota, Policy

for m in (AvailabilityRule, Blackout, Quota, Policy,):
    admin.site.register(m)
