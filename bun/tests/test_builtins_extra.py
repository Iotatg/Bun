import pytest

from bun.errors import BunRuntimeError, BunTypeError
from bun.interpreter import Interpreter
from bun.lexer import Lexer
from bun.parser import parse, parse_expression
from bun.types import BUILTIN_SIGNATURES


def run(source, engine="vm"):
    if engine == "tree":
        interp = Interpreter()
        interp.run(parse(source))
        return interp
    from bun.compiler import Compiler
    from bun.vm import VM
    vm = VM()
    code = Compiler("<test>", source).compile_program(parse(source))
    vm.run(code)
    return vm


def eval_expr(source):
    interp = Interpreter()
    return interp.evaluate(parse_expression(source), interp.globals)


def test_hex_binary_octal_literals():
    assert eval_expr("0xff") == 255
    assert eval_expr("0XFF") == 255
    assert eval_expr("0b1010") == 10
    assert eval_expr("0o17") == 15
    assert eval_expr("0x0") == 0


def test_invalid_numeric_literal_is_lex_error():
    from bun.errors import LexError
    with pytest.raises(LexError):
        Lexer("0x").tokenize()
    with pytest.raises(LexError):
        Lexer("0b").tokenize()


def test_range_supports_step():
    assert eval_expr("range(0, 10, 3)") == [0, 3, 6, 9]
    assert eval_expr("range(10, 0, -2)") == [10, 8, 6, 4, 2]
    assert eval_expr("range(3)") == [0, 1, 2]


def test_range_rejects_zero_step():
    with pytest.raises(BunRuntimeError):
        eval_expr("range(0, 10, 0)")


def test_int_with_base():
    assert eval_expr('int("ff", 16)') == 255
    assert eval_expr('int("1010", 2)') == 10
    assert eval_expr('int("17", 8)') == 15
    assert eval_expr('int("42")') == 42


def test_int_rejects_invalid_base():
    with pytest.raises(BunRuntimeError):
        eval_expr('int("10", 1)')


def test_chr_and_ord():
    assert eval_expr("chr(65)") == "A"
    assert eval_expr("ord(\"A\")") == 65
    with pytest.raises(BunRuntimeError):
        eval_expr("ord(\"AB\")")


def test_string_builtins_are_available():
    assert eval_expr('starts_with("hello", "he")') is True
    assert eval_expr('ends_with("hello", "lo")') is True
    assert eval_expr('substring("hello", 1, 3)') == "el"
    assert eval_expr('substring("hello", 1)') == "ello"
    assert eval_expr('index_of("hello", "ll")') == 2
    assert eval_expr('index_of("hello", "z")') == -1
    assert eval_expr('split("a,b", ",")') == ["a", "b"]
    assert eval_expr('join(["a", "b"], "-")') == "a-b"
    assert eval_expr('replace("aXa", "X", "-")') == "a-a"
    assert eval_expr('trim("  a  ")') == "a"
    assert eval_expr('lower("AbC")') == "abc"
    assert eval_expr('upper("AbC")') == "ABC"


def test_dump_produces_canonical_json():
    assert eval_expr('dump({"b": 1, "a": [1, "x"]})') == '{"a": [1, "x"], "b": 1}'


def test_trailing_comma_in_list_literal():
    assert eval_expr("[1, 2, 3,]") == [1, 2, 3]
    assert eval_expr("[]") == []


def test_trailing_comma_in_dict_literal():
    assert eval_expr('({"a": 1,}).len()') == 1
    assert eval_expr('({"a": 1,}).get("a")') == 1


def test_trailing_comma_matches_across_engines():
    for engine in ("vm", "tree"):
        result = run("var xs = [1, 2,]\nprint(xs.len())", engine=engine)
        assert result is not None


def test_new_builtin_signatures_are_declared():
    for name in ("chr", "ord", "dump", "starts_with", "ends_with",
                 "substring", "index_of", "split", "join", "replace",
                 "trim", "lower", "upper", "random", "random_int", "input",
                 "exec"):
        assert name in BUILTIN_SIGNATURES


def test_random_returns_a_number_between_zero_and_one():
    value = eval_expr("random()")
    assert 0.0 <= value < 1.0


def test_random_int_stays_inside_the_bounds():
    for _ in range(20):
        value = eval_expr("random_int(3, 7)")
        assert 3 <= value <= 7


def test_random_int_rejects_a_reversed_range():
    with pytest.raises(BunRuntimeError):
        eval_expr("random_int(7, 3)")


def test_input_reads_a_line_from_the_standard_input(monkeypatch, capsys):
    import io
    import sys
    monkeypatch.setattr(sys, "stdin", io.StringIO("bun\n"))
    run('let name = input("name: ")\nprint("hello " + name)')
    assert capsys.readouterr().out == "name: hello bun\n"


def test_input_reaches_the_end_of_the_input(monkeypatch):
    import io
    import sys
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    with pytest.raises(BunRuntimeError):
        run("input()")
