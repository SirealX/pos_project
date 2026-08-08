"""
Reports views: dashboard, sales aggregation, staff hours, CSV exports.

Architecture: all reporting logic lives here — views are thin wrappers
that call shared query helpers and pass results to templates.

WHY a separate reports app instead of adding views to sales/staff?
Sales and staff apps own their *domain* — transactions and attendance.
Reporting is a separate concern: it reads from multiple domains (sales
AND staff AND inventory) to produce cross-cutting summaries. Mixing it
into either domain app would create circular-dependency risk and blur
responsibility. A reports app is also the natural place for future
additions (inventory turnover, per-cashier performance, etc.).

WHY Python-level aggregation for staff hours instead of a pure ORM query?
Django's ORM can compute SUM/COUNT at the DB level but extracting a
duration between two DateTimeFields into decimal hours requires either:
  - PostgreSQL-specific: Extract('epoch', F('clock_out') - F('clock_in'))
  - SQLite-compatible: fetching the rows and computing in Python

Since the project supports SQLite for development, the Python-level
approach (_aggregate_hours) is used. It is fast enough for any
realistic shift log (thousands of rows), and the existing hours_worked
property on Shift already encapsulates the arithmetic correctly.

CSV EXPORTS
The CSV views share the exact same filtering logic as the HTML views via
module-level helpers (_build_sales_qs, _get_date_range, GROUP_BY_TRUNC).
No duplication, and the query is only constructed once per request.
"""
import csv
import datetime
from collections import defaultdict

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Avg, Count, Sum
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View

from apps.inventory.models import Product
from apps.mixins import ManagerRequiredMixin, manager_required
from apps.sales.models import Sale
from apps.staff.models import Shift

# Maps the ?group_by= query parameter to the Django ORM truncation function.
# Defined at module level so both the HTML view and CSV view share the mapping
# without a class reference.
GROUP_BY_TRUNC = {
    'day': TruncDate,
    'week': TruncWeek,
    'month': TruncMonth,
}


# ── Shared helpers ──────────────────────────────────────────────────────────────

def _get_date_range(request):
    """
    Parse ?start= and ?end= GET params into date objects.
    Defaults: start = first day of current month, end = today.
    Invalid or missing values fall back to defaults silently.
    """
    today = timezone.localdate()
    try:
        start = datetime.date.fromisoformat(request.GET.get('start', ''))
    except (ValueError, TypeError):
        start = today.replace(day=1)
    try:
        end = datetime.date.fromisoformat(request.GET.get('end', ''))
    except (ValueError, TypeError):
        end = today
    return start, end


def _build_sales_qs(start, end):
    """Base queryset: completed sales within the date range."""
    return Sale.objects.completed().filter(
        completed_at__date__gte=start,
        completed_at__date__lte=end,
    )


def _aggregate_hours(shifts):
    """
    Group a completed-shift queryset by employee and sum hours in Python.

    Returns a list of dicts sorted by display_name:
        [{'employee': User, 'shift_count': int, 'total_hours': float, 'avg_hours': float}]

    WHY in Python instead of pure ORM?
    Computing duration between two DateTimeFields as decimal hours requires
    database-specific expressions (PostgreSQL: Extract epoch; SQLite: no native
    support). Fetching rows and using the existing Shift.hours_worked property
    is correct, readable, and works across all supported backends.
    """
    by_employee: dict[int, dict] = defaultdict(lambda: {'employee': None, 'shifts': []})
    for shift in shifts:
        bucket = by_employee[shift.employee_id]
        bucket['employee'] = shift.employee
        bucket['shifts'].append(shift)

    results = []
    for data in by_employee.values():
        shift_list = data['shifts']
        total = sum(s.hours_worked for s in shift_list)
        count = len(shift_list)
        results.append({
            'employee': data['employee'],
            'shift_count': count,
            'total_hours': round(total, 2),
            'avg_hours': round(total / count, 2) if count else 0.0,
        })

    results.sort(key=lambda r: r['employee'].display_name)
    return results


# ── Dashboard ───────────────────────────────────────────────────────────────────

class DashboardView(LoginRequiredMixin, View):
    """
    At-a-glance metrics for the current business day.

    Visible to all authenticated users — staff see operational numbers
    (today's transactions, who is clocked in) that are relevant at the POS.
    Managers see the same plus revenue totals and inventory alerts.

    WHY not use TemplateView?
    get_context_data on TemplateView requires calling super() and unpacking
    kwargs. View.get() is cleaner when the whole method is custom logic
    with no standard CRUD lifecycle.
    """
    template_name = 'reports/dashboard.html'

    def get(self, request):
        today = timezone.localdate()
        week_start = today - datetime.timedelta(days=today.weekday())  # Monday
        month_start = today.replace(day=1)

        completed = Sale.objects.completed()

        today_stats = completed.filter(
            completed_at__date=today
        ).aggregate(count=Count('id'), revenue=Sum('total_amount'))

        week_stats = completed.filter(
            completed_at__date__gte=week_start
        ).aggregate(revenue=Sum('total_amount'))

        month_stats = completed.filter(
            completed_at__date__gte=month_start
        ).aggregate(revenue=Sum('total_amount'))

        return render(request, self.template_name, {
            'today': today,
            'today_count': today_stats['count'] or 0,
            'today_revenue': today_stats['revenue'] or 0,
            'week_revenue': week_stats['revenue'] or 0,
            'month_revenue': month_stats['revenue'] or 0,
            'active_staff': (
                Shift.objects.active()
                .select_related('employee')
                .order_by('clock_in')
            ),
            'low_stock_count': Product.objects.low_stock().count(),
            'recent_sales': (
                completed
                .select_related('cashier')
                .order_by('-completed_at')[:5]
            ),
        })


# ── Sales report ────────────────────────────────────────────────────────────────

class SalesReportView(ManagerRequiredMixin, View):
    """
    Aggregated sales report grouped by day, week, or month.

    The TruncDate/TruncWeek/TruncMonth functions collapse individual sale
    timestamps into period buckets. Django evaluates this as a single SQL
    GROUP BY query — no Python-level looping over sale rows.

    Example query generated for group_by=day:
        SELECT DATE(completed_at) AS period,
               COUNT(id) AS count,
               SUM(total_amount) AS revenue,
               AVG(total_amount) AS avg_sale
        FROM sales_sale
        WHERE status='COMPLETED'
          AND DATE(completed_at) BETWEEN %s AND %s
        GROUP BY period
        ORDER BY period
    """
    template_name = 'reports/sales_report.html'

    def get(self, request):
        start, end = _get_date_range(request)
        group_by = request.GET.get('group_by', 'day')
        TruncFn = GROUP_BY_TRUNC.get(group_by, TruncDate)

        qs = _build_sales_qs(start, end)

        rows = (
            qs.annotate(period=TruncFn('completed_at'))
            .values('period')
            .annotate(
                count=Count('id'),
                revenue=Sum('total_amount'),
                avg_sale=Avg('total_amount'),
            )
            .order_by('period')
        )

        totals = qs.aggregate(
            total_count=Count('id'),
            total_revenue=Sum('total_amount'),
            avg_sale=Avg('total_amount'),
        )

        return render(request, self.template_name, {
            'rows': rows,
            'totals': totals,
            'start': start,
            'end': end,
            'group_by': group_by,
        })


@manager_required
def sales_report_csv(request):
    """Download the current sales report filter as a CSV file."""
    start, end = _get_date_range(request)
    group_by = request.GET.get('group_by', 'day')
    TruncFn = GROUP_BY_TRUNC.get(group_by, TruncDate)

    rows = (
        _build_sales_qs(start, end)
        .annotate(period=TruncFn('completed_at'))
        .values('period')
        .annotate(
            count=Count('id'),
            revenue=Sum('total_amount'),
            avg_sale=Avg('total_amount'),
        )
        .order_by('period')
    )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = (
        f'attachment; filename="sales_report_{start}_{end}.csv"'
    )
    writer = csv.writer(response)
    writer.writerow(['Period', 'Transactions', 'Revenue ($)', 'Avg Sale ($)'])
    for row in rows:
        # TruncDate/Week/Month return datetime objects; .date() gives a date.
        period = row['period'].date() if hasattr(row['period'], 'date') else row['period']
        writer.writerow([
            period,
            row['count'],
            f"{row['revenue']:.2f}",
            f"{row['avg_sale']:.2f}" if row['avg_sale'] else '0.00',
        ])
    return response


# ── Staff hours report ──────────────────────────────────────────────────────────

class StaffHoursReportView(ManagerRequiredMixin, View):
    """
    Per-employee hours summary for a date range.

    Useful for payroll: shows total hours worked, number of shifts, and
    average hours per shift for each employee in the selected period.
    """
    template_name = 'reports/staff_hours_report.html'

    def get(self, request):
        start, end = _get_date_range(request)

        shifts = (
            Shift.objects.completed()
            .filter(clock_in__date__gte=start, clock_in__date__lte=end)
            .select_related('employee')
            .order_by('employee__last_name', 'employee__first_name', 'clock_in')
        )

        results = _aggregate_hours(shifts)

        return render(request, self.template_name, {
            'results': results,
            'start': start,
            'end': end,
            'grand_total_hours': sum(r['total_hours'] for r in results),
            'grand_total_shifts': sum(r['shift_count'] for r in results),
        })


@manager_required
def staff_hours_csv(request):
    """Download the current staff hours filter as a CSV file."""
    start, end = _get_date_range(request)

    shifts = (
        Shift.objects.completed()
        .filter(clock_in__date__gte=start, clock_in__date__lte=end)
        .select_related('employee')
        .order_by('employee__last_name', 'employee__first_name', 'clock_in')
    )
    results = _aggregate_hours(shifts)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = (
        f'attachment; filename="staff_hours_{start}_{end}.csv"'
    )
    writer = csv.writer(response)
    writer.writerow(['Employee', 'Shifts', 'Total Hours', 'Avg Hours/Shift'])
    for r in results:
        writer.writerow([
            r['employee'].display_name,
            r['shift_count'],
            r['total_hours'],
            r['avg_hours'],
        ])
    return response
