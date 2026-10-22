# Bun Language — Phase 4 Design: Front-End Self-Hosting

Date: 2026-10-17

## Goal and Motivation

Phase 4 rewrites the Bun **front end** in Bun itself: lexer, parser, and
bytecode compiler. The Python VM remains the execution engine, consuming the
plain-data code objects that the Phase 3.5 design defined as the stable
compiler/VM interface. This makes the language definition executable in its
own syntax and proves that the Phase 3.5 emission contract is real, before any
further investment in a Bun-written runtime.

Self-hosting here means: the Bun source of a program is tokenized, parsed, and
compiled by Bun code, and the resulting code object runs on the existing VM
with results byte-identical to the Python pipeline.

## 1. Scope and Decomposition

In scope:

- `selfhost/lexer.bun` — tokens as dicts.
- `selfhost/parser.bun` — AST as dicts mirroring `bun/ast.py`.
- `selfhost/compiler.bun` — AST dicts to code objects.
- `selfhost/main.bun` — driver (modes: run, `--lex`, `--ast`, `--dump`).
- `bun/selfhost.py` — Python bridge: normalization, canonical dumps, driver
  builtins, driver launch.
- `bun/cli.py` — `--front-end python|bun` flag (default `python`).
- Differential parity tests across the whole existing corpus.

Out of scope for Phase 4 (candidate Phase 5):

- A Bun-written type checker, VM, or runtime value model.
- Serialized bytecode files (`.bunb`); code objects stay in memory.
- Flipping the default front end; `--front-end bun` is opt-in.
- A self-hosted REPL and self-hosted module loading (see section 7).
- Deleting or rewriting the Python front end.

## 2. Architecture

```
source
  |
  +--> [python front end]  lex -> parse -> check        (always, for static errors)
  |
  +--> --front-end bun:
         selfhost/main.bun (runs on the Python VM)
           lex -> parse -> compile -> run_code(code object)
                                        |
                                    bridge: normalize
                                        |
                                    Python VM executes
```

The Python pipeline still runs first for every program: static errors
(`LexError`, `ParseError`, `BunTypeError`) must be raised, positioned, and
non-catchable exactly as today. The Bun front end then re-lexes, re-parses, and
compiles the same source. Python-side results are used only for checking; the
executed code object is the Bun-compiled one.

Rationale: the checker is out of scope, and duplicating static-error behavior
would create a second oracle for the same messages. This keeps the
non-catchable static-error invariant structurally intact.

## 3. Data Model

### Tokens

A list of dicts: `{"type": <string>, "value": <value>, "line": <int>,
"col": <int>}`. `type` is the Python `TokenType` name (`"INT"`, `"PLUS"`,
`"IDENT"`, ...). The lexer keeps a `keywords` dict and an escape-sequence
table; both are ordinary Bun dicts.

### AST

A dict per node: `{"kind": <string>, ...fields}`. `kind` is the Python
dataclass name (`"Program"`, `"LetStmt"`, `"Binary"`, ...), and fields mirror
`bun/ast.py` one-to-one, optional fields included. Nodes are plain data: no
constructors, no classes. Dispatch is by `kind` string.

### Code objects and instructions

Exactly the Phase 3.5 contract:

```text
CodeObject = {
  "name": str, "params": [str], "code": [Instruction],
  "filename": str, "source": str
}
Instruction = [op: str, arg, line: int, col: int]
```

Bun has no tuples, so instructions are 4-element lists and multi-field
operands (for example `METHOD_CALL`) are lists. The bridge normalizes nested
BunDicts to dicts and leaves lists as lists; the VM already destructures
4-element instructions without caring about list versus tuple.

## 4. Bridge (`bun/selfhost.py`)

- `normalize(value)` — deep conversion: `BunDict` to `dict`, lists recurse,
  scalars pass through.
- `canonical(value)` — deterministic text dump for parity: dict keys sorted,
  no whitespace variance. Used by tests and by the driver's dump modes.
- `run_front_end(path, mode)` — reads the source, builds a driver invocation
  with the target as `args()`, executes `selfhost/main.bun` on a fresh VM, and
  returns the textual result (`--dump`/`--ast`/`--lex`) or `None` for run mode.
- Driver builtins injected into the driver's global environment:
  - `args()` — returns the driver's argument list.
  - `run_code(code)` — normalizes and executes a code object on a fresh VM
    whose `base_dir` is the target file's directory.
  - `dump(value)` — canonical dump string (used by `--lex`, `--ast`,
    `--dump`).

The bridge lives in Python because it is host integration, not language
semantics. Everything that produces tokens, AST, or code objects is Bun.

## 5. CLI

`bun --front-end python|bun file.bun` (default `python`).

- `--front-end bun` requires the VM engine; combined with `--engine tree` it
  exits 2 with a clear message (the tree-walker consumes AST dataclasses, not
  code objects).
- `--no-check` still skips the checker; lexing and parsing in Python still run
  so static errors stay first-class.
- Exit codes and error formatting are unchanged.

## 6. Error Handling

- Static errors: Python pipeline, unchanged, before the driver starts.
- Runtime errors from Bun-compiled code: raised by the VM from emitted
  instruction positions and formatted by the existing CLI path with the target
  file's path and source.
- Driver failures on valid input indicate a compiler bug. The driver reports
  `error: <message>` and exits 1; the bridge surfaces it as a `BunRuntimeError`
  so no raw exception escapes.

## 7. Constraints and Limitations

Bun's current feature set bounds the port. The self-hosted sources must avoid:

- `break`/`continue` (not in the language).
- Direct dict iteration; use `.keys()`/`.values()` explicitly.
- `isinstance`; dispatch on `kind` fields instead.
- Character-class helpers (`isdigit`, `isalpha`); use range or membership
  checks on single-character strings.
- `ord`; keep an explicit escape-character dict.

Available and relied upon: string indexing and iteration, `int(str)`,
`float(str)`, `list`/`dict`/`string` methods, closures, `try`/`catch`,
`read_file`, and dictionaries with string keys.

Entry-file-only self-compilation: `IMPORT` instructions executed by the VM
still compile imported modules with the Python compiler. Parity tests target
single-file programs; module self-hosting is deferred.

## 8. Testing and Acceptance

New `tests/test_selfhost.py`, plus CLI additions in `tests/test_cli.py`.
Corpus: every `.bun` file under `tests/golden/`, `examples/`, `tools/`, and
`selfhost/`.

Gates, all must pass:

1. **Token parity** — `--lex` dump equals a canonical dump of the Python
   lexer's tokens, for every corpus file.
2. **AST parity** — `--ast` equals the canonical dump of the Python parser's
   AST, for every corpus file.
3. **Code parity** — `--dump` equals the canonical dump of the Python
   compiler's code object, for every corpus file.
4. **Execution parity** — every golden's stdout under `--front-end bun` equals
   the stored `.out` byte-for-byte; runtime error messages and positions match
   the Python front end.
5. **Self-compilation fixpoint** — each `selfhost/*.bun` file, when compiled by
   the Bun compiler, yields a code object identical to the Python compiler's.
6. **Regression** — the existing suite stays green (293 tests at the time of
   writing), including all `[tree]`/`[vm]` differential tests.

## 9. Risks

- **Parser port size.** `bun/parser.py` is the largest front-end module; the
  AST parity gate catches drift immediately, and the port proceeds
  expression-category by expression-category.
- **Numeric literal fidelity.** Python parses `1.5` to float and `15` to int;
  the Bun port must distinguish the same way. Token parity pins this.
- **Dump stability.** One canonical serializer lives in the bridge (Python);
  the format is pinned by unit tests (sorted keys, stable list order, explicit
  float formatting). The Bun side only produces plain data.
- **Suite runtime.** Parity over the whole corpus is heavier; parity tests
  live in their own file and run once per corpus file, not per engine.

## 10. Definition of Done

- All six gates pass with zero skips.
- `README.md` documents `--front-end python|bun` and the self-hosting status.
- The roadmap marks Phase 4 as done with the deferred items listed.
- `selfhost/` contains only Bun sources; no duplicated semantics in Python
  beyond the bridge.
