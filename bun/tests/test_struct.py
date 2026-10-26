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


POINT = "struct Point {\n    x: int,\n    y: int\n}\n"


def test_struct_declaration_passes():
    check(POINT)


def test_struct_fields_are_read():
    check(POINT + "let p = Point(1, 2)\nlet n: int = p.x\n")


def test_struct_type_is_kept_for_the_name():
    check(POINT + "let p = Point(1, 2)\nlet q: Point = p\n")


def test_unknown_field_errors():
    error_message = error(POINT + "let p = Point(1, 2)\nlet n = p.z\n")
    assert error_message.msg == "unknown field 'z' on Point"


def test_field_of_another_type_errors():
    error_message = error(POINT + "let n: int = 1\nlet v = n.x\n")
    assert error_message.msg == "type 'int' has no fields"


def test_duplicate_field_errors():
    error_message = error(
        "struct Point {\n    x: int,\n    x: int\n}\n")
    assert error_message.msg == "duplicate field 'x' on struct 'Point'"


def test_unknown_type_of_field_errors():
    error_message = error("struct Point {\n    x: banana\n}\n")
    assert error_message.msg == "unknown type 'banana'"


def test_constructor_argument_count_errors():
    error_message = error(POINT + "let p = Point(1)\n")
    assert error_message.msg == "struct 'Point' expects 2 argument(s), got 1"


def test_constructor_argument_type_errors():
    error_message = error(POINT + 'let p = Point(1, "two")\n')
    assert error_message.msg == (
        "argument of type 'string' is not assignable to field 'y' of type 'int'")


def test_constructor_uses_the_default_of_the_field():
    check("struct Point {\n    x: int,\n    y: int = 2\n}\nlet p = Point(1)\n")


def test_impl_of_unknown_type_errors():
    error_message = error(
        "impl Nope {\n    fn get(self) -> int {\n        return 1\n    }\n}\n")
    assert error_message.msg == "impl of unknown type 'Nope'"


def test_unknown_method_errors():
    error_message = error(
        POINT
        + "impl Point {\n    fn sum(self) -> int {\n        return 1\n    }\n}\n"
        + "let p = Point(1, 2)\nlet n = p.nope()\n")
    assert error_message.msg == "unknown method 'nope' on Point"


def test_method_call_checks_the_arguments():
    error_message = error(
        POINT
        + "impl Point {\n    fn scaled(self, factor: int) -> int {\n"
        + "        return self.x * factor\n    }\n}\n"
        + 'let p = Point(1, 2)\nlet n = p.scaled("two")\n')
    assert error_message.msg == (
        "argument of type 'string' is not assignable to parameter of type "
        "'int' in call to 'scaled'")


def test_method_call_checks_the_argument_count():
    error_message = error(
        POINT
        + "impl Point {\n    fn scaled(self, factor: int) -> int {\n"
        + "        return self.x * factor\n    }\n}\n"
        + "let p = Point(1, 2)\nlet n = p.scaled()\n")
    assert error_message.msg == "method 'scaled' expects 1 argument(s), got 0"


def test_mutating_method_on_immutable_name_errors():
    error_message = error(
        POINT
        + "impl Point {\n    fn bump(self) {\n        self.x = self.x + 1\n    }\n}\n"
        + "let p = Point(1, 2)\np.bump()\n")
    assert error_message.msg == (
        "cannot call mutating method 'bump' on immutable variable 'p'")


def test_mutating_method_on_mutable_name_passes():
    check(
        POINT
        + "impl Point {\n    fn bump(self) {\n        self.x = self.x + 1\n    }\n}\n"
        + "var p = Point(1, 2)\np.bump()\n")


def test_write_to_immutable_field_errors():
    error_message = error(
        "struct Point {\n    x: int,\n    y: int\n}\n"
        + "let p = Point(1, 2)\np.x = 3\n")
    assert error_message.msg == (
        "cannot assign to field of immutable variable 'p'")


def test_write_to_immutable_variable_errors():
    error_message = error(
        "struct Point {\n    x: int,\n    y: int\n}\n"
        + "var p = Point(1, 2)\nlet q = p\nq.x = 3\n")
    assert error_message.msg == (
        "cannot assign to field of immutable variable 'q'")


def test_the_method_return_type_is_used():
    check(
        POINT
        + "impl Point {\n    fn sum(self) -> int {\n        return self.x\n    }\n}\n"
        + "let p = Point(1, 2)\nlet n: int = p.sum()\n")


ENGINES = ["tree", "vm", "register"]


def run_program(source, engine):
    run_source(source, filename="<struct>.bun", check=True, engine=engine)


@pytest.mark.parametrize("engine", ENGINES, ids=ENGINES)
def test_every_engine_reads_the_fields(engine, capsys):
    run_program(POINT + "let p = Point(1, 2)\nprint(p.x)\nprint(p.y)\n",
                engine)
    assert capsys.readouterr().out == "1\n2\n"


@pytest.mark.parametrize("engine", ENGINES, ids=ENGINES)
def test_every_engine_calls_the_methods(engine, capsys):
    run_program(
        POINT
        + "impl Point {\n    fn sum(self) -> int {\n"
        + "        return self.x + self.y\n    }\n}\n"
        + "let p = Point(1, 2)\nprint(p.sum())\n", engine)
    assert capsys.readouterr().out == "3\n"


@pytest.mark.parametrize("engine", ENGINES, ids=ENGINES)
def test_every_engine_copies_the_value(engine, capsys):
    run_program(
        POINT + "var a = Point(1, 2)\nvar b = a\nb.x = 9\n"
        + "print(a.x)\nprint(b.x)\n", engine)
    assert capsys.readouterr().out == "1\n9\n"


@pytest.mark.parametrize("engine", ENGINES, ids=ENGINES)
def test_every_engine_shows_the_value(engine, capsys):
    run_program(POINT + "let p = Point(1, 2)\nprint(p)\n", engine)
    assert capsys.readouterr().out == "Point{x: 1, y: 2}\n"


@pytest.mark.parametrize("engine", ENGINES, ids=ENGINES)
def test_every_engine_reports_an_unknown_field(engine):
    with pytest.raises(BunRuntimeError) as info:
        run_source(
            POINT + "let p = Point(1, 2)\nlet v = p\nprint(v.nope)\n",
            filename="<struct>.bun", check=False, engine=engine)
    assert "unknown field 'nope' on Point" in str(info.value)
