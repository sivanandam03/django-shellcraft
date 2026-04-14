import warnings

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

BANNER = """\
shellcraft {version} — Rails-style Django shell
  User.find(1)          User.all()        User.where(active=True)
  User.first()          User.last()       User.count()
  user.update(k=v)      user.destroy()
  User.fields()         tables()
"""


class Command(BaseCommand):
    help = "Rails-style Django shell with pretty printing and model shortcuts"

    def handle(self, *_args, **_options):
        # Use CommandError instead of SystemExit so Django's management
        # framework can format the message via stderr and return a proper
        # non-zero exit code.  SystemExit would skip that pipeline entirely.
        if not settings.DEBUG:
            raise CommandError(
                "shellcraft: refusing to run with DEBUG=False (production guard)"
            )

        from shellcraft.mixins import inject

        inject()

        namespace = self._build_namespace()
        self._start_shell(namespace)

    def _build_namespace(self):
        from django.apps import apps

        from shellcraft.printer import CYAN, RESET, ap

        def tables():
            all_models = apps.get_models()
            for model in all_models:
                label = model._meta.app_label
                self.stdout.write(f"  {CYAN}{label}{RESET}.{model.__name__}")
            self.stdout.write(f"\n{len(all_models)} tables")

        namespace = {
            "ap": ap,
            "tables": tables,
        }

        # Build model-name → model mapping, warning when two apps define a
        # model with the same class name.  Without the warning the second
        # model silently shadows the first, which is a confusing footgun when
        # working with multi-app projects (e.g. two apps both define `Profile`).
        seen: dict = {}
        for model in apps.get_models():
            name = model.__name__
            if name in seen:
                warnings.warn(
                    f"shellcraft: model name conflict — '{name}' exists in both "
                    f"'{seen[name]._meta.app_label}' and '{model._meta.app_label}'. "
                    f"The '{model._meta.app_label}.{name}' version is used in the "
                    "shell namespace.  Access the other via "
                    "apps.get_model('<app_label>', '<ModelName>').",
                    stacklevel=2,
                )
            seen[name] = model
            namespace[name] = model

        return namespace

    def _start_shell(self, namespace):
        from shellcraft import __version__

        banner = BANNER.format(version=__version__)
        self.stdout.write(banner)

        # Detect which shell is available before entering it, so that
        # code.interact is never called inside an `except` block.  If it were,
        # Python would set __context__ on every shell exception to the
        # ModuleNotFoundError, producing spurious "During handling of the above
        # exception" noise on every traceback the user sees.
        use_ipython = False
        try:
            import IPython  # noqa: F401
            use_ipython = True
        except ImportError:
            self.stdout.write("(IPython not found — using standard Python shell)\n")

        if use_ipython:
            import IPython
            IPython.start_ipython(argv=["--no-banner"], user_ns=namespace)
        else:
            import code
            code.interact(banner="", local=namespace)
