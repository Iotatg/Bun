import pytest

from bun.checker import Checker
from bun.errors import BunError
from bun.parser import parse


def check(source):
    Checker().check(parse(source))


def test_annotated_program_passes():
    check("fn add(a: int, b: int) -> int {\n    return a + b\n}\n"
          "let x: int = add(1, 2)")


def test_declaration_mismatch_errors():
    with pytest.raises(BunError) as info:
        check('let x: int = "hello"')
    assert info.value.msg == (
        "cannot assign value of type 'string' to variable 'x' of type 'int'")
    assert info.value.line == 1


def test_int_widens_to_float_declaration():
    check("let x: float = 5")


def test_float_not_assignable_to_int():
    with pytest.raises(BunError):
        check("let x: int = 5.0")


def test_null_assignable_to_annotated_declaration():
    check("let x: string = null")


def test_assignment_mismatch_errors():
    with pytest.raises(BunError) as info:
        check('var count: int = 0\ncount = "nope"')
    assert info.value.line == 2


def test_unannotated_is_any():
    check('let x = "hello"\nlet y: int = x')


def test_return_mismatch_errors():
    with pytest.raises(BunError) as info:
        check('fn f() -> int {\n    return "s"\n}')
    assert "cannot return value of type 'string'" in info.value.msg
    assert info.value.line == 2


def test_return_null_allowed():
    check("fn f() -> int {\n    return null\n}")


def test_call_argument_type_mismatch_errors():
    with pytest.raises(BunError) as info:
        check('fn f(a: int) -> int {\n    return a\n}\nf("s")')
    assert "not assignable to parameter" in info.value.msg


def test_call_arity_mismatch_errors():
    with pytest.raises(BunError) as info:
        check("fn f(a: int, b: int) -> int {\n    return a\n}\nf(1)")
    assert info.value.msg == (
        "function 'f' expects 2 argument(s), got 1")


def test_forward_reference_call():
    check("fn a() -> int {\n    return b()\n}\nfn b() -> int {\n    return 1\n}\n"
          "let x: int = a()")


def test_unknown_type_name_errors():
    with pytest.raises(BunError) as info:
        check("let x: banana = 5")
    assert info.value.msg == "unknown type 'banana'"


def test_non_callable_identifier_errors():
    with pytest.raises(BunError) as info:
        check("let x: int = 5\nx(1)")
    assert info.value.msg == "'x' of type 'int' is not callable"


def test_fn_typed_parameter_call_allowed():
    check("fn apply(f: fn, v: int) {\n    return f(v)\n}\n"
          "let x = apply(fn(v) { return v }, 2)")


def test_fn_typed_binding_argument_mismatch_errors():
    with pytest.raises(BunError) as info:
        check('let f: fn = fn(a: int) -> int {\n    return a\n}\nf("s")')
    assert "not assignable to parameter" in info.value.msg


def test_unannotated_fn_binding_keeps_signature():
    with pytest.raises(BunError) as info:
        check('let g = fn(a: int) -> int {\n    return a\n}\ng("s")')
    assert "not assignable to parameter" in info.value.msg


def test_fn_typed_binding_arity_mismatch_errors():
    with pytest.raises(BunError) as info:
        check("let h: fn = fn() {}\nh(1)")
    assert info.value.msg == "function 'h' expects 0 argument(s), got 1"


def test_fn_typed_binding_positive():
    check('let ok: fn = fn(a: int) -> int {\n    return a\n}\n'
          "let r: int = ok(1)")


def test_builtin_len_returns_int():
    check("let n: int = len([1, 2])")


def test_builtin_arg_type_mismatch_errors():
    with pytest.raises(BunError):
        check('let s: string = len([1])')


def test_builtin_arity_error():
    with pytest.raises(BunError) as info:
        check("len(1, 2)")
    assert "len()" in info.value.msg


def test_range_both_arities():
    check("let a: list = range(5)\nlet b: list = range(0, 5)")


def test_list_and_dict_literal_annotations():
    check('let xs: list = [1, 2, 3]\nlet d: dict = {"a": 1}')


def test_operators_unchecked():
    check("let x: string = 1 + 2")


def test_method_calls_unchecked():
    check('let s: int = "a, b".split(",")[0]')


def test_block_scope_assignment():
    check("fn f() -> int {\n    var x: int = 1\n    if true {\n        x = 2\n    }\n"
          "    return x\n}")


def test_anonymous_fn_return_checked():
    with pytest.raises(BunError):
        check('let f = fn() -> int {\n    return "s"\n}')


def write(path, text):
    with open(path, "w") as handle:
        handle.write(text)


def test_imported_fn_argument_mismatch_errors(tmp_path):
    write(str(tmp_path / "math.bun"),
          "export fn double(x: int) -> int {\n    return x * 2\n}\n")
    program = parse('import { double } from "./math"\nlet y: int = double("s")')
    with pytest.raises(BunError):
        Checker().check(program, base_dir=str(tmp_path))


def test_imported_fn_positive(tmp_path):
    write(str(tmp_path / "math.bun"),
          "export fn double(x: int) -> int {\n    return x * 2\n}\n")
    program = parse('import { double } from "./math"\nlet y: int = double(21)')
    Checker().check(program, base_dir=str(tmp_path))


def test_imported_value_type_known(tmp_path):
    write(str(tmp_path / "cfg.bun"), 'export let name: string = "bun"\n')
    program = parse('import { name } from "./cfg"\nlet n: int = name')
    with pytest.raises(BunError):
        Checker().check(program, base_dir=str(tmp_path))


def test_imported_unannotated_is_any(tmp_path):
    write(str(tmp_path / "u.bun"), "export let x = 1\n")
    program = parse('import { x } from "./u"\nlet s: string = x')
    Checker().check(program, base_dir=str(tmp_path))


def test_missing_module_type_error(tmp_path):
    program = parse('import { x } from "./nope"')
    with pytest.raises(BunError):
        Checker().check(program, base_dir=str(tmp_path))


def test_circular_import_type_error(tmp_path):
    write(str(tmp_path / "a.bun"), 'import { b } from "./b"\nexport let a = 1\n')
    write(str(tmp_path / "b.bun"), 'import { a } from "./a"\nexport let b = 2\n')
    program = parse('import { a } from "./a"')
    with pytest.raises(BunError) as info:
        Checker().check(program, base_dir=str(tmp_path))
    assert "circular" in info.value.msg


def test_module_syntax_error_wrapped(tmp_path):
    write(str(tmp_path / "bad.bun"), "let = \n")
    program = parse('import { x } from "./bad"')
    with pytest.raises(BunError) as info:
        Checker().check(program, base_dir=str(tmp_path))
    assert "cannot load module" in info.value.msg


def test_module_export_unknown_type_names_module(tmp_path):
    write(str(tmp_path / "bad.bun"), "export let x: banana = 1\n")
    program = parse('import { x } from "./bad"')
    with pytest.raises(BunError) as info:
        Checker().check(program, base_dir=str(tmp_path))
    assert "./bad" in info.value.msg
    assert "unknown type 'banana'" in info.value.msg


def test_try_catch_passes():
    check('try {\n    throw "x"\n} catch e {\n    print(e)\n}')


def test_catch_param_is_any_typed():
    check('try {\n    let x: int = 1\n} catch e {\n    let y: string = e\n'
          '    let z: int = e\n}')


def test_throw_non_string_value_passes():
    check('try {\n    throw 42\n} catch {\n}')
