"""
Custom User model for the POS system.

WHY a custom user model?
Django's docs say to always swap in a custom user model at the start of a
project, even if you don't need extra fields yet.  Once you have real
migrations it is very painful to switch.  Doing it now costs nothing.

WHY role on the User vs a separate profile model?
Cesar's project has a separate Employee model with a OneToOneField.  That
works, but it means every permission check requires a JOIN:
    user.employee.position == 'manager'
With role on User directly, permission checks are a single attribute read
with zero DB queries, and you can filter by role efficiently with an index.
"""
from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import UserManager


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Admin'
        MANAGER = 'MANAGER', 'Manager'
        STAFF = 'STAFF', 'Staff'

    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.STAFF,
        db_index=True,
    )
    phone = models.CharField(max_length=20, blank=True)
    # Hourly rate lives here so we can compute wage cost in shift reports
    # without a JOIN to a separate profile table.
    hourly_rate = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    objects = UserManager()

    class Meta:
        ordering = ['first_name', 'last_name']
        verbose_name = 'user'
        verbose_name_plural = 'users'

    def __str__(self):
        full_name = self.get_full_name()
        return f"{full_name or self.username} ({self.get_role_display()})"

    # ------------------------------------------------------------------
    # Role helpers — use these in views and templates instead of raw
    # string comparisons so a typo raises AttributeError, not silent pass.
    # ------------------------------------------------------------------

    @property
    def is_admin(self) -> bool:
        return self.role == self.Role.ADMIN

    @property
    def is_manager_or_above(self) -> bool:
        return self.role in (self.Role.ADMIN, self.Role.MANAGER)

    @property
    def display_name(self) -> str:
        return self.get_full_name() or self.username
