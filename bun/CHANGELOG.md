# Changelog

All notable changes to the Bun language are recorded here.  The version
number is the one `bun version` prints; a release is only made after the
full test suite passes and the maturity probe has written a real receipt.

## 0.7.0 — 2026-11-14

The safety wave.  It adds **Raksha** (रक्षा, "protection"): a static
memory-safety pass, a runtime library written in Bun, and a ledger of
rules and error codes.  The idea is the useful half of Rust's ownership
model — exactly one owner, move, shared XOR exclusive loans, regions as
sets of program points, deterministic destruction, interior mutability,
result/option channels and labelled diagnostics.  **原理借用、语法未借用**
(the principle is borrowed, the syntax is not): there is no `&`, no `'a`,
no `mut`, no `unsafe`, no `Drop` trait and no `Result<T,E>`.  Every new
word is a function name of `bun:raksha`, no keyword was added, and the
118 language packs can therefore write the wave on the day it ships.

- **One memory flow per function.**  `bun/raksha.py` lowers statements to
  `bindu` (program points) and edges, computes predecessors, reverse
  postorder, dominators and natural loops, and infers each loan's `kaal`
  as the set of points reachable from its issue to its last use — the NLL
  idea of a region, not a lexical scope.  Two overlapping regions with an
  `adhikar` between them are refused statically.
- **14 error codes, 14 names.**  `RK01`–`RK14` cover use after move,
  double move, loan conflict, write through a shared loan, move while
  loaned, use after release, double release, loan escape, owner leak,
  unhandled result, unchecked option, unsafe/raw-pointer names refused,
  a loan crossing into `spawn`, and drop order.  Each `nidan` carries a
  primary `sthan`, labelled `chinh` spans, a hint and notes.
- **Bun-style RAII, not Rust syntax.**  `swatva(value)` returns an owner
  dict carrying `__enter__` and `__exit__`; the existing `with ... as ...`
  statement therefore calls `visarjan` on a normal exit *and* on a throw,
  with `__exit__(err)` distinguishing the two.  `on leave { ... }` is the
  explicit cleanup spelling.  No new statement, no new opcode.
- **A runtime library in Bun.**  `lib/bun/raksha.bun` exports `swatva`,
  `sanchay`, `udhaar`, `adhikar`, `padh`, `likh`, `visarjan`, `kosh`,
  `parinam_*`, `vikalp_*`, `niyam()`, `codes()`, `audit()` and
  `summary()`.  Its `audit()` uses real calls, not a table lookup, and
  certifies the ledger with `RAKSHA_LEDGER_CERTIFIED`.
- **Two commands.**  `bun raksha <file.bun>` prints the analysis;
  `--json`, `--dot`, `--stats`, `--verify` and `--explain` answer the
  five questions a tool asks.  A diagnostic or a failed `verify()` gives
  exit status 1.  `bun check --raksha <file.bun>` folds the nidan into
  the ordinary `check` diagnostics, and `bun check` without the flag is
  unchanged.
- **An honest boundary.**  `antar` refuses `with` by name because its
  machine does not implement that statement; Raksha does not refuse it —
  it is the construct the cleanup edge is built on.  The four-engine
  maturity program `tools/maturity/raksha_core.bun` deliberately avoids
  `with` so tree, vm, register and antar stay byte-identical.
- **The identity ledger grew without a keyword.**  `bun:identity` gains
  one `bun` family (`safety`, held to R5) and three canonical forms —
  `with rk.swatva(v) as a { ... }`, `on leave { rk.visarjan(a) }` and
  `import "bun:raksha" as rk`.  `keywords()` is untouched and `audit()`
  still runs exactly 15 falsifiable checks.  The counts in
  `docs/reference/bun-identity.md` are updated with it.
- **Reference and receipts.**  `docs/reference/raksha.md` is the normative
  reference: vocabulary, the 14 codes, the `with`/`__exit__` protocol,
  `kaal`/region, a Rust comparison table that names what was and was not
  borrowed, both commands, and reproducible commands.  The acceptance
  receipts (`pytest`, maturity probe, `tools/verify_raksha.py`,
  `bun doctor`, four-engine parity) live in `/workspace/`.

## 0.6.0 — 2026-11-14

The graph wave.  It adds **Antar** (`antar`, "the inside"), Bun's own
control-flow intermediate representation: one graph per function, built
from the syntax tree, verified before it runs, and shared by the engine,
the verifier and the dump.  The idea came from reading Rust's MIR and from
running REA over an optimised Rust binary; the design, the vocabulary and
the semantics are Bun's own.

- **A graph, not a seventh private lowering.**  `bun/antar.py` lowers
  `if`, `else if`, `while`, `for ... in range(...)`, `break`, `continue`
  and `return` into `khand` (straight-line blocks) that end in exactly one
  `nirnaya` (terminator): `ja`, `chunav`, `laut`, `samaapt` or `viram`.
  Short-circuit `and`/`or` in a condition becomes a chain of khand, so the
  short circuit is visible in the graph instead of hidden in an evaluator.
- **A verifier that runs before the engine.**  `verify()` checks that every
  khand has one terminator, that every edge names a khand that exists, that
  a `chunav` has both targets, that the entry exists, and that every action
  is known.  A dead khand is reported as `dead` in the stats, never deleted
  silently.
- **The three questions every later stage asks.**  `predecessors()`,
  `reverse_postorder()` and `dominators()` are computed on the graph, and
  `loops()` finds natural loops from back edges (`h` dominates `n` for an
  edge `n -> h`).  These are the queries Rust's `CfgCache` caches; Bun
  answers them on its own graph in pure Python.
- **A seventh engine.**  `bun --engine antar` walks the graph: a khand runs
  in order and control leaves only through its nirnaya.  Expressions are
  evaluated by the same evaluator the tree engine uses, and a call to a
  function of the program runs that function's own `pravah`, so the call
  stack is a stack of graphs.  `tree`, `vm`, `register` and `antar` agree
  on `tools/maturity/antar_core.bun` — a `gcd` loop, an `else if` chain, a
  labelled `for` with `break` and `continue`, a recursive `fib` and a
  short-circuit condition.
- **A command that shows the shape.**  `bun antar file.bun` prints the
  graph, `--json` gives blocks, edges, reverse postorder and loops, `--dot`
  gives Graphviz, `--verify` gives the structural report and `--stats`
  gives the counts.  The command never runs the program.
- **Refusals by name.**  `for` over anything but `range(...)`, a dynamic
  `range` step, `try`, `match`, `with`, generators, structs, enums,
  protocols, impls, imports, and assignment to a field or an index are
  refused with `Unsupported("antar", ...)`.  One semantic difference is
  documented: a `pravah` has one environment, so block scoping belongs to
  `--engine vm`.
- **What was read and what was measured.**  `docs/reference/antar.md`
  quotes the Rust MIR definitions the principle rests on (file and line),
  and records the REA run over `rustc -O` output: ELF x86_64, 684
  procedures, `main::main` at `0x1143e0` and `main` at `0x1147a0`, and the
  ambiguity refusal that made the design choose honest refusal over
  approximate lowering.  Optimisation removes instructions, not
  control-flow shape.
- **A live subject, checked honestly.** `bun:hawking_page` applies SUTRA to
  the Hawking–Page transition: a two-branch free energy, `Tc = 3/(2 pi L)`,
  and four models that differ only in signs. It measures `Tc ~ L^-1`,
  `S ~ T^3` and a slope jump of `4 k V Tc^3`, certifies six checks, and
  keeps the 2003 small-universe question `UNRESOLVED` and the 2026 preprint
  `UNVERIFIED`. The fourth check is *direction*, because a shape classifier
  cannot see a sign: `+T^4` and `-T^4` move identically.
- **`lang_table(code)` is a real builtin.** It was a host-only helper for the
  Bun-written front end; it is now in `builtins.py`, `types.py` and the docs
  registry, so the Python checker and the self-hosted checker agree on
  `selfhost/checker.bun` again.

## 0.5.0 — 2026-11-10 (shipped inside v0.6.0)

The engine wave.  It closes the last two open capabilities of the 2026-11-08
maturity ledger with working code, so the measured score goes from `98/100`
to `100/100` and `E` (runtime and engines) is `10/10`.  Nothing in the ledger
was weakened: E06 and E07 now run a real Bun program of the integer core, and
the two `test_maturity.py` guards that used to lock the gaps in now lock the
closed ledger in instead.

- **A binary WebAssembly backend, and Bun's own WebAssembly machine.**
  `bun/wasm.py` emits an actual `.wasm` module — type, import, function,
  memory, export, code and data sections, with LEB128 lengths and a data
  segment whose offset is an `i32.const`.  It is not WAT text: `bun compile
  --target wasm` writes bytes that begin `0061736d`, and the H07 probe checks
  that exact magic.  `bun/wasmvm.py` decodes those bytes and executes them on
  a machine Bun owns, with host imports `print_i64`, `print_bool` and
  `print_str`.  Two hidden helper functions make `/` and `%` obey Bun's
  floor-division semantics rather than WebAssembly's truncation-toward-zero
  semantics.  The module passed `WebAssembly.validate` in Node/V8.
- **A native x86-64 JIT.**  `bun/jit.py` emits machine code into an `mmap`
  region with `PROT_READ|PROT_WRITE|PROT_EXEC` and calls it through
  `ctypes.CFUNCTYPE`.  It handles local slots, function calls, loops,
  strings, shifts, division, modulo and short-circuit operands; callbacks are
  kept alive for the whole run.  The JIT is listed as available only on an
  x86-64 host.
- **One shared integer core, not two dialects.**  `bun/intcore.py` holds the
  parts the two native backends must agree on: how `range(...)` is read, the
  static type of an expression, and the `Unsupported` refusal that names the
  construct a backend does not implement.  Both engines run
  `tools/maturity/engine_core.bun` — a `gcd` function, a mutable accumulator
  in a loop, and arithmetic — and both print `6` and `385`.
- **Module-level localized keywords in the Bun-written front end.**  A
  `#lang:`, `#lang ` or `#!lang ` prefix at the top of a file now selects the
  language pack for that module.  A `lang_table` builtin (host-provided in
  0.5.0, a normal builtin since 0.6.0) and `selfhost/checker.bun`'s
  `module_lang` / `tokenize_module` let the self-hosted checker read the same
  keyword table as the Python lexer.
- **Honest scope.**  WASM and JIT implement the integer core, not the whole
  language; a program outside that core is refused with a diagnostic that
  names the missing construct, and `tests/test_engine_core.py` measures that
  refusal.  `100/100` means all 100 gaps measured on 2026-11-08 are closed
  with working code; it does not mean the language is finished.

`tests/test_engine_core.py` adds 23 tests over the binary emitter, the
decoder, the machine, the JIT, engine parity, the CLI dispatch and the
`Unsupported` refusal.  The full suite, the maturity probe, `bun doctor`,
`bun ci` and the independent verifier are run before the release; their
receipts are written next to the report.

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
