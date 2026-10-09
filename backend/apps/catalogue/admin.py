from django.contrib import admin

from .models import Location, ResourceType, Resource, ResourceImage, ResourceAttribute, Custodian

for m in (Location, ResourceType, Resource, ResourceImage, ResourceAttribute, Custodian,):
    admin.site.register(m)
