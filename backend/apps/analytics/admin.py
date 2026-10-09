from django.contrib import admin

from .models import UtilisationSnapshot

for m in (UtilisationSnapshot,):
    admin.site.register(m)
