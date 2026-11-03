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


SHAPE = (
    "enum Shape {\n"
    "    Dot\n"
    "    Circle(float)\n"
    "    Rect(float, float)\n"
    "}\n"
)

AREA = (
    "fn area(s: Shape) -> float {\n"
    "    match s {\n"
    "        Shape.Dot => return 0.0\n"
    "        Shape.Circle(r) => return 3.14 * r\n"
    "        Shape.Rect(w, h) => return w * h\n"
    "    }\n"
    "    return 0.0\n"
    "}\n"
)

ENGINES = ["tree", "vm", "register"]


def test_enum_declaration_passes():
    check(SHAPE)


def test_variant_without_fields_passes():
    check(SHAPE + "let s = Shape.Dot\n")


def test_variant_with_fields_passes():
    check(SHAPE + "let s = Shape.Circle(2.0)\n")


def test_match_on_variant_passes():
    check(SHAPE + AREA + "let a = area(Shape.Dot)\n")


def test_match_catches_every_variant():
    check(SHAPE + AREA + "let a = area(Shape.Circle(1.0))\n")


def test_enum_is_a_type():
    check(SHAPE + "fn f() -> Shape {\n    return Shape.Dot\n}\n")


def test_variant_is_a_value():
    check(SHAPE + "let s = Shape.Dot\n")


def test_match_binds_the_fields():
    check(
        SHAPE +
        "fn f(s: Shape) -> float {\n"
        "    match s {\n"
        "        Shape.Rect(w, h) => return w + h\n"
        "        Shape.Circle(r) => return r\n"
        "        Shape.Dot => return 0.0\n"
        "    }\n"
        "    return 0.0\n"
        "}\n"
    )


def test_duplicate_variant_errors():
    error_message = error(
        "enum Shape {\n    Dot\n    Dot\n}\n")
    assert error_message.msg == "duplicate variant 'Dot' on enum 'Shape'"


def test_unknown_variant_errors():
    error_message = error(SHAPE + "let s = Shape.Triangle\n")
    assert error_message.msg == "enum 'Shape' has no variant 'Triangle'"


def test_variant_of_unknown_enum_errors():
    error_message = error("let s = Shape.Dot\n")
    assert error_message.msg == "undefined variable 'Shape'"


def test_enum_name_as_value_errors():
    error_message = error(SHAPE + "let s = Shape\n")
    assert error_message.msg == "enum 'Shape' is not a value"


def test_wrong_arity_errors():
    error_message = error(SHAPE + "let s = Shape.Circle(1.0, 2.0)\n")
    assert error_message.msg == (
        "variant 'Shape.Circle' expects 1 argument(s), got 2")


def test_field_of_the_variant_must_be_a_type():
    error_message = error(
        "enum Shape {\n    Circle(banana)\n}\n")
    assert error_message.msg == "unknown type 'banana'"


@pytest.mark.parametrize("engine", ENGINES, ids=ENGINES)
def test_every_engine_answers_the_variant(engine, capsys):
    run_source(SHAPE + AREA + "print(area(Shape.Rect(2.0, 3.0)))\n",
               filename="<enum>.bun", engine=engine)
    assert capsys.readouterr().out == "6.0\n"


@pytest.mark.parametrize("engine", ENGINES, ids=ENGINES)
def test_every_engine_matches_the_variant(engine, capsys):
    run_source(
        SHAPE +
        "let s = Shape.Dot\n"
        "match s {\n"
        "    Shape.Dot => print(\"dot\")\n"
        "    Shape.Circle(r) => print(r)\n"
        "    Shape.Rect(w, h) => print(w)\n"
        "}\n",
        filename="<enum>.bun", engine=engine)
    assert capsys.readouterr().out == "dot\n"


@pytest.mark.parametrize("engine", ENGINES, ids=ENGINES)
def test_every_engine_walks_the_variants(engine, capsys):
    run_source(
        SHAPE + AREA +
        "for s in [Shape.Circle(1.0), Shape.Rect(2.0, 2.0)] {\n"
        "    print(area(s))\n"
        "}\n",
        filename="<enum>.bun", engine=engine)
    assert capsys.readouterr().out == "3.14\n4.0\n"


def test_the_enum_name_in_a_function_type_errors():
    error_message = error(
        SHAPE + "fn f() -> Shap {\n    return Shape.Dot\n}\n")
    assert error_message.msg == "unknown type 'Shap'"
