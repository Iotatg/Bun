"""The tests of the native backend.

The backend turns the register code of a program into C and leaves the
work to the compiler of the system.  The rule of the phase is the same
as the rule of the register tier: a program that prints something
different under the native backend is a bug in the backend, never a
difference in the language.

The backend refuses what it cannot translate, and it refuses it by name
at compile time, so that the program does not fail later with a
confusing message.
"""

import os
import shutil
import subprocess

import pytest

from bun import cbackend
from bun.cli import NativeExit, run_source
from bun.compiler import Compiler
from bun.errors import BunError, format_error
from bun.lexer import Lexer
from bun.parser import Parser
from bun.regcompile import registerize
from bun.regverify import verify_program

GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "golden")

PROGRAM = """
fn fib(n) {
    if n < 2 {
        return n
    }
    return fib(n - 1) + fib(n - 2)
}

let numbers = [1, 2, 3, 4]
let table = { "a": 1, "b": 2 }
var total = 0

for n in numbers {
    total = total + n
}
print("total " + str(total))

for key in table {
    print(key + "=" + str(table[key]))
}

print(f"fib {fib(10)}")
print(f"pct {0.5:.1%}")
print(f"pad [{42:>5}]")

try {
    throw "boom"
} catch err {
    print("caught " + err)
}
"""


def _has_compiler():
    return shutil.which("cc") is not None


needs_compiler = pytest.mark.skipif(not _has_compiler(),
                                    reason="no C compiler")


def _compile(source, filename="<cbackend>"):
    compiler = Compiler(filename, source)
    register = registerize(compiler.compile_program(_program(source)))
    verify_program(register)
    return register


def _run_c(source, filename="<cbackend>", capfd=None):
    run_source(source, filename=filename, check=True, engine="c")
    if capfd is None:
        return ""
    return capfd.readouterr().out


def _run_vm(source, filename="<cbackend>", capfd=None):
    run_source(source, filename=filename, check=True, engine="vm")
    if capfd is None:
        return ""
    return capfd.readouterr().out


def _program(source):
    return Parser(Lexer(source).tokenize()).parse()


def _vm_failure(source, capfd, filename="<cbackend>"):
    """The failure of the machine, in the picture of the command line."""
    capfd.readouterr()
    try:
        run_source(source, filename=filename, check=False, engine="vm")
    except BunError as error:
        # The command line prints the picture with a line of its own.
        return format_error(error, source, filename) + "\n"
    return ""


def _c_failure(source, capfd, filename="<cbackend>"):
    """The failure of the backend, in the picture of the command line."""
    capfd.readouterr()
    try:
        run_source(source, filename=filename, check=False, engine="c")
    except NativeExit:
        pass
    except cbackend.CBackendError:
        return ""
    return capfd.readouterr().err


def _refuse(source):
    """The message of the refusal of a program the backend cannot take."""
    program = _program(source)
    cbackend.check_builtins(program)
    code = Compiler("<t>", source).compile_program(program)
    reg = registerize(code)
    with pytest.raises(cbackend.CBackendError) as error:
        cbackend.emit_program(reg)
    return str(error.value)


@needs_compiler
def test_the_backend_prints_the_same_as_the_machine(capfd):
    expected = _run_vm(PROGRAM, capfd=capfd)
    got = _run_c(PROGRAM, capfd=capfd)
    assert got == expected


@needs_compiler
def test_the_backend_agrees_on_the_golden_corpus(capfd):
    """Every program is the same or refused by name."""
    checked = 0
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
        try:
            got = _run_c(source, filename=path, capfd=capfd)
        except cbackend.CBackendError:
            continue
        assert got == wanted, name
        checked += 1
    assert checked > 0


@needs_compiler
def test_no_program_of_the_corpus_prints_something_else(capfd):
    """No program of the corpus is allowed to print something else."""
    different = []
    refused = 0
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
        try:
            got = _run_c(source, filename=path, capfd=capfd)
        except cbackend.CBackendError:
            refused += 1
            continue
        if got != wanted:
            different.append(name)
    assert different == []
    assert refused > 0


@pytest.mark.parametrize("source,name", [
    ("scope {\n    print(1)\n}\n", "scope"),
    ("fn gen() {\n    yield 1\n}\n", "yield"),
])
def test_the_backend_refuses_what_it_cannot_translate(source, name):
    assert name in _refuse(source)


@pytest.mark.parametrize("source,name", [
    ("print(json_stringify({}))\n", "json_stringify"),
    ("print(next([1]))\n", "next"),
])
def test_the_backend_refuses_a_builtin_it_does_not_have(source, name):
    with pytest.raises(cbackend.CBackendError) as error:
        cbackend.check_builtins(_program(source))
    assert name in str(error.value)


def test_a_name_of_the_program_is_not_a_builtin():
    """A name of the program shadows the builtin."""
    source = """
    fn secret(value) {
        return value
    }
    print(secret("x"))
    """
    cbackend.check_builtins(_program(source))


def test_the_list_of_the_builtins_is_the_list_of_the_runtime():
    """The list of the builtins must not drift away from the runtime."""
    import inspect

    import bun.builtins as builtins_module
    source = inspect.getsource(builtins_module)
    names = set()
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped.startswith("env.define("):
            continue
        start = stripped.index('"')
        end = stripped.index('"', start + 1)
        names.add(stripped[start + 1:end])
    assert names == set(cbackend.LANGUAGE_BUILTINS)


@needs_compiler
def test_the_backend_refuses_an_unknown_instruction():
    code = registerize(Compiler("<t>", "print(1)\n").compile_program(
        _program("print(1)\n")))
    code["code"].append(("NO_SUCH_OP", 0, 0, 0))
    with pytest.raises(cbackend.CBackendError) as error:
        cbackend.emit_program(code)
    assert "NO_SUCH_OP" in str(error.value)


@needs_compiler
def test_the_binary_is_built_and_removed():
    code = registerize(Compiler("<t>", "print(1)\n").compile_program(
        _program("print(1)\n")))
    verify_program(code)
    binary, directory = cbackend.build_binary(code, "<t>")
    try:
        assert os.path.exists(binary)
        result = subprocess.run([binary], capture_output=True, text=True)
        assert result.returncode == 0
        assert result.stdout == "1\n"
    finally:
        cbackend.cleanup(directory)
    assert not os.path.exists(directory)


@needs_compiler
def test_the_capture_of_an_error_in_a_caller(capfd):
    """A try in a caller catches the error of a callee."""
    source = """
    fn fail() {
        throw "deep"
    }
    try {
        fail()
    } catch err {
        print("caught " + err)
    }
    """
    assert _run_c(source, capfd=capfd) == "caught deep\n"


@needs_compiler
def test_the_finally_runs_after_an_error(capfd):
    source = """
    var log = []
    try {
        throw "boom"
    } catch err {
        log.push("caught")
    } finally {
        log.push("finally")
    }
    print(log.join(","))
    """
    assert _run_c(source, capfd=capfd) == "caught,finally\n"


@needs_compiler
def test_the_values_of_the_containers(capfd):
    source = """
    let numbers = [3, 1, 2]
    numbers.push(4)
    numbers.sort()
    print(numbers.join("-"))
    let table = { "a": 1 }
    table.set("b", 2)
    print(table.get("b"))
    print(table.has("a"))
    """
    assert _run_c(source, capfd=capfd) == _run_vm(source, capfd=capfd)


@needs_compiler
def test_the_slices_and_the_indexing(capfd):
    source = """
    let numbers = [1, 2, 3, 4, 5]
    print(numbers[1])
    print(numbers[1:3].join(","))
    numbers[0] = 9
    print(numbers.join(","))
    let text = "hello"
    print(text[1:3])
    print(text.upper())
    """
    assert _run_c(source, capfd=capfd) == _run_vm(source, capfd=capfd)


@needs_compiler
def test_the_float_formatting_is_the_same(capfd):
    source = """
    print(0.1 + 0.2)
    print(1.0)
    print(1 / 3)
    print(10 / 2)
    """
    assert _run_c(source, capfd=capfd) == _run_vm(source, capfd=capfd)

# The programs of the differential check.  Every one of them has to print
# the same bytes under the backend and under the machine.
PROGRAMS = [
    # The closures.
    """
    fn outer(n) {
        fn inner(x) {
            return x + n
        }
        return inner
    }
    let add5 = outer(5)
    print(add5(3))
    """,
    # The default parameters and the keyword arguments.
    """
    fn greet(name, greeting = "hello", punct = "!") {
        return greeting + " " + name + punct
    }
    print(greet("world"))
    print(greet("world", "hi"))
    print(greet("world", "hi", "?"))
    """,
    # The variadic parameters.
    """
    fn total(*numbers) {
        var sum = 0
        for n in numbers {
            sum = sum + n
        }
        return sum
    }
    print(total(1, 2, 3))
    """,
    # The comprehensions.
    """
    let numbers = [1, 2, 3, 4]
    print([n * 2 for n in numbers].join(","))
    print([n for n in numbers if n > 2].join(","))
    """,


    # The assignment into a slice.
    """
    var numbers = [1, 2, 3, 4]
    numbers[1:3] = [9, 9]
    print(numbers.join(","))
    """,
    # The string methods.
    """
    let text = "  Hello World  "
    print(text.trim())
    print(text.trim().lower())
    print(text.trim().upper())
    print(text.contains("World"))
    print(text.trim().starts_with("Hello"))
    print(text.trim().ends_with("World"))
    print(text.trim().replace("World", "Bun"))
    print(text.trim().split(" ").join("-"))
    print(text.trim().index_of("World"))
    print(str(len(text)))
    print("ab".repeat(3))
    """,
    # The list methods.
    """
    var numbers = [3, 1, 2]
    numbers.push(4)
    print(numbers.len())
    print(numbers.pop())
    print(numbers.shift())
    print(numbers.join(","))
    print(numbers.contains(2))
    numbers.reverse()
    print(numbers.join(","))
    numbers.sort()
    print(numbers.join(","))
    print(numbers.slice(0, 2).join(","))
    numbers.insert(0, 9)
    print(numbers.join(","))
    numbers.splice(0, 1)
    print(numbers.join(","))
    """,
    # The dict methods.
    """
    var table = { "a": 1 }
    table.set("b", 2)
    print(table.get("b"))
    print(table.has("a"))
    print(table.len())
    print(table.keys().join(","))
    print(table.values().join(","))
    table.update({ "c": 3 })
    print(table.len())
    table.remove("c")
    print(table.len())
    """,
    # The bit operators.
    """
    print(12 & 10)
    print(12 | 10)
    print(12 ^ 10)
    print(~12)
    print(1 << 4)
    print(16 >> 2)
    print(-8 >> 1)
    """,
    # The arithmetic of the signs.
    """
    print(-7 / 2)
    print(7 / 2)
    print(-7 % 3)
    print(7 % 3)
    print(2.5 * 4)
    print(-2.5)
    """,
    # The comparisons and the logic.
    """
    print(1 == 1.0)
    print("a" < "b")
    print([1, 2] == [1, 2])
    print(not true)
    print(true and false)
    print(true or false)
    print(1 != 2)
    """,
    # The nested control flow.
    """
    var count = 0
    for i in [1, 2, 3, 4, 5] {
        if i % 2 == 0 {
            continue
        }
        if i > 3 {
            break
        }
        count = count + i
    }
    print(count)
    """,
    # The while loop with a nested loop.
    """
    var i = 0
    var total = 0
    while i < 5 {
        var j = 0
        while j < 5 {
            total = total + i * j
            j = j + 1
        }
        i = i + 1
    }
    print(total)
    """,
    # The recursion.
    """
    fn fact(n) {
        if n <= 1 {
            return 1
        }
        return n * fact(n - 1)
    }
    print(fact(10))
    """,
    # The mutual recursion.
    """
    fn is_even(n) {
        if n == 0 {
            return true
        }
        return is_odd(n - 1)
    }
    fn is_odd(n) {
        if n == 0 {
            return false
        }
        return is_even(n - 1)
    }
    print(is_even(10))
    print(is_odd(10))
    """,
    # The errors.
    """
    try {
        let numbers = [1]
        print(numbers[5])
    } catch err {
        print("caught " + err)
    }
    try {
        print(1 + "a")
    } catch err {
        print("caught " + err)
    }
    """,
    # The nested try.
    """
    try {
        try {
            throw "inner"
        } catch err {
            print("inner caught " + err)
            throw "outer"
        }
    } catch err {
        print("outer caught " + err)
    }
    """,
    # The finally with a return.
    """
    fn work() {
        try {
            return 1
        } finally {
            print("finally")
        }
    }
    print(work())
    """,
    # The shadowing of a name.
    """
    let value = 1
    fn shadow() {
        let value = 2
        return value
    }
    print(value)
    print(shadow())
    """,
    # The formatting of the values.
    """
    print(1.0)
    print(0.1)
    print(1 / 3)
    print([1, 2])
    print({"a": 1})
    print("text")
    print(true)
    print(null)
    """,
    # The f-string with the parts.
    """
    let name = "world"
    let n = 42
    print(f"hello {name}!")
    print(f"{n} items")
    print(f"escaped {{literal}}")
    print(f"{n * 2}")
    print(f"pi {3.14159:.2f}")
    print(f"pad [{n:>5}]")
    print(f"pad0 [{n:05}]")
    print(f"comma {1234567:,}")
    print(f"hex {255:x}")
    print(f"upper {255:X}")
    print(f"oct {64:o}")
    print(f"bin {5:b}")
    print(f"pct {0.5:.1%}")
    print(f"repr {"quoted"!r}")
    print(f"str {n!s}")
    """,


    # The nested lists.
    """
    let rows = [[1, 2], [3, 4]]
    print(rows[0][1])
    print(rows[1][0])
    rows[0][0] = 9
    print(rows[0].join(","))
    """,
    # The functions that return nothing.
    """
    fn nothing() {
        print("inside")
    }
    nothing()
    """,
    # The loop over a dict and over a list of pairs.
    """
    let table = { "a": 1, "b": 2 }
    for key in table {
        print(key + "=" + str(table[key]))
    }
    let pairs = [["x", 1], ["y", 2]]
    for name, value in pairs {
        print(name + ":" + str(value))
    }
    """,
    # The everyday builtins.
    """
    print(sum([1, 2, 3]))
    print(sum([1.5, 2.5]))
    print(any([0, 1, 0]))
    print(any([]))
    print(all([1, 2]))
    print(all([1, 0]))
    print(all([]))
    print(min([4, 2, 9]))
    print(max([4, 2, 9]))
    print(sorted([3, 1, 2]).join(","))
    print(sorted(["b", "a"]).join(","))
    print(reversed([1, 2, 3]).join(","))
    let pairs = zip([1, 2, 3], ["a", "b"])
    print(pairs.len())
    print(pairs[0][0])
    print(pairs[0][1])
    let numbered = enumerate(["x", "y"])
    print(numbered[0][0])
    print(numbered[1][1])
    """,
    # The comparison of the sorting builtins.
    """
    try {
        print(min([{ "x": 1 }, { "y": 2 }]))
    } catch err {
        print("caught " + err)
    }
    try {
        print(sorted([true, false]))
    } catch err {
        print("caught " + err)
    }
    """,
]

@pytest.mark.parametrize("source", PROGRAMS,
                         ids=[str(index) for index in range(len(PROGRAMS))])
def test_the_backend_agrees_with_the_machine_on_a_program(source, capfd):
    expected = _run_vm(source, capfd=capfd)
    got = _run_c(source, capfd=capfd)
    assert got == expected

SCOPE_PROGRAMS = [
    # A closure that takes a name of the module and a name of its frame.
    """
    let base = 10
    fn make(step) {
        fn inner(x) {
            return x + base + step
        }
        return inner
    }
    let add = make(5)
    print(add(1))
    """,
    # A function that is defined inside a block.
    """
    if true {
        fn helper() {
            return 41
        }
        print(helper())
    }
    """,
    # A closure that changes a name of its frame.
    """
    fn make_counter() {
        var count = 0
        fn bump() {
            count = count + 1
            return count
        }
        return bump
    }
    let counter = make_counter()
    print(counter())
    print(counter())
    """,
    # The shadowing of a name in a nested block.
    """
    let value = 1
    fn shadow() {
        let value = 2
        if true {
            let value = 3
            print(value)
        }
        print(value)
        return value
    }
    print(shadow())
    print(value)
    """,
    # A parameter that hides a name of the module.
    """
    let n = 1
    fn f(n) {
        return n
    }
    print(f(5))
    print(n)
    """,
    # A name that is read before it is defined.
    """
    try {
        print(later)
    } catch err {
        print("caught " + err)
    }
    let later = 1
    """,
    # A default that reads the parameter before it.
    """
    fn pair(a, b = a * 2) {
        return a + b
    }
    print(pair(3))
    """,
    # A name that lives in the body of a loop.
    """
    var total = 0
    for i in [1, 2, 3] {
        let double = i * 2
        total = total + double
    }
    print(total)
    """,
    # A closure that takes the name of a loop.
    """
    fn make() {
        let fns = []
        for i in [1, 2, 3] {
            fn capture() {
                return i
            }
            fns.push(capture)
        }
        return fns
    }
    let fns = make()
    print(fns[0]())
    print(fns[2]())
    """,
    # The scopes that a break and a continue leave.
    """
    var total = 0
    for i in [1, 2, 3, 4, 5] {
        let keep = i * 10
        if i == 3 {
            continue
        }
        if i == 5 {
            break
        }
        total = total + keep
    }
    print(total)
    """,
    # The scopes of a while loop with a break.
    """
    var i = 0
    var total = 0
    while i < 10 {
        let step = i + 1
        if step > 4 {
            break
        }
        total = total + step
        i = i + 1
    }
    print(total)
    """,
    # A function that holds a closure and a try.
    """
    fn work(flag) {
        var seen = 0
        try {
            if flag {
                throw "boom"
            }
            seen = 1
        } catch err {
            seen = 2
        } finally {
            seen = seen + 10
        }
        return seen
    }
    print(work(false))
    print(work(true))
    """,
    # The cases of a match.
    """
    fn describe(value) {
        match value {
            int => print("an int"),
            string => print("a string"),
            [first, second] => print("a pair " + str(first) + "," + str(second)),
            [head, *rest] => print("a list " + str(head) + " and " + str(rest.len())),
            { "name": name } => print("a table of " + name),
            1 to 10 => print("a small number"),
            null => print("nothing"),
            _ => print("something else"),
        }
    }
    describe(5)
    describe("bun")
    describe([1, 2])
    describe([1, 2, 3])
    describe({ "name": "bun" })
    describe(null)
    describe(true)
    """,
    # The guards of a match.
    """
    fn kind(value) {
        match value {
            n if n > 10 => print("big " + str(n)),
            n if n > 0 => print("small " + str(n)),
            _ => print("other"),
        }
    }
    kind(50)
    kind(5)
    kind(-1)
    """,
    # The alternatives of a case.
    """
    match 3 {
        1, 2, 3 => print("small"),
        4 to 9 => print("medium"),
        _ => print("large"),
    }
    """,
    # A pattern binds a name that a function of the module holds.
    """
    fn helper() {
        return 1
    }
    match [7] {
        [helper] => print("bound " + str(helper)),
        _ => print("no"),
    }
    """,
    # A pattern binds a name of a builtin, and the name leaves the case.
    """
    match [1] {
        [min] => print("min is " + str(min)),
        _ => print("no"),
    }
    print(min([3, 1, 2]))
    """,
    # A pattern binds a name in a function, and a closure of it reads the name.
    """
    fn outer(value) {
        match value {
            [first, *rest] => {
                fn inner() {
                    return len(rest)
                }
                return inner()
            }
            _ => return 0
        }
    }
    print(outer([1, 2, 3]))
    """,
    # A name that a closure captures hides the function of the module.
    """
    fn helper() {
        return 1
    }
    fn shadow() {
        fn helper() {
            return 2
        }
        fn inner() {
            return helper()
        }
        print(helper())
        return inner()
    }
    print(shadow())
    print(helper())
    """,
    # A name that a closure captures hides the builtin of the language.
    """
    fn shadow() {
        fn len(text) {
            return 7
        }
        fn inner() {
            return len("abc")
        }
        print(len("abc"))
        return inner()
    }
    print(shadow())
    print(len("abc"))
    """,
]


@pytest.mark.parametrize("source", SCOPE_PROGRAMS,
                         ids=[str(index) for index in range(len(SCOPE_PROGRAMS))])
def test_the_backend_agrees_with_the_machine_on_a_scope(source, capfd):
    """The names of a frame live where the machine keeps them."""
    expected = _run_vm(source, capfd=capfd)
    got = _run_c(source, capfd=capfd)
    assert got == expected


ERROR_PROGRAMS = [
    # The keyword argument of a builtin.
    """
    print(len("abc", y = 1))
    """,
    # The index of a list that is too small.
    """
    let xs = [1, 2, 3]
    print(xs[7])
    """,
    # The division by zero.
    """
    let a = 10
    let b = 0
    print(a / b)
    """,
    # The name that does not exist.
    """
    print(missing_name)
    """,
    # The values that do not fill the names.
    """
    let a, b = [1]
    print(a)
    """,
    # The assertion that does not hold.
    """
    assert 1 == 2, "the promise"
    """,
    # The value that cannot be walked.
    """
    for x in 5 {
        print(x)
    }
    """,
    # The name that is given twice.
    """
    fn f(a: int) -> int {
        return a
    }
    print(f(1, a = 2))
    """,
    # The keyword the function does not have.
    """
    fn f(a: int) -> int {
        return a
    }
    print(f(1, b = 2))
    """,
    # The method that a type does not have.
    """
    let xs = [1, 2]
    print(xs.row())
    """,
]


@pytest.mark.parametrize("source", ERROR_PROGRAMS,
                         ids=[str(index) for index in range(len(ERROR_PROGRAMS))])
def test_the_backend_shows_the_same_failure(source, capfd):
    """A failure of the backend has the picture of a failure of the machine.

    The picture is the message, the place of the source, the caret and the
    advice, and it is the same under the two engines.
    """
    expected = _vm_failure(source, capfd=capfd)
    got = _c_failure(source, capfd=capfd)
    assert expected != ""
    assert got == expected


# The programs of the linker: the program, the module it imports and the
# module the module imports.
LINKED = {
    "main.bun": """
import { add, name } from "./math.bun"
import { twice } from "./twice.bun"
print(add(2, 3))
print(name)
print(twice(21))
""",
    "math.bun": """
export let name = "math"
export fn add(a, b) {
    return a + b
}
""",
    "twice.bun": """
import { add } from "./math.bun"
export fn twice(value) {
    return add(value, value)
}
""",
}


def _write_linked(directory):
    """Write the programs of the linker into a directory."""
    for name, source in LINKED.items():
        path = os.path.join(str(directory), name)
        with open(path, "w") as handle:
            handle.write(source)
    return os.path.join(str(directory), "main.bun")


@needs_compiler
def test_the_backend_links_the_modules_it_imports(tmp_path, capfd):
    """A module is linked into the program of the backend."""
    path = _write_linked(tmp_path)
    expected = _run_vm(LINKED["main.bun"], filename=path, capfd=capfd)
    got = _run_c(LINKED["main.bun"], filename=path, capfd=capfd)
    assert got == expected
    assert expected == "5\nmath\n42\n"


@needs_compiler
def test_the_backend_refuses_a_module_it_cannot_take(tmp_path, capfd):
    """The refusal of a module names the builtin the backend does not have."""
    path = os.path.join(str(tmp_path), "main.bun")
    source = "import { thing } from \"./module.bun\"\nprint(thing)\n"
    with open(path, "w") as handle:
        handle.write(source)
    with open(os.path.join(str(tmp_path), "module.bun"), "w") as handle:
        handle.write("export fn thing() {\n"
                     "    return json_stringify({})\n"
                     "}\n")
    program = _program(source)
    code = registerize(Compiler(path, source).compile_program(program))
    with pytest.raises(cbackend.CBackendError) as error:
        cbackend.emit_program(code, path, source)
    assert "json_stringify" in str(error.value)


@needs_compiler
def test_the_backend_shows_a_module_that_does_not_export_a_name(tmp_path, capfd):
    """The name a module does not export is the same in the two engines."""
    path = os.path.join(str(tmp_path), "main.bun")
    source = "import { missing } from \"./module.bun\"\nprint(missing)\n"
    with open(path, "w") as handle:
        handle.write(source)
    with open(os.path.join(str(tmp_path), "module.bun"), "w") as handle:
        handle.write("export fn thing() {\n    return 1\n}\n")
    expected = _vm_failure(source, capfd=capfd, filename=path)
    got = _c_failure(source, capfd=capfd, filename=path)
    assert expected != ""
    assert got == expected


@needs_compiler
def test_the_backend_has_the_everyday_builtins(capfd):
    """The backend translates the builtins that a program uses first."""
    source = """
    print(sum([1, 2]))
    print(sorted([2, 1]).join(","))
    print(reversed([1, 2]).join(","))
    print(enumerate(["a"])[0][0])
    print(zip([1], [2])[0][1])
    print(any([true]))
    print(all([true]))
    """
    expected = _run_vm(source, capfd=capfd)
    got = _run_c(source, capfd=capfd)
    assert got == expected


def test_the_cache_reuses_the_binary(tmp_path, monkeypatch, capfd):
    monkeypatch.setenv("BUN_CACHE_DIR", str(tmp_path / "cache"))
    import importlib
    import bun.cbackend as cbackend
    importlib.reload(cbackend)
    source = "print('cached')\n"
    code = _compile(source)
    first, directory = cbackend.build_binary(code, "cached.bun")
    assert os.path.exists(first)
    assert cbackend.is_cached(directory)
    second, again = cbackend.build_binary(code, "cached.bun")
    assert second == first
    assert again == directory


def test_the_cache_key_covers_the_source(tmp_path, monkeypatch):
    monkeypatch.setenv("BUN_CACHE_DIR", str(tmp_path / "cache"))
    import importlib
    import bun.cbackend as cbackend
    importlib.reload(cbackend)
    assert cbackend.cache_key("print(1)\n", "cc") != cbackend.cache_key(
        "print(2)\n", "cc")
    assert cbackend.cache_key("print(1)\n", "cc") != cbackend.cache_key(
        "print(1)\n", "clang")


def _c_source(source, filename="<cbackend>"):
    """The C that the backend writes for a program."""
    code = _compile(source, filename)
    text, _ = cbackend.emit_program(code, filename, source)
    return text


def _cached_names(source, filename="<cbackend>"):
    """The names of a program that the backend keeps in a static."""
    code = _compile(source, filename)
    emitter = cbackend.CEmitter(code, filename, source)
    emitter.collect(code, 0)
    emitter.collect_modules()
    emitter.prepare_params()
    emitter.collect_plans()
    emitter.analyse_globals()
    return set(name for _, name in emitter.static_globals)


def test_the_registers_of_a_function_are_plain_variables():
    """The registers of a function that catches no error are variables.

    A variable lives in the registers of the machine, and an array lives
    in the memory, so a loop over an array writes to the memory on every
    step.
    """
    text = _c_source("print(1)\n")
    assert "BunValue r0" in text
    assert "BunValue regs[" not in text


def test_the_registers_of_a_function_that_catches_an_error_live_in_the_memory():
    """A function that catches an error keeps its frame in the memory.

    The error jumps into the frame of the function, and the values of an
    automatic object would be lost by the jump.
    """
    text = _c_source("try {\n    print(1)\n} catch err {\n    print(err)\n}\n")
    assert "BunValue *regs" in text


def test_a_name_that_never_changes_is_read_from_a_static():
    """A name of the module that never changes is read from a variable.

    The lookup of a name in the environment is the most expensive part of
    a call, and a name that the program defines once and never changes
    does not have to be looked up.  The name has to live in the
    environment, and a name that a closure of the module reads lives
    there.
    """
    assert _cached_names("fn helper(n) {\n    return helper(n - 1)\n}\n"
                         "print(helper(3))\n") == {"helper"}


def test_a_name_that_changes_is_not_read_from_a_static():
    """A name that the program assigns is looked up every time."""
    names = _cached_names("fn helper(n) {\n    return helper(n - 1)\n}\n"
                          "fn caller() {\n    helper = 2\n    return helper\n}\n"
                          "print(caller())\n")
    assert "helper" not in names


def test_a_name_that_is_defined_twice_is_not_read_from_a_static():
    """A name that the program defines twice is looked up every time."""
    names = _cached_names("fn helper(n) {\n    return helper(n - 1)\n}\n"
                          "fn helper(n) {\n    return helper(n - 2)\n}\n"
                          "print(helper(1))\n")
    assert "helper" not in names


def test_a_name_that_is_removed_is_not_read_from_a_static():
    """A name that the program removes is looked up every time."""
    names = _cached_names("fn helper(n) {\n    return helper(n - 1)\n}\n"
                          "del helper\n"
                          "print(1)\n")
    assert "helper" not in names


def test_a_name_that_is_shadowed_is_not_read_from_a_static():
    """A name that an enclosing function binds is the name of that function."""
    source = ("fn helper(n) {\n    return helper(n - 1)\n}\n"
              "fn outer() {\n    let helper = 5\n"
              "    return helper\n}\n"
              "print(outer())\n")
    assert "helper" in _cached_names(source)
    text = _c_source(source)
    # The function that binds the name reads it from its own frame, and
    # the name of the module is only read by the function itself.
    assert text.count("bun_static_0") == 3


@needs_compiler
def test_the_backend_agrees_with_the_machine_on_a_name_that_never_changes(capfd):
    """A name that the backend caches prints what the machine prints."""
    source = """
    fn helper(n) {
        return n + 1
    }
    fn caller(n) {
        return helper(n)
    }
    print(caller(1))
    print(caller(2))
    """
    expected = _run_vm(source, capfd=capfd)
    got = _run_c(source, capfd=capfd)
    assert got == expected


def test_a_call_of_a_known_name_is_a_direct_call():
    """A call of a name that never changes is a call of the C function.

    The compiler of the system sees which function is called, so it can
    inline the call and keep the arguments in the registers.
    """
    source = ("fn helper(n) {\n    return helper(n - 1)\n}\n"
              "print(helper(3))\n")
    text = _c_source(source)
    assert "bun_static_env_0" in text
    # The call of the function itself is a call of the C function.
    assert "bun_fn_1(callee_env" in text


def test_a_call_of_an_unknown_name_is_not_a_direct_call():
    """A call of a name that the program changes is a call of the value."""
    source = ("fn helper(n) {\n    return n + 1\n}\n"
              "fn caller(n) {\n    helper = helper\n    return helper(n)\n}\n"
              "print(caller(3))\n")
    text = _c_source(source)
    assert "bun_fn_1(callee_env" not in text


@needs_compiler
def test_the_backend_agrees_with_the_machine_on_a_recursive_function(capfd):
    """A function that calls itself prints what the machine prints."""
    source = """
    fn fact(n) {
        if n <= 1 {
            return 1
        }
        return n * fact(n - 1)
    }
    print(fact(10))
    """
    expected = _run_vm(source, capfd=capfd)
    got = _run_c(source, capfd=capfd)
    assert got == expected


def test_the_names_of_a_function_are_plain_variables():
    """The names of a function that catches no error are variables.

    A variable lives in the registers of the machine, and an array lives
    in the memory, so a loop over the names of a function writes them to
    the memory on every step.
    """
    text = _c_source("fn helper(n) {\n    return n + 1\n}\nprint(helper(1))\n")
    assert "BunValue slot_0;" in text
    assert "BunValue slots[" not in text


def test_the_names_of_a_function_that_catches_an_error_live_in_the_memory():
    """A function that catches an error keeps its names in the memory.

    The error jumps into the frame of the function, and the values of an
    automatic object would be lost by the jump.
    """
    text = _c_source("fn helper(n) {\n"
                     "    try {\n"
                     "        return n + 1\n"
                     "    } catch err {\n"
                     "        return 0\n"
                     "    }\n"
                     "}\nprint(helper(1))\n")
    assert "BunValue *slots" in text


@needs_compiler
def test_the_backend_agrees_with_the_machine_on_a_function_with_arguments(
        capfd):
    """A function that takes arguments prints what the machine prints."""
    source = """
    fn total(a, b) {
        var sum = 0
        for value in [a, b, a + b] {
            sum = sum + value
        }
        return sum
    }
    print(total(3, 4))
    """
    expected = _run_vm(source, capfd=capfd)
    got = _run_c(source, capfd=capfd)
    assert got == expected


def test_a_string_of_the_pool_is_built_once():
    """A string of the program is one string and not one per use.

    A loop that uses a string ten million times builds it ten million
    times when the string is built at every use, and the program is a
    hundred times slower.
    """
    text = _c_source("fn f() {\n    return \"text\"\n}\nprint(f())\n")
    assert "static BunValue bun_const_" in text
    assert "bun_init_constants" in text
    # The body of the function does not build the string.
    body = text.split("static BunValue bun_fn_1(")[1]
    assert "bun_str_from_c" not in body.split("}")[0]


def test_a_refusal_points_at_the_line_of_the_program():
    """A refusal of the backend carries the place of the source.

    A program that uses a builtin the backend does not have is refused
    at compile time, and the refusal says where the program uses it.
    """
    source = "print(1)\nprint(json_stringify(\"a\"))\n"
    program = _program(source)
    with pytest.raises(cbackend.CBackendError) as failure:
        cbackend.check_builtins(program)
    assert failure.value.line == 2
    assert failure.value.col == 7


def test_a_call_of_a_builtin_is_a_direct_call():
    """A call of a builtin of the language is a call of the C function.

    The name of the builtin always holds the builtin, so the call does not
    look the builtin up in the environment.
    """
    source = "print(len(\"abc\"))\n"
    text = _c_source(source)
    assert "bun_builtin_len(call_args, 1)" in text


def test_the_backend_reads_and_writes_the_files(tmp_path, capfd):
    """The files of a program are the files of the machine.

    The machine reads a file and writes a file, and the backend does the
    same, with the same text and the same answers.
    """
    path = str(tmp_path / "bun_test.txt")
    source = ('write_file("%s", "hello\\n")\n'
              'print(read_file("%s"))\n'
              'print(file_exists("%s"))\n'
              'print(file_exists("%s.missing"))\n' % (path, path, path, path))
    expected = _run_vm(source, capfd=capfd)
    got = _run_c(source, capfd=capfd)
    assert got == expected
    assert "hello" in got


def test_a_file_that_is_not_there_is_a_failure_of_the_machine(tmp_path,
                                                               capfd):
    """A file that cannot be read is a failure of the machine.

    The message of the failure and the place of it are the same under
    the backend and under the machine.
    """
    path = str(tmp_path / "bun_test_missing.txt")
    source = 'print(read_file("%s"))\n' % path
    expected = _vm_failure(source, capfd)
    got = _c_failure(source, capfd)
    assert got == expected
    assert "cannot read" in got


def test_a_builtin_of_the_program_is_kept_in_a_static():
    """A builtin that the program reads is kept in a static variable.

    The builtin of the language lives in the table of the globals, and
    the lookup of a name in that table is the most expensive part of a
    read, so the builtin is copied into a static variable once.
    """
    source = "print(len(\"abc\"))\n"
    text = _c_source(source)
    assert "static BunValue bun_builtin_static_0;" in text
    assert "bun_builtin_static_0 = bun_env_get(globals, \"len\");" in text


def test_a_builtin_that_the_program_binds_is_not_kept_in_a_static():
    """A name that the program binds is the name of the program.

    The program that binds the name of a builtin reads its own name, so
    the builtin is not kept in a static variable.
    """
    source = ("fn len(text) {\n"
              "    return 7\n"
              "}\n"
              "print(len(\"abc\"))\n")
    text = _c_source(source)
    assert "bun_env_get(globals, \"len\")" not in text


def test_a_local_name_that_a_closure_captures_hides_the_function_of_the_module():
    """A name that a function binds is not the function of the module.

    The name of the module is kept in a static variable, and a function
    that binds the name itself reads its own name.
    """
    source = ("fn helper() {\n"
              "    return 1\n"
              "}\n"
              "fn shadow() {\n"
              "    fn helper() {\n"
              "        return 2\n"
              "    }\n"
              "    fn inner() {\n"
              "        return helper()\n"
              "    }\n"
              "    print(helper())\n"
              "    return inner()\n"
              "}\n"
              "print(shadow())\n")
    text = _c_source(source)
    assert 'bun_env_get(env, "helper")' in text


def test_a_call_of_a_shadowed_builtin_is_not_a_direct_call():
    """A name that the program binds is the name of the program.

    A function that has a name of a builtin binds the name, and the call
    of the name is a call of the value, and not a call of the builtin.
    """
    source = ("fn helper() {\n"
              "    fn len(text) {\n"
              "        return 7\n"
              "    }\n"
              "    return len(\"abc\")\n"
              "}\n"
              "print(helper())\n")
    text = _c_source(source)
    assert "bun_builtin_len(call_args, 1)" not in text


def test_a_call_of_a_builtin_with_a_keyword_is_not_a_direct_call():
    """A builtin takes no keyword argument, and the call stays a call.

    The call with a keyword argument is refused by the runtime, with the
    message and the place of the machine.
    """
    source = "print(len(\"abc\", y = 1))\n"
    text = _c_source(source)
    assert "bun_builtin_len(call_args, 1)" not in text


@needs_compiler
def test_the_backend_knows_the_set(capfd):
    """A set is a set under the backend and under the machine.

    The values of a set, the order of the values, the methods of a set
    and the operators of two sets are the same.
    """
    source = ("let a = set([1, 2, 3, 2])\n"
              "let b = set([2, 3, 4])\n"
              "print(a)\n"
              "print(b)\n"
              "print(a.len())\n"
              "print(a.contains(2))\n"
              "a.add(4)\n"
              "a.remove(1)\n"
              "print(a.values())\n"
              "print(a | b)\n"
              "print(a & b)\n"
              "print(a - b)\n"
              "print(a ^ b)\n"
              "print(type_of(a))\n")
    expected = _run_vm(source, capfd=capfd)
    got = _run_c(source, capfd=capfd)
    assert got == expected


@needs_compiler
def test_the_failure_of_a_set_is_the_failure_of_the_machine(capfd):
    """A set that cannot do something says the same thing.

    The message of the failure and the place of it are the same under
    the backend and under the machine.
    """
    programs = [
        "let s = set([1, 2])\ns.remove(9)\n",
        "let s = set([1, 2])\ns.nope()\n",
        "let s = set([1, 2])\ns.union([1])\n",
        "let s = set([1, 2])\nprint(s - 3)\n",
        "let s = set([1, 2])\ns.add([1])\n",
        "print(set(1))\n",
    ]
    for source in programs:
        expected = _vm_failure(source, capfd)
        got = _c_failure(source, capfd)
        assert got == expected


def test_a_call_of_the_builtin_of_a_set_is_a_direct_call():
    """The builtin of a set is a call of the C function.

    The name of the builtin always holds the builtin, so the call does
    not look the builtin up in the environment.
    """
    source = "let s = set([1, 2])\nprint(s.len())\n"
    text = _c_source(source)
    assert "bun_builtin_set(call_args, 1)" in text


@needs_compiler
def test_a_dictionary_of_many_keys_is_a_table_and_not_a_walk(capfd):
    """A dictionary of many keys is found in a moment.

    The backend keeps the keys of a dictionary in a table, so a program
    that fills a dictionary and reads it back does not walk the keys for
    every read.
    """
    source = ("var table = {}\n"
              "var index = 0\n"
              "while index < 5000 {\n"
              "    table[str(index)] = index\n"
              "    index = index + 1\n"
              "}\n"
              "var total = 0\n"
              "index = 0\n"
              "while index < 5000 {\n"
              "    total = total + table[str(index)]\n"
              "    index = index + 1\n"
              "}\n"
              "print(total)\n")
    expected = _run_vm(source, capfd=capfd)
    got = _run_c(source, capfd=capfd)
    assert got == expected


@needs_compiler
def test_a_key_that_is_removed_and_added_again_is_found(capfd):
    """The table of the keys follows the removals and the additions.

    A key that is removed leaves the dictionary, and a key that is added
    again is a new key, and the table of the keys still finds it.
    """
    source = ("var table = {}\n"
              "var index = 0\n"
              "while index < 500 {\n"
              "    table[str(index)] = index * 2\n"
              "    index = index + 1\n"
              "}\n"
              "var removed = 0\n"
              "index = 0\n"
              "while index < 500 {\n"
              "    if index % 2 == 0 {\n"
              "        del table[str(index)]\n"
              "        removed = removed + 1\n"
              "    }\n"
              "    index = index + 1\n"
              "}\n"
              "print(removed)\n"
              "print(table.len())\n"
              "print(table.has(\"250\"))\n"
              "print(table.has(\"251\"))\n"
              "table[\"250\"] = 7\n"
              "print(table[\"250\"])\n"
              "print(table.len())\n")
    expected = _run_vm(source, capfd=capfd)
    got = _run_c(source, capfd=capfd)
    assert got == expected


@needs_compiler
def test_a_set_of_many_values_is_a_table_and_not_a_walk(capfd):
    """A set of many values is found in a moment.

    The backend keeps the values of a set in a table, so a program that
    fills a set and asks it for a value does not walk the values for
    every question.
    """
    source = ("var values = set()\n"
              "var index = 0\n"
              "while index < 5000 {\n"
              "    values.add(index)\n"
              "    index = index + 1\n"
              "}\n"
              "print(values.len())\n"
              "print(values.contains(4999))\n"
              "print(values.contains(5000))\n")
    expected = _run_vm(source, capfd=capfd)
    got = _run_c(source, capfd=capfd)
    assert got == expected


@needs_compiler
def test_the_backend_knows_the_with_statement(capfd):
    """A `with` is a `with` under the backend and under the machine.

    The target of the statement is entered, the body runs, the target is
    left, and the target of a statement that fails is left with the
    message of the failure.
    """
    source = ("var log = []\n"
              "fn target(label) {\n"
              "    return {\n"
              "        \"__enter__\": fn() { log.push(\"enter \" + label) "
              "return label },\n"
              "        \"__exit__\": fn(err) { log.push(\"exit \" + label) "
              "return false }\n"
              "    }\n"
              "}\n"
              "with target(\"a\") as first {\n"
              "    log.push(\"body \" + first)\n"
              "}\n"
              "with target(\"b\") as second, target(\"c\") as third {\n"
              "    log.push(\"body \" + second + third)\n"
              "}\n"
              "try {\n"
              "    with target(\"d\") as fourth {\n"
              "        throw \"failed\"\n"
              "    }\n"
              "} catch err {\n"
              "    log.push(\"caught \" + err)\n"
              "}\n"
              "print(log.join(\",\"))\n")
    expected = _run_vm(source, capfd=capfd)
    got = _run_c(source, capfd=capfd)
    assert got == expected


@needs_compiler
def test_the_failure_of_a_with_is_the_failure_of_the_machine(capfd):
    """A target that cannot be entered says the same thing.

    The message of the failure and the place of it are the same under
    the backend and under the machine.
    """
    programs = [
        "with 5 as value {\n    print(value)\n}\n",
        "with {} as value {\n    print(value)\n}\n",
        "with {\"__enter__\": 5} as value {\n    print(value)\n}\n",
        "with {\"__enter__\": fn() { return 1 }} as value {\n"
        "    print(value)\n}\n",
    ]
    for source in programs:
        expected = _vm_failure(source, capfd)
        got = _c_failure(source, capfd)
        assert got == expected


@needs_compiler
def test_the_name_of_a_with_lives_in_the_environment():
    """The name of a `with` is a name of the environment.

    The statement defines the name in the environment of the scope that
    holds it, and the name leaves the scope when the scope ends.
    """
    text = _c_source("with target() as value {\n    print(value)\n}\n")
    assert 'bun_env_define(env, "value"' in text
    assert "with_stack[with_depth++] = regs[0];" in text


@needs_compiler
def test_the_counters_of_a_function_that_catches_an_error_live_in_the_memory(
        ):
    """The counters of a function that catches an error are certain.

    An error jumps into the frame of the function, and a counter that
    the compiler of the system keeps in a register would have a value
    that nobody knows, so the counters live in the memory.
    """
    text = _c_source("try {\n    throw \"boom\"\n} catch err {\n"
                     "    print(err)\n}\n")
    assert "volatile int iter_count = 0;" in text


@needs_compiler
def test_the_backend_knows_the_secret(capfd):
    """A secret is a secret under the backend and under the machine.

    The value of a secret is masked in every rendering, and only the
    method `reveal` gives it back.
    """
    source = ("var token = secret(\"hunter2\")\n"
              "print(token)\n"
              "print(str(token))\n"
              "print(dump(token))\n"
              "print(type_of(token))\n"
              "print(token.reveal())\n"
              "print(dump({\"api_key\": token, \"name\": \"demo\"}))\n"
              "print({\"api_key\": token, \"name\": \"demo\"})\n"
              "print([token])\n"
              "print(f\"token={token}\")\n"
              "print(token == secret(\"hunter2\"))\n"
              "print(token == secret(\"other\"))\n"
              "print(token == \"hunter2\")\n")
    expected = _run_vm(source, capfd=capfd)
    got = _run_c(source, capfd=capfd)
    assert got == expected


@needs_compiler
def test_the_backend_knows_the_dump(capfd):
    """The dump of a value is the dump of the machine.

    The keys of a dictionary are in order, the secrets are masked, and
    the values are the values of the machine.
    """
    source = ("print(dump(1))\n"
              "print(dump(1.0))\n"
              "print(dump(0.5))\n"
              "print(dump(\"a\\nb\"))\n"
              "print(dump([1, \"x\", null, true]))\n"
              "print(dump({\"b\": 1, \"a\": 2, \"c\": {\"z\": 1, \"y\": 2}}))\n"
              "print(dump(set([3, 1])))\n")
    expected = _run_vm(source, capfd=capfd)
    got = _run_c(source, capfd=capfd)
    assert got == expected


@needs_compiler
def test_the_failure_of_a_secret_is_the_failure_of_the_machine(capfd):
    """A secret that cannot do something says the same thing.

    The message of the failure and the place of it are the same under
    the backend and under the machine.
    """
    programs = [
        "print(secret())\n",
        "print(dump())\n",
        "var s = secret(\"x\")\nprint(s.reveal(1))\n",
        "var s = secret(\"x\")\nprint(s.nope())\n",
        "print(dump(print))\n",
    ]
    for source in programs:
        expected = _vm_failure(source, capfd)
        got = _c_failure(source, capfd)
        assert got == expected
