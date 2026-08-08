"""
SaleService tests — the most critical business logic in the system.

Every test here corresponds to a rule that, if broken, would corrupt data
or cause a real financial error. Test names encode the rule being verified
so failures are self-documenting.

WHY test the service directly instead of through the view?
The service contains the invariants. A view test exercises HTTP plumbing;
a service test verifies the business rule. Both matter, but the service
test is the authoritative check for "does this rule hold?"
"""
from decimal import Decimal

import pytest

from apps.inventory.exceptions import InsufficientStockError
from apps.inventory.models import Product
from apps.sales.cart import CartService
from apps.sales.exceptions import EmptyCartError, UnderpaymentError
from apps.sales.models import Sale
from apps.sales.services import SaleService

from .factories import ProductFactory, UserFactory


# ── Helpers ──────────────────────────────────────────────────────────────────────

def make_cart(*products_and_qtys):
    """Build a CartService backed by a plain dict, pre-loaded with items."""
    cart = CartService({})
    for product, qty in products_and_qtys:
        cart.add(product.pk, qty)
    return cart


def call_service(cashier, cart, payment=Sale.PaymentMethod.CASH, tendered=None, notes=''):
    return SaleService.create_from_cart(
        cashier=cashier,
        cart=cart,
        payment_method=payment,
        amount_tendered=tendered,
        notes=notes,
    )


# ── Happy path ───────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_create_from_cart_returns_completed_sale():
    cashier = UserFactory()
    product = ProductFactory(price=Decimal('5.00'), stock_quantity=10)
    cart = make_cart((product, 2))

    sale = call_service(cashier, cart, tendered=Decimal('20.00'))

    assert sale.pk is not None
    assert sale.status == Sale.Status.COMPLETED
    assert sale.cashier == cashier


@pytest.mark.django_db
def test_sale_totals_computed_correctly():
    cashier = UserFactory()
    p = ProductFactory(price=Decimal('7.50'), stock_quantity=10)
    cart = make_cart((p, 4))  # 4 × 7.50 = 30.00

    sale = call_service(cashier, cart, tendered=Decimal('30.00'))

    assert sale.subtotal == Decimal('30.00')
    assert sale.total_amount == Decimal('30.00')  # TAX_RATE=0 in test settings


@pytest.mark.django_db
def test_sale_line_items_created_for_each_product():
    cashier = UserFactory()
    p1 = ProductFactory(price=Decimal('3.00'), stock_quantity=10)
    p2 = ProductFactory(price=Decimal('6.00'), stock_quantity=10)
    cart = make_cart((p1, 1), (p2, 2))

    sale = call_service(cashier, cart, tendered=Decimal('20.00'))

    assert sale.line_items.count() == 2
    line_totals = set(sale.line_items.values_list('line_total', flat=True))
    assert Decimal('3.00') in line_totals
    assert Decimal('12.00') in line_totals


@pytest.mark.django_db
def test_stock_is_deducted_after_sale():
    cashier = UserFactory()
    product = ProductFactory(stock_quantity=10)
    cart = make_cart((product, 3))

    call_service(cashier, cart, tendered=Decimal('999.00'))

    product.refresh_from_db()
    assert product.stock_quantity == 7


@pytest.mark.django_db
def test_cart_is_cleared_after_successful_sale():
    cashier = UserFactory()
    product = ProductFactory(stock_quantity=10)
    cart = make_cart((product, 1))

    call_service(cashier, cart, tendered=Decimal('10.00'))

    assert cart.is_empty()


@pytest.mark.django_db
def test_change_due_computed_for_cash_overpayment():
    cashier = UserFactory()
    product = ProductFactory(price=Decimal('7.00'), stock_quantity=10)
    cart = make_cart((product, 1))

    sale = call_service(cashier, cart, tendered=Decimal('10.00'))

    assert sale.change_due == Decimal('3.00')


@pytest.mark.django_db
def test_card_payment_requires_no_amount_tendered():
    cashier = UserFactory()
    product = ProductFactory(stock_quantity=5)
    cart = make_cart((product, 1))

    # amount_tendered=None is valid for card payments
    sale = call_service(cashier, cart, payment=Sale.PaymentMethod.CARD, tendered=None)

    assert sale.status == Sale.Status.COMPLETED
    assert sale.amount_tendered is None
    assert sale.change_due is None


# ── Error paths ──────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_empty_cart_raises_empty_cart_error():
    cashier = UserFactory()
    cart = CartService({})

    with pytest.raises(EmptyCartError):
        call_service(cashier, cart, tendered=Decimal('0'))


@pytest.mark.django_db
def test_insufficient_stock_raises_error():
    cashier = UserFactory()
    product = ProductFactory(stock_quantity=2)
    cart = make_cart((product, 5))  # want 5, only have 2

    with pytest.raises(InsufficientStockError) as exc_info:
        call_service(cashier, cart, tendered=Decimal('999.00'))

    assert product.name in exc_info.value.product_names


@pytest.mark.django_db
def test_insufficient_stock_reports_all_failing_products():
    """Service collects ALL stock errors before raising — not just the first."""
    cashier = UserFactory()
    p1 = ProductFactory(name='Widget', stock_quantity=0)
    p2 = ProductFactory(name='Gadget', stock_quantity=0)
    cart = make_cart((p1, 1), (p2, 1))

    with pytest.raises(InsufficientStockError) as exc_info:
        call_service(cashier, cart, tendered=Decimal('999.00'))

    assert 'Widget' in exc_info.value.product_names
    assert 'Gadget' in exc_info.value.product_names


@pytest.mark.django_db
def test_insufficient_stock_does_not_persist_partial_sale():
    """A failed sale must not leave any DB records (atomicity check)."""
    cashier = UserFactory()
    product = ProductFactory(stock_quantity=0)
    cart = make_cart((product, 1))

    with pytest.raises(InsufficientStockError):
        call_service(cashier, cart, tendered=Decimal('999.00'))

    assert Sale.objects.count() == 0


@pytest.mark.django_db
def test_underpayment_raises_error():
    cashier = UserFactory()
    product = ProductFactory(price=Decimal('10.00'), stock_quantity=5)
    cart = make_cart((product, 1))  # total = 10.00

    with pytest.raises(UnderpaymentError) as exc_info:
        call_service(cashier, cart, tendered=Decimal('5.00'))

    assert exc_info.value.tendered == Decimal('5.00')
    assert exc_info.value.total == Decimal('10.00')
    assert exc_info.value.shortfall == Decimal('5.00')


@pytest.mark.django_db
def test_underpayment_does_not_deduct_stock():
    """An underpayment error must roll back before inventory is touched."""
    cashier = UserFactory()
    product = ProductFactory(price=Decimal('10.00'), stock_quantity=5)
    cart = make_cart((product, 1))

    with pytest.raises(UnderpaymentError):
        call_service(cashier, cart, tendered=Decimal('1.00'))

    product.refresh_from_db()
    assert product.stock_quantity == 5  # unchanged


# ── void_sale ────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_void_sale_changes_status_to_voided():
    cashier = UserFactory()
    product = ProductFactory(stock_quantity=10)
    cart = make_cart((product, 2))
    sale = call_service(cashier, cart, tendered=Decimal('999.00'))

    SaleService.void_sale(sale)

    sale.refresh_from_db()
    assert sale.status == Sale.Status.VOIDED


@pytest.mark.django_db
def test_void_sale_restores_inventory():
    cashier = UserFactory()
    product = ProductFactory(stock_quantity=10)
    cart = make_cart((product, 3))
    sale = call_service(cashier, cart, tendered=Decimal('999.00'))

    product.refresh_from_db()
    assert product.stock_quantity == 7  # deducted

    SaleService.void_sale(sale)

    product.refresh_from_db()
    assert product.stock_quantity == 10  # restored


@pytest.mark.django_db
def test_void_already_voided_sale_raises():
    cashier = UserFactory()
    product = ProductFactory(stock_quantity=10)
    cart = make_cart((product, 1))
    sale = call_service(cashier, cart, tendered=Decimal('999.00'))
    SaleService.void_sale(sale)

    with pytest.raises(ValueError, match="already voided"):
        SaleService.void_sale(sale)


@pytest.mark.django_db
def test_void_pending_sale_raises():
    from .factories import SaleFactory
    pending = SaleFactory(status=Sale.Status.PENDING)

    with pytest.raises(ValueError, match="Only completed"):
        SaleService.void_sale(pending)
