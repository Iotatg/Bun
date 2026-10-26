import pytest

from bun.checker import Checker
from bun.errors import BunError
from bun.parser import parse
from bun.cli import run_source


def check(source):
    Checker().check(parse(source))


def error(source):
    with pytest.raises(BunError) as info:
        check(source)
    return info.value


IDENTITY = "fn identity<T>(value: T) -> T {\n    return value\n}\n"
SUM = "fn sum<T: Num>(xs: list<T>) -> T {\n    return xs[0]\n}\n"


def test_a_type_parameter_is_a_type_in_scope():
    check(IDENTITY)


def test_the_type_of_a_call_is_the_return_type():
    check(IDENTITY + "let n: int = identity(1)\n")


def test_the_type_of_a_call_follows_the_argument():
    check(IDENTITY + "let s: string = identity(\"a\")\n")


def test_the_type_of_a_call_that_does_not_fit_errors():
    error_message = error(IDENTITY + "let s: string = identity(1)\n")
    assert error_message.msg == (
        "cannot assign value of type 'int' to variable 's' of type 'string'")


def test_a_type_parameter_outside_a_function_is_an_unknown_type():
    error_message = error("let x: T = 1\n")
    assert error_message.msg == "unknown type 'T'"


def test_a_type_parameter_with_a_bound_is_a_type_in_scope():
    check(SUM)


def test_a_bound_that_the_type_does_not_satisfy_errors():
    error_message = error(SUM + "let n: int = sum([\"a\"])\n")
    assert error_message.msg == (
        "type 'string' does not satisfy the bound 'Num' of type parameter 'T'")


def test_a_bound_that_the_type_satisfies_passes():
    check(SUM + "let n: int = sum([1, 2])\n")


def test_a_number_bound_takes_a_float():
    check(SUM + "let n: float = sum([1.5])\n")


def test_an_unknown_bound_errors():
    error_message = error(
        "fn f<T: Nope>(x: T) -> T {\n    return x\n}\n")
    assert error_message.msg == "unknown bound 'Nope'"


def test_a_duplicate_type_parameter_errors():
    error_message = error(
        "fn f<T, T>(x: T) -> T {\n    return x\n}\n")
    assert error_message.msg == "duplicate type parameter 'T'"


def test_the_type_of_a_list_is_the_type_of_its_elements():
    check(
        "fn first<T>(xs: list<T>) -> T {\n    return xs[0]\n}\n"
        + "let n: int = first([1, 2])\n")


def test_the_type_of_a_list_that_does_not_fit_errors():
    error_message = error(
        "fn first<T>(xs: list<T>) -> T {\n    return xs[0]\n}\n"
        + "let n: string = first([1, 2])\n")
    assert error_message.msg == (
        "cannot assign value of type 'int' to variable 'n' of type 'string'")


def test_the_type_of_the_loop_over_a_list_is_the_type_of_its_elements():
    check(
        "fn each<T>(xs: list<T>) -> int {\n"
        "    var n = 0\n"
        "    for x in xs {\n"
        "        let v: T = x\n"
        "    }\n"
        "    return n\n"
        "}\n")


def test_a_list_of_a_type_with_type_arguments_is_a_type():
    check("fn f(xs: list<int>) -> int {\n    return xs[0]\n}\n")


def test_an_unknown_type_argument_errors():
    error_message = error("fn f(xs: list<banana>) -> int {\n    return 0\n}\n")
    assert error_message.msg == "unknown type 'banana'"


def test_a_type_argument_may_be_a_type_parameter():
    check(
        "fn f<T>(xs: list<T>) -> int {\n    return 0\n}\n")


def test_the_argument_of_a_generic_call_is_checked():
    error_message = error(
        "fn f<T>(x: T) -> T {\n    return x\n}\n"
        + "let n: int = f(\"a\")\n")
    assert error_message.msg == (
        "cannot assign value of type 'string' to variable 'n' of type 'int'")


def test_a_type_argument_that_cannot_be_found_is_any():
    check(
        "fn f<T>(x: T) -> T {\n    return x\n}\n"
        + "let xs = [1, 2]\n"
        + "let n: int = f(xs[0])\n")


ENGINES = ["tree", "vm", "register"]


def run_program(source, engine):
    run_source(source, filename="<generics>.bun", check=True, engine=engine)


@pytest.mark.parametrize("engine", ENGINES, ids=ENGINES)
def test_every_engine_runs_a_generic_function(engine, capsys):
    run_program(
        IDENTITY
        + "print(identity(1))\n"
        + "print(identity(\"bun\"))\n", engine)
    assert capsys.readouterr().out == "1\nbun\n"


@pytest.mark.parametrize("engine", ENGINES, ids=ENGINES)
def test_every_engine_runs_a_generic_function_with_a_bound(engine, capsys):
    run_program(
        "fn total<T: Num>(xs: list<T>) -> T {\n"
        "    var sum = 0\n"
        "    for x in xs {\n"
        "        sum = sum + x\n"
        "    }\n"
        "    return sum\n"
        "}\n"
        + "print(total([1, 2, 3]))\n", engine)
    assert capsys.readouterr().out == "6\n"
