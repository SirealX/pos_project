from decimal import Decimal

from django import forms

from .models import Sale


class CheckoutForm(forms.Form):
    """
    Collects payment details at the end of a POS transaction.

    WHY pass total_amount into __init__?
    The form needs to validate that cash tendered >= total. The total is not
    a fixed value — it changes with each cart. Passing it as a constructor
    argument keeps validation logic in the form (correct) rather than in the
    view (incorrect).
    """
    payment_method = forms.ChoiceField(
        choices=Sale.PaymentMethod.choices,
        initial=Sale.PaymentMethod.CASH,
    )
    amount_tendered = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        min_value=Decimal('0.01'),
        help_text="Required for cash payments.",
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 2}),
        required=False,
    )

    def __init__(self, *args, total_amount: Decimal = Decimal('0'), **kwargs):
        self._total_amount = total_amount
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get('payment_method')
        tendered = cleaned.get('amount_tendered')

        if method == Sale.PaymentMethod.CASH:
            if not tendered:
                self.add_error('amount_tendered', "Amount tendered is required for cash payments.")
            elif tendered < self._total_amount:
                shortfall = self._total_amount - tendered
                self.add_error(
                    'amount_tendered',
                    f"${shortfall:.2f} short. Total is ${self._total_amount:.2f}.",
                )
        return cleaned
