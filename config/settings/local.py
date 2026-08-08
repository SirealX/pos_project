"""
Local development settings.

Imports everything from base, then overrides or adds dev-only behaviour.
The pattern `from .base import *` is intentional here — this module's entire
purpose is to be a thin override layer, not an independent config file.
"""
from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']

# Use unfingerprinted static files in dev so changes are visible immediately
# without running collectstatic.
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

# Print emails to the console instead of sending them.
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# ---------------------------------------------------------------------------
# Django Debug Toolbar (only activated when the package is installed)
# ---------------------------------------------------------------------------
# We guard with try/except so that running `pip install -r requirements/base.txt`
# (without local.txt) still works — toolbar is a dev-only concern.
try:
    import debug_toolbar  # noqa: F401

    INSTALLED_APPS += ['debug_toolbar']  # noqa: F405
    # Must come early in middleware, right after SecurityMiddleware.
    MIDDLEWARE = [  # noqa: F405
        'debug_toolbar.middleware.DebugToolbarMiddleware',
    ] + MIDDLEWARE  # noqa: F405
    INTERNAL_IPS = ['127.0.0.1']
except ModuleNotFoundError:
    pass
