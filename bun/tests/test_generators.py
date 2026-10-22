"""The tests of the generators.

A generator gives its values one at a time. The program asks for the
next one, and the function wakes up where it left off.
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


def run_everywhere(source, capsys):
    """Run the same source on every engine and assert the same output."""
    outputs = []
    for engine in ENGINES:
        run_source(source, filename="<gen>.bun", check=True, engine=engine)
        outputs.append(capsys.readouterr().out)
    assert len(set(outputs)) == 1, outputs
    return outputs[0]


def run_error(source, capsys, engine="vm"):
    with pytest.raises(BunError) as info:
        run_source(source, filename="<gen>.bun", check=True, engine=engine)
    return info.value.msg


def test_a_generator_gives_its_values_one_at_a_time(capsys):
    out = run_everywhere(
        "fn counter() {\n"
        "    yield 1\n"
        "    yield 2\n"
        "}\n"
        "let g = counter()\n"
        "print(next(g))\n"
        "print(next(g))\n", capsys)
    assert out == "1\n2\n"


def test_a_generator_can_be_used_in_a_loop(capsys):
    out = run_everywhere(
        "fn counter() {\n"
        "    yield 1\n"
        "    yield 2\n"
        "    yield 3\n"
        "}\n"
        "for value in counter() {\n"
        "    print(value)\n"
        "}\n", capsys)
    assert out == "1\n2\n3\n"


def test_the_generator_runs_when_the_program_asks(capsys):
    out = run_everywhere(
        "fn steps() {\n"
        "    print(\"a\")\n"
        "    yield 1\n"
        "    print(\"b\")\n"
        "    yield 2\n"
        "}\n"
        "let g = steps()\n"
        "print(\"before\")\n"
        "print(next(g))\n"
        "print(\"between\")\n"
        "print(next(g))\n", capsys)
    assert out == "before\na\n1\nbetween\nb\n2\n"


def test_a_value_can_be_sent_into_a_generator(capsys):
    out = run_everywhere(
        "fn echo() {\n"
        "    var value = yield 0\n"
        "    yield value\n"
        "}\n"
        "let g = echo()\n"
        "print(next(g))\n"
        "print(send(g, 7))\n", capsys)
    assert out == "0\n7\n"


def test_the_value_of_a_yield_is_the_value_that_is_sent(capsys):
    out = run_everywhere(
        "fn echo() {\n"
        "    let answer = yield 1\n"
        "    yield answer\n"
        "}\n"
        "let g = echo()\n"
        "print(next(g))\n"
        "print(send(g, \"hi\"))\n", capsys)
    assert out == "1\nhi\n"


def test_a_generator_that_is_over_is_an_error(capsys):
    message = run_error(
        "fn once() {\n"
        "    yield 1\n"
        "}\n"
        "let g = once()\n"
        "print(next(g))\n"
        "print(next(g))\n", capsys)
    assert message == "the generator is over"


def test_next_takes_a_default_value(capsys):
    out = run_everywhere(
        "fn once() {\n"
        "    yield 1\n"
        "}\n"
        "let g = once()\n"
        "print(next(g))\n"
        "print(next(g, \"none\"))\n", capsys)
    assert out == "1\nnone\n"


def test_a_generator_that_is_over_is_an_error_in_a_loop(capsys):
    out = run_everywhere(
        "fn once() {\n"
        "    yield 1\n"
        "}\n"
        "for value in once() {\n"
        "    print(value)\n"
        "}\n"
        "print(\"done\")\n", capsys)
    assert out == "1\ndone\n"


def test_a_generator_may_return_a_value(capsys):
    out = run_everywhere(
        "fn gen() {\n"
        "    yield 1\n"
        "    return 9\n"
        "}\n"
        "let g = gen()\n"
        "print(next(g))\n"
        "print(next(g, \"end\"))\n", capsys)
    assert out == "1\nend\n"


def test_a_generator_that_is_not_one_is_an_error(capsys):
    message = run_error("print(next(5))\n", capsys)
    assert message == "next() expects a generator"


def test_a_yield_outside_of_a_function_is_a_static_error(capsys):
    message = run_error("yield 1\n", capsys)
    assert message == "'yield' outside of a function"


def test_the_body_of_a_generator_does_not_run_until_it_is_read(capsys):
    out = run_everywhere(
        "fn f() {\n"
        "    print(\"body\")\n"
        "    yield 1\n"
        "}\n"
        "let g = f()\n"
        "print(\"made\")\n"
        "print(next(g))\n", capsys)
    assert out == "made\nbody\n1\n"


def test_a_generator_takes_its_arguments(capsys):
    out = run_everywhere(
        "fn counter(start) {\n"
        "    yield start\n"
        "    yield start + 1\n"
        "}\n"
        "for value in counter(10) {\n"
        "    print(value)\n"
        "}\n", capsys)
    assert out == "10\n11\n"


@needs_compiler
def test_the_native_backend_refuses_the_statement(capsys):
    from bun.cbackend import CBackendError
    with pytest.raises(CBackendError) as info:
        run_source("fn g() {\n    yield 1\n}\ng()\n",
                   filename="<gen>.bun", check=True, engine="c")
    assert "the yield statement" in str(info.value)
