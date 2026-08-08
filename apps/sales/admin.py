from django.contrib import admin

from .models import Sale, SaleLineItem


class SaleLineItemInline(admin.TabularInline):
    model = SaleLineItem
    extra = 0
    readonly_fields = ('line_total',)
    fields = ('product', 'quantity', 'unit_price', 'line_total')
    raw_id_fields = ('product',)


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'cashier', 'status', 'payment_method',
        'subtotal', 'tax_amount', 'total_amount', 'created_at',
    )
    list_filter = ('status', 'payment_method', 'created_at')
    search_fields = ('cashier__username', 'cashier__first_name', 'cashier__last_name')
    readonly_fields = ('created_at', 'completed_at', 'subtotal', 'tax_amount', 'total_amount')
    raw_id_fields = ('cashier',)
    date_hierarchy = 'created_at'
    inlines = [SaleLineItemInline]
