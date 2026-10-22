# Bun Language — Phase 3 Design: Error Handling and Tool Conversion

Date: 2026-10-15

## Goal and Scope Decision

The master spec's original Phase 3 was "bytecode compiler + VM for
startup-speed performance." That is **deferred**, with this phase redefined as
**reliability + surface**:

- A bytecode VM in a Python-hosted interpreter speeds up execution throughput
  (roughly 2-5x) but not startup, which is dominated by the Python runtime
  itself (~30-50 ms) — the stated motivation does not hold.
- A VM adds a third AST consumer (interpreter, checker, compiler) and requires
  exact semantic replication of closures, modules, and the value model;
  differential testing would be mandatory.
- Phase 4 (self-hosting) does not require a VM — a tree-walker can self-host.

This phase instead: JS-style `try`/`catch`/`throw` error handling, one small
list method (`sort`), a real bun-runtime tool conversion, and the cheap,
safe deferred minors from the ledger.

## 1. Error Handling: try / catch / throw

### Grammar

```
try_stmt     := "try" block catch_clause
catch_clause := "catch" (IDENT | "(" IDENT ")")? block
throw_stmt   := "throw" expr
```

- At most one catch clause per try; try statements may nest freely.
- `catch (error)`, `catch error { }` (no parens), and `catch { }` (no
  binding) are all allowed; the binding receives the error message string.

### Semantics

- The try block executes; a `BunRuntimeError` raised anywhere during its
  execution transfers control to the catch block.
- Catchable: runtime errors only — undefined variable, wrong call arity, type
  mismatch at runtime, file I/O errors, division by zero, immutable
  reassignment, circular import, `throw`n errors.
- Not catchable: `LexError` and `ParseError` (raised before execution) and
  `BunTypeError` (raised by the checker before execution). A static error is a
  static guarantee; programs cannot catch what never ran.
- `throw <expr>` raises `BunRuntimeError` whose message is `stringify(value)`.
- `return` inside try or catch propagates normally; only `BunRuntimeError` is
  caught. After the catch block completes, execution continues after the try
  statement. Re-throwing works naturally (`throw error` inside catch).
- The catch binding is block-scoped and shadows like any parameter binding.

### Type checker

`TryStmt` and `ThrowStmt` are walked structurally (their blocks/expressions
are checked) but impose no rules — dynamic, like operators and method calls.
Consistent with the Phase 2 gradual model.

## 2. List Method: sort()

- `list.sort()` — sorts in place, lexicographically, using the same ordering
  as the `<` operator; stable (equal elements keep their order).
- Elements that cannot be compared (mixed types, unorderable values) raise
  `BunRuntimeError("cannot sort list with mixed types")` rather than leaking
  Python's `TypeError`.
- Returns `null` (in-place mutation), consistent with `push`/`reverse`.
- No comparator or key function this phase (YAGNI). The tool conversion's
  length-bucketing needs only stability, not a custom comparator.

## 3. Tool Conversion: mime_type_list.generate.ts

Source: `bun-runtime/src/http_types/mime_type_list.generate.ts` — a pure text
transform (verified: no network, shell, binary buffers, or zstd). It
regenerates `mime_type_list_sorted.rs` from `mime_type_list.txt`, and a
`bun:test` file pins its output byte-for-byte — the golden-test pattern
applied to a real upstream tool.

### Files

- `tools/mime_type/mime_type_list.bun` — module exporting
  `generate(list_text) -> string` producing the Rust source. No file I/O
  inside the module (importable, testable, mirrors the unicode-generator
  split).
- `tools/mime_type/example.bun` — standalone driver: reads
  `mime_type_list.txt`, writes `mime_type_list_sorted.rs`, with the read
  wrapped in try/catch for a graceful error (documented deviation: the TS
  version lets `readFileSync` throw raw). This is try/catch's real-world
  exercise.
- `tests/golden/mime_type_list.bun` — golden driver:
  `import { generate } from "../../tools/mime_type/mime_type_list"` (this
  doubles as the automatic regression test for deferred `../`-combo imports,
  ledger minor), reads `tests/golden/mime_list.txt` inside try/catch, prints
  the generated Rust source to stdout.
- `tests/golden/mime_list.txt` — small diverse fixture (~25 entries covering
  several lengths and boundary cases).
- `tests/golden/mime_type_list.out` — byte-exact expected output.

### Algorithm (faithful port)

1. Split the list on `\n`, drop empty lines, dedupe preserving first-seen
   order (dict keys).
2. `sort()` lexicographically.
3. Stable bucket by length 0..maxLen+1 (sentinel entry past the longest
   name); concatenate names into the NAMES blob, recording
   (offset, position) per length.
4. Escape the blob: `\` → `\\`, `"` → `\"`.
5. Wrap the blob at 100 characters without splitting an escape sequence
   (manual index loop; no backslash near the cut point).
6. Emit the Rust scaffolding: header comment, `NAMES` byte-string,
   `BUCKETS` table.

### Documented deviations

- The TS version compares latin1-encoded bytes; MIME names are ASCII, so Bun
  string ordering is equivalent.
- TS `JSON.stringify` escapes control characters; MIME data is printable
  ASCII, so escaping `\` and `"` is sufficient.

## 4. Deferred Minor Fixes (cheap + safe)

- **REPL cross-line type info**: the REPL keeps one `Checker` and its
  top-level scope across lines, so annotated bindings from earlier lines
  remain visible to later lines' checks (currently a fresh checker per line
  silently forgets them).
- **Module error caret**: a runtime error raised during a module's top-level
  execution carries the module's filename and source; the CLI formats the
  error frame against the module file, not the entry file. (Today the frame
  shows the entry program with a caret into the wrong text.)
- **Golden dedup**: `tests/golden/example.bun` imports
  `../../tools/unicode/unicode_generator` instead of the duplicated
  `tests/golden/unicode_generator.bun`, which is deleted. Deletion requires
  explicit user approval — the plan carries it as its own confirmation step.
- **Deferred `../` test**: the mime golden driver's `../../tools/...` import
  becomes the automatic regression test for deferred imports combined with
  `../` paths.

## 5. Testing and Success Criteria

- New tests: try/catch/throw (~15-20: basics, nesting, catchable vs
  non-catchable errors, throw with various values, catch binding scope,
  return propagation, interaction with functions), `sort()` (~5: basic,
  stability, empty, mixed-type error, in-place semantics), mime golden (1
  program), minors regressions (REPL persistence, module caret, dedup
  golden unchanged output).
- Full suite: 181 → ~215-225 passed, 1 skipped (the pre-existing
  unicode_generator golden skip), zero regressions in existing tests.
- Golden mime output byte-exact.
- Manual end-to-end: a throw/catch program, a sort demo, and
  `python3 -m bun tools/mime_type/example.bun` run cleanly.

## 6. Non-Goals (this phase)

- No `finally`, no multiple catch clauses, no catch-by-error-type.
- No comparator or key function for `sort()`.
- No regex, no binary I/O, no zstd (the reasons the add-completions tool was
  not convertible).
- No bytecode VM — deferred; see Scope Decision.

## 7. Docs and Roadmap

- README: add an "Error handling (Phase 3)" section.
- Master spec: add a "Phase 3 Additions" section; update the Roadmap so
  Phase 3 reads DONE (reliability + surface) and the bytecode VM is a
  separate later milestone.
