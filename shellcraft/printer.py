import datetime
import re
from decimal import Decimal

# ANSI color codes
BLUE   = '\033[34m'
YELLOW = '\033[33m'
GREEN  = '\033[32m'
RED    = '\033[31m'
CYAN   = '\033[36m'
GRAY   = '\033[90m'
RESET  = '\033[0m'

_FIELD_TYPE_COLORS = {
    'AutoField': CYAN, 'BigAutoField': CYAN, 'SmallAutoField': CYAN,
    'IntegerField': BLUE, 'BigIntegerField': BLUE, 'SmallIntegerField': BLUE,
    'FloatField': BLUE, 'DecimalField': BLUE,
    'CharField': YELLOW, 'TextField': YELLOW, 'SlugField': YELLOW,
    'EmailField': YELLOW, 'URLField': YELLOW,
    'BooleanField': GREEN, 'NullBooleanField': GREEN,
    'DateField': CYAN, 'DateTimeField': CYAN, 'TimeField': CYAN,
    'ForeignKey': GRAY, 'OneToOneField': GRAY, 'ManyToManyField': GRAY,
}

# Matches any ANSI CSI escape sequence — covers colors, cursor movement,
# clear-screen codes, etc.  Used to sanitize user-supplied string values
# before they reach the terminal to prevent terminal injection.
_ANSI_ESCAPE_RE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')


def _strip_ansi(s: str) -> str:
    """Remove ANSI escape sequences embedded in a user-supplied string value.

    A database value such as ``"\\033[2J\\033[0;0H"`` would otherwise clear the
    terminal when printed.  We strip rather than escape because the point is
    display-only output; the raw data is unmodified in the database.
    """
    return _ANSI_ESCAPE_RE.sub('', s)


def colorize(value):
    """Return ANSI-colored string representation of a Python value."""
    # bool must be checked before int because bool is a subclass of int.
    if isinstance(value, bool):
        return f"{GREEN}true{RESET}" if value else f"{RED}false{RESET}"
    if isinstance(value, (int, float, Decimal)):
        return f"{BLUE}{value}{RESET}"
    if isinstance(value, str):
        # Sanitize before wrapping in color codes so embedded escape sequences
        # cannot bleed into the terminal (terminal injection prevention).
        return f'{YELLOW}"{_strip_ansi(value)}"{RESET}'
    if value is None:
        return f"{RED}nil{RESET}"
    # datetime.datetime is a subclass of datetime.date, so both are matched
    # here.  datetime.time is a separate type and also colored cyan to match
    # the field-type color for TimeField.
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return f"{CYAN}{value}{RESET}"
    return str(value)


def _get_fields(obj):
    """Return list of (attname, value) for concrete fields of a model instance."""
    return [
        (field.attname, getattr(obj, field.attname, None))
        for field in obj.__class__._meta.concrete_fields
    ]


def _format_record(obj):
    """Format a single model instance as an awesome_print-style string."""
    cls = obj.__class__
    header = f"#<{cls.__name__}:{hex(id(obj))}>"
    fields = _get_fields(obj)

    max_key_len = max((len(name) for name, _ in fields), default=0)

    lines = [f"{header} {{"]
    for name, value in fields:
        key = f":{name}".ljust(max_key_len + 1)
        lines.append(f"    {key} => {colorize(value)},")
    lines.append("}")
    return '\n'.join(lines)


def _is_queryset_like(obj) -> bool:
    """Return True if *obj* is a Django QuerySet or a compatible iterable.

    Design:
    - We prefer a concrete ``isinstance`` check when Django is importable so
      that objects such as ``ModelForm`` (which has both ``.__iter__`` and
      ``.model``) are not mistakenly treated as querysets.
    - A duck-typing fallback is kept so that lightweight test mocks (which
      carry ``__iter__`` and ``.model`` but are not real QuerySet instances)
      continue to work without requiring a live Django setup in every test.
    - The ``not hasattr(obj, '_meta')`` guard prevents a single model
      instance from being routed into the list path if it ever exposes
      ``.model`` (uncommon, but possible with custom model mixins).
    """
    try:
        from django.db.models.query import QuerySet
        if isinstance(obj, QuerySet):
            return True
    except ImportError:
        pass

    # Duck-typing fallback for test mocks and custom queryset-like objects.
    return (
        hasattr(obj, '__iter__')
        and hasattr(obj, 'model')
        and not hasattr(obj, '_meta')
    )


def ap(obj):
    """Pretty-print a model instance or queryset in awesome_print style."""
    if obj is None:
        print(colorize(None))
        return

    if _is_queryset_like(obj):
        _print_queryset(list(obj))
        return

    # Single model instance
    if hasattr(obj, '_meta'):
        print(_format_record(obj))
        return

    print(repr(obj))


def _print_queryset(records):
    if not records:
        print("[]")
        return

    if len(records) == 1:
        print(_format_record(records[0]))
        return

    # Precompute the width of the widest index label (e.g. "[99]" = 4 chars)
    # so that all headers and field lines stay aligned for any result count.
    max_idx_width = len(f"[{len(records) - 1}]")
    # Prefix for the record header line: "    [N…] "
    content_start = 4 + max_idx_width + 1
    # Field lines are indented 4 more chars than the header start (inside {}).
    field_indent = " " * (content_start + 4)
    close_indent = " " * content_start

    print("[")
    for i, record in enumerate(records):
        is_last = i == len(records) - 1
        fields = _get_fields(record)
        cls = record.__class__
        header = f"#<{cls.__name__}:{hex(id(record))}>"
        max_key_len = max((len(name) for name, _ in fields), default=0)

        # Pad the plain label before applying color so ljust counts visible
        # characters only (ANSI codes are zero-width).
        idx_label = f"[{i}]".ljust(max_idx_width)
        idx_colored = f"{GRAY}{idx_label}{RESET}"

        print(f"    {idx_colored} {header} {{")
        for name, value in fields:
            key = f":{name}".ljust(max_key_len + 1)
            print(f"{field_indent}{key} => {colorize(value)},")
        comma = "" if is_last else ","
        print(f"{close_indent}}}{comma}")
    print("]")
    count = len(records)
    print(f"{count} records")  # count is always >= 2 here; single records exit early above


def format_fields(model_class):
    """Return a colored schema summary for a model class."""
    concrete = list(model_class._meta.concrete_fields)
    m2m = list(model_class._meta.many_to_many)

    all_names = [f.attname for f in concrete] + [f.name for f in m2m]
    max_name_len = max((len(n) for n in all_names), default=0)

    lines = [f"{CYAN}{model_class.__name__}{RESET} {{"]

    for field in concrete:
        type_name = field.__class__.__name__
        color = _FIELD_TYPE_COLORS.get(type_name, RESET)
        name = f":{field.attname}".ljust(max_name_len + 1)
        nullable = getattr(field, 'null', False)
        null_tag = f"  {GRAY}null: true{RESET}" if nullable else ""
        lines.append(f"    {name}  {color}{type_name}{RESET}{null_tag}")

    for field in m2m:
        type_name = field.__class__.__name__
        color = _FIELD_TYPE_COLORS.get(type_name, GRAY)
        name = f":{field.name}".ljust(max_name_len + 1)
        lines.append(f"    {name}  {color}{type_name}{RESET}")

    lines.append("}")
    return '\n'.join(lines)
