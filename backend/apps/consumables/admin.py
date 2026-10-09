from django.contrib import admin

from .models import Consumable, Issuance

for m in (Consumable, Issuance,):
    admin.site.register(m)
