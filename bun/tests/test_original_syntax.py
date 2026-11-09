"""Tests of the 0.4.0 wave: Bun's own syntax for four language capabilities.

The wave adds a scope-exit action (`on leave`), recursive type arguments
(`list of list of int`), a function type as a parameter (`fn(int) -> int`),
and a named loop (`for ... as outer` with `break outer`).  The tests run
every construct on the tree interpreter and both virtual machines, check
that the checker rejects the mistakes, and check that the Bun-written
front end reads the same programs.
"""

import json
import os
import subprocess
import sys

import pytest

from bun.cli import run_file, run_source
from bun.errors import BunTypeError
from bun import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def run_all(source, capsys):
    """Run one program on the tree interpreter and both virtual machines."""
    outputs = []
    for engine in ("tree", "vm", "register"):
        run_source(source, filename="<test>.bun", check=True, engine=engine)
        outputs.append(capsys.readouterr().out)
    assert len(set(outputs)) == 1, outputs
    return outputs[0]


# ---------------------------------------------------------------------------
# `on leave`
# ---------------------------------------------------------------------------

def test_on_leave_runs_before_the_caller_sees_the_value(capsys):
    out = run_all(
        "fn f() -> int {\n"
        "    on leave { print(\"bye\") }\n"
        "    return 1\n"
        "}\n"
        "print(f())\n", capsys)
    assert out == "bye\n1\n"


def test_on_leave_runs_in_reverse_order(capsys):
    out = run_all(
        "fn f() {\n"
        "    on leave { print(\"first\") }\n"
        "    on leave { print(\"second\") }\n"
        "    print(\"body\")\n"
        "}\n"
        "f()\n", capsys)
    assert out == "body\nsecond\nfirst\n"


def test_on_leave_runs_when_the_block_throws(capsys):
    out = run_all(
        "fn f() {\n"
        "    on leave { print(\"clean\") }\n"
        "    throw \"boom\"\n"
        "}\n"
        "try {\n"
        "    f()\n"
        "} catch e {\n"
        "    print(\"caught\")\n"
        "}\n", capsys)
    assert out == "clean\ncaught\n"


def test_on_leave_runs_when_a_loop_breaks(capsys):
    out = run_all(
        "for i in range(3) {\n"
        "    on leave { print(\"body\") }\n"
        "    if i == 1 { break }\n"
        "}\n", capsys)
    assert out == "body\nbody\n"


def test_on_leave_is_lowered_to_try_finally():
    # The surface form is not a new engine instruction: the parser lowers
    # it to the try/finally every engine already runs.
    from bun.lexer import Lexer
    from bun.parser import Parser
    from bun import ast
    program = Parser(Lexer(
        'fn f() {\n    on leave { print("x") }\n    print("y")\n}\n'
    ).tokenize()).parse()
    body = program.statements[0].body.statements
    assert len(body) == 1
    assert isinstance(body[0], ast.TryStmt)
    assert body[0].catch_block is None
    assert body[0].finally_body is not None


# ---------------------------------------------------------------------------
# Nested type arguments
# ---------------------------------------------------------------------------

def test_nested_type_argument_in_the_word_form(capsys):
    out = run_all(
        "fn probe(v: list of list of int) -> int {\n"
        "    return len(v)\n"
        "}\n"
        "print(probe([[1, 2], [3]]))\n", capsys)
    assert out == "2\n"


def test_nested_type_argument_in_the_bracket_form(capsys):
    out = run_all(
        "fn probe(v: list<list<int>>) -> int {\n"
        "    return len(v)\n"
        "}\n"
        "print(probe([[1, 2], [3]]))\n", capsys)
    assert out == "2\n"


def test_nested_type_argument_keeps_the_commas_of_a_dict(capsys):
    out = run_all(
        "fn probe(v: dict of string to list of int) -> int {\n"
        "    return len(v)\n"
        "}\n"
        "print(probe({\"a\": [1], \"b\": [2, 3]}))\n", capsys)
    assert out == "2\n"


def test_type_helpers_read_nested_arguments():
    assert types.type_args("list<list<int>>") == ["list<int>"]
    assert types.type_args("dict<string, list<int>>") == ["string", "list<int>"]
    assert types.type_args("list<dict<string, int>>") == ["dict<string, int>"]
    assert types.base_type("list<list<int>>") == "list"


# ---------------------------------------------------------------------------
# Function types
# ---------------------------------------------------------------------------

def test_a_function_type_parameter_is_callable(capsys):
    out = run_all(
        "fn apply(f: fn(int) -> int, x: int) -> int {\n"
        "    return f(x)\n"
        "}\n"
        "fn inc(n: int) -> int { return n + 1 }\n"
        "print(apply(inc, 4))\n", capsys)
    assert out == "5\n"


def test_a_function_type_rejects_the_wrong_argument_type():
    with pytest.raises(BunTypeError,
                       match="not assignable to parameter of type 'int'"):
        run_source(
            "fn apply(f: fn(int) -> int, x: int) -> int { return f(x) }\n"
            "fn inc(n: int) -> int { return n + 1 }\n"
            "print(apply(inc, \"four\"))\n",
            filename="<test>.bun", check=True, engine="vm")


def test_a_function_type_checks_its_inner_types():
    with pytest.raises(BunTypeError, match="unknown type 'Nope'"):
        run_source(
            "fn apply(f: fn(Nope) -> int, x: int) -> int { return f(x) }\n",
            filename="<test>.bun", check=True, engine="vm")


def test_function_signature_is_parsed_with_nested_types():
    params, result = types.function_signature(
        "fn(int, list<list<int>>) -> dict<string, int>")
    assert params == ["int", "list<list<int>>"]
    assert result == "dict<string, int>"
    assert types.base_type("fn(int) -> int") == "fn"


# ---------------------------------------------------------------------------
# Named loops
# ---------------------------------------------------------------------------

def test_break_leaves_an_outer_loop(capsys):
    out = run_all(
        "fn probe() -> int {\n"
        "    for i in range(3) as outer {\n"
        "        for j in range(3) {\n"
        "            break outer\n"
        "        }\n"
        "    }\n"
        "    return 7\n"
        "}\n"
        "print(probe())\n", capsys)
    assert out == "7\n"


def test_continue_restarts_an_outer_loop(capsys):
    out = run_all(
        "var seen = []\n"
        "for i in range(3) as outer {\n"
        "    for j in range(3) {\n"
        "        if j == 1 { continue outer }\n"
        "        seen.push(i * 10 + j)\n"
        "    }\n"
        "}\n"
        "print(seen)\n", capsys)
    assert out == "[0, 10, 20]\n"


def test_the_prefix_label_form_is_the_same_loop(capsys):
    out = run_all(
        "var count = 0\n"
        "outer: for i in range(3) {\n"
        "    for j in range(3) {\n"
        "        count = count + 1\n"
        "        break outer\n"
        "    }\n"
        "}\n"
        "print(count)\n", capsys)
    assert out == "1\n"


def test_an_unknown_loop_label_is_refused():
    with pytest.raises(BunTypeError, match="unknown loop label 'nope'"):
        run_source(
            "for i in range(3) as outer {\n"
            "    break nope\n"
            "}\n",
            filename="<test>.bun", check=True, engine="vm")


# ---------------------------------------------------------------------------
# The Bun-written front end
# ---------------------------------------------------------------------------

def test_the_bun_written_front_end_reads_the_same_program(tmp_path, capsys):
    path = tmp_path / "original.bun"
    path.write_text(
        "fn count(v: list of list of int) -> int {\n"
        "    return len(v)\n"
        "}\n"
        "fn apply(f: fn(int) -> int, x: int) -> int {\n"
        "    return f(x)\n"
        "}\n"
        "fn inc(n: int) -> int { return n + 1 }\n"
        "fn find() -> int {\n"
        "    for i in range(3) as outer {\n"
        "        for j in range(3) {\n"
        "            break outer\n"
        "        }\n"
        "    }\n"
        "    return 7\n"
        "}\n"
        "fn note() -> int {\n"
        "    on leave { print(\"leave\") }\n"
        "    return 1\n"
        "}\n"
        "print(count([[1, 2], [3]]))\n"
        "print(apply(inc, 4))\n"
        "print(find())\n"
        "print(note())\n", encoding="utf-8")
    expected = "2\n5\n7\nleave\n1\n"
    run_file(str(path), front_end="python")
    assert capsys.readouterr().out == expected
    run_file(str(path), front_end="bun")
    assert capsys.readouterr().out == expected


# ---------------------------------------------------------------------------
# The originality audit
# ---------------------------------------------------------------------------

def test_originality_lists_bun_forms_and_the_lexical_overlap():
    result = subprocess.run(
        [sys.executable, "-m", "bun", "originality", "--json"],
        cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    forms = {item["form"] for item in data["constructs"]}
    assert "on leave { ... }" in forms
    assert "list of int / dict of string to int" in forms
    assert "for ... as name" in forms
    assert data["bun_only"] == ["protocol"]
    assert data["caveat"].startswith("A keyword is a word")
