"""Tests for the ``match`` statement."""

import pytest

from bun.cli import run_source
from bun.errors import BunRuntimeError


def run_both(source, capsys):
    """Run the same source on both engines and assert identical output."""
    run_source(source, filename="<match>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<match>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    return vm_out


def run_error(source, capsys):
    """Run a source that must fail, and return the error message."""
    with pytest.raises(BunRuntimeError) as info:
        run_source(source, filename="<match>.bun", check=True, engine="vm")
    return info.value.msg


def test_the_literal_case(capsys):
    out = run_both("let code = 404\n"
                   "match code {\n"
                   "    200 => print(\"ok\"),\n"
                   "    404 => print(\"not found\"),\n"
                   "    _ => print(\"other\"),\n"
                   "}\n", capsys)
    assert out == "not found\n"


def test_the_first_case_wins(capsys):
    out = run_both("match 1 {\n"
                   "    1 => print(\"first\"),\n"
                   "    1 => print(\"second\"),\n"
                   "}\n", capsys)
    assert out == "first\n"


def test_the_binding_case(capsys):
    out = run_both("match 42 {\n"
                   "    value => print(\"bound \" + str(value)),\n"
                   "}\n", capsys)
    assert out == "bound 42\n"


def test_the_wildcard_case_binds_nothing(capsys):
    out = run_both("match 42 {\n"
                   "    _ => print(\"anything\"),\n"
                   "}\n", capsys)
    assert out == "anything\n"


def test_the_type_case(capsys):
    out = run_both("match \"text\" {\n"
                   "    int => print(\"an int\"),\n"
                   "    string => print(\"a string\"),\n"
                   "    _ => print(\"other\"),\n"
                   "}\n", capsys)
    assert out == "a string\n"


def test_the_type_case_of_a_list(capsys):
    out = run_both("match [1] {\n"
                   "    list => print(\"a list\"),\n"
                   "    _ => print(\"other\"),\n"
                   "}\n", capsys)
    assert out == "a list\n"


def test_the_type_case_of_a_dict(capsys):
    out = run_both("match { \"a\": 1 } {\n"
                   "    dict => print(\"a dict\"),\n"
                   "    _ => print(\"other\"),\n"
                   "}\n", capsys)
    assert out == "a dict\n"


def test_the_type_case_of_null(capsys):
    out = run_both("match null {\n"
                   "    null => print(\"nothing\"),\n"
                   "    _ => print(\"other\"),\n"
                   "}\n", capsys)
    assert out == "nothing\n"


def test_the_range_case(capsys):
    out = run_both("match 5 {\n"
                   "    1 to 9 => print(\"small\"),\n"
                   "    10 to 20 => print(\"medium\"),\n"
                   "    _ => print(\"large\"),\n"
                   "}\n", capsys)
    assert out == "small\n"


def test_the_range_is_inclusive(capsys):
    out = run_both("match 9 {\n"
                   "    1 to 9 => print(\"inside\"),\n"
                   "    _ => print(\"outside\"),\n"
                   "}\n", capsys)
    assert out == "inside\n"


def test_the_list_case(capsys):
    out = run_both("match [1, 2] {\n"
                   "    [a, b] => print(str(a) + str(b)),\n"
                   "    _ => print(\"other\"),\n"
                   "}\n", capsys)
    assert out == "12\n"


def test_the_list_case_of_a_wrong_length(capsys):
    out = run_both("match [1, 2, 3] {\n"
                   "    [a, b] => print(\"two\"),\n"
                   "    _ => print(\"other\"),\n"
                   "}\n", capsys)
    assert out == "other\n"


def test_the_list_case_of_a_list_of_literals(capsys):
    out = run_both("match [1, 2] {\n"
                   "    [1, 2] => print(\"one and two\"),\n"
                   "    _ => print(\"other\"),\n"
                   "}\n", capsys)
    assert out == "one and two\n"


def test_the_dict_case(capsys):
    out = run_both("match { \"id\": 7, \"name\": \"x\" } {\n"
                   "    { \"id\": id } => print(\"id \" + str(id)),\n"
                   "    _ => print(\"other\"),\n"
                   "}\n", capsys)
    assert out == "id 7\n"


def test_the_dict_case_without_the_key(capsys):
    out = run_both("match { \"name\": \"x\" } {\n"
                   "    { \"id\": id } => print(\"has an id\"),\n"
                   "    _ => print(\"other\"),\n"
                   "}\n", capsys)
    assert out == "other\n"


def test_the_case_body_may_be_a_block(capsys):
    out = run_both("match 1 {\n"
                   "    1 => {\n"
                   "        print(\"one\")\n"
                   "        print(\"and a half\")\n"
                   "    },\n"
                   "    _ => print(\"other\"),\n"
                   "}\n", capsys)
    assert out == "one\nand a half\n"


def test_the_comma_after_a_case_is_optional(capsys):
    out = run_both("match 1 {\n"
                   "    1 => print(\"one\")\n"
                   "    _ => print(\"other\")\n"
                   "}\n", capsys)
    assert out == "one\n"


def test_the_subject_is_evaluated_once(capsys):
    out = run_both("var calls = 0\n"
                   "fn subject() -> int {\n"
                   "    calls = calls + 1\n"
                   "    return 1\n"
                   "}\n"
                   "match subject() {\n"
                   "    2 => print(\"two\"),\n"
                   "    _ => print(\"one\"),\n"
                   "}\n"
                   "print(calls)\n", capsys)
    assert out == "one\n1\n"


def test_a_match_without_a_case_is_an_error(capsys):
    assert run_error("match 123 {\n"
                     "    1 => print(\"one\"),\n"
                     "}\n", capsys) == "no matching case for 123"


def test_a_match_without_any_case_is_an_error(capsys):
    assert run_error("match 123 {\n"
                     "}\n", capsys) == "no matching case for 123"


def test_the_error_names_the_value(capsys):
    assert run_error("match \"text\" {\n"
                     "    1 => print(\"one\"),\n"
                     "}\n", capsys) == 'no matching case for "text"'


def test_the_names_of_a_case_do_not_leak_into_the_next(capsys):
    out = run_both("match 1 {\n"
                   "    1 => {\n"
                   "        let bound = 5\n"
                   "        print(bound)\n"
                   "    },\n"
                   "    _ => print(\"other\"),\n"
                   "}\n", capsys)
    assert out == "5\n"


def test_the_match_is_a_soft_keyword(capsys):
    out = run_both("var match = 5\n"
                   "print(match)\n"
                   "match = 7\n"
                   "print(match)\n", capsys)
    assert out == "5\n7\n"


def test_the_match_name_can_be_a_function(capsys):
    out = run_both("fn match(x: int) -> int {\n"
                   "    return x * 2\n"
                   "}\n"
                   "print(match(3))\n", capsys)
    assert out == "6\n"


def test_the_break_inside_a_match(capsys):
    out = run_both("for i in [1, 2, 3] {\n"
                   "    match i {\n"
                   "        2 => break,\n"
                   "        _ => print(\"item \" + str(i)),\n"
                   "    }\n"
                   "}\n"
                   "print(\"done\")\n", capsys)
    assert out == "item 1\ndone\n"


def test_the_continue_inside_a_match(capsys):
    out = run_both("for i in [1, 2, 3] {\n"
                   "    match i {\n"
                   "        2 => continue,\n"
                   "        _ => print(\"item \" + str(i)),\n"
                   "    }\n"
                   "    print(\"after \" + str(i))\n"
                   "}\n", capsys)
    assert out == "item 1\nafter 1\nitem 3\nafter 3\n"


def test_the_return_inside_a_match(capsys):
    out = run_both("fn find(value: int) -> string {\n"
                   "    match value {\n"
                   "        1 => return \"one\",\n"
                   "        _ => return \"other\",\n"
                   "    }\n"
                   "    return \"never\"\n"
                   "}\n"
                   "print(find(1))\n", capsys)
    assert out == "one\n"


def test_the_match_inside_a_function(capsys):
    out = run_both("fn kind(value: any) -> string {\n"
                   "    match value {\n"
                   "        int => return \"int\",\n"
                   "        string => return \"string\",\n"
                   "        _ => return \"other\",\n"
                   "    }\n"
                   "}\n"
                   "print(kind(1))\n"
                   "print(kind(\"a\"))\n"
                   "print(kind(1.5))\n", capsys)
    assert out == "int\nstring\nother\n"


def test_the_undefined_name_of_a_pattern_is_caught(capsys):
    with pytest.raises(Exception) as info:
        run_source("match 1 {\n"
                   "    1 => print(missing_name),\n"
                   "}\n", filename="<match>.bun", check=True, engine="vm")
    assert "missing_name" in str(info.value)


def test_the_case_body_may_be_an_unpacking_assignment(capsys):
    out = run_both("var a = 0\n"
                   "var b = 0\n"
                   "match 1 {\n"
                   "    _ => a, b = [7, 8],\n"
                   "}\n"
                   "print(a)\n"
                   "print(b)\n", capsys)
    assert out == "7\n8\n"


def test_the_case_body_may_be_a_dict_in_parentheses(capsys):
    out = run_both("match 1 {\n"
                   "    _ => ({\"a\": 1}),\n"
                   "}\n", capsys)
    assert out == ""


def test_the_alternatives_of_one_case(capsys):
    out = run_both("match 302 {\n"
                   "    301, 302 => print(\"moved\"),\n"
                   "    _ => print(\"other\"),\n"
                   "}\n", capsys)
    assert out == "moved\n"


def test_the_first_alternative_that_matches_wins(capsys):
    out = run_both("match 2 {\n"
                   "    1, 2, 3 => print(\"small\"),\n"
                   "    2, 9 => print(\"never\"),\n"
                   "}\n", capsys)
    assert out == "small\n"


def test_an_alternative_may_be_a_type_pattern(capsys):
    out = run_both("match \"text\" {\n"
                   "    int, float => print(\"a number\"),\n"
                   "    string => print(\"a string\"),\n"
                   "    _ => print(\"neither\"),\n"
                   "}\n", capsys)
    assert out == "a string\n"


def test_an_alternative_may_bind_a_name(capsys):
    out = run_both("match 7 {\n"
                   "    1, 2 => print(\"small\"),\n"
                   "    n => print(\"other \" + str(n)),\n"
                   "}\n", capsys)
    assert out == "other 7\n"


def test_the_alternatives_are_tried_in_order(capsys):
    out = run_both("match 5 {\n"
                   "    1, 5 => print(\"first\"),\n"
                   "    5, 9 => print(\"second\"),\n"
                   "}\n", capsys)
    assert out == "first\n"


def test_a_case_without_an_alternative_still_works(capsys):
    out = run_both("match 1 {\n"
                   "    1 => print(\"one\"),\n"
                   "    2 => print(\"two\"),\n"
                   "}\n", capsys)
    assert out == "one\n"

def test_the_guard_holds(capsys):
    out = run_both("match 5 {\n"
                   "    n if n > 3 => print(\"big \" + str(n)),\n"
                   "    _ => print(\"small\"),\n"
                   "}\n", capsys)
    assert out == "big 5\n"


def test_the_guard_sends_the_case_on_to_the_next_one(capsys):
    out = run_both("match 2 {\n"
                   "    n if n > 3 => print(\"big\"),\n"
                   "    n => print(\"small \" + str(n)),\n"
                   "}\n", capsys)
    assert out == "small 2\n"


def test_a_guard_may_be_false_for_every_case(capsys):
    out = run_both("match 1 {\n"
                   "    n if n > 3 => print(\"big\"),\n"
                   "    _ => print(\"small\"),\n"
                   "}\n", capsys)
    assert out == "small\n"


def test_the_guard_sees_the_name_of_the_pattern(capsys):
    out = run_both("match \"text\" {\n"
                   "    s if s == \"text\" => print(\"the word\"),\n"
                   "    _ => print(\"other\"),\n"
                   "}\n", capsys)
    assert out == "the word\n"


def test_a_guard_may_use_any_expression(capsys):
    out = run_both("fn big(value: int) -> bool {\n"
                   "    return value > 10\n"
                   "}\n"
                   "match 5 {\n"
                   "    n if big(n) => print(\"big\"),\n"
                   "    _ => print(\"small\"),\n"
                   "}\n", capsys)
    assert out == "small\n"


def test_a_guard_may_hold_a_name_of_the_pattern(capsys):
    out = run_both("match [1, 2] {\n"
                   "    [a, b] if a < b => print(\"in order\"),\n"
                   "    _ => print(\"not in order\"),\n"
                   "}\n", capsys)
    assert out == "in order\n"


def test_a_guard_with_alternatives(capsys):
    out = run_both("match 7 {\n"
                   "    1, 2 => print(\"small\"),\n"
                   "    7, 8 => print(\"seven\"),\n"
                   "    _ => print(\"other\"),\n"
                   "}\n", capsys)
    assert out == "seven\n"

def test_the_list_pattern_with_a_tail(capsys):
    out = run_both("match [1, 2, 3] {\n"
                   "    [first, *rest] => print(str(first) + \" \" + str(len(rest))),\n"
                   "    _ => print(\"no match\"),\n"
                   "}\n", capsys)
    assert out == "1 2\n"


def test_the_tail_may_be_empty(capsys):
    out = run_both("match [1] {\n"
                   "    [first, *rest] => print(str(first) + \" \" + str(len(rest))),\n"
                   "    _ => print(\"no match\"),\n"
                   "}\n", capsys)
    assert out == "1 0\n"


def test_the_tail_may_take_the_whole_list(capsys):
    out = run_both("match [1, 2] {\n"
                   "    [*all] => print(str(len(all))),\n"
                   "    _ => print(\"no match\"),\n"
                   "}\n", capsys)
    assert out == "2\n"


def test_a_list_without_a_tail_still_needs_the_same_length(capsys):
    out = run_both("match [1, 2, 3] {\n"
                   "    [a, b] => print(\"two\"),\n"
                   "    _ => print(\"other\"),\n"
                   "}\n", capsys)
    assert out == "other\n"


def test_a_list_shorter_than_the_pattern_does_not_match(capsys):
    out = run_both("match [1] {\n"
                   "    [a, b, c] => print(\"three\"),\n"
                   "    _ => print(\"other\"),\n"
                   "}\n", capsys)
    assert out == "other\n"
