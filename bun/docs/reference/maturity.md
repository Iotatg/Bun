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
the absolute quality of the language.  A score of 94 means 94 of those 100
gaps are closed with working code; it does not mean the language is 94%
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
MATURITY: 94/100 (94%)
VERDICT: MATURITY_10_PERCENT_REACHED
```

The exit status is 0 once the score reaches 10.

## Keeping the registries honest

`bun/maturity.py` is the single source of truth for the standard-library
builtins: 55 added in 0.2.0 and 9 more in 0.3.0, **64 in total**.  The nine
0.3.0 builtins back the native `bytes` value type and typed error values.
`tools/sync_maturity.py` mirrors its table into six places:

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

## Instrument repair (0.3.0)

A capability is only meaningful if its probe is a real measurement.  In the
0.2.0 ledger seven D-area probes were broken measuring devices rather than
capability tests: five called undefined `*_probe()` helpers, one used the
invalid `fn f(): int` form, and one used `//`, which is Bun's line-comment
marker.  A broken probe cannot distinguish "the feature is missing" from
"the probe is wrong" — it is the same trap as counting *written* tests as
*executed* tests.

0.3.0 replaces each with a real Bun program that attempts the actual syntax.
Three capabilities (class patterns in `match`, multiline strings, and floor
division via `div`) now PASS because the language really does them; the rest
FAIL with a diagnostic naming the exact construct that is absent.  No ledger
entry was edited to hide a failure.  `tests/test_maturity.py` asserts that no
`*_probe()` helper call remains, and that the failing set is exactly the six
documented gaps below.

## What is deliberately not implemented

The probe does not skip anything.  Six capabilities still FAIL, and that is
an honest result, not an oversight to be hidden:

* **D02** — `defer` (run a statement at scope exit).
* **D04** — nested generic type arguments such as `list<list<int>>`.
* **D05** — a function type used as a type argument, e.g. `fn(int) -> int`.
* **D06** — labelled `break` out of a nested loop.
* **E06–E07** — the WASM and JIT execution engines.  `bun engines --json`
  reports both as `not-implemented`; the CLI refuses to run on them with a
  specific error.  `compile --target wasm` emits WAT **text**, not a binary
  module or a runnable engine, and says so in its output.

Each of these is probed with real syntax or a real CLI attempt, so the FAIL
measures a genuine gap.  Other honest scope limits remain: `bun ci` collects
the test suite rather than executing it, `bun coverage` measures one module
with the stdlib `trace` module, and `bun audit` is a static pattern scan,
not a security proof.  Every command states its own scope.
