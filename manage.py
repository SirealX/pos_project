#!/usr/bin/env python
"""Django's command-line utility for administrative tasks.

Usage:
    python manage.py runserver
    python manage.py makemigrations
    python manage.py migrate
"""
import os
import sys


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Activate your virtual environment: "
            ".\\venv\\Scripts\\Activate.ps1"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
