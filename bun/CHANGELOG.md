# Changelog

All notable changes to the Bun language are recorded here.  The version
number is the one `bun version` prints; a release is only made after the
full test suite passes and the maturity probe has written a real receipt.

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
