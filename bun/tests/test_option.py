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


LOOKUP = (
    "fn find(d: dict, key: string) -> option {\n"
    "    if d.has(key) {\n"
    "        return some(d[key])\n"
    "    }\n"
    "    return none()\n"
    "}\n"
)

TABLE = "let d = {\"a\": 7}\n"

ENGINES = ["tree", "vm", "register"]


def test_option_is_a_type():
    check("fn f() -> option {\n    return some(1)\n}\n")


def test_some_is_an_option():
    check(LOOKUP)


def test_none_is_an_option():
    check(LOOKUP + "let d = {}\nlet f = find(d, \"a\")\n")


def test_some_answers_is_some():
    check(LOOKUP + "let d = {\"a\": 1}\nprint(is_some(find(d, \"a\")))\n")


def test_none_answers_is_none():
    check(LOOKUP + "let d = {}\nprint(is_none(find(d, \"a\")))\n")


def test_question_marks_an_option_in_the_function():
    check(
        "fn find(d: dict, key: string) -> option {\n"
        "    return none()\n"
        "}\n"
        "fn take(d: dict) -> option {\n"
        "    let v = find(d, \"a\")?\n"
        "    return some(v)\n"
        "}\n"
    )


def test_question_mark_of_a_result_answers_a_result():
    check(
        "fn half(n: int) -> result {\n"
        "    if n % 2 != 0 {\n"
        "        return Err(\"odd\")\n"
        "    }\n"
        "    return Ok(n / 2)\n"
        "}\n"
        "fn taken(n: int) -> result {\n"
        "    let v = half(n)?\n"
        "    return Ok(v * 2)\n"
        "}\n"
    )


def test_question_mark_of_a_result_in_an_option_function_errors():
    error_message = error(
        "fn half(n: int) -> result {\n"
        "    return Ok(n)\n"
        "}\n"
        "fn taken(n: int) -> option {\n"
        "    let v = half(n)?\n"
        "    return some(v)\n"
        "}\n"
    )
    assert error_message.msg == (
        "the '?' operator needs a function that returns 'result'")


def test_question_off_a_value_errors():
    error_message = error("fn f(n: int) -> int {\n    return n?\n}\n")
    assert error_message.msg == "cannot use '?' on a value of type 'int'"


def test_none_with_an_argument_errors():
    with pytest.raises(BunError):
        check("fn f() -> option {\n    return none(1)\n}\n")


def test_a_for_loop_over_an_option_errors():
    error_message = error(
        LOOKUP + "let d = {}\nfor v in find(d, \"a\") {\n    print(v)\n}\n")
    assert error_message.msg == "'option' is not walked by a 'for'"


def test_a_for_loop_over_a_result_errors():
    error_message = error(
        "fn half(n: int) -> result {\n"
        "    return Ok(n)\n"
        "}\n"
        "for v in half(1) {\n    print(v)\n}\n")
    assert error_message.msg == "'result' is not walked by a 'for'"


def test_a_bare_some_answers_a_function_not_an_option():
    error_message = error(
        "fn f() -> option {\n    return some\n}\n")
    assert error_message.msg == (
        "cannot return value of type 'fn' from function with "
        "return type 'option'")


def test_a_result_is_not_an_option():
    error_message = error(
        "fn f() -> option {\n    return Err(1)\n}\n")
    assert error_message.msg == (
        "cannot return value of type 'result' from function with "
        "return type 'option'")


@pytest.mark.parametrize("engine", ENGINES, ids=ENGINES)
def test_every_engine_tells_a_some_from_a_none(engine, capsys):
    run_source(
        LOOKUP + TABLE +
        "print(is_some(find(d, \"a\")))\n"
        "print(is_none(find(d, \"b\")))\n",
        filename="<option>.bun", engine=engine)
    assert capsys.readouterr().out == "true\ntrue\n"


@pytest.mark.parametrize("engine", ENGINES, ids=ENGINES)
def test_every_engine_passes_a_none_along(engine, capsys):
    run_source(
        "fn find() -> option {\n"
        "    return none()\n"
        "}\n"
        "fn take() -> option {\n"
        "    let v = find()?\n"
        "    return some(v + 1)\n"
        "}\n"
        "print(take())\n",
        filename="<option>.bun", engine=engine)
    assert capsys.readouterr().out == "{none: null}\n"


@pytest.mark.parametrize("engine", ENGINES, ids=ENGINES)
def test_every_engine_answers_the_question_of_a_some(engine, capsys):
    run_source(
        "fn find() -> option {\n"
        "    return some(7)\n"
        "}\n"
        "fn take() -> option {\n"
        "    let v = find()?\n"
        "    return some(v * 2)\n"
        "}\n"
        "print(take())\n",
        filename="<option>.bun", engine=engine)
    assert capsys.readouterr().out == "{some: 14}\n"
