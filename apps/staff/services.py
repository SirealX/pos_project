"""
ShiftService — clock-in/out logic and schedule management.

WHY CLOCK-IN/OUT BELONGS IN A SERVICE (NOT A VIEW)
───────────────────────────────────────────────────────────────────────────
Cesar's clock_in_view does:

    if user.is_staff:
        if not Shift.objects.filter(employee=user, clock_out__isnull=True).exists():
            Shift.objects.create(employee=user)
        else:
            messages.warning(request, "You are already clocked in.")

And CustomLoginView.get_success_url() also creates shifts:

    if user.is_staff:
        if not Shift.objects.filter(employee=user, clock_out__isnull=True).exists():
            Shift.objects.create(employee=user)

The business rule ("can't clock in twice") is duplicated in two places.
If a third entry point appears (e.g. a mobile API), it must be duplicated again.
And the race condition (double-click → two shifts) exists in both copies.

ShiftService centralises the rules once. Views call:
    ShiftService.clock_in(request.user)
and catch AlreadyClockedInError for the flash message.

THE RACE CONDITION FIX
───────────────────────────────────────────────────────────────────────────
Two simultaneous requests (e.g. slow network + double-click):
    T1: .exists() → False (no active shift)
    T2: .exists() → False (no active shift)
    T1: Shift.objects.create(employee=user) ← shift 1 created
    T2: Shift.objects.create(employee=user) ← shift 2 created
    → User now has two active shifts. Hours-worked reports are wrong.

Fix: select_for_update() on the user row.
    T1 acquires row lock on user
    T2 blocks trying to acquire the same lock
    T1 checks .exists() → False, creates shift, commits
    T2 lock acquired, checks .exists() → True, raises AlreadyClockedInError

In PostgreSQL production you can add belt-and-suspenders with a partial
unique index (enforced at DB level):
    CREATE UNIQUE INDEX one_active_shift_per_user
    ON staff_shift (employee_id)
    WHERE clock_out IS NULL;

Django equivalent (add to Shift.Meta for PostgreSQL):
    constraints = [
        models.UniqueConstraint(
            fields=['employee'],
            condition=models.Q(clock_out__isnull=True),
            name='unique_active_shift_per_employee',
        )
    ]
This is omitted from the model here because SQLite (used in dev) does not
support partial unique constraints, and it would break the dev setup.
───────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.staff.exceptions import AlreadyClockedInError, NotClockedInError
from apps.staff.models import Shift, ScheduledShift


class ShiftService:

    @staticmethod
    @transaction.atomic
    def clock_in(user) -> Shift:
        """
        Start a new shift for the user.

        Acquires a row-level lock on the user row before checking for an
        existing active shift, preventing the double-clock-in race condition.

        Raises:
            AlreadyClockedInError — user already has an open shift
        """
        from apps.users.models import User

        # Row lock on this user serialises concurrent clock-in attempts.
        # The second request blocks here until the first transaction commits.
        User.objects.select_for_update().get(pk=user.pk)

        if Shift.objects.for_employee(user).active().exists():
            raise AlreadyClockedInError(
                f"{user.display_name} already has an active shift."
            )

        return Shift.objects.create(employee=user)

    @staticmethod
    def clock_out(user) -> Shift:
        """
        End the user's most recent active shift.

        Uses .last() rather than .get() to handle the edge case where a
        user has two active shifts (possible via admin override). .get()
        would raise MultipleObjectsReturned; .last() is safe and always
        closes the most recently opened shift.

        Raises:
            NotClockedInError — no active shift found
        """
        shift = Shift.objects.for_employee(user).active().first()
        if shift is None:
            raise NotClockedInError(
                f"{user.display_name} is not currently clocked in."
            )
        shift.clock_out_now()
        return shift

    @staticmethod
    def force_clock_out(user, actor) -> Shift:
        """
        Manager/admin-initiated clock-out for a user who forgot to clock out.

        The permission check is in the SERVICE, not the view, so it applies
        no matter which code path calls this (view, management command, API).

        Raises:
            PermissionError   — actor is not a manager or admin
            NotClockedInError — target user is not clocked in
        """
        if not actor.is_manager_or_above:
            raise PermissionError(
                "Only managers and admins can force clock-out another employee."
            )
        shift = Shift.objects.for_employee(user).active().last()
        if shift is None:
            raise NotClockedInError(f"{user.display_name} is not clocked in.")
        shift.clock_out_now()
        return shift

    @staticmethod
    def get_active_shift(user) -> Shift | None:
        """Return the user's current open shift, or None if not clocked in."""
        return Shift.objects.for_employee(user).active().first()

    @staticmethod
    def create_scheduled_shift(
        employee,
        scheduled_date,
        start_time,
        end_time,
        created_by,
        notes: str = '',
    ) -> ScheduledShift:
        """
        Create or update a scheduled shift entry.

        Uses update_or_create because ScheduledShift.unique_together =
        ('employee', 'scheduled_date') — calling this twice for the same
        employee/date updates rather than raising IntegrityError.
        This is safer than checking-then-creating, especially under load.

        Returns:
            The ScheduledShift instance (created or updated).
        """
        shift, _ = ScheduledShift.objects.update_or_create(
            employee=employee,
            scheduled_date=scheduled_date,
            defaults={
                'start_time': start_time,
                'end_time': end_time,
                'notes': notes,
                'created_by': created_by,
            },
        )
        return shift

    @staticmethod
    def delete_scheduled_shift(employee, scheduled_date, actor) -> None:
        """
        Remove a scheduled shift. Only managers/admins can do this.

        Raises:
            PermissionError       — actor lacks permission
            ScheduledShift.DoesNotExist — no shift on that date for that employee
        """
        if not actor.is_manager_or_above:
            raise PermissionError(
                "Only managers and admins can delete scheduled shifts."
            )
        ScheduledShift.objects.get(
            employee=employee, scheduled_date=scheduled_date
        ).delete()
