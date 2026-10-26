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


SHAPE = "protocol Shape {\n    fn area(self) -> float\n}\n"

CIRCLE = (
    "struct Circle {\n    var r: float\n}\n"
    "impl Circle {\n    fn area(self) -> float {\n"
    "        return 3.0 * self.r * self.r\n    }\n}\n"
)


def test_protocol_declaration_passes():
    check(SHAPE)


def test_a_type_with_the_method_satisfies_the_protocol():
    check(SHAPE + CIRCLE + "fn show(s: Shape) {\n    print(s.area())\n}\n"
          + "show(Circle(2.0))\n")


def test_a_type_without_the_method_does_not_satisfy_the_protocol():
    error_message = error(
        SHAPE
        + "struct Point {\n    var x: int\n}\n"
        + "fn show(s: Shape) {\n    print(s.area())\n}\n"
        + "show(Point(1))\n")
    assert error_message.msg == (
        "type 'Point' does not satisfy protocol 'Shape': missing method 'area'")


def test_the_missing_method_is_the_first_one_of_the_protocol():
    error_message = error(
        "protocol Shape {\n    fn area(self) -> float\n    fn name(self) -> string\n}\n"
        + "struct Point {\n    var x: int\n}\n"
        + "fn show(s: Shape) {\n    print(s.area())\n}\n"
        + "show(Point(1))\n")
    assert error_message.msg == (
        "type 'Point' does not satisfy protocol 'Shape': missing method 'area'")


def test_a_protocol_may_be_used_before_it_is_declared():
    check(
        "fn show(s: Shape) {\n    print(s.area())\n}\n"
        + SHAPE
        + CIRCLE
        + "show(Circle(2.0))\n")


def test_a_protocol_is_not_a_value():
    error_message = error(SHAPE + "let s = Shape\n")
    assert error_message.msg == "protocol 'Shape' is not a value"


def test_an_unknown_method_of_a_protocol_errors():
    error_message = error(
        SHAPE
        + "fn show(s: Shape) {\n    print(s.nope())\n}\n")
    assert error_message.msg == "unknown method 'nope' on Shape"


def test_the_arguments_of_a_protocol_method_are_checked():
    error_message = error(
        "protocol Shape {\n    fn scaled(self, factor: int) -> float\n}\n"
        + "fn show(s: Shape) {\n    print(s.scaled(\"two\"))\n}\n")
    assert error_message.msg == (
        "argument of type 'string' is not assignable to parameter of type "
        "'int' in call to 'scaled'")


def test_the_argument_count_of_a_protocol_method_is_checked():
    error_message = error(
        "protocol Shape {\n    fn scaled(self, factor: int) -> float\n}\n"
        + "fn show(s: Shape) {\n    print(s.scaled())\n}\n")
    assert error_message.msg == (
        "method 'scaled' expects 1 argument(s), got 0")


def test_the_return_type_of_a_protocol_is_checked():
    error_message = error(
        SHAPE
        + "fn show(s: Shape) -> float {\n    return \"two\"\n}\n")
    assert error_message.msg == (
        "cannot return value of type 'string' from function with return type "
        "'float'")


def test_a_duplicate_method_of_a_protocol_errors():
    error_message = error(
        "protocol Shape {\n    fn area(self) -> float\n    fn area(self) -> float\n}\n")
    assert error_message.msg == "duplicate method 'area' on protocol 'Shape'"


def test_an_unknown_type_of_a_protocol_method_errors():
    error_message = error(
        "protocol Shape {\n    fn area(self) -> banana\n}\n")
    assert error_message.msg == "unknown type 'banana'"


def test_the_type_of_a_protocol_method_is_used():
    check(
        SHAPE
        + CIRCLE
        + "fn show(s: Shape) -> float {\n    return s.area()\n}\n")


def test_any_satisfies_a_protocol():
    check(SHAPE + "fn show(s: Shape) {\n    print(s.area())\n}\n"
          + "let x: any = 1\nshow(x)\n")


def test_a_protocol_may_be_a_field_of_a_struct():
    check(
        "protocol Shape {\n    fn area(self) -> float\n}\n"
        + "struct Holder {\n    var shape: Shape\n}\n")


def test_a_protocol_may_be_the_type_of_a_variable():
    check(
        SHAPE
        + CIRCLE
        + "let s: Shape = Circle(2.0)\n")


ENGINES = ["tree", "vm", "register"]


def run_program(source, engine):
    run_source(source, filename="<protocol>.bun", check=True, engine=engine)


@pytest.mark.parametrize("engine", ENGINES, ids=ENGINES)
def test_every_engine_calls_the_methods_of_a_protocol(engine, capsys):
    run_program(
        SHAPE
        + "struct Circle {\n    var r: float\n}\n"
        + "impl Circle {\n    fn area(self) -> float {\n"
        + "        return 3.0 * self.r * self.r\n    }\n}\n"
        + "fn show(s: Shape) {\n    print(s.area())\n}\n"
        + "show(Circle(2.0))\n", engine)
    assert capsys.readouterr().out == "12.0\n"
