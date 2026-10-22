"""Tests for ``finally`` blocks and exception chaining."""

import pytest

from bun.cli import run_source
from bun.errors import BunError, BunRuntimeError, ParseError


def run_both(source, capsys):
    """Run the same source on both engines and assert identical output."""
    run_source(source, filename="<test>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<test>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    return vm_out


def test_finally_runs_after_catch(capsys):
    out = run_both(
        "var log = []\n"
        "try {\n"
        '    log.push("try")\n'
        '    throw "boom"\n'
        "} catch e {\n"
        '    log.push("catch")\n'
        "} finally {\n"
        '    log.push("finally")\n'
        "}\n"
        'print(log.join(","))\n', capsys)
    assert out == "try,catch,finally\n"


def test_finally_runs_on_normal_completion(capsys):
    out = run_both(
        "try {\n"
        '    print("body")\n'
        "} finally {\n"
        '    print("fin")\n'
        "}\n", capsys)
    assert out == "body\nfin\n"


def test_finally_without_catch(capsys):
    out = run_both(
        "try {\n"
        '    print("body")\n'
        "} finally {\n"
        '    print("fin")\n'
        "}\n", capsys)
    assert out == "body\nfin\n"


def test_finally_runs_when_error_propagates(capsys):
    out = run_both(
        "var seen = []\n"
        "try {\n"
        "    try {\n"
        '        seen.push("try")\n'
        '        throw "boom"\n'
        "    } finally {\n"
        '        seen.push("finally")\n'
        "    }\n"
        "} catch e {\n"
        '    seen.push("caught")\n'
        "}\n"
        'print(seen.join(","))\n', capsys)
    assert out == "try,finally,caught\n"


def test_finally_runs_on_return(capsys):
    out = run_both(
        "fn pick() {\n"
        "    try {\n"
        '        return "value"\n'
        "    } finally {\n"
        '        print("fin")\n'
        "    }\n"
        "}\n"
        'print(pick())\n', capsys)
    assert out == "fin\nvalue\n"


def test_finally_runs_on_break(capsys):
    out = run_both(
        "for x in [1, 2, 3] {\n"
        "    try {\n"
        "        if x == 2 { break }\n"
        '        print("body " + x)\n'
        "    } finally {\n"
        '        print("fin " + x)\n'
        "    }\n"
        "}\n", capsys)
    assert out == "body 1\nfin 1\nfin 2\n"


def test_finally_runs_on_continue(capsys):
    out = run_both(
        "var total = 0\n"
        "for x in [1, 2, 3] {\n"
        "    try {\n"
        "        if x == 2 { continue }\n"
        "        total = total + x\n"
        "    } finally {\n"
        '        print("fin " + x)\n'
        "    }\n"
        "}\n"
        "print(total)\n", capsys)
    assert out == "fin 1\nfin 2\nfin 3\n4\n"


def test_finally_runs_when_catch_rethrows(capsys):
    with pytest.raises(BunRuntimeError) as info:
        run_source(
            "var log = []\n"
            "try {\n"
            '    throw "first"\n'
            "} catch e {\n"
            '    log.push("catch")\n'
            '    throw "second"\n'
            "} finally {\n"
            '    log.push("finally")\n'
            "}\n", filename="<test>.bun", check=True, engine="vm")
    assert info.value.msg == "second"


def test_nested_finally_order(capsys):
    out = run_both(
        "var log = []\n"
        "try {\n"
        "    try {\n"
        '        throw "x"\n'
        "    } finally {\n"
        '        log.push("inner")\n'
        "    }\n"
        "} catch e {\n"
        '    log.push("catch")\n'
        "} finally {\n"
        '    log.push("outer")\n'
        "}\n"
        'print(log.join(","))\n', capsys)
    assert out == "inner,catch,outer\n"


def test_nested_finally_on_break(capsys):
    out = run_both(
        "var log = []\n"
        "for x in [1] {\n"
        "    try {\n"
        "        try {\n"
        "            break\n"
        "        } finally {\n"
        '            log.push("inner")\n'
        "        }\n"
        "    } finally {\n"
        '        log.push("outer")\n'
        "    }\n"
        "}\n"
        'print(log.join(","))\n', capsys)
    assert out == "inner,outer\n"


def test_finally_throws_replaces_error(capsys):
    with pytest.raises(BunRuntimeError) as info:
        run_source(
            "try {\n"
            '    throw "original"\n'
            "} finally {\n"
            '    throw "replacement"\n'
            "}\n", filename="<test>.bun", check=True, engine="vm")
    assert info.value.msg == "replacement"


def test_finally_throws_replaces_caught_error(capsys):
    with pytest.raises(BunRuntimeError) as info:
        run_source(
            "try {\n"
            '    throw "original"\n'
            "} catch e {\n"
            '    print("caught " + e)\n'
            "} finally {\n"
            '    throw "replacement"\n'
            "}\n", filename="<test>.bun", check=True, engine="vm")
    assert info.value.msg == "replacement"


def test_catch_still_runs_before_finally(capsys):
    out = run_both(
        "try {\n"
        '    throw "boom"\n'
        "} catch e {\n"
        '    print("caught " + e)\n'
        "} finally {\n"
        '    print("fin")\n'
        "}\n", capsys)
    assert out == "caught boom\nfin\n"


def test_try_without_catch_or_finally_is_a_parse_error():
    with pytest.raises(ParseError):
        run_source("try {\n    print(1)\n}\n", filename="<test>.bun",
                   check=True, engine="vm")


def test_throw_with_cause_keeps_message(capsys):
    out = run_both(
        "try {\n"
        '    throw "outer", "inner"\n'
        "} catch e {\n"
        '    print("caught " + e)\n'
        "}\n", capsys)
    assert out == "caught outer\n"


def test_throw_with_cause_records_cause():
    with pytest.raises(BunRuntimeError) as info:
        run_source(
            'throw "outer", "inner"\n', filename="<test>.bun", check=True,
            engine="vm")
    assert info.value.msg == "outer"
    assert info.value.cause == "inner"


def test_throw_with_cause_records_cause_in_tree_engine():
    with pytest.raises(BunRuntimeError) as info:
        run_source(
            'throw "outer", "inner"\n', filename="<test>.bun", check=True,
            engine="tree")
    assert info.value.msg == "outer"
    assert info.value.cause == "inner"


def test_error_renderer_shows_cause_chain(capsys):
    from bun.errors import format_error
    error = BunRuntimeError("outer", 1, 0, cause="inner")
    rendered = format_error(error, 'throw "outer", "inner"', "<test>.bun")
    assert "error: outer" in rendered
    assert "caused by: inner" in rendered


def test_finally_block_scope_is_isolated(capsys):
    out = run_both(
        "var value = 1\n"
        "try {\n"
        "    var value = 2\n"
        "} finally {\n"
        "    var value = 3\n"
        "}\n"
        "print(value)\n", capsys)
    assert out == "1\n"


def test_finally_can_read_outer_variables(capsys):
    out = run_both(
        "var counter = 0\n"
        "try {\n"
        "    counter = counter + 1\n"
        "} finally {\n"
        "    counter = counter + 10\n"
        "}\n"
        "print(counter)\n", capsys)
    assert out == "11\n"


def test_return_inside_finally_wins(capsys):
    out = run_both(
        "fn pick() {\n"
        "    try {\n"
        '        return "try"\n'
        "    } finally {\n"
        '        return "finally"\n'
        "    }\n"
        "}\n"
        'print(pick())\n', capsys)
    assert out == "finally\n"


def test_uncaught_error_in_finally_reports_position(capsys):
    with pytest.raises(BunError) as info:
        run_source(
            "try {\n"
            '    throw "a"\n'
            "} finally {\n"
            '    throw "b"\n'
            "}\n", filename="<test>.bun", check=True, engine="vm")
    assert info.value.line == 4
