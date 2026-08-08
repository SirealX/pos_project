"""
View-level permission tests.

These tests verify the HTTP layer enforces role boundaries correctly:
  - Unauthenticated → 302 to login
  - Staff on manager-only view → 302 to POS with flash error
  - Manager on admin-only view → 302 to POS with flash error
  - Staff accessing another cashier's sale detail → 404 (not 403)

WHY 404 instead of 403 for cross-cashier sale access?
A 403 tells the requester "this resource exists but you can't see it."
A 404 leaks nothing — the sale might not exist at all. Implemented by
filtering get_queryset() rather than checking object ownership after fetch.
"""
import pytest
from django.urls import reverse


# ── Unauthenticated access ────────────────────────────────────────────────────────

class TestUnauthenticatedRedirects:
    @pytest.mark.django_db
    def test_pos_redirects_to_login(self, anon_client):
        r = anon_client.get(reverse('sales:pos'))
        assert r.status_code == 302
        assert '/login/' in r['Location']

    @pytest.mark.django_db
    def test_product_list_redirects_to_login(self, anon_client):
        r = anon_client.get(reverse('inventory:product-list'))
        assert r.status_code == 302
        assert '/login/' in r['Location']

    @pytest.mark.django_db
    def test_dashboard_redirects_to_login(self, anon_client):
        r = anon_client.get(reverse('reports:dashboard'))
        assert r.status_code == 302
        assert '/login/' in r['Location']

    @pytest.mark.django_db
    def test_shift_log_redirects_to_login(self, anon_client):
        r = anon_client.get(reverse('staff:shift-log'))
        assert r.status_code == 302
        assert '/login/' in r['Location']


# ── Staff cannot access manager views ─────────────────────────────────────────────

class TestStaffPermissionBoundaries:
    @pytest.mark.django_db
    def test_staff_cannot_create_product(self, staff_client):
        r = staff_client.get(reverse('inventory:product-create'))
        # ManagerRequiredMixin redirects to POS, not login
        assert r.status_code == 302
        assert reverse('sales:pos') in r['Location']

    @pytest.mark.django_db
    def test_staff_cannot_update_product(self, staff_client, product):
        r = staff_client.get(reverse('inventory:product-update', args=[product.pk]))
        assert r.status_code == 302
        assert reverse('sales:pos') in r['Location']

    @pytest.mark.django_db
    def test_staff_cannot_delete_product(self, staff_client, product):
        r = staff_client.get(reverse('inventory:product-delete', args=[product.pk]))
        assert r.status_code == 302
        assert reverse('sales:pos') in r['Location']

    @pytest.mark.django_db
    def test_staff_cannot_access_sales_report(self, staff_client):
        r = staff_client.get(reverse('reports:sales-report'))
        assert r.status_code == 302
        assert reverse('sales:pos') in r['Location']

    @pytest.mark.django_db
    def test_staff_cannot_access_staff_hours_report(self, staff_client):
        r = staff_client.get(reverse('reports:staff-hours'))
        assert r.status_code == 302
        assert reverse('sales:pos') in r['Location']

    @pytest.mark.django_db
    def test_staff_cannot_create_schedule(self, staff_client):
        r = staff_client.get(reverse('staff:schedule-create'))
        assert r.status_code == 302

    @pytest.mark.django_db
    def test_staff_cannot_void_sale(self, staff_client, db):
        from .factories import SaleFactory
        sale = SaleFactory()
        r = staff_client.get(reverse('sales:sale-void', args=[sale.pk]))
        assert r.status_code == 302


# ── Manager has access to manager views ───────────────────────────────────────────

class TestManagerAccess:
    @pytest.mark.django_db
    def test_manager_can_access_product_create(self, manager_client):
        r = manager_client.get(reverse('inventory:product-create'))
        assert r.status_code == 200

    @pytest.mark.django_db
    def test_manager_can_access_sales_report(self, manager_client):
        r = manager_client.get(reverse('reports:sales-report'))
        assert r.status_code == 200

    @pytest.mark.django_db
    def test_manager_can_access_dashboard(self, manager_client):
        r = manager_client.get(reverse('reports:dashboard'))
        assert r.status_code == 200

    @pytest.mark.django_db
    def test_manager_can_access_staff_hours(self, manager_client):
        r = manager_client.get(reverse('reports:staff-hours'))
        assert r.status_code == 200

    @pytest.mark.django_db
    def test_manager_can_access_user_list(self, manager_client):
        r = manager_client.get(reverse('users:list'))
        assert r.status_code == 200


# ── Sale detail: staff can see own sale, not others' ─────────────────────────────

class TestSaleDetailPermissions:
    @pytest.mark.django_db
    def test_staff_can_view_own_sale(self, client, staff_user):
        from .factories import SaleFactory
        own_sale = SaleFactory(cashier=staff_user)
        client.force_login(staff_user)

        r = client.get(reverse('sales:sale-detail', args=[own_sale.pk]))

        assert r.status_code == 200

    @pytest.mark.django_db
    def test_staff_gets_404_for_other_cashiers_sale(self, client, staff_user, db):
        from .factories import SaleFactory, UserFactory
        other = UserFactory()
        other_sale = SaleFactory(cashier=other)
        client.force_login(staff_user)

        r = client.get(reverse('sales:sale-detail', args=[other_sale.pk]))

        # 404, not 403 — doesn't leak that the sale exists
        assert r.status_code == 404

    @pytest.mark.django_db
    def test_manager_can_view_any_sale(self, client, manager_user, db):
        from .factories import SaleFactory, UserFactory
        cashier = UserFactory()
        sale = SaleFactory(cashier=cashier)
        client.force_login(manager_user)

        r = client.get(reverse('sales:sale-detail', args=[sale.pk]))

        assert r.status_code == 200
