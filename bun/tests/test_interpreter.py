import pytest

from bun.interpreter import Interpreter
from bun.parser import parse, parse_expression
from bun.errors import BunRuntimeError


def run(source):
    interp = Interpreter()
    interp.run(parse(source))
    return interp


def eval_expr(source):
    interp = Interpreter()
    return interp.evaluate(parse_expression(source), interp.globals)


def test_arithmetic():
    assert eval_expr("1 + 2 * 3") == 7
    assert eval_expr("10 / 3") == 3
    assert eval_expr("10 % 3") == 1
    assert eval_expr("2.5 + 0.5") == 3.0


def test_string_concat():
    assert eval_expr('"a" + "b"') == "ab"


def test_comparison_and_logical():
    assert eval_expr("1 < 2") is True
    assert eval_expr("true and false") is False
    assert eval_expr("null or 5") == 5


def test_let_and_var():
    interp = run("let x = 1\nvar y = 2\ny = y + 1")
    assert interp.globals.get("y") == 3


def test_immutable_assignment_errors():
    with pytest.raises(BunRuntimeError):
        run("let x = 1\nx = 2")


def test_undefined_variable_errors():
    with pytest.raises(BunRuntimeError):
        run("print(unknown)")


def test_if_else():
    interp = run("var r = 0\nif 1 < 2 { r = 1 } else { r = 2 }")
    assert interp.globals.get("r") == 1


def test_while_loop():
    interp = run("var i = 0\nwhile i < 5 { i = i + 1 }")
    assert interp.globals.get("i") == 5


def test_for_range():
    interp = run("var total = 0\nfor i in range(1, 4) { total = total + i }")
    assert interp.globals.get("total") == 6


def test_function_and_return():
    interp = run("fn add(a, b) { return a + b }\nlet r = add(2, 3)")
    assert interp.globals.get("r") == 5


def test_recursion():
    source = "fn fact(n) { if n < 2 { return 1 } return n * fact(n - 1) }\nlet r = fact(5)"
    interp = run(source)
    assert interp.globals.get("r") == 120


def test_closure_counter():
    source = (
        "fn make() {\n"
        "  var c = 0\n"
        "  fn inc() { c = c + 1\n    return c }\n"
        "  return inc\n"
        "}\n"
        "let f = make()\n"
        "let a = f()\n"
        "let b = f()"
    )
    interp = run(source)
    assert interp.globals.get("a") == 1
    assert interp.globals.get("b") == 2


def test_list_index_assignment():
    interp = run("let xs = [1, 2, 3]\nxs[0] = 9\nlet first = xs[0]\nlet n = len(xs)")
    assert interp.globals.get("first") == 9
    assert interp.globals.get("n") == 3


def test_index_out_of_range():
    with pytest.raises(BunRuntimeError):
        run("let xs = [1]\nlet x = xs[5]")


def test_division_by_zero():
    with pytest.raises(BunRuntimeError):
        run("let x = 1 / 0")


def test_modulo_by_zero():
    with pytest.raises(BunRuntimeError):
        run("let x = 1 % 0")


def test_function_arity_mismatch():
    with pytest.raises(BunRuntimeError):
        run("fn f(a) { return a }\nlet x = f(1, 2)")


def test_list_concat():
    assert eval_expr("[1, 2] + [3]") == [1, 2, 3]


def test_unary_minus_and_not():
    assert eval_expr("-5") == -5
    assert eval_expr("!true") is False


def test_top_level_return_errors():
    with pytest.raises(BunRuntimeError):
        run("return 1")


UNBOUNDED_RECURSION = "fn boom(n) { return boom(n + 1) }\nboom(0)"


def test_unbounded_recursion_raises_bun_runtime_error():
    with pytest.raises(BunRuntimeError) as info:
        run(UNBOUNDED_RECURSION)
    assert "stack overflow" in str(info.value)
    assert "RecursionError" not in repr(info.value)


def test_unbounded_recursion_is_catchable(capsys):
    source = (
        "fn boom(n) { return boom(n + 1) }\n"
        "try {\n"
        "  boom(0)\n"
        "} catch error {\n"
        '  print("caught")\n'
        "}"
    )
    run(source)
    assert capsys.readouterr().out == "caught\n"


def test_deep_but_bounded_recursion_succeeds():
    source = (
        "fn count(n) { if n < 1 { return 0 } return 1 + count(n - 1) }\n"
        "let r = count(50)"
    )
    interp = run(source)
    assert interp.globals.get("r") == 50
