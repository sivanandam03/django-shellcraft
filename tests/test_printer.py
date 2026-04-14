import datetime
import re
from decimal import Decimal

from shellcraft.printer import (
    BLUE,
    CYAN,
    GREEN,
    GRAY,
    RED,
    RESET,
    YELLOW,
    _format_record,
    _get_fields,
    _is_queryset_like,
    _strip_ansi,
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
# colorize — basic types
# ---------------------------------------------------------------------------

def test_colorize_int():
    out = colorize(42)
    assert '42' in out
    assert BLUE in out


def test_colorize_negative_int():
    out = colorize(-5)
    assert '-5' in out
    assert BLUE in out


def test_colorize_zero():
    out = colorize(0)
    assert BLUE in out


def test_colorize_float():
    out = colorize(3.14)
    assert '3.14' in out
    assert BLUE in out


def test_colorize_str():
    out = colorize('hello')
    assert '"hello"' in out
    assert YELLOW in out


def test_colorize_empty_string():
    out = colorize("")
    assert '""' in out
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
# colorize — FIX: datetime.time was previously uncolored
# ---------------------------------------------------------------------------

def test_colorize_time():
    """datetime.time should be cyan, same as date/datetime (TimeField color)."""
    t = datetime.time(10, 30, 45)
    out = colorize(t)
    assert str(t) in out
    assert CYAN in out


def test_colorize_time_midnight():
    out = colorize(datetime.time(0, 0, 0))
    assert CYAN in out


# ---------------------------------------------------------------------------
# colorize — FIX: ANSI terminal injection prevention
# ---------------------------------------------------------------------------

def test_colorize_string_strips_ansi_color_code():
    """A value containing an ANSI color escape must not reach the terminal."""
    malicious = "\033[31minjected\033[0m"
    out = colorize(malicious)
    # The injected escape sequences should be gone from the user-data portion.
    # We strip our own known wrapper codes first, then assert no ESC remains.
    inner = out.replace(YELLOW, "").replace(RESET, "")
    assert "\033[" not in inner


def test_colorize_string_strips_ansi_cursor_clear():
    """Clear-screen / cursor-home sequences must be stripped."""
    malicious = "\033[2J\033[0;0H"
    out = colorize(malicious)
    inner = out.replace(YELLOW, "").replace(RESET, "")
    assert "\033[" not in inner


def test_colorize_string_preserves_content_after_strip():
    """Legitimate text around embedded ANSI codes is preserved."""
    value = "hello\033[31mworld\033[0m!"
    out = colorize(value)
    assert "helloworld!" in out


def test_colorize_string_with_embedded_quotes():
    """Strings that contain double-quotes are passed through unchanged."""
    out = colorize('say "hi"')
    assert 'say "hi"' in out


def test_colorize_unknown_type_no_crash():
    """Objects with no special handling fall back to str() without raising."""
    class Weird:
        def __str__(self):
            return "weird_value"
    out = colorize(Weird())
    assert "weird_value" in out


# ---------------------------------------------------------------------------
# colorize — Decimal
# ---------------------------------------------------------------------------

def test_colorize_decimal():
    out = colorize(Decimal('9.99'))
    assert '9.99' in out
    assert BLUE in out


def test_colorize_decimal_zero():
    out = colorize(Decimal('0'))
    assert BLUE in out


# ---------------------------------------------------------------------------
# _strip_ansi (internal helper — exported for testing)
# ---------------------------------------------------------------------------

def test_strip_ansi_removes_color_codes():
    assert _strip_ansi("\033[31mred\033[0m") == "red"


def test_strip_ansi_removes_cursor_movement():
    assert _strip_ansi("\033[2J\033[0;0H") == ""


def test_strip_ansi_preserves_plain_text():
    assert _strip_ansi("no escapes here") == "no escapes here"


def test_strip_ansi_empty_string():
    assert _strip_ansi("") == ""


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


def test_format_record_no_fields():
    """A model with zero concrete fields must not raise and must show braces."""
    obj = _make_instance('Empty')
    out = _format_record(obj)
    assert '#<Empty:' in out
    assert '{' in out
    assert '}' in out


# ---------------------------------------------------------------------------
# _is_queryset_like — FIX: duck-typing too broad
# ---------------------------------------------------------------------------

def test_is_queryset_like_returns_true_for_mock_qs():
    qs = _MockQuerySet('User', [])
    assert _is_queryset_like(qs) is True


def test_is_queryset_like_returns_false_for_model_instance():
    """A single model instance must not be routed into the list path."""
    obj = _make_instance('User', id=1)
    assert _is_queryset_like(obj) is False


def test_is_queryset_like_returns_false_for_plain_list():
    assert _is_queryset_like([1, 2, 3]) is False


def test_is_queryset_like_returns_false_for_none():
    assert _is_queryset_like(None) is False


def test_is_queryset_like_returns_false_for_plain_object():
    assert _is_queryset_like(object()) is False


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


def test_ap_plain_object_falls_back_to_repr(capsys):
    """Objects with neither _meta nor queryset-like duck-typing use repr()."""
    ap(42)
    assert '42' in capsys.readouterr().out


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
# _print_queryset — FIX: hardcoded indentation for large indices
# ---------------------------------------------------------------------------

def _strip_ansi_re(s):
    return re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', s)


def test_queryset_index_alignment_single_digits(capsys):
    """All '=>' arrows must be at the same column for indices [0]-[9]."""
    records = [_make_instance('User', id=i, username=f'u{i}') for i in range(3)]
    qs = _MockQuerySet('User', records)
    ap(qs)
    raw = capsys.readouterr().out
    clean = _strip_ansi_re(raw)
    arrow_cols = [
        ln.index("=>")
        for ln in clean.splitlines()
        if "=>" in ln
    ]
    assert len(set(arrow_cols)) == 1, f"Arrows misaligned: columns={arrow_cols}"


def test_queryset_index_alignment_crosses_ten(capsys):
    """Indentation must stay consistent when index labels go from [9] to [10]."""
    records = [_make_instance('User', id=i) for i in range(11)]
    qs = _MockQuerySet('User', records)
    ap(qs)
    raw = capsys.readouterr().out
    clean = _strip_ansi_re(raw)
    arrow_cols = [
        ln.index("=>")
        for ln in clean.splitlines()
        if "=>" in ln
    ]
    assert len(set(arrow_cols)) == 1, f"Arrows misaligned across digit boundary: {arrow_cols}"


def test_queryset_close_brace_alignment(capsys):
    """Closing braces must all appear at the same column."""
    records = [_make_instance('User', id=i, username=f'u{i}') for i in range(3)]
    qs = _MockQuerySet('User', records)
    ap(qs)
    raw = capsys.readouterr().out
    clean = _strip_ansi_re(raw)
    # Closing brace lines start with spaces then '}'
    brace_cols = [
        len(ln) - len(ln.lstrip())
        for ln in clean.splitlines()
        if ln.lstrip().startswith('}')
    ]
    assert len(set(brace_cols)) == 1, f"Closing braces misaligned: {brace_cols}"


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


def test_format_fields_no_fields_no_crash():
    """A model with no fields must render as 'ModelName {}' without raising."""
    model = _make_model_class('Empty', [])
    out = format_fields(model)
    assert 'Empty' in out
    assert '{' in out
    assert '}' in out


def _strip_colors(s):
    """Strip only color codes (ending in 'm') for column-alignment tests.
    This is intentionally narrower than _strip_ansi from printer.py, which
    strips all CSI sequences.  Renamed to avoid shadowing the import above.
    """
    return re.sub(r'\x1b\[[0-9;]*m', '', s)


def test_format_fields_alignment():
    """Field names should be padded so type names are column-aligned."""
    model = _make_model_class('Product', [
        _make_field_stub('id', 'AutoField'),
        _make_field_stub('description', 'TextField'),
    ])
    raw = format_fields(model)
    # Strip ANSI; keep only field lines (those starting with ":")
    field_lines = [
        _strip_colors(ln) for ln in raw.splitlines() if ln.lstrip().startswith(":")
    ]
    # Each line: "    :name  TypeName" — type starts after the last double-space gap.
    type_cols = [ln.rindex("  ") + 2 for ln in field_lines]
    assert len(set(type_cols)) == 1, f"type names not column-aligned: {type_cols}"


# ---------------------------------------------------------------------------
# format_fields — FIX GAP: M2M fields (printer.py:193-197 previously uncovered)
# ---------------------------------------------------------------------------

def _make_m2m_stub(name, field_type_name='ManyToManyField'):
    """Return a M2M field stub compatible with the format_fields M2M loop.

    format_fields uses ``f.name`` (not ``f.attname``) and ``f.__class__.__name__``
    for M2M fields, matching the pattern used by _make_field_stub for concrete fields.
    """
    return type("M2MField", (), {
        "name": name,
        "__class__": type(field_type_name, (), {"__name__": field_type_name}),
    })()


def test_format_fields_with_m2m_field():
    """M2M field name and type must appear in output (covers printer.py:193-197)."""
    concrete = [_make_field_stub('id', 'AutoField')]
    m2m     = [_make_m2m_stub('tags', 'ManyToManyField')]
    model = _make_model_class('Article', concrete, m2m=m2m)
    out = format_fields(model)
    assert ':tags' in out
    assert 'ManyToManyField' in out


def test_format_fields_m2m_uses_gray_color():
    """ManyToManyField is listed as GRAY in _FIELD_TYPE_COLORS."""
    m2m = [_make_m2m_stub('tags', 'ManyToManyField')]
    model = _make_model_class('Article', [], m2m=m2m)
    out = format_fields(model)
    assert GRAY in out


def test_format_fields_unknown_m2m_type_falls_back_to_gray():
    """An M2M field type not in _FIELD_TYPE_COLORS defaults to GRAY."""
    m2m = [_make_m2m_stub('related', 'CustomM2MField')]
    model = _make_model_class('Widget', [], m2m=m2m)
    out = format_fields(model)
    assert 'CustomM2MField' in out
    assert GRAY in out


def test_format_fields_m2m_only_model_no_crash():
    """A model with M2M fields but zero concrete fields must render cleanly."""
    m2m = [_make_m2m_stub('friends', 'ManyToManyField')]
    model = _make_model_class('SocialProfile', [], m2m=m2m)
    out = format_fields(model)
    assert ':friends' in out
    assert 'SocialProfile' in out
    assert '{' in out
    assert '}' in out


def test_format_fields_m2m_and_concrete_column_alignment():
    """Concrete and M2M field type-names must be aligned to the same column."""
    concrete = [_make_field_stub('description', 'TextField')]
    m2m      = [_make_m2m_stub('tags', 'ManyToManyField')]
    model = _make_model_class('Article', concrete, m2m=m2m)
    raw = format_fields(model)
    field_lines = [
        _strip_colors(ln) for ln in raw.splitlines() if ln.lstrip().startswith(':')
    ]
    assert len(field_lines) == 2, "Expected one concrete + one M2M field line"
    type_cols = [ln.rindex("  ") + 2 for ln in field_lines]
    assert len(set(type_cols)) == 1, f"M2M type not column-aligned: {type_cols}"


def test_format_fields_multiple_m2m_fields():
    """Multiple M2M fields must all appear in the output."""
    m2m = [
        _make_m2m_stub('tags',       'ManyToManyField'),
        _make_m2m_stub('categories', 'ManyToManyField'),
    ]
    model = _make_model_class('Article', [], m2m=m2m)
    out = format_fields(model)
    assert ':tags' in out
    assert ':categories' in out


# ---------------------------------------------------------------------------
# _is_queryset_like — FIX GAP: ImportError fallback (printer.py:104-105)
# ---------------------------------------------------------------------------

def test_is_queryset_like_importerror_accepts_duck_typed_qs():
    """When Django's QuerySet cannot be imported the duck-typing branch runs
    (covers printer.py:104-105).

    Setting sys.modules['django.db.models.query'] = None causes Python to raise
    ImportError on ``from django.db.models.query import QuerySet``, exercising
    the except-branch that was previously unreachable.
    """
    import sys

    class DuckQS:
        """Minimal queryset-like stub: has __iter__ and .model, no _meta."""
        model = type("FakeModel", (), {})()
        def __iter__(self): return iter([])

    real_module = sys.modules.get('django.db.models.query')
    sys.modules['django.db.models.query'] = None  # type: ignore[assignment]
    try:
        result = _is_queryset_like(DuckQS())
    finally:
        if real_module is not None:
            sys.modules['django.db.models.query'] = real_module
        else:
            sys.modules.pop('django.db.models.query', None)

    assert result is True


def test_is_queryset_like_importerror_rejects_plain_object():
    """Duck-typing fallback must still reject objects that lack .model."""
    import sys

    real_module = sys.modules.get('django.db.models.query')
    sys.modules['django.db.models.query'] = None  # type: ignore[assignment]
    try:
        result = _is_queryset_like(object())
    finally:
        if real_module is not None:
            sys.modules['django.db.models.query'] = real_module
        else:
            sys.modules.pop('django.db.models.query', None)

    assert result is False


def test_is_queryset_like_importerror_rejects_object_with_meta():
    """Duck-typing fallback must reject objects that have _meta (model instances)."""
    import sys

    class ModelLike:
        """Has __iter__ and .model AND ._meta — must be rejected."""
        model = object()
        _meta = object()
        def __iter__(self): return iter([])

    real_module = sys.modules.get('django.db.models.query')
    sys.modules['django.db.models.query'] = None  # type: ignore[assignment]
    try:
        result = _is_queryset_like(ModelLike())
    finally:
        if real_module is not None:
            sys.modules['django.db.models.query'] = real_module
        else:
            sys.modules.pop('django.db.models.query', None)

    assert result is False
