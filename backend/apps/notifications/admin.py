from django.contrib import admin

from .models import Notification

for m in (Notification,):
    admin.site.register(m)
