"""
Inventory views: Product and Category CRUD.

Architecture: Class-Based Views for all standard CRUD operations.

WHY CBVs here instead of FBVs?
Each CRUD view has a very predictable shape:
    GET  → render form with (optional) instance
    POST → validate form → save → redirect OR re-render with errors

ListView / CreateView / UpdateView / DeleteView encode this shape perfectly.
The only custom logic is:
    - get_queryset(): filter by is_active, apply search param, prefetch category
    - get_context_data(): inject extra template context (low_stock count)
    - form_valid(): add a success flash message before the standard redirect

Any logic beyond that belongs in forms.py (validation) or services.py (business
operations like bulk price updates). Views stay thin.

Performance note on ProductListView:
    .select_related('category') prevents N+1 for the category name column
    that appears on every row of the product table.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.mixins import ManagerRequiredMixin

from .forms import CategoryForm, ProductForm
from .models import Category, Product


# ── Products ───────────────────────────────────────────────────────────────────

class ProductListView(LoginRequiredMixin, ListView):
    template_name = 'inventory/product_list.html'
    context_object_name = 'products'
    paginate_by = 25

    def get_queryset(self):
        qs = Product.objects.active().select_related('category').order_by('name')
        query = self.request.GET.get('q', '').strip()
        if query:
            qs = qs.filter(name__icontains=query)
        category_id = self.request.GET.get('category')
        if category_id:
            qs = qs.filter(category_id=category_id)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['low_stock_count'] = Product.objects.low_stock().count()
        ctx['categories'] = Category.objects.filter(is_active=True)
        ctx['query'] = self.request.GET.get('q', '')
        ctx['selected_category'] = self.request.GET.get('category', '')
        return ctx


class ProductCreateView(ManagerRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'inventory/product_form.html'
    success_url = reverse_lazy('inventory:product-list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['action'] = 'Add Product'
        return ctx

    def form_valid(self, form):
        messages.success(self.request, f"Product '{form.instance.name}' created.")
        return super().form_valid(form)


class ProductUpdateView(ManagerRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'inventory/product_form.html'
    success_url = reverse_lazy('inventory:product-list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['action'] = 'Edit Product'
        return ctx

    def form_valid(self, form):
        messages.success(self.request, f"Product '{form.instance.name}' updated.")
        return super().form_valid(form)


class ProductDeleteView(ManagerRequiredMixin, DeleteView):
    model = Product
    template_name = 'inventory/product_confirm_delete.html'
    success_url = reverse_lazy('inventory:product-list')

    def form_valid(self, form):
        name = self.get_object().name
        result = super().form_valid(form)
        messages.success(self.request, f"Product '{name}' deleted.")
        return result


# ── Categories ─────────────────────────────────────────────────────────────────

class CategoryListView(ManagerRequiredMixin, ListView):
    model = Category
    template_name = 'inventory/category_list.html'
    context_object_name = 'categories'

    def get_queryset(self):
        return Category.objects.filter(is_active=True).order_by('name')


class CategoryCreateView(ManagerRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = 'inventory/category_form.html'
    success_url = reverse_lazy('inventory:category-list')

    def form_valid(self, form):
        messages.success(self.request, f"Category '{form.instance.name}' created.")
        return super().form_valid(form)


class CategoryUpdateView(ManagerRequiredMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = 'inventory/category_form.html'
    success_url = reverse_lazy('inventory:category-list')

    def form_valid(self, form):
        messages.success(self.request, f"Category '{form.instance.name}' updated.")
        return super().form_valid(form)
