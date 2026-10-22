"""Tests for list and dict comprehensions."""

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


def test_simple_list_comprehension(capsys):
    out = run_both(
        "let xs = [1, 2, 3]\n"
        "print([x for x in xs])\n", capsys)
    assert out == "[1, 2, 3]\n"


def test_transforming_comprehension(capsys):
    out = run_both(
        "let xs = [1, 2, 3]\n"
        "print([x * 2 for x in xs])\n", capsys)
    assert out == "[2, 4, 6]\n"


def test_comprehension_with_condition(capsys):
    out = run_both(
        "let xs = [1, 2, 3, 4, 5, 6]\n"
        "print([x for x in xs if x % 2 == 0])\n", capsys)
    assert out == "[2, 4, 6]\n"


def test_comprehension_over_range(capsys):
    out = run_both(
        "print([x for x in range(5)])\n", capsys)
    assert out == "[0, 1, 2, 3, 4]\n"


def test_multiple_for_clauses(capsys):
    out = run_both(
        "let xs = [1, 2]\n"
        "print([x + y for x in xs for y in [10, 20]])\n", capsys)
    assert out == "[11, 21, 12, 22]\n"


def test_multiple_clauses_with_condition(capsys):
    out = run_both(
        "let xs = [1, 2, 3]\n"
        "print([x * y for x in xs for y in [2, 3] if x != y])\n", capsys)
    assert out == "[2, 3, 6, 6]\n"


def test_dict_comprehension(capsys):
    out = run_both(
        "let xs = [1, 2, 3]\n"
        "print({x: x * x for x in xs})\n", capsys)
    assert out == "{1: 1, 2: 4, 3: 9}\n"


def test_dict_comprehension_with_condition(capsys):
    out = run_both(
        "let xs = [1, 2, 3, 4]\n"
        "print({x: x for x in xs if x % 2 == 0})\n", capsys)
    assert out == "{2: 2, 4: 4}\n"


def test_empty_comprehension(capsys):
    out = run_both(
        "print([x for x in []])\n", capsys)
    assert out == "[]\n"


def test_comprehension_variable_does_not_leak(capsys):
    out = run_both(
        "let x = 1\n"
        "print([x for x in [2, 3]])\n"
        "print(x)\n", capsys)
    assert out == "[2, 3]\n1\n"


def test_comprehension_shadows_outer_variable(capsys):
    out = run_both(
        "let x = 1\n"
        "print([x for x in [2, 3]])\n"
        "print(x)\n", capsys)
    assert out == "[2, 3]\n1\n"


def test_nested_comprehension(capsys):
    out = run_both(
        "print([[y for y in [1, 2]] for x in [1, 2]])\n", capsys)
    assert out == "[[1, 2], [1, 2]]\n"


def test_comprehension_over_strings(capsys):
    out = run_both(
        'print([c for c in "abc"])\n', capsys)
    assert out == "[a, b, c]\n"


def test_comprehension_result_can_be_indexed(capsys):
    out = run_both(
        "let xs = [1, 2, 3, 4]\n"
        "print([x for x in xs][1])\n", capsys)
    assert out == "2\n"


def test_comprehension_result_can_be_sliced(capsys):
    out = run_both(
        "let xs = [1, 2, 3, 4]\n"
        "print([x for x in xs][1:3])\n", capsys)
    assert out == "[2, 3]\n"


def test_comprehension_inside_function(capsys):
    out = run_both(
        "fn evens(xs: list) -> list {\n"
        "  return [x for x in xs if x % 2 == 0]\n"
        "}\n"
        "print(evens([1, 2, 3, 4]))\n", capsys)
    assert out == "[2, 4]\n"


def test_comprehension_in_loop(capsys):
    out = run_both(
        "var out = []\n"
        "for i in [1, 2] {\n"
        "  out.push([j for j in [1, 2]])\n"
        "}\n"
        "print(out)\n", capsys)
    assert out == "[[1, 2], [1, 2]]\n"


def test_comprehension_over_call_result(capsys):
    out = run_both(
        "fn make() -> list {\n"
        "  return [1, 2, 3]\n"
        "}\n"
        "print([x * 2 for x in make()])\n", capsys)
    assert out == "[2, 4, 6]\n"


def test_comprehension_over_dict_values(capsys):
    out = run_both(
        "let d = {\"a\": 1, \"b\": 2}\n"
        "print([k for k in d.keys()])\n", capsys)
    assert out == "[a, b]\n"


def test_missing_for_in_comprehension_is_error():
    with pytest.raises(BunError) as info:
        run_source("print([x for x])\n", filename="<test>.bun")
    assert "expected 'in'" in str(info.value)


def test_comprehension_needs_a_loop_variable(capsys):
    with pytest.raises(BunError) as info:
        run_source("print([x for 1 in [2]])\n", filename="<test>.bun")
    assert "loop variable name" in str(info.value)


def test_two_conditions_are_rejected():
    with pytest.raises(BunError) as info:
        run_source("print([x for x in [1] if x if x])\n", filename="<test>.bun")
    assert "expected ']'" in str(info.value)


def test_comprehension_type_is_a_list(capsys):
    out = run_both(
        "let xs = [1, 2, 3]\n"
        "let c = [x for x in xs]\n"
        "print(type_of(c))\n", capsys)
    assert out == "array\n"


def test_comprehension_type_is_a_dict(capsys):
    out = run_both(
        "let xs = [1, 2, 3]\n"
        "let c = {x: x for x in xs}\n"
        "print(type_of(c))\n", capsys)
    assert out == "dict\n"
