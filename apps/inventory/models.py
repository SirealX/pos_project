"""
Inventory models: Category and Product.

Key decisions vs Cesar's implementation:
- Product has a `sku` field (unique identifier for POS scanning / reporting)
- `cost` field enables gross margin calculation for business analytics
- `low_stock_threshold` is per-product, not a global constant — a high-turnover
  item needs a higher threshold than a slow-moving one
- `is_low_stock` uses the instance's own threshold, not settings.LOW_STOCK_THRESHOLD
- Custom manager with a chainable QuerySet for clean, reusable filters
- `db_index=True` on `name` and `is_active` because every product list page
  filters by active and searches by name
"""
from django.db import models

from .managers import ProductManager


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
    )
    name = models.CharField(max_length=200, db_index=True)
    sku = models.CharField(max_length=50, unique=True, db_index=True)
    description = models.TextField(blank=True)
    # Selling price charged to the customer
    price = models.DecimalField(max_digits=10, decimal_places=2)
    # Purchase / cost price — used for margin reports, never shown at POS
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stock_quantity = models.PositiveIntegerField(default=0)
    # Per-product threshold so high-velocity items alert earlier
    low_stock_threshold = models.PositiveIntegerField(default=10)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProductManager()

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} (SKU: {self.sku})"

    @property
    def is_low_stock(self) -> bool:
        return self.stock_quantity <= self.low_stock_threshold

    @property
    def is_out_of_stock(self) -> bool:
        return self.stock_quantity == 0

    @property
    def gross_margin(self) -> float:
        """Return gross margin as a percentage, e.g. 40.0 for 40%."""
        if not self.price:
            return 0.0
        return round(float((self.price - self.cost) / self.price) * 100, 2)
