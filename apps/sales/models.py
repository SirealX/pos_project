"""
Sales models: Sale and SaleLineItem.

Key decisions vs Cesar's implementation:

1. cashier = PROTECT (not SET_NULL)
   Cesar uses SET_NULL, which means deleting a user wipes "who made this sale"
   from every historical record.  PROTECT prevents the delete entirely — you
   must deactivate a user, not delete them, which is the correct POS flow.

2. unit_price is a snapshot on SaleLineItem
   Both implementations store this correctly.  It is critical: if you FK to
   Product.price and the price later changes, all historical line items show
   the new price, corrupting your records.

3. line_total is a STORED field (not a method)
   Cesar's get_total_price() computes line totals in Python.  Storing them
   lets the DB aggregate with SUM(line_total) instead of pulling all rows.
   SaleLineItem.save() keeps it in sync automatically.

4. Sale stores subtotal, tax_amount, total_amount
   These are computed once at checkout and stored.  Recalculating on every
   read would mean every report query joins to line_items and sums.
   Denormalization here is correct — sale totals are immutable after completion.

5. Status transitions via model methods (mark_completed, void)
   Instead of setting .status = 'COMPLETED' in views (scattered, easy to
   forget the completed_at timestamp), callers use sale.mark_completed().
   State transitions live in one place and always do the right thing.

6. unique_together on (sale, product)
   Prevents the same product appearing twice in one sale — the service layer
   should merge quantities instead.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from .managers import SaleManager


class Sale(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        COMPLETED = 'COMPLETED', 'Completed'
        VOIDED = 'VOIDED', 'Voided'

    class PaymentMethod(models.TextChoices):
        CASH = 'CASH', 'Cash'
        CARD = 'CARD', 'Card'
        TRANSFER = 'TRANSFER', 'Bank Transfer'

    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='sales',
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    payment_method = models.CharField(
        max_length=10,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # tax_rate stored per-sale so historical records are unaffected if the
    # rate changes in settings later.
    tax_rate = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_tendered = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    change_due = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = SaleManager()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Sale #{self.pk} — {self.get_status_display()} — ${self.total_amount}"

    def mark_completed(self):
        """Transition to COMPLETED and record the timestamp atomically."""
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        # update_fields tells Django to only UPDATE these two columns,
        # not the entire row — safer and faster under concurrent load.
        self.save(update_fields=['status', 'completed_at'])

    def void(self):
        """Transition to VOIDED. Inventory reversal is the caller's responsibility."""
        self.status = self.Status.VOIDED
        self.save(update_fields=['status'])


class SaleLineItem(models.Model):
    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name='line_items',
    )
    product = models.ForeignKey(
        'inventory.Product',
        on_delete=models.PROTECT,
        related_name='sale_line_items',
    )
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    # Stored (denormalised) for fast aggregation. Kept in sync by save().
    line_total = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ('sale', 'product')

    def __str__(self):
        return f"{self.quantity}× {self.product.name} @ ${self.unit_price}"

    def save(self, *args, **kwargs):
        self.line_total = self.quantity * self.unit_price
        super().save(*args, **kwargs)
