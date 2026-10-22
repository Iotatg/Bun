import glob
import os

import pytest

from bun.checker import Checker
from bun.dict import BunDict
from bun.lexer import Lexer
from bun.cli import main
from bun.compiler import Compiler
from bun.errors import BunError
from bun.parser import Parser
from bun import docs
from bun.selfhost import (
    ast_to_data,
    canonical,
    code_to_data,
    normalize,
    run_front_end,
    token_to_data,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def corpus():
    patterns = [
        os.path.join(ROOT, "tests", "golden", "*.bun"),
        os.path.join(ROOT, "examples", "*.bun"),
        os.path.join(ROOT, "tools", "**", "*.bun"),
        os.path.join(ROOT, "selfhost", "*.bun"),
    ]
    paths = []
    for pattern in patterns:
        paths.extend(glob.glob(pattern, recursive=True))
    return sorted(paths)


def corpus_id(path):
    return os.path.relpath(path, ROOT)


def selfhost_files():
    return sorted(glob.glob(os.path.join(ROOT, "selfhost", "*.bun")))


@pytest.mark.parametrize("path", corpus(), ids=corpus_id)
def test_code_parity(path, capsys):
    source = read(path)
    program = Parser(Lexer(source).tokenize()).parse()
    expected = canonical(code_to_data(Compiler(path, source).compile_program(program)))
    run_front_end(path, "dump", check=False)
    assert capsys.readouterr().out == expected + "\n"


@pytest.mark.parametrize("path", selfhost_files(), ids=corpus_id)
def test_selfhost_compiles_itself(path, capsys):
    source = read(path)
    program = Parser(Lexer(source).tokenize()).parse()
    expected = canonical(code_to_data(Compiler(path, source).compile_program(program)))
    run_front_end(path, "dump", check=False)
    assert capsys.readouterr().out == expected + "\n"


def test_docs_registry_parity(capsys):
    run_front_end(os.path.join(ROOT, "selfhost", "main.bun"), "docs",
                  check=False)
    assert capsys.readouterr().out.strip() == canonical(docs.docs_data())


GOLDEN_DIR = os.path.join(ROOT, "tests", "golden")


def golden_programs():
    return sorted(glob.glob(os.path.join(GOLDEN_DIR, "*.bun")))


@pytest.mark.parametrize("path", golden_programs(), ids=os.path.basename)
def test_execution_parity(path, capsys, tmp_path):
    out_path = path[:-4] + ".out"
    if not os.path.exists(out_path):
        pytest.skip("golden module file, not a program")
    source = read(path)
    expected = read(out_path)
    input_path = path[:-4] + ".in"
    target = path
    if os.path.exists(input_path):
        source = source.replace("__INPUT__", read(input_path).strip())
        target = str(tmp_path / os.path.basename(path))
        with open(target, "w") as handle:
            handle.write(source)
    assert main(["--front-end", "bun", target]) == 0
    assert capsys.readouterr().out == expected


def test_error_parity(capsys, tmp_path):
    program = tmp_path / "boom.bun"
    program.write_text("let xs = []\nlet item = xs[3]\n")
    assert main([str(program)]) == 1
    python_error = capsys.readouterr().err
    assert main(["--front-end", "bun", str(program)]) == 1
    bun_error = capsys.readouterr().err
    assert python_error == bun_error
    assert "Traceback" not in bun_error


def test_static_error_parity(capsys, tmp_path):
    program = tmp_path / "bad.bun"
    program.write_text('let x: int = "s"\nprint("ran")\n')
    assert main([str(program)]) == 1
    python_error = capsys.readouterr().err
    assert main(["--front-end", "bun", str(program)]) == 1
    bun_error = capsys.readouterr().err
    assert python_error == bun_error


def read(path):
    with open(path, "r") as handle:
        return handle.read()


def test_canonical_scalars():
    assert canonical(None) == "null"
    assert canonical(True) == "true"
    assert canonical(False) == "false"
    assert canonical(1) == "1"
    assert canonical(1.5) == "1.5"
    assert canonical("a\nb\t\"c\\\\d") == '"a\\nb\\t\\"c\\\\\\\\d"'


def test_canonical_containers_are_sorted_and_stable():
    assert canonical({"b": 1, "a": [2, 3]}) == '{"a": [2, 3], "b": 1}'
    assert canonical([1, {"b": True}]) == '[1, {"b": true}]'


def test_normalize_converts_bun_dicts_recursively():
    inner = BunDict()
    inner.set("k", [1, 2])
    outer = BunDict()
    outer.set("inner", inner)
    assert normalize(outer) == {"inner": {"k": [1, 2]}}


@pytest.mark.parametrize("path", corpus(), ids=corpus_id)
def test_token_parity(path, capsys):
    source = read(path)
    expected = canonical([token_to_data(token) for token in Lexer(source).tokenize()])
    run_front_end(path, "lex", check=False)
    assert capsys.readouterr().out == expected + "\n"


@pytest.mark.parametrize("path", corpus(), ids=corpus_id)
def test_ast_parity(path, capsys):
    source = read(path)
    program = Parser(Lexer(source).tokenize()).parse()
    expected = canonical(ast_to_data(program))
    run_front_end(path, "ast", check=False)
    assert capsys.readouterr().out == expected + "\n"


def python_check_error(source, base_dir):
    program = Parser(Lexer(source).tokenize()).parse()
    try:
        Checker().check(program, base_dir=base_dir)
    except BunError as error:
        return (error.msg, error.line, error.col)
    return None


def bun_check_error(path):
    try:
        run_front_end(path, "check", check=False)
    except BunError as error:
        return (error.msg, error.line, error.col)
    return None


@pytest.mark.parametrize("path", corpus(), ids=corpus_id)
def test_checker_parity_on_corpus(path):
    source = read(path)
    base_dir = os.path.dirname(os.path.abspath(path))
    assert bun_check_error(path) == python_check_error(source, base_dir)


CHECKER_ERROR_CASES = [
    'let x: int = "hello"',
    'var count: int = 0\ncount = "nope"',
    'fn f() -> int {\n    return "s"\n}',
    'fn f(a: int) -> int {\n    return a\n}\nf("s")',
    'fn f(a: int, b: int) -> int {\n    return a\n}\nf(1)',
    "let x: banana = 5",
    "let x: int = 5\nx(1)",
    "print(1, 2)",
    'let g = fn(a: int) -> int {\n    return a\n}\ng("s")',
    "let h: fn = fn() {}\nh(1)",
    'let x: float = 5\nlet y: int = 5.0',
    'fn f(a: banana) -> int {\n    return a\n}',
    "let n: int = len([1, 2])\nlet s: string = len([1])",
    "break",
    "continue",
    "fn f() {\n    break\n}",
    "if true {\n    continue\n}",
    "for x in [1, 2] {\n    if x == 1 { break }\n}",
    "while true {\n    continue\n}",
    "let x = 1\nx = 2",
    "var x = 1\nx = 2",
    "let x: int = 1\nx = \"nope\"",
    "fn f() {\n    return 1\n}\nf = fn() {\n    return 2\n}",
    'fn f(a: int, b: int = 2) -> int {\n    return a\n}\nf()',
    'fn f(a: int, b: int = 2) -> int {\n    return a\n}\nf(1, 2, 3)',
    'fn f(a: int, b: int = 2) -> int {\n    return a\n}\nf(1, z = 3)',
    'fn f(a: int, b: int = 2) -> int {\n    return a\n}\nf(1, a = 3)',
    'fn f(a: int, b: int = 2) -> int {\n    return a\n}\nf("x")',
    'fn f(a: int, *, token: string) -> string {\n    return token\n}\nf("x")',
    'fn f(a: int, *, token: string) -> string {\n    return token\n}\nf("x", "y")',
    "let a = 1\na, b = [2, 3]",
    "var a = 1\nvar b = 2\n[a, b] = [3, 4]",
    "try {\n    print(1)\n} finally {\n    let x: int = \"s\"\n}",
    "try {\n    print(1)\n} catch e {\n    let y: int = e\n    print(y)\n}",
    "var x: string = secret(\"a\")",
    "print(not_defined)",
    "let x = not_defined",
    "fn f() {\n    return missing_name\n}",
    "fn f() {\n    missing_call()\n}",
    "for item in [1, 2] {\n    print(item)\n}",
    "fn f() {\n    for item in [1, 2] {\n        print(item)\n    }\n}",
    "assert missing_name",
    "assert 1 == 1, missing_name",
    "for a, b in [[1, 2]] {\n    print(missing_name)\n}",
    "fn f() {\n    for a, b in [[1, 2]] {\n        print(a)\n    }\n}",
    "match 1 {\n    1 => print(missing_name),\n}",
    "match 1 {\n    value => print(value),\n}",
    "fn f() {\n    match 1 {\n        1 => print(missing_name),\n    }\n}",
    "@missing\nfn one(a) {\n    return a\n}",
    "let x: int = 5\n@x\nfn one(a) {\n    return a\n}",
]


@pytest.mark.parametrize("source", CHECKER_ERROR_CASES)
def test_checker_error_parity(tmp_path, source):
    path = tmp_path / "prog.bun"
    path.write_text(source)
    assert bun_check_error(str(path)) == python_check_error(source, str(tmp_path))


IMPORT_CASES = [
    (
        {"math.bun": "export fn double(x: int) -> int {\n    return x * 2\n}\n"},
        'import { double } from "./math"\nlet y: int = double(21)',
    ),
    (
        {"math.bun": "export fn double(x: int) -> int {\n    return x * 2\n}\n"},
        'import { double } from "./math"\nlet y: int = double("s")',
    ),
    (
        {"cfg.bun": 'export let name: string = "bun"\n'},
        'import { name } from "./cfg"\nlet n: int = name',
    ),
    (
        {"u.bun": "export let x = 1\n"},
        'import { x } from "./u"\nlet s: string = x',
    ),
    (
        {"cfg.bun": 'export let name: string = "bun"\n'},
        'import { nope } from "./cfg"',
    ),
    ({}, 'import { x } from "./nope"'),
    (
        {"a.bun": 'import { b } from "./b"\nexport let a = 1\n',
         "b.bun": 'import { a } from "./a"\nexport let b = 2\n'},
        'import { a } from "./a"',
    ),
    ({"bad.bun": "let = \n"}, 'import { x } from "./bad"'),
    (
        {"bad.bun": "export let x: banana = 1\n"},
        'import { x } from "./bad"',
    ),
    (
        {"lvl.bun": 'import { inner } from "./inner"\nexport fn outer() -> int {\n    return inner()\n}\n',
         "inner.bun": 'import { nope } from "./missing"\nexport fn inner() -> int {\n    return 1\n}\n'},
        'import { outer } from "./lvl"',
    ),
]


@pytest.mark.parametrize("files,source", IMPORT_CASES)
def test_checker_import_parity(tmp_path, files, source):
    for name, text in files.items():
        (tmp_path / name).write_text(text)
    path = tmp_path / "prog.bun"
    path.write_text(source)
    assert bun_check_error(str(path)) == python_check_error(source, str(tmp_path))


def test_bun_checker_runs_unchecked_program(capsys, tmp_path):
    program = tmp_path / "ok.bun"
    program.write_text('let x: int = "s"\nprint("ran")\n')
    assert main(["--front-end", "bun", "--no-check", str(program)]) == 0
    assert capsys.readouterr().out == "ran\n"
