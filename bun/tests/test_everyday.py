"""Tests for the everyday expressions of the language."""

import pytest

from bun.cli import run_source
from bun.errors import BunError, ParseError


def run_both(source, capsys):
    run_source(source, filename="<everyday>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<everyday>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    return vm_out


def test_compound_assign_on_a_name(capsys):
    out = run_both("var x = 1\nx += 4\nprint(x)\n", capsys)
    assert out == "5\n"


def test_compound_assign_on_an_index(capsys):
    out = run_both("var items = [1, 2]\nitems[0] += 10\nprint(items)\n", capsys)
    assert out == "[11, 2]\n"


def test_increment_is_a_statement(capsys):
    out = run_both("var i = 0\ni++\nprint(i)\n++i\nprint(i)\n", capsys)
    assert out == "1\n2\n"


def test_increment_is_not_an_expression():
    with pytest.raises(ParseError) as info:
        run_source("print(x++)\n", filename="<everyday>.bun", check=True)
    assert "the increment is a statement, not an expression" in info.value.msg


def test_null_coalesce(capsys):
    out = run_both("print(null ?? 7)\nprint(3 ?? 7)\n", capsys)
    assert out == "7\n3\n"


def test_null_coalesce_under_the_fused_tier(capsys):
    source = "var a = null\nvar b = 2\nprint(a ?? 7)\nprint(b ?? 7)\n"
    run_source(source, filename="<everyday>.bun", check=True, engine="register",
               tier=True)
    fused_out = capsys.readouterr().out
    run_source(source, filename="<everyday>.bun", check=True, engine="register")
    assert fused_out == capsys.readouterr().out == "7\n2\n"


def test_match_expression(capsys):
    out = run_both("print(match 2 { 1 => \"one\" 2 => \"two\" _ => \"many\" })\n",
                   capsys)
    assert out == "two\n"


def test_match_expression_refuses_a_block():
    with pytest.raises(BunError) as info:
        run_source("var x = match 1 { 1 => { 2 } }\n",
                   filename="<everyday>.bun", check=True)
    assert "the arm of a match expression answers a value, not a block" in (
        info.value.msg)
