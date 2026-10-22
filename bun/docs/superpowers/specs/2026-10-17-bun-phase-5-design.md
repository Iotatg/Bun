# Bun Language — Phase 5 Design: Self-Hosted Type Checker

Date: 2026-10-17

## Goal and Motivation

Phase 5 rewrites the gradual static type checker in Bun itself. Together with
the Phase 4 lexer, parser, and compiler, the whole front end of the language —
everything from source text to a runnable code object, including static
rejection — is now defined in Bun. The Python VM remains the execution engine.

The checker must reject and accept exactly the same programs as
`bun/checker.py`, with identical messages and positions.

## 1. Scope

In scope:

- `selfhost/checker.bun` — scoped AST walk over `selfhost/parser.bun` dicts.
- `selfhost/main.bun` — a `check` mode, and checking before compile in `run`
  mode.
- `bun/selfhost.py` — four driver builtins (`type_error`, `type_of`,
  `module_path`, `read_module`) and an updated `run_front_end`.
- Differential parity tests for the checker across the corpus and for
  representative error and import cases.

Out of scope:

- A Bun-written VM or runtime value model.
- Serialized bytecode (`.bunb`).
- Flipping the default front end; `--front-end python` stays the default.
- Self-hosted REPL and runtime module loading (the VM still loads modules with
  the Python front end).

## 2. Architecture

```
source
  |
  +--> [python pipeline]   lex -> parse                     (static lex/parse errors)
  |
  +--> --front-end bun:
         selfhost/main.bun (runs on the Python VM)
           lex -> parse -> check -> compile -> run_code(code object)
                            |
                    bridge builtins
                            |
                    type_error / type_of / module_path
```

For `--front-end bun` the Python pipeline still lexes and parses the entry
file first, so `LexError` and `ParseError` keep their exact behavior and stay
non-catchable. Type checking moves entirely to Bun: the Python checker is no
longer run on this path. `--no-check` disables the Bun checker and the Python
pipeline still lexes and parses.

`selfhost/main.bun` receives `[path, mode, check_flag, base_dir]` from `args()`.
`check` mode checks and stops; `run` mode checks when the flag is set, then
compiles and runs.

## 3. Data Model

The checker consumes the Phase 4 AST dicts unchanged. Dispatch is on `kind`.

- **Binding**: `{"type": str, "param_types": [str|null]|null,
  "return_type": str|null}`. Function bindings carry parameter and return
  types; value bindings leave those null.
- **Scope**: a Bun dict from name to binding. Child scopes are shallow copies
  made by iterating `.keys()`.
- **State**: `{"base_dir": str, "return_stack": [str|null],
  "module_cache": {path: exports}, "module_loading": {path: true}}`.

## 4. Bridge Additions

Four driver builtins live in Python because they touch host state or the
runtime value model:

- `type_error(message, line, col)` — raises `BunTypeError`. It is not a
  `BunRuntimeError`, so Bun `try`/`catch` cannot intercept it; the error
  reaches the CLI unchanged.
- `type_of(value)` — classifies a literal value as `int`, `float`, `string`,
  `bool`, `null`, or `any`. Bun has no `isinstance`, and `1 == 1.0` cannot
  distinguish int from float, so this probe stays in the host.
- `module_path(path, base_dir)` — delegates to
  `bun/modules.py:resolve_module_path`, preserving relative-path rules and
  messages.
- `read_module(path, full_path)` — reads module source, preserving the Python
  loader's `cannot read module ...` messages (including invalid UTF-8).

Everything that walks the AST, decides types, and produces messages is Bun.

## 5. Module Checking

Imports are checked without loading runtime state:

1. Resolve the path with `module_path`.
2. Re-read and re-parse the module with the Bun lexer and parser.
3. Load exports recursively (cycle detection via `module_loading`; results
   cached in `module_cache`).
4. Validate exported annotations and expose their bindings.

Errors are wrapped as `cannot load module '<path>': <message>` at the import
node, matching the Python checker. Annotation errors raised while collecting
exports use a catchable `throw` so they can be wrapped; all other type errors
use `type_error` and abort immediately.

## 6. Constraints and Limitations

The port respects the Phase 4 language restrictions: no classes, no
`break`/`continue`, no `isinstance`, no direct dict iteration, no `ord`, and no
character-class helpers. `fn` cannot be a parameter name (it is a keyword), so
function declarations are bound to `decl`.

State restoration on error is unnecessary: a type error always aborts the
whole check.

## 7. Testing and Acceptance

`tests/test_selfhost.py` gains:

1. **Corpus parity** — for every file under `tests/golden/`, `examples/`,
   `tools/`, and `selfhost/`, the Python and Bun checkers agree on pass/fail,
   message, line, and column.
2. **Error parity** — representative declaration, assignment, return, call,
   builtin, and annotation failures compare `(msg, line, col)` exactly.
3. **Import parity** — success, argument mismatch, imported value types,
   missing modules, missing exports, circular imports, module syntax errors,
   unknown export types, and nested missing modules.
4. **Regression** — the full suite stays green.

## 8. Definition of Done

- `--front-end bun` type-checks with `selfhost/checker.bun`; `--no-check`
  skips it.
- Checker parity gates pass with zero skips.
- `README.md` and the roadmap document Phase 5.
