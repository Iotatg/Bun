"""Tests for f-string interpolation, formatting, and conversions."""

import pytest

from bun.cli import run_source
from bun.errors import BunError


def run_both(source, capsys):
    """Run the same source on both engines and assert identical output."""
    run_source(source, filename="<test>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<test>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    return vm_out


def test_simple_interpolation(capsys):
    out = run_both(
        'let name = "world"\n'
        'print(f"hello {name}")\n', capsys)
    assert out == "hello world\n"


def test_expression_inside_braces(capsys):
    out = run_both(
        'let a = 2\n'
        'let b = 3\n'
        'print(f"{a + b} {a * b} {a - b} {a / b}")\n', capsys)
    assert out == "5 6 -1 0\n"


def test_function_call_inside_braces(capsys):
    out = run_both(
        'let items = [1, 2, 3]\n'
        'print(f"count={len(items)}")\n', capsys)
    assert out == "count=3\n"


def test_escaped_braces(capsys):
    out = run_both(
        'print(f"{{literal}}")\n'
        'print(f"a{{b}}c")\n', capsys)
    assert out == "{literal}\na{b}c\n"


def test_literal_only_fstring(capsys):
    out = run_both('print(f"no interpolation")\n', capsys)
    assert out == "no interpolation\n"


def test_empty_interpolation_is_error():
    with pytest.raises(BunError) as info:
        run_source('print(f"empty {}")\n', filename="<test>.bun")
    assert "empty expression in f-string" in str(info.value)


def test_single_closing_brace_is_error():
    with pytest.raises(BunError) as info:
        run_source('print(f"lonely }")\n', filename="<test>.bun")
    assert "single '}' in f-string" in str(info.value)


def test_repr_conversion(capsys):
    out = run_both(
        'let text = "quoted"\n'
        'print(f"{text!r}")\n', capsys)
    assert out == '"quoted"\n'


def test_str_conversion(capsys):
    out = run_both(
        'let n = 42\n'
        'print(f"{n!s}")\n', capsys)
    assert out == "42\n"


def test_invalid_conversion_is_error():
    with pytest.raises(BunError) as info:
        run_source('let n = 1\nprint(f"{n!z}")\n', filename="<test>.bun")
    assert "invalid f-string conversion" in str(info.value)


def test_self_documenting_form(capsys):
    out = run_both(
        'let n = 42\n'
        'print(f"{n = }")\n'
        'print(f"{n=}")\n', capsys)
    assert out == "n =42\nn=42\n"


def test_width_and_alignment(capsys):
    out = run_both(
        'let n = 42\n'
        'print(f"[{n:5}]")\n'
        'print(f"[{n:<5}]")\n'
        'print(f"[{n:>5}]")\n'
        'print(f"[{n:^5}]")\n', capsys)
    assert out == "[   42]\n[42   ]\n[   42]\n[ 42  ]\n"


def test_zero_padding(capsys):
    out = run_both(
        'let n = 42\n'
        'print(f"{n:05}")\n', capsys)
    assert out == "00042\n"


def test_precision(capsys):
    out = run_both(
        'let pi = 3.14159\n'
        'print(f"{pi:.2f}")\n', capsys)
    assert out == "3.14\n"


def test_thousands_separator(capsys):
    out = run_both('print(f"{1234567:,}")\n', capsys)
    assert out == "1,234,567\n"


def test_numeric_types(capsys):
    out = run_both(
        'print(f"{255:x}")\n'
        'print(f"{255:X}")\n'
        'print(f"{64:o}")\n'
        'print(f"{5:b}")\n', capsys)
    assert out == "ff\nFF\n100\n101\n"


def test_percentage(capsys):
    out = run_both('print(f"{0.5:.1%}")\n', capsys)
    assert out == "50.0%\n"


def test_nested_fstring(capsys):
    out = run_both(
        'let n = 42\n'
        'print(f"nested {f"inner {n}"}")\n', capsys)
    assert out == "nested inner 42\n"


def test_nested_quotes_in_expression(capsys):
    out = run_both(
        'let text = "quoted"\n'
        'print(f"{text!r}")\n'
        "print(f\"{'single'}\")\n", capsys)
    assert out == '"quoted"\nsingle\n'


def test_fstring_with_escapes(capsys):
    out = run_both(
        'let n = 1\n'
        'print(f"line\\nnext {n}")\n', capsys)
    assert out == "line\nnext 1\n"


def test_fstring_in_function(capsys):
    out = run_both(
        'fn greet(name: string) -> string {\n'
        '  return f"hi {name}"\n'
        '}\n'
        'print(greet("bun"))\n', capsys)
    assert out == "hi bun\n"


def test_fstring_concatenation(capsys):
    out = run_both(
        'let a = "x"\n'
        'let b = "y"\n'
        'print(f"{a}{b}")\n', capsys)
    assert out == "xy\n"


def test_fstring_value_is_string(capsys):
    out = run_both(
        'let n = 1\n'
        'let s = f"{n}"\n'
        'print(type_of(s))\n', capsys)
    assert out == "string\n"
