"""
Base settings shared across all environments.

Architecture note: Settings are split into base / local / production so that
the production config is an explicit, additive layer on top of base — you can
never accidentally ship DEBUG=True because production.py never imports it as True.
Every secret (SECRET_KEY, DATABASE_URL) is read exclusively from the .env file
via django-environ, so there is no risk of committing credentials.
"""
import environ
from pathlib import Path

# BASE_DIR resolves to the repository root (where manage.py lives).
# Path(__file__) → config/settings/base.py
# .parent       → config/settings/
# .parent       → config/
# .parent       → project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / '.env')

# ---------------------------------------------------------------------------
# SECURITY
# ---------------------------------------------------------------------------
SECRET_KEY = env('SECRET_KEY')
DEBUG = env.bool('DEBUG', default=False)
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])

# ---------------------------------------------------------------------------
# APPLICATIONS
# ---------------------------------------------------------------------------
# Grouping INSTALLED_APPS by origin makes it immediately obvious what is
# Django built-in, what is third-party, and what is ours — helpful for audits
# and for understanding app-loading order.
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'crispy_forms',
    'crispy_tailwind',
    'django_htmx',
]

LOCAL_APPS = [
    'apps.users.apps.UsersConfig',
    'apps.inventory.apps.InventoryConfig',
    'apps.sales.apps.SalesConfig',
    'apps.staff.apps.StaffConfig',
    'apps.reports.apps.ReportsConfig',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ---------------------------------------------------------------------------
# MIDDLEWARE
# ---------------------------------------------------------------------------
# WhiteNoiseMiddleware sits directly after SecurityMiddleware so static files
# are served before any session/auth logic runs — correct and efficient.
# HtmxMiddleware adds request.htmx so views can branch on HTMX vs full-page.
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
]

ROOT_URLCONF = 'config.urls'

# ---------------------------------------------------------------------------
# TEMPLATES
# ---------------------------------------------------------------------------
# DIRS points to a top-level templates/ folder for shared base templates.
# APP_DIRS=True lets each app declare its own templates/ subdirectory.
# Both are searched; top-level DIRS take precedence, allowing global overrides.
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# ---------------------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------------------
# env.db() parses a DATABASE_URL string (e.g. postgres://user:pass@host/db)
# into the Django DATABASES dict format.  The sqlite fallback means a developer
# with no Postgres installed can still run the project immediately.
DATABASES = {
    'default': env.db('DATABASE_URL', default=f'sqlite:///{BASE_DIR / "db.sqlite3"}')
}

# ---------------------------------------------------------------------------
# AUTHENTICATION
# ---------------------------------------------------------------------------
# Declaring AUTH_USER_MODEL is the single most important decision in a new
# Django project.  Once you have real migrations, switching is painful.
# Always do this before your first `makemigrations`.
AUTH_USER_MODEL = 'users.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = 'users:login'
LOGIN_REDIRECT_URL = 'sales:pos'
LOGOUT_REDIRECT_URL = 'users:login'

# ---------------------------------------------------------------------------
# INTERNATIONALIZATION
# ---------------------------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = env('TIME_ZONE', default='UTC')
USE_I18N = True
USE_TZ = True  # Always True — store UTC, render local in templates

# ---------------------------------------------------------------------------
# STATIC & MEDIA FILES
# ---------------------------------------------------------------------------
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ---------------------------------------------------------------------------
# DEFAULT PRIMARY KEY
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# CRISPY FORMS
# ---------------------------------------------------------------------------
CRISPY_ALLOWED_TEMPLATE_PACKS = 'tailwind'
CRISPY_TEMPLATE_PACK = 'tailwind'

# ---------------------------------------------------------------------------
# SESSION & CSRF SECURITY (base flags; HTTPS flags added in production.py)
# ---------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

# ---------------------------------------------------------------------------
# BUSINESS LOGIC CONSTANTS
# ---------------------------------------------------------------------------
# Keeping these in settings makes them configurable per environment without
# code changes (e.g. different tax rates per region, different stock thresholds).
TAX_RATE = env.float('TAX_RATE', default=0.0)
LOW_STOCK_THRESHOLD = env.int('LOW_STOCK_THRESHOLD', default=10)
