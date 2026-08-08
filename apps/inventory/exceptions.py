class InsufficientStockError(Exception):
    """
    Raised by SaleService when a cart item requests more units than available.

    Carries the list of product names so the view can show a specific message
    ("Not enough stock for: Coca-Cola, Lays Chips") rather than a generic one.
    """

    def __init__(self, product_names: list[str]):
        self.product_names = product_names
        super().__init__(f"Insufficient stock for: {', '.join(product_names)}")
