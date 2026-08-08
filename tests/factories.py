"""
factory_boy factories for all domain models.

DESIGN NOTES
────────────────────────────────────────────────────────────────────────────
1. UserFactory uses _create() to route through create_user() so the password
   is always hashed. Calling User.objects.create(**kwargs) directly stores the
   password in plaintext and breaks client.login().

2. Sequence() gives each factory call a unique, deterministic value for fields
   with unique constraints (username, sku, category name). This eliminates
   IntegrityError collisions when many tests run in the same transaction.

3. Decimal fields use string literals ('10.00') — Decimal(float) can introduce
   floating-point imprecision that causes assertion mismatches in money tests.

4. Sub-factories (SubFactory) create related objects lazily on first use.
   Passing an explicit instance overrides the sub-factory entirely, which is
   the cleanest way to share objects between factories in a single test.
"""
from decimal import Decimal

import factory
from django.contrib.auth import get_user_model
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.inventory.models import Category, Product
from apps.sales.models import Sale, SaleLineItem
from apps.staff.models import Shift, ScheduledShift

User = get_user_model()


# ── Users ───────────────────────────────────────────────────────────────────────

class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f'user{n}')
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    email = factory.LazyAttribute(lambda o: f'{o.username}@example.com')
    password = 'testpass123'
    role = User.Role.STAFF
    is_active = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        # Route through create_user() so Django hashes the password.
        return model_class.objects.create_user(
            username=kwargs.pop('username'),
            password=kwargs.pop('password', 'testpass123'),
            **kwargs,
        )


class ManagerFactory(UserFactory):
    role = User.Role.MANAGER


class AdminFactory(UserFactory):
    role = User.Role.ADMIN


# ── Inventory ───────────────────────────────────────────────────────────────────

class CategoryFactory(DjangoModelFactory):
    class Meta:
        model = Category

    name = factory.Sequence(lambda n: f'Category {n}')
    is_active = True


class ProductFactory(DjangoModelFactory):
    class Meta:
        model = Product

    category = factory.SubFactory(CategoryFactory)
    name = factory.Sequence(lambda n: f'Product {n}')
    sku = factory.Sequence(lambda n: f'SKU{n:06d}')
    price = Decimal('10.00')
    cost = Decimal('4.00')
    stock_quantity = 100
    low_stock_threshold = 10
    is_active = True


# ── Sales ────────────────────────────────────────────────────────────────────────

class SaleFactory(DjangoModelFactory):
    class Meta:
        model = Sale

    cashier = factory.SubFactory(UserFactory)
    status = Sale.Status.COMPLETED
    payment_method = Sale.PaymentMethod.CASH
    subtotal = Decimal('10.00')
    tax_rate = Decimal('0.0000')
    tax_amount = Decimal('0.00')
    total_amount = Decimal('10.00')
    amount_tendered = Decimal('10.00')
    change_due = Decimal('0.00')


class SaleLineItemFactory(DjangoModelFactory):
    class Meta:
        model = SaleLineItem

    sale = factory.SubFactory(SaleFactory)
    product = factory.SubFactory(ProductFactory)
    quantity = 1
    unit_price = Decimal('10.00')
    line_total = Decimal('10.00')


# ── Staff ────────────────────────────────────────────────────────────────────────

class ShiftFactory(DjangoModelFactory):
    class Meta:
        model = Shift

    employee = factory.SubFactory(UserFactory)
    clock_in = factory.LazyFunction(timezone.now)


class ActiveShiftFactory(ShiftFactory):
    """A shift with no clock_out — the employee is currently clocked in."""
    clock_out = None


class CompletedShiftFactory(ShiftFactory):
    """A finished shift with an explicit clock_out time."""
    clock_out = factory.LazyAttribute(
        lambda o: o.clock_in + __import__('datetime').timedelta(hours=8)
    )
