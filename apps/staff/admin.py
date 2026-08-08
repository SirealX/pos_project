from django.contrib import admin

from .models import Shift, ScheduledShift


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = (
        'employee', 'clock_in', 'clock_out',
        'hours_worked_display', 'active_badge', 'is_approved', 'approved_by',
    )
    list_filter = ('is_approved', 'clock_in')
    search_fields = ('employee__username', 'employee__first_name', 'employee__last_name')
    readonly_fields = ('created_at', 'hours_worked_display')
    raw_id_fields = ('employee', 'approved_by')
    date_hierarchy = 'clock_in'
    actions = ['approve_shifts', 'unapprove_shifts']

    @admin.display(description='Hours')
    def hours_worked_display(self, obj):
        return f"{obj.hours_worked:.2f}h"

    @admin.display(boolean=True, description='Active?')
    def active_badge(self, obj):
        return obj.is_active

    @admin.action(description='Approve selected shifts')
    def approve_shifts(self, request, queryset):
        queryset.update(is_approved=True, approved_by=request.user)

    @admin.action(description='Unapprove selected shifts')
    def unapprove_shifts(self, request, queryset):
        queryset.update(is_approved=False, approved_by=None)


@admin.register(ScheduledShift)
class ScheduledShiftAdmin(admin.ModelAdmin):
    list_display = ('employee', 'scheduled_date', 'start_time', 'end_time', 'created_by')
    list_filter = ('scheduled_date',)
    search_fields = ('employee__username', 'employee__first_name', 'employee__last_name')
    raw_id_fields = ('employee', 'created_by')
    date_hierarchy = 'scheduled_date'
