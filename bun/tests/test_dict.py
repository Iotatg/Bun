import pytest

from bun.dict import BunDict
from bun.interpreter import Interpreter
from bun.parser import parse, parse_expression
from bun.values import stringify, values_equal
from bun.errors import BunRuntimeError


def run(source):
    interp = Interpreter()
    interp.run(parse(source))
    return interp


def test_empty_and_literal():
    interp = run('let d = {}\nlet e = {"a": 1, "b": 2}')
    assert isinstance(interp.globals.get("d"), BunDict)
    assert interp.globals.get("e").get("a") == 1


def test_index_get_and_set():
    interp = run('let d = {}\nd["x"] = 10\nlet v = d["x"]')
    assert interp.globals.get("v") == 10


def test_overwrite_key():
    interp = run('let d = {"a": 1}\nd["a"] = 2\nlet v = d["a"]')
    assert interp.globals.get("v") == 2


def test_methods():
    interp = Interpreter()
    interp.evaluate(parse_expression('{"a": 1, "b": 2}'), interp.globals)
    assert stringify(interp.evaluate(
        parse_expression('{"a": 1, "b": 2}'), interp.globals)) == "{a: 1, b: 2}"


def test_dict_len_and_has():
    assert stringify(run('let d = {"a": 1}\nlet n = d.len()').globals.get("n")) == "1"
    interp = Interpreter()
    d = interp.evaluate(parse_expression('{"a": 1}'), interp.globals)
    assert d.has("a") is True
    assert d.has("z") is False


def test_keys_values_sorted_output():
    d = BunDict()
    d.set("b", 2)
    d.set("a", 1)
    assert sorted(d.keys()) == ["a", "b"]
    assert sorted(d.values()) == [1, 2]


def test_remove():
    interp = run('let d = {"a": 1}\nd.remove("a")\nlet n = d.len()')
    assert interp.globals.get("n") == 0


def test_int_vs_string_keys_distinct():
    d = BunDict()
    d.set(1, "int")
    d.set("1", "str")
    assert d.get(1) == "int"
    assert d.get("1") == "str"


def test_missing_key_read_returns_null():
    # JavaScript object semantics: reading a missing key yields undefined
    # (null in Bun), it must not raise.
    interp = run('let d = {}\nlet v = d["nope"]')
    assert interp.globals.get("v") is None


def test_missing_key_read_compares_equal_to_null():
    interp = run('let d = {}\nlet v = d["nope"]\nlet same = v == null')
    assert interp.globals.get("same") is True


def test_get_missing_key_returns_null():
    interp = run('let d = {}\nlet v = d.get("nope")')
    assert interp.globals.get("v") is None


def test_remove_missing_key_errors():
    with pytest.raises(BunRuntimeError):
        run('let d = {}\nd.remove("nope")')


def test_unknown_dict_method_errors():
    with pytest.raises(BunRuntimeError):
        run('let d = {}\nd.frobnicate()')


def test_method_on_int_still_errors():
    with pytest.raises(BunRuntimeError):
        run("let n = 5\nn.len()")


def test_dict_equality():
    d1 = BunDict()
    d1.set("a", 1)
    d2 = BunDict()
    d2.set("a", 1)
    assert values_equal(d1, d2) is True
    d2.set("a", 2)
    assert values_equal(d1, d2) is False


def test_dict_in_list_stringify():
    d = BunDict()
    d.set("a", 1)
    assert stringify([d]) == "[{a: 1}]"
