"""The tests of the set of the language.

A set holds the values that are not equal to each other.  The set is a
value like a list and a dict, so every engine prints the same thing for
it, and the checker knows its type.
"""

import pytest

from bun.cli import run_source
from bun.errors import BunRuntimeError, BunTypeError


def run_both(source, capsys):
    """Run the same source on every engine and assert identical output."""
    run_source(source, filename="<set>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<set>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    run_source(source, filename="<set>.bun", check=True, engine="register")
    reg_out = capsys.readouterr().out
    assert vm_out == reg_out
    return vm_out


def run_error(source, capsys):
    """Run a source that must fail, and return the message."""
    with pytest.raises((BunRuntimeError, BunTypeError)) as info:
        run_source(source, filename="<set>.bun", check=True, engine="vm")
    return info.value.msg


def test_a_set_keeps_the_values_that_are_not_equal(capsys):
    out = run_both(
        "let s = set([1, 2, 3, 2, 1])\n"
        "print(s.len())\n", capsys)
    assert out == "3\n"


def test_a_set_keeps_the_order_of_the_values(capsys):
    out = run_both(
        "let s = set([\"b\", \"a\", \"c\"])\n"
        "print(s.values().join(\",\"))\n", capsys)
    assert out == "b,a,c\n"


def test_a_set_knows_what_it_holds(capsys):
    out = run_both(
        "let s = set([1, 2])\n"
        "print(s.contains(2))\n"
        "print(s.contains(9))\n", capsys)
    assert out == "true\nfalse\n"


def test_a_set_takes_a_value_and_loses_one(capsys):
    out = run_both(
        "let s = set([1])\n"
        "s.add(2)\n"
        "s.remove(1)\n"
        "print(s.values().join(\",\"))\n", capsys)
    assert out == "2\n"


def test_the_sets_are_joined(capsys):
    out = run_both(
        "let a = set([1, 2])\n"
        "let b = set([2, 3])\n"
        "print((a | b).len())\n"
        "print((a & b).len())\n"
        "print((a - b).values().join(\",\"))\n", capsys)
    assert out == "3\n1\n1\n"


def test_a_set_is_a_value_of_its_own(capsys):
    out = run_both(
        "let s = set([1])\n"
        "print(type_of(s))\n"
        "print(s)\n", capsys)
    assert out == "set\n{1}\n"


def test_two_sets_with_the_same_values_are_equal(capsys):
    out = run_both(
        "print(set([1, 2]) == set([2, 1]))\n"
        "print(set([1]) == set([2]))\n", capsys)
    assert out == "true\nfalse\n"


def test_a_set_can_be_walked(capsys):
    out = run_both(
        "let s = set([1, 2, 3])\n"
        "var total = 0\n"
        "for value in s {\n"
        "    total = total + value\n"
        "}\n"
        "print(total)\n", capsys)
    assert out == "6\n"


def test_an_empty_set_is_empty(capsys):
    out = run_both(
        "let s = set()\n"
        "print(s.len())\n"
        "print(s.contains(1))\n", capsys)
    assert out == "0\nfalse\n"


def test_a_set_of_values_it_cannot_hold_is_an_error(capsys):
    assert run_error("set([1, [2]])\n", capsys) == \
        "dict keys must be strings, numbers, or null"


def test_a_set_needs_a_list(capsys):
    assert run_error("set(1)\n", capsys) == \
        "set() received arguments that do not match its signature " \
        "(expected 0 or 1 argument(s))"


def test_the_type_of_a_set_is_known(capsys):
    out = run_both(
        "let s: set = set([1])\n"
        "print(s.len())\n", capsys)
    assert out == "1\n"


def test_a_set_is_not_a_list(capsys):
    assert run_error(
        "let s: list = set([1])\n", capsys) == \
        "cannot assign value of type 'set' to variable 's' of type 'list'"


def test_a_value_that_is_not_in_a_set_cannot_be_removed(capsys):
    assert run_error(
        "let s = set([1])\n"
        "s.remove(9)\n", capsys) == "value not in set"
