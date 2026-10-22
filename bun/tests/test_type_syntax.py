import pytest

from bun.errors import ParseError
from bun.parser import parse, parse_expression


def test_let_type_annotation():
    program = parse("let x: int = 5")
    decl = program.statements[0]
    assert decl.name == "x"
    assert decl.type_ann == "int"
    assert decl.value.value == 5


def test_var_type_annotation():
    program = parse('var count: string = "a"')
    assert program.statements[0].type_ann == "string"


def test_unannotated_let_has_no_type_ann():
    program = parse("let x = 5")
    assert program.statements[0].type_ann is None


def test_fn_param_and_return_annotations():
    program = parse("fn add(a: int, b: float) -> int {\n    return a\n}")
    fn = program.statements[0]
    assert [param.name for param in fn.params] == ["a", "b"]
    assert [param.type_name for param in fn.params] == ["int", "float"]
    assert fn.return_type == "int"


def test_fn_partial_annotations():
    program = parse('fn f(a: int, b) -> string {\n    return "x"\n}')
    fn = program.statements[0]
    assert [param.type_name for param in fn.params] == ["int", None]
    assert fn.return_type == "string"


def test_fn_without_annotations():
    program = parse("fn f(a, b) {\n    return a\n}")
    fn = program.statements[0]
    assert [param.type_name for param in fn.params] == [None, None]
    assert fn.return_type is None


def test_anonymous_fn_annotations():
    fn = parse_expression("fn(a: int) -> int {\n    return a\n}")
    assert fn.name == ""
    assert [param.type_name for param in fn.params] == ["int"]
    assert fn.return_type == "int"


def test_any_identifier_accepted_as_type_name():
    program = parse("let x: banana = 5")
    assert program.statements[0].type_ann == "banana"


def test_fn_keyword_accepted_as_type_name():
    program = parse("fn apply(f: fn) -> fn {\n    return f\n}")
    fn = program.statements[0]
    assert [param.type_name for param in fn.params] == ["fn"]
    assert fn.return_type == "fn"


def test_missing_type_name_errors():
    with pytest.raises(ParseError):
        parse("let x: = 5")
