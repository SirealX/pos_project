from django.contrib.auth.forms import UserCreationForm as BaseUserCreationForm
from django import forms

from .models import User


class UserCreateForm(BaseUserCreationForm):
    """
    Extends Django's built-in UserCreationForm to add our custom fields.

    WHY extend the base form?
    BaseUserCreationForm already handles password hashing, password-confirm
    matching, and username uniqueness validation. Extending it means we get
    all of that for free — we only need to declare the extra fields.
    """
    class Meta(BaseUserCreationForm.Meta):
        model = User
        fields = (
            'username', 'first_name', 'last_name', 'email',
            'role', 'phone', 'hourly_rate',
        )


class UserUpdateForm(forms.ModelForm):
    """
    Update an existing user's profile, role, and active status.
    Excludes password — use Django's built-in password change flow for that.
    """
    class Meta:
        model = User
        fields = (
            'username', 'first_name', 'last_name', 'email',
            'role', 'phone', 'hourly_rate', 'is_active',
        )
