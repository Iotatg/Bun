import pytest

from bun.interpreter import Interpreter
from bun.parser import parse_expression
from bun.errors import BunRuntimeError


def run(program):
    interp = Interpreter()
    interp.run(program)
    return interp


def eval_expr(source):
    interp = Interpreter()
    return interp.evaluate(parse_expression(source), interp.globals)


def test_trim_lower_upper():
    assert eval_expr('"  aB  ".trim()') == "aB"
    assert eval_expr('"aB".lower()') == "ab"
    assert eval_expr('"ab".upper()') == "AB"


def test_split_join():
    assert eval_expr('"a,b,c".split(",")') == ["a", "b", "c"]
    assert eval_expr('["a", "b"].join("-")') == "a-b"


def test_contains_starts_ends():
    assert eval_expr('"hello".contains("ell")') is True
    assert eval_expr('"hello".starts_with("he")') is True
    assert eval_expr('"hello".ends_with("lo")') is True


def test_replace_repeat_slice():
    assert eval_expr('"aaa".replace("a", "b")') == "bbb"
    assert eval_expr('"ab".repeat(3)') == "ababab"
    assert eval_expr('"abcdef".slice(1, 4)') == "bcd"


def test_index_of_and_len():
    assert eval_expr('"abcabc".index_of("b")') == 1
    assert eval_expr('"abc".len()') == 3


def test_index_of_absent_returns_minus_one():
    assert eval_expr('"abc".index_of("z")') == -1


def test_list_slice_and_value_errors():
    assert eval_expr("[1, 2, 3].slice(0, 2)") == [1, 2]
    assert eval_expr('"abc".slice(1, 99)') == "bc"
    with pytest.raises(BunRuntimeError):
        eval_expr("[].pop()")
    with pytest.raises(BunRuntimeError):
        eval_expr('"ab".repeat(-1)')


def test_chaining():
    assert eval_expr('"  A,B  ".trim().lower().split(",")') == ["a", "b"]


def test_list_push_mutates():
    from bun.parser import parse
    interp = run(parse("let xs = [1]\nxs.push(2)\nlet n = xs.len()"))
    assert interp.globals.get("n") == 2
    assert interp.globals.get("xs") == [1, 2]


def test_list_pop_reverse_contains():
    assert eval_expr("[1, 2].pop()") == 2
    assert eval_expr("[1, 2].reverse()") == [2, 1]
    assert eval_expr("[1, 2].contains(2)") is True


def test_list_shift_takes_the_first_item():
    from bun.parser import parse
    interp = run(parse("let xs = [1, 2, 3]\nlet first = xs.shift()\nlet n = xs.len()"))
    assert interp.globals.get("first") == 1
    assert interp.globals.get("n") == 2
    assert interp.globals.get("xs") == [2, 3]


def test_list_shift_on_an_empty_list_errors():
    with pytest.raises(BunRuntimeError, match="shift"):
        eval_expr("[].shift()")


def test_unknown_method_errors():
    with pytest.raises(BunRuntimeError, match="string"):
        eval_expr('"x".frobnicate()')
    with pytest.raises(BunRuntimeError, match="int"):
        eval_expr("5.frobnicate()")


def test_method_on_int_errors():
    with pytest.raises(BunRuntimeError, match="int"):
        eval_expr("5.trim()")


def test_arity_errors():
    with pytest.raises(BunRuntimeError):
        eval_expr('"x".split()')


def test_arg_type_errors():
    with pytest.raises(BunRuntimeError):
        eval_expr('"x".split(5)')


def test_join_renders_values_with_stringify():
    assert eval_expr('["a", "b"].join("-")') == "a-b"
    assert eval_expr('[null, true].join(",")') == "null,true"
    from bun.parser import parse
    interp = Interpreter()
    interp.run(parse('let d = {"a": 1}'))
    assert interp.evaluate(
        parse_expression('[d].join(",")'), interp.globals) == "{a: 1}"


def test_repeat_count_too_large():
    with pytest.raises(BunRuntimeError):
        eval_expr('"ab".repeat(100001)')
    assert eval_expr('"ab".repeat(2)') == "abab"


def test_sort_numbers_in_place():
    from bun.parser import parse
    interp = run(parse("var xs = [3, 1, 2]\nxs.sort()"))
    assert interp.globals.get("xs") == [1, 2, 3]


def test_sort_strings():
    from bun.parser import parse
    interp = run(parse('var xs = ["b", "a", "c"]\nxs.sort()'))
    assert interp.globals.get("xs") == ["a", "b", "c"]


def test_sort_returns_null():
    assert eval_expr("[3, 1, 2].sort()") is None


def test_sort_empty_list():
    from bun.parser import parse
    interp = run(parse("var xs = []\nxs.sort()"))
    assert interp.globals.get("xs") == []


def test_sort_mixed_types_errors():
    from bun.parser import parse
    with pytest.raises(BunRuntimeError):
        run(parse('var xs = [1, "a"]\nxs.sort()'))


def test_sort_rejects_bool_elements():
    from bun.parser import parse
    with pytest.raises(BunRuntimeError):
        run(parse("var xs = [true, 1]\nxs.sort()"))


def test_sort_arity_error():
    with pytest.raises(BunRuntimeError):
        eval_expr("[1, 2].sort(1)")


def test_splice_removes_and_returns_items():
    from bun.parser import parse
    interp = run(parse("var xs = [1, 2, 3, 4, 5]\nvar out = xs.splice(1, 2)"))
    assert interp.globals.get("out") == [2, 3]
    assert interp.globals.get("xs") == [1, 4, 5]


def test_splice_with_zero_count_removes_nothing():
    from bun.parser import parse
    interp = run(parse("var xs = [1, 2, 3]\nvar out = xs.splice(0, 0)"))
    assert interp.globals.get("out") == []
    assert interp.globals.get("xs") == [1, 2, 3]


def test_splice_clamps_out_of_range_start():
    from bun.parser import parse
    interp = run(parse("var xs = [1, 2, 3]\nvar out = xs.splice(10, 2)"))
    assert interp.globals.get("out") == []
    assert interp.globals.get("xs") == [1, 2, 3]


def test_splice_requires_two_integer_arguments():
    with pytest.raises(BunRuntimeError):
        eval_expr("[1, 2].splice(0)")


def test_insert_places_item_at_index():
    from bun.parser import parse
    interp = run(parse("var xs = [1, 3]\nxs.insert(1, 2)"))
    assert interp.globals.get("xs") == [1, 2, 3]


def test_insert_appends_when_index_past_end():
    from bun.parser import parse
    interp = run(parse("var xs = [1]\nxs.insert(99, 2)"))
    assert interp.globals.get("xs") == [1, 2]


def test_insert_requires_two_arguments():
    with pytest.raises(BunRuntimeError):
        eval_expr("[1, 2].insert(0)")
