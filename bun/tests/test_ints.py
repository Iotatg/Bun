"""The tests of the width of the integers.

The integers of Bun are 64 bits wide, in every engine.  A program that
leaves the range is an error and not a number that wraps around: the
native backend holds its integers in 64 bits, and a program that
behaves differently under one engine is a bug in the engine, never a
difference in the language.
"""

import shutil

import pytest

from bun.cli import run_source
from bun.errors import BunError

ENGINES = ("tree", "vm", "register")


def _has_compiler():
    return shutil.which("cc") is not None


needs_compiler = pytest.mark.skipif(not _has_compiler(),
                                    reason="no C compiler")


def run_everywhere(source, capsys, engines=ENGINES):
    """Run the same source on every engine and assert the same output."""
    outputs = []
    for engine in engines:
        run_source(source, filename="<ints>.bun", check=True, engine=engine)
        outputs.append(capsys.readouterr().out)
    assert len(set(outputs)) == 1, outputs
    return outputs[0]


def run_error(source, capsys, engine="vm"):
    """Run a source that must fail, and return the message of the error."""
    with pytest.raises(BunError) as info:
        run_source(source, filename="<ints>.bun", check=True, engine=engine)
    return info.value.msg


def test_the_sum_that_leaves_the_range_is_an_error(capsys):
    message = run_error("print(9223372036854775807 + 1)\n", capsys)
    assert message == "integer overflow"


def test_the_difference_that_leaves_the_range_is_an_error(capsys):
    message = run_error("print(-9223372036854775807 - 2)\n", capsys)
    assert message == "integer overflow"


def test_the_product_that_leaves_the_range_is_an_error(capsys):
    message = run_error("print(4294967296 * 4294967296)\n", capsys)
    assert message == "integer overflow"


def test_the_shift_that_leaves_the_range_is_an_error(capsys):
    message = run_error("print(1 << 64)\n", capsys)
    assert message == "integer overflow"


def test_the_negation_of_the_smallest_integer_is_an_error(capsys):
    message = run_error("let x = -9223372036854775807 - 1\nprint(-x)\n",
                        capsys)
    assert message == "integer overflow"


def test_a_literal_that_does_not_fit_is_an_error(capsys):
    message = run_error("let x = 99999999999999999999\n", capsys)
    assert message == "integer literal out of range"


def test_a_literal_in_hex_that_does_not_fit_is_an_error(capsys):
    message = run_error("let x = 0xFFFFFFFFFFFFFFFFF\n", capsys)
    assert message == "integer literal out of range"


def test_a_number_that_does_not_fit_is_an_error(capsys):
    message = run_error("print(int(\"99999999999999999999\"))\n", capsys)
    assert message == "integer out of range"


def test_the_largest_integer_is_still_an_integer(capsys):
    out = run_everywhere("print(9223372036854775807)\n", capsys)
    assert out == "9223372036854775807\n"


def test_the_smallest_integer_is_still_an_integer(capsys):
    out = run_everywhere("print(-9223372036854775807 - 1)\n", capsys)
    assert out == "-9223372036854775808\n"


def test_the_arithmetic_near_the_border_is_exact(capsys):
    out = run_everywhere(
        "print(9223372036854775807 - 9223372036854775806)\n"
        "print(3037000499 * 3037000499)\n", capsys)
    assert out == "1\n9223372030926249001\n"


def test_a_float_is_not_an_integer(capsys):
    out = run_everywhere("print(9223372036854775807.0 + 1.0)\n", capsys)
    assert out == "9.223372036854776e+18\n"


@needs_compiler
def test_the_native_backend_fails_the_same_way(capfd):
    from bun.cli import NativeExit
    from bun.errors import format_error
    source = "print(9223372036854775807 + 1)\n"
    capfd.readouterr()
    try:
        run_source(source, filename="<ints>.bun", check=True, engine="vm")
    except BunError as error:
        expected = format_error(error, source, "<ints>.bun") + "\n"
    else:
        expected = ""
    try:
        run_source(source, filename="<ints>.bun", check=True, engine="c")
    except NativeExit:
        pass
    assert capfd.readouterr().err == expected
    assert "integer overflow" in expected
