from django.contrib.auth.models import BaseUserManager


class UserManager(BaseUserManager):
    """
    Custom manager required whenever you extend AbstractUser, so that
    `create_superuser` populates the custom `role` field correctly.

    We also expose queryset helpers here (managers_and_above, active_staff)
    so views can call User.objects.managers_and_above() instead of repeating
    the filter logic everywhere.
    """

    def create_user(self, username, password=None, **extra_fields):
        extra_fields.setdefault('role', self.model.Role.STAFF)
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault('role', self.model.Role.ADMIN)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(username, password, **extra_fields)

    def managers_and_above(self):
        return self.filter(role__in=[self.model.Role.ADMIN, self.model.Role.MANAGER])

    def active_staff(self):
        return self.filter(is_active=True)
