from bun.dict import BunDict
from bun.values import (
    BunFunction, Builtin, is_number, is_truthy, stringify, values_equal,
)


def test_truthiness():
    assert is_truthy(1) is True
    assert is_truthy(0) is False
    assert is_truthy("") is False
    assert is_truthy("x") is True
    assert is_truthy(None) is False
    assert is_truthy([]) is False
    assert is_truthy([1]) is True


def test_stringify():
    assert stringify(True) == "true"
    assert stringify(None) == "null"
    assert stringify([1, "a", False]) == "[1, a, false]"


def test_stringify_self_referential_list():
    items = [1]
    items.append(items)
    assert stringify(items) == "[1, [...]]"


def test_stringify_self_referential_dict():
    d = BunDict()
    d.set("a", 1)
    d.set("self", d)
    assert stringify(d) == "{a: 1, self: {...}}"


def test_stringify_shared_acyclic_list_prints_fully():
    a = [1]
    assert stringify([a, a]) == "[[1], [1]]"


def test_stringify_shared_acyclic_dict_prints_fully():
    d = BunDict()
    d.set("a", 1)
    outer = BunDict()
    outer.set("x", d)
    outer.set("y", d)
    assert stringify(outer) == "{x: {a: 1}, y: {a: 1}}"


def test_stringify_cycle_through_dict_inside_list():
    items = [1]
    d = BunDict()
    d.set("items", items)
    items.append(d)
    assert stringify(items) == "[1, {items: [...]}]"


def test_stringify_cycle_through_list_inside_dict():
    d = BunDict()
    d.set("a", 1)
    items = [d]
    d.set("items", items)
    assert stringify(d) == "{a: 1, items: [{...}]}"


def test_stringify_non_cyclic_values_unchanged():
    fn = BunFunction("f", [], None, None)
    assert stringify(fn) == "<fn f>"
    assert stringify(Builtin("len", None)) == "<builtin len>"
    assert stringify(3.5) == "3.5"
    assert stringify("plain") == "plain"


def test_values_equal_types():
    assert values_equal(True, 1) is False
    assert values_equal(True, True) is True
    assert values_equal(1, 1.0) is True
    assert values_equal([1, 2], [1, 2]) is True


def test_is_number_excludes_bool():
    assert is_number(1) is True
    assert is_number(True) is False
