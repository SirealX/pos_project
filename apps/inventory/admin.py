from django.contrib import admin

from .models import Category, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'sku', 'category', 'price', 'cost',
        'gross_margin_display', 'stock_quantity', 'is_active', 'low_stock_badge',
    )
    list_filter = ('is_active', 'category')
    list_editable = ('price', 'stock_quantity', 'is_active')
    search_fields = ('name', 'sku', 'description')
    readonly_fields = ('created_at', 'updated_at', 'gross_margin_display')
    fieldsets = (
        (None, {
            'fields': ('name', 'sku', 'category', 'description', 'image', 'is_active'),
        }),
        ('Pricing & Stock', {
            'fields': ('price', 'cost', 'gross_margin_display', 'stock_quantity', 'low_stock_threshold'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Margin %')
    def gross_margin_display(self, obj):
        return f"{obj.gross_margin}%"

    @admin.display(boolean=True, description='Low stock?')
    def low_stock_badge(self, obj):
        return obj.is_low_stock
