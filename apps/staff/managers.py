from django.db import models
from django.utils import timezone


class ShiftQuerySet(models.QuerySet):
    def active(self):
        """Shifts currently in progress (clocked in, not yet out)."""
        return self.filter(clock_out__isnull=True)

    def completed(self):
        """Shifts with a clock-out time recorded."""
        return self.filter(clock_out__isnull=False)

    def today(self):
        return self.filter(clock_in__date=timezone.now().date())

    def for_employee(self, user):
        return self.filter(employee=user)

    def by_date_range(self, start, end):
        return self.filter(clock_in__date__gte=start, clock_in__date__lte=end)

    def approved(self):
        return self.filter(is_approved=True)

    def unapproved(self):
        return self.filter(is_approved=False)


class ShiftManager(models.Manager):
    def get_queryset(self):
        return ShiftQuerySet(self.model, using=self._db)

    def active(self):
        return self.get_queryset().active()

    def completed(self):
        return self.get_queryset().completed()

    def today(self):
        return self.get_queryset().today()

    def for_employee(self, user):
        return self.get_queryset().for_employee(user)

    def by_date_range(self, start, end):
        return self.get_queryset().by_date_range(start, end)


class ScheduledShiftQuerySet(models.QuerySet):
    def upcoming(self):
        return self.filter(scheduled_date__gte=timezone.now().date())

    def for_employee(self, user):
        return self.filter(employee=user)


class ScheduledShiftManager(models.Manager):
    def get_queryset(self):
        return ScheduledShiftQuerySet(self.model, using=self._db)

    def upcoming(self):
        return self.get_queryset().upcoming()

    def for_employee(self, user):
        return self.get_queryset().for_employee(user)
