# POS System

A backend-focused Point of Sale system built with Django. I started this after repeatedly seeing the same operational gaps at businesses using off-the-shelf POS software for tasks it wasn't really built for inventory counts drifting out of sync, sales not always registering, no real way to handle staff scheduling from the same tool. The software itself wasn't bad, it just wasn't purpose-built for those specific tasks, and running into it firsthand at two different jobs was what got me to actually sit down and build something myself. I wanted to understand how POS software works from the data model up, not just how to use one.

**Stack:** Python 3.13 · Django 5.2 · SQLite (Postgres-ready) · Tailwind CSS · HTMX · pytest-django

---

## What it does

- **Product & inventory management** — category-aware product catalogue with per-product low-stock thresholds, cost tracking for margin reporting, and SKU-based lookup
- **Point of sale flow** — cart session → checkout → completed sale with line items, tax calculation, and cash change computation
- **Concurrency-safe stock deduction** — uses `select_for_update()` + Django `F()` expressions to prevent overselling under concurrent transactions
- **Staff management** — custom user model with role-based access (Admin / Manager / Staff), clock-in/out tracking, and manager-created shift scheduling as two separate models
- **Sales reporting** — revenue totals, top products, and gross margin breakdowns filtered by date range
- **Void & reversal flow** — completed sales can be voided with automatic inventory restoration

---

## Architecture decisions worth noting

### Service layer over fat views

Business logic lives in `SaleService`, not in views. The `create_from_cart()` method owns the entire checkout transaction — stock locking, validation, line item creation, inventory deduction, and state transitions in one atomic operation. Views just call the service and handle the HTTP response.

```
apps/
├── inventory/   — Product, Category, custom QuerySet managers
├── sales/       — Sale, SaleLineItem, CartService, SaleService
├── staff/       — Shift (clock records) + ScheduledShift (future schedule)
├── users/       — Custom AbstractUser with role field
└── reports/     — Aggregation views over completed sales
```

### The oversell problem

A naive POS implementation reads stock into Python, checks it, then writes the decremented value back:

```python
# Broken — two concurrent cashiers can both read stock=1, both pass the check,
# and both complete the sale. You end up at stock=0 with two sold items.
product.stock -= quantity
product.save()
```

This system fixes it with two layers:

1. `select_for_update()` acquires a row-level lock before any check, so a second transaction blocks until the first commits and re-reads the updated value
2. `F('stock_quantity') - quantity` moves the subtraction into the database, eliminating any stale Python value from the deduction itself

### Shift vs ScheduledShift

The original implementation used a single `Shift` model with nullable fields for both clock records and future schedules. This created ambiguous queries and made `unique_together` constraints impossible (you can't prevent duplicate scheduled days without also blocking multiple clock-in records for the same person).

Two models with single responsibilities makes both the queries and the constraints self-documenting.

### Custom User model with role

Role lives directly on `User` rather than a separate `Employee` profile table. Permission checks are a single attribute read with no JOIN, and you can filter efficiently with a DB index. The profile-table pattern works but costs a query on every permission check.

---

## Setup

```bash
git clone https://github.com/SirealX/pos-system
cd pos-system
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements/local.txt  # use requirements/production.txt for deployment

# Create a .env file in the project root (see "Environment variables" below)

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

The app uses split settings (`config/settings/base.py`, `local.py`, `production.py`). `manage.py` defaults `DJANGO_SETTINGS_MODULE` to `config.settings.local`; set the environment variable explicitly to run against `config.settings.production`.

### Environment variables

Create a `.env` file in the project root (gitignored, never committed) with:

| Variable              | Required           | Default               | Notes                                               |
| --------------------- | ------------------ | --------------------- | --------------------------------------------------- |
| `SECRET_KEY`          | Yes                | —                     | Generate your own                                   |
| `DEBUG`               | No                 | `False`               | Set `True` for local development                    |
| `DATABASE_URL`        | No                 | SQLite (`db.sqlite3`) | Set to a `postgres://` URL to run against Postgres  |
| `ALLOWED_HOSTS`       | Only in production | `[]`                  | Comma-separated, e.g. `example.com,www.example.com` |
| `TIME_ZONE`           | No                 | `UTC`                 | IANA name, e.g. `America/New_York`                  |
| `TAX_RATE`            | No                 | `0.0`                 | Decimal, e.g. `0.08` for 8%                         |
| `LOW_STOCK_THRESHOLD` | No                 | `10`                  | Quantity that triggers the low-stock warning        |

Minimum to get running locally on SQLite:

```
SECRET_KEY=<generate one>
DEBUG=True
```

---

## Running tests

```bash
pytest
```

Tests cover the sale creation flow, stock deduction, void/reversal, and the concurrency guards in `SaleService`.

---

## What I learned building this

Going in I understood Django's ORM basics. Coming out I have a much clearer picture of where real bugs hide in business logic — specifically the class of bugs that only appear under concurrent load. The oversell problem isn't obvious until you think through the read-modify-write cycle carefully. `select_for_update()` and `F()` expressions both existed in Django before I started; understanding _why_ they exist, not just _how_ to call them, was the actual lesson.

The architecture refactor (splitting `core` into focused apps, moving logic into a service layer, separating `Shift` from `ScheduledShift`) reinforced how much easier code is to reason about when each piece has one clear responsibility.

---

## Status

Currently runs on SQLite locally. Deployment and a proper frontend are the next steps before this is fully portfolio-ready. The data model and backend logic are solid — the gaps are presentation, not substance.
