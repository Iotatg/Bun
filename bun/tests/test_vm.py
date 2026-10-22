import os
import pytest

from bun.cli import run_source
from bun.errors import BunRuntimeError, BunTypeError


def run_vm(source, check=True):
    run_source(source, filename="<test>.bun", check=check, engine="vm")


def test_vm_prints_string(capsys):
    run_vm('print("hello")')
    assert capsys.readouterr().out == "hello\n"


def test_vm_let_and_identifier(capsys):
    run_vm('let greeting = "hi"\nprint(greeting)')
    assert capsys.readouterr().out == "hi\n"


def test_vm_immutable_assign_rejected():
    with pytest.raises((BunRuntimeError, BunTypeError)) as info:
        run_vm("let x = 1\nx = 2")
    assert "immutable" in str(info.value)


def test_vm_discards_expression_statements(capsys):
    run_vm('let items = [1, 2, 3]\nprint(len(items))')
    assert capsys.readouterr().out == "3\n"


def test_vm_builds_lists(capsys):
    run_vm('print(len([1, 2, 3]))')
    assert capsys.readouterr().out == "3\n"


def test_vm_builds_dicts(capsys):
    run_vm('let scores = {"a": 1}\nprint(scores)')
    assert capsys.readouterr().out == "{a: 1}\n"


def test_vm_function_call_and_return(capsys):
    run_vm('fn greet(name) { return name }\nprint(greet("bun"))')
    assert capsys.readouterr().out == "bun\n"


def test_vm_implicit_null_return(capsys):
    run_vm('fn nothing() { }\nprint(nothing())')
    assert capsys.readouterr().out == "null\n"


def test_vm_closure_captures_scope(capsys):
    run_vm('fn outer() {\n  fn inner() {\n    return "deep"\n  }\n  return inner()\n}\nprint(outer())')
    assert capsys.readouterr().out == "deep\n"


def test_vm_anonymous_function_expression(capsys):
    run_vm('let double = fn(x) { return x * 2 }\nprint(double(21))')
    assert capsys.readouterr().out == "42\n"


def test_vm_anonymous_function_stringify_matches_tree(capsys):
    source = 'let ctx = {}\nctx["get"] = fn(cp) { return "Lu" }\nprint(ctx["get"](65))\nlet anon = fn(x) { return x }\nprint(anon)'
    run_source(source, filename="<test>.bun", engine="vm")
    expected = capsys.readouterr().out
    run_source(source, filename="<test>.bun", engine="tree")
    assert capsys.readouterr().out == expected
    assert expected == 'Lu\n<fn anonymous>\n'


def test_vm_call_arity_error():
    with pytest.raises(BunRuntimeError) as info:
        run_vm('fn one(a) { return a }\none(1, 2)', check=False)
    assert "argument" in str(info.value)


def test_vm_block_scope_shadowing(capsys):
    run_vm('let x = "outer"\nfn f() {\n  let x = "inner"\n  return x\n}\nprint(f())\nprint(x)')
    assert capsys.readouterr().out == "inner\nouter\n"


def test_vm_top_level_return_position_matches_tree_walker():
    positions = {}
    for engine in ("tree", "vm"):
        with pytest.raises(BunRuntimeError) as info:
            run_source("let x = 1\nreturn x", filename="<test>.bun",
                       check=True, engine=engine)
        positions[engine] = (info.value.msg, info.value.line, info.value.col)
    assert positions["tree"] == positions["vm"]
    assert positions["tree"] == ("'return' outside of a function", 2, 1)


def test_vm_arithmetic(capsys):
    run_vm('print(1 + 2 * 3)')
    assert capsys.readouterr().out == "7\n"


def test_vm_string_concat_and_comparison(capsys):
    run_vm('print("a" + "b")\nprint(1 < 2)\nprint("x" == "x")')
    assert capsys.readouterr().out == "ab\ntrue\ntrue\n"


def test_vm_division_semantics(capsys):
    run_vm('print(7 / 2)\nprint(7.0 / 2)')
    assert capsys.readouterr().out == "3\n3.5\n"


def test_vm_unary(capsys):
    run_vm('print(-5)\nprint(!true)')
    assert capsys.readouterr().out == "-5\nfalse\n"


def test_vm_division_by_zero():
    with pytest.raises(BunRuntimeError) as info:
        run_vm("print(1 / 0)")
    assert "division by zero" in str(info.value)


def test_vm_if_else(capsys):
    run_vm('let x = 5\nif x > 3 {\n  print("big")\n} else {\n  print("small")\n}')
    assert capsys.readouterr().out == "big\n"


def test_vm_else_if_chain(capsys):
    run_vm('let x = 2\nif x == 1 {\n  print("one")\n} else if x == 2 {\n  print("two")\n} else {\n  print("many")\n}')
    assert capsys.readouterr().out == "two\n"


def test_vm_while_loop(capsys):
    run_vm('var i = 0\nwhile i < 3 {\n  print(i)\n  i = i + 1\n}')
    assert capsys.readouterr().out == "0\n1\n2\n"


def test_vm_for_list(capsys):
    run_vm('for item in ["a", "b"] {\n  print(item)\n}')
    assert capsys.readouterr().out == "a\nb\n"


def test_vm_for_string(capsys):
    run_vm('for ch in "hi" {\n  print(ch)\n}')
    assert capsys.readouterr().out == "h\ni\n"


def test_vm_nested_for(capsys):
    run_vm('for a in [1, 2] {\n  for b in ["x", "y"] {\n    print(a)\n    print(b)\n  }\n}')
    assert capsys.readouterr().out == "1\nx\n1\ny\n2\nx\n2\ny\n"


def test_vm_logical_returns_operands(capsys):
    run_vm('print(0 and 5)\nprint(3 or 7)\nprint("" or "fallback")')
    assert capsys.readouterr().out == "0\n3\nfallback\n"


def test_vm_index_read(capsys):
    run_vm('let items = [10, 20, 30]\nprint(items[1])')
    assert capsys.readouterr().out == "20\n"


def test_vm_index_out_of_range():
    with pytest.raises(BunRuntimeError) as info:
        run_vm("let items = [1]\nprint(items[5])")
    assert "out of range" in str(info.value)


def test_vm_index_assignment(capsys):
    run_vm('let items = [1, 2, 3]\nitems[0] = 9\nprint(items[0])')
    assert capsys.readouterr().out == "9\n"


def test_vm_string_method(capsys):
    run_vm('print("  hi  ".trim())\nprint("AB".lower())')
    assert capsys.readouterr().out == "hi\nab\n"


def test_vm_list_sort_and_push(capsys):
    run_vm('let items = [3, 1, 2]\nitems.sort()\nitems.push(4)\nprint(items)')
    assert capsys.readouterr().out == "[1, 2, 3, 4]\n"


def test_vm_dict_index_assignment(capsys):
    run_vm('let scores = {"a": 1}\nscores["c"] = 3\nprint(scores["c"])')
    assert capsys.readouterr().out == "3\n"


def test_vm_method_error():
    with pytest.raises(BunRuntimeError) as info:
        run_vm("let x = 5\nx.trim()")
    assert "not a method" in str(info.value)


def test_vm_index_assignment_evaluation_order(capsys):
    run_vm('fn f() { print("f")\nreturn 0 }\nfn g() { print("g")\nreturn 9 }\nlet a = [1, 2]\na[f()] = g()\nprint(a)')
    assert capsys.readouterr().out == "g\nf\n[9, 2]\n"


MODULE_DIR = os.path.join(os.path.dirname(__file__), "vm_fixtures")


def write_module(name, text):
    os.makedirs(MODULE_DIR, exist_ok=True)
    path = os.path.join(MODULE_DIR, name)
    with open(path, "w") as handle:
        handle.write(text)
    return path


def test_vm_import_and_call(capsys):
    write_module("greet.bun", "export fn greet(name) {\n  return \"hi \" + name\n}\n")
    write_module("main.bun", "import { greet } from \"./greet\"\nprint(greet(\"bun\"))")
    with open(os.path.join(MODULE_DIR, "main.bun")) as handle:
        source = handle.read()
    run_source(source, filename=os.path.join(MODULE_DIR, "main.bun"), engine="vm")
    assert capsys.readouterr().out == "hi bun\n"


def test_vm_module_error_reports_module_frame():
    write_module("boom.bun", "export let value = 1\nlet missing = not_defined\n")
    write_module("main.bun", "import { value } from \"./boom\"\nprint(value)")
    with open(os.path.join(MODULE_DIR, "main.bun")) as handle:
        source = handle.read()
    with pytest.raises(BunRuntimeError) as info:
        run_source(source, filename=os.path.join(MODULE_DIR, "main.bun"), engine="vm")
    assert info.value.filename.endswith("boom.bun")
    assert info.value.line == 2


def test_vm_missing_export():
    write_module("lib.bun", "export let one = 1\n")
    write_module("main.bun", "import { two } from \"./lib\"\nprint(two)")
    with open(os.path.join(MODULE_DIR, "main.bun")) as handle:
        source = handle.read()
    with pytest.raises(BunRuntimeError) as info:
        run_source(source, filename=os.path.join(MODULE_DIR, "main.bun"), engine="vm", check=False)
    assert "does not export" in str(info.value)


def test_vm_circular_import():
    write_module("a.bun", "import { b } from \"./b\"\nexport let a = 1\n")
    write_module("b.bun", "import { a } from \"./a\"\nexport let b = 2\n")
    write_module("main.bun", "import { a } from \"./a\"\nprint(a)")
    with open(os.path.join(MODULE_DIR, "main.bun")) as handle:
        source = handle.read()
    with pytest.raises(BunRuntimeError) as info:
        run_source(source, filename=os.path.join(MODULE_DIR, "main.bun"), engine="vm", check=False)
    assert "circular import" in str(info.value)


def test_vm_module_runs_once(capsys):
    write_module("once.bun", "print(\"loaded\")\nexport let value = 7\n")
    write_module("main.bun",
                 "import { value } from \"./once\"\nimport { value } from \"./once\"\n"
                 "print(value + value)")
    with open(os.path.join(MODULE_DIR, "main.bun")) as handle:
        source = handle.read()
    run_source(source, filename=os.path.join(MODULE_DIR, "main.bun"), engine="vm")
    assert capsys.readouterr().out == "loaded\n14\n"


def test_vm_deferred_import_resolves_against_defining_module(capsys, tmp_path):
    pkg = tmp_path / "pkg"
    app = tmp_path / "app"
    pkg.mkdir()
    app.mkdir()
    (pkg / "lib.bun").write_text('export let v = "PKGLIB"\n')
    (pkg / "mid.bun").write_text(
        'export fn go() {\n    import { v } from "./lib"\n    return v\n}\n')
    (app / "lib.bun").write_text('export let v = "APPLIB"\n')
    source = 'import { go } from "../pkg/mid"\nprint(go())'
    run_source(source, filename=str(app / "main.bun"), engine="vm")
    assert capsys.readouterr().out == "PKGLIB\n"


def test_vm_module_top_level_return_parity():
    write_module("retmod.bun", "export let value = 1\nreturn value\n")
    write_module("main.bun", "import { value } from \"./retmod\"\nprint(value)")
    with open(os.path.join(MODULE_DIR, "main.bun")) as handle:
        source = handle.read()
    results = {}
    for engine in ("tree", "vm"):
        with pytest.raises(BunRuntimeError) as info:
            run_source(source, filename=os.path.join(MODULE_DIR, "main.bun"),
                       check=True, engine=engine)
        results[engine] = (info.value.msg, info.value.line, info.value.col,
                           info.value.filename)
    assert results["tree"] == results["vm"]
    assert results["tree"][0] == "'return' outside of a function"
    assert results["tree"][1] == 2
    assert results["tree"][3].endswith("retmod.bun")


def test_vm_try_catch_binds_message(capsys):
    with pytest.raises(BunTypeError) as error:
        run_vm('try {\n  let x = not_defined\n} catch error {\n  print(error)\n}')
    assert "undefined variable 'not_defined'" in str(error.value)


def test_vm_undefined_variable_is_a_static_error(capsys):
    run_vm('try {\n  let x = not_defined\n} catch error {\n  print(error)\n}',
           check=False)
    out = capsys.readouterr().out
    assert "undefined variable" in out


def test_vm_throw_and_catch(capsys):
    run_vm('try {\n  throw "boom"\n} catch error {\n  print(error)\n}')
    assert capsys.readouterr().out == "boom\n"


def test_vm_throw_number_stringifies(capsys):
    run_vm('try {\n  throw 42\n} catch error {\n  print(error)\n}')
    assert capsys.readouterr().out == "42\n"


def test_vm_catch_across_function_frames(capsys):
    run_vm('fn boom() {\n  throw "deep"\n}\ntry {\n  boom()\n} catch error {\n  print(error)\n}')
    assert capsys.readouterr().out == "deep\n"


def test_vm_rethrow(capsys):
    run_vm('try {\n  try {\n    throw "inner"\n  } catch error {\n    throw error\n  }\n} catch error {\n  print(error)\n}')
    assert capsys.readouterr().out == "inner\n"


def test_vm_bare_catch(capsys):
    run_vm('try {\n  throw "ignored"\n} catch {\n  print("caught")\n}')
    assert capsys.readouterr().out == "caught\n"


def test_vm_try_completes_without_error(capsys):
    run_vm('try {\n  print("ok")\n} catch error {\n  print("bad")\n}')
    assert capsys.readouterr().out == "ok\n"


def test_vm_uncaught_runtime_error_propagates():
    with pytest.raises(BunRuntimeError):
        run_vm('throw "escape"')


def test_vm_catch_outside_loop_preserves_iterator_stack(capsys):
    run_vm('for i in [1, 2] {\n  try {\n    for j in [1] {\n      throw "x"\n    }\n  } catch error {\n    print("caught")\n  }\n}')
    assert capsys.readouterr().out == "caught\ncaught\n"


CYCLE_LIST_SOURCE = "let a = [1]\na.push(a)\nprint(a)"

CYCLE_DICT_SOURCE = 'let d = {"a": 1}\nd["self"] = d\nprint(d)'

UNBOUNDED_RECURSION_SOURCE = "fn boom(n) { return boom(n + 1) }\nboom(0)"

CATCHABLE_OVERFLOW_SOURCE = (
    "fn boom(n) { return boom(n + 1) }\n"
    "try {\n"
    "  boom(0)\n"
    "} catch error {\n"
    '  print("caught")\n'
    "}"
)


def test_engines_print_acyclic_list_identically(capsys):
    expected = None
    for engine in ("tree", "vm"):
        run_source(CYCLE_LIST_SOURCE, filename="<test>.bun", engine=engine)
        out = capsys.readouterr().out
        if expected is None:
            expected = out
        assert out == expected
    assert expected == "[1, [...]]\n"


def test_engines_print_acyclic_dict_identically(capsys):
    expected = None
    for engine in ("tree", "vm"):
        run_source(CYCLE_DICT_SOURCE, filename="<test>.bun", engine=engine)
        out = capsys.readouterr().out
        if expected is None:
            expected = out
        assert out == expected
    assert expected == "{a: 1, self: {...}}\n"


def test_engines_report_identical_stack_overflow():
    results = {}
    for engine in ("tree", "vm"):
        with pytest.raises(BunRuntimeError) as info:
            run_source(UNBOUNDED_RECURSION_SOURCE, filename="<test>.bun",
                       check=False, engine=engine)
        results[engine] = (type(info.value), info.value.msg)
    assert results["tree"] == results["vm"]
    assert results["tree"][1] == "stack overflow"


def test_engines_catch_stack_overflow_identically(capsys):
    expected = None
    for engine in ("tree", "vm"):
        run_source(CATCHABLE_OVERFLOW_SOURCE, filename="<test>.bun",
                   check=False, engine=engine)
        out = capsys.readouterr().out
        if expected is None:
            expected = out
        assert out == expected
    assert expected == "caught\n"


DICT_MISSING_KEY_SOURCE = (
    'let d = {"a": 1}\n'
    'print(d["missing"] == null)\n'
    'print(d.get("missing") == null)\n'
    'print(d["a"])\n'
    'print(d.has("a"))\n'
    'print(d.has("missing"))\n'
)


def test_engines_read_missing_dict_key_identically(capsys):
    expected = None
    for engine in ("tree", "vm"):
        run_source(DICT_MISSING_KEY_SOURCE, filename="<test>.bun", engine=engine)
        out = capsys.readouterr().out
        if expected is None:
            expected = out
        assert out == expected
    assert expected == "true\ntrue\n1\ntrue\nfalse\n"
