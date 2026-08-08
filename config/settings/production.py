"""
Production settings.

These are additive security hardening on top of base.  Nothing here relaxes
a restriction from base — it only tightens them.  This file should be the
DJANGO_SETTINGS_MODULE on your production server (set in wsgi.py / gunicorn).
"""
from .base import *  # noqa: F401, F403
import logging

DEBUG = False

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS')  # noqa: F405 — must be explicit in prod

# ---------------------------------------------------------------------------
# HTTPS / HSTS
# ---------------------------------------------------------------------------
# SECURE_SSL_REDIRECT forces HTTP → HTTPS at the Django layer.
# If your load balancer / reverse proxy already does this, set it to False
# to avoid a double-redirect loop.
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31_536_000          # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ---------------------------------------------------------------------------
# COOKIE SECURITY
# ---------------------------------------------------------------------------
SESSION_COOKIE_SECURE = True   # Only transmit session cookie over HTTPS
CSRF_COOKIE_SECURE = True      # Only transmit CSRF cookie over HTTPS
SESSION_COOKIE_AGE = 28800     # 8 hours — reasonable POS session timeout

# ---------------------------------------------------------------------------
# CONTENT SECURITY
# ---------------------------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': env('DJANGO_LOG_LEVEL', default='ERROR'),  # noqa: F405
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}
