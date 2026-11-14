# Samanvay — coordination in Bun's own words

**समन्वय** (*samanvay*) means "coordination". This is the normative
reference of the 0.8.0 wave. It describes what the wave guarantees, what
it refuses, and how to check both.

The wave answers one question:

> When two tasks touch the same thing, which orders did the program allow,
> and can I see that order again tomorrow?

Three mechanisms answer it, and none of them is a keyword:

1. a **deterministic scheduler** — one baton, one running task, one seeded
   choice per scheduling point;
2. **happens-before** over vector clocks — a race is a missing edge, not a
   timing accident;
3. a **wait-for graph** — a deadlock is a cycle, and a blocked set with no
   cycle is still reported with every wait it contains.

## 0. The one rule

> **The seed is the replay token.**

A program that coordinates only through `bun:samanvay` produces the same
interleaving for the same seed, byte for byte, on every engine. If a run
found a race at seed 3, `--seed=3` finds it again. If a run hung at seed 7,
`--seed=7` hangs again — and now the deadlock report names the cycle.

This is the FoundationDB principle (determinism makes a failure repeatable)
applied to a language runtime instead of a database. The boundary is
stated in §8: code that synchronises through something else — a raw
`mutex`, a file, a clock — is outside the guarantee.

## 1. Vocabulary (Bun's own words)

Every word below is a function of `bun:samanvay`. No keyword was added, so
all 118 language packs can write the wave today.

| Word | Meaning | Python-side name |
|---|---|---|
| `sajha` | a shared cell | `Cell` |
| `padh` | read a cell | `Runtime.read` |
| `likh` | write a cell | `Runtime.write` |
| `tal` | a lock | `Tal` |
| `pakad` | acquire | `Runtime.acquire` |
| `chhod` | release | `Runtime.release` |
| `kanal` | a channel (capacity `n`) | `Channel` |
| `bhej` | send | `Runtime.send` |
| `le` | receive (`null` after close) | `Runtime.recv` |
| `band` | close | `Runtime.close` |
| `kary` | start a task | `Runtime.spawn` |
| `mel` | join, and re-raise the child's error | `Runtime.join` |
| `chhodo` | cancel a task | `Runtime.cancel` |
| `ajna` | an explicit scheduling point | `Runtime.checkpoint` |
| `beej` | the seed | `Scheduler(seed)` |
| `trace` | the run summary | `Runtime.summary` |
| `dwand` | a data race | `SV03` |
| `bandh` | a deadlock | `SV04` |
| `ghadi` | a vector clock | `dict[tid, int]` |

A cell is created explicitly:

```bun
import "bun:samanvay" as sv

let counter = sv.sajha(0, "counter")   // the name is for the report
let guard = sv.tal()
```

`sv.sajha` returns a handle. `sv.padh` and `sv.likh` are the only traced
accesses; a plain variable is not traced, and §2.2 says why that is a
boundary rather than an oversight.

## 2. The runtime

### 2.1 The baton

Exactly one task runs at a time. A task runs until it reaches a
coordination call; at that point the scheduler picks the next task from
the ready set with `random.Random(seed).randrange`. Two consequences:

* the interleaving is a function of `(program, seed)`, not of the OS;
* a task that never coordinates is never preempted — which is why
  `sv.ajna()` exists, to make a scheduling point explicit where the
  program wants one.

A coordination call is a scheduling point: `padh`, `likh`, `pakad`,
`chhod`, `bhej`, `le`, `band`, `ajna`. `mel` blocks until the child is
done; `kary` registers the child and returns immediately.

### 2.2 Cells, and why sharing is explicit

A `Cell` stores:

```
value        the value
last_write   (tid, clock, span) of the last write
reads        tid -> (tid, clock, span) of the last read
```

A plain variable cannot be traced without instrumenting every load and
store in every engine. The wave chooses the Rust answer instead: you can
only share what you wrapped. `Mutex<T>` makes the lock part of the type;
`sv.sajha` makes the cell part of the trace. The static pass (`SV01`)
refuses a task that writes a captured variable directly, so the boundary
is enforced rather than assumed.

### 2.3 Happens-before

Every task carries a vector clock `dict[tid, int]`. The edges are:

| Operation | Edge |
|---|---|
| `sv.kary` | parent ticks; child starts with a copy of the parent clock |
| `sv.mel` | parent merges the child's clock |
| `sv.bhej` → `sv.le` | the value carries the sender's clock; the receiver merges it |
| `sv.band` → `sv.le` | the close clock is merged on the receive |
| `sv.chhod` → `sv.pakad` | the release clock is merged on the acquire |

An access is ordered when `epoch.clock <= task.clock` pointwise. A read
that is not ordered after the last write, or a write that is not ordered
after a read, is `SV03` — with both spans, both task ids and the sentence
"neither access happens before the other".

### 2.4 Channels

* capacity `n`: `bhej` blocks while the buffer is full; `le` blocks while
  it is empty.
* capacity `0`: rendezvous. A sender waits for a receiver and hands the
  value over directly; a receiver waits for a sender.
* `band` wakes every waiting receiver; they see `null` and the close
  clock. A second `band` and a `bhej` after `band` are refused by name.
* FIFO: the buffer is a queue, and a blocked sender's value enters the
  buffer when space appears, so ordering survives the block.

### 2.5 Deadlock

When no task is ready and at least one is blocked, the scheduler builds a
wait-for graph:

* `join t` → an edge to `t`;
* `lock #n` → an edge to the task that holds `#n`.

A cycle is reported with the cycle itself (`t3 -> t4 -> t3`). No cycle but
no progress is still `SV04`, with the full blocked set and what each task
waits for — an honest report instead of a hang.

## 3. The eight codes

| Code | Name | Meaning | Kind |
|---|---|---|---|
| `SV01` | `asurakshit_lekh` | a task writes a captured variable with no coordination | static |
| `SV02` | `kary_leak` | a spawned task is never joined | static |
| `SV03` | `dwand` | two tasks touch one cell and neither happens before the other | runtime |
| `SV04` | `bandh` | no task can make progress | runtime |
| `SV05` | `kanal_dosh` | the channel is used after it was closed | static |
| `SV06` | `stale` | a task reads a value the parent writes after the spawn | static |
| `SV07` | `tal_kram` | two flows take the same two locks in opposite order | static |
| `SV08` | `kary_visfot` | a task is spawned inside a loop with no scope | static |

Every diagnostic carries a primary span, at least one labelled span, a
hint and at least one note. `verify()` fails a diagnostic that is missing
any of them, and fails a code that is not in `CODES`.

### 3.1 Why SV01 is static and SV03 is not

`SV01` is about the *shape* of the program: a write inside a task, to a
name declared outside it, with no coordination call anywhere in that task.
It can be decided without running anything, and it is the mistake that
makes the runtime detector blind (an untraced write cannot be ordered).

`SV03` is about one *execution*: the same program can race at seed 3 and
not at seed 0, because at seed 0 the two accesses happened to be ordered
by the schedule. Reporting it statically would be a lie in the other
direction. The wave reports what it measured, and the seed says which
execution it measured.

### 3.2 SV07 needs two flows

The check compares the first-use order of lock names in every top-level
function. `left` takes `a` then `b`; `right` takes `b` then `a`; one of
the two orders must change. The diagnostic points at the acquire that
breaks the order in the second flow, not at a synthetic position.

## 4. The command

```
bun samanvay <file.bun>                     # static report, never runs
bun samanvay --json|--dot|--stats|--verify|--explain <file.bun>
bun samanvay --run [--seed=N] <file.bun>    # run under the scheduler
bun samanvay --seeds=A:B <file.bun>         # sweep, report the first hit
```

* `--run` executes on the tree engine (the reference engine), because the
  trace needs the source span of every coordination call. The `vm` and
  `register` engines record spans too; the tree engine is used so the run
  has one definition.
* `--seeds=A:B` runs the program once per seed, prints one line per seed,
  and exits 1 if any seed produced a race or a deadlock.
* Exit status: 0 when clean, 1 when a nidan, a race or a deadlock was
  found, 2 for a usage error.

Example:

```
$ bun samanvay --seeds=0:8 examples/samanvay_race.bun
seed 0    races=1 deadlocks=0 steps=7    hash=fcad8155d495b0e7
...
SAMANVAY SWEEP: 9 seed(s), 9 with findings, first 0
```

## 5. The library half

`lib/bun/samanvay.bun` is written in Bun. It re-exports the builtins
under the wave's names, so `sv.padh(cell)` is a direct builtin call at the
caller's line — that is why the trace points at the program and not at the
library. It also carries:

* `niyam()` — eight rule dicts, the mirror of `RULES` in
  `bun/samanvay.py`;
* `codes()` — eight code dicts, the mirror of `CODES`;
* `audit()` — eight falsifiable checks with real calls (a cell roundtrip,
  a lock, a channel, a spawned task that is joined, the step counter, the
  schedule hash, its own race-freedom, and the 8 + 8 ledger);
* `ledger()` — runs `audit()` and prints `SAMANVAY_LEDGER_CERTIFIED 8/8`.

## 6. What the scheduler does not promise

* **Fairness.** The seeded choice may starve a task for a long time. The
  step limit (`200000`) turns starvation into a report instead of a hang.
* **Wall-clock behaviour.** `sleep`, `now` and I/O are not scheduling
  points and not part of the replay. A program that reads the clock is
  deterministic only up to that read.
* **Memory-model completeness.** Only `sajha` cells, channels and locks
  create edges. A raw `mutex()` from the pre-0.8 builtins is invisible to
  the detector.

## 7. What the static pass does not see

The pass reads the syntax tree, not the call graph. A task that writes a
captured variable only through a helper function called from the task is
not `SV01`; the runtime detector still sees it if the write goes through
`sv.likh`. This is stated here so that a clean static report is not read
as a proof of safety.

## 8. Boundary: `antar` and the engines

The deterministic scheduler runs task bodies on the machine that compiled
them: `Interpreter` for the tree engine, `VM` for stack bytecode,
`RegisterVM` for register bytecode. A body compiled by the register engine
carries `consts`, and the VM cannot execute a `CONST` op — the wave
detects the flavour instead of assuming the VM, which is also the fix for
the same assumption in the pre-0.8 `spawn` path.

The `antar` engine has no `sv.*` support: it refuses the wave's statements
by name, like it refuses `with`. This is a boundary, not a defect.

## 9. Reproducible commands

```bash
cd bun

python3 -m bun examples/samanvay.bun                     # SAMANVAY PIPELINE OK
python3 -m bun examples/samanvay_hi.bun                  # byte-identical
BUN_SAMANVAY_SEED=3 python3 -m bun examples/samanvay_race.bun   # counter 1

python3 -m bun samanvay examples/samanvay.bun            # SAMANVAY: OK
python3 -m bun samanvay --json examples/samanvay.bun
python3 -m bun samanvay --dot examples/samanvay.bun
python3 -m bun samanvay --stats examples/samanvay.bun
python3 -m bun samanvay --verify examples/samanvay.bun
python3 -m bun samanvay --explain examples/samanvay.bun
python3 -m bun samanvay --run --seed=3 examples/samanvay_race.bun
python3 -m bun samanvay --seeds=0:8 examples/samanvay_race.bun

python3.11 tools/verify_samanvay.py                      # external checks
python3 -m pytest tests/test_samanvay.py -q
```

## 10. Why this shape

Three sources shaped the design, and none of them is copied:

* **ThreadSanitizer** computes happens-before from vector clocks and
  reports a race with two stacks. Bun keeps the algorithm and the shape of
  the report (two spans, one sentence) but computes it on its own trace.
* **Structured concurrency** (Sústrik's term, Smith's popularisation, Java's
  `StructuredTaskScope`, Python's `TaskGroup`) says subtasks return to the
  block that started them. Bun already had `scope { ... }`; the wave adds
  the part that was missing — `SV02` refuses a task that escapes it.
* **Deterministic simulation** (FoundationDB) says a failure must be
  repeatable. Bun makes the seed the token, so the repeat is one flag.

The vocabulary is Bun's own; the principles are named where they came
from. That is the same rule as Raksha: **原理借用、语法未借用** — the
principle is borrowed, the syntax is not.
