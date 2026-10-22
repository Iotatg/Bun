"""Tests for unpacking assignments and declarations."""

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


def test_two_names(capsys):
    out = run_both(
        "let a, b = [1, 2]\n"
        "print(a)\n"
        "print(b)\n", capsys)
    assert out == "1\n2\n"


def test_mutable_unpacking(capsys):
    out = run_both(
        "var a, b = [1, 2]\n"
        "a = 10\n"
        "print(a + b)\n", capsys)
    assert out == "12\n"


def test_star_captures_the_rest(capsys):
    out = run_both(
        "let first, *rest = [1, 2, 3, 4]\n"
        "print(first)\n"
        "print(rest)\n", capsys)
    assert out == "1\n[2, 3, 4]\n"


def test_star_can_be_empty(capsys):
    out = run_both(
        "let first, *rest = [1]\n"
        "print(rest)\n", capsys)
    assert out == "[]\n"


def test_list_pattern(capsys):
    out = run_both(
        "let [x, y] = [7, 8]\n"
        "print(x)\n"
        "print(y)\n", capsys)
    assert out == "7\n8\n"


def test_nested_list_pattern(capsys):
    out = run_both(
        "let [m, n] = [[1, 2], [3, 4]]\n"
        "print(m)\n"
        "print(n)\n", capsys)
    assert out == "[1, 2]\n[3, 4]\n"


def test_deeply_nested_list_pattern(capsys):
    out = run_both(
        "let [[a, b], [c, d]] = [[1, 2], [3, 4]]\n"
        "print(a)\n"
        "print(d)\n", capsys)
    assert out == "1\n4\n"


def test_tuple_assignment(capsys):
    out = run_both(
        "var a = 0\n"
        "var b = 0\n"
        "a, b = [5, 6]\n"
        "print(a)\n"
        "print(b)\n", capsys)
    assert out == "5\n6\n"


def test_list_assignment(capsys):
    out = run_both(
        "var a = 0\n"
        "[a] = [42]\n"
        "print(a)\n", capsys)
    assert out == "42\n"


def test_list_assignment_with_two_targets(capsys):
    out = run_both(
        "var a = 0\n"
        "var b = 0\n"
        "[a, b] = [1, 2]\n"
        "print(a)\n"
        "print(b)\n", capsys)
    assert out == "1\n2\n"


def test_unpacking_a_string(capsys):
    out = run_both(
        "let first, second = \"hi\"\n"
        "print(first)\n"
        "print(second)\n", capsys)
    assert out == "h\ni\n"


def test_unpacking_a_function_result(capsys):
    out = run_both(
        "fn make() -> list {\n"
        "  return [11, 22]\n"
        "}\n"
        "let [a, b] = make()\n"
        "print(a)\n"
        "print(b)\n", capsys)
    assert out == "11\n22\n"


def test_star_inside_a_list_pattern(capsys):
    out = run_both(
        "let [a, *middle, z] = [1, 2, 3, 4]\n"
        "print(a)\n"
        "print(middle)\n"
        "print(z)\n", capsys)
    assert out == "1\n[2, 3]\n4\n"


def test_unpacking_a_non_iterable_is_an_error(capsys):
    with pytest.raises(BunError) as info:
        run_source("let a, b = 5\n", filename="<test>.bun")
    assert "cannot unpack" in str(info.value)


def test_too_many_values_is_an_error(capsys):
    with pytest.raises(BunError) as info:
        run_source("let a, b = [1, 2, 3]\n", filename="<test>.bun")
    assert "too many values to unpack (expected 2)" in str(info.value)


def test_too_few_values_is_an_error(capsys):
    with pytest.raises(BunError) as info:
        run_source("let a, b = [1]\n", filename="<test>.bun")
    assert "not enough values to unpack (expected 2, got 1)" in str(info.value)


def test_star_still_needs_the_other_values(capsys):
    with pytest.raises(BunError) as info:
        run_source("let a, *rest = []\n", filename="<test>.bun")
    assert "not enough values to unpack (expected 1, got 0)" in str(info.value)


def test_unpacking_into_an_immutable_is_an_error(capsys):
    with pytest.raises(BunError) as info:
        run_source(
            "let a = 1\n"
            "a, b = [2, 3]\n", filename="<test>.bun")
    assert "cannot assign to immutable variable 'a'" in str(info.value)


def test_unpacking_does_not_leak_into_the_next_statement(capsys):
    out = run_both(
        "var total = 0\n"
        "[total] = [3]\n"
        "print(total)\n", capsys)
    assert out == "3\n"


def test_unpacking_into_an_index(capsys):
    out = run_both(
        "var xs = [0, 0]\n"
        "[xs[0], xs[1]] = [4, 5]\n"
        "print(xs)\n", capsys)
    assert out == "[4, 5]\n"
