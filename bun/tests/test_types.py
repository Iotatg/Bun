"""The tests of the type names of the language.

A program may say `number` where it means `float`, and `text` where it
means `string`.  The alias is kept in the message of an error, so a
program that says `number` is told about a `number`.
"""

import pytest

from bun.cli import run_source
from bun.errors import BunRuntimeError, BunTypeError


def run_both(source, capsys):
    """Run the same source on every engine and assert identical output."""
    run_source(source, filename="<types>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<types>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    run_source(source, filename="<types>.bun", check=True, engine="register")
    reg_out = capsys.readouterr().out
    assert vm_out == reg_out
    return vm_out


def run_error(source, capsys):
    """Run a source that must fail, and return the message."""
    with pytest.raises((BunRuntimeError, BunTypeError)) as info:
        run_source(source, filename="<types>.bun", check=True, engine="vm")
    return info.value.msg


def test_a_number_is_a_float(capsys):
    out = run_both(
        "let x: number = 1.5\n"
        "print(x)\n", capsys)
    assert out == "1.5\n"


def test_an_int_is_a_number(capsys):
    out = run_both(
        "let x: number = 2\n"
        "print(x)\n", capsys)
    assert out == "2\n"


def test_a_text_is_a_string(capsys):
    out = run_both(
        "let x: text = \"hello\"\n"
        "print(x)\n", capsys)
    assert out == "hello\n"


def test_an_alias_may_be_the_type_of_a_parameter(capsys):
    out = run_both(
        "fn show(a: number, b: text) -> text {\n"
        "    return b + str(a)\n"
        "}\n"
        "print(show(1.5, \"the \"))\n", capsys)
    assert out == "the 1.5\n"


def test_a_string_is_not_a_number(capsys):
    assert run_error(
        "let x: number = \"hello\"\n", capsys) == \
        "cannot assign value of type 'string' to variable 'x' of type 'number'"


def test_a_number_is_not_a_text(capsys):
    assert run_error(
        "let x: text = 1.5\n", capsys) == \
        "cannot assign value of type 'float' to variable 'x' of type 'text'"


def test_a_name_that_is_not_a_type_is_an_error(capsys):
    assert run_error(
        "let x: money = 1\n", capsys) == "unknown type 'money'"
