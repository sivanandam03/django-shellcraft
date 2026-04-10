from django.conf import settings
from django.core.management.base import BaseCommand

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
        if not settings.DEBUG:
            raise SystemExit(
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

        for model in apps.get_models():
            namespace[model.__name__] = model

        return namespace

    def _start_shell(self, namespace):
        from shellcraft import __version__

        banner = BANNER.format(version=__version__)
        self.stdout.write(banner)

        try:
            import IPython

            IPython.start_ipython(argv=["--no-banner"], user_ns=namespace)
        except ImportError:
            import code

            code.interact(banner="", local=namespace)
