"""
Tests for shellcraft/management/commands/shellcraft.py.

The management command is interactive (it opens a Python or IPython shell),
so _start_shell is mocked in every test that exercises handle() or the
overall flow.  Tests that specifically target namespace building or the
DEBUG guard do not need the shell to start at all.

Isolation:
- The ``restore_inject`` autouse fixture (same pattern as test_mixins.py)
  sets DEBUG=True, resets _INJECTED, and removes Model patches after each test.
- ``call_command`` is avoided in most tests because it requires Django's app
  registry to be fully populated AND it swallows output through stdout/stderr
  capture.  We instantiate Command() directly so we can inspect internals.
"""
import warnings
from io import StringIO
from unittest.mock import MagicMock, patch, call

import pytest
from django.core.management.base import CommandError

import shellcraft.mixins as _mixins_module

_INJECTED_NAMES = (
    "find", "all", "where", "first", "last", "count", "fields",
    "update", "destroy",
)


# ---------------------------------------------------------------------------
# Shared fixture (mirrors test_mixins.py pattern)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def restore_inject(settings):
    """Set DEBUG=True and clean up Model patches after every test."""
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


def _make_command():
    """Return a Command instance with stdout/stderr wired to StringIO."""
    from shellcraft.management.commands.shellcraft import Command
    cmd = Command()
    cmd.stdout = StringIO()
    cmd.stderr = StringIO()
    return cmd


# ---------------------------------------------------------------------------
# TC-CMD01 / TC-CMD02 — handle(): DEBUG guard
# ---------------------------------------------------------------------------

class TestHandleDebugGuard:
    def test_raises_command_error_when_debug_false(self, settings):
        """DEBUG=False must raise CommandError, not SystemExit or RuntimeError."""
        settings.DEBUG = False
        cmd = _make_command()
        with pytest.raises(CommandError, match="DEBUG=False"):
            cmd.handle()

    def test_error_message_mentions_production_guard(self, settings):
        settings.DEBUG = False
        cmd = _make_command()
        with pytest.raises(CommandError) as exc_info:
            cmd.handle()
        assert "production guard" in str(exc_info.value).lower() or \
               "debug" in str(exc_info.value).lower()

    def test_no_error_when_debug_true(self, settings):
        """DEBUG=True must pass the guard without raising."""
        settings.DEBUG = True
        cmd = _make_command()
        with patch.object(cmd, "_start_shell"):
            cmd.handle()   # must not raise

    def test_inject_called_during_handle(self, settings):
        """handle() must call inject() to wire up model shortcuts.

        inject() is a deferred import inside handle() so we patch it at its
        source module (shellcraft.mixins) rather than the command module.
        """
        settings.DEBUG = True
        cmd = _make_command()
        with patch("shellcraft.mixins.inject") as mock_inject, \
             patch.object(cmd, "_start_shell"):
            cmd.handle()
        mock_inject.assert_called_once()

    def test_build_namespace_called_during_handle(self, settings):
        """handle() must call _build_namespace() to prepare shell variables."""
        settings.DEBUG = True
        cmd = _make_command()
        with patch.object(cmd, "_build_namespace", return_value={}) as mock_ns, \
             patch.object(cmd, "_start_shell"):
            cmd.handle()
        mock_ns.assert_called_once()

    def test_start_shell_receives_namespace(self, settings):
        """The namespace dict from _build_namespace must be passed to _start_shell."""
        settings.DEBUG = True
        cmd = _make_command()
        fake_ns = {"User": object(), "ap": object()}
        with patch.object(cmd, "_build_namespace", return_value=fake_ns), \
             patch.object(cmd, "_start_shell") as mock_shell:
            cmd.handle()
        mock_shell.assert_called_once_with(fake_ns)


# ---------------------------------------------------------------------------
# TC-NS01–TC-NS06 — _build_namespace()
# ---------------------------------------------------------------------------

class TestBuildNamespace:
    def test_ap_always_in_namespace(self):
        cmd = _make_command()
        ns = cmd._build_namespace()
        assert "ap" in ns
        assert callable(ns["ap"])

    def test_tables_always_in_namespace(self):
        cmd = _make_command()
        ns = cmd._build_namespace()
        assert "tables" in ns
        assert callable(ns["tables"])

    def test_model_names_in_namespace(self):
        """Every app model's class name must appear as a top-level key."""
        from django.apps import apps
        cmd = _make_command()
        ns = cmd._build_namespace()
        for model in apps.get_models():
            assert model.__name__ in ns, f"{model.__name__} missing from namespace"

    def test_namespace_models_are_actual_model_classes(self):
        from django.apps import apps
        from django.db import models as django_models
        cmd = _make_command()
        ns = cmd._build_namespace()
        for model in apps.get_models():
            assert issubclass(ns[model.__name__], django_models.Model)

    def test_collision_emits_warning(self):
        """Two models with the same __name__ must trigger a UserWarning."""
        from django.apps import apps

        # Fabricate a second model with the same name as an existing one.
        existing = list(apps.get_models())[0]
        duplicate_name = existing.__name__

        fake_model = type(
            duplicate_name,
            (),
            {"_meta": type("Meta", (), {
                "app_label": "fake_app",
            })()},
        )

        original_get_models = apps.get_models

        def patched_get_models(*a, **kw):
            return list(original_get_models(*a, **kw)) + [fake_model]

        cmd = _make_command()
        with patch.object(apps, "get_models", patched_get_models), \
             warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            cmd._build_namespace()

        collision_warnings = [
            w for w in caught
            if duplicate_name in str(w.message)
        ]
        assert collision_warnings, "Expected a warning about model name collision"

    def test_tables_function_writes_model_list(self):
        """Calling tables() must write at least one line per installed model."""
        from django.apps import apps
        cmd = _make_command()
        ns = cmd._build_namespace()
        ns["tables"]()
        output = cmd.stdout.getvalue()
        for model in apps.get_models():
            assert model.__name__ in output

    def test_tables_function_writes_count_line(self):
        """tables() must print 'N tables' as the last line."""
        from django.apps import apps
        cmd = _make_command()
        ns = cmd._build_namespace()
        ns["tables"]()
        output = cmd.stdout.getvalue()
        model_count = len(list(apps.get_models()))
        assert f"{model_count} tables" in output


# ---------------------------------------------------------------------------
# TC-SHL01–TC-SHL04 — _start_shell(): banner and shell selection
# ---------------------------------------------------------------------------

class TestStartShell:
    def test_banner_written_to_stdout(self):
        """The version banner must appear in stdout before the shell starts."""
        import sys
        cmd = _make_command()
        # Remove IPython from sys.modules so the ImportError branch runs,
        # then mock code.interact so no real interactive shell opens.
        ipython_backup = sys.modules.pop("IPython", None)
        try:
            with patch("code.interact"):
                cmd._start_shell({})
        finally:
            if ipython_backup is not None:
                sys.modules["IPython"] = ipython_backup
        output = cmd.stdout.getvalue()
        assert "shellcraft" in output

    def test_uses_code_interact_when_ipython_missing(self):
        """When IPython is not installed, code.interact must be used."""
        cmd = _make_command()
        with patch.dict("sys.modules", {"IPython": None}):
            with patch("code.interact") as mock_interact:
                cmd._start_shell({"x": 1})
        mock_interact.assert_called_once()

    def test_ipython_used_when_available(self):
        """When IPython is importable, IPython.start_ipython must be called."""
        cmd = _make_command()
        mock_ipython = MagicMock()
        test_ns = {"sentinel": object()}
        with patch.dict("sys.modules", {"IPython": mock_ipython}):
            cmd._start_shell(test_ns)
        mock_ipython.start_ipython.assert_called_once_with(
            argv=["--no-banner"], user_ns=test_ns
        )

    def test_namespace_passed_to_shell(self):
        """The namespace dict must be forwarded to whichever shell runs."""
        cmd = _make_command()
        test_ns = {"sentinel": object()}
        with patch.dict("sys.modules", {"IPython": None}):
            with patch("code.interact") as mock_interact:
                cmd._start_shell(test_ns)
        _, kwargs = mock_interact.call_args
        assert kwargs.get("local") is test_ns
