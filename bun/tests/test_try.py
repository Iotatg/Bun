import pytest

from bun.cli import run_source
from bun.errors import BunRuntimeError, BunTypeError
from bun.interpreter import Interpreter
from bun.parser import parse


def run(source):
    interp = Interpreter()
    interp.run(parse(source))
    return interp


def test_try_success_skips_catch(capsys):
    run('try {\n    print("ok")\n} catch e {\n    print("caught")\n}')
    assert capsys.readouterr().out == "ok\n"


def test_runtime_error_enters_catch(capsys):
    run('try {\n    print(missing)\n} catch e {\n    print("caught: " + e)\n}')
    assert capsys.readouterr().out == "caught: undefined variable 'missing'\n"


def test_method_errors_are_catchable(capsys):
    run('try {\n    let xs = []\n    xs.pop()\n} catch e {\n'
        '    print("caught: " + e)\n}')
    assert capsys.readouterr().out == "caught: 'pop' on an empty list\n"


def test_catch_binds_message_string(capsys):
    run('try {\n    throw "boom"\n} catch e {\n    print(e)\n}')
    assert capsys.readouterr().out == "boom\n"


def test_throw_stringifies_non_strings(capsys):
    run('try {\n    throw 42\n} catch e {\n    print(e + "!")\n}')
    assert capsys.readouterr().out == "42!\n"


def test_catch_without_param(capsys):
    run('try {\n    throw 1\n} catch {\n    print("anon")\n}')
    assert capsys.readouterr().out == "anon\n"


def test_throw_unwinds_through_function_call(capsys):
    run('fn boom() {\n    throw "from fn"\n}\n'
        'try {\n    boom()\n} catch e {\n    print("caught: " + e)\n}')
    assert capsys.readouterr().out == "caught: from fn\n"


def test_catch_param_is_block_scoped():
    with pytest.raises(BunRuntimeError, match="undefined variable 'e'"):
        run('try {\n    throw "x"\n} catch e {\n    print(e)\n}\nprint(e)')


def test_nested_try_inner_catches_first(capsys):
    run('try {\n    try {\n        throw "inner"\n    } catch e {\n'
        '        throw "outer: " + e\n    }\n} catch e2 {\n    print(e2)\n}')
    assert capsys.readouterr().out == "outer: inner\n"


def test_return_propagates_through_try():
    interp = run('fn pick(flag) {\n    try {\n        return 1\n    } catch e {\n'
                 '        return 2\n    }\n}\nlet a = pick(true)\nlet b = pick(false)')
    assert interp.globals.get("a") == 1
    assert interp.globals.get("b") == 1


def test_return_from_catch_block():
    interp = run('fn pick() {\n    try {\n        throw 1\n    } catch e {\n'
                 '        return "c"\n    }\n}\nlet r = pick()')
    assert interp.globals.get("r") == "c"


def test_uncaught_throw_propagates():
    with pytest.raises(BunRuntimeError, match="x"):
        run('try {\n    throw "x"\n} catch e {\n    throw e\n}')


def test_throw_outside_try_is_runtime_error():
    with pytest.raises(BunRuntimeError) as info:
        run('throw "outside"')
    assert info.value.msg == "outside"
    assert info.value.line == 1


def test_type_errors_are_not_catchable():
    with pytest.raises(BunTypeError):
        run_source('try {\n    let x: int = "s"\n} catch e {\n'
                   '    print("caught")\n}')
