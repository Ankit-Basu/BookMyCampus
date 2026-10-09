from django.contrib import admin

from .models import TimetableVersion, TimetableEntry

for m in (TimetableVersion, TimetableEntry,):
    admin.site.register(m)
