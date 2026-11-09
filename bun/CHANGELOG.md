# Changelog

All notable changes to the Bun language are recorded here.  The version
number is the one `bun version` prints; a release is only made after the
full test suite passes and the maturity probe has written a real receipt.

## 0.4.0 — 2026-11-09

The language-core wave.  It closes the four language gaps that the 0.3.0
ledger left open, writes each one in Bun's own surface syntax, and repairs
a second measurement error in the ledger.  The score goes from `94/100`
to `98/100`; `D` is now `10/10`.

- **`on leave { ... }` — a scope-exit action.**  The block runs when
  control leaves the enclosing block, in the reverse order of
  registration, and it runs on a normal end, a `return`, a `break`, or a
  `throw`.  It is Bun's own form: a soft keyword pair, not a borrowed
  `defer`.  The parser lowers it to `try`/`finally`, so the tree
  interpreter, both virtual machines, the native C backend and the
  Bun-written front end run it with code they already have; there is no
  new opcode and no second semantics.
- **Recursive type arguments, in Bun's word form.**  `list of list of
  int` and `dict of string to list of int` are types; the bracket form
  `list<list<int>>` still works.  The lexer reads `>>` as a shift token,
  so the type parser splits it into two closing brackets only in a type.
  `types.type_args()` now splits nested argument lists on the commas that
  are not inside a nested type.
- **Function types as parameters.**  `fn(int) -> int` is parsed,
  checked (including the types inside it), and callable.  A function
  value of type `fn` is assignable to a declared function type with the
  same arity; the checker rejects a wrong argument type and an unknown
  type inside the signature.
- **Named loops.**  `for i in range(3) as outer { ... }` names a loop;
  `break outer` leaves it and `continue outer` restarts it from a nested
  loop.  The older `outer: for ...` form is still accepted and produces
  the same AST.  The compiler pops the `for` iterators between the jump
  and its target, so a `continue` to an outer loop does not leak the
  iterators of the loops it leaves.
- **`bun originality`.**  A lexical audit, not a proof: it reports the
  keywords Bun shares with Python, JavaScript, Go, Rust, C and Java, the
  one keyword no compared language has (`protocol`), and the constructs
  Bun spells in its own way (`on leave`, `for ... as name`, `list of
  int`, `div`, `import "path" as ns`, `scope`, `match` as an expression,
  `#lang:`, `bun:<name>`).  The command states its own limit in the
  output.

### Honest score breakdown

`D` moves from `6/10` to `10/10`; `E` stays `8/10`.  The two remaining
FAILs are the WASM (E06) and JIT (E07) execution engines, measured with a
real CLI attempt.  The ledger is now `98/100`.

`D02` also repairs an instrument error: the 0.3.0 probe expected
`"1\nbye"`, but a scope-exit action runs before the caller sees the
return value, so the only correct output is `"bye\n1"`.  A probe that
asks for the wrong order can never pass, however good the language is.
No ledger entry was edited to hide a failure.

`98/100` still does not mean "the language is 98% finished"; it means 98
of the 100 capabilities that were missing on 2026-11-08 now have working
code.

## 0.3.0 — 2026-11-08

The second maturity wave.  It adds native runtime value types, four pieces
of Bun-original syntax, and — just as importantly — repairs broken
measurement instruments in the maturity ledger.  The ledger goes from
`84/100` to `94/100`.

- **Native `bytes` value type.**  `BunBytes` is a real byte buffer backed by
  a `memoryview` over immutable `bytes`, not a list of integers.  A slice
  returns another view onto the same memory (zero-copy).  Nine new builtins
  cover `bytes_from_list`, `bytes_to_list`, `bytes_len`, `bytes_concat`,
  `bytes_slice` (now native), and typed errors.  `BunBytes + BunBytes` and
  `==`-by-content work; `type_of()` reports `bytes`.  `bun/maturity.py` now
  owns **64** builtins (55 in 0.2.0 + 9), still mirrored by one idempotent
  sync.
- **Typed error values.**  `BunErrorValue` is a first-class value with a
  `code` and `message`.  `fail_with` / `fail_with_message` build one;
  `error_code` / `error_message` / `is_error` inspect it.  Building an error
  is separate from raising it (`throw`); `type_of()` reports `error`.
- **Bun-original syntax, in both front ends and all engines.**  String
  repeat (`"ab" * 3` and `3 * "xy"`); optional semicolons as decorative
  statement separators (Bun's grammar still needs none); `div`, a soft word
  operator for floor division, because `//` is and stays the line-comment
  marker; and triple-quoted multiline strings (`"""..."""` / `'''...'''`).
  `div` has a real register opcode (`FLOORDIV`); the C backend refuses it
  by name rather than miscompiling.
- **Honest instrument repair.**  Seven 0.2.0 D-area probes were broken
  measuring devices, not capability tests: five called undefined
  `*_probe()` helpers, one used the invalid `fn f(): int` form, and one used
  `//` (a comment).  A broken probe cannot tell "feature missing" from
  "probe wrong".  Each is replaced with a real Bun program that attempts the
  actual syntax.  Three capabilities (class patterns in `match`, multiline
  strings, integer division) now PASS because the language really does them;
  the rest FAIL with a specific diagnostic naming the missing construct.
  No ledger entry was edited to hide a failure.

### Honest score breakdown

With the 0.3.0 implementation but the old broken probes the ledger reads
`91/100`; repairing the three placeholder probes that measure working
capabilities takes it to `94/100`.  `D` is `6/10` and `E` is `8/10`.  The
six remaining FAILs are genuine, honestly-measured gaps: `defer` (D02),
nested generic type arguments (D04), function type arguments (D05),
labelled break (D06), and the WASM (E06) and JIT (E07) execution engines.

`94/100` still does not mean "the language is 94% finished"; it means 94 of
the 100 capabilities that were missing on 2026-11-08 now have working code.

## 0.2.0 — 2026-11-08

The first measured maturity wave.  The ledger at
`tools/maturity_probe.py` scores 100 executable capabilities, one percent
each.  The baseline recorded on this date was `0/100`; this release adds
the first batch of real capabilities.

- **Standard library, 55 builtins.**  Encoding and digests (HMAC-SHA256/512,
  base64url, hex, gzip, SHA-512, BLAKE2b, timing-safe compare), UTC time
  and date (format/parse/parts/add/diff/weekday/leap/days/epoch-ms), text
  (named formatting, padding, centre, title/swap case, truncate, wrap, NFC
  normalisation, Levenshtein), URL/HTTP helpers (url/query/cookie/header
  parse and build, status text/class, MIME, percent encoding), data
  formats (struct pack/unpack, TOML, JSON pointer/equality, exact decimal
  addition, bitsets, ordered dicts, UUID v4, ULID), and semantic versions
  (`semver_compare`, `semver_satisfies`).
- **Unicode escapes.**  `\xHH`, `\uHHHH` and `\UHHHHHHHH` now work in
  ordinary strings and f-strings, in both the Python and the Bun-written
  front ends.  An invalid escape is reported, never silently accepted.
- **Single source of truth.**  `bun/maturity.py` owns the registry;
  `tools/sync_maturity.py` mirrors it into the checker, runtime, docs, the
  Bun-written docs and checker mirrors, and the C backend name list.  The
  sync is idempotent and has a `--check` mode used by the test suite.
- **Toolchain.**  `bun version`, `fmt`, `lint`, `pkg`, `doc --html`,
  `doc --exports`, `compile --cache`, `compile --target wasm`,
  `check --cycles`, `startup`, `engines`, `parallel`, `changelog`, `ci`,
  `release --dry-run`, `coverage`, `fuzz`, `bench`, `audit`, `doctor` and
  `maturity`.  Each command does real work and reports its own scope.
- **Maturity probe.**  A falsifiable external probe with a `selftest()`
  anchor; no capability is scored by reading a file or a checklist.

### Not implemented in 0.2.0

The ledger is honest about what is still missing: the WASM and JIT execution
engines, a native `bytes` value type, `defer`, labelled break, typed error
codes, class patterns in `match`, nested generics, and several package
manager operations are still `NOT_IMPLEMENTED`.  See the maturity receipt
shipped with the release.

## 0.1.0 — earlier work

The language core: lexer, parser, checker, tree/VM/register/C engines,
namespace imports, language packs, the Bun-written front end, and the
SUTRA / ETH / discovery libraries.
