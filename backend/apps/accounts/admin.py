from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Tenant, User, SSHCredential


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "created_at")
    list_filter = ("status",)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "tenant", "role", "is_active")
    list_filter = ("role", "tenant")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("SITOP", {"fields": ("tenant", "role")}),
    )


@admin.register(SSHCredential)
class SSHCredentialAdmin(admin.ModelAdmin):
    list_display = ("name", "username", "auth_type", "tenant", "created_at")
    list_filter = ("auth_type", "tenant")
