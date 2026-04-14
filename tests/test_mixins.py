"""
Tests for shellcraft/mixins.py.

Key design decisions:
- pytest-django sets DEBUG=False by default (mirrors Django's own test runner).
  shellcraft.inject() refuses to run when DEBUG=False.  The ``restore_inject``
  autouse fixture sets DEBUG=True via pytest-django's ``settings`` fixture so
  that every test that needs inject() can call it freely.  Tests that
  specifically verify the DEBUG=False guard set settings.DEBUG=False themselves.

- The ``restore_inject`` fixture saves and restores the global _INJECTED flag
  AND every attribute that inject() adds to django.db.models.Model, so test
  ordering never matters.

- DB tests use @pytest.mark.django_db (pytest-django creates the schema
  automatically using the in-memory SQLite database from conftest.py).
"""
import warnings

import pytest
import shellcraft.mixins as _mixins_module
from shellcraft.mixins import _safe_inject, inject

# Names that inject() adds to django.db.models.Model.
_INJECTED_NAMES = (
    "find", "all", "where", "first", "last", "count", "fields",
    "update", "destroy",
)


@pytest.fixture(autouse=True)
def restore_inject(settings):
    """
    Ensure every test runs with DEBUG=True and a clean injection state.

    Why DEBUG=True: pytest-django sets DEBUG=False by default; inject() raises
    RuntimeError when DEBUG=False, so we need to explicitly enable it here.
    Tests that verify the DEBUG=False guard override it themselves.

    The fixture saves/restores Model attributes so tests are hermetic.
    """
    # Guarantee inject() can run in tests that don't test the guard.
    settings.DEBUG = True

    from django.db import models

    original_injected = _mixins_module._INJECTED
    original_attrs = {
        name: models.Model.__dict__.get(name)   # None if not present
        for name in _INJECTED_NAMES
    }

    yield

    # Restore _INJECTED flag.
    _mixins_module._INJECTED = original_injected

    # Restore (or remove) each attribute on Model.
    for name, original in original_attrs.items():
        if original is None:
            # inject() added it — remove it.
            try:
                delattr(models.Model, name)
            except AttributeError:
                pass
        else:
            setattr(models.Model, name, original)


# ---------------------------------------------------------------------------
# inject() — idempotency
# ---------------------------------------------------------------------------

class TestInjectIdempotency:
    def test_second_call_is_noop(self):
        """inject() called twice must not double-patch or raise."""
        _mixins_module._INJECTED = False
        inject()
        inject()  # second call — must be silent
        assert _mixins_module._INJECTED is True

    def test_sets_injected_flag(self):
        _mixins_module._INJECTED = False
        inject()
        assert _mixins_module._INJECTED is True

    def test_methods_present_after_inject(self):
        from django.db import models
        _mixins_module._INJECTED = False
        inject()
        for name in _INJECTED_NAMES:
            assert hasattr(models.Model, name), f"Model.{name} missing after inject()"


# ---------------------------------------------------------------------------
# inject() — FIX: production guard
# ---------------------------------------------------------------------------

class TestInjectProductionGuard:
    def test_raises_when_debug_false(self, settings):
        """inject() must raise RuntimeError when DEBUG=False."""
        settings.DEBUG = False
        _mixins_module._INJECTED = False
        with pytest.raises(RuntimeError, match="DEBUG=False"):
            inject()

    def test_does_not_set_flag_when_debug_false(self, settings):
        """If inject() raises, _INJECTED must remain False."""
        settings.DEBUG = False
        _mixins_module._INJECTED = False
        with pytest.raises(RuntimeError):
            inject()
        assert _mixins_module._INJECTED is False

    def test_succeeds_when_debug_true(self, settings):
        settings.DEBUG = True
        _mixins_module._INJECTED = False
        inject()   # must not raise
        assert _mixins_module._INJECTED is True


# ---------------------------------------------------------------------------
# _safe_inject — collision warning
# ---------------------------------------------------------------------------

class TestSafeInject:
    def test_injects_new_method(self):
        from django.db import models
        sentinel = object()
        _safe_inject(models.Model, "_sc_test_sentinel", sentinel)
        assert models.Model._sc_test_sentinel is sentinel
        delattr(models.Model, "_sc_test_sentinel")

    def test_warns_on_collision(self):
        from django.db import models
        # Add a temporary attribute to Model to simulate a collision.
        models.Model._sc_collision_test = lambda self: None
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                _safe_inject(models.Model, "_sc_collision_test", lambda: None)
            assert len(caught) == 1
            assert "_sc_collision_test" in str(caught[0].message)
        finally:
            del models.Model._sc_collision_test

    def test_collision_leaves_original_intact(self):
        from django.db import models
        original = lambda self: "original"  # noqa: E731
        models.Model._sc_intact_test = original
        try:
            _safe_inject(models.Model, "_sc_intact_test", lambda: "replacement")
            assert models.Model._sc_intact_test is original
        finally:
            del models.Model._sc_intact_test


# ---------------------------------------------------------------------------
# _update — FIX: dunder key rejection
# ---------------------------------------------------------------------------

class TestUpdateDunderRejection:
    def test_rejects_dunder_key(self):
        """user.update(__class__=X) must raise ValueError immediately."""
        _mixins_module._INJECTED = False
        inject()
        from django.contrib.auth.models import User
        u = User.__new__(User)
        with pytest.raises(ValueError, match="private or dunder"):
            u.update(__class__=object)

    def test_rejects_single_underscore_key(self):
        _mixins_module._INJECTED = False
        inject()
        from django.contrib.auth.models import User
        u = User.__new__(User)
        with pytest.raises(ValueError, match="private or dunder"):
            u.update(_state=None)

    def test_accepts_valid_field_name(self):
        """A recognised field name must not raise — tested via save() mock."""
        _mixins_module._INJECTED = False
        inject()
        from unittest.mock import patch
        from django.contrib.auth.models import User
        u = User(username="original")
        with patch.object(u, "save") as mock_save:
            result = u.update(username="updated")
        assert u.username == "updated"
        mock_save.assert_called_once()
        assert result is u


# ---------------------------------------------------------------------------
# _update — FIX: unknown field warning
# ---------------------------------------------------------------------------

class TestUpdateUnknownFieldWarning:
    def test_warns_for_unknown_field(self):
        _mixins_module._INJECTED = False
        inject()
        from unittest.mock import patch
        from django.contrib.auth.models import User
        u = User(username="x")
        with patch.object(u, "save"):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                u.update(nonexistent_field="value")
        assert any("nonexistent_field" in str(w.message) for w in caught)

    def test_no_warning_for_valid_field(self):
        _mixins_module._INJECTED = False
        inject()
        from unittest.mock import patch
        from django.contrib.auth.models import User
        u = User(username="x")
        with patch.object(u, "save"):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                u.update(username="new")
        shellcraft_warnings = [
            w for w in caught if "shellcraft" in str(w.message)
        ]
        assert shellcraft_warnings == []


# ---------------------------------------------------------------------------
# Class methods — FIX: return values (was returning None)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestMethodReturnValues:
    """Verify that _all, _where, _first, _last return their result so
    developers can do ``users = User.all()`` and get a real queryset/instance.
    """

    def test_all_returns_queryset(self, capsys):
        _mixins_module._INJECTED = False
        inject()
        from django.contrib.auth.models import User
        result = User.all()
        capsys.readouterr()  # discard printed output
        assert result is not None
        assert hasattr(result, 'count')

    def test_where_returns_queryset(self, capsys):
        _mixins_module._INJECTED = False
        inject()
        from django.contrib.auth.models import User
        result = User.where(is_active=True)
        capsys.readouterr()
        assert result is not None
        assert hasattr(result, 'count')

    def test_first_returns_none_on_empty_table(self, capsys):
        _mixins_module._INJECTED = False
        inject()
        from django.contrib.auth.models import User
        # No users in DB — should return None, not raise
        result = User.first()
        capsys.readouterr()
        assert result is None

    def test_last_returns_none_on_empty_table(self, capsys):
        _mixins_module._INJECTED = False
        inject()
        from django.contrib.auth.models import User
        result = User.last()
        capsys.readouterr()
        assert result is None


# ---------------------------------------------------------------------------
# destroy — delegates to .delete()
# ---------------------------------------------------------------------------

class TestDestroy:
    def test_destroy_calls_delete(self):
        _mixins_module._INJECTED = False
        inject()
        from unittest.mock import patch
        from django.contrib.auth.models import User
        u = User(username="bye")
        delete_return = (1, {"auth.User": 1})
        with patch.object(u, "delete", return_value=delete_return) as mock_del:
            result = u.destroy()
        mock_del.assert_called_once()
        assert result == delete_return


# ---------------------------------------------------------------------------
# find — propagates DoesNotExist
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestFind:
    def test_find_raises_for_missing_pk(self):
        _mixins_module._INJECTED = False
        inject()
        from django.contrib.auth.models import User
        with pytest.raises(User.DoesNotExist):
            User.find(99999)

    def test_find_returns_instance(self):
        _mixins_module._INJECTED = False
        inject()
        from django.contrib.auth.models import User
        created = User.objects.create_user(username="findme", password="x")
        result = User.find(created.pk)
        assert result.pk == created.pk


# ---------------------------------------------------------------------------
# FIX GAP: _first() / _last() when the table has records (mixins.py:57, 63)
#
# Existing tests only covered the empty-table path (return None).
# These tests exercise the non-None branch where ap(obj) is printed.
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestFirstLastWithData:
    """_first() and _last() must print AND return the instance when a row exists."""

    def test_first_returns_instance_when_record_exists(self, capsys):
        _mixins_module._INJECTED = False
        inject()
        from django.contrib.auth.models import User
        created = User.objects.create_user(username="first_user", password="x")
        result = User.first()
        capsys.readouterr()
        assert result is not None
        assert result.pk == created.pk

    def test_first_prints_record_when_record_exists(self, capsys):
        """ap(obj) must be called — output must contain the model header."""
        _mixins_module._INJECTED = False
        inject()
        from django.contrib.auth.models import User
        User.objects.create_user(username="first_printed", password="x")
        User.first()
        out = capsys.readouterr().out
        assert '#<User:' in out

    def test_last_returns_instance_when_record_exists(self, capsys):
        _mixins_module._INJECTED = False
        inject()
        from django.contrib.auth.models import User
        created = User.objects.create_user(username="last_user", password="x")
        result = User.last()
        capsys.readouterr()
        assert result is not None
        assert result.pk == created.pk

    def test_last_prints_record_when_record_exists(self, capsys):
        """ap(obj) must be called — output must contain the model header."""
        _mixins_module._INJECTED = False
        inject()
        from django.contrib.auth.models import User
        User.objects.create_user(username="last_printed", password="x")
        User.last()
        out = capsys.readouterr().out
        assert '#<User:' in out

    def test_first_and_last_return_different_records(self, capsys):
        """With multiple rows, first() and last() must return distinct instances."""
        _mixins_module._INJECTED = False
        inject()
        from django.contrib.auth.models import User
        u1 = User.objects.create_user(username="alpha", password="x")
        u2 = User.objects.create_user(username="omega", password="x")
        first = User.first()
        last  = User.last()
        capsys.readouterr()
        assert first.pk == u1.pk
        assert last.pk  == u2.pk
        assert first.pk != last.pk


# ---------------------------------------------------------------------------
# FIX GAP: _count() and _fields() — zero dedicated tests (mixins.py:67, 70)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCountAndFields:
    """Dedicated tests for _count() and _fields(), previously untested."""

    # --- _count() ---

    def test_count_returns_zero_on_empty_table(self):
        _mixins_module._INJECTED = False
        inject()
        from django.contrib.auth.models import User
        result = User.count()
        assert result == 0

    def test_count_returns_integer(self):
        _mixins_module._INJECTED = False
        inject()
        from django.contrib.auth.models import User
        assert isinstance(User.count(), int)

    def test_count_reflects_created_rows(self):
        _mixins_module._INJECTED = False
        inject()
        from django.contrib.auth.models import User
        User.objects.create_user(username="c1", password="x")
        User.objects.create_user(username="c2", password="x")
        assert User.count() == 2

    def test_count_is_silent(self, capsys):
        """_count() must return a value without printing anything."""
        _mixins_module._INJECTED = False
        inject()
        from django.contrib.auth.models import User
        User.count()
        assert capsys.readouterr().out == ""

    # --- _fields() ---

    def test_fields_prints_model_name(self, capsys):
        _mixins_module._INJECTED = False
        inject()
        from django.contrib.auth.models import User
        User.fields()
        out = capsys.readouterr().out
        assert 'User' in out

    def test_fields_prints_at_least_one_field_name(self, capsys):
        _mixins_module._INJECTED = False
        inject()
        from django.contrib.auth.models import User
        User.fields()
        out = capsys.readouterr().out
        # auth.User always has id, username, email, etc.
        assert ':id' in out or ':username' in out

    def test_fields_returns_none(self, capsys):
        """_fields() prints the schema but has no return value."""
        _mixins_module._INJECTED = False
        inject()
        from django.contrib.auth.models import User
        result = User.fields()
        capsys.readouterr()
        assert result is None

    def test_fields_output_contains_opening_brace(self, capsys):
        """Schema output must match the format: ModelName { ... }"""
        _mixins_module._INJECTED = False
        inject()
        from django.contrib.auth.models import User
        User.fields()
        out = capsys.readouterr().out
        assert '{' in out
        assert '}' in out


# ---------------------------------------------------------------------------
# FIX GAP: _update() real DB persistence (previously only mock-patched save)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestUpdatePersistence:
    """Verify that _update() actually persists changes to the database."""

    def test_update_persists_field_to_db(self):
        _mixins_module._INJECTED = False
        inject()
        from django.contrib.auth.models import User
        user = User.objects.create_user(username="before_update", password="x")
        user.update(username="after_update")
        refreshed = User.objects.get(pk=user.pk)
        assert refreshed.username == "after_update"

    def test_update_returns_self_after_save(self):
        _mixins_module._INJECTED = False
        inject()
        from django.contrib.auth.models import User
        user = User.objects.create_user(username="selfcheck", password="x")
        result = user.update(username="selfcheck_new")
        assert result is user

    def test_update_multiple_fields(self):
        _mixins_module._INJECTED = False
        inject()
        from django.contrib.auth.models import User
        user = User.objects.create_user(
            username="multi_before", email="old@example.com", password="x"
        )
        user.update(username="multi_after", email="new@example.com")
        refreshed = User.objects.get(pk=user.pk)
        assert refreshed.username == "multi_after"
        assert refreshed.email    == "new@example.com"
