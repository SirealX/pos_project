from django.db import models


class ProductQuerySet(models.QuerySet):
    """
    Custom QuerySet attached to ProductManager so that chaining works:
        Product.objects.active().low_stock()
        Product.objects.in_stock().by_category(cat)

    If these were plain Manager methods that returned QuerySets, chaining
    would call the base QuerySet's methods and lose the custom filters.
    Putting them on QuerySet (and proxying them on Manager) fixes that.
    """

    def active(self):
        return self.filter(is_active=True)

    def low_stock(self):
        # Compare stock against each product's own threshold using F() —
        # a single DB expression instead of pulling every row into Python.
        return self.active().filter(stock_quantity__lte=models.F('low_stock_threshold'))

    def in_stock(self):
        return self.active().filter(stock_quantity__gt=0)

    def out_of_stock(self):
        return self.active().filter(stock_quantity=0)

    def by_category(self, category):
        return self.active().filter(category=category)


class ProductManager(models.Manager):
    def get_queryset(self):
        return ProductQuerySet(self.model, using=self._db)

    # Proxy the most common methods so callers can use Product.objects.active()
    # and also Product.objects.all().active() interchangeably.
    def active(self):
        return self.get_queryset().active()

    def low_stock(self):
        return self.get_queryset().low_stock()

    def in_stock(self):
        return self.get_queryset().in_stock()

    def out_of_stock(self):
        return self.get_queryset().out_of_stock()
