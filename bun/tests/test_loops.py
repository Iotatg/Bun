"""Tests for the loop over pairs, the loop over a dict and `assert`."""

import pytest

from bun.cli import run_source
from bun.errors import BunRuntimeError, BunTypeError


def run_both(source, capsys):
    """Run the same source on both engines and assert identical output."""
    run_source(source, filename="<loops>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<loops>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    return vm_out


def run_error(source, capsys):
    """Run a source that must fail, and return the error message."""
    with pytest.raises((BunRuntimeError, BunTypeError)) as info:
        run_source(source, filename="<loops>.bun", check=True, engine="vm")
    return info.value.msg


def test_the_loop_over_pairs(capsys):
    out = run_both("let pairs = [[1, \"a\"], [2, \"b\"]]\n"
                   "for k, v in pairs {\n"
                   "    print(str(k) + \"=\" + v)\n"
                   "}\n", capsys)
    assert out == "1=a\n2=b\n"


def test_the_loop_over_three_names(capsys):
    out = run_both("for a, b, c in [[1, 2, 3]] {\n"
                   "    print(str(a) + str(b) + str(c))\n"
                   "}\n", capsys)
    assert out == "123\n"


def test_the_loop_over_one_name_still_works(capsys):
    out = run_both("for x in [1, 2, 3] {\n"
                   "    print(x)\n"
                   "}\n", capsys)
    assert out == "1\n2\n3\n"


def test_the_loop_over_a_dict_walks_the_keys(capsys):
    out = run_both("let data = { \"x\": 1, \"y\": 2 }\n"
                   "for key in data {\n"
                   "    print(key + \"=\" + str(data[key]))\n"
                   "}\n", capsys)
    assert out == "x=1\ny=2\n"


def test_the_keys_of_a_dict_keep_their_order(capsys):
    out = run_both("let data = {}\n"
                   "data.set(\"b\", 1)\n"
                   "data.set(\"a\", 2)\n"
                   "for key in data {\n"
                   "    print(key)\n"
                   "}\n", capsys)
    assert out == "b\na\n"


def test_the_loop_over_a_string(capsys):
    out = run_both("for letter in \"abc\" {\n"
                   "    print(letter)\n"
                   "}\n", capsys)
    assert out == "a\nb\nc\n"


def test_a_pair_that_is_too_short_is_an_error(capsys):
    assert run_error("for a, b in [[1]] {\n"
                     "    print(a)\n"
                     "}\n", capsys) == \
        "not enough values to unpack (expected 2, got 1)"


def test_one_name_binds_the_element_as_it_is(capsys):
    out = run_both("for a in [[1, 2]] {\n"
                   "    print(a)\n"
                   "}\n", capsys)
    assert out == "[1, 2]\n"


def test_a_pair_that_is_not_a_list_is_an_error(capsys):
    assert run_error("for a, b in [1] {\n"
                     "    print(a)\n"
                     "}\n", capsys) == "cannot unpack number"


def test_a_number_is_not_iterable(capsys):
    assert run_error("for x in 5 {\n"
                     "    print(x)\n"
                     "}\n", capsys) == "value is not iterable"


def test_the_assert_that_holds(capsys):
    out = run_both("assert 1 + 1 == 2\n"
                   "assert true, \"never\"\n"
                   "print(\"ok\")\n", capsys)
    assert out == "ok\n"


def test_the_assert_that_fails(capsys):
    assert run_error("assert 1 == 2\n", capsys) == "assertion failed"


def test_the_assert_with_a_message(capsys):
    assert run_error("assert 1 == 2, \"the world is flat\"\n", capsys) == \
        "assertion failed: the world is flat"


def test_the_assert_can_be_caught(capsys):
    out = run_both("try {\n"
                   "    assert false, \"nope\"\n"
                   "} catch (err) {\n"
                   "    print(err)\n"
                   "}\n", capsys)
    assert out == "assertion failed: nope\n"


def test_the_assert_names_the_line(capsys):
    out = run_both("try {\n"
                   "    assert false\n"
                   "} catch (err) {\n"
                   "    print(err)\n"
                   "}\n", capsys)
    assert out == "assertion failed\n"


def test_the_loop_variable_of_a_pair_is_defined(capsys):
    out = run_both("for a, b in [[1, 2]] {\n"
                   "    print(a + b)\n"
                   "}\n", capsys)
    assert out == "3\n"


def test_the_loop_over_a_dict_inside_a_function(capsys):
    out = run_both("fn total(data: any) -> int {\n"
                   "    var sum = 0\n"
                   "    for key in data {\n"
                   "        sum = sum + data[key]\n"
                   "    }\n"
                   "    return sum\n"
                   "}\n"
                   "print(total({ \"a\": 1, \"b\": 2 }))\n", capsys)
    assert out == "3\n"


def test_the_break_still_works_in_a_pair_loop(capsys):
    out = run_both("for a, b in [[1, 2], [3, 4], [5, 6]] {\n"
                   "    if a == 3 {\n"
                   "        break\n"
                   "    }\n"
                   "    print(a)\n"
                   "}\n", capsys)
    assert out == "1\n"


def test_the_continue_still_works_in_a_pair_loop(capsys):
    out = run_both("for a, b in [[1, 2], [3, 4]] {\n"
                   "    if a == 1 {\n"
                   "        continue\n"
                   "    }\n"
                   "    print(a)\n"
                   "}\n", capsys)
    assert out == "3\n"

def test_the_else_of_a_loop_runs_when_the_loop_ends(capsys):
    out = run_both("for x in [1, 2, 3] {\n"
                   "    print(x)\n"
                   "} else {\n"
                   "    print(\"no break\")\n"
                   "}\n", capsys)
    assert out == "1\n2\n3\nno break\n"


def test_the_else_of_a_loop_is_skipped_after_a_break(capsys):
    out = run_both("for x in [1, 2, 3] {\n"
                   "    if x == 2 {\n"
                   "        break\n"
                   "    }\n"
                   "    print(x)\n"
                   "} else {\n"
                   "    print(\"no break\")\n"
                   "}\n", capsys)
    assert out == "1\n"


def test_the_else_of_a_while_loop(capsys):
    out = run_both("var i = 0\n"
                   "while i < 3 {\n"
                   "    i = i + 1\n"
                   "} else {\n"
                   "    print(\"done \" + str(i))\n"
                   "}\n", capsys)
    assert out == "done 3\n"


def test_the_else_of_a_while_loop_is_skipped_after_a_break(capsys):
    out = run_both("var i = 0\n"
                   "while i < 3 {\n"
                   "    i = i + 1\n"
                   "    if i == 2 {\n"
                   "        break\n"
                   "    }\n"
                   "} else {\n"
                   "    print(\"no break\")\n"
                   "}\n", capsys)
    assert out == ""


def test_the_else_of_a_loop_over_an_empty_list(capsys):
    out = run_both("for x in [] {\n"
                   "    print(x)\n"
                   "} else {\n"
                   "    print(\"empty\")\n"
                   "}\n", capsys)
    assert out == "empty\n"


def test_the_else_of_a_loop_does_not_see_the_loop_variable(capsys):
    # A loop has a scope of its own, so the name of the loop is gone
    # when the else runs.
    message = run_error("for x in [1, 2] {\n"
                         "    print(x)\n"
                         "} else {\n"
                         "    print(x)\n"
                         "}\n", capsys)
    assert "undefined variable 'x'" in message
