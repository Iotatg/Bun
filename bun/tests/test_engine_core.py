"""Tests of the 0.5.0 wave: two native engines.

`bun --engine wasm` builds a binary WebAssembly module and runs it on
Bun's own machine (`bun/wasmvm.py`).  `bun --engine jit` emits x86-64
machine code and calls it.  Both run one subset — the integer core — and
both refuse a program outside it by name.

The tests check the real artefacts: the bytes of the module, the sections
of the binary, the machine code's answer, and the parity of the two
engines with the virtual machine on the same programs.  A program outside
the core must be refused with a message that names the engine, never
silently miscompiled.
"""

import io
import os
import shutil
import subprocess
import sys
from contextlib import redirect_stdout

import pytest

from bun import jit, wasm, wasmvm
from bun.cli import run_source
from bun.errors import BunError
from bun.intcore import Unsupported
from bun.lexer import Lexer
from bun.parser import Parser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "tools", "maturity", "engine_core.bun")


def run_engine(source, engine):
    """Run a program on one engine and answer its output."""
    captured = io.StringIO()
    with redirect_stdout(captured):
        run_source(source, filename="<test>.bun", check=True, engine=engine)
    return captured.getvalue()


def parity(source):
    """The three engines must agree on a program of the core."""
    outputs = [run_engine(source, engine)
               for engine in ("vm", "wasm", "jit")]
    assert len(set(outputs)) == 1, outputs
    return outputs[0]


PROGRAM = (
    "fn gcd(a: int, b: int) -> int {\n"
    "    while b != 0 {\n"
    "        let t = b\n"
    "        b = a % b\n"
    "        a = t\n"
    "    }\n"
    "    return a\n"
    "}\n"
    "var total = 0\n"
    "for i in range(1, 11) {\n"
    "    total = total + i * i\n"
    "}\n"
    "print(gcd(48, 18))\n"
    "print(total)\n"
    "print(\"engine\")\n"
    "print(true and false)\n"
)


# ---------------------------------------------------------------------------
# The WASM backend and Bun's own WebAssembly machine
# ---------------------------------------------------------------------------

def test_the_module_starts_with_the_webassembly_magic():
    program = Parser(Lexer(PROGRAM).tokenize()).parse()
    data = wasm.compile_program(program)
    assert data[:4] == b"\x00asm"
    assert data[4:8] == b"\x01\x00\x00\x00"


def test_the_module_decodes_into_the_sections_it_needs():
    program = Parser(Lexer(PROGRAM).tokenize()).parse()
    module = wasmvm.decode(wasm.compile_program(program))
    assert module.types
    assert len(module.functions) >= 2
    assert [item[1] for item in module.imports] == [
        "print_i64", "print_bool", "print_str"]
    assert "main" in module.exports
    assert "memory" in module.exports
    assert module.data


def test_the_wasm_engine_runs_the_program(capsys):
    assert run_engine(PROGRAM, "wasm") == "6\n385\nengine\nfalse\n"


def test_the_wasm_machine_refuses_a_module_that_is_not_wasm():
    with pytest.raises(wasmvm.WasmError, match="magic"):
        wasmvm.decode(b"not a module at all")


def test_the_wasm_machine_refuses_an_unknown_instruction():
    module = wasmvm.Module()
    module.types = [([], [wasmvm.I64])]
    function = wasmvm.Function(0, [], b"")
    function.code = [(0xFC, None)]          # a prefix this machine has not
    module.functions = [function]
    module.exports = {"main": (0, 0)}
    with pytest.raises(wasmvm.WasmError, match="unknown instruction"):
        wasmvm.run_module(module, "main")


def test_compile_target_wasm_writes_a_binary_module(tmp_path):
    source = tmp_path / "small.bun"
    source.write_text("print(7 * 6)\n")
    result = subprocess.run(
        [sys.executable, "-m", "bun", "compile", "--target", "wasm",
         str(source)],
        capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr
    target = tmp_path / "small.wasm"
    assert target.exists()
    assert target.read_bytes()[:4] == b"\x00asm"
    assert "0061736d" in result.stdout


@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node is not installed")
def test_v8_accepts_the_module_and_runs_it(tmp_path):
    """The module is not merely ours: V8 validates it and runs it."""
    source = tmp_path / "small.bun"
    source.write_text("fn twice(n: int) -> int {\n    return n * 2\n}\n"
                      "print(twice(21))\n")
    subprocess.run(
        [sys.executable, "-m", "bun", "compile", "--target", "wasm",
         str(source)], check=True, capture_output=True, cwd=ROOT)
    script = (
        "const fs = require('fs');"
        "const b = fs.readFileSync(process.argv[1]);"
        "if (!WebAssembly.validate(b)) { process.exit(1); }"
        "const out = [];"
        "const i = new WebAssembly.Instance(new WebAssembly.Module(b),"
        " {env: {print_i64: v => out.push(String(v)),"
        " print_bool: v => out.push(v ? 'true' : 'false'),"
        " print_str: (p, n) => out.push('')}});"
        "i.exports.main();"
        "process.stdout.write(out.join('\\n'));")
    result = subprocess.run(["node", "-e", script,
                             str(tmp_path / "small.wasm")],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "42"


# ---------------------------------------------------------------------------
# The x86-64 JIT
# ---------------------------------------------------------------------------

def test_the_jit_runs_the_program(capsys):
    assert run_engine(PROGRAM, "jit") == "6\n385\nengine\nfalse\n"


def test_the_jit_emits_machine_code_not_a_closure():
    program = Parser(Lexer("print(1 + 1)\n").tokenize()).parse()
    machine = jit.Jit(program).compile()
    assert machine.buffer
    # `mov rbp, rsp` and `leave` are the frame of a real native function.
    assert bytes([0x48, 0x89, 0xE5]) in machine.buffer
    assert bytes([0xC9, 0xC3]) in machine.buffer


def test_the_jit_answers_the_value_of_a_function():
    program = Parser(Lexer(
        "fn add(a: int, b: int) -> int {\n    return a + b\n}\n"
        "print(add(20, 22))\n").tokenize()).parse()
    assert jit.run_program(program) == 0


# ---------------------------------------------------------------------------
# The core: what both engines agree on, and what they refuse
# ---------------------------------------------------------------------------

def test_the_three_engines_agree_on_the_fixture():
    with open(FIXTURE) as handle:
        source = handle.read()
    assert parity(source) == "6\n385\n"


def test_the_three_engines_agree_on_arithmetic_and_loops():
    source = (
        "print(-7 div 2)\n"
        "print(-7 % 2)\n"
        "print(7 div -2)\n"
        "print(1 << 4)\n"
        "print(255 >> 4)\n"
        "print(3 and 5)\n"
        "print(0 or 7)\n"
        "var i = 0\n"
        "while i < 3 {\n"
        "    print(i)\n"
        "    i = i + 1\n"
        "}\n")
    assert parity(source) == "-4\n1\n-4\n16\n15\n5\n7\n0\n1\n2\n"


def test_the_three_engines_agree_on_named_breaks():
    source = (
        "fn find(limit: int) -> int {\n"
        "    var found = -1\n"
        "    for i in range(limit) as outer {\n"
        "        for j in range(limit) {\n"
        "            if i * j == 12 {\n"
        "                found = i * 100 + j\n"
        "                break outer\n"
        "            }\n"
        "        }\n"
        "    }\n"
        "    return found\n"
        "}\n"
        "print(find(10))\n")
    assert parity(source) == "206\n"


@pytest.mark.parametrize("source,engine", [
    ("let xs = [1, 2]\nprint(len(xs))\n", "wasm"),
    ("let xs = [1, 2]\nprint(len(xs))\n", "jit"),
    ("let x = 1.5\nprint(x)\n", "wasm"),
    ("let x = 1.5\nprint(x)\n", "jit"),
    ("print(\"a\" + \"b\")\n", "wasm"),
    ("print(\"a\" + \"b\")\n", "jit"),
])
def test_an_engine_refuses_what_it_does_not_run(source, engine):
    with pytest.raises(Unsupported) as failure:
        run_engine(source, engine)
    assert engine in str(failure.value)
    assert "--engine vm" in str(failure.value)


def test_the_refusal_is_a_bun_error_with_a_position():
    with pytest.raises(BunError) as failure:
        run_engine("print(1)\nlet xs = [1]\nprint(len(xs))\n", "jit")
    assert failure.value.line == 2
    # The refusal happens while lowering, not while running: Unsupported is
    # a BunError, deliberately not a BunRuntimeError.  It still carries the
    # source position of the construct the engine cannot emit.
    assert isinstance(failure.value, Unsupported)


# ---------------------------------------------------------------------------
# The command line and the engine list
# ---------------------------------------------------------------------------

def test_the_engine_list_reports_both_engines_as_available():
    result = subprocess.run(
        [sys.executable, "-m", "bun", "engines", "--json"],
        capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0
    import json
    data = json.loads(result.stdout)
    status = {item["name"]: item["status"] for item in data["engines"]}
    assert status["wasm"] == "available"
    assert status["jit"].startswith("available")


def test_the_command_line_runs_the_fixture_on_both_engines():
    for engine in ("wasm", "jit"):
        result = subprocess.run(
            [sys.executable, "-m", "bun", "--engine", engine, FIXTURE],
            capture_output=True, text=True, cwd=ROOT)
        assert result.returncode == 0, result.stderr
        assert result.stdout == "6\n385\n"


def test_an_unknown_engine_is_still_refused():
    result = subprocess.run(
        [sys.executable, "-m", "bun", "--engine", "brainfuck", FIXTURE],
        capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 2
    assert "wasm" in result.stderr and "jit" in result.stderr
