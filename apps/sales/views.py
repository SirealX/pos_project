"""
Sales views: POS checkout screen, cart HTMX endpoints, sale history.

THE POS SCREEN ARCHITECTURE
─────────────────────────────────────────────────────────────────────────────
The checkout screen is split into two zones:
    Left:  product grid (renders once, doesn't change)
    Right: cart panel (updates on every add/remove/quantity change)

Naive approach: every cart action does a full page redirect:
    add_product_to_cart → redirect('pos_checkout') → full page re-render

This module's approach: HTMX partials
    POST /pos/cart/add/42/ → returns only the cart panel HTML
    HTMX swaps the cart panel in-place → no full page load

How it works with request.htmx (from django_htmx middleware):
    if request.htmx:
        return render(request, 'sales/partials/cart_panel.html', ctx)
    else:
        return redirect('sales:pos')  # fallback for JS-disabled browsers

The partial template renders ONLY the cart sidebar. HTMX's hx-target on the
button specifies which DOM element to swap — the cart panel div.

WHY FBVs for the cart endpoints instead of CBVs?
These are POST-only actions that don't fit a standard CRUD lifecycle.
They receive a product ID from the URL, mutate session state, and return a
partial HTML fragment. FBVs + @login_required is cleaner than shoehorning
this into a FormView or View subclass.

THE CHECKOUT FLOW
─────────────────────────────────────────────────────────────────────────────
1. Cashier adds products → cart panel updates via HTMX
2. Cashier submits the CheckoutForm (payment method, amount tendered)
3. checkout() view calls SaleService.create_from_cart()
4. On success → redirect to sale detail (receipt page)
5. On error (empty cart, insufficient stock, underpayment) → re-render POS
   with the form errors and the current cart

Error handling in checkout():
- We catch domain exceptions from SaleService and convert them to user
  messages. The view never knows HOW the checkout works — it only handles
  the result.
- The transaction.atomic() in SaleService means partial failures are rolled
  back automatically. No manual sale.delete() needed.

SALE DETAIL PERMISSIONS
─────────────────────────────────────────────────────────────────────────────
Staff can only see their own sales. Managers can see all sales.
This is enforced in get_queryset() by conditionally adding .for_cashier(user).
If a staff member tries /pos/sales/99/ and pk=99 belongs to another cashier,
the filtered queryset produces a 404 — not a 403 (which would leak that
the sale exists).
─────────────────────────────────────────────────────────────────────────────
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from apps.inventory.exceptions import InsufficientStockError
from apps.inventory.models import Category, Product
from apps.mixins import ManagerRequiredMixin

from .cart import CartService
from .exceptions import EmptyCartError, UnderpaymentError
from .forms import CheckoutForm
from .models import Sale
from .services import SaleService


# ── POS screen ─────────────────────────────────────────────────────────────────

@login_required
def pos_view(request):
    """
    Main POS checkout screen.

    Renders the product grid and the initial cart panel. All subsequent cart
    updates arrive as HTMX partials that swap only the cart panel.
    """
    cart = CartService(request.session)
    cart_items = cart.get_items()
    products = (
        Product.objects
        .in_stock()
        .select_related('category')
        .order_by('category__name', 'name')
    )
    categories = Category.objects.filter(is_active=True).order_by('name')

    return render(request, 'sales/pos.html', {
        'products': products,
        'categories': categories,
        'cart': cart,
        'cart_items': cart_items,                   # pre-fetched, no extra query
        'form': CheckoutForm(total_amount=cart.subtotal()),
    })


# ── Cart mutation endpoints (HTMX targets) ─────────────────────────────────────

@require_POST
@login_required
def cart_add(request, product_id):
    """
    Add a product to the cart.

    HTMX request → return the cart panel partial.
    Plain POST (JS disabled) → full redirect back to POS.

    WHY get_object_or_404 here instead of trusting the product exists?
    The product ID comes from the URL, which the user could manually craft.
    get_object_or_404 + is_active=True prevents adding deleted or inactive
    products to the cart via a crafted URL.
    """
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    quantity = max(1, int(request.POST.get('quantity', 1)))

    cart = CartService(request.session)
    cart.add(product.pk, quantity)

    if request.htmx:
        cart_items = cart.get_items()
        return render(request, 'sales/partials/cart_panel.html', {
            'cart': cart,
            'cart_items': cart_items,
            'form': CheckoutForm(total_amount=cart.subtotal()),
        })
    return redirect('sales:pos')


@require_POST
@login_required
def cart_remove(request, product_id):
    """Remove a product line entirely from the cart."""
    cart = CartService(request.session)
    cart.remove(product_id)

    if request.htmx:
        cart_items = cart.get_items()
        return render(request, 'sales/partials/cart_panel.html', {
            'cart': cart,
            'cart_items': cart_items,
            'form': CheckoutForm(total_amount=cart.subtotal()),
        })
    return redirect('sales:pos')


@require_POST
@login_required
def cart_set_quantity(request, product_id):
    """
    Update the quantity of a cart line item.

    Called when the cashier types directly in the quantity input (HTMX event:
    'change' or 'blur'). Setting quantity=0 removes the item.
    """
    try:
        quantity = int(request.POST.get('quantity', 1))
    except (ValueError, TypeError):
        quantity = 1

    cart = CartService(request.session)
    cart.set_quantity(product_id, quantity)

    if request.htmx:
        cart_items = cart.get_items()
        return render(request, 'sales/partials/cart_panel.html', {
            'cart': cart,
            'cart_items': cart_items,
            'form': CheckoutForm(total_amount=cart.subtotal()),
        })
    return redirect('sales:pos')


# ── Checkout ───────────────────────────────────────────────────────────────────

@require_POST
@login_required
def checkout(request):
    """
    Finalise the cart as a completed Sale.

    The view's only job:
        1. Validate the form (payment details)
        2. Call SaleService.create_from_cart()
        3. Convert domain exceptions to user messages
        4. Redirect on success / re-render on failure

    It does NOT touch Product, Shift, or raw SQL — that lives in services.py.
    """
    cart = CartService(request.session)
    form = CheckoutForm(request.POST, total_amount=cart.subtotal())

    if not form.is_valid():
        # Form-level validation failed (e.g. cash payment with no amount)
        # Re-render the POS with the form errors visible.
        cart_items = cart.get_items()
        return render(request, 'sales/pos.html', {
            'products': Product.objects.in_stock().select_related('category'),
            'categories': Category.objects.filter(is_active=True),
            'cart': cart,
            'cart_items': cart_items,
            'form': form,
        })

    try:
        sale = SaleService.create_from_cart(
            cashier=request.user,
            cart=cart,
            payment_method=form.cleaned_data['payment_method'],
            amount_tendered=form.cleaned_data.get('amount_tendered'),
            notes=form.cleaned_data.get('notes', ''),
        )
        messages.success(
            request,
            f"Sale #{sale.pk} completed! Total: ${sale.total_amount:.2f}",
        )
        return redirect('sales:sale-detail', pk=sale.pk)

    except EmptyCartError:
        messages.error(request, "Cart is empty.")
    except InsufficientStockError as exc:
        messages.error(request, f"Not enough stock: {', '.join(exc.product_names)}")
    except UnderpaymentError as exc:
        messages.error(request, str(exc))

    cart_items = cart.get_items()
    return render(request, 'sales/pos.html', {
        'products': Product.objects.in_stock().select_related('category'),
        'categories': Category.objects.filter(is_active=True),
        'cart': cart,
        'cart_items': cart_items,
        'form': form,
    })


# ── Sale history ───────────────────────────────────────────────────────────────

class SaleListView(LoginRequiredMixin, ListView):
    template_name = 'sales/sale_list.html'
    context_object_name = 'sales'
    paginate_by = 20

    def get_queryset(self):
        # Completed sales only — pending/voided visible to managers via admin
        qs = (
            Sale.objects
            .completed()
            .select_related('cashier')
            .order_by('-created_at')
        )
        # Staff see only their own sales; managers see all
        if not self.request.user.is_manager_or_above:
            qs = qs.for_cashier(self.request.user)
        return qs


class SaleDetailView(LoginRequiredMixin, DetailView):
    """
    Sale receipt view. Also serves as the post-checkout 'thank you' page.

    prefetch_related('line_items__product') prevents N+1 on the receipt:
        for item in sale.line_items.all()  ← would be N+1 without prefetch
    With prefetch, line_items AND their products are fetched in 2 extra queries
    (not N) regardless of how many line items are on the sale.
    """
    template_name = 'sales/sale_detail.html'
    context_object_name = 'sale'

    def get_queryset(self):
        qs = (
            Sale.objects
            .select_related('cashier')
            .prefetch_related('line_items__product')
        )
        if not self.request.user.is_manager_or_above:
            qs = qs.for_cashier(self.request.user)
        return qs


class SaleVoidView(ManagerRequiredMixin, DetailView):
    """
    GET  → confirmation page ("Are you sure you want to void sale #X?")
    POST → void the sale and restore inventory via SaleService.void_sale()
    """
    model = Sale
    template_name = 'sales/sale_void_confirm.html'
    context_object_name = 'sale'

    def post(self, request, *args, **kwargs):
        sale = self.get_object()
        try:
            SaleService.void_sale(sale)
            messages.success(
                request,
                f"Sale #{sale.pk} voided and inventory restored.",
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect('sales:sale-detail', pk=sale.pk)
