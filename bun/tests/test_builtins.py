"""Tests for the everyday builtins of the language.

The builtins that Python has and a program reaches for on the first
line: the truth of a value, the total of a collection, the pairs of two
collections. Every test runs on both engines, and the ones the native
backend can take run there too.
"""

import pytest

from bun.cli import run_source
from bun.errors import BunRuntimeError


def run_both(source, capsys):
    """Run the same source on both engines and assert identical output."""
    run_source(source, filename="<builtins>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<builtins>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    return vm_out


def test_the_truth_of_a_value(capsys):
    out = run_both(
        "print(str(bool(0)))\n"
        "print(str(bool(1)))\n"
        "print(str(bool(\"\")))\n"
        "print(str(bool(\"x\")))\n"
        "print(str(bool([])))\n"
        "print(str(bool([0])))\n"
        "print(str(bool(null)))\n", capsys)
    assert out == ("false\ntrue\nfalse\ntrue\nfalse\ntrue\nfalse\n")


def test_the_size_of_a_number(capsys):
    out = run_both(
        "print(str(abs(-3)))\n"
        "print(str(abs(3)))\n"
        "print(str(abs(-3.5)))\n", capsys)
    assert out == "3\n3\n3.5\n"


def test_the_total_of_a_list(capsys):
    out = run_both(
        "print(str(sum([1, 2, 3])))\n"
        "print(str(sum([])))\n"
        "print(str(sum([1.5, 2.5])))\n", capsys)
    assert out == "6\n0\n4.0\n"


def test_the_truth_of_a_list(capsys):
    out = run_both(
        "print(str(any([0, 1])))\n"
        "print(str(any([0, 0])))\n"
        "print(str(any([])))\n"
        "print(str(all([1, 1])))\n"
        "print(str(all([1, 0])))\n"
        "print(str(all([])))\n", capsys)
    assert out == ("true\nfalse\nfalse\ntrue\nfalse\ntrue\n")


def test_the_smallest_and_the_largest(capsys):
    out = run_both(
        "print(str(min([3, 1, 2])))\n"
        "print(str(max([3, 1, 2])))\n"
        "print(str(min([\"b\", \"a\"])))\n"
        "print(str(max([\"b\", \"a\"])))\n", capsys)
    assert out == "1\n3\na\nb\n"


def test_the_pairs_of_two_lists(capsys):
    out = run_both(
        "print(str(zip([1, 2], [\"a\", \"b\"])))\n"
        "print(str(zip([1, 2, 3], [\"a\"])))\n", capsys)
    assert out == "[[1, a], [2, b]]\n[[1, a]]\n"


def test_the_numbers_of_a_list(capsys):
    out = run_both(
        "print(str(enumerate([\"a\", \"b\"])))\n", capsys)
    assert out == "[[0, a], [1, b]]\n"


def test_a_sorted_list_is_a_new_list(capsys):
    out = run_both(
        "let values = [3, 1, 2]\n"
        "let ordered = sorted(values)\n"
        "print(str(ordered))\n"
        "print(str(values))\n", capsys)
    assert out == "[1, 2, 3]\n[3, 1, 2]\n"


def test_the_sort_refuses_values_that_cannot_be_compared(capsys):
    with pytest.raises(BunRuntimeError) as info:
        run_source("sorted([{\"a\": 1}, {\"a\": 2}])\n",
                   filename="<builtins>.bun", check=True, engine="vm")
    assert "cannot compare" in info.value.msg


def test_a_list_backwards(capsys):
    out = run_both(
        "print(str(reversed([1, 2, 3])))\n", capsys)
    assert out == "[3, 2, 1]\n"


def test_the_sum_of_a_list_of_text_is_an_error(capsys):
    with pytest.raises(BunRuntimeError) as info:
        run_source("sum([\"a\"])\n", filename="<builtins>.bun", check=True,
                   engine="vm")
    assert "numbers" in info.value.msg


def test_the_smallest_of_an_empty_list_is_an_error(capsys):
    with pytest.raises(BunRuntimeError) as info:
        run_source("min([])\n", filename="<builtins>.bun", check=True,
                   engine="vm")
    assert "at least one value" in info.value.msg


def test_two_values_of_different_types_cannot_be_compared(capsys):
    with pytest.raises(BunRuntimeError) as info:
        run_source("min([1, \"a\"])\n", filename="<builtins>.bun", check=True,
                   engine="vm")
    assert "cannot compare" in info.value.msg


NATIVE_PROGRAM = """
print(str(bool([])))
print(str(abs(-3)))
print(str(min([3, 1, 2])))
print(str(max([3, 1, 2])))
"""


def test_the_native_backend_agrees_on_the_builtins(capfd):
    import shutil
    if shutil.which("cc") is None:
        pytest.skip("no C compiler")
    run_source(NATIVE_PROGRAM, filename="<builtins>.bun", check=True,
               engine="vm")
    expected = capfd.readouterr().out
    run_source(NATIVE_PROGRAM, filename="<builtins>.bun", check=True,
               engine="c")
    assert capfd.readouterr().out == expected


# ---------------------------------------------------------------------------
# The hints of the errors
# ---------------------------------------------------------------------------

def test_an_error_says_what_to_do_next(capsys, tmp_path):
    """The hint of an error is under the error."""
    from bun.errors import format_error
    program = tmp_path / "bad.bun"
    program.write_text("let xs = []\nlet item = xs[3]\n")
    with pytest.raises(BunRuntimeError) as info:
        run_source(program.read_text(), filename=str(program), check=True,
                   engine="vm")
    text = format_error(info.value, program.read_text(), str(program))
    assert "hint:" in text
    assert "the index is past the end" in text


def test_the_hint_of_an_undefined_name(capsys):
    from bun.errors import hint_for
    assert "declare the name" in hint_for("undefined variable 'x'")
    assert hint_for("something nobody knows") is None
