import warnings

_INJECTED = False


def inject():
    """Inject Rails-style class/instance methods onto Django's base Model.

    Safe to call multiple times — idempotent after first call.
    Only call this from the shellcraft management command.
    """
    global _INJECTED
    if _INJECTED:
        return
    _INJECTED = True

    from django.db import models

    from shellcraft.printer import ap, format_fields

    def _find(cls, pk):
        return cls.objects.get(pk=pk)

    def _all(cls):
        ap(cls.objects.all())

    def _where(cls, **kwargs):
        ap(cls.objects.filter(**kwargs))

    def _first(cls):
        return cls.objects.first()

    def _last(cls):
        return cls.objects.last()

    def _count(cls):
        return cls.objects.count()

    def _fields(cls):
        print(format_fields(cls))

    def _update(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.save()
        return self

    def _destroy(self):
        return self.delete()

    class_methods = {
        'find':   _find,
        'all':    _all,
        'where':  _where,
        'first':  _first,
        'last':   _last,
        'count':  _count,
        'fields': _fields,
    }
    instance_methods = {
        'update':  _update,
        'destroy': _destroy,
    }

    for name, fn in class_methods.items():
        _safe_inject(models.Model, name, classmethod(fn))

    for name, fn in instance_methods.items():
        _safe_inject(models.Model, name, fn)


def _safe_inject(cls, name, method):
    if hasattr(cls, name):
        existing = getattr(cls, name)
        warnings.warn(
            f"shellcraft: '{name}' already exists on {cls.__name__} "
            f"(defined in {getattr(existing, '__module__', '?')}) — skipping injection",
            stacklevel=3,
        )
        return
    setattr(cls, name, method)
