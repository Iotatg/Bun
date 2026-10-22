"""Tests for function parameters: defaults, `*args`, `**kwargs` and
keyword-only arguments."""

import pytest

from bun.cli import run_source
from bun.errors import BunError


def run_both(source, capsys):
    """Run the same source on both engines and assert identical output."""
    run_source(source, filename="<test>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<test>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    return vm_out


def test_default_value_is_used(capsys):
    out = run_both(
        "fn greet(name, greeting = \"Hello\") {\n"
        "  return greeting + name\n"
        "}\n"
        "print(greet(\"World\"))\n", capsys)
    assert out == "HelloWorld\n"


def test_default_is_overridden(capsys):
    out = run_both(
        "fn greet(name, greeting = \"Hello\") {\n"
        "  return greeting + name\n"
        "}\n"
        "print(greet(\"World\", \"Hi\"))\n", capsys)
    assert out == "HiWorld\n"


def test_default_is_evaluated_at_call_time(capsys):
    out = run_both(
        "var counter = 0\n"
        "fn next() -> int {\n"
        "  counter = counter + 1\n"
        "  return counter\n"
        "}\n"
        "fn pick(value = next()) -> int {\n"
        "  return value\n"
        "}\n"
        "print(pick())\n"
        "print(pick())\n", capsys)
    assert out == "1\n2\n"


def test_default_can_use_earlier_parameters(capsys):
    out = run_both(
        "fn scaled(value, factor = value * 2) -> int {\n"
        "  return value * factor\n"
        "}\n"
        "print(scaled(3))\n", capsys)
    assert out == "18\n"


def test_keyword_argument_at_call_site(capsys):
    out = run_both(
        "fn greet(name, greeting = \"Hello\") {\n"
        "  return greeting + \", \" + name\n"
        "}\n"
        "print(greet(greeting = \"Yo\", name = \"Bob\"))\n", capsys)
    assert out == "Yo, Bob\n"


def test_keyword_and_positional_arguments_mix(capsys):
    out = run_both(
        "fn connect(host, port = 8080) -> string {\n"
        "  return host + \":\" + str(port)\n"
        "}\n"
        "print(connect(\"localhost\", port = 90))\n", capsys)
    assert out == "localhost:90\n"


def test_varargs_collects_extra_arguments(capsys):
    out = run_both(
        "fn total(base, *values) -> int {\n"
        "  var result = base\n"
        "  for value in values {\n"
        "    result = result + value\n"
        "  }\n"
        "  return result\n"
        "}\n"
        "print(total(1, 2, 3, 4))\n", capsys)
    assert out == "10\n"


def test_varargs_can_be_empty(capsys):
    out = run_both(
        "fn total(base, *values) -> int {\n"
        "  return base + values.len()\n"
        "}\n"
        "print(total(7))\n", capsys)
    assert out == "7\n"


def test_varargs_is_a_list(capsys):
    out = run_both(
        "fn collect(*values) -> int {\n"
        "  return values.len()\n"
        "}\n"
        "print(collect(1, 2, 3))\n", capsys)
    assert out == "3\n"


def test_kwargs_collects_extra_keywords(capsys):
    out = run_both(
        "fn describe(label, **extra) -> string {\n"
        "  var text = label\n"
        "  for key in extra.keys() {\n"
        "    text = text + \" \" + key + \"=\" + str(extra.get(key))\n"
        "  }\n"
        "  return text\n"
        "}\n"
        "print(describe(\"stats\", views = 10))\n", capsys)
    assert out == "stats views=10\n"


def test_kwargs_is_empty_when_unused(capsys):
    out = run_both(
        "fn describe(label, **extra) -> int {\n"
        "  return extra.len()\n"
        "}\n"
        "print(describe(\"stats\"))\n", capsys)
    assert out == "0\n"


def test_keyword_only_parameter(capsys):
    out = run_both(
        "fn connect(host, port = 8080, *, timeout = 30) -> string {\n"
        "  return host + \":\" + str(port) + \"/\" + str(timeout)\n"
        "}\n"
        "print(connect(\"localhost\", timeout = 5))\n", capsys)
    assert out == "localhost:8080/5\n"


def test_keyword_only_parameter_is_required_without_default(capsys):
    out = run_both(
        "fn connect(host, *, token) -> string {\n"
        "  return host + \"/\" + token\n"
        "}\n"
        "print(connect(\"localhost\", token = \"abc\"))\n", capsys)
    assert out == "localhost/abc\n"


def test_keyword_only_rejects_positional_argument(capsys):
    with pytest.raises(BunError) as info:
        run_source(
            "fn connect(host, *, token) -> string {\n"
            "  return host + token\n"
            "}\n"
            "print(connect(\"localhost\", \"abc\"))\n", filename="<test>.bun")
    assert "expects 1 argument(s), got 2" in str(info.value)


def test_varargs_and_kwargs_together(capsys):
    out = run_both(
        "fn collect(*values, **options) -> string {\n"
        "  return str(values.len()) + \":\" + str(options.len())\n"
        "}\n"
        "print(collect(1, 2, a = 1, b = 2))\n", capsys)
    assert out == "2:2\n"


def test_default_keeps_signature_arity(capsys):
    out = run_both(
        "fn f(a, b = 2, c = 3) -> int {\n"
        "  return a + b + c\n"
        "}\n"
        "print(f(1))\n"
        "print(f(1, 5))\n"
        "print(f(1, 5, 9))\n", capsys)
    assert out == "6\n9\n15\n"


def test_too_many_positional_arguments_is_an_error(capsys):
    with pytest.raises(BunError) as info:
        run_source(
            "fn f(a, b = 2) -> int {\n"
            "  return a + b\n"
            "}\n"
            "print(f(1, 2, 3))\n", filename="<test>.bun")
    assert "expects 2 argument(s), got 3" in str(info.value)


def test_missing_required_argument_is_an_error(capsys):
    with pytest.raises(BunError) as info:
        run_source(
            "fn f(a, b = 2) -> int {\n"
            "  return a + b\n"
            "}\n"
            "print(f())\n", filename="<test>.bun")
    assert "missing required argument 'a'" in str(info.value)


def test_unexpected_keyword_argument_is_an_error(capsys):
    with pytest.raises(BunError) as info:
        run_source(
            "fn f(a) -> int {\n"
            "  return a\n"
            "}\n"
            "print(f(1, z = 2))\n", filename="<test>.bun")
    assert "unexpected keyword argument 'z'" in str(info.value)


def test_duplicate_argument_is_an_error(capsys):
    with pytest.raises(BunError) as info:
        run_source(
            "fn f(a, b = 2) -> int {\n"
            "  return a + b\n"
            "}\n"
            "print(f(1, a = 3))\n", filename="<test>.bun")
    assert "multiple values for argument 'a'" in str(info.value)


def test_anonymous_function_with_defaults(capsys):
    out = run_both(
        "let f = fn(a, b = 2) -> int {\n"
        "  return a + b\n"
        "}\n"
        "print(f(1))\n"
        "print(f(1, 5))\n", capsys)
    assert out == "3\n6\n"


def test_function_value_is_passed_as_argument(capsys):
    out = run_both(
        "fn double(value) -> int {\n"
        "  return value * 2\n"
        "}\n"
        "fn apply_twice(fn_ptr, value) -> int {\n"
        "  return fn_ptr(fn_ptr(value))\n"
        "}\n"
        "print(apply_twice(double, 3))\n", capsys)
    assert out == "12\n"


def test_keyword_argument_forwarding(capsys):
    out = run_both(
        "fn inner(a, b = 2) -> int {\n"
        "  return a + b\n"
        "}\n"
        "fn outer(a, b = 5) -> int {\n"
        "  return inner(a, b = b)\n"
        "}\n"
        "print(outer(1))\n", capsys)
    assert out == "6\n"


def test_typed_parameters_still_work(capsys):
    out = run_both(
        "fn add(a: int, b: int = 2) -> int {\n"
        "  return a + b\n"
        "}\n"
        "print(add(1))\n"
        "print(add(b = 3, a = 1))\n", capsys)
    assert out == "3\n4\n"


def test_typed_parameter_type_mismatch_is_reported(capsys):
    with pytest.raises(BunError) as info:
        run_source(
            "fn add(a: int, b: int = 2) -> int {\n"
            "  return a + b\n"
            "}\n"
            "print(add(\"x\"))\n", filename="<test>.bun")
    assert "not assignable to parameter of type 'int'" in str(info.value)
