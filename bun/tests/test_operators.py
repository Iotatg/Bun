"""Tests for the bit operators: &, |, ^, ~, << and >>."""

import pytest

from bun.cli import run_source
from bun.errors import BunRuntimeError, BunTypeError


def run_both(source, capsys):
    """Run the same source on both engines and assert identical output."""
    run_source(source, filename="<bits>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<bits>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    return vm_out


def run_error(source, capsys):
    """Run a source that must fail, and return the error message."""
    with pytest.raises((BunRuntimeError, BunTypeError)) as info:
        run_source(source, filename="<bits>.bun", check=True, engine="vm")
    return info.value.msg


def test_the_and_or_and_xor(capsys):
    out = run_both("print(5 & 3)\n"
                   "print(5 | 3)\n"
                   "print(5 ^ 3)\n"
                   "print(0 & 7)\n"
                   "print(0 | 0)\n"
                   "print(7 ^ 7)\n", capsys)
    assert out == "1\n7\n6\n0\n0\n0\n"


def test_the_masks_of_the_binary_literals(capsys):
    out = run_both("let flags = 0b1010\n"
                   "print(flags & 0b0110)\n"
                   "print(flags | 0b0001)\n"
                   "print(flags ^ 0b1111)\n", capsys)
    assert out == "2\n11\n5\n"


def test_the_shifts(capsys):
    out = run_both("print(1 << 10)\n"
                   "print(1024 >> 3)\n"
                   "print(0 << 5)\n"
                   "print(255 >> 8)\n", capsys)
    assert out == "1024\n128\n0\n0\n"


def test_the_shift_of_a_negative_number_moves_the_sign(capsys):
    out = run_both("print(-8 >> 1)\n"
                   "print(-1 >> 4)\n", capsys)
    assert out == "-4\n-1\n"


def test_the_not(capsys):
    out = run_both("print(~5)\n"
                   "print(~0)\n"
                   "print(~-1)\n", capsys)
    assert out == "-6\n-1\n0\n"


def test_the_precedence_of_the_operators(capsys):
    out = run_both("print(1 + 2 * 3)\n"
                   "print(1 << 2 + 1)\n"
                   "print(6 & 3 == 2)\n"
                   "print(1 | 2 & 0)\n"
                   "print(1 ^ 3 | 2)\n", capsys)
    assert out == "7\n8\ntrue\n1\n2\n"


def test_the_operators_work_on_the_hex_and_the_octal_literals(capsys):
    out = run_both("print(0x1f & 0x0f)\n"
                   "print(0o17 | 0o1)\n", capsys)
    assert out == "15\n15\n"


def test_the_operators_of_the_big_numbers(capsys):
    out = run_both("print(4294967295 & 255)\n"
                   "print(4294967295 >> 24)\n", capsys)
    assert out == "255\n255\n"


def test_a_float_is_not_an_integer(capsys):
    assert run_error("print(1.5 & 2)\n", capsys) == \
        "unsupported operands for '&'"


def test_a_string_is_not_an_integer(capsys):
    assert run_error("print(\"a\" | 2)\n", capsys) == \
        "unsupported operands for '|'"


def test_the_not_of_a_float_is_an_error(capsys):
    assert run_error("print(~1.5)\n", capsys) == \
        "unary '~' expects an integer"


def test_a_negative_shift_is_an_error(capsys):
    assert run_error("print(1 << -1)\n", capsys) == "negative shift count"


def test_the_operators_are_the_same_on_the_two_engines(capsys):
    source = "var mask = 0\n" \
             "for i in range(0, 16) {\n" \
             "    mask = mask | (1 << i)\n" \
             "}\n" \
             "print(mask)\n" \
             "print(mask & 0xAAAA)\n" \
             "print(mask ^ mask)\n" \
             "print(mask >> 4)\n"
    out = run_both(source, capsys)
    assert out == "65535\n43690\n0\n4095\n"


def test_the_word_not(capsys):
    out = run_both("print(not true)\n"
                   "print(not false)\n"
                   "print(not 0)\n"
                   "print(not \"x\")\n"
                   "print(not null)\n", capsys)
    assert out == "false\ntrue\ntrue\nfalse\ntrue\n"


def test_the_word_not_binds_looser_than_a_comparison(capsys):
    out = run_both("print(not 1 == 2)\n"
                   "print(not 1 != 2)\n"
                   "print(not 1 < 2)\n", capsys)
    assert out == "true\nfalse\nfalse\n"


def test_the_word_not_binds_tighter_than_and(capsys):
    out = run_both("print(not false and true)\n"
                   "print(true or not false)\n"
                   "print(false or not false and true)\n", capsys)
    assert out == "true\ntrue\ntrue\n"


def test_the_word_not_can_be_chained(capsys):
    out = run_both("print(not not true)\n"
                   "print(not not not false)\n", capsys)
    assert out == "true\ntrue\n"


def test_the_word_not_and_the_mark_say_the_same_thing(capsys):
    out = run_both("let value = 0\n"
                   "print(not value)\n"
                   "print(!value)\n"
                   "print(not value == !value)\n", capsys)
    assert out == "true\ntrue\ntrue\n"
