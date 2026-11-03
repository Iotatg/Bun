import pytest

from bun.checker import Checker
from bun.errors import BunError, BunRuntimeError
from bun.parser import parse
from bun.cli import run_source


def check(source):
    Checker().check(parse(source))


def error(source):
    with pytest.raises(BunError) as info:
        check(source)
    return info.value


PARSE = (
    "fn parse(s: string) -> result {\n"
    "    if s == \"bad\" {\n"
    "        return Err(\"bad input\")\n"
    "    }\n"
    "    return Ok(len(s))\n"
    "}\n"
)

TWICE = (
    "fn twice(s: string) -> result {\n"
    "    let n = parse(s)?\n"
    "    return Ok(n * 2)\n"
    "}\n"
)


def test_result_is_a_type():
    check("fn f() -> result {\n    return Ok(1)\n}\n")


def test_ok_returns_a_result():
    check("let r: result = Ok(1)\n")


def test_err_returns_a_result():
    check("let r: result = Err(\"no\")\n")


def test_is_ok_returns_a_bool():
    check("let b: bool = is_ok(Ok(1))\n")


def test_is_err_returns_a_bool():
    check("let b: bool = is_err(Err(\"no\"))\n")


def test_the_question_outside_a_function_errors():
    error_message = error("let x = Ok(1)?\n")
    assert error_message.msg == (
        "the '?' operator is only allowed inside a function")


def test_the_question_in_a_function_that_does_not_return_a_result_errors():
    error_message = error(
        "fn f() -> int {\n    return Ok(1)?\n}\n")
    assert error_message.msg == (
        "the '?' operator needs a function that returns 'result'")


def test_the_question_on_a_value_that_is_not_a_result_errors():
    error_message = error(
        "fn f() -> result {\n    let n = 5?\n    return Ok(n)\n}\n")
    assert error_message.msg == "cannot use '?' on a value of type 'int'"


def test_the_question_on_a_value_of_an_unknown_type_is_left_to_the_runtime():
    check(
        "fn f() -> result {\n"
        "    let x: any = 5\n"
        "    let n = x?\n"
        "    return Ok(n)\n"
        "}\n")


def test_the_question_on_a_dict_is_left_to_the_runtime():
    check(
        "fn f() -> result {\n"
        "    let d = {\"ok\": 1}\n"
        "    let n = d?\n"
        "    return Ok(n)\n"
        "}\n")


def test_a_result_is_may_be_the_type_of_a_parameter():
    check(
        "fn show(r: result) {\n"
        "    print(is_ok(r))\n"
        "}\n")


def test_the_question_of_a_function_without_a_return_type_is_allowed():
    check(
        "fn f() {\n"
        "    let n = Ok(1)?\n"
        "    print(n)\n"
        "}\n")


def test_a_result_may_not_be_assigned_to_a_number():
    error_message = error("let n: int = Ok(1)\n")
    assert error_message.msg == (
        "cannot assign value of type 'result' to variable 'n' of type 'int'")


def test_ok_takes_one_argument():
    with pytest.raises(BunRuntimeError) as info:
        run_source("print(Ok())\n", filename="<result>.bun", check=False)
    assert "Ok() expects 1 argument" in str(info.value)


def test_err_takes_one_argument():
    with pytest.raises(BunRuntimeError) as info:
        run_source("print(Err())\n", filename="<result>.bun", check=False)
    assert "Err() expects 1 argument" in str(info.value)


def test_the_question_on_a_value_that_is_not_a_result_is_a_runtime_error():
    with pytest.raises(BunRuntimeError) as info:
        run_source(
            "fn f() -> result {\n"
            "    let x: any = 5\n"
            "    let n = x?\n"
            "    return Ok(n)\n"
            "}\n"
            "f()\n",
            filename="<result>.bun", check=False)
    assert "'?' expects a Result or an option value, got int" in str(
        info.value)


def test_the_question_on_a_dict_that_is_not_a_result_is_a_runtime_error():
    with pytest.raises(BunRuntimeError) as info:
        run_source(
            "fn f() -> result {\n"
            "    let d = {\"a\": 1}\n"
            "    let n = d?\n"
            "    return Ok(n)\n"
            "}\n"
            "f()\n",
            filename="<result>.bun", check=False)
    assert "'?' expects a Result or an option value" in str(info.value)


ENGINES = ["tree", "vm", "register"]


def run_program(source, engine):
    run_source(source, filename="<result>.bun", check=True, engine=engine)


@pytest.mark.parametrize("engine", ENGINES, ids=ENGINES)
def test_every_engine_unwraps_a_success(engine, capsys):
    run_program(
        PARSE + TWICE + "print(twice(\"bun\")[\"ok\"])\n", engine)
    assert capsys.readouterr().out == "6\n"


@pytest.mark.parametrize("engine", ENGINES, ids=ENGINES)
def test_every_engine_passes_a_failure_along(engine, capsys):
    run_program(
        PARSE + TWICE + "print(twice(\"bad\")[\"err\"])\n", engine)
    assert capsys.readouterr().out == "bad input\n"


@pytest.mark.parametrize("engine", ENGINES, ids=ENGINES)
def test_every_engine_tells_a_success_from_a_failure(engine, capsys):
    run_program(
        PARSE + TWICE
        + "print(is_ok(twice(\"bun\")))\n"
        + "print(is_err(twice(\"bad\")))\n", engine)
    assert capsys.readouterr().out == "true\ntrue\n"
