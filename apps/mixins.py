"""
Reusable permission mixins and decorators for the POS system.

WHY NOT just use @staff_member_required / is_staff?
─────────────────────────────────────────────────────────────────────────────
Cesar's code uses @staff_member_required and user.is_superuser checks. This
conflates Django's internal is_staff / is_superuser flags with our application
roles (Admin, Manager, Staff).

Problems:
- is_staff=True is required to access Django Admin, but that doesn't mean
  the person is a "manager" in POS terms.
- is_superuser conflates "Django superuser" with "POS Admin".
- There's no middle tier: everyone is either staff (can do everything) or
  superuser (can do everything + more).
- Changing the role hierarchy means editing every decorator call site.

This module's approach: role-based mixins built on UserPassesTestMixin.
- test_func() checks user.is_manager_or_above (a property on our custom User)
- handle_no_permission() gives a flash message + redirect instead of a 403 page
- A single FBV decorator (@manager_required) mirrors the CBV mixin behaviour
─────────────────────────────────────────────────────────────────────────────
"""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import redirect


# ── CBV mixins ────────────────────────────────────────────────────────────────

class ManagerRequiredMixin(UserPassesTestMixin):
    """Allow access only to users with role MANAGER or ADMIN."""

    def test_func(self):
        return (
            self.request.user.is_authenticated
            and self.request.user.is_manager_or_above
        )

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            # Let Django's default behaviour redirect to login
            return super().handle_no_permission()
        messages.error(self.request, "Manager access required.")
        return redirect("sales:pos")


class AdminRequiredMixin(UserPassesTestMixin):
    """Allow access only to users with role ADMIN."""

    def test_func(self):
        return (
            self.request.user.is_authenticated
            and self.request.user.is_admin
        )

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.error(self.request, "Admin access required.")
        return redirect("sales:pos")


# ── FBV decorators ────────────────────────────────────────────────────────────

def manager_required(view_func):
    """
    FBV equivalent of ManagerRequiredMixin.

    Usage:
        @manager_required
        def my_view(request): ...

    Redirects unauthenticated users to login and non-managers to the POS
    with an error message — matches ManagerRequiredMixin behaviour exactly.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("users:login")
        if not request.user.is_manager_or_above:
            messages.error(request, "Manager access required.")
            return redirect("sales:pos")
        return view_func(request, *args, **kwargs)
    return wrapper
