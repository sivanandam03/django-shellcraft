import warnings

_INJECTED = False


def inject():
    """Inject Rails-style class/instance methods onto Django's base Model.

    Safe to call multiple times — idempotent after first call.
    Only call this from the shellcraft management command.

    Raises RuntimeError when DEBUG is False so that an accidental import of
    this module in a production Celery worker or WSGI request cannot
    activate the shell shortcuts on every model in the process.
    """
    global _INJECTED
    if _INJECTED:
        return

    # Belt-and-suspenders production guard.  The management command also
    # checks DEBUG before calling inject(), but inject() is a public function
    # and could be called from user code (e.g. a custom management command
    # that wraps shellcraft).  Checking here ensures the guard can never be
    # bypassed simply by calling inject() directly.
    from django.conf import settings
    if not settings.DEBUG:
        raise RuntimeError(
            "shellcraft.inject() must not be called when DEBUG=False. "
            "The shellcraft shell is a development-only tool."
        )

    _INJECTED = True

    from django.db import models

    from shellcraft.printer import ap, format_fields

    def _find(cls, pk):
        return cls.objects.get(pk=pk)

    def _all(cls):
        # Return the queryset so callers can assign: `users = User.all()`.
        # Printing and returning are both useful; returning None was a silent
        # footgun for anyone who stored the result.
        qs = cls.objects.all()
        ap(qs)
        return qs

    def _where(cls, **kwargs):
        qs = cls.objects.filter(**kwargs)
        ap(qs)
        return qs

    def _first(cls):
        obj = cls.objects.first()
        if obj is not None:
            ap(obj)
        return obj

    def _last(cls):
        obj = cls.objects.last()
        if obj is not None:
            ap(obj)
        return obj

    def _count(cls):
        return cls.objects.count()

    def _fields(cls):
        print(format_fields(cls))

    def _update(self, **kwargs):
        # Block dunder and private-attribute keys outright.  Allowing
        # user.update(__class__=X) or user.update(__dict__={...}) would let
        # shell users overwrite Python internals, bypassing Django's field
        # validation entirely and corrupting the object in memory.
        for key in kwargs:
            if key.startswith("_"):
                raise ValueError(
                    f"shellcraft: cannot update private or dunder attribute '{key}'. "
                    "Pass only model field names."
                )

        # Warn (don't raise) for keys that don't correspond to any known field
        # on this model.  Django's save() will silently ignore them, which is
        # confusing during interactive development.
        valid_fields = {f.attname for f in self.__class__._meta.concrete_fields}
        valid_fields.update(f.name for f in self.__class__._meta.concrete_fields)
        valid_fields.update(f.name for f in self.__class__._meta.many_to_many)

        for key in kwargs:
            if key not in valid_fields:
                warnings.warn(
                    f"shellcraft: '{key}' is not a recognised field on "
                    f"{self.__class__.__name__} — the attribute will be set "
                    "but will not be persisted by Django's save().",
                    stacklevel=2,
                )

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
