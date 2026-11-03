"""Tests for the containers that speak and for the print of many values."""

import pytest

from bun.cli import run_source
from bun.errors import BunError, BunTypeError


def run_both(source, capsys):
    run_source(source, filename="<containers>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<containers>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    return vm_out


DOUBLE = "fn double(n) { return n * 2 }\n"
EVEN = "fn is_even(n) { return n % 2 == 0 }\n"


def test_map_answers_a_new_list(capsys):
    out = run_both(DOUBLE + "print([1, 2, 3].map(double))\n", capsys)
    assert out == "[2, 4, 6]\n"


def test_map_of_an_empty_list(capsys):
    out = run_both(DOUBLE + "print([].map(double))\n", capsys)
    assert out == "[]\n"


def test_filter_keeps_the_values_the_predicate_keeps(capsys):
    out = run_both(EVEN + "print([1, 2, 3, 4].filter(is_even))\n", capsys)
    assert out == "[2, 4]\n"


def test_reduce_folds_the_list(capsys):
    source = ("fn add_to(acc, value) { return acc + value }\n"
              "print([1, 2, 3].reduce(0, add_to))\n")
    out = run_both(source, capsys)
    assert out == "6\n"


def test_reduce_of_an_empty_list_answers_the_start(capsys):
    source = ("fn add_to(acc, value) { return acc + value }\n"
              "print([].reduce(7, add_to))\n")
    out = run_both(source, capsys)
    assert out == "7\n"


def test_find_answers_the_first_value_the_predicate_keeps(capsys):
    out = run_both(EVEN + "print([1, 2, 3].find(is_even))\n", capsys)
    assert out == "2\n"


def test_find_answers_null_when_the_predicate_keeps_nothing(capsys):
    source = "fn never(n) { return false }\nprint([1, 2].find(never))\n"
    out = run_both(source, capsys)
    assert out == "null\n"


def test_any_and_all(capsys):
    source = EVEN + "print([1, 2].any(is_even))\nprint([1, 3].all(is_even))\n"
    out = run_both(source, capsys)
    assert out == "true\nfalse\n"


def test_each_runs_the_function_for_every_value(capsys):
    source = "fn show(v) { print(v) }\n[1, 2].each(show)\n"
    out = run_both(source, capsys)
    assert out == "1\n2\n"


def test_sort_with_a_comparator(capsys):
    source = ("fn descending(a, b) { return b - a }\n"
              "var numbers = [1, 3, 2]\n"
              "numbers.sort(descending)\n"
              "print(numbers)\n")
    out = run_both(source, capsys)
    assert out == "[3, 2, 1]\n"


def test_sort_without_an_argument_keeps_its_old_meaning(capsys):
    out = run_both("var numbers = [3, 1, 2]\nnumbers.sort()\nprint(numbers)\n",
                   capsys)
    assert out == "[1, 2, 3]\n"


def test_sort_by_the_key_of_every_value(capsys):
    source = ("fn by_length(word) { return len(word) }\n"
              "var words = [\"pear\", \"fig\", \"apple\"]\n"
              "words.sort_by(by_length)\n"
              "print(words)\n")
    out = run_both(source, capsys)
    assert out == "[fig, pear, apple]\n"


def test_items_answers_the_pairs_of_the_dict(capsys):
    out = run_both("print({\"a\": 1}.items())\n", capsys)
    assert out == "[[a, 1]]\n"


def test_len_answers_the_number_of_the_entries_of_a_dict(capsys):
    out = run_both("print(len({\"a\": 1, \"b\": 2}))\n", capsys)
    assert out == "2\n"


def test_print_takes_many_arguments(capsys):
    out = run_both("print(\"a\", 1, true)\n", capsys)
    assert out == "a 1 true\n"


def test_print_without_arguments_writes_an_empty_line(capsys):
    out = run_both("print()\n", capsys)
    assert out == "\n"


def test_the_checker_refuses_a_method_the_container_does_not_have():
    with pytest.raises(BunTypeError) as info:
        run_source("print([1, 2].bogus())\n", filename="<containers>.bun",
                   check=True)
    assert "unknown method 'bogus' on list" in info.value.msg


def test_the_checker_refuses_the_wrong_number_of_arguments():
    with pytest.raises(BunTypeError) as info:
        run_source("var l: list = [1, 2]\nprint(l.map())\n",
                   filename="<containers>.bun", check=True)
    assert "'map' expects 1 argument(s), got 0" in info.value.msg


def test_a_method_that_is_not_a_function_is_refused():
    with pytest.raises(BunError) as info:
        run_source("print([1, 2].map(5))\n", filename="<containers>.bun",
                   check=True)
    assert "5 is not callable" in info.value.msg


def test_the_c_backend_answers_the_same(capfd):
    source = (DOUBLE + EVEN + "print([1, 2, 3].map(double))\n"
              "print([1, 2, 3].filter(is_even))\n")
    run_source(source, filename="<containers>.bun", check=True, engine="tree")
    tree_out = capfd.readouterr().out
    run_source(source, filename="<containers>.bun", check=True, engine="c")
    assert capfd.readouterr().out == tree_out


def test_the_register_engine_answers_the_same(capsys):
    source = (DOUBLE + EVEN + "print([1, 2, 3].map(double))\n"
              "print([1, 2, 3].filter(is_even))\n")
    run_source(source, filename="<containers>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<containers>.bun", check=True, engine="register")
    assert capsys.readouterr().out == tree_out


def test_the_comparator_must_answer_a_number(capsys):
    source = ("fn wrong(a, b) { return \"x\" }\n"
              "var numbers = [1, 2]\n"
              "numbers.sort(wrong)\n")
    with pytest.raises(BunError) as info:
        run_source(source, filename="<containers>.bun", check=True, engine="vm")
    assert "'sort' expects a number from the comparator" in info.value.msg


def test_sort_by_refuses_keys_that_are_not_numbers_or_strings(capsys):
    source = ("fn wrong(word) { return {\"a\": 1} }\n"
              "var words = [\"pear\"]\n"
              "words.sort_by(wrong)\n")
    with pytest.raises(BunError) as info:
        run_source(source, filename="<containers>.bun", check=True, engine="vm")
    assert "cannot sort list with mixed types" in info.value.msg
