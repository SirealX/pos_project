"""
SaleService — creates and voids sales, coordinates inventory deduction.

WHY THE RACE CONDITIONS IN CESAR'S CODE MATTER
───────────────────────────────────────────────────────────────────────────
Cesar's complete_sale view does this:

    product.stock -= quantity   # (1) read stock into Python
    product.save()              # (2) write Python value back to DB

This is a classic "lost update" bug. With two concurrent cashiers:

    Cashier A reads stock=1
    Cashier B reads stock=1
    Cashier A checks: 1 >= 1 → OK, sells it, writes stock=0
    Cashier B checks: 1 >= 1 → OK, sells it, writes stock=0
    → Both sales succeed. Stock is now 0 but two items were "sold". Oversell.

Cesar also does `sale.delete()` on the error path, which is wrong — if the
delete itself fails, or if a different error fires after a partial commit, you
get orphaned records. transaction.atomic() + exception-based flow fixes this.

THE TWO-PART FIX
───────────────────────────────────────────────────────────────────────────
Part 1 — select_for_update() (prevents the check-then-act race):

    products = Product.objects.select_for_update().filter(pk__in=ids)
    # SQL: SELECT ... FOR UPDATE

    This acquires a row-level exclusive lock for the duration of the
    transaction. Cashier B's select_for_update() BLOCKS until Cashier A's
    transaction commits. After commit, Cashier B re-reads stock=0 and raises
    InsufficientStockError. Oversell impossible.

    order_by('pk') ensures consistent lock order across concurrent transactions
    — without it, two transactions locking {A, B} and {B, A} can deadlock.

Part 2 — F() expression (prevents the lost-update bug in the deduction itself):

    Product.objects.filter(pk=pk).update(
        stock_quantity=F('stock_quantity') - qty
    )
    # SQL: UPDATE SET stock_quantity = stock_quantity - qty

    This evaluates the subtraction IN the database. The DB column never
    leaves the DB — no stale Python value can overwrite a concurrent update.
    Belt (select_for_update) + suspenders (F expression) = safe under any load.
───────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import transaction
from django.db.models import F

from apps.inventory.exceptions import InsufficientStockError
from apps.inventory.models import Product
from apps.sales.cart import CartService
from apps.sales.exceptions import EmptyCartError, UnderpaymentError
from apps.sales.models import Sale, SaleLineItem


class SaleService:

    @staticmethod
    @transaction.atomic
    def create_from_cart(
        cashier,
        cart: CartService,
        payment_method: str = Sale.PaymentMethod.CASH,
        amount_tendered: Decimal | None = None,
        notes: str = '',
    ) -> Sale:
        """
        Convert a CartService into a completed, persisted Sale.

        Steps (all inside one atomic transaction):
          1. Guard: empty cart → EmptyCartError
          2. Lock product rows with select_for_update()
          3. Validate every item's stock — fail with ALL errors, not just first
          4. Compute totals (subtotal, tax, total)
          5. Validate cash payment if applicable
          6. Create Sale header
          7. Create SaleLineItem rows + deduct inventory with F()
          8. Mark sale COMPLETED + clear cart

        Raises:
            EmptyCartError         — cart has no items
            InsufficientStockError — one or more products have insufficient stock
            UnderpaymentError      — cash tendered < total (card payments pass None)
        """
        if cart.is_empty():
            raise EmptyCartError("Cannot complete a sale with an empty cart.")

        cart_items = cart.get_items()
        product_ids = [item['product'].pk for item in cart_items]

        # ── Step 2: Lock ───────────────────────────────────────────────
        # order_by('pk') = consistent lock ordering across transactions.
        # Without this, T1 locking {pk=3, pk=7} and T2 locking {pk=7, pk=3}
        # can deadlock. Consistent order means one always waits for the other.
        locked_products = {
            p.pk: p
            for p in Product.objects
                            .select_for_update()
                            .filter(pk__in=product_ids)
                            .order_by('pk')
        }

        # ── Step 3: Stock validation ───────────────────────────────────
        # Collect ALL errors before raising — the cashier sees everything at
        # once rather than fixing one item and hitting the next error.
        out_of_stock_names = [
            locked_products[item['product'].pk].name
            for item in cart_items
            if locked_products[item['product'].pk].stock_quantity < item['quantity']
        ]
        if out_of_stock_names:
            raise InsufficientStockError(out_of_stock_names)

        # ── Step 4: Totals ─────────────────────────────────────────────
        subtotal = sum(
            (item['line_total'] for item in cart_items),
            Decimal('0'),
        )
        # tax_rate comes from settings (configurable per environment via .env)
        tax_rate = Decimal(str(settings.TAX_RATE))
        # ROUND_HALF_UP matches standard retail rounding (0.005 → 0.01)
        tax_amount = (subtotal * tax_rate).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        total_amount = subtotal + tax_amount

        # ── Step 5: Cash validation ────────────────────────────────────
        if amount_tendered is not None and amount_tendered < total_amount:
            raise UnderpaymentError(amount_tendered, total_amount)

        change_due = (
            (amount_tendered - total_amount).quantize(Decimal('0.01'))
            if amount_tendered is not None
            else None
        )

        # ── Step 6: Sale header ────────────────────────────────────────
        # tax_rate is stored ON the sale record so that historical reports
        # remain accurate if the tax rate in settings changes later.
        sale = Sale.objects.create(
            cashier=cashier,
            payment_method=payment_method,
            subtotal=subtotal,
            tax_rate=tax_rate,
            tax_amount=tax_amount,
            total_amount=total_amount,
            amount_tendered=amount_tendered,
            change_due=change_due,
            notes=notes,
        )

        # ── Steps 7a + 7b: Line items + inventory deduction ───────────
        for item in cart_items:
            SaleLineItem.objects.create(
                sale=sale,
                product=item['product'],
                quantity=item['quantity'],
                unit_price=item['unit_price'],
                # line_total is auto-computed by SaleLineItem.save()
            )
            # F() expression: the DB does the subtraction, not Python.
            # Prevents any stale-read issue in the deduction step itself.
            Product.objects.filter(pk=item['product'].pk).update(
                stock_quantity=F('stock_quantity') - item['quantity']
            )

        # ── Step 8: Finalise ───────────────────────────────────────────
        sale.mark_completed()  # sets status=COMPLETED + completed_at timestamp
        cart.clear()
        return sale

    @staticmethod
    @transaction.atomic
    def void_sale(sale: Sale) -> Sale:
        """
        Void a completed sale and restore all inventory.

        Uses select_related on line_items to eliminate N+1 when restoring stock.
        Inventory is restored with F() — same rationale as deduction.

        Raises:
            ValueError — if the sale is already voided or not yet completed
        """
        if sale.status == Sale.Status.VOIDED:
            raise ValueError("Sale is already voided.")
        if sale.status != Sale.Status.COMPLETED:
            raise ValueError("Only completed sales can be voided.")

        # Restore stock atomically using F() expressions
        for item in sale.line_items.select_related('product'):
            Product.objects.filter(pk=item.product_id).update(
                stock_quantity=F('stock_quantity') + item.quantity
            )

        sale.void()
        return sale
