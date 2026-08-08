"""
Shared pytest fixtures.

Scope strategy:
  - 'function' (default): user/product objects that tests may mutate.
  - No 'session' or 'module' scope here — each test gets a fresh DB state
    via pytest-django's transaction rollback, so sharing objects across tests
    would only be an optimisation at the cost of test isolation.

CartService with a plain dict:
  CartService._persist() wraps `session.modified = True` in try/except so a
  plain {} works as a session stub. This lets cart unit tests run without a
  real Django session or request context.
"""
import pytest
from django.test import Client

from .factories import (
    AdminFactory,
    CategoryFactory,
    ManagerFactory,
    ProductFactory,
    UserFactory,
)


# ── Users ────────────────────────────────────────────────────────────────────────

@pytest.fixture
def staff_user(db):
    return UserFactory()


@pytest.fixture
def manager_user(db):
    return ManagerFactory()


@pytest.fixture
def admin_user(db):
    return AdminFactory()


# ── HTTP clients (pre-authenticated) ────────────────────────────────────────────

@pytest.fixture
def staff_client(client, staff_user):
    client.force_login(staff_user)
    return client


@pytest.fixture
def manager_client(client, manager_user):
    client.force_login(manager_user)
    return client


@pytest.fixture
def anon_client():
    return Client()


# ── Inventory ───────────────────────────────────────────────────────────────────

@pytest.fixture
def category(db):
    return CategoryFactory()


@pytest.fixture
def product(db):
    return ProductFactory(stock_quantity=10, price=Decimal('5.00'))


@pytest.fixture
def product_low_stock(db):
    return ProductFactory(stock_quantity=2, low_stock_threshold=5)


# ── Cart (no DB needed for pure unit tests) ──────────────────────────────────────

@pytest.fixture
def empty_cart():
    from apps.sales.cart import CartService
    return CartService({})


# Lazy import so the fixture can be used without importing at module level
from decimal import Decimal
