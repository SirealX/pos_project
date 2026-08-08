"""
User management views and custom auth views.

Key differences from Cesar's implementation:
─────────────────────────────────────────────────────────────────────────────
1. Clock-in/out is delegated to ShiftService — the view doesn't know HOW
   it works, only WHAT to do with the result (success / exception → message).

2. CustomLogoutView overrides dispatch() so clock-out fires BEFORE
   logout() clears request.user. Cesar's approach is the same but tied to
   the view; here the service owns the logic.

3. User CRUD is protected by AdminRequiredMixin (role=ADMIN) rather than
   @staff_member_required (Django's internal is_staff flag). This means
   you can have a POS Admin who manages users without giving them full
   Django Admin access (is_staff=True).
─────────────────────────────────────────────────────────────────────────────
"""
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.mixins import AdminRequiredMixin, ManagerRequiredMixin
from apps.staff.exceptions import AlreadyClockedInError, NotClockedInError
from apps.staff.services import ShiftService

from .forms import UserCreateForm, UserUpdateForm

User = get_user_model()


# ── Authentication ─────────────────────────────────────────────────────────────

class CustomLoginView(LoginView):
    """
    Extends LoginView to auto-clock-in the user on successful login.

    WHY override form_valid and NOT get_success_url?
    get_success_url is only called after the response is built. By overriding
    form_valid, we can perform side effects (clock-in) BEFORE the response
    is constructed, and still leverage Django's redirect logic normally.

    redirect_authenticated_user=True: sending an already-logged-in user to
    /login/ bounces them straight to LOGIN_REDIRECT_URL — no double render.
    """
    template_name = 'users/login.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        # super() calls auth.login(), which sets request.user.
        # After this line, self.request.user is the newly logged-in user.
        response = super().form_valid(form)
        user = self.request.user
        try:
            ShiftService.clock_in(user)
            messages.success(
                self.request,
                f"Welcome, {user.display_name}! You have been clocked in.",
            )
        except AlreadyClockedInError:
            # Already clocked in (e.g. session restored, or second tab login)
            messages.info(self.request, f"Welcome back, {user.display_name}!")
        return response


class CustomLogoutView(LogoutView):
    """
    Extends LogoutView to auto-clock-out the user.

    WHY override dispatch and not post?
    dispatch() is called before post(). post() calls logout(request) which
    clears request.user. We need request.user to still be set when we call
    ShiftService.clock_out(), so dispatch() is the correct hook.
    """
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            try:
                shift = ShiftService.clock_out(request.user)
                messages.info(
                    request,
                    f"Goodbye, {request.user.display_name}! "
                    f"Shift: {shift.hours_worked:.2f}h",
                )
            except NotClockedInError:
                messages.info(request, f"Goodbye, {request.user.display_name}!")
        return super().dispatch(request, *args, **kwargs)


# ── User management (Admin only) ───────────────────────────────────────────────

class UserListView(ManagerRequiredMixin, ListView):
    """
    List all users. Readable by managers (to see who is on staff),
    but create/update/delete requires Admin role.
    """
    model = User
    template_name = 'users/user_list.html'
    context_object_name = 'users'

    def get_queryset(self):
        return User.objects.active_staff().order_by('role', 'first_name', 'last_name')


class UserCreateView(AdminRequiredMixin, CreateView):
    model = User
    form_class = UserCreateForm
    template_name = 'users/user_form.html'
    success_url = reverse_lazy('users:list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['action'] = 'Create'
        return ctx

    def form_valid(self, form):
        messages.success(self.request, f"User '{form.instance.username}' created.")
        return super().form_valid(form)


class UserUpdateView(AdminRequiredMixin, UpdateView):
    model = User
    form_class = UserUpdateForm
    template_name = 'users/user_form.html'
    success_url = reverse_lazy('users:list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['action'] = 'Update'
        return ctx

    def form_valid(self, form):
        messages.success(self.request, f"User '{form.instance.username}' updated.")
        return super().form_valid(form)


class UserDeleteView(AdminRequiredMixin, DeleteView):
    model = User
    template_name = 'users/user_confirm_delete.html'
    success_url = reverse_lazy('users:list')

    def form_valid(self, form):
        username = self.get_object().username
        result = super().form_valid(form)
        messages.success(self.request, f"User '{username}' deleted.")
        return result

    def get_queryset(self):
        # Prevent admins from deleting themselves
        return User.objects.exclude(pk=self.request.user.pk)
