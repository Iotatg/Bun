"""The tests of the decorators.

A decorator is written in front of a function.  Each of them receives
the function and returns the value that the name of the function holds
afterwards.  The decorator that is written last is the one that is
called first.

The tests run every program on every engine, so that a difference
between the engines shows up as a failure of the test and not as a
surprise later.
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
        run_source(source, filename="<decorators>.bun", check=True,
                   engine=engine)
        outputs.append(capsys.readouterr().out)
    assert len(set(outputs)) == 1, outputs
    return outputs[0]


def run_error(source, capsys, engine="vm"):
    """Run a source that must fail, and return the message of the error."""
    with pytest.raises(BunError) as info:
        run_source(source, filename="<decorators>.bun", check=True,
                   engine=engine)
    return info.value.msg


def test_a_decorator_replaces_the_function(capsys):
    out = run_everywhere(
        "fn twice(f) {\n"
        "    return fn (a) {\n"
        "        return f(a) * 2\n"
        "    }\n"
        "}\n"
        "\n"
        "@twice\n"
        "fn one(a) {\n"
        "    return a + 1\n"
        "}\n"
        "\n"
        "print(one(1))\n", capsys)
    assert out == "4\n"


def test_the_closest_decorator_is_called_first(capsys):
    out = run_everywhere(
        "fn one(f) {\n"
        "    return fn (a) {\n"
        "        return f(a) + 1\n"
        "    }\n"
        "}\n"
        "\n"
        "fn two(f) {\n"
        "    return fn (a) {\n"
        "        return f(a) * 10\n"
        "    }\n"
        "}\n"
        "\n"
        "@one\n"
        "@two\n"
        "fn three(a) {\n"
        "    return a\n"
        "}\n"
        "\n"
        "print(three(1))\n", capsys)
    assert out == "11\n"


def test_the_order_of_the_decorators_is_the_other_way_around(capsys):
    out = run_everywhere(
        "fn one(f) {\n"
        "    return fn (a) {\n"
        "        return f(a) + 1\n"
        "    }\n"
        "}\n"
        "\n"
        "fn two(f) {\n"
        "    return fn (a) {\n"
        "        return f(a) * 10\n"
        "    }\n"
        "}\n"
        "\n"
        "@two\n"
        "@one\n"
        "fn three(a) {\n"
        "    return a\n"
        "}\n"
        "\n"
        "print(three(1))\n", capsys)
    assert out == "20\n"


def test_a_decorator_may_call_the_function_it_decorates(capsys):
    out = run_everywhere(
        "fn again(f) {\n"
        "    return fn (a) {\n"
        "        return f(f(a))\n"
        "    }\n"
        "}\n"
        "\n"
        "@again\n"
        "fn add_one(a) {\n"
        "    return a + 1\n"
        "}\n"
        "\n"
        "print(add_one(1))\n", capsys)
    assert out == "3\n"


def test_the_name_of_a_decorated_function_stays_immutable(capsys):
    message = run_error(
        "fn identity(f) {\n"
        "    return f\n"
        "}\n"
        "\n"
        "@identity\n"
        "fn one(a) {\n"
        "    return a\n"
        "}\n"
        "\n"
        "one = 5\n", capsys)
    assert "cannot assign value of type 'int' to variable 'one' of type 'fn'" \
        in message


def test_an_undefined_decorator_is_a_static_error(capsys):
    message = run_error(
        "@missing\n"
        "fn one(a) {\n"
        "    return a\n"
        "}\n", capsys)
    assert message == "undefined decorator 'missing'"


def test_a_decorator_that_is_not_a_function_is_a_static_error(capsys):
    message = run_error(
        "let x: int = 5\n"
        "@x\n"
        "fn one(a) {\n"
        "    return a\n"
        "}\n", capsys)
    assert message == "decorator 'x' is not a function"


def test_the_decorator_of_a_function_may_be_imported(capsys, tmp_path):
    (tmp_path / "lib.bun").write_text(
        "fn twice(f) {\n"
        "    return fn (a) {\n"
        "        return f(a) * 2\n"
        "    }\n"
        "}\n"
        "\n"
        "export @twice\n"
        "fn one(a) {\n"
        "    return a + 1\n"
        "}\n")
    source = ("import { one } from \"./lib.bun\"\n"
              "print(one(1))\n")
    path = str(tmp_path / "main.bun")
    with open(path, "w") as handle:
        handle.write(source)
    for engine in ENGINES:
        run_source(source, filename=path, check=True, engine=engine)
        assert capsys.readouterr().out == "4\n"


def test_a_decorated_function_may_be_exported(capsys, tmp_path):
    (tmp_path / "lib.bun").write_text(
        "fn twice(f) {\n"
        "    return fn (a) {\n"
        "        return f(a) * 2\n"
        "    }\n"
        "}\n"
        "\n"
        "@twice\n"
        "export fn one(a) {\n"
        "    return a + 1\n"
        "}\n")
    source = ("import { one } from \"./lib.bun\"\n"
              "print(one(1))\n")
    path = str(tmp_path / "main.bun")
    with open(path, "w") as handle:
        handle.write(source)
    for engine in ENGINES:
        run_source(source, filename=path, check=True, engine=engine)
        assert capsys.readouterr().out == "4\n"


@needs_compiler
def test_the_native_backend_gives_the_same_answer(capfd):
    source = ("fn tagged(f) {\n"
              "    return fn (a, b) {\n"
              "        return f(a, b) + 1\n"
              "    }\n"
              "}\n"
              "\n"
              "@tagged\n"
              "fn add(a, b) {\n"
              "    return a + b\n"
              "}\n"
              "\n"
              "print(add(1, 2))\n")
    run_source(source, filename="<decorators>.bun", check=True, engine="vm")
    expected = capfd.readouterr().out
    run_source(source, filename="<decorators>.bun", check=True, engine="c")
    assert capfd.readouterr().out == expected
    assert expected == "4\n"
