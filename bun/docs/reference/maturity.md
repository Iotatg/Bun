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
the absolute quality of the language.  A score of 100 means all 100 of those
gaps are closed with working code; it does not mean the language is 100%
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
MATURITY: 100/100 (100%)
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
division via `div`) now PASS because the language really does them; at the
time the rest FAIL with a diagnostic naming the exact construct that is
absent.  No ledger entry was edited to hide a failure.  `tests/test_maturity.py`
asserts that no `*_probe()` helper call remains; its companion guard, which
used to assert the exact failing set, now asserts that the ledger has **no**
undocumented failure at all.

## Closed in 0.4.0

The four language gaps that 0.3.0 left open are now real capabilities, and
each one is written in Bun's own surface syntax:

* **D02** — `on leave { ... }`, a block that runs when control leaves the
  enclosing block.  It runs on a normal end, a `return`, a `break`, or a
  `throw`, in the reverse order of registration.  The parser lowers it to
  `try`/`finally`, so no engine needed a new instruction.
* **D04** — nested type arguments, written `list of list of int` (the
  bracket form `list<list<int>>` still works).
* **D05** — a function type as a parameter, e.g. `fn(int) -> int`.
* **D06** — a named loop, `for i in range(3) as outer { ... }`, with
  `break outer` and `continue outer`.  The older `outer: for` form is
  still accepted.

## Instrument repair (0.4.0)

The 0.3.0 D02 probe expected `"1\nbye"`, but a scope-exit action runs
before the caller sees the return value, so the only correct output is
`"bye\n1"`.  The probe asked for an order no correct implementation can
produce; it was a measuring error, not a language gap.  0.4.0 fixes the
expected value and uses the Bun form of the construct.

## Closed in 0.5.0

The last two gaps are now real engines, measured by a real program:

* **E06** — `bun/wasm.py` emits a binary WebAssembly module (the H07 probe
  checks the `0061736d` magic) and `bun/wasmvm.py` decodes and runs it on
  Bun's own machine.  `compile --target wasm` writes a `.wasm` file instead
  of WAT text.
* **E07** — `bun/jit.py` emits and executes x86-64 machine code through an
  executable `mmap` region and `ctypes`.  `bun engines --json` reports it as
  available on an x86-64 host and explains why it is unavailable elsewhere.

Both run `tools/maturity/engine_core.bun`, a `gcd` function plus a loop with
a mutable accumulator, and both print `6` and `385`.  They share
`bun/intcore.py` so that `range`, expression types and the `Unsupported`
refusal cannot drift between them.  `tests/test_engine_core.py` measures the
binary emitter, the decoder, the machine, the JIT, their parity with the
stack VM, and their refusal of a program outside the integer core.

## What is deliberately not implemented

The probe does not skip anything; it now has no failing entry.  Honest scope
limits remain, and each is stated by the command or engine that owns it:

* The WASM and JIT engines implement the **integer core**, not the whole
  language.  A construct outside it is refused with a diagnostic that names
  it, rather than being silently miscompiled.
* `bun ci` collects the test suite rather than executing it, `bun coverage`
  measures one module with the stdlib `trace` module, and `bun audit` is a
  static pattern scan, not a security proof.
* The ledger measures the 100 gaps of 2026-11-08.  Closing all 100 does not
  close the language; it closes that ledger.
