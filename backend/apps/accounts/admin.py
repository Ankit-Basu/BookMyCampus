from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Department, User


@admin.register(User)
class BMCUserAdmin(UserAdmin):
    list_display = ["username", "first_name", "last_name", "role", "department", "restricted_until"]
    list_filter = ["role", "department"]
    fieldsets = UserAdmin.fieldsets + (("Campus", {"fields": ("role", "department", "phone", "restricted_until", "restriction_reason")}),)


admin.site.register(Department)
