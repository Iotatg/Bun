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


POINT = (
    "struct Point {\n"
    "    var x: int\n"
    "    var y: int\n"
    "}\n"
)

LINE = (
    POINT +
    "struct Line {\n"
    "    var start: Point\n"
    "    var end: Point\n"
    "}\n"
)

ENGINES = ["tree", "vm", "register"]


def test_a_struct_pattern_passes():
    check(POINT + "let p = Point(1, 2)\n"
          "match p {\n    Point(x, y) => print(x)\n}\n")


def test_the_field_of_a_pattern_may_be_a_literal():
    check(POINT + "let p = Point(0, 2)\n"
          "match p {\n    Point(x: 0, y) => print(y)\n}\n")


def test_a_pattern_without_fields_passes():
    check(POINT + "let p = Point(1, 2)\n"
          "match p {\n    Point() => print(\"empty\")\n}\n")


def test_a_nested_pattern_passes():
    check(LINE + "let l = Line(Point(0, 0), Point(1, 1))\n"
          "match l {\n    Line(start: Point(x: 0, y: 0), end) => print(end)\n}\n")


def test_a_field_may_be_a_binding_pattern():
    check(POINT + "let p = Point(1, 2)\n"
          "match p {\n    Point(x: n, y) => print(n)\n}\n")


def test_unknown_field_errors():
    error_message = error(
        POINT + "let p = Point(1, 2)\n"
        "match p {\n    Point(z) => print(1)\n}\n")
    assert error_message.msg == (
        "unknown field 'z' on struct 'Point' in a pattern")


def test_unknown_struct_errors():
    error_message = error(
        "let p = 1\nmatch p {\n    Nope(a) => print(1)\n}\n")
    assert error_message.msg == "unknown struct 'Nope' in a pattern"


def test_an_enum_name_in_a_pattern_errors():
    error_message = error(
        "enum Color {\n    Red\n}\n"
        "match Color.Red {\n    Color(x) => print(1)\n}\n")
    assert error_message.msg == "unknown struct 'Color' in a pattern"


@pytest.mark.parametrize("engine", ENGINES, ids=ENGINES)
def test_every_engine_matches_the_field(engine, capsys):
    run_source(
        POINT +
        "let p = Point(0, 5)\n"
        "match p {\n    Point(x: 0, y) => print(y)\n}\n",
        filename="<pattern>.bun", engine=engine)
    assert capsys.readouterr().out == "5\n"


@pytest.mark.parametrize("engine", ENGINES, ids=ENGINES)
def test_every_engine_falls_to_the_next_case(engine, capsys):
    run_source(
        POINT +
        "let p = Point(2, 5)\n"
        "match p {\n    Point(x: 0, y) => print(y)\n    Point(x, y) => print(x * y)\n}\n",
        filename="<pattern>.bun", engine=engine)
    assert capsys.readouterr().out == "10\n"


def test_a_struct_of_another_type_does_not_answer():
    with pytest.raises(BunRuntimeError):
        run_source(
            POINT +
            "let d = {\"x\": 1, \"y\": 2}\n"
            "match d {\n    Point(x, y) => print(x)\n}\n",
            filename="<pattern>.bun", engine="tree")
