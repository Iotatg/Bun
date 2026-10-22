"""Tests for the ``with`` statement and its context manager protocol."""

import pytest

from bun.cli import run_source
from bun.errors import BunRuntimeError, ParseError


CTX = (
    "var log = []\n"
    "fn ctx(label, suppress) {\n"
    "    return {\n"
    '        "__enter__": fn() {\n'
    '            log.push("enter " + label)\n'
    "            return label\n"
    "        },\n"
    '        "__exit__": fn(err) {\n'
    "            if err == null {\n"
    '                log.push("exit " + label)\n'
    "            } else {\n"
    '                log.push("exit " + label + " err=" + err)\n'
    "            }\n"
    "            return suppress\n"
    "        }\n"
    "    }\n"
    "}\n"
)


def run_both(source, capsys):
    """Run the same source on both engines and assert identical output."""
    run_source(source, filename="<test>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<test>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    return vm_out


def test_with_binds_enter_result(capsys):
    out = run_both(
        CTX +
        'with ctx("a", false) as c {\n'
        '    print("body " + c)\n'
        "}\n", capsys)
    assert out == "body a\n"


def test_with_calls_enter_and_exit(capsys):
    out = run_both(
        CTX +
        'with ctx("a", false) as c {\n'
        '    log.push("body")\n'
        "}\n"
        'print(log.join(","))\n', capsys)
    assert out == "enter a,body,exit a\n"


def test_with_exit_receives_null_on_success(capsys):
    out = run_both(
        CTX +
        'with ctx("a", false) as c {\n'
        "}\n"
        'print(log.join(","))\n', capsys)
    assert out == "enter a,exit a\n"


def test_with_exit_receives_the_error(capsys):
    out = run_both(
        CTX +
        "try {\n"
        '    with ctx("a", false) as c {\n'
        '        throw "boom"\n'
        "    }\n"
        "} catch e {\n"
        '    print("caught " + e)\n'
        "}\n"
        'print(log.join(","))\n', capsys)
    assert out == "caught boom\nenter a,exit a err=boom\n"


def test_with_exit_can_suppress_the_error(capsys):
    out = run_both(
        CTX +
        "try {\n"
        '    with ctx("a", true) as c {\n'
        '        throw "boom"\n'
        "    }\n"
        '    print("after")\n'
        "} catch e {\n"
        '    print("caught " + e)\n'
        "}\n", capsys)
    assert out == "after\n"


def test_with_exit_runs_on_return(capsys):
    out = run_both(
        CTX +
        "fn run() {\n"
        '    with ctx("a", false) as c {\n'
        '        return "value"\n'
        "    }\n"
        "}\n"
        'print(run())\n'
        'print(log.join(","))\n', capsys)
    assert out == "value\nenter a,exit a\n"


def test_with_exit_runs_on_break(capsys):
    out = run_both(
        CTX +
        "for x in [1, 2, 3] {\n"
        '    with ctx("a", false) as c {\n'
        "        if x == 2 { break }\n"
        '        log.push("body " + x)\n'
        "    }\n"
        "}\n"
        'print(log.join(","))\n', capsys)
    assert out == "enter a,body 1,exit a,enter a,exit a\n"


def test_with_exit_runs_on_continue(capsys):
    out = run_both(
        CTX +
        "for x in [1, 2, 3] {\n"
        '    with ctx("a", false) as c {\n'
        "        if x == 2 { continue }\n"
        '        log.push("body " + x)\n'
        "    }\n"
        "}\n"
        'print(log.join(","))\n', capsys)
    assert out == "enter a,body 1,exit a,enter a,exit a,enter a,body 3,exit a\n"


def test_nested_with_exits_in_reverse_order(capsys):
    out = run_both(
        CTX +
        'with ctx("outer", false) as a {\n'
        '    with ctx("inner", false) as b {\n'
        '        log.push("body")\n'
        "    }\n"
        "}\n"
        'print(log.join(","))\n', capsys)
    assert out == "enter outer,enter inner,body,exit inner,exit outer\n"


def test_with_supports_multiple_items(capsys):
    out = run_both(
        CTX +
        'with ctx("a", false) as x, ctx("b", false) as y {\n'
        '    log.push("body " + x + y)\n'
        "}\n"
        'print(log.join(","))\n', capsys)
    assert out == "enter a,enter b,body ab,exit b,exit a\n"


def test_with_target_without_enter_is_an_error():
    with pytest.raises(BunRuntimeError) as info:
        run_source('with 42 as x {\n    print(x)\n}\n',
                   filename="<test>.bun", check=True, engine="vm")
    assert "__enter__" in info.value.msg


def test_with_target_without_exit_is_an_error():
    with pytest.raises(BunRuntimeError) as info:
        run_source(
            'with {"__enter__": fn() { return 1 }} as x {\n'
            "    print(x)\n"
            "}\n", filename="<test>.bun", check=True, engine="vm")
    assert "__exit__" in info.value.msg


def test_with_target_with_non_callable_enter_is_an_error():
    with pytest.raises(BunRuntimeError) as info:
        run_source(
            'with {"__enter__": 5, "__exit__": fn(e) { return false }} as x {\n'
            "    print(x)\n"
            "}\n", filename="<test>.bun", check=True, engine="vm")
    assert "not callable" in info.value.msg


def test_with_requires_as_keyword():
    with pytest.raises(ParseError):
        run_source('with 42 x {\n    print(x)\n}\n', filename="<test>.bun",
                   check=True, engine="vm")


def test_with_body_scope_is_isolated(capsys):
    out = run_both(
        CTX +
        "var value = 1\n"
        'with ctx("a", false) as c {\n'
        "    var value = 2\n"
        "}\n"
        "print(value)\n", capsys)
    assert out == "1\n"


def test_with_name_is_visible_in_the_body(capsys):
    out = run_both(
        CTX +
        'with ctx("a", false) as c {\n'
        '    print(c)\n'
        "}\n", capsys)
    assert out == "a\n"
