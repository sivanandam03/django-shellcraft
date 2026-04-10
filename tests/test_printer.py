import datetime
import re
from decimal import Decimal

from shellcraft.printer import (
    BLUE,
    CYAN,
    GREEN,
    GRAY,
    RED,
    YELLOW,
    _format_record,
    _get_fields,
    ap,
    colorize,
    format_fields,
)

# ---------------------------------------------------------------------------
# Helpers — minimal mock objects that look enough like Django model instances
# ---------------------------------------------------------------------------

def _make_field(attname):
    """Return a minimal concrete-field stub."""
    return type("Field", (), {"attname": attname})()


def _make_instance(class_name, **fields):
    """Return a minimal model-instance stub with _meta.concrete_fields."""
    field_list = [_make_field(k) for k in fields]

    class Meta:
        concrete_fields = field_list

    cls = type(class_name, (), {"_meta": Meta()})
    obj = cls()
    for k, v in fields.items():
        setattr(obj, k, v)
    return obj


class _MockQuerySet:
    """Minimal queryset-like object (has .model and __iter__)."""
    def __init__(self, class_name, records):
        self.model = type(class_name, (), {})
        self._records = records

    def __iter__(self):
        return iter(self._records)


# ---------------------------------------------------------------------------
# colorize
# ---------------------------------------------------------------------------

def test_colorize_int():
    out = colorize(42)
    assert '42' in out
    assert BLUE in out


def test_colorize_float():
    out = colorize(3.14)
    assert '3.14' in out
    assert BLUE in out


def test_colorize_str():
    out = colorize('hello')
    assert '"hello"' in out
    assert YELLOW in out


def test_colorize_true():
    out = colorize(True)
    assert 'true' in out
    assert GREEN in out


def test_colorize_false():
    out = colorize(False)
    assert 'false' in out
    assert RED in out


def test_colorize_none():
    out = colorize(None)
    assert 'nil' in out
    assert RED in out


def test_colorize_datetime():
    dt = datetime.datetime(2024, 1, 15, 10, 30, 0)
    out = colorize(dt)
    assert str(dt) in out
    assert CYAN in out


def test_colorize_date():
    d = datetime.date(2024, 1, 15)
    out = colorize(d)
    assert str(d) in out
    assert CYAN in out


def test_colorize_bool_before_int():
    """True/False must be caught before int check (bool is a subclass of int)."""
    assert 'true' in colorize(True)
    assert 'false' in colorize(False)
    assert GREEN in colorize(True)
    assert RED in colorize(False)


# ---------------------------------------------------------------------------
# _get_fields
# ---------------------------------------------------------------------------

def test_get_fields_returns_name_value_pairs():
    obj = _make_instance('User', id=1, username='siva')
    fields = _get_fields(obj)
    assert ('id', 1) in fields
    assert ('username', 'siva') in fields


# ---------------------------------------------------------------------------
# _format_record
# ---------------------------------------------------------------------------

def test_format_record_header():
    obj = _make_instance('User', id=1)
    out = _format_record(obj)
    assert '#<User:' in out
    assert '{' in out
    assert '}' in out


def test_format_record_field_names():
    obj = _make_instance('User', id=1, username='siva', is_active=True)
    out = _format_record(obj)
    assert ':id' in out
    assert ':username' in out
    assert ':is_active' in out


def test_format_record_colorizes_int():
    obj = _make_instance('User', id=1)
    out = _format_record(obj)
    assert BLUE in out


def test_format_record_colorizes_str():
    obj = _make_instance('User', username='siva')
    out = _format_record(obj)
    assert YELLOW in out


def test_format_record_alignment():
    """Longer field names should be padded so '=>' is aligned."""
    obj = _make_instance('User', id=1, username='siva')
    lines = _format_record(obj).splitlines()
    arrow_cols = [ln.index("=>") for ln in lines if "=>" in ln]
    assert len(set(arrow_cols)) == 1, "'=>' should be column-aligned"


# ---------------------------------------------------------------------------
# ap — None
# ---------------------------------------------------------------------------

def test_ap_none(capsys):
    ap(None)
    assert 'nil' in capsys.readouterr().out


# ---------------------------------------------------------------------------
# ap — single instance
# ---------------------------------------------------------------------------

def test_ap_single_instance(capsys):
    obj = _make_instance('User', id=1, username='siva', is_active=True)
    ap(obj)
    out = capsys.readouterr().out
    assert '#<User:' in out
    assert ':id' in out
    assert ':username' in out
    assert '[0]' not in out   # no index for single record


# ---------------------------------------------------------------------------
# ap — queryset / list-like
# ---------------------------------------------------------------------------

def test_ap_empty_queryset(capsys):
    qs = _MockQuerySet('User', [])
    ap(qs)
    assert '[]' in capsys.readouterr().out


def test_ap_single_record_queryset_no_index(capsys):
    obj = _make_instance('User', id=1, username='siva')
    qs = _MockQuerySet('User', [obj])
    ap(qs)
    out = capsys.readouterr().out
    assert '#<User:' in out
    assert '[0]' not in out


def test_ap_multiple_records_shows_index(capsys):
    r1 = _make_instance('User', id=1, username='siva')
    r2 = _make_instance('User', id=2, username='kumar')
    qs = _MockQuerySet('User', [r1, r2])
    ap(qs)
    out = capsys.readouterr().out
    assert '[0]' in out
    assert '[1]' in out


def test_ap_multiple_records_count_line(capsys):
    r1 = _make_instance('User', id=1, username='siva')
    r2 = _make_instance('User', id=2, username='kumar')
    qs = _MockQuerySet('User', [r1, r2])
    ap(qs)
    out = capsys.readouterr().out
    assert '2 records' in out


def test_ap_one_record_singular(capsys):
    """A queryset with exactly one record bypasses the list view."""
    r = _make_instance('User', id=1, username='siva')
    qs = _MockQuerySet('User', [r])
    ap(qs)
    out = capsys.readouterr().out
    # displayed as single record, no count line
    assert 'record' not in out


def test_ap_three_records_count_line(capsys):
    records = [_make_instance('User', id=i, username=f'u{i}') for i in range(3)]
    qs = _MockQuerySet('User', records)
    ap(qs)
    out = capsys.readouterr().out
    assert '3 records' in out


# ---------------------------------------------------------------------------
# colorize — Decimal (Django stores DecimalField values as Decimal objects)
# ---------------------------------------------------------------------------

def test_colorize_decimal():
    out = colorize(Decimal('9.99'))
    assert '9.99' in out
    assert BLUE in out


def test_colorize_decimal_zero():
    out = colorize(Decimal('0'))
    assert BLUE in out


# ---------------------------------------------------------------------------
# format_fields
# ---------------------------------------------------------------------------

def _make_field_stub(attname, field_type_name, null=False):
    """Return a concrete-field stub with enough attributes for format_fields."""
    return type("Field", (), {
        "attname": attname,
        "__class__": type(field_type_name, (), {"__name__": field_type_name}),
        "null": null,
    })()


def _make_model_class(class_name, fields, m2m=None):
    """Return a minimal model class stub for format_fields."""
    class Meta:
        concrete_fields = fields
        many_to_many = m2m or []

    return type(class_name, (), {"_meta": Meta()})


def test_format_fields_header():
    model = _make_model_class('Product', [
        _make_field_stub('id', 'AutoField'),
    ])
    out = format_fields(model)
    assert 'Product' in out
    assert CYAN in out
    assert '{' in out
    assert '}' in out


def test_format_fields_shows_field_names():
    model = _make_model_class('Product', [
        _make_field_stub('id', 'AutoField'),
        _make_field_stub('name', 'CharField'),
        _make_field_stub('price', 'DecimalField'),
    ])
    out = format_fields(model)
    assert ':id' in out
    assert ':name' in out
    assert ':price' in out


def test_format_fields_shows_type_names():
    model = _make_model_class('Product', [
        _make_field_stub('id', 'AutoField'),
        _make_field_stub('price', 'DecimalField'),
    ])
    out = format_fields(model)
    assert 'AutoField' in out
    assert 'DecimalField' in out


def test_format_fields_nullable_tag():
    model = _make_model_class('Product', [
        _make_field_stub('description', 'TextField', null=True),
    ])
    out = format_fields(model)
    assert 'null: true' in out


def test_format_fields_non_nullable_no_tag():
    model = _make_model_class('Product', [
        _make_field_stub('name', 'CharField', null=False),
    ])
    out = format_fields(model)
    assert 'null: true' not in out


def _strip_ansi(s):
    return re.sub(r'\x1b\[[0-9;]*m', '', s)


def test_format_fields_alignment():
    """Field names should be padded so type names are column-aligned."""
    model = _make_model_class('Product', [
        _make_field_stub('id', 'AutoField'),
        _make_field_stub('description', 'TextField'),
    ])
    raw = format_fields(model)
    # Strip ANSI so column arithmetic is clean; keep only field lines (start with "    :")
    field_lines = [_strip_ansi(ln) for ln in raw.splitlines() if ln.lstrip().startswith(':')]
    # Each line: "    :name  TypeName" — the type starts right after the last "  " gap.
    type_cols = [ln.rindex('  ') + 2 for ln in field_lines]
    assert len(set(type_cols)) == 1, f"type names not column-aligned: {type_cols}"
