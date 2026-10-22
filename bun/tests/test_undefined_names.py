import pytest

from bun.cli import run_source
from bun.errors import BunTypeError


def check_error(source):
    with pytest.raises(BunTypeError) as error:
        run_source(source, filename="<test>.bun", check=True)
    return str(error.value)


def test_undefined_variable_is_reported():
    message = check_error("print(not_defined)")
    assert "undefined variable 'not_defined'" in message


def test_undefined_variable_in_an_assignment_is_reported():
    message = check_error("let x = not_defined")
    assert "undefined variable 'not_defined'" in message


def test_undefined_function_is_reported():
    message = check_error("fn f() {\n    missing_call()\n}")
    assert "undefined variable 'missing_call'" in message


def test_the_name_of_a_function_of_a_block_is_accepted():
    run_source("if true {\n    fn helper() {\n        return 1\n    }\n"
               "    print(helper())\n}", filename="<test>.bun", check=True)


def test_the_name_of_a_function_of_a_loop_is_accepted():
    run_source("for item in [1, 2] {\n    fn helper() {\n        return item\n"
               "    }\n    print(helper())\n}", filename="<test>.bun", check=True)


def test_a_known_name_is_accepted():
    run_source("let x = 1\nprint(x)", filename="<test>.bun", check=True)


def test_a_name_of_a_later_statement_is_accepted():
    run_source("fn f() {\n    return helper()\n}\n"
               "fn helper() -> int {\n    return 1\n}\n"
               "print(f())", filename="<test>.bun", check=True)


def test_a_name_of_a_later_variable_is_accepted():
    run_source("fn f() -> int {\n    return later\n}\n"
               "let later = 1\nprint(f())", filename="<test>.bun", check=True)


def test_the_name_of_a_parameter_is_accepted():
    run_source("fn f(name: string) {\n    print(name)\n}\nf(\"bun\")",
               filename="<test>.bun", check=True)


def test_the_name_of_a_loop_variable_is_accepted():
    run_source("for item in [1, 2] {\n    print(item)\n}",
               filename="<test>.bun", check=True)


def test_the_name_of_a_catch_parameter_is_accepted():
    run_source("try {\n    print(1)\n} catch error {\n    print(error)\n}",
               filename="<test>.bun", check=True)


def test_the_name_of_a_with_item_is_accepted():
    run_source('fn ctx() {\n'
               '    return {"__enter__": fn() { return 1 }, '
               '"__exit__": fn(err) { return null }}\n'
               '}\n'
               'with ctx() as handle {\n    print(handle)\n}',
               filename="<test>.bun", check=True)


def test_the_name_of_a_comprehension_target_is_accepted():
    run_source("let xs = [item * 2 for item in [1, 2]]\nprint(xs)",
               filename="<test>.bun", check=True)


def test_the_name_of_an_unpacked_value_is_accepted():
    run_source("let a, b = [1, 2]\nprint(a + b)",
               filename="<test>.bun", check=True)


def test_a_builtin_name_is_accepted():
    run_source("print(len([1, 2]))", filename="<test>.bun", check=True)


def test_the_name_of_a_method_is_not_a_variable():
    run_source("let xs = [1, 2]\nxs.push(3)\nprint(xs)",
               filename="<test>.bun", check=True)


def test_the_name_of_a_keyword_argument_is_not_a_variable():
    run_source("fn f(a: int, b: int) -> int {\n    return a + b\n}\n"
               "print(f(a=1, b=2))", filename="<test>.bun", check=True)
