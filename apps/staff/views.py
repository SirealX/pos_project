"""
Staff views: shift log, schedule management, manager force clock-out.

View responsibilities:
─────────────────────────────────────────────────────────────────────────────
ShiftLogView    — paginated list of shifts. Staff see their own; managers see
                  all employees. Accepts ?start=YYYY-MM-DD&end=YYYY-MM-DD for
                  date-range filtering (useful for payroll week views).

ScheduleListView — upcoming scheduled shifts. Staff see only their own.
                   Managers see everyone (and get a link to create new entries).

ScheduleCreateView / ScheduleUpdateView / ScheduleDeleteView
                — Manager-only CRUD for ScheduledShift. Uses
                  ShiftService.create_scheduled_shift() on create/update so
                  the unique_together constraint is handled gracefully
                  (update_or_create vs IntegrityError).

force_clock_out — Manager POST endpoint to close a forgotten active shift.
                  Returns HTMX partial if the request came from HTMX;
                  otherwise redirects to the shift log.

WHY FBV for force_clock_out instead of a CBV?
Same reason as cart actions in sales — it's a mutation-only POST that doesn't
map to a standard CRUD lifecycle. One decorator stack + one service call is
cleaner than a FormView or custom View with empty get().
─────────────────────────────────────────────────────────────────────────────
"""
import datetime

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, UpdateView
from django.urls import reverse_lazy

from apps.mixins import ManagerRequiredMixin

from .exceptions import NotClockedInError
from .forms import ScheduledShiftForm
from .models import ScheduledShift, Shift
from .services import ShiftService

User = get_user_model()


# ── Shift log ──────────────────────────────────────────────────────────────────

class ShiftLogView(LoginRequiredMixin, ListView):
    """
    Paginated shift history.

    Staff see only their own shifts. Managers see all employees.
    Optional GET params: ?start=YYYY-MM-DD&end=YYYY-MM-DD
    """
    template_name = 'staff/shift_log.html'
    context_object_name = 'shifts'
    paginate_by = 25

    def get_queryset(self):
        qs = (
            Shift.objects
            .select_related('employee', 'approved_by')
            .order_by('-clock_in')
        )

        if not self.request.user.is_manager_or_above:
            qs = qs.for_employee(self.request.user)

        start = self._parse_date(self.request.GET.get('start'))
        end = self._parse_date(self.request.GET.get('end'))
        if start:
            qs = qs.filter(clock_in__date__gte=start)
        if end:
            qs = qs.filter(clock_in__date__lte=end)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['start'] = self.request.GET.get('start', '')
        ctx['end'] = self.request.GET.get('end', '')
        if self.request.user.is_manager_or_above:
            # Show active shifts at the top of the manager view
            ctx['active_shifts'] = (
                Shift.objects.active()
                .select_related('employee')
                .order_by('clock_in')
            )
        return ctx

    @staticmethod
    def _parse_date(value):
        if not value:
            return None
        try:
            return datetime.date.fromisoformat(value)
        except (ValueError, TypeError):
            return None


# ── Schedule ───────────────────────────────────────────────────────────────────

class ScheduleListView(LoginRequiredMixin, ListView):
    """
    Upcoming scheduled shifts.

    Staff see their own schedule. Managers see everyone's and can
    create new entries via the link in the template.
    """
    template_name = 'staff/schedule_list.html'
    context_object_name = 'scheduled_shifts'

    def get_queryset(self):
        qs = (
            ScheduledShift.objects
            .upcoming()
            .select_related('employee', 'created_by')
        )
        if not self.request.user.is_manager_or_above:
            qs = qs.for_employee(self.request.user)
        return qs


class ScheduleCreateView(ManagerRequiredMixin, CreateView):
    model = ScheduledShift
    form_class = ScheduledShiftForm
    template_name = 'staff/schedule_form.html'
    success_url = reverse_lazy('staff:schedule-list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['action'] = 'Create Schedule'
        return ctx

    def form_valid(self, form):
        # Delegate to service so update_or_create handles unique_together gracefully
        cd = form.cleaned_data
        ShiftService.create_scheduled_shift(
            employee=cd['employee'],
            scheduled_date=cd['scheduled_date'],
            start_time=cd['start_time'],
            end_time=cd['end_time'],
            created_by=self.request.user,
            notes=cd.get('notes', ''),
        )
        messages.success(
            self.request,
            f"Schedule saved for {cd['employee'].display_name} on {cd['scheduled_date']}.",
        )
        return redirect(self.success_url)


class ScheduleUpdateView(ManagerRequiredMixin, UpdateView):
    model = ScheduledShift
    form_class = ScheduledShiftForm
    template_name = 'staff/schedule_form.html'
    success_url = reverse_lazy('staff:schedule-list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['action'] = 'Edit Schedule'
        return ctx

    def form_valid(self, form):
        cd = form.cleaned_data
        ShiftService.create_scheduled_shift(
            employee=cd['employee'],
            scheduled_date=cd['scheduled_date'],
            start_time=cd['start_time'],
            end_time=cd['end_time'],
            created_by=self.request.user,
            notes=cd.get('notes', ''),
        )
        messages.success(
            self.request,
            f"Schedule updated for {cd['employee'].display_name} on {cd['scheduled_date']}.",
        )
        return redirect(self.success_url)


class ScheduleDeleteView(ManagerRequiredMixin, DeleteView):
    model = ScheduledShift
    template_name = 'staff/schedule_confirm_delete.html'
    success_url = reverse_lazy('staff:schedule-list')
    context_object_name = 'scheduled_shift'

    def form_valid(self, form):
        obj = self.get_object()
        name = obj.employee.display_name
        date = obj.scheduled_date
        result = super().form_valid(form)
        messages.success(self.request, f"Schedule for {name} on {date} deleted.")
        return result


# ── Force clock-out (manager action) ──────────────────────────────────────────

@require_POST
@login_required
def force_clock_out(request, user_id):
    """
    Manager-initiated clock-out for a user who forgot to clock out.

    Permission is checked inside ShiftService.force_clock_out() so the
    rule is enforced even if called from other entry points (API, command).
    The view just handles the HTTP layer.
    """
    target_user = get_object_or_404(User, pk=user_id, is_active=True)
    try:
        shift = ShiftService.force_clock_out(user=target_user, actor=request.user)
        messages.success(
            request,
            f"{target_user.display_name} clocked out. "
            f"Shift duration: {shift.hours_worked:.2f}h",
        )
    except PermissionError as exc:
        messages.error(request, str(exc))
    except NotClockedInError as exc:
        messages.error(request, str(exc))

    return redirect('staff:shift-log')
