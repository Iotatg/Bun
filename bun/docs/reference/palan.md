# Palan — resilience in Bun's own words

**Palan** (पालन, "nurture") is the 0.9.0 wave. It answers the question the
concurrency wave left open: *a task died. What happens next, and can I make
that death repeatable?*

The wave has two halves:

* a **virtual clock** and a **seeded die**, which are builtins because only
  the scheduler may move time or decide a failure;
* a **policy** — supervisors, retry, circuit breaker — written in Bun, in
  `lib/bun/palan.bun`.

Everything is reached through `bun:palan`, and nothing is a keyword.

---

## 0. The one rule

> A failure is a fact about a *schedule*, not about a machine.

If a program fails, the failure must be expressible as "at tick T, task N
failed", and that sentence must be true again tomorrow. Every design
decision below follows from this.

---

## 1. Vocabulary

| Word | Meaning | Kind |
|---|---|---|
| `sona(n)` | sleep for `n` ticks | builtin |
| `abhi()` | the current tick | builtin |
| `avadhi(n)` | set a deadline `n` ticks from now | builtin |
| `jaanch()` | check the deadline; raises if passed | builtin |
| `sankat(p)` | the program may fail with probability `p` | builtin |
| `jokhim()` | roll the die; `true` means "fail now" | builtin |
| `chunav(n)` | a deterministic integer in `[0, n)` | builtin |
| `rakshak(strategy, budget, window)` | make a supervisor | library |
| `baccha(sup, fn, name)` | add a child | library |
| `chalau(sup)` | run it | library |
| `punar(fn, attempts, base, cap)` | retry with backoff | library |
| `vyavdhi(threshold, cooldown)` | make a circuit breaker | library |
| `guzar(breaker, fn)` | call through it | library |
| `report()` | the runtime counters | builtin |
| `niyam()` `codes()` `audit()` `ledger()` | the ledger | library |

None of these is a keyword. All 118 language packs can write the wave on
the day it ships, and `examples/palan_hi.bun` proves it: the Hindi program
and the English one produce byte-identical output.

---

## 2. The clock

### 2.1 One tick per scheduling point

The clock starts at 0. The rule is **one tick per scheduling point**:
`sv.ajna()`,
`sv.le()` on an empty channel, `sv.mel()` on a running task, `pl.sona()`.
Nothing else moves it — not CPU time, not the wall clock, not the OS.

This is the whole trick. A program that computes for an hour without
yielding stays at tick 0, because from the scheduler's point of view
nothing happened: no other task could have run. A program that yields a
thousand times is at tick 1000, because a thousand decisions were made.

### 2.2 Sleeping

```bun
let a = pl.abhi()      // 0
pl.sona(50)
let b = pl.abhi()      // 50
```

A sleeping task is *blocked on a timer*. When no task can run, the
scheduler does not report a deadlock: it jumps the clock to the earliest
wake-up and wakes everything due. That is why `pl.sona(3_600_000)` takes
microseconds and still returns a clock that has moved an hour.

The jump is counted: `report()["wakes"]` says how many times the scheduler
had to move time because everyone was asleep.

### 2.3 Deadlines

```bun
pl.avadhi(100)         // fail after tick now+100
pl.jaanch()            // raises if the clock has passed it
```

A deadline is a **check**, not an alarm. Bun will not interrupt a task in
the middle of an operation, because a runtime that can stop a thread
between two instructions cannot promise anything about what it left
behind. The task checks at the points where stopping is safe, and the
check is what makes the deadline real.

The static pass reports a deadline with no check as `PL03`, because that is
the failure mode that actually happens: someone writes `avadhi` and forgets
`jaanch`, and the deadline is decoration.

### 2.4 What the clock does not promise

| Not promised | Why |
|---|---|
| real elapsed time | the clock counts decisions, not nanoseconds |
| monotonic across runs with different seeds | different schedules, different tick counts — by design |
| a timeout that fires during a non-yielding loop | the clock only moves when the task yields |

A program that needs real time (a heartbeat, a rate limiter against a
remote server) must not use this clock. That is stated here, in the
reference, rather than discovered in production.

---

## 3. The die

```bun
pl.sankat(0.35)        // this program may fail 35% of the time
if pl.jokhim() { throw "E_IO: read failed" }
```

`jokhim()` is `true` with probability `p`, and the answer is derived from
`(seed, task id, roll index)`. Consequences:

* the same seed and the same program give the same sequence of answers;
* two tasks rolling at the same moment get *different* answers, because the
  task id is in the key;
* adding a roll changes every later roll in that task — a roll is a
  position in a stream, not a hash of the source line.

`chunav(n)` draws from a **separate** stream, so adding a jitter call
inside a backoff cannot change which read fails. That separation is not an
implementation detail; it is what keeps two unrelated policies from
perturbing each other's replay.

The probability is program-wide (`sankat` describes the world, not one
task), the roll is per task.

---

## 4. Supervisors

### 4.1 A supervisor is a value

```bun
let sup = pl.rakshak("ek", 3, 2000)   // strategy, budget, window
pl.baccha(sup, worker, "worker")
let r = pl.chalau(sup)                // {rounds, restarts, log, children}
```

Nothing starts until `chalau`. That is deliberate: a supervisor tree is a
data structure a test can build, inspect and compare before anything runs.

### 4.2 Strategies

| Strategy | On a child failure |
|---|---|
| `"ek"` (one) | restart the failed child only |
| `"sab"` (all) | join every live sibling, then start all children again |
| `"baad"` (rest) | join the children after the failed one, then restart the failed child and those after it |

These are OTP's `one_for_one`, `one_for_all` and `rest_for_one`. The
difference is written down in `research/failure_semantics.md` §1: **Bun joins, it does not kill.** A supervisor that killed its children would need
every child to reach a checkpoint, and a child that never yields could not
be killed at all.

### 4.3 The budget is a window, not a total

`rakshak(strategy, budget, window)` allows `budget` restarts inside
`window` ticks. The count starts again when the clock has moved past the
window. This is OTP's `intensity` per `period`, measured on the virtual
clock instead of `monotonic_time` — which is what makes "two restarts in
twenty ticks" a reproducible statement.

When the budget is exhausted the supervisor **escalates**: it records
`PL07` and throws

```
palan: supervisor escalated after N restarts in M ticks
```

The wave does not escalate to a parent automatically. A supervisor raises;
who catches it is the program's decision, and `examples/palan.bun` shows
the decision being made.

### 4.4 Backoff before restart

A restart waits `1, 2, 4, … 64` ticks plus a deterministic jitter of up to
half that. The jitter comes from `chunav`, so it is decorrelated across
supervisors and identical across runs.

---

## 5. Retry

```bun
let value = pl.punar(fetch, 3, 2, 16)
//                  fn   attempts base cap
```

`attempts` counts the **first try**. `attempts = 1` is a loop that runs
once, which is why the static pass calls it `PL02`.

The wait is `base * backoff(n)`, capped at `cap`. The last failure is
re-raised unchanged, so the caller sees the error the child produced, not a
wrapper.

`punar` does not decide what is retryable. That is the caller's job: a
retry of a write that already happened is a duplicate, and no amount of
backoff makes it safe. (The static pass cannot see this either; it is
listed in §8.)

---

## 6. Circuit breakers

```bun
let disk = pl.vyavdhi(4, 25)          // threshold, cooldown in ticks
let n = pl.guzar(disk, read_one)      // call through it
```

| State | Name | Behaviour |
|---|---|---|
| closed | `band` | calls pass, failures counted |
| open | `khula` | calls are refused until the cooldown elapses |
| half-open | `aadha` | one trial call decides: success closes, failure re-opens |

A refusal raises `palan: circuit breaker is open` and records `PL08`. The
breaker counts *consecutive* failures: a success resets the counter.

The cooldown is measured on the virtual clock, so a breaker that opens at
tick 40 and has a 25-tick cooldown is guaranteed to allow a trial at tick
65 — on every machine, in every run with that seed.

---

## 7. The eight codes

| Code | Name | When | Kind |
|---|---|---|---|
| `PL01` | rikt rakshak | a supervisor with no children | static |
| `PL02` | vyarth punar | `punar` with `attempts <= 1` | static |
| `PL03` | anaavashyak avadhi | `avadhi` in a function with no `jaanch` | static |
| `PL04` | shunya budget | `rakshak` with `budget = 0` | static |
| `PL05` | tal mein sona | `sona` while a `sv.tal` lock is held | static |
| `PL06` | kabhi band | `vyavdhi` with `cooldown = 0` | static |
| `PL07` | budget khatam | a supervisor exhausted its budget | runtime |
| `PL08` | vyavdhan khula | a call was refused by an open breaker | runtime |

Every diagnostic carries a primary span, labelled spans, a hint and notes —
the same shape as Raksha's and Samanvay's, rendered by the same renderer.

### 7.1 Why PL05 needs both modules

`PL05` reads `sv.pakad` / `sv.chhod` and `pl.sona` in source order inside
one function and keeps a depth counter. A sleep while the depth is positive
is a sleep under a lock: the virtual clock advances while every other task
that wants the lock is blocked, which is the cheapest way to turn a slow
task into a stalled system.

The check is textual, not flow-sensitive. A lock acquired in one branch and
released in another is counted as held. That is the conservative direction,
and it is stated in §8.

### 7.2 What is runtime and what is not

`PL07` and `PL08` cannot be static: whether a budget runs out or a breaker
opens depends on which calls failed, and that is the schedule. The static
pass reports the *shape* (a budget of 0, a cooldown of 0); the run reports
the *event*.

---

## 8. What the static pass does not see

* **Retry safety.** `punar` around a write that is not idempotent is a
  duplicate waiting to happen. The pass knows the attempts, not the effect.
* **A lock held across a call.** `PL05` sees `pakad`/`sona` in one
  function. A sleep inside a function called under a lock is invisible.
* **A deadline checked somewhere else.** `PL03` requires the check in the
  same function. A `jaanch` in a helper silences the call site, not the
  helper.
* **Supervisor trees built at run time.** A supervisor created inside a
  loop, or passed as a parameter, is not bound to a name the pass can
  follow; `baccha` calls it cannot resolve suppress `PL01` rather than
  guess.
* **Whether a child is worth restarting.** A supervisor restarts a child
  that fails because its input is invalid, forever, until the budget runs
  out. That is the budget's job, not the analyzer's.

---

## 9. The command

```bash
bun palan examples/palan.bun                  # the static report
bun palan --json  examples/palan.bun          # the same, for a tool
bun palan --dot   examples/palan.bun          # the supervisor tree
bun palan --stats examples/palan.bun          # counters only
bun palan --verify examples/palan.bun         # exit 1 on a nidan
bun palan --explain examples/palan.bun        # the eight principles
bun palan --run --seed=7 examples/palan.bun   # run one world
bun palan --chaos=0:15 examples/palan.bun     # sixteen worlds, one table
```

Without `--run` the command never executes the program. With `--run` it
executes it on the tree engine under the deterministic scheduler and prints
the clock, the sleeps, the rolls, the failures and any runtime finding.
`--chaos=A:B` prints one line per seed; two seeds that print the same line
produced the same run.

---

## 10. The library half

`lib/bun/palan.bun` is the policy, in Bun:

* `rakshak` / `baccha` / `chalau` — the supervisor;
* `punar` — retry;
* `vyavdhi` / `guzar` — the breaker;
* `niyam()` / `codes()` — the ledger, mirrored one-to-one by `bun/palan.py`;
* `audit()` — eight claims, each proved by a real call, including its own
  escalation and its own open breaker;
* `ledger()` — prints `PALAN_LEDGER_CERTIFIED 8/8`.

The clock and the die are builtins because only the scheduler may move
virtual time or decide a failure. Everything else is a Bun program, and it
is checked by the same interpreter as the program that uses it.

---

## 11. Boundary

* **Samanvay.** Palan borrows the scheduler, the seed and the task ids. It
  does not have a second clock, because a second clock would be a second
  truth. `pl.sona` inside a `sv.pakad`/`sv.chhod` pair is `PL05` for
  exactly that reason.
* **Raksha.** Nothing in Palan allocates a capability; the wave is about
  what happens after something fails, not about how memory is held.
* **The engines.** `tree`, `vm` and `register` produce byte-identical
  output for `examples/palan.bun` at the same seed. The task body is run by
  the machine that compiled it (the 0.8.0 fix), so a supervisor works the
  same way on all three.

---

## 12. Reproducible commands

```bash
python3 -m bun examples/palan.bun                    # one world (seed 0)
python3 -m bun examples/palan_hi.bun                 # byte-identical, Hindi
python3 -m bun palan examples/palan.bun              # static report
python3 -m bun palan --chaos=0:15 examples/palan.bun # sixteen worlds
python3 -m bun --engine register examples/palan.bun  # the same bytes
python3 -m bun - <<'EOF'
import "bun:palan" as pl
pl.sona(3600000)
print(pl.abhi())
EOF
```

The last one prints `3600000` and returns in microseconds. That is the
whole wave in one command: an hour of backoff, no hour.

---

## 13. Why this shape

A resilience library is easy to write and hard to trust. The usual version
is a pile of timers, and the reason nobody trusts it is that a timer is the
one thing a test cannot control.

Bun already had the unusual part — a scheduler that makes an interleaving a
value. Palan spends it: the clock becomes a counter, the failure becomes a
roll, and the whole policy becomes a program that a seed can replay. The
library is then small enough to audit, and the audit is a program that
prints its own score.
