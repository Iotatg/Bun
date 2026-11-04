# The five engines — and why an interpreter is not a slow compiler

Bun runs the same program on five engines. The choice is not about
"which one is best"; it is about which cost you are willing to pay.

| Engine | What it does | Start | Hot loop |
|--------|--------------|-------|----------|
| `tree` | walks the syntax tree directly | fastest | slowest |
| `vm` | stack machine over the bytecode (default) | fast | good |
| `register` | register machine over the bytecode | fast | good |
| `register --tier` | register machine plus the superinstructions | fast | better |
| `c` | lowers the whole program to C, compiles, runs | slowest | fastest |

```bash
bun --engine tree     program.bun
bun --engine vm       program.bun
bun --engine register --tier program.bun
bun --engine c        program.bun
```

## The two costs

A compiled language pays the compile cost on every change. Change one
constant — `a = 10` becomes `a = 30` — and the whole pipeline runs
again: lex, parse, check, lower, optimise, emit, link. That is fine
when the program is finished and runs a million times. It is painful
while the program is being written, because the program is *not*
finished yet.

An interpreter pays the interpretation cost on every execution. The
runtime walks the program and does most of the work itself — binding
names, choosing branches, building values — and calls into the machine
only for the actual arithmetic. That is why Python feels slow in a hot
loop and why it feels instant when you change a line and run it again.

> The interpreter was not built to be fast. It was built so that you
> can experiment: run a line, look at the answer, change it, run it
> again. Experiments are what produce the useful features.

## The measurement

`tools/bench_engines.py` runs one workload on every engine:

```bash
python3 tools/bench_engines.py --n 200000 --repeat 2
```

A sample run on this machine (500 000 loop steps, same program):

| engine | ms | vs vm |
|--------|-----|-------|
| tree | 4578 | 2.26x |
| vm | 2022 | — |
| register | 3639 | 1.80x |
| register + tier | 3533 | 1.75x |
| c | 64 | 0.03x |

The numbers move with the workload; the shape does not. The tree walk
is the most expensive per step, the C backend is roughly an order of
magnitude ahead of the interpreters on a hot loop, and the two bytecode
machines sit in between.

## What each engine is for

- **`tree`** — debugging the language itself. Every node is visible in
  the Python debugger, so a wrong answer is easy to trace.
- **`vm`** — the default. Small, predictable, and the engine the golden
  corpus is written against.
- **`register`** — the same bytecode with named slots instead of a
  stack; useful for comparing instruction-selection strategies.
- **`register --tier`** — the superinstructions (fused compare-and-jump,
  fused load-and-add) that remove dispatch overhead in hot code.
- **`c`** — the finished program: `bun compile --profile` shows where the
  time goes, `build_binary()` writes a standalone ELF that runs without
  Python at all.

The REPL, `bun test --doc`, and the language packs all run on the
interpreters, because their job is to answer a question in
milliseconds, not to win a benchmark.
