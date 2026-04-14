"""
Pytest configuration for django-shellcraft tests.

Django must be configured before any test module is imported that touches
``django.db``, ``django.conf.settings``, or any model.  pytest-django does
this automatically when DJANGO_SETTINGS_MODULE is set, but since this package
ships with no settings file we configure Django inline here instead.

The configuration is intentionally minimal:
- SQLite in-memory so no file is left behind and tests are fast.
- Only apps required by django.contrib.auth (our real model under test).
- DEBUG=True so inject() can run without raising.
"""
import django
from django.conf import settings


def pytest_configure(config):
    if not settings.configured:
        settings.configure(
            INSTALLED_APPS=[
                "django.contrib.contenttypes",
                "django.contrib.auth",
            ],
            DATABASES={
                "default": {
                    "ENGINE": "django.db.backends.sqlite3",
                    "NAME": ":memory:",
                }
            },
            DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
            DEBUG=True,
        )
