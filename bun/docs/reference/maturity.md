# The maturity probe

`tools/maturity_probe.py` is an executable, falsifiable progress scale for
the Bun language.  It exists because "the language is 10% done" is easy to
say and hard to measure.

## The scale

* 100 capabilities, one percent each, in 10 areas of 10 items.
* The areas are: encoding and digests, time and date, toolchain, language
  core, runtime and engines, network and services, data and formats,
  modules and packages, text, and engineering quality.
* A capability counts **only** when a real Bun program prints the expected
  answer, or a real CLI command exits with the expected output.  Nothing is
  scored because a file exists, a document mentions a name, or a checklist
  says "done".
* The expected answers are computed independently inside the probe, so the
  implementation is never asked what the right answer is.
* `selftest()` runs `print(1 + 1)` and must pass.  If the probe could not
  see a real PASS, a score of 0 would be meaningless in either direction.

The scale measures the work that was **still missing on 2026-11-08**, not
the absolute quality of the language.  A score of 84 means 84 of those 100
gaps are closed with working code; it does not mean the language is 84%
finished.

## Running it

```sh
python3.11 tools/maturity_probe.py            # human readable report
python3.11 tools/maturity_probe.py --json     # machine readable
bun maturity                                 # the same, through the CLI
bun maturity --last                          # show the last saved receipt
```

The stable verdict lines are:

```
MATURITY: 84/100 (84%)
VERDICT: MATURITY_10_PERCENT_REACHED
```

The exit status is 0 once the score reaches 10.

## Keeping the registries honest

`bun/maturity.py` is the single source of truth for the 55 standard-library
builtins added in 0.2.0.  `tools/sync_maturity.py` mirrors its table into
six places:

| File | Why it must agree |
|---|---|
| `bun/builtins.py` | runtime registration; literal `env.define(...)` lines are read by the C backend drift test |
| `bun/types.py` | checker signatures for the Python front end |
| `bun/docs.py` | the docs / API registry |
| `selfhost/docs.bun` | the Bun-written docs mirror, checked for strict parity |
| `selfhost/checker.bun` | checker signatures for the Bun-written front end |
| `bun/cbackend.py` | `LANGUAGE_BUILTINS`; new names are deliberately **not** added to `SUPPORTED_BUILTINS`, so the C backend refuses them by name |

```sh
python3.11 tools/sync_maturity.py            # idempotent; replaces marked regions
python3.11 tools/sync_maturity.py --check    # used by tests/test_maturity.py
```

Generated regions are delimited by `BEGIN GENERATED MATURITY WAVE 1` and
`END GENERATED MATURITY WAVE 1`, so running the script twice changes
nothing.

## What is deliberately not implemented

The probe does not skip anything.  In 0.2.0 the following still FAIL, and
that is an honest result, not an oversight to be hidden:

* **D01–D10** — typed error codes, `defer`, class patterns in `match`,
  nested generics, function type arguments, labelled break, string repeat,
  multiline strings, `&=`, and integer division (`//` is already the
  comment marker).
* **E01–E04** — a native `bytes` value type.  Bun currently represents
  bytes as lists of integers.
* **E06–E07** — the WASM and JIT execution engines.  `bun engines --json`
  reports both as `not-implemented`.

`compile --target wasm` emits WAT **text**, not a binary module, and says so
in its output.  `bun ci` collects the test suite rather than executing it.
`bun coverage` measures one module with the stdlib `trace` module.  `bun
audit` is a static pattern scan, not a security proof.  Every command
states its own scope.
