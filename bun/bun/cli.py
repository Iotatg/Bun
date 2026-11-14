import contextlib
import io
import os
import sys

from .lexer import Lexer
from .parser import Parser
from .checker import Checker
from .interpreter import Interpreter
from .compiler import Compiler
from .vm import VM
from .selfhost import run_front_end
from .values import stringify, ReturnSignal, canonical_dump
from .errors import BunError, BunRuntimeError, format_error
from . import ast
from . import docs
from . import types

USAGE = """Bun programming language

Usage:
  bun <file.bun>                  run a Bun program
  bun -                           run a Bun program from the standard input
  bun --no-check <file.bun>       run without type checking
  bun --engine tree|vm|register|c|wasm|jit|antar <file.bun> choose the execution
                                  engine (default: vm)
  bun --engine register --tier <file.bun> run with the superinstructions
  bun antar <file.bun> [--json|--dot|--verify|--stats]  show the control-flow graph
  bun raksha <file.bun> [--json|--dot|--verify|--stats|--explain]  static safety analysis
  bun check --raksha <file.bun>   type check plus the Raksha safety pass
  bun check --samanvay <file.bun> type check plus the Samanvay concurrency pass
  bun check --palan <file.bun>    type check plus the Palan resilience pass
  bun samanvay <file.bun> [--json|--dot|--verify|--stats|--explain]  concurrency report
  bun samanvay --run [--seed=N] <file.bun>   run under the deterministic scheduler
  bun samanvay --seeds=A:B <file.bun>        sweep seeds, report the first finding
  bun palan <file.bun> [--json|--dot|--verify|--stats|--explain]  resilience report
  bun palan --run [--seed=N] <file.bun>      run under the virtual clock
  bun palan --chaos=A:B <file.bun>           sweep seeds, one line per world
  bun --front-end python|bun <file.bun> choose the front end (default: python)
  bun --lang <code>|auto <file.bun>  write Bun in another language (see: bun langs)
  bun langs [--json]              list the language packs of the keywords
  bun reverse <binary> [procedure] reverse engineer any binary (via REA)
  bun repl [--json]               a session; with --json it speaks JSON-RPC
  bun api [--json]                list the builtin signatures
  bun doc [<symbol>] [--json]     show the documentation
  bun test [--json]               run the golden corpus
  bun test --doc [<symbol>]       run the documentation examples
  bun check [--json] <file.bun>   type check a file without running it
  bun compile [--profile] <file>  show the bytecode, or profile the run
  bun version [--short]           print the semantic version
  bun fmt [--check] <file.bun>    format a file, or check its formatting
  bun lint [--json] <file.bun>    report unused bindings
  bun pkg init|list|lock|verify|search|install   local package manager
  bun doc --html <out.html>       write a browsable API page
  bun doc <module> --exports      list the exports of a module
  bun compile --cache <file>      cache compiled bytecode
  bun check --cycles <file>       find cyclic imports
  bun startup | engines | parallel   measure the runtime
  bun changelog | ci | release | coverage | fuzz | bench | audit | doctor
  bun maturity [--run]            the 100-capability maturity probe
  bun originality [--json]        the lexical overlap and Bun's own forms
  bun                             start the interactive REPL
  bun -h | --help                 show this help
"""


def run_source(source, filename="<stdin>", check=True, engine="vm",
               program_args=None, tier=False, lang=None):
    if lang == "auto":
        from . import langpacks
        lang = langpacks.detect_auto(source)
    tokens = Lexer(source, lang=lang).tokenize()
    program = Parser(tokens).parse()
    base_dir = os.path.dirname(os.path.abspath(filename))
    if check:
        Checker().check(program, base_dir=base_dir)
    if engine == "register":
        from .regcompile import registerize
        from .regfuse import fuse
        from .regverify import verify_program
        from .regvm import RegisterVM
        vm = RegisterVM(program_args)
        code = Compiler(filename, source).compile_program(program)
        code = registerize(code)
        verify_program(code)
        if tier:
            code = fuse(code)
            verify_program(code)
        vm.run(code, base_dir=base_dir)
        return vm.globals
    if engine == "c":
        return _run_with_c_backend(source, filename, program, program_args,
                                   base_dir)
    if engine == "wasm":
        from . import wasm, wasmvm
        data = wasm.compile_program(program, filename)
        wasmvm.run_module(wasmvm.decode(data), "main")
        return {}
    if engine == "jit":
        from .jit import run_program
        run_program(program, filename)
        return {}
    if engine == "antar":
        from .antar import run_program as run_antar
        run_antar(program, filename, program_args, base_dir=base_dir)
        return {}
    if engine == "vm":
        vm = VM(program_args)
        code = Compiler(filename, source).compile_program(program)
        vm.run(code, base_dir=base_dir)
        return vm.globals
    interpreter = Interpreter(program_args)
    interpreter.run(program, base_dir=base_dir)
    return interpreter.globals


class NativeExit(Exception):
    """A program of the native backend ended with a status.

    The program of the backend has already printed its own error, so the
    command line must not print a second one.
    """

    def __init__(self, status):
        super().__init__(status)
        self.status = status


def _run_with_c_backend(source, filename, program, program_args, base_dir):
    """Run a program with the native backend."""
    from .cbackend import (build_binary, check_builtins, cleanup, is_cached,
                            run_binary)
    from .regcompile import registerize
    from .regverify import verify_program

    check_builtins(program)
    code = Compiler(filename, source).compile_program(program)
    code = registerize(code)
    verify_program(code)
    binary, directory = build_binary(code, filename, source=source)
    try:
        result = run_binary(binary, program_args or [], filename)
    finally:
        if not is_cached(directory):
            cleanup(directory)
    if result.returncode != 0:
        raise NativeExit(result.returncode)
    return {}


def run_file(path, check=True, engine="vm", front_end="python",
             program_args=None, tier=False, lang=None):
    if path == "-":
        source = sys.stdin.read()
        try:
            run_source(source, filename="<stdin>", check=check, engine=engine,
                       program_args=program_args, tier=tier, lang=lang)
            return 0
        except BunError as error:
            print(format_error(error, source, "<stdin>"), file=sys.stderr)
            return 1
    try:
        with open(path, "r") as handle:
            source = handle.read()
    except OSError as error:
        print("error: cannot open file '%s': %s" % (path, error), file=sys.stderr)
        return 1
    try:
        if front_end == "bun":
            run_front_end(path, "run", check=check, lang=lang)
        else:
            run_source(source, filename=path, check=check, engine=engine,
                       program_args=program_args, tier=tier, lang=lang)
        return 0
    except NativeExit as exit:
        return exit.status
    except BunError as error:
        print(format_error(error, source, path), file=sys.stderr)
        return 1


def cmd_langs(args):
    """`bun langs [--json]` — the language packs of the keywords."""
    from . import langpacks
    as_json = "--json" in args
    args = [arg for arg in args if arg != "--json"]
    if args:
        print("error: langs takes no arguments", file=sys.stderr)
        return 2
    rows = langpacks.list_packs()
    if as_json:
        print(canonical_dump({
            "count": len(rows),
            "languages": [{"code": code, "name": name, "keywords": count}
                          for code, name, count in rows],
        }))
        return 0
    print("%d language packs; use one with --lang <code> or a first line"
          " `#!lang <code>`" % len(rows))
    for code, name, count in rows:
        print("  %-10s %-38s %2d keywords" % (code, name, count))
    return 0


def cmd_reverse(args):
    """`bun reverse <binary> [procedure]` — reverse engineer any binary
    with the REA toolkit behind the scenes."""
    from . import reatool
    return reatool.cmd_reverse(args)


def cmd_repl(args):
    """`bun repl [--json]` — the session of the language.

    With `--json` the session speaks JSON-RPC 2.0 on the standard input
    and the standard output, one object per line.
    """
    if "--json" in args:
        from .rpc import Server
        return Server().serve()
    return repl()


def repl(check=True, engine="vm"):
    interpreter = Interpreter()
    vm = VM()
    checker = Checker()
    scope = {}
    while True:
        try:
            line = input("bun> ")
        except EOFError:
            print()
            break
        if line.strip() == "":
            continue
        try:
            program = Parser(Lexer(line).tokenize()).parse()
            if check:
                scope = checker.check(program, base_dir=os.getcwd(), scope=scope)
            if engine == "vm":
                _repl_run_vm(vm, program, line)
            else:
                _repl_run_tree(interpreter, program, line)
        except BunError as error:
            print(format_error(error, line, "<repl>"))
    return 0


def _repl_run_vm(vm, program, line):
    statements = program.statements
    if len(statements) == 1 and isinstance(statements[0], ast.ExprStmt):
        value = vm.eval_expression(
            statements[0].expr, vm.globals, os.getcwd())
        if value is not None:
            print(stringify(value))
        return
    code = Compiler("<repl>", line).compile_program(program)
    vm.run(code, env=vm.globals, base_dir=os.getcwd())


def _repl_run_tree(interpreter, program, line):
    for statement in program.statements:
        if isinstance(statement, ast.ExprStmt):
            value = interpreter.evaluate(statement.expr, interpreter.globals)
            if value is not None:
                print(stringify(value))
        else:
            try:
                interpreter.execute(statement, interpreter.globals)
            except ReturnSignal:
                raise BunRuntimeError(
                    "'return' outside of a function",
                    statement.line, statement.col)


def api_data():
    """Return the builtin signature table as plain data."""
    return {
        "builtins": {
            name: [[list(params), return_type]
                   for params, return_type in signatures]
            for name, signatures in types.BUILTIN_SIGNATURES.items()
        }
    }


def cmd_api(args):
    """`bun api [--json]` — list the builtin signatures."""
    if "--json" in args:
        print(canonical_dump(api_data()))
        return 0
    for name in sorted(types.BUILTIN_SIGNATURES):
        for params, return_type in types.BUILTIN_SIGNATURES[name]:
            if params == (types.VARARGS,):
                rendered = "args: any..."
            else:
                rendered = ", ".join("arg%d: %s" % (index, item)
                                     for index, item in enumerate(params))
            print("%s(%s) -> %s" % (name, rendered, return_type))
    return 0


def cmd_doc(args):
    """`bun doc [<symbol>] [--json]` — show the documentation."""
    wanted = [arg for arg in args if not arg.startswith("--")]
    as_json = "--json" in args
    if as_json:
        print(canonical_dump(docs.docs_data()))
        return 0
    if not wanted:
        for name in docs.doc_names():
            print(name)
        return 0
    name = wanted[0]
    text = docs.render_doc(name)
    if text is None:
        print("error: no documentation for '%s'" % name, file=sys.stderr)
        return 1
    print(text)
    return 0


def cmd_test_doc(args):
    """`bun test --doc [<symbol>]` — run the documentation examples."""
    wanted = [arg for arg in args if not arg.startswith("--")]
    if wanted:
        names = wanted
    else:
        names = docs.doc_names()
    failures = 0
    ran = 0
    for name in names:
        entry = docs.DOCS.get(name)
        if entry is None:
            print("error: no documentation for '%s'" % name, file=sys.stderr)
            failures += 1
            continue
        example = entry.get("example")
        if not example:
            continue
        ran += 1
        captured = io.StringIO()
        try:
            with contextlib.redirect_stdout(captured):
                run_source(example, filename="<doc:%s>" % name, check=True,
                           engine="vm")
        except BunError as error:
            print("error: the example for '%s' failed: %s"
                  % (name, error.msg), file=sys.stderr)
            failures += 1
    if failures:
        print("%d of %d documentation example(s) failed" % (failures, ran),
              file=sys.stderr)
        return 1
    print("%d documentation example(s) passed" % ran)
    return 0


def cmd_test(args):
    """`bun test [--json] [--doc]` — run the tests of the language.

    Without a flag the golden corpus runs: every program of
    `tests/golden/` against the bytes it must print.  With `--doc` the
    examples of the documentation run instead.  With `--json` the report
    is a JSON document.
    """
    if "--doc" in args:
        return cmd_test_doc(args)
    return cmd_test_golden(args)


def cmd_test_golden(args):
    """`bun test [--json]` — run the golden corpus."""
    as_json = "--json" in args
    engine = "vm"
    if "--engine" in args:
        index = args.index("--engine")
        if index + 1 < len(args):
            engine = args[index + 1]
    directory = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tests", "golden")
    cases = []
    failures = 0
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".bun"):
            continue
        path = os.path.join(directory, name)
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
        captured = io.StringIO()
        error = None
        try:
            with contextlib.redirect_stdout(captured):
                run_source(source, filename=path, check=True, engine=engine)
            got = captured.getvalue()
        except BunError as failure:
            got = captured.getvalue()
            error = failure.msg
        passed = got == wanted and error is None
        if not passed:
            failures += 1
        cases.append({
            "name": name[:-4],
            "engine": engine,
            "passed": passed,
            "expected": wanted,
            "got": got,
            "error": error,
        })
    if as_json:
        print(canonical_dump({
            "cases": cases,
            "total": len(cases),
            "failed": failures,
            "passed": len(cases) - failures,
        }))
        return 1 if failures else 0
    for case in cases:
        if not case["passed"]:
            print("FAIL %s" % case["name"], file=sys.stderr)
            if case["error"]:
                print("  %s" % case["error"], file=sys.stderr)
            else:
                print("  expected: %r" % case["expected"][:200], file=sys.stderr)
                print("  got:      %r" % case["got"][:200], file=sys.stderr)
    if failures:
        print("%d of %d golden case(s) failed" % (failures, len(cases)),
              file=sys.stderr)
        return 1
    print("%d golden case(s) passed" % len(cases))
    return 0


def cmd_compile(args):
    """`bun compile [--profile] <file.bun>` — show the bytecode of a file.

    With `--profile` the program is run with the instruction profiler and
    the hot instructions of the workload are reported.  The counts are the
    measurement the register VM design needs.
    """
    profile = "--profile" in args
    paths = [arg for arg in args if not arg.startswith("--")]
    if not paths:
        print("error: bun compile expects a file", file=sys.stderr)
        return 2
    path = paths[0]
    try:
        with open(path, "r") as handle:
            source = handle.read()
    except OSError as error:
        print("error: cannot open file '%s': %s" % (path, error),
              file=sys.stderr)
        return 1
    try:
        program = Parser(Lexer(source).tokenize()).parse()
        Checker().check(program,
                       base_dir=os.path.dirname(os.path.abspath(path)))
        code = Compiler(path, source).compile_program(program)
    except BunError as error:
        print(format_error(error, source, path), file=sys.stderr)
        return 1
    if not profile:
        for index, instruction in enumerate(code["code"]):
            print("%4d  %-14s %-20s line %d col %d"
                  % (index, instruction[0], repr(instruction[1]),
                     instruction[2], instruction[3]))
        return 0
    vm = VM(profile=True)
    try:
        vm.run(code, base_dir=os.path.dirname(os.path.abspath(path)))
    except BunError as error:
        print(format_error(error, source, path), file=sys.stderr)
        return 1
    counts = vm.instruction_counts
    total = sum(counts.values())
    print("instruction profile: %d instructions" % total)
    for op, count in sorted(counts.items(), key=lambda item: -item[1]):
        share = (100.0 * count / total) if total else 0.0
        print("%6.2f%%  %9d  %s" % (share, count, op))
    return 0


def _raksha_diagnostics(program, path):
    """Run the static Raksha pass and return `bun check` diagnostics.

    `bun/raksha.py` is imported lazily: the default `bun check` must not
    depend on the safety pass at all.  A nidan becomes the same six-field
    diagnostic shape `_error_kind` feeds, plus its code and hint.
    """
    from . import raksha as raksha_module

    analysis = raksha_module.analyze_program(program, path)
    out = []
    for nidan in analysis.diagnostics:
        sthan = nidan.primary
        out.append({
            "file": path,
            "severity": "error",
            "kind": "raksha",
            "code": nidan.code,
            "hint": nidan.hint,
            "message": "raksha[%s]: %s" % (nidan.code, nidan.message),
            "line": getattr(sthan, "line", 0) or 0,
            "col": getattr(sthan, "col", 0) or 0,
        })
    return out


def _palan_diagnostics(program, path):
    """Run the static Palan pass and return `bun check` diagnostics."""
    from . import palan as palan_module

    analysis = palan_module.analyze_program(program, path)
    out = []
    for nidan in analysis.nidan:
        sthan = nidan.primary
        out.append({
            "file": path,
            "severity": "error",
            "kind": "palan",
            "code": nidan.code,
            "hint": nidan.hint,
            "message": "palan[%s]: %s" % (nidan.code, nidan.message),
            "line": getattr(sthan, "line", 0) or 0,
            "col": getattr(sthan, "col", 0) or 0,
        })
    return out


def _samanvay_diagnostics(program, path):
    """Run the static Samanvay pass and return `bun check` diagnostics."""
    from . import samanvay as samanvay_module

    analysis = samanvay_module.analyze_program(program, path)
    out = []
    for nidan in analysis.diagnostics:
        sthan = nidan.primary
        out.append({
            "file": path,
            "severity": "error",
            "kind": "samanvay",
            "code": nidan.code,
            "hint": nidan.hint,
            "message": "samanvay[%s]: %s" % (nidan.code, nidan.message),
            "line": getattr(sthan, "line", 0) or 0,
            "col": getattr(sthan, "col", 0) or 0,
        })
    return out


def cmd_check(args, raksha=False):
    """`bun check [--json] [--raksha|--samanvay|--palan] <file.bun>...`.

    With a pass flag the type check is followed by that static pass; its
    nidan are appended to the same diagnostics list, so `--json` consumers
    see one stream.  Without a flag, nothing changes.

    With `raksha=True` (or an explicit `--raksha` flag) the type check is
    followed by the static safety pass; its nidan are appended to the same
    diagnostics list.  Without it, nothing changes.
    """
    as_json = "--json" in args
    raksha = raksha or "--raksha" in args
    palan = "--palan" in args
    samanvay = "--samanvay" in args
    paths = [arg for arg in args if not arg.startswith("--")]
    if not paths:
        print("error: bun check expects at least one file", file=sys.stderr)
        return 2
    files = []
    for path in paths:
        files.extend(_check_targets(path))
    diagnostics = []
    for path in files:
        try:
            with open(path, "r") as handle:
                source = handle.read()
        except OSError as error:
            print("error: cannot open file '%s': %s" % (path, error),
                  file=sys.stderr)
            return 1
        program = None
        checked = False
        try:
            program = Parser(Lexer(source).tokenize()).parse()
            Checker().check(program,
                           base_dir=os.path.dirname(os.path.abspath(path)))
            checked = True
        except BunError as error:
            diagnostics.append({
                "file": path,
                "severity": "error",
                "kind": _error_kind(error),
                "message": error.msg,
                "line": error.line,
                "col": error.col,
            })
        if raksha and checked and program is not None:
            try:
                diagnostics.extend(_raksha_diagnostics(program, path))
            except Exception as error:                       # noqa: BLE001
                diagnostics.append({
                    "file": path,
                    "severity": "error",
                    "kind": "raksha",
                    "message": "raksha analysis failed: %s" % error,
                    "line": 0,
                    "col": 0,
                })
        if samanvay and checked and program is not None:
            try:
                diagnostics.extend(_samanvay_diagnostics(program, path))
            except Exception as error:                       # noqa: BLE001
                diagnostics.append({
                    "file": path,
                    "severity": "error",
                    "kind": "samanvay",
                    "message": "samanvay analysis failed: %s" % error,
                    "line": 0,
                    "col": 0,
                })
        if palan and checked and program is not None:
            try:
                diagnostics.extend(_palan_diagnostics(program, path))
            except Exception as error:                       # noqa: BLE001
                diagnostics.append({
                    "file": path,
                    "severity": "error",
                    "kind": "palan",
                    "message": "palan analysis failed: %s" % error,
                    "line": 0,
                    "col": 0,
                })
    if as_json:
        print(canonical_dump({
            "ok": not diagnostics,
            "diagnostics": diagnostics,
        }))
    else:
        for diagnostic in diagnostics:
            print("error: %s" % diagnostic["message"], file=sys.stderr)
            print("  --> %s:%s:%s" % (diagnostic["file"],
                                      diagnostic["line"],
                                      diagnostic["col"]), file=sys.stderr)
    return 1 if diagnostics else 0


def _check_targets(path):
    """Expand a path into the list of the Bun files it names."""
    if os.path.isdir(path):
        found = []
        for root, dirs, names in os.walk(path):
            dirs[:] = [name for name in dirs
                       if name not in ("scratch", "__pycache__")]
            for name in sorted(names):
                if name.endswith(".bun"):
                    found.append(os.path.join(root, name))
        return found
    return [path]


def _error_kind(error):
    """Name the kind of an error for the structured output."""
    name = type(error).__name__
    if name == "BunTypeError":
        return "type"
    if name == "ParseError":
        return "syntax"
    if name == "LexError":
        return "lex"
    return "runtime"


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    check = True
    engine = "vm"
    if "--no-check" in args:
        args = [arg for arg in args if arg != "--no-check"]
        check = False
    if "--engine" in args:
        index = args.index("--engine")
        if index + 1 >= len(args) or args[index + 1] not in (
                "tree", "vm", "register", "c", "wasm", "jit", "antar"):
            print("error: --engine expects 'tree', 'vm', 'register', 'c',"
                  " 'wasm', 'jit' or 'antar'", file=sys.stderr)
            return 2
        engine = args[index + 1]
        del args[index:index + 2]
    front_end = "python"
    if "--front-end" in args:
        index = args.index("--front-end")
        if index + 1 >= len(args) or args[index + 1] not in ("python", "bun"):
            print("error: --front-end expects 'python' or 'bun'", file=sys.stderr)
            return 2
        front_end = args[index + 1]
        del args[index:index + 2]
    tier = False
    if "--tier" in args:
        args = [arg for arg in args if arg != "--tier"]
        tier = True
        if engine != "register":
            print("error: --tier requires --engine register", file=sys.stderr)
            return 2
    lang = None
    if "--lang" in args:
        index = args.index("--lang")
        if index + 1 >= len(args):
            print("error: --lang expects a language code (see: bun langs)",
                  file=sys.stderr)
            return 2
        lang = args[index + 1]
        del args[index:index + 2]
        if lang != "auto":
            from . import langpacks
            if not langpacks.has_pack(lang):
                print("error: unknown language pack '%s' (see: bun langs)"
                      % lang, file=sys.stderr)
                return 2
    if front_end == "bun" and engine == "tree":
        print("error: --front-end bun requires --engine vm", file=sys.stderr)
        return 2
    if not args:
        if front_end == "bun":
            print("error: --front-end bun requires a file", file=sys.stderr)
            return 2
        return repl(check, engine)
    if args[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    from . import toolchain
    if toolchain.wants_toolchain(args[0], args[1:]):
        return toolchain.dispatch(args[0], args[1:])
    if args[0] == "repl":
        return cmd_repl(args[1:])
    if args[0] == "langs":
        return cmd_langs(args[1:])
    if args[0] == "reverse":
        return cmd_reverse(args[1:])
    if args[0] == "api":
        return cmd_api(args[1:])
    if args[0] == "doc":
        return cmd_doc(args[1:])
    if args[0] == "check":
        return cmd_check(args[1:])
    if args[0] == "compile":
        return cmd_compile(args[1:])
    if args[0] == "test":
        return cmd_test(args[1:])
    return run_file(args[0], check=check, engine=engine, front_end=front_end,
                    program_args=args[1:], tier=tier, lang=lang)
