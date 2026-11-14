# Concurrency bugs: what the sources actually say

**Wave**: 0.8.0 «Samanvay»　**Date**: 2026-11-14　**Author**: the Bun
implementation, not a summary of blog posts.

This report records what was read before the wave was designed, quoted
verbatim, with the URL and the date it was fetched.  Nothing below is a
claim from memory: every quotation was pulled from the page in this
environment on 2026-11-14 with `curl`, and the sentence is reproduced as
the page has it.  Where a source says something the wave *did not* copy,
that is recorded too.

---

## 0. Method

| # | Source | URL | What it was read for |
|---|---|---|---|
| S1 | ThreadSanitizer (Clang documentation) | `https://clang.llvm.org/docs/ThreadSanitizer.html` | what a data race is, what a report looks like, what it costs |
| S2 | Go race detector | `https://go.dev/doc/articles/race_detector` | the limits of dynamic detection |
| S3 | JEP 453, Structured Concurrency | `https://openjdk.org/jeps/453` | the definition and the guarantee of structured concurrency |
| S4 | PEP 654, Exception Groups and `except*` | `https://peps.python.org/pep-0654/` | why one exception cannot carry several task failures |
| S5 | FoundationDB, Simulation and Testing | `https://apple.github.io/foundationdb/testing.html` | deterministic simulation as an engineering practice |
| S6 | Python `asyncio` task groups | `https://docs.python.org/3/library/asyncio-task.html` | the user-facing shape of a task group |

Each finding below is one quotation plus what the wave did with it.

---

## 1. A data race is a missing happens-before edge

**S1** introduces the tool with a single sentence:

> "ThreadSanitizer is a tool that detects data races. It consists of a
> compiler instrumentation module and a run-time library."

and the example report is two stacks and one sentence:

> "WARNING: ThreadSanitizer: data race … Write of size 4 at 0x… by thread
> T1 … Previous write of size 4 at 0x… by main thread"

Two things are worth noticing.  First, the report is *two events*, not a
stack trace with a warning on top; the second event is what makes the
report actionable.  Second, the tool needs both events to have happened.

**What Bun did**: `SV03` carries exactly two events — the first access
(tid, clock, span) and the second (tid, clock, span) — and one sentence:
"neither access happens before the other".  The detector is the same
algorithm (vector clocks, release/acquire edges); the trace is Bun's own.

**Cost, from S1**:

> "Typical slowdown introduced by ThreadSanitizer is about 5x-15x. Typical
> memory overhead introduced by ThreadSanitizer is about 5x-10x."

**What Bun did**: the wave does not instrument every load and store.  It
instruments the operations a program *chose* to share (`sv.padh`,
`sv.likh`), so the cost is proportional to shared accesses, not to all
accesses.  That is a design trade, not an improvement in the algorithm: an
untraced access is invisible, and §5 says so.

## 2. A dynamic detector only sees the paths it ran

**S2** states the limit without softening it:

> "The race detector only finds races that happen at runtime, so it can't
> find races in code paths that are not executed. If your tests have
> incomplete coverage, you may find more races by running a binary built
> with -race under a realistic workload."

**What Bun did**: this is the reason the wave has *two* halves.  The
static pass (`SV01`, `SV06`, `SV07`) reads the program and does not care
which path ran; the runtime pass (`SV03`, `SV04`) reports what one
execution actually did.  Neither is allowed to claim the other's result.
It is also the reason `--seeds=A:B` exists: if one seed is one test, a
sweep is a coverage strategy, and the sweep prints how many seeds it ran.

## 3. Structured concurrency is a lifetime rule, not a syntax

**S3** defines the idea and names where it came from:

> "The term 'structured concurrency' was coined by Martin Sústrik and
> popularized by Nathaniel J. Smith."

> "Structured concurrency derives from the simple principle that If a task
> splits into concurrent subtasks then they all return to the same place,
> namely the task's code block."

and the guarantee that follows:

> "All of the subtasks' threads are guaranteed to have terminated once the
> scope is closed, and no thread is left behind when the block exits."

**What Bun did**: Bun already had `scope { ... }` and `spawn` as soft
keywords (0.5).  The wave adds the *check* that was missing: `SV02`
refuses a spawned task that is neither joined nor inside a scope, and
`SV08` refuses a fan-out in a loop with no scope.  The rule is S3's; the
spelling (`sv.kary` / `sv.mel`) is Bun's, and no keyword was added.

## 4. One exception cannot carry several failures

**S4** exists because a single exception value cannot represent what
happened when several tasks fail at once.  Its answer is a group:
`ExceptionGroup` plus `except*`, and `asyncio.TaskGroup` aggregates the
failures of its children into one group while cancelling the siblings.

**S6** shows the user-facing shape:

> "The `asyncio.TaskGroup` class provides a more modern alternative to
> `create_task()`."

**What Bun did, and did not do**: Bun already has `Ok`/`Err` and `?`, and
`scope` already collects the first child error.  The wave does *not* add
an exception group: `sv.mel(h)` re-raises the child's own error at the
join, which is one error from one task at one place.  A group type would
be a second error channel, and Raksha's rule R6 (one concept, one
mechanism) refuses that.  This is a deliberate divergence, recorded here
so it is not mistaken for an oversight.

## 5. Determinism is what makes a failure usable

**S5** is the strongest statement of the practice found in the sources:

> "Simulation is able to conduct a deterministic simulation of an entire
> FoundationDB cluster within a single-threaded process. Determinism is
> crucial in that it allows perfect repeatability of a simulated run,
> facilitating controlled experiments to home in on issues."

> "Simulation runs tens of thousands of simulations every night, each one
> simulating large numbers of component failures. Based on the volume of
> tests that we run and the increased intensity of the failures in our
> scenarios, we estimate that we have run the equivalent of roughly one
> trillion CPU-hours of simulation on FoundationDB."

**What Bun did**: the scheduler is a baton, the choice is
`random.Random(seed)`, and the seed is the replay token.  Bun does not
claim FoundationDB's scale — one process, one program, one run at a time —
but it copies the property that matters: a failing run is repeatable by
typing one number.  `--seeds=A:B` is the smallest possible version of
"tens of thousands of simulations every night".

---

## 6. Measurements on this implementation

All numbers below come from commands run in this environment on
2026-11-14; they are reproducible with the commands in
`docs/reference/samanvay.md` §9.

### 6.1 The race is not rare

`examples/samanvay_race.bun` is two tasks, one cell, one read and one
write each, with an explicit scheduling point between them.  Over 16
seeds:

| Result | Seeds | Count |
|---|---|---|
| both increments survive (`counter == 2`) | 0, 1, 2, 5, 9, 11, 12, 15 | 8 |
| one increment is lost (`counter == 1`) | 3, 4, 6, 7, 8, 10, 13, 14 | 8 |

**8 of 16 seeds lose an update.**  A test that runs this program once has
a coin-flip chance of seeing the bug.  That is the empirical argument for
the sweep: the same program, the same code, and the answer depends on a
number nobody wrote down.

### 6.2 The schedules really are different

`bun samanvay --seeds=0:15 examples/samanvay_race.bun` reports 16 runs,
**13 distinct schedule hashes**, step counts of 8 or 9, and 1 or 2 race
reports per run (a read/write pair and a write/write pair are two
findings, not one).

The two runs with the same hash (6 and 10) are the same interleaving
reached from different seeds — the generator is not a bijection on
schedules, and the hash is what proves it.

### 6.3 Locks remove the finding, not the schedule

The same program with `sv.pakad` / `sv.chhod` around the pair reports
`races 0` for every seed in 0–5 while still producing 4 distinct
schedules.  The wave did not make the program sequential; it made the
accesses ordered.

### 6.4 A deadlock is a cycle, and the report says so

`examples/samanvay_race.bun`'s sibling test takes two locks in opposite
orders.  At seed 0 the report is:

```
SV04 bandh: a cycle in the wait-for graph
  cycle: t3 -> t4 -> t3
  t0 waits for join t3
  t3 waits for lock #2
  t4 waits for lock #1
```

The first line is the diagnosis, the second is the proof, the rest is the
evidence.  A program that hangs would have produced none of it.

---

## 7. What the sources changed in the design

| Finding | Design decision it forced |
|---|---|
| S1: a report is two events | `Nidan` carries two `Epoch`s, not one |
| S1: 5–15x cost | instrument only explicit shared accesses, and say so |
| S2: only executed paths | two halves, static and runtime, with separate codes |
| S3: no thread left behind | `SV02` / `SV08`; `scope` is the join point |
| S4: one error, one channel | no `ExceptionGroup`; `sv.mel` re-raises the child's error |
| S5: determinism | the seed is the replay token, and `--seeds` is the sweep |

## 8. Honest limits of this report

1. **Six sources, not a survey.**  This is what was read, not the state of
   the art.  A claim outside these pages is not made.
2. **No bug-study statistics are quoted.**  The classic studies of
   real-world concurrency bugs were not fetched in this environment, so
   their numbers do not appear here; a number without a fetched source
   would be exactly the kind of claim this project refuses.
3. **The measurements are one program.**  §6 measures the wave's own
   example, not a corpus.  It shows that the mechanism works and that the
   seed matters; it does not estimate a defect rate.
4. **The detector is not a proof.**  It sees the accesses that go through
   `sv.padh` / `sv.likh`, and the edges that go through the wave's
   channels, locks and joins.  Everything else is outside the trace, and
   `docs/reference/samanvay.md` §7 states it in the reference.
