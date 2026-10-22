"""Tests for slice syntax and Python-compatible slice semantics."""

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


def test_basic_slice(capsys):
    out = run_both(
        "let xs = [0, 1, 2, 3, 4, 5]\n"
        "print(xs[2:5])\n", capsys)
    assert out == "[2, 3, 4]\n"


def test_open_start(capsys):
    out = run_both(
        "let xs = [0, 1, 2, 3, 4, 5]\n"
        "print(xs[:3])\n", capsys)
    assert out == "[0, 1, 2]\n"


def test_open_stop(capsys):
    out = run_both(
        "let xs = [0, 1, 2, 3, 4, 5]\n"
        "print(xs[3:])\n", capsys)
    assert out == "[3, 4, 5]\n"


def test_full_slice(capsys):
    out = run_both(
        "let xs = [0, 1, 2, 3, 4, 5]\n"
        "print(xs[:])\n", capsys)
    assert out == "[0, 1, 2, 3, 4, 5]\n"


def test_step(capsys):
    out = run_both(
        "let xs = [0, 1, 2, 3, 4, 5]\n"
        "print(xs[::2])\n", capsys)
    assert out == "[0, 2, 4]\n"


def test_start_stop_step(capsys):
    out = run_both(
        "let xs = [0, 1, 2, 3, 4, 5, 6, 7]\n"
        "print(xs[1:8:3])\n", capsys)
    assert out == "[1, 4, 7]\n"


def test_negative_step_reverses(capsys):
    out = run_both(
        "let xs = [0, 1, 2, 3, 4]\n"
        "print(xs[::-1])\n", capsys)
    assert out == "[4, 3, 2, 1, 0]\n"


def test_negative_step_with_bounds(capsys):
    out = run_both(
        "let xs = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]\n"
        "print(xs[8:2:-2])\n", capsys)
    assert out == "[8, 6, 4]\n"


def test_negative_start(capsys):
    out = run_both(
        "let xs = [0, 1, 2, 3, 4, 5]\n"
        "print(xs[-2:])\n", capsys)
    assert out == "[4, 5]\n"


def test_negative_stop(capsys):
    out = run_both(
        "let xs = [0, 1, 2, 3, 4, 5]\n"
        "print(xs[:-2])\n", capsys)
    assert out == "[0, 1, 2, 3]\n"


def test_out_of_range_is_clamped(capsys):
    out = run_both(
        "let xs = [0, 1, 2]\n"
        "print(xs[-100:100])\n", capsys)
    assert out == "[0, 1, 2]\n"


def test_empty_result(capsys):
    out = run_both(
        "let xs = [0, 1, 2, 3, 4]\n"
        "print(xs[3:1])\n", capsys)
    assert out == "[]\n"


def test_string_slice(capsys):
    out = run_both(
        'let text = "abcdef"\n'
        'print(text[1:4])\n', capsys)
    assert out == "bcd\n"


def test_string_negative_step(capsys):
    out = run_both(
        'let text = "abcdef"\n'
        'print(text[::-1])\n', capsys)
    assert out == "fedcba\n"


def test_slice_assignment(capsys):
    out = run_both(
        "var xs = [1, 2, 3, 4, 5]\n"
        "xs[1:3] = [9, 9]\n"
        "print(xs)\n", capsys)
    assert out == "[1, 9, 9, 4, 5]\n"


def test_slice_assignment_shrinks(capsys):
    out = run_both(
        "var xs = [1, 2, 3, 4, 5]\n"
        "xs[1:3] = []\n"
        "print(xs)\n", capsys)
    assert out == "[1, 4, 5]\n"


def test_slice_assignment_grows(capsys):
    out = run_both(
        "var xs = [1, 2, 3]\n"
        "xs[0:0] = [7, 8]\n"
        "print(xs)\n", capsys)
    assert out == "[7, 8, 1, 2, 3]\n"


def test_extended_slice_assignment_requires_matching_length(capsys):
    with pytest.raises(BunError) as info:
        run_source("var xs = [1, 2, 3, 4]\nxs[::2] = [1, 2, 3]\n",
                   filename="<test>.bun")
    assert "extended slice" in str(info.value)


def test_zero_step_is_rejected(capsys):
    with pytest.raises(BunError) as info:
        run_source("let xs = [1, 2, 3]\nprint(xs[::0])\n",
                   filename="<test>.bun")
    assert "slice step cannot be zero" in str(info.value)


def test_slice_of_non_sequence_is_rejected(capsys):
    with pytest.raises(BunError) as info:
        run_source("let x = 5\nprint(x[0:1])\n", filename="<test>.bun")
    assert "not sliceable" in str(info.value)


def test_slice_in_expression(capsys):
    out = run_both(
        "let xs = [1, 2, 3, 4]\n"
        "var total = 0\n"
        "for x in xs[1:3] {\n"
        "  total = total + x\n"
        "}\n"
        "print(total)\n", capsys)
    assert out == "5\n"


def test_slice_of_function_result(capsys):
    out = run_both(
        "fn make() -> list {\n"
        "  return [1, 2, 3, 4]\n"
        "}\n"
        "print(make()[1:3])\n", capsys)
    assert out == "[2, 3]\n"


def test_nested_slice(capsys):
    out = run_both(
        "let grid = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]\n"
        "print(grid[1][0:2])\n", capsys)
    assert out == "[4, 5]\n"


def test_slice_of_slice(capsys):
    out = run_both(
        "let xs = [0, 1, 2, 3, 4, 5, 6, 7]\n"
        "print(xs[1:7][::2])\n", capsys)
    assert out == "[1, 3, 5]\n"
