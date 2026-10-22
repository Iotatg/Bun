# Bun Language — Phase 2 Design Specification (Static Type Checker)

Date: 2026-10-15

## Goal

Add a **gradual static type checker** to Bun. Annotations are optional; every
unannotated name, parameter, and expression is treated as `any` and passes
unchecked. The checker runs before the interpreter by default, reports type
errors with line/col in the existing error format, and blocks execution;
`--no-check` restores the previous behavior.

Bun stays soft: the checker protects what you annotate and never demands
annotations you did not write.

## Non-Goals (Phase 2)

- Generics (`list[int]`, `dict[K, V]`), traits, sum types
- Hindley-Milner inference — unannotated means `any`, never inferred
- Method-call checking (`receiver.method(args)`) — stays dynamic
- Binary-operator operand checking (`1 + "x"`) — stays a runtime error
- Missing-return / path-sensitive control-flow analysis
- Ownership, lifetimes, borrow checking

## Syntax

Annotations are optional and Rust-like:

```bun
let x: int = 5
var count: int = 0

fn add(a: int, b: int) -> int {
    return a + b
}

let greet: fn = fn(name) {
    return "hi " + name
}
```

- `let name: T = expr` / `var name: T = expr` — annotation after the name
- `fn name(params) -> T { ... }` — optional param annotations, optional
  `-> ReturnType`
- Anonymous `fn(params) -> T { ... }` may also annotate
- Unannotated names and parameters are `any`
- Type names are the reserved set below; anything else is a type error
  (`unknown type 'foo'`). `list[int]` is rejected with a clear message
  (generics are a later phase)

## Types

| Type | Meaning |
|------|---------|
| `int` | integers |
| `float` | floating point |
| `string` | text |
| `bool` | true / false |
| `null` | the null value |
| `any` | dynamic — assignable both directions |
| `list` | list value (elements unchecked) |
| `dict` | dict value (keys/values unchecked) |
| `fn` | any function value (callable check only) |

## Assignability

A source type S is assignable to target T when:

- either side is `any` (gradual typing — both directions), or
- S == T, or
- S is `int` and T is `float` (implicit widening), or
- S is `null` and T is anything (nullable by default).

`float -> int` is an error. `null -> string` is allowed.

## Checker Rules

New component `bun/checker.py`: a scoped AST walk (scopes mirror the
interpreter's lexical environments) that verifies:

1. **Declarations**: `let x: T = expr` / `var x: T = expr` — expr's type must
   be assignable to T.
2. **Assignments**: `x = expr` where x has a declared type — expr's type must
   be assignable to it. (Assignments to undeclared names remain the existing
   runtime error.)
3. **Returns**: every `return expr` inside a function with a declared return
   type must return an assignable type.
4. **Direct calls**: `f(args)` where f is statically known (an `fn` declaration
   or a `fn`-typed binding) — argument types must be assignable to the
   parameter types, and the arity must match.
5. **Builtin signatures** (known to the checker):

   | Builtin | Signature |
   |---------|-----------|
   | `print` | `(any) -> null` |
   | `len` | `(any) -> int` |
   | `range` | `(int) -> list` or `(int, int) -> list` (matches the runtime's 1-or-2 arity) |
   | `str` | `(any) -> string` |
   | `int` / `float` | `(any) -> int` / `(any) -> float` |
   | file I/O | `read_file(string) -> string`, `write_file(string, string) -> null`, `append_file(string, string) -> null`, `file_exists(string) -> bool` |

6. **Annotation locations**: annotations on `let`/`var`/`fn` params/returns.
   Type names must come from the table; arity of builtin calls checked as
   above.

Unchecked (dynamic): method calls, operators, indexing, unannotated code,
function values stored in `dict`/`list` fields.

Forward references are allowed: the checker collects a scope's `fn`
declarations before walking the body.

## Architecture

Pipeline becomes:

```
source.bun -> Lexer -> Parser -> **Checker** -> Interpreter -> output
```

| File | Responsibility |
|------|----------------|
| `bun/types.py` | Type universe as plain string constants (`INT`, `FLOAT`, `STRING`, `BOOL`, `NULL`, `ANY`, `LIST`, `DICT`, `FN`), the assignability rule, the builtin signature table. |
| `bun/checker.py` | Scoped AST walk producing `TypeError`s. |
| `bun/errors.py` | Add `BunTypeError` to the `BunError` family (same line/col formatting). |
| `bun/cli.py` | Run checker between parse and run by default; `--no-check` skips. REPL checks each line. |
| `bun/ast.py` / `bun/parser.py` / `bun/tokens.py` / `bun/lexer.py` | Annotation syntax: `:` and `->` tokens, optional string annotation fields (`type_ann` on `LetStmt`, `param_types`/`return_type` on `FnDecl`) — no dedicated `TypeAnn` node type. |

The checker depends only on the AST, `bun/types.py`, and `bun/modules.py`
(module-aware checking) — no interpreter state, no runtime values — so it is
testable in isolation.

## CLI Integration

- `python3 -m bun file.bun`: lex -> parse -> check -> run.
- Type errors print `error: <message>` with source frame via the existing
  `format_error`, exit code 1, program does not run.
- `python3 -m bun --no-check file.bun`: checker skipped (previous behavior).
- REPL: each line is checked; type errors render in the REPL error format.

## Module Boundaries

- The checker resolves `import ... from "./path"` the same way the
  interpreter does (relative path, optional `.bun`), parses the module, and
  collects the declared types of exported names without executing it.
- Imported bindings carry their declared types to the import site, so
  cross-module call-site checking works.
- Parse/lex errors inside a checked module surface as `TypeError`s naming the
  module (same wrapping approach as the interpreter's loader).
- Circular imports in the checker follow the same rule: error.

## Testing

- `tests/test_checker.py` (new):
  - decl/return/assignment mismatch errors with line assertions
  - call-site arg type + arity errors (direct and via `fn`-typed binding)
  - positive cases: null into any type, any passthrough, int->float widening,
    unannotated code entirely unchecked, forward references
  - unknown type name error
- Parser tests: annotation syntax on `let`/`var`/`fn` params/returns,
  anonymous fns, `--` arrow reuse, negative syntax cases.
- Golden: one annotated program with no type errors that runs end-to-end
  through checker + interpreter.
- Regression: the existing 123 tests must stay green (unannotated code is
  all `any`, so nothing newly fails).

## Phase 2 Additions (implementation notes)

- `bun/types.py`: the type universe (`TYPE_NAMES`), `is_assignable`, and
  `BUILTIN_SIGNATURES`.
- `bun/checker.py`: `Checker.check(program, base_dir)` — scoped AST walk
  raising `BunTypeError`.
- `bun/errors.py`: `BunTypeError` added to the `BunError` family (named
  `BunTypeError` rather than `TypeError` to avoid shadowing Python's
  builtin).
- CLI: lex -> parse -> check -> run by default; `--no-check` skips checking.

## Roadmap Update

- **Phase 2 (static type checker)**: gradual optional annotations over the
  AST — DONE.
