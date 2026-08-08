"""
ShiftService tests — clock-in/out rules and permission enforcement.

The core invariant: no user should ever have two active shifts simultaneously.
These tests verify that the guard logic (AlreadyClockedInError) fires under
normal single-request conditions. The race-condition prevention (select_for_update)
is tested by the service logic itself; a single-threaded test cannot verify
the lock, but it can confirm the guard fires on the second call.
"""
import pytest

from apps.staff.exceptions import AlreadyClockedInError, NotClockedInError
from apps.staff.models import Shift
from apps.staff.services import ShiftService

from .factories import ActiveShiftFactory, UserFactory, ManagerFactory


# ── clock_in ─────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_clock_in_creates_active_shift():
    user = UserFactory()

    shift = ShiftService.clock_in(user)

    assert shift.pk is not None
    assert shift.employee == user
    assert shift.clock_out is None
    assert shift.is_active


@pytest.mark.django_db
def test_clock_in_persists_to_database():
    user = UserFactory()

    ShiftService.clock_in(user)

    assert Shift.objects.for_employee(user).active().count() == 1


@pytest.mark.django_db
def test_clock_in_twice_raises_already_clocked_in():
    user = UserFactory()
    ShiftService.clock_in(user)

    with pytest.raises(AlreadyClockedInError):
        ShiftService.clock_in(user)


@pytest.mark.django_db
def test_clock_in_after_clock_out_succeeds():
    user = UserFactory()
    ShiftService.clock_in(user)
    ShiftService.clock_out(user)

    shift2 = ShiftService.clock_in(user)  # should not raise

    assert shift2.is_active


# ── clock_out ────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_clock_out_sets_clock_out_time():
    user = UserFactory()
    ShiftService.clock_in(user)

    shift = ShiftService.clock_out(user)

    assert shift.clock_out is not None
    assert not shift.is_active


@pytest.mark.django_db
def test_clock_out_returns_the_shift():
    user = UserFactory()
    created = ShiftService.clock_in(user)

    returned = ShiftService.clock_out(user)

    assert returned.pk == created.pk


@pytest.mark.django_db
def test_clock_out_when_not_clocked_in_raises():
    user = UserFactory()

    with pytest.raises(NotClockedInError):
        ShiftService.clock_out(user)


@pytest.mark.django_db
def test_clock_out_closes_most_recent_shift_if_multiple_exist():
    """
    If a user somehow has two active shifts (e.g. via admin override),
    clock_out() should close the most recently opened one (.last() by clock_in).
    """
    user = UserFactory()
    older = ActiveShiftFactory(employee=user)
    newer = ActiveShiftFactory(employee=user)

    closed = ShiftService.clock_out(user)

    # Most recent shift (newer) is closed
    assert closed.pk == newer.pk
    older.refresh_from_db()
    assert older.is_active  # untouched


# ── force_clock_out ───────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_force_clock_out_by_manager_succeeds():
    manager = ManagerFactory()
    employee = UserFactory()
    ActiveShiftFactory(employee=employee)

    shift = ShiftService.force_clock_out(user=employee, actor=manager)

    assert shift.clock_out is not None


@pytest.mark.django_db
def test_force_clock_out_by_staff_raises_permission_error():
    staff_actor = UserFactory()
    target = UserFactory()
    ActiveShiftFactory(employee=target)

    with pytest.raises(PermissionError):
        ShiftService.force_clock_out(user=target, actor=staff_actor)


@pytest.mark.django_db
def test_force_clock_out_when_not_clocked_in_raises():
    manager = ManagerFactory()
    employee = UserFactory()  # no active shift

    with pytest.raises(NotClockedInError):
        ShiftService.force_clock_out(user=employee, actor=manager)


# ── get_active_shift ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_get_active_shift_returns_none_when_not_clocked_in():
    user = UserFactory()
    assert ShiftService.get_active_shift(user) is None


@pytest.mark.django_db
def test_get_active_shift_returns_shift_when_clocked_in():
    user = UserFactory()
    shift = ShiftService.clock_in(user)

    result = ShiftService.get_active_shift(user)

    assert result.pk == shift.pk
