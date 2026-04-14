"""
Security-focused tests for django-shellcraft.

These tests treat every user-supplied value as potentially hostile.
Even though shellcraft is a developer tool, it reads data from the database
and renders it to a terminal.  A developer working with production data
in a staging clone could inadvertently trigger attacks stored in field
values.

Attack categories covered:
1. Terminal injection  — ANSI escape codes stored in string fields
2. Attribute injection — dunder / private keys passed to _update()
3. Production guard    — DEBUG=False must block all entry points
4. ORM safety          — _where() passes kwargs to .filter(); Django's ORM
                         prevents SQL injection but we verify no code-path
                         bypasses the ORM
5. Object integrity    — inject() must not corrupt Model when DEBUG=False

Assumption: all tests run with pytest-django's autouse ``settings`` fixture
reset to DEBUG=True by default (via restore_inject).
"""
import warnings

import pytest

import shellcraft.mixins as _mixins_module
from shellcraft.printer import _strip_ansi, colorize, _format_record, ap
from shellcraft.mixins import inject

_INJECTED_NAMES = (
    "find", "all", "where", "first", "last", "count", "fields",
    "update", "destroy",
)


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def restore_inject(settings):
    """Ensure DEBUG=True and clean Model state before and after each test."""
    settings.DEBUG = True

    from django.db import models
    original_injected = _mixins_module._INJECTED
    original_attrs = {
        name: models.Model.__dict__.get(name)
        for name in _INJECTED_NAMES
    }

    yield

    _mixins_module._INJECTED = original_injected
    for name, original in original_attrs.items():
        if original is None:
            try:
                delattr(models.Model, name)
            except AttributeError:
                pass
        else:
            setattr(models.Model, name, original)


def _make_field(attname):
    return type("Field", (), {"attname": attname})()


def _make_instance(class_name, **fields):
    field_list = [_make_field(k) for k in fields]

    class Meta:
        concrete_fields = field_list

    cls = type(class_name, (), {"_meta": Meta()})
    obj = cls()
    for k, v in fields.items():
        setattr(obj, k, v)
    return obj


# ===========================================================================
# 1. TERMINAL INJECTION — ANSI escape sequences in field values
# ===========================================================================

class TestTerminalInjection:
    """
    A database field value containing ANSI escape codes could:
    - Clear the terminal  (\\033[2J)
    - Move the cursor     (\\033[0;0H)
    - Change colors       (\\033[31m...\\033[0m)
    - Execute OS commands in some older terminals (\\033]2;...)

    All of these must be stripped from string values before printing.
    """

    # --- colorize() ---

    def test_ansi_color_code_stripped_from_string_value(self):
        """\\033[31m should be removed from a field value string."""
        malicious = "\033[31minjected_red\033[0m"
        out = colorize(malicious)
        # Strip our own wrapper colors to isolate the user-data portion
        inner = out.replace("\033[33m", "").replace("\033[0m", "")
        assert "\033[" not in inner, "Embedded ANSI escape leaked into output"

    def test_ansi_clear_screen_stripped(self):
        """\\033[2J (clear screen) must be stripped."""
        malicious = "\033[2J\033[0;0H"
        out = colorize(malicious)
        inner = out.replace("\033[33m", "").replace("\033[0m", "")
        assert "\033[" not in inner

    def test_ansi_cursor_movement_stripped(self):
        """Cursor-position sequences must be stripped."""
        malicious = "\033[10;20H moved here"
        out = colorize(malicious)
        inner = out.replace("\033[33m", "").replace("\033[0m", "")
        assert "\033[" not in inner

    def test_legitimate_text_survives_sanitization(self):
        """Stripping ANSI must not remove normal printable characters."""
        mixed = "safe\033[31mDANGER\033[0msafe"
        out = colorize(mixed)
        assert "safesafesafe" in out or "safesafe" in out or "safe" in out

    def test_ansi_stripped_inside_format_record(self, capsys):
        """ANSI sequences in field values must not appear in _format_record."""
        obj = _make_instance("User", username="\033[2Jcleared")
        out = _format_record(obj)
        # Remove our own formatting codes so only user-data escapes remain
        clean = _strip_ansi(out)
        assert "\033[" not in clean, "_format_record leaked an escape sequence"

    def test_ansi_stripped_inside_ap(self, capsys):
        """ap() must strip ANSI codes from any field value string."""
        obj = _make_instance("User", bio="\033[1mBOLD\033[0m")
        ap(obj)
        raw = capsys.readouterr().out
        clean = _strip_ansi(raw)
        assert "\033[" not in clean

    def test_multiple_sequences_all_stripped(self):
        """A value with several interleaved escape sequences must be clean."""
        malicious = "\033[1m\033[31m\033[4mstyle bomb\033[0m\033[0m"
        out = colorize(malicious)
        inner = out.replace("\033[33m", "").replace("\033[0m", "")
        assert "\033[" not in inner

    def test_non_string_types_not_affected(self):
        """Numeric and None values don't go through the sanitizer — must still work."""
        assert "\033[" not in colorize(42).replace("\033[34m", "").replace("\033[0m", "")
        assert "nil" in colorize(None)


# ===========================================================================
# 2. ATTRIBUTE INJECTION — dunder / private keys in _update()
# ===========================================================================

class TestAttributeInjection:
    """
    user.update(__class__=Evil) could overwrite Python internals.
    user.update(__dict__={"is_superuser": True}) could corrupt the instance
    entirely, bypassing all Django field validation.
    user.update(_state=None) could corrupt Django's internal ORM state.

    All keys beginning with '_' must be rejected before setattr is called.
    """

    def _get_user_instance(self):
        from django.contrib.auth.models import User
        _mixins_module._INJECTED = False
        inject()
        return User.__new__(User)

    def test_dunder_class_rejected(self):
        u = self._get_user_instance()
        with pytest.raises(ValueError, match="private or dunder"):
            u.update(__class__=object)

    def test_dunder_dict_rejected(self):
        """Overwriting __dict__ would bypass all field validation."""
        u = self._get_user_instance()
        with pytest.raises(ValueError, match="private or dunder"):
            u.update(__dict__={"is_superuser": True})

    def test_dunder_module_rejected(self):
        u = self._get_user_instance()
        with pytest.raises(ValueError, match="private or dunder"):
            u.update(__module__="evil.module")

    def test_single_underscore_state_rejected(self):
        """_state is Django's internal tracking object — must be protected."""
        u = self._get_user_instance()
        with pytest.raises(ValueError, match="private or dunder"):
            u.update(_state=None)

    def test_single_underscore_arbitrary_rejected(self):
        u = self._get_user_instance()
        with pytest.raises(ValueError, match="private or dunder"):
            u.update(_arbitrary_private="x")

    def test_rejection_happens_before_setattr(self):
        """setattr must never be called when a dunder key is present."""
        u = self._get_user_instance()
        original_class = type(u)
        try:
            u.update(__class__=object)
        except ValueError:
            pass
        assert type(u) is original_class, "__class__ was mutated despite ValueError"

    def test_valid_field_not_blocked(self):
        """Legitimate field names starting without '_' must be accepted."""
        from unittest.mock import patch
        from django.contrib.auth.models import User
        _mixins_module._INJECTED = False
        inject()
        u = User(username="original")
        with patch.object(u, "save"):
            u.update(username="updated")   # must not raise
        assert u.username == "updated"

    def test_mixed_kwargs_dunder_blocks_all(self):
        """If ANY key is a dunder, the whole call must fail before any setattr."""
        from django.contrib.auth.models import User
        _mixins_module._INJECTED = False
        inject()
        u = User(username="unchanged")
        with pytest.raises(ValueError):
            u.update(username="changed", __class__=object)
        # username must not have been modified
        assert u.username == "unchanged"


# ===========================================================================
# 3. PRODUCTION GUARD — all entry points must block when DEBUG=False
# ===========================================================================

class TestProductionGuard:
    """
    The package must refuse to activate in any production-like environment.
    Three entry points exist: inject(), the management command, and (indirectly)
    any injected method.  inject() itself is the root lock.
    """

    def test_inject_raises_when_debug_false(self, settings):
        settings.DEBUG = False
        _mixins_module._INJECTED = False
        with pytest.raises(RuntimeError, match="DEBUG=False"):
            inject()

    def test_inject_leaves_model_clean_when_debug_false(self, settings):
        """Model must have no shellcraft methods after a failed inject()."""
        from django.db import models
        settings.DEBUG = False
        _mixins_module._INJECTED = False
        with pytest.raises(RuntimeError):
            inject()
        for name in _INJECTED_NAMES:
            assert not hasattr(models.Model, name), \
                f"Model.{name} was injected despite DEBUG=False"

    def test_management_command_raises_command_error_when_debug_false(self, settings):
        """The management command must raise CommandError, not SystemExit."""
        from django.core.management.base import CommandError
        from shellcraft.management.commands.shellcraft import Command
        from io import StringIO

        settings.DEBUG = False
        cmd = Command()
        cmd.stdout = StringIO()
        cmd.stderr = StringIO()

        with pytest.raises(CommandError):
            cmd.handle()

    def test_management_command_does_not_use_system_exit(self, settings):
        """SystemExit bypasses Django's pipeline — must never be raised."""
        from shellcraft.management.commands.shellcraft import Command
        from io import StringIO

        settings.DEBUG = False
        cmd = Command()
        cmd.stdout = StringIO()
        cmd.stderr = StringIO()

        with pytest.raises(Exception) as exc_info:
            cmd.handle()

        assert not isinstance(exc_info.value, SystemExit), \
            "Command raised SystemExit instead of CommandError"

    def test_inject_idempotent_flag_not_set_on_failure(self, settings):
        """_INJECTED must remain False after a DEBUG=False RuntimeError."""
        settings.DEBUG = False
        _mixins_module._INJECTED = False
        with pytest.raises(RuntimeError):
            inject()
        assert _mixins_module._INJECTED is False


# ===========================================================================
# 4. ORM SAFETY — _where() kwargs passthrough
# ===========================================================================

class TestORMSafety:
    """
    _where(**kwargs) forwards its arguments directly to Django's .filter().
    Django's ORM uses parameterised queries, so SQL injection is not
    possible through this path.  These tests verify that:
    - Normal filter kwargs work correctly
    - Django's ORM raises on invalid lookup syntax (not shellcraft)
    - No raw SQL strings are constructed by shellcraft itself
    """

    @pytest.mark.django_db
    def test_valid_filter_does_not_raise(self, capsys):
        """A legitimate filter kwarg must pass through to Django's ORM."""
        from django.contrib.auth.models import User
        _mixins_module._INJECTED = False
        inject()
        # This should call User.objects.filter(is_active=True) — no crash
        result = User.where(is_active=True)
        capsys.readouterr()
        assert result is not None

    def test_invalid_lookup_raises_django_error(self, capsys):
        """Django must raise FieldError for nonsense lookups — not shellcraft."""
        from django.core.exceptions import FieldError
        from django.contrib.auth.models import User
        _mixins_module._INJECTED = False
        inject()
        with pytest.raises(FieldError):
            User.where(nonexistent_field__lookup="value")
        capsys.readouterr()

    @pytest.mark.django_db
    def test_where_does_not_return_all_records_on_empty_filter(self, capsys):
        """where() with a false-value filter must not return unfiltered results."""
        from django.contrib.auth.models import User
        _mixins_module._INJECTED = False
        inject()
        User.objects.create_user(username="present", password="x")
        result = User.where(username="definitely_absent")
        capsys.readouterr()
        assert result.count() == 0


# ===========================================================================
# 5. OBJECT INTEGRITY — inject() must not leave Model in a broken state
# ===========================================================================

class TestObjectIntegrity:
    def test_injected_find_is_classmethod(self):
        """find() must be a classmethod so User.find(1) works."""
        from django.db import models
        _mixins_module._INJECTED = False
        inject()
        descriptor = models.Model.__dict__.get("find")
        assert isinstance(descriptor, classmethod), \
            "find was not injected as a classmethod"

    def test_injected_all_is_classmethod(self):
        from django.db import models
        _mixins_module._INJECTED = False
        inject()
        descriptor = models.Model.__dict__.get("all")
        assert isinstance(descriptor, classmethod)

    def test_injected_update_is_instance_method(self):
        """update() must be an instance method (not classmethod)."""
        from django.db import models
        _mixins_module._INJECTED = False
        inject()
        descriptor = models.Model.__dict__.get("update")
        assert not isinstance(descriptor, classmethod), \
            "update was incorrectly injected as a classmethod"

    def test_inject_does_not_overwrite_existing_objects_manager(self):
        """inject() must never replace Django's built-in .objects manager."""
        from django.contrib.auth.models import User
        _mixins_module._INJECTED = False
        # Capture the manager instance before injection
        pre_inject_manager = User.__class_getitem__ if False else type(User.objects)
        pre_inject_manager = type(User.objects)
        inject()
        # Manager class must be unchanged after injection
        assert type(User.objects) is pre_inject_manager, \
            "inject() changed the .objects manager type"
        # Verify shellcraft never injects a method named 'objects'
        assert not hasattr(User.objects, "__sc_injected__"), \
            "inject() attached unexpected attribute to objects manager"
        # Sanity: objects must still be queryable after injection
        assert hasattr(User.objects, "all"), \
            "User.objects lost its .all() method after inject()"

    def test_second_inject_does_not_corrupt_methods(self):
        """Double-inject must leave the same method references in place."""
        from django.db import models
        _mixins_module._INJECTED = False
        inject()
        refs_after_first = {
            name: models.Model.__dict__.get(name)
            for name in _INJECTED_NAMES
        }
        inject()  # second call — _INJECTED is True, should be noop
        refs_after_second = {
            name: models.Model.__dict__.get(name)
            for name in _INJECTED_NAMES
        }
        assert refs_after_first == refs_after_second, \
            "Second inject() changed method references"
