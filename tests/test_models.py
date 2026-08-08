"""
Model and QuerySet tests.

These tests verify:
  - Custom QuerySet filter methods return exactly the right rows
  - Model properties compute correct values
  - Model methods perform correct state transitions
  - Denormalised fields (line_total, completed_at) stay in sync

WHY test QuerySets separately from service tests?
Services use QuerySets, but a service test that fails doesn't tell you
whether the bug is in the service logic or the queryset filter. Dedicated
queryset tests isolate each filter so the root cause is always clear.
"""
import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.inventory.models import Product
from apps.sales.models import Sale, SaleLineItem
from apps.staff.models import Shift

from .factories import (
    CategoryFactory,
    CompletedShiftFactory,
    ManagerFactory,
    ProductFactory,
    SaleFactory,
    SaleLineItemFactory,
    UserFactory,
)


# ── Product QuerySet ──────────────────────────────────────────────────────────────

class TestProductQuerySet:
    @pytest.mark.django_db
    def test_active_excludes_inactive_products(self):
        active = ProductFactory(is_active=True)
        inactive = ProductFactory(is_active=False)

        qs = Product.objects.active()

        assert active in qs
        assert inactive not in qs

    @pytest.mark.django_db
    def test_in_stock_excludes_zero_stock(self):
        stocked = ProductFactory(stock_quantity=5)
        empty = ProductFactory(stock_quantity=0)

        qs = Product.objects.in_stock()

        assert stocked in qs
        assert empty not in qs

    @pytest.mark.django_db
    def test_in_stock_excludes_inactive_products(self):
        # in_stock() chains .active() — inactive products must be excluded
        # even if they have stock_quantity > 0
        inactive_with_stock = ProductFactory(is_active=False, stock_quantity=10)

        qs = Product.objects.in_stock()

        assert inactive_with_stock not in qs

    @pytest.mark.django_db
    def test_low_stock_uses_per_product_threshold(self):
        """
        Each product has its own low_stock_threshold — not a global constant.
        A product with stock=5 is low if its threshold is 10, but fine if 3.
        """
        low = ProductFactory(stock_quantity=5, low_stock_threshold=10)
        fine = ProductFactory(stock_quantity=5, low_stock_threshold=3)

        qs = Product.objects.low_stock()

        assert low in qs
        assert fine not in qs

    @pytest.mark.django_db
    def test_low_stock_includes_product_exactly_at_threshold(self):
        at_threshold = ProductFactory(stock_quantity=10, low_stock_threshold=10)
        one_above = ProductFactory(stock_quantity=11, low_stock_threshold=10)

        qs = Product.objects.low_stock()

        assert at_threshold in qs
        assert one_above not in qs

    @pytest.mark.django_db
    def test_out_of_stock_returns_only_empty_products(self):
        empty = ProductFactory(stock_quantity=0)
        stocked = ProductFactory(stock_quantity=1)

        qs = Product.objects.out_of_stock()

        assert empty in qs
        assert stocked not in qs


# ── Product model properties ──────────────────────────────────────────────────────

class TestProductProperties:
    @pytest.mark.django_db
    def test_is_low_stock_true_at_threshold(self):
        p = ProductFactory(stock_quantity=5, low_stock_threshold=5)
        assert p.is_low_stock is True

    @pytest.mark.django_db
    def test_is_low_stock_false_above_threshold(self):
        p = ProductFactory(stock_quantity=6, low_stock_threshold=5)
        assert p.is_low_stock is False

    @pytest.mark.django_db
    def test_is_out_of_stock_true_when_zero(self):
        p = ProductFactory(stock_quantity=0)
        assert p.is_out_of_stock is True

    @pytest.mark.django_db
    def test_gross_margin_calculation(self):
        p = ProductFactory(price=Decimal('10.00'), cost=Decimal('4.00'))
        # (10 - 4) / 10 * 100 = 60.0%
        assert p.gross_margin == 60.0

    def test_gross_margin_zero_when_no_price(self):
        p = Product(price=Decimal('0'), cost=Decimal('0'))
        assert p.gross_margin == 0.0


# ── Sale QuerySet ─────────────────────────────────────────────────────────────────

class TestSaleQuerySet:
    @pytest.mark.django_db
    def test_completed_returns_only_completed_sales(self):
        completed = SaleFactory(status=Sale.Status.COMPLETED)
        pending = SaleFactory(status=Sale.Status.PENDING)
        voided = SaleFactory(status=Sale.Status.VOIDED)

        qs = Sale.objects.completed()

        assert completed in qs
        assert pending not in qs
        assert voided not in qs

    @pytest.mark.django_db
    def test_for_cashier_returns_only_that_cashiers_sales(self):
        cashier = UserFactory()
        other = UserFactory()
        own_sale = SaleFactory(cashier=cashier)
        other_sale = SaleFactory(cashier=other)

        qs = Sale.objects.completed().for_cashier(cashier)

        assert own_sale in qs
        assert other_sale not in qs

    @pytest.mark.django_db
    def test_queryset_methods_are_chainable(self):
        cashier = UserFactory()
        SaleFactory(cashier=cashier, status=Sale.Status.COMPLETED)

        # Chain should return a queryset, not raise
        qs = Sale.objects.completed().select_related('cashier').for_cashier(cashier)
        assert list(qs)  # evaluates without error


# ── Sale model methods ────────────────────────────────────────────────────────────

class TestSaleModel:
    @pytest.mark.django_db
    def test_mark_completed_sets_status_and_timestamp(self):
        sale = SaleFactory(status=Sale.Status.PENDING, completed_at=None)

        sale.mark_completed()

        sale.refresh_from_db()
        assert sale.status == Sale.Status.COMPLETED
        assert sale.completed_at is not None

    @pytest.mark.django_db
    def test_void_sets_status_to_voided(self):
        sale = SaleFactory(status=Sale.Status.COMPLETED)

        sale.void()

        sale.refresh_from_db()
        assert sale.status == Sale.Status.VOIDED


# ── SaleLineItem auto-computed field ─────────────────────────────────────────────

class TestSaleLineItem:
    @pytest.mark.django_db
    def test_save_computes_line_total_automatically(self):
        sale = SaleFactory()
        product = ProductFactory()

        item = SaleLineItem.objects.create(
            sale=sale,
            product=product,
            quantity=3,
            unit_price=Decimal('7.50'),
            line_total=Decimal('0'),  # intentionally wrong — save() corrects it
        )

        assert item.line_total == Decimal('22.50')

    @pytest.mark.django_db
    def test_line_total_updates_on_re_save(self):
        sale = SaleFactory()
        product = ProductFactory()
        item = SaleLineItem.objects.create(
            sale=sale, product=product,
            quantity=2, unit_price=Decimal('5.00'), line_total=Decimal('10.00'),
        )

        item.quantity = 4
        item.save()

        assert item.line_total == Decimal('20.00')


# ── Shift model ───────────────────────────────────────────────────────────────────

class TestShiftModel:
    def test_is_active_true_when_no_clock_out(self):
        from apps.staff.models import Shift as ShiftModel
        shift = ShiftModel(clock_in=timezone.now(), clock_out=None)
        assert shift.is_active is True

    @pytest.mark.django_db
    def test_is_active_false_when_clocked_out(self):
        shift = CompletedShiftFactory()
        assert shift.is_active is False

    @pytest.mark.django_db
    def test_hours_worked_for_completed_shift(self):
        now = timezone.now()
        shift = CompletedShiftFactory(
            clock_in=now - datetime.timedelta(hours=8),
            clock_out=now,
        )
        assert shift.hours_worked == pytest.approx(8.0, abs=0.01)

    @pytest.mark.django_db
    def test_clock_out_now_sets_clock_out(self):
        from apps.staff.models import Shift as ShiftModel
        user = UserFactory()
        shift = ShiftModel.objects.create(employee=user)

        shift.clock_out_now()

        shift.refresh_from_db()
        assert shift.clock_out is not None


# ── Shift QuerySet ────────────────────────────────────────────────────────────────

class TestShiftQuerySet:
    @pytest.mark.django_db
    def test_active_returns_only_open_shifts(self):
        from .factories import ActiveShiftFactory
        active = ActiveShiftFactory()
        completed = CompletedShiftFactory()

        qs = Shift.objects.active()

        assert active in qs
        assert completed not in qs

    @pytest.mark.django_db
    def test_completed_returns_only_closed_shifts(self):
        from .factories import ActiveShiftFactory
        active = ActiveShiftFactory()
        completed = CompletedShiftFactory()

        qs = Shift.objects.completed()

        assert completed in qs
        assert active not in qs

    @pytest.mark.django_db
    def test_for_employee_filters_by_user(self):
        user = UserFactory()
        other = UserFactory()
        own_shift = CompletedShiftFactory(employee=user)
        other_shift = CompletedShiftFactory(employee=other)

        qs = Shift.objects.for_employee(user)

        assert own_shift in qs
        assert other_shift not in qs


# ── User model ────────────────────────────────────────────────────────────────────

class TestUserModel:
    @pytest.mark.django_db
    def test_is_admin_true_only_for_admin_role(self):
        admin = UserFactory(role='ADMIN')
        manager = UserFactory(role='MANAGER')
        staff = UserFactory(role='STAFF')

        assert admin.is_admin is True
        assert manager.is_admin is False
        assert staff.is_admin is False

    @pytest.mark.django_db
    def test_is_manager_or_above_includes_manager_and_admin(self):
        admin = UserFactory(role='ADMIN')
        manager = UserFactory(role='MANAGER')
        staff = UserFactory(role='STAFF')

        assert admin.is_manager_or_above is True
        assert manager.is_manager_or_above is True
        assert staff.is_manager_or_above is False

    @pytest.mark.django_db
    def test_display_name_returns_full_name_when_available(self):
        user = UserFactory(first_name='Jane', last_name='Doe', username='jdoe')
        assert user.display_name == 'Jane Doe'

    @pytest.mark.django_db
    def test_display_name_falls_back_to_username(self):
        user = UserFactory(first_name='', last_name='', username='cashier1')
        assert user.display_name == 'cashier1'
