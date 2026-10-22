import pytest

from bun.cli import run_source
from bun.errors import BunError, BunRuntimeError, BunTypeError
from bun.interpreter import Interpreter
from bun.parser import parse


def run(source, base_dir):
    return run_source(source, filename=base_dir + "/main.bun")


def write(path, text):
    with open(path, "w") as handle:
        handle.write(text)


def test_import_function(tmp_path):
    write(str(tmp_path / "math.bun"),
          "export fn double(x) {\n    return x * 2\n}\n")
    env = run('import { double } from "./math"\nlet r = double(21)',
              str(tmp_path))
    assert env.get("r") == 42


def test_import_value(tmp_path):
    write(str(tmp_path / "cfg.bun"), 'export let answer = 42\n')
    env = run('import { answer } from "./cfg"\nlet r = answer', str(tmp_path))
    assert env.get("r") == 42


def test_module_cached_runs_once(tmp_path):
    write(str(tmp_path / "state.bun"),
          "var loads = 0\nloads = loads + 1\nexport fn get_loads() {\n"
          "    return loads\n}\n")
    write(str(tmp_path / "user.bun"),
          'import { get_loads } from "./state"\nexport fn load_count() {\n'
          "    return get_loads()\n}\n")
    env = run('import { load_count } from "./user"\n'
              'import { get_loads } from "./state"\n'
              "let a = load_count()\nlet b = get_loads()",
              str(tmp_path))
    assert env.get("a") == 1
    assert env.get("b") == 1


def test_shared_module_state_across_importers(tmp_path):
    write(str(tmp_path / "counter.bun"),
          "var count = 0\nexport fn bump() {\n    count = count + 1\n"
          "    return count\n}\n")
    write(str(tmp_path / "pass.bun"),
          'import { bump } from "./counter"\nexport fn bumped() {\n'
          "    return bump()\n}\n")
    env = run('import { bump } from "./counter"\n'
              'import { bumped } from "./pass"\n'
              "let a = bump()\nlet b = bumped()",
              str(tmp_path))
    assert env.get("a") == 1
    assert env.get("b") == 2


def test_anonymous_function_closure():
    env = run("fn make() {\n    var n = 0\n    return fn() {\n"
              "        n = n + 1\n        return n\n    }\n}\n"
              "let f = make()\nlet a = f()\nlet b = f()", "/tmp/opencode")
    assert env.get("a") == 1
    assert env.get("b") == 2


def test_missing_module_errors(tmp_path):
    with pytest.raises(BunError):
        run('import { x } from "./nope"', str(tmp_path))


def test_unknown_export_errors(tmp_path):
    write(str(tmp_path / "m.bun"), 'export let a = 1\n')
    with pytest.raises(BunError):
        run('import { b } from "./m"', str(tmp_path))


def test_circular_import_errors(tmp_path):
    write(str(tmp_path / "a.bun"),
          'import { b } from "./b"\nexport let a = 1\n')
    write(str(tmp_path / "b.bun"),
          'import { a } from "./a"\nexport let b = 2\n')
    with pytest.raises(BunError):
        run('import { a } from "./a"', str(tmp_path))


def test_non_relative_path_errors(tmp_path):
    with pytest.raises(BunError):
        run('import { x } from "math"', str(tmp_path))


def test_export_outside_module_errors(tmp_path):
    with pytest.raises(BunRuntimeError):
        run("export let x = 1", str(tmp_path))


def test_export_after_failed_import_errors(tmp_path):
    write(str(tmp_path / "boom.bun"), "let x = missing\n")
    interp = Interpreter()
    with pytest.raises(BunRuntimeError):
        interp.run(parse('import { x } from "./boom"'), base_dir=str(tmp_path))
    assert interp.export_stack == []
    with pytest.raises(BunRuntimeError, match="'export' is only allowed in modules"):
        interp.execute(parse("export let x = 1"), interp.globals)


def test_reassign_import_errors(tmp_path):
    write(str(tmp_path / "m.bun"), "export fn f() {\n    return 1\n}\n")
    with pytest.raises((BunRuntimeError, BunTypeError)):
        run('import { f } from "./m"\nf = fn() {\n    return 2\n}', str(tmp_path))


def test_deferred_import_resolves_against_defining_module(tmp_path, capsys):
    pkg = tmp_path / "pkg"
    app = tmp_path / "app"
    pkg.mkdir()
    app.mkdir()
    write(str(pkg / "lib.bun"), 'export let v = "PKGLIB"\n')
    write(str(pkg / "mid.bun"),
          'export fn go() {\n    import { v } from "./lib"\n    return v\n}\n')
    write(str(app / "lib.bun"), 'export let v = "APPLIB"\n')
    run_source('import { go } from "../pkg/mid"\nprint(go())',
               filename=str(app / "main.bun"))
    assert capsys.readouterr().out == "PKGLIB\n"


def test_import_parent_relative_path(tmp_path):
    write(str(tmp_path / "root.bun"), 'export let v = "ROOT"\n')
    sub = tmp_path / "sub"
    sub.mkdir()
    write(str(sub / "mid.bun"),
          'import { v } from "../root"\nexport let out = v\n')
    env = run_source('import { out } from "./sub/mid"\nlet r = out',
                     filename=str(tmp_path / "main.bun"))
    assert env.get("r") == "ROOT"


def test_non_utf8_module_errors(tmp_path):
    with open(str(tmp_path / "bad.bun"), "wb") as handle:
        handle.write(b"\xff\xfebad")
    with pytest.raises(BunError, match="not valid UTF-8"):
        run('import { x } from "./bad"', str(tmp_path))


def test_module_error_reports_module_frame(tmp_path):
    write(str(tmp_path / "mod.bun"), "export let ok = 1\nprint(missing)\n")
    with pytest.raises(BunRuntimeError) as info:
        run('import { ok } from "./mod"\nprint(ok)', str(tmp_path))
    assert info.value.filename == str(tmp_path / "mod.bun")
    assert info.value.line == 2
    assert "missing" in info.value.source


def test_nested_module_error_keeps_innermost_frame(tmp_path):
    write(str(tmp_path / "inner.bun"), "export let v = 1\nprint(also_missing)\n")
    write(str(tmp_path / "outer.bun"),
          'import { v } from "./inner"\nexport let w = v\n')
    with pytest.raises(BunRuntimeError) as info:
        run('import { w } from "./outer"\nprint(w)', str(tmp_path))
    assert info.value.filename == str(tmp_path / "inner.bun")
    assert info.value.line == 2
