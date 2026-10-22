import pytest

from bun import ast
from bun.parser import parse, parse_expression
from bun.errors import ParseError


def test_let_statement():
    stmt = parse("let x = 1").statements[0]
    assert isinstance(stmt, ast.LetStmt)
    assert stmt.name == "x" and stmt.mutable is False
    assert isinstance(stmt.value, ast.Literal) and stmt.value.value == 1


def test_var_is_mutable():
    stmt = parse("var y = 2").statements[0]
    assert isinstance(stmt, ast.LetStmt) and stmt.mutable is True


def test_binary_precedence():
    expr = parse_expression("1 + 2 * 3")
    assert isinstance(expr, ast.Binary) and expr.op == "+"
    assert isinstance(expr.right, ast.Binary) and expr.right.op == "*"


def test_logical_precedence():
    expr = parse_expression("a or b and c")
    assert isinstance(expr, ast.Logical) and expr.op == "or"
    assert isinstance(expr.right, ast.Logical) and expr.right.op == "and"


def test_function_declaration():
    fn = parse("fn add(a, b) { return a + b }").statements[0]
    assert isinstance(fn, ast.FnDecl)
    assert [param.name for param in fn.params] == ["a", "b"]


def test_if_else():
    stmt = parse("if x { } else { }").statements[0]
    assert isinstance(stmt, ast.IfStmt)
    assert stmt.then_branch is not None and stmt.else_branch is not None


def test_assignment_statement():
    stmt = parse("x = 5").statements[0]
    assert isinstance(stmt, ast.AssignStmt)
    assert isinstance(stmt.target, ast.Identifier)


def test_index_assignment():
    stmt = parse("nums[0] = 5").statements[0]
    assert isinstance(stmt, ast.AssignStmt)
    assert isinstance(stmt.target, ast.Index)


def test_invalid_assignment_target():
    with pytest.raises(ParseError):
        parse("1 = 2")


def test_list_literal():
    expr = parse_expression("[1, 2, 3]")
    assert isinstance(expr, ast.ListLiteral) and len(expr.elements) == 3


def test_try_catch_statement():
    stmt = parse('try {\n    print(1)\n} catch e {\n    print(e)\n}').statements[0]
    assert isinstance(stmt, ast.TryStmt)
    assert stmt.catch_params == ["e"]
    assert isinstance(stmt.try_block, ast.Block)
    assert isinstance(stmt.catch_block, ast.Block)


def test_try_catch_without_param():
    stmt = parse("try {\n} catch {\n}").statements[0]
    assert isinstance(stmt, ast.TryStmt)
    assert stmt.catch_params == []


def test_try_catch_with_paren_param():
    stmt = parse("try {\n} catch (e) {\n}").statements[0]
    assert isinstance(stmt, ast.TryStmt)
    assert stmt.catch_params == ["e"]


def test_throw_statement():
    stmt = parse('throw "boom"').statements[0]
    assert isinstance(stmt, ast.ThrowStmt)
    assert isinstance(stmt.value, ast.Literal)
    assert stmt.value.value == "boom"


def test_try_requires_catch():
    with pytest.raises(ParseError):
        parse("try {\n    print(1)\n}")


def test_throw_requires_value():
    with pytest.raises(ParseError):
        parse("throw")
