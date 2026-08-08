"""
Staff models: Shift and ScheduledShift.

The critical architectural difference from Cesar's implementation:

Cesar uses one Shift model with nullable fields for both roles:
    clock_in, clock_out        → actual work session
    scheduled_date, start_time → planned schedule

This leads to awkward queries like:
    Shift.objects.filter(scheduled_date__isnull=False)  # get schedules
    Shift.objects.filter(clock_in__isnull=False)         # get clock records

And messy validation: a Shift with only scheduled_date and no clock_in — is
that a future shift or a bug?

This module's approach: two distinct models with single, clear responsibilities.
    Shift        → immutable record of work actually done (clock-in/out)
    ScheduledShift → plan for future work (manager-created calendar entry)

This separation makes queries self-documenting:
    Shift.objects.active()                        # who is working right now
    ScheduledShift.objects.upcoming().for_employee(user)  # their next shifts

It also enables proper constraints:
    unique_together on (employee, scheduled_date) — one schedule per day per person
    This is impossible in Cesar's model because you'd block multiple
    clock-in records for the same person on the same day.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from .managers import ShiftManager, ScheduledShiftManager


class Shift(models.Model):
    """An actual clock-in / clock-out record."""

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='shifts',
    )
    # default=timezone.now (not auto_now_add) so managers can retroactively
    # correct a clock-in time without writing a migration or raw SQL.
    clock_in = models.DateTimeField(default=timezone.now, db_index=True)
    clock_out = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    is_approved = models.BooleanField(default=False)
    # Audit trail: who approved this shift record
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_shifts',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ShiftManager()

    class Meta:
        ordering = ['-clock_in']

    def __str__(self):
        status = 'Active' if self.is_active else 'Completed'
        return f"{self.employee.display_name} — {self.clock_in.date()} [{status}]"

    @property
    def is_active(self) -> bool:
        return self.clock_out is None

    @property
    def duration(self):
        """timedelta of worked time. Uses now() for active shifts."""
        end = self.clock_out or timezone.now()
        return end - self.clock_in

    @property
    def hours_worked(self) -> float:
        """Duration in decimal hours, rounded to 2dp."""
        return round(self.duration.total_seconds() / 3600, 2)

    def clock_out_now(self):
        """Record clock-out at the current time."""
        self.clock_out = timezone.now()
        self.save(update_fields=['clock_out'])


class ScheduledShift(models.Model):
    """A planned shift created by a manager before the work session begins."""

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='scheduled_shifts',
    )
    scheduled_date = models.DateField(db_index=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_schedules',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ScheduledShiftManager()

    class Meta:
        ordering = ['scheduled_date', 'start_time']
        # One schedule entry per employee per day — prevents accidental doubles
        unique_together = ('employee', 'scheduled_date')

    def __str__(self):
        return (
            f"{self.employee.display_name} — "
            f"{self.scheduled_date} {self.start_time}–{self.end_time}"
        )
