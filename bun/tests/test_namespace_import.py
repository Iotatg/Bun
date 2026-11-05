"""Namespace imports: `import * as ns from "path"`.

The feature is checked on every engine, on both tiers of the register VM,
on the self-hosted front end, and on the native `bun:` module path. The C
backend refuses it by name, and that refusal is tested too.
"""

import os

import pytest

from bun import ast, cbackend, ops
from bun.checker import Checker
from bun.cli import run_file, run_source
from bun.errors import BunTypeError, ParseError
from bun.lexer import Lexer
from bun.parser import Parser
from bun.selfhost import run_front_end


ENGINES = [
    ("tree", False),
    ("vm", False),
    ("register", False),
    ("register", True),
]

MODULE = (
    "export fn add(a, b) {\n"
    "    return a + b\n"
    "}\n"
    "\n"
    'export let greeting = "namaste"\n'
    "\n"
    "export fn scale(x) {\n"
    "    return x * 3\n"
    "}\n"
)

OTHER = (
    "export fn add(a, b) {\n"
    "    return a - b\n"
    "}\n"
    'export let greeting = "other"\n'
)


def write(path, text):
    with open(str(path), "w") as handle:
        handle.write(text)


def run(source, base_dir, engine="vm", tier=False):
    return run_source(source, filename=os.path.join(str(base_dir), "main.bun"),
                      engine=engine, tier=tier)


def fixture(tmp_path):
    write(tmp_path / "m.bun", MODULE)
    write(tmp_path / "m2.bun", OTHER)
    return str(tmp_path)


def check(source, base_dir):
    program = Parser(Lexer(source).tokenize()).parse()
    return Checker().check(program, base_dir=base_dir)


@pytest.mark.parametrize("engine,tier", ENGINES, ids=[
    "tree", "vm", "register", "register+tier"])
def test_all_engines_print_the_same(tmp_path, capsys, engine, tier):
    base = fixture(tmp_path)
    source = ('import * as m from "./m.bun"\n'
              "print(m.add(2, 3))\n"
              "print(m.greeting)\n"
              "print(m.scale(7))\n"
              "print(m.add(10, 5))\n")
    run(source, base, engine=engine, tier=tier)
    assert capsys.readouterr().out == "5\nnamaste\n21\n15\n"


def test_namespace_is_one_binding_not_many(tmp_path):
    base = fixture(tmp_path)
    env = run('import * as m from "./m.bun"\nlet r = m.add(20, 22)',
              base)
    assert env.get("r") == 42
    assert env.has("m")
    # Only the alias is bound: the module's exports are NOT flattened into
    # the importing scope. `get` would raise on an unbound name, so use the
    # non-throwing `has` membership check here.
    assert not env.has("add")
    assert not env.has("greeting")
    assert not env.has("scale")


def test_plain_import_still_works(tmp_path):
    base = fixture(tmp_path)
    env = run('import { add, greeting } from "./m.bun"\n'
              "let r = add(2, 3)\nlet g = greeting", base)
    assert env.get("r") == 5
    assert env.get("g") == "namaste"


def test_two_namespaces_do_not_collide(tmp_path):
    base = fixture(tmp_path)
    env = run('import * as a from "./m.bun"\n'
              'import * as b from "./m2.bun"\n'
              "let x = a.add(9, 4)\n"
              "let y = b.add(9, 4)\n"
              "let p = a.greeting\n"
              "let q = b.greeting", base)
    assert (env.get("x"), env.get("y")) == (13, 5)
    assert (env.get("p"), env.get("q")) == ("namaste", "other")


def test_namespace_is_usable_inside_a_function(tmp_path):
    base = fixture(tmp_path)
    env = run('import * as m from "./m.bun"\n'
              "fn helper(x) {\n    return m.add(x, 1)\n}\n"
              "let r = helper(100)", base)
    assert env.get("r") == 101


def test_native_module_namespace(tmp_path):
    env = run('import * as math from "bun:math"\n'
              "let p = math.pi\n"
              "let q = math.max(3.0, 7.0)", str(tmp_path))
    assert env.get("p") == 3.141592653589793
    assert env.get("q") == 7.0


def test_unknown_field_is_a_type_error(tmp_path):
    base = fixture(tmp_path)
    with pytest.raises(BunTypeError, match="does not export 'typo'"):
        check('import * as m from "./m.bun"\nprint(m.typo)\n', base)


def test_unknown_method_is_a_type_error(tmp_path):
    base = fixture(tmp_path)
    with pytest.raises(BunTypeError, match="does not export 'typo'"):
        check('import * as m from "./m.bun"\nprint(m.typo())\n', base)


def test_wrong_arity_is_a_type_error(tmp_path):
    base = fixture(tmp_path)
    with pytest.raises(BunTypeError, match="expects 2 argument"):
        check('import * as m from "./m.bun"\nprint(m.add(1))\n', base)


def test_namespace_field_is_read_only(tmp_path):
    base = fixture(tmp_path)
    with pytest.raises(BunTypeError, match="cannot assign to a field"):
        check('import * as m from "./m.bun"\n'
              'm.greeting = "changed"\n', base)


def test_missing_module_is_reported(tmp_path):
    with pytest.raises(BunTypeError, match="cannot load module"):
        check('import * as m from "./nope.bun"\nprint(m.x)\n',
              str(tmp_path))


def test_circular_namespace_import_is_a_type_error(tmp_path):
    write(tmp_path / "a.bun",
          'import * as b from "./b.bun"\n'
          "export fn fa() { return b.fb() }\n")
    write(tmp_path / "b.bun",
          'import * as a from "./a.bun"\n'
          "export fn fb() { return 7 }\n")
    with pytest.raises(BunTypeError, match="circular import"):
        check('import * as a from "./a.bun"\nprint(a.fa())\n',
              str(tmp_path))


def test_namespace_alias_cannot_be_reassigned(tmp_path):
    base = fixture(tmp_path)
    with pytest.raises(BunTypeError, match="cannot assign"):
        check('import * as m from "./m.bun"\nm = 5\n', base)


def test_exports_are_not_flattened_into_scope(tmp_path):
    base = fixture(tmp_path)
    with pytest.raises(BunTypeError, match="undefined variable 'add'"):
        check('import * as m from "./m.bun"\nprint(add(1, 2))\n', base)


@pytest.mark.parametrize("source", [
    'import * from "./m.bun"\n',
    'import * as from "./m.bun"\n',
    'import * as m "./m.bun"\n',
])
def test_malformed_namespace_import_is_a_parse_error(source):
    with pytest.raises(ParseError):
        Parser(Lexer(source).tokenize()).parse()


def test_import_operand_two_element_form_is_still_accepted():
    assert ops.unpack_import(("./m.bun", ["a"])) == ("./m.bun", ["a"], None)
    assert ops.unpack_import(("./m.bun", [], "ns")) == ("./m.bun", [], "ns")


def test_namespace_value_is_a_struct_with_the_exports():
    ns = ops.module_namespace({"a": 1, "b": 2}, "./m.bun")
    assert ns.type_name == "module:./m.bun"
    assert ops.get_field(ns, "a") == 1
    assert ops.get_field(ns, "b") == 2


def test_c_backend_refuses_namespace_imports_by_name():
    source = 'import * as m from "./m.bun"\nprint(m.greeting)\n'
    program = Parser(Lexer(source).tokenize()).parse()
    # `tests/test_cbackend.py` reloads bun.cbackend while testing its build
    # cache, which replaces the exception class object. Resolve both the
    # class and the function through the module at call time, so this test
    # keeps working no matter which order pytest collects the files in.
    with pytest.raises(cbackend.CBackendError, match="namespace imports"):
        cbackend.check_builtins(program)


def test_c_backend_cli_path_refuses_namespace_imports(tmp_path):
    # The real `--engine c` path, not just the check_builtins helper: the
    # refusal must happen before any C is written or compiled.
    base = fixture(tmp_path)
    with pytest.raises(cbackend.CBackendError, match="namespace imports"):
        run('import * as m from "./m.bun"\nprint(m.add(1, 2))\n',
            base, engine="c")


def test_c_backend_accepts_a_plain_import():
    source = 'import { a } from "./m.bun"\nprint(a)\n'
    program = Parser(Lexer(source).tokenize()).parse()
    cbackend.check_builtins(program)


def test_selfhost_front_end_agrees(tmp_path, capsys):
    base = fixture(tmp_path)
    write(tmp_path / "main.bun",
          'import * as m from "./m.bun"\n'
          "print(m.add(2, 3))\n"
          "print(m.greeting)\n"
          "print(m.scale(7))\n"
          "print(m.add(10, 5))\n")
    run_file(os.path.join(base, "main.bun"), front_end="bun")
    assert capsys.readouterr().out == "5\nnamaste\n21\n15\n"


@pytest.mark.parametrize("source,message", [
    ('import * as m from "./m.bun"\nprint(m.typo)\n',
     "does not export 'typo'"),
    ('import * as m from "./m.bun"\nprint(m.typo(1))\n',
     "does not export 'typo'"),
    ('import * as m from "./m.bun"\nprint(m.add(1))\n',
     "expects 2 argument"),
    ('import * as m from "./m.bun"\nm.greeting = "x"\n',
     "cannot assign to a field"),
])
def test_selfhost_checker_matches_python_checker(tmp_path, source, message):
    # Both front ends must reject the program STATICALLY, with the same
    # message. A run-time "unknown field" would not satisfy this test.
    base = fixture(tmp_path)
    with pytest.raises(BunTypeError, match=message):
        check(source, base)
    path = tmp_path / "main.bun"
    write(path, source)
    with pytest.raises(BunTypeError, match=message):
        run_front_end(str(path), mode="check", check=True)


def test_selfhost_checker_accepts_a_valid_namespace_program(tmp_path):
    fixture(tmp_path)
    path = tmp_path / "main.bun"
    write(path, 'import * as m from "./m.bun"\n'
                "print(m.add(2, 3))\n"
                "print(m.greeting)\n")
    # No exception means the self-hosted checker accepted the program.
    run_front_end(str(path), mode="check", check=True)
