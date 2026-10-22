"""Tests for the `eval` builtin."""

import pytest

from bun.cli import run_source
from bun.errors import BunRuntimeError, BunTypeError


def run_both(source, capsys):
    """Run the same source on both engines and assert identical output."""
    run_source(source, filename="<test>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<test>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    return vm_out


def test_eval_returns_the_last_expression(capsys):
    out = run_both("print(eval(\"1 + 1\"))\n", capsys)
    assert out == "2\n"


def test_eval_runs_a_whole_program(capsys):
    out = run_both(
        "print(eval(\"let a = 5\\na * 2\"))\n", capsys)
    assert out == "10\n"


def test_eval_without_an_expression_is_null(capsys):
    out = run_both("print(eval(\"let a = 5\"))\n", capsys)
    assert out == "null\n"


def test_eval_of_a_list_and_a_dict(capsys):
    out = run_both(
        "print(eval(\"[1, 2, 3]\"))\n"
        "print(eval(\"{\\\"a\\\": 1}\")[\"a\"])\n", capsys)
    assert out == "[1, 2, 3]\n1\n"


def test_eval_sees_the_builtins(capsys):
    out = run_both("print(eval(\"len([1, 2])\"))\n", capsys)
    assert out == "2\n"


def test_a_syntax_error_is_catchable(capsys):
    out = run_both(
        "try {\n"
        "    eval(\"1 +\")\n"
        "} catch err {\n"
        "    print(err)\n"
        "}\n", capsys)
    assert out.startswith("eval() failed: ")


def test_an_undefined_name_is_catchable(capsys):
    out = run_both(
        "try {\n"
        "    eval(\"print(nope)\")\n"
        "} catch err {\n"
        "    print(err)\n"
        "}\n", capsys)
    assert out == "eval() failed: undefined variable 'nope'\n"


def test_a_runtime_error_keeps_its_message(capsys):
    out = run_both(
        "try {\n"
        "    eval(\"throw \\\"boom\\\"\")\n"
        "} catch err {\n"
        "    print(err)\n"
        "}\n", capsys)
    assert out == "boom\n"


def test_eval_of_a_non_string_is_an_error():
    with pytest.raises(BunTypeError) as info:
        run_source("eval(1)\n", filename="<test>.bun", check=True, engine="vm")
    assert "eval() received arguments that do not match its signature" in str(
        info.value)


def test_eval_with_two_arguments_is_an_error():
    with pytest.raises(BunTypeError) as info:
        run_source("eval(\"1\", \"2\")\n", filename="<test>.bun", check=True,
                   engine="vm")
    assert "eval() received arguments that do not match its signature" in str(
        info.value)


def test_eval_does_not_see_the_caller_scope(capsys):
    out = run_both(
        "let secret_value = 42\n"
        "try {\n"
        "    eval(\"print(secret_value)\")\n"
        "} catch err {\n"
        "    print(err)\n"
        "}\n", capsys)
    assert out == "eval() failed: undefined variable 'secret_value'\n"
