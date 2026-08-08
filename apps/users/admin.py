from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Extend Django's built-in UserAdmin rather than replacing it.
    This preserves the password change form, permission management,
    and all built-in functionality while surfacing our custom fields.
    """
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'is_active')
    list_filter = ('role', 'is_active', 'is_staff')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'phone')
    ordering = ('first_name', 'last_name')

    fieldsets = BaseUserAdmin.fieldsets + (
        ('POS Role & Info', {
            'fields': ('role', 'phone', 'hourly_rate'),
        }),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('POS Role & Info', {
            'fields': ('role', 'phone', 'hourly_rate'),
        }),
    )
