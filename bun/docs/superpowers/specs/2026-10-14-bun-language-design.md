# Bun Language — Design Specification (v0.1)

Date: 2026-10-14

## Goal

Create **Bun**, an original interpreted programming language inspired by
Rust, Go, C++, and Python. Bun combines Rust/Go-like readable syntax with
Python-like dynamic simplicity, delivered as a tree-walking interpreter
written in Python.

## Non-Goals (v0.1)

- Static type system, generics, traits
- Ownership / borrow checker / lifetimes
- Native or bytecode compilation
- Classes
- Self-hosting

These are deferred to later phases (see Roadmap).

## Architecture

Pipeline:

```
source.bun  ->  Lexer  ->  tokens  ->  Parser  ->  AST  ->  Interpreter  ->  output
```

### Components

| File | Responsibility |
|------|----------------|
| `bun/lexer.py` | Convert source text into a token stream. Tracks line/column. |
| `bun/tokens.py` | Token type definitions and `Token` dataclass. |
| `bun/ast.py` | AST node dataclasses (`LetStmt`, `FnDecl`, `BinOp`, `Call`, ...). |
| `bun/parser.py` | Recursive-descent parser producing AST from tokens. |
| `bun/values.py` | Runtime value types (int, float, string, bool, list, function, null). |
| `bun/environment.py` | Lexical scope chain for variable bindings. |
| `bun/interpreter.py` | Tree-walking evaluator over the AST. |
| `bun/builtins.py` | Built-in functions: `print`, `range`, `len`, `str`, `int`, `float`. |
| `bun/errors.py` | `LexError`, `ParseError`, `RuntimeError` with line/column info. |
| `bun/cli.py` | Command-line entry: run a file or start REPL. |
| `bun/__main__.py` | Enables `python -m bun`. |
| `tests/` | pytest unit tests and golden `.bun` programs. |

Each component has one clear purpose and communicates through a well-defined
interface (tokens / AST / values), so components can be understood and tested
independently.

## Syntax (v0.1)

```bun
// line comment
# also a comment

let x = 10          // immutable binding
var count = 0       // mutable binding
let name = "Bun"
let ok = true
let nothing = null

fn add(a, b) {
    return a + b
}

if x > 5 {
    print("big")
} else {
    print("small")
}

while count < 3 {
    count = count + 1
}

for i in range(0, 5) {
    print(i)
}

let nums = [1, 2, 3]
nums[0] = 99
print(len(nums))
```

## Semantics

- **Dynamic typing**: values carry their own type at runtime.
- **Bindings**: `let` is immutable (reassignment raises a runtime error),
  `var` is mutable. Assignment targets must already be declared.
- **Scoping**: block scoping with a lexical environment chain.
- **Functions**: first-class values with closures; `fn` declarations and
  `return`.
- **Comments**: both `//` and `#` run to end of line.
- **Truthiness**: `false`, `null`, `0`, `0.0`, `""`, and `[]` are falsy;
  everything else is truthy.

### Operators (precedence low to high)

1. `or`
2. `and`
3. `==` `!=`
4. `<` `<=` `>` `>=`
5. `+` `-`
6. `*` `/` `%`
7. unary `-` `!`
8. call `()` and index `[]`

## Error Handling

All errors report `line:column`, the offending source line, and a caret marker.
Examples:

```
error: unexpected token '}'
  --> program.bun:4:1
   |
 4 | }
   | ^
```

Runtime errors (undefined variable, type mismatch, division by zero,
immutable reassignment) use the same format.

## Testing Strategy

- Unit tests per component (lexer, parser, interpreter) with pytest.
- Golden programs: `.bun` files with expected output in a sibling `.out` file,
  run end-to-end by the CLI and compared.
- Target: every exported behavior has at least one test.

## Identity

Bun's spirit follows the Bun runtime: **zero-config, "baked-in" utilities,
soft syntax.** A program should start with nothing but the file — no manifest,
no build step, no boilerplate. Everything you commonly need already ships in
the box. Syntax stays minimal and forgiving, and the REPL greets you as `bun>`.

v0.1 realizations of this identity: a single self-contained package with no
third-party dependencies; `python -m bun <file>` runs a program with no
configuration; built-ins `print`, `len`, `range`, `str`, `int`, `float` are
always available; `bin/bun` provides a native launcher; both `//` and `#`
comments are accepted.

Later phases should extend this identity (JS-flavored sugar, batteries-included
standard library, fast startup) without abandoning it.

## Phase 1.5 Additions

- **Method calls**: `receiver.method(args)` on strings, lists, and dicts.
- **String methods**: `trim`, `lower`, `upper`, `split`, `contains`,
  `starts_with`, `ends_with`, `replace`, `repeat`, `slice`, `index_of`, `len`.
- **List methods**: `push`, `pop`, `len`, `join`, `contains`, `reverse`, `slice`.
- **Dicts**: literal syntax `{}` / `{"key": value}`, `d["key"]` read/write, and
  methods `len`, `has`, `get`, `keys`, `values`, `remove`. Keys may be strings
  or numbers; `1` and `"1"` are distinct keys.
- **File I/O built-ins**: `read_file`, `write_file`, `append_file`,
  `file_exists`.

## Phase 1.6 Additions

- **Modules**: `export fn` / `export let` / `export var` mark module exports;
  `import { a, b } from "./path"` imports them. Paths are relative to the
  importing file, `.bun` optional. Modules run once per path and are cached;
  importers share module state. Circular imports raise a runtime error.
  Imported bindings are immutable. Exports are recorded while module-level code
  runs, so `export` in the entry program, or in a function called after the
  module finished loading, raises a runtime error.
- **Anonymous functions**: `fn(params) { ... }` in expression position creates
  a closure named `anonymous`.
- **Converted tool**: `tools/unicode/` ports the Bun runtime's
  `misctools/unicode-generator.ts` table generator to Bun, used as the first
  real-world module plus a golden test.

## Phase 3 Additions

- **Error handling**: `try { ... } catch (e) { ... }` catches runtime errors
  (`BunRuntimeError` only; lex/parse/type errors are not catchable). `throw`
  raises a runtime error whose message is `str(value)`.
- **`list.sort()`**: in-place, stable, lexicographic ordering (numbers or
  strings, not mixed); returns `null`.
- **Converted tool**: `tools/mime_type/` ports
  `src/http_types/mime_type_list.generate.ts` from the Bun runtime's own
  tooling, with a golden test.

See `docs/superpowers/specs/2026-10-15-bun-phase-3-design.md` for the design.

## Roadmap

- **Phase 1 (this spec)**: tree-walking interpreter — DONE.
- **Phase 1.5 (identity pass)**: more "baked-in" utilities and softer syntax
  (string built-ins, list methods, `bun:*`-style standard modules), keeping the
  zero-config principle — DONE.
- **Phase 1.6 (module system)**: `import`/`export` for relative-path modules
  with a run-once cache, plus the first converted tool from the Bun runtime's
  own tooling — DONE.
- **Phase 2**: static type checker on top of the AST — DONE.
- **Phase 3**: error handling (`try`/`catch`/`throw`), `list.sort()`, and the
  mime_type_list tool conversion — DONE.
- **Phase 3.5**: bytecode compiler + stack VM, built for Phase 4
  self-hosting readiness — DONE (default engine; tree-walker retained as
  the differential oracle; see the Phase 3.5 design spec).
- **Phase 4**: front-end self-hosting (lexer, parser, compiler written in Bun;
  `--front-end bun`) — DONE.
- **Phase 5**: self-hosted type checker (`selfhost/checker.bun`) running in the
  `--front-end bun` pipeline with message-for-message error parity — DONE.
  Deferred: Bun-written VM, serialized bytecode, default front end, self-hosted
  REPL and runtime module loading.
