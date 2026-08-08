"""
CartService — session-backed cart for the POS checkout flow.

COMPARE WITH CESAR'S cart.py
─────────────────────────────────────────────────────────────────────────────
Cesar's approach: module-level functions, each taking `session` as a parameter.

    def add_to_cart(session, product_id, quantity=1):
        cart = session.get("cart", {})
        ...
        session["cart"] = cart
        session.modified = True

Problems with this approach:
  1. The session dict structure {'product_id': {'quantity': N}} is an
     implicit contract. Any caller that touches session['cart'] directly
     bypasses the contract without a type error.
  2. N+1 query in pos_checkout view: get_object_or_404(Product, pk=pid)
     is called inside a for-loop — one DB query per cart item.
  3. No way to cache the result within a single request — the view calls
     get_cart() and then re-fetches products on every render.
  4. Total is recomputed in the view. Any second place that needs the total
     (e.g. a cart badge in the navbar) duplicates the computation.

This module's approach: a class that encapsulates ALL cart concerns.
  1. Session structure is private — callers use .add(), .remove(), etc.
  2. get_items() fetches ALL products in ONE query (IN clause), then
     dict-looks up each cart entry. Zero N+1.
  3. _items_cache stores the result for the lifetime of the request.
     Call get_items() five times in one view — one DB query total.
  4. subtotal() delegates to get_items() — computed once, reused.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.contrib.sessions.backends.base import SessionBase


class CartService:
    SESSION_KEY = 'cart'

    def __init__(self, session: SessionBase):
        self._session = session
        # Lazily initialise the cart dict in session if it doesn't exist yet.
        if self.SESSION_KEY not in session:
            session[self.SESSION_KEY] = {}
        # Per-request cache for get_items(). Invalidated on any mutation.
        self._items_cache: list[dict] | None = None

    # ------------------------------------------------------------------
    # Mutation API
    # ------------------------------------------------------------------

    def add(self, product_id: int, quantity: int = 1) -> None:
        pid = str(product_id)
        if pid in self._raw:
            self._raw[pid]['quantity'] += quantity
        else:
            self._raw[pid] = {'quantity': quantity}
        self._invalidate()
        self._persist()

    def remove(self, product_id: int) -> None:
        self._raw.pop(str(product_id), None)
        self._invalidate()
        self._persist()

    def set_quantity(self, product_id: int, quantity: int) -> None:
        """Directly set quantity. Removes the item if quantity ≤ 0."""
        if quantity <= 0:
            self.remove(product_id)
        else:
            self._raw[str(product_id)] = {'quantity': quantity}
            self._invalidate()
            self._persist()

    def clear(self) -> None:
        self._session[self.SESSION_KEY] = {}
        self._invalidate()
        self._persist()

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def is_empty(self) -> bool:
        return not bool(self._raw)

    def product_ids(self) -> list[int]:
        return [int(pid) for pid in self._raw]

    def get_items(self) -> list[dict]:
        """
        Return enriched cart line items as a list of dicts:
            {
                'product':    <Product instance>,
                'quantity':   int,
                'unit_price': Decimal,
                'line_total': Decimal,
            }

        One DB query — Products are fetched in bulk using an IN clause then
        looked up by pk from an in-memory dict. Items whose product was
        deleted or deactivated since being added are silently dropped.

        The result is cached on this instance. Subsequent calls within the
        same request return the cached list immediately.
        """
        if self._items_cache is not None:
            return self._items_cache

        if self.is_empty():
            self._items_cache = []
            return self._items_cache

        # Deferred import: CartService lives in sales.cart but depends on
        # inventory.models. Deferring avoids a circular import at module load.
        from apps.inventory.models import Product

        # Single IN query — no loop, no N+1
        products_by_pk = {
            str(p.pk): p
            for p in Product.objects.filter(
                pk__in=self.product_ids(),
                is_active=True,
            ).select_related('category')
        }

        items = []
        for pid, data in self._raw.items():
            product = products_by_pk.get(pid)
            if product is None:
                # Product deleted or deactivated — skip it silently
                continue
            qty = data['quantity']
            items.append({
                'product': product,
                'quantity': qty,
                'unit_price': product.price,
                'line_total': product.price * qty,
            })

        self._items_cache = items
        return items

    def subtotal(self) -> Decimal:
        """Sum of all line_totals. Zero for an empty cart."""
        return sum(
            (item['line_total'] for item in self.get_items()),
            Decimal('0'),
        )

    def item_count(self) -> int:
        """Total number of individual units across all lines."""
        return sum(d['quantity'] for d in self._raw.values())

    # ------------------------------------------------------------------
    # Dunder helpers — lets views do `if cart:` and `len(cart)`
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return self.item_count()

    def __bool__(self) -> bool:
        return not self.is_empty()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @property
    def _raw(self) -> dict:
        """Direct reference to the session dict — use carefully."""
        return self._session[self.SESSION_KEY]

    def _persist(self) -> None:
        """
        Tell Django the session was mutated so it writes to the DB/cache.

        The `modified` flag is set via attribute assignment rather than a
        method so that plain dicts can be used as session stubs in unit
        tests — dicts simply don't have the attribute and the setattr is a
        no-op for them.  Real Django sessions do have it.
        """
        try:
            self._session.modified = True
        except (AttributeError, TypeError):
            pass

    def _invalidate(self) -> None:
        self._items_cache = None
