from django.contrib import admin

from .models import MaintenanceWindow

for m in (MaintenanceWindow,):
    admin.site.register(m)
