"""The tests of the tiers of the machine.

Bun has three engines and one tier on top of the newest one:

- the tree engine, which walks the syntax tree;
- the stack VM, which is the reference semantics of the language;
- the register VM, which runs the same program with the values in the
  registers of a frame;
- the superinstruction tier, which fuses the pairs of loads of the
  register code.

The rule of the phase: a program that prints something different under
another engine is a bug in the tier, never a difference in the language.
"""

import io
import os
import contextlib

import pytest

from bun.cli import run_source
from bun.compiler import Compiler
from bun.lexer import Lexer
from bun.parser import Parser
from bun import regcode
from bun.regcode import REGISTER_COUNT
from bun.regcompile import registerize
from bun.regfuse import count_fused, count_pairs, fuse
from bun.regverify import VerifyError, verify_program

GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "golden")

PROGRAM = """
fn twice(n) {
    return n * 2
}

let numbers = [1, 2, 3]
let doubled = [twice(n) for n in numbers]
var total = 0
for n in doubled {
    total = total + n
}
print("total " + str(total))

let table = { "a": 1, "b": 2 }
for key in table {
    print(key + "=" + str(table[key]))
}

match total {
    12 => { print("twelve") }
    _ => { print("other") }
}

try {
    throw "boom"
} catch err {
    print("caught " + err)
}
"""

ENGINES = [
    ("tree", False),
    ("vm", False),
    ("register", False),
    ("register", True),
]


def _run(engine, tier):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        run_source(PROGRAM, filename="<tiers>", check=True, engine=engine,
                   tier=tier)
    return buffer.getvalue()


def _register_code(source=PROGRAM):
    program = Parser(Lexer(source).tokenize()).parse()
    code = Compiler("<tiers>", source).compile_program(program)
    return registerize(code)


@pytest.mark.parametrize("engine,tier", ENGINES,
                         ids=["tree", "vm", "register", "tier"])
def test_every_tier_prints_the_same(engine, tier):
    expected = "total 12\na=1\nb=2\ntwelve\ncaught boom\n"
    assert _run(engine, tier) == expected


def test_the_tiers_agree_on_the_golden_corpus():
    for name in sorted(os.listdir(GOLDEN_DIR)):
        if not name.endswith(".bun"):
            continue
        path = os.path.join(GOLDEN_DIR, name)
        out_path = path[:-4] + ".out"
        if not os.path.exists(out_path):
            continue
        with open(path, "r") as handle:
            source = handle.read()
        with open(out_path, "r") as handle:
            wanted = handle.read()
        input_path = path[:-4] + ".in"
        if os.path.exists(input_path):
            with open(input_path, "r") as handle:
                source = source.replace("__INPUT__", handle.read().strip())
        for tier in (False, True):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                run_source(source, filename=path, check=True,
                           engine="register", tier=tier)
            assert buffer.getvalue() == wanted, name


def test_the_fusion_makes_the_code_shorter():
    code = _register_code()
    fused = fuse(code)
    assert len(fused["code"]) < len(code["code"])


def test_the_fused_code_passes_the_verifier():
    code = _register_code()
    verify_program(code)
    fused = fuse(code)
    verify_program(fused)


def test_the_fusion_only_touches_the_loads():
    code = _register_code()
    counts = count_pairs(code)
    assert counts
    fused = fuse(code)
    made = count_fused(fused)
    # The count is the number of pairs that sit next to each other, and
    # the fusion only takes the ones that are safe to take.
    assert 0 < made <= sum(counts.values())


def test_the_register_file_is_big_enough():
    assert REGISTER_COUNT >= 32


def test_the_verifier_refuses_a_register_that_is_not_live():
    code = _register_code()
    instructions = list(code["code"])
    for index, instruction in enumerate(instructions):
        if instruction[0] == regcode.STORE_NAME:
            # The store of a name reads the register of the value, so a
            # register that is above the depth of the expression is a
            # value that was never written.
            instructions[index] = (regcode.STORE_NAME, 9, instruction[2], 0)
            break
    else:
        raise AssertionError("the program has no store of a name")
    broken = dict(code)
    broken["code"] = instructions
    with pytest.raises(VerifyError):
        verify_program(broken)


def test_every_register_that_is_read_is_live():
    for name in sorted(os.listdir(GOLDEN_DIR)):
        if not name.endswith(".bun"):
            continue
        path = os.path.join(GOLDEN_DIR, name)
        with open(path, "r") as handle:
            source = handle.read()
        code = _register_code(source)
        for object_ in _code_objects(code):
            depths = object_.get("depths", [])
            for index, instruction in enumerate(object_.get("code", [])):
                if index >= len(depths):
                    continue
                for slot in regcode.read_slots(object_, instruction):
                    assert slot < depths[index], (name, index, instruction)


def _code_objects(code):
    """A code object and every function it holds."""
    yield code
    for value in code.get("consts", []):
        if isinstance(value, dict) and "code" in value:
            for nested in _code_objects(value):
                yield nested

