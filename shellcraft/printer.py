import datetime
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


def colorize(value):
    """Return ANSI-colored string representation of a Python value."""
    if isinstance(value, bool):
        return f"{GREEN}true{RESET}" if value else f"{RED}false{RESET}"
    if isinstance(value, (int, float, Decimal)):
        return f"{BLUE}{value}{RESET}"
    if isinstance(value, str):
        return f'{YELLOW}"{value}"{RESET}'
    if value is None:
        return f"{RED}nil{RESET}"
    if isinstance(value, (datetime.datetime, datetime.date)):
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


def ap(obj):
    """Pretty-print a model instance or queryset in awesome_print style."""
    if obj is None:
        print(colorize(None))
        return

    # QuerySet (has both __iter__ and .model)
    if hasattr(obj, '__iter__') and hasattr(obj, 'model'):
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

    print("[")
    for i, record in enumerate(records):
        is_last = i == len(records) - 1
        fields = _get_fields(record)
        cls = record.__class__
        header = f"#<{cls.__name__}:{hex(id(record))}>"
        max_key_len = max((len(name) for name, _ in fields), default=0)

        idx = f"{GRAY}[{i}]{RESET}"
        print(f"    {idx} {header} {{")
        for name, value in fields:
            key = f":{name}".ljust(max_key_len + 1)
            print(f"            {key} => {colorize(value)},")
        comma = "" if is_last else ","
        print(f"        }}{comma}")
    print("]")
    count = len(records)
    print(f"{count} {'record' if count == 1 else 'records'}")


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
