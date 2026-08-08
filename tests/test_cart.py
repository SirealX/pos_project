"""
CartService unit tests.

Most of these tests use a plain dict as the session stub (no DB, no request).
Only tests that call get_items() need @pytest.mark.django_db because that
method queries the Product table.
"""
from decimal import Decimal

import pytest

from apps.sales.cart import CartService

from .factories import ProductFactory


def make_cart(session=None):
    return CartService(session if session is not None else {})


# ── Mutation API ─────────────────────────────────────────────────────────────────

def test_add_new_item():
    cart = make_cart()
    cart.add(42, 3)
    assert cart._raw == {'42': {'quantity': 3}}


def test_add_merges_quantity_for_existing_item():
    cart = make_cart()
    cart.add(42, 2)
    cart.add(42, 3)
    assert cart._raw['42']['quantity'] == 5


def test_add_different_products_are_separate_lines():
    cart = make_cart()
    cart.add(1, 1)
    cart.add(2, 1)
    assert len(cart._raw) == 2


def test_remove_existing_item():
    cart = make_cart()
    cart.add(1, 2)
    cart.remove(1)
    assert '1' not in cart._raw


def test_remove_nonexistent_item_is_silent():
    cart = make_cart()
    cart.remove(999)  # should not raise


def test_set_quantity_updates_value():
    cart = make_cart()
    cart.add(1, 5)
    cart.set_quantity(1, 3)
    assert cart._raw['1']['quantity'] == 3


def test_set_quantity_zero_removes_item():
    cart = make_cart()
    cart.add(1, 2)
    cart.set_quantity(1, 0)
    assert '1' not in cart._raw


def test_set_quantity_negative_removes_item():
    cart = make_cart()
    cart.add(1, 2)
    cart.set_quantity(1, -1)
    assert '1' not in cart._raw


def test_clear_empties_cart():
    cart = make_cart()
    cart.add(1, 1)
    cart.add(2, 3)
    cart.clear()
    assert cart._raw == {}


# ── Read API (no DB) ─────────────────────────────────────────────────────────────

def test_is_empty_true_on_new_cart():
    assert make_cart().is_empty()


def test_is_empty_false_after_add():
    cart = make_cart()
    cart.add(1, 1)
    assert not cart.is_empty()


def test_bool_false_for_empty_cart():
    assert not make_cart()


def test_bool_true_after_add():
    cart = make_cart()
    cart.add(1, 1)
    assert cart


def test_item_count_sums_quantities():
    cart = make_cart()
    cart.add(1, 3)
    cart.add(2, 4)
    assert cart.item_count() == 7


def test_len_equals_item_count():
    cart = make_cart()
    cart.add(1, 5)
    assert len(cart) == 5


def test_subtotal_zero_for_empty_cart():
    assert make_cart().subtotal() == Decimal('0')


def test_product_ids_returns_int_list():
    cart = make_cart()
    cart.add(7, 1)
    cart.add(11, 2)
    assert set(cart.product_ids()) == {7, 11}


# ── get_items() — requires DB ────────────────────────────────────────────────────

@pytest.mark.django_db
def test_get_items_returns_enriched_dicts():
    product = ProductFactory(price=Decimal('5.00'), stock_quantity=10)
    cart = make_cart()
    cart.add(product.pk, 2)

    items = cart.get_items()

    assert len(items) == 1
    item = items[0]
    assert item['product'] == product
    assert item['quantity'] == 2
    assert item['unit_price'] == Decimal('5.00')
    assert item['line_total'] == Decimal('10.00')


@pytest.mark.django_db
def test_get_items_caches_result(django_assert_num_queries):
    product = ProductFactory(stock_quantity=5)
    cart = make_cart()
    cart.add(product.pk, 1)

    with django_assert_num_queries(1):
        cart.get_items()   # first call: 1 DB query
        cart.get_items()   # second call: cache hit, 0 extra queries


@pytest.mark.django_db
def test_add_invalidates_get_items_cache():
    product1 = ProductFactory(stock_quantity=5)
    product2 = ProductFactory(stock_quantity=5)
    cart = make_cart()
    cart.add(product1.pk, 1)
    cart.get_items()  # populate cache

    cart.add(product2.pk, 1)  # should invalidate cache

    items = cart.get_items()
    assert len(items) == 2


@pytest.mark.django_db
def test_get_items_drops_inactive_product():
    active = ProductFactory(is_active=True, stock_quantity=5)
    inactive = ProductFactory(is_active=False, stock_quantity=5)
    cart = make_cart()
    cart.add(active.pk, 1)
    cart.add(inactive.pk, 1)

    items = cart.get_items()

    pks = [i['product'].pk for i in items]
    assert active.pk in pks
    assert inactive.pk not in pks


@pytest.mark.django_db
def test_subtotal_uses_product_price():
    product = ProductFactory(price=Decimal('7.50'), stock_quantity=10)
    cart = make_cart()
    cart.add(product.pk, 4)

    assert cart.subtotal() == Decimal('30.00')


# ── Session persistence ──────────────────────────────────────────────────────────

def test_cart_persists_to_session_dict():
    session = {}
    cart = CartService(session)
    cart.add(1, 2)
    # The session dict should hold the raw cart data
    assert session[CartService.SESSION_KEY] == {'1': {'quantity': 2}}


def test_persist_tolerates_plain_dict_session():
    """CartService must work without Django's session .modified attribute."""
    session = {}
    cart = CartService(session)
    cart.add(1, 1)  # triggers _persist() — must not raise
