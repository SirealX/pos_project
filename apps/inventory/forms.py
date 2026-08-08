from django import forms

from .models import Category, Product


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ('name', 'description', 'is_active')


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = (
            'name', 'sku', 'category', 'description',
            'price', 'cost', 'stock_quantity', 'low_stock_threshold',
            'image', 'is_active',
        )
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_sku(self):
        """Normalise SKU to uppercase so 'abc123' and 'ABC123' are the same."""
        return self.cleaned_data['sku'].upper().strip()

    def clean(self):
        cleaned = super().clean()
        price = cleaned.get('price')
        cost = cleaned.get('cost')
        if price is not None and cost is not None and cost > price:
            self.add_error('cost', "Cost cannot be higher than the selling price.")
        return cleaned
