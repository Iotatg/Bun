# Failure semantics: what the 0.9.0 wave borrows, and what it refuses

Palan (पालन, "nurture") is the resilience wave. It answers the question
0.8.0 left open: *a task died — now what, and can I make that death
repeatable?*

This note records the sources the wave was built against, the sentence each
one contributed, and the sentence each one was **not** allowed to
contribute. Every quotation below was fetched from the URL shown beside it
on 2026-11-14.

---

## 1. Erlang/OTP: supervision is a tree with a budget

> "`strategy` specifies the restart strategy. `intensity` and `period`
> specify the maximum restart intensity."
> — <https://www.erlang.org/doc/design_principles/sup_princ.html>

> "`strategy() = one_for_all | one_for_one | rest_for_one |
> simple_one_for_one`"
> — same page

> "`one_for_one`: If a child process terminates, only that process is
> restarted."
> — same page

**Borrowed.** The three strategies keep OTP's names and meanings, because
they are the right three: restart one, restart all, restart the tail. The
restart budget is `intensity` per `period`, and it is what separates a
hiccup from an outage — a child that fails once is restarted, a child that
fails forever must stop being restarted.

**Refused.** Two things.

1. **`simple_one_for_one`.** It exists in OTP to spawn identical children
   on demand. In Bun that is `sv.kary` in a loop, and 0.8.0 already reports
   the unbounded case as `SV08`. A supervisor whose child list grows at
   run time is a different object; the wave does not pretend to have it.

2. **Killing.** OTP terminates a child with `exit(Pid, shutdown)` and the
   child dies wherever it is. Bun's cancellation is cooperative: a task
   stops at its next checkpoint (`sv.ajna` or `pl.jaanch`), and a task that
   never yields cannot be stopped at all. So `sab` and `baad` **join** the
   live siblings instead of killing them. That is slower and it can block
   on a child that never finishes — and it is the honest primitive, because
   a runtime that claims to kill a task it cannot interrupt is lying.

**Where the wave differs on purpose.** The period is measured on the
*virtual* clock, not on `erlang:monotonic_time`. That is what makes a
restart budget reproducible: "two restarts inside twenty ticks" is a
statement about the schedule, not about how fast the machine happened to
be.

---

## 2. AWS: backoff needs jitter, and the jitter needs to be reproducible

> "The no-jitter exponential backoff approach is the clear loser."
> — Marc Brooker, *Exponential Backoff and Jitter*, AWS Architecture Blog,
> 2015-03-04, <https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/>

> "Let's call the algorithm above 'Full Jitter', and consider two
> alternatives. The first alternative is 'Equal Jitter', where we always
> keep some of the backoff and jitter by a smaller amount … A second
> alternative is 'Decorrelated Jitter' …"
> — same page

**Borrowed.** The shape: wait `base * 2^n`, cap it, and add jitter so that
N clients that failed together do not retry together. `palan.punar` uses
the *Equal Jitter* family — it keeps the whole exponential wait and adds a
deterministic fraction of half of it — because a retry that can fire
immediately is a retry storm with extra steps.

**Refused.** `random()`. In a deterministic runtime, an unseeded jitter
source is a hole in the replay token: the same seed would produce a
different schedule on the next run, and the whole 0.8.0 argument would
collapse. The jitter here comes from `pl.chunav`, which is derived from
`(seed, task, call index)`. It is decorrelated across tasks and identical
across runs. That is not a compromise; for a simulator it is strictly
better, because a "random" delay you cannot reproduce is a bug you cannot
reproduce either.

---

## 3. Circuit breakers: three states and a trial call

> "Calling the circuit breaker will call the underlying block if the
> circuit is closed, but return an error if it's open."
> — Martin Fowler, *CircuitBreaker*, 2014-03-11,
> <https://martinfowler.com/bliki/CircuitBreaker.html>

> "Asked to call in the half-open state results in a trial call, which will
> either reset the breaker if successful or restart the timeout if not."
> — same page

**Borrowed.** The three states and the trial call. `pl.vyavdhi` returns a
dict whose `state` is `band` (closed), `khula` (open) or `aadha`
(half-open); `pl.guzar` performs the trial and either resets the counter or
re-opens the breaker.

**Refused.** The timeout object. Fowler's breaker wraps a call with
`Timeout.timeout(invocation_timeout)`. Bun has no preemptive timeout, and
inventing one would mean killing a thread mid-operation — the same lie as
above. A deadline here is a *check* (`pl.avadhi` + `pl.jaanch`), which the
task performs at a point where it is safe to stop. The breaker's cooldown,
unlike the call timeout, is a pure wait and is measured on the virtual
clock.

**A detail that matters.** The breaker counts *consecutive* failures: a
success resets the counter. Fowler's Ruby sample resets on success too, but
many production breakers count over a window; the wave picked the simpler
rule and wrote it down, because a rule a reader can verify in ten lines is
worth more than a rule that needs a paragraph.

---

## 4. Chaos engineering: the experiment needs a control group

> "Start by defining 'steady state' as some measurable output of a system
> that indicates normal behavior. Hypothesize that this steady state will
> continue in both the control group and the experimental group. Introduce
> variables that reflect real world events like servers that crash, hard
> drives that malfunction, network connections that are severed, etc. Try
> to disprove the hypothesis by looking for a difference in steady state
> between the control group and the experimental group."
> — *Principles of Chaos Engineering*, <https://principlesofchaos.org/>

> "Systemic weaknesses could take the form of: … retry storms from
> improperly tuned timeouts; outages when a downstream dependency receives
> too much traffic; cascading failures when a single point of failure
> crashes …"
> — same page

**Borrowed.** The experiment shape, and two of the three named weaknesses:
the retry storm (bounded by `punar` + jitter) and the cascade (bounded by
the breaker).

**Refused.** Production traffic, and the word "random". A chaos experiment
in the usual sense injects failures into a live system and watches the
steady state. Here the injection is a *declared* possibility —
`pl.sankat(p)` says "this program may fail here", `pl.jokhim()` decides
whether it does — and the experiment runs in a simulator whose entire
schedule is a function of one integer. The control group is seed N; the
experimental group is seed N+1; the difference between the two tables is
the finding.

That is the smallest honest version of the idea. It is also the version a
CI job can run a thousand times a night, which the production version
cannot.

---

## 5. Deterministic simulation, again

The 0.8.0 note already quotes FoundationDB's determinism argument
(`research/concurrency_bugs.md`, §5). The wave reuses it rather than
re-arguing it, and adds one thing: **virtual time**.

A deterministic scheduler without a virtual clock can reproduce *which*
task runs, but not *when* a timeout fires, because timeouts are measured
against a clock the simulator does not control. Two runs of the same seed
would then agree on the interleaving and disagree on the deadlines — which
is exactly the class of bug (a timeout that fires on one machine and not
another) that the wave is supposed to find.

So the clock is part of the schedule: one tick per scheduling point, and a
sleep parks the task until the clock passes its wake-up. Nothing in the
program can observe wall-clock time, so nothing in the program can
disagree with the replay.

The cost is explicit: `pl.sona(3_600_000)` is not a promise about an hour.
It is a promise about 3.6 million ticks, and it takes microseconds. A
program that needs real time — a heartbeat, a rate limiter against a
remote server — must not use this clock, and the reference says so.

---

## What the wave deliberately does not have

| Missing | Why |
|---|---|
| Preemptive cancellation | Bun's tasks stop at checkpoints; a kill that cannot interrupt is a lie. |
| A wall-clock timeout | It would break the replay token. `avadhi` is a tick budget. |
| `simple_one_for_one` | Dynamic child lists are `sv.kary` plus `SV08`, not a supervisor. |
| Supervision across processes | There is one process. A supervisor that survived its runtime would need a second runtime to be honest about it. |
| Automatic escalation to a parent supervisor | A supervisor raises; who catches it is the program's decision. The wave reports the escalation (`PL07`) and stops. |
