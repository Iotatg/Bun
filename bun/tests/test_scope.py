"""Tests for structured concurrency: the `scope` statement."""

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


def test_scope_joins_its_children(capsys):
    out = run_both(
        "scope {\n"
        "    let a = spawn { return 21 * 2 }\n"
        "    print(task_join(a))\n"
        "}\n"
        "print(\"after\")\n", capsys)
    assert out == "42\nafter\n"


def test_scope_waits_for_children_it_never_joins(capsys):
    out = run_both(
        "var log = []\n"
        "scope {\n"
        "    let slow = spawn {\n"
        "        sleep(0.05)\n"
        "        log.push(\"child\")\n"
        "    }\n"
        "}\n"
        "log.push(\"parent\")\n"
        "print(log.join(\",\"))\n", capsys)
    assert out == "child,parent\n"


def test_a_failing_child_is_raised_in_the_parent(capsys):
    out = run_both(
        "try {\n"
        "    scope {\n"
        "        let bad = spawn { throw \"child failed\" }\n"
        "    }\n"
        "    print(\"no error\")\n"
        "} catch e {\n"
        "    print(\"caught \" + e)\n"
        "}\n", capsys)
    assert out == "caught child failed\n"


def test_the_body_error_wins_over_a_child_error(capsys):
    out = run_both(
        "try {\n"
        "    scope {\n"
        "        let bad = spawn {\n"
        "            sleep(0.05)\n"
        "            throw \"child failed\"\n"
        "        }\n"
        "        throw \"body failed\"\n"
        "    }\n"
        "} catch e {\n"
        "    print(\"caught \" + e)\n"
        "}\n", capsys)
    assert out == "caught body failed\n"


def test_scope_runs_its_body_in_its_own_block():
    with pytest.raises(BunTypeError) as error:
        run_source("scope {\n    let inside = 1\n}\nprint(inside)\n",
                   filename="<test>.bun", check=True, engine="vm")
    assert "undefined variable 'inside'" in str(error.value)


def test_spawn_accepts_a_block(capsys):
    out = run_both(
        "let t = spawn {\n"
        "    return 7\n"
        "}\n"
        "print(task_join(t))\n", capsys)
    assert out == "7\n"


def test_spawn_accepts_a_call_with_a_function(capsys):
    out = run_both(
        "let t = spawn(fn() {\n"
        "    return 7\n"
        "})\n"
        "print(task_join(t))\n", capsys)
    assert out == "7\n"


def test_scope_is_a_soft_keyword(capsys):
    out = run_both(
        "let scope = 3\n"
        "print(scope)\n", capsys)
    assert out == "3\n"


def test_nested_scopes(capsys):
    out = run_both(
        "scope {\n"
        "    let outer = spawn { return 1 }\n"
        "    scope {\n"
        "        let inner = spawn { return 2 }\n"
        "        print(task_join(inner))\n"
        "    }\n"
        "    print(task_join(outer))\n"
        "}\n", capsys)
    assert out == "2\n1\n"


def test_cancellation_is_cooperative(capsys):
    out = run_both(
        "scope {\n"
        "    let t = spawn {\n"
        "        var spins = 0\n"
        "        while !task_cancelled() {\n"
        "            sleep(0.01)\n"
        "            spins = spins + 1\n"
        "        }\n"
        "        return spins\n"
        "    }\n"
        "    sleep(0.05)\n"
        "    cancel(t)\n"
        "    print(task_join(t) > 0)\n"
        "}\n", capsys)
    assert out == "true\n"


def test_task_cancelled_reports_the_handle(capsys):
    out = run_both(
        "let t = spawn { return 1 }\n"
        "print(task_cancelled(t))\n"
        "cancel(t)\n"
        "print(task_cancelled(t))\n", capsys)
    assert out == "false\ntrue\n"


def test_task_cancelled_outside_a_task_is_false(capsys):
    out = run_both("print(task_cancelled())\n", capsys)
    assert out == "false\n"


def test_scope_body_is_type_checked():
    with pytest.raises(BunTypeError) as error:
        run_source("scope {\n    let x: int = \"s\"\n}\n",
                   filename="<test>.bun", check=True, engine="vm")
    assert "cannot assign value of type 'string'" in str(error.value)


def test_scope_outside_a_function_joins_at_the_end(capsys):
    out = run_both(
        "scope {\n"
        "    let t = spawn { return 1 }\n"
        "}\n"
        "print(\"done\")\n", capsys)
    assert out == "done\n"


def test_a_scope_inside_a_function_returns(capsys):
    out = run_both(
        "fn f() {\n"
        "    scope {\n"
        "        let t = spawn { return 5 }\n"
        "    }\n"
        "    return 6\n"
        "}\n"
        "print(f())\n", capsys)
    assert out == "6\n"


def test_return_inside_a_scope_returns_from_the_function(capsys):
    out = run_both(
        "fn f() {\n"
        "    scope {\n"
        "        return 5\n"
        "    }\n"
        "    return 6\n"
        "}\n"
        "print(f())\n", capsys)
    assert out == "5\n"
