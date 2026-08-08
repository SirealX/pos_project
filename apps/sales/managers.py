from django.db import models
from django.utils import timezone


class SaleQuerySet(models.QuerySet):
    """
    Chainable queryset for Sale.

    String literals ('COMPLETED' etc.) are used instead of importing
    Sale.Status to avoid a circular import (models.py imports this file).
    The values are identical — TextChoices stores the first tuple element.
    """

    def completed(self):
        return self.filter(status='COMPLETED')

    def pending(self):
        return self.filter(status='PENDING')

    def voided(self):
        return self.filter(status='VOIDED')

    def today(self):
        return self.filter(created_at__date=timezone.now().date())

    def for_cashier(self, user):
        return self.filter(cashier=user)

    def by_date_range(self, start, end):
        """Filter by inclusive date range (date objects, not datetimes)."""
        return self.filter(created_at__date__gte=start, created_at__date__lte=end)


class SaleManager(models.Manager):
    def get_queryset(self):
        return SaleQuerySet(self.model, using=self._db)

    def completed(self):
        return self.get_queryset().completed()

    def today(self):
        return self.get_queryset().today()

    def by_date_range(self, start, end):
        return self.get_queryset().by_date_range(start, end)
