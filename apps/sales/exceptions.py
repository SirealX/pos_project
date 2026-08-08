from decimal import Decimal


class EmptyCartError(Exception):
    """Raised when attempting to finalize a sale with nothing in the cart."""
    pass


class UnderpaymentError(Exception):
    """
    Raised when cash tendered is less than the total amount due.

    Carries both values so the view can tell the cashier exactly how much
    more is needed without recalculating.
    """

    def __init__(self, tendered: Decimal, total: Decimal):
        self.tendered = tendered
        self.total = total
        self.shortfall = total - tendered
        super().__init__(
            f"Amount tendered (${tendered}) is less than total (${total}). "
            f"Shortfall: ${self.shortfall}"
        )
