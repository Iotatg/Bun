# Antar — the graph inside a Bun program

`antar` (अंतर) means *the inside, the interval between*.  It is Bun's own
intermediate representation: one control-flow graph per function, built
once from the syntax tree, verified, and then used by tools that need to
reason about a program instead of running it.

This document records where the idea came from, what was actually read,
and what Bun built with it.  The principle is borrowed from Rust's MIR.
The design, the vocabulary, the invariants and the engine are Bun's own.

---

## 1. What was read in Rust

The clone is `rust-lang/rust` at `compiler/` (sparse, depth 1).  These are
the definitions the design rests on, quoted by file and line.

**A block is statements plus one terminator.**  `compiler/rustc_middle/src/mir/mod.rs:1323`

```rust
pub struct BasicBlockData<'tcx> {
    pub statements: Vec<Statement<'tcx>>,
    pub after_last_stmt_debuginfos: StmtDebugInfos<'tcx>,
    pub terminator: Option<Terminator<'tcx>>,
    pub is_cleanup: bool,
}
```

The comment above `terminator` says it should be `None` only during
construction.  A block without a terminator is not a finished block.

**A terminator owns the edges.**  `compiler/rustc_middle/src/mir/terminator.rs:424`

```rust
pub struct Terminator<'tcx> {
    pub source_info: SourceInfo,
    pub kind: TerminatorKind<'tcx>,
}

impl<'tcx> Terminator<'tcx> {
    pub fn successors(&self) -> Successors<'_> {
        self.kind.successors()
    }
}
```

`TerminatorKind` is a closed set — `Goto`, `SwitchInt`, `Return`,
`Unreachable`, `Drop`, `Call`, and so on (`syntax.rs:685`).  Every edge
of the graph comes from one of them; nothing else may jump.

**The graph caches the three questions every later stage asks.**
`compiler/rustc_middle/src/mir/basic_blocks.rs:15`

```rust
pub struct BasicBlocks<'tcx> {
    basic_blocks: IndexVec<BasicBlock, BasicBlockData<'tcx>>,
    cache: Arc<CfgCache>,
}

pub struct CfgCache {
    predecessors: OnceLock<Predecessors>,
    reverse_postorder: OnceLock<Vec<BasicBlock>>,
    dominators: OnceLock<Dominators<BasicBlock>>,
}
```

The comment next to `Predecessors` is a useful fact: *"Typically 95%+ of
basic blocks have 4 or fewer predecessors."*  The cache is shared, not
recomputed per pass.

**One structure serves every phase.**  `syntax.rs:25` says all flavours
of MIR use the same data structure; a phase only tightens which
constructs are legal.  Borrow checking, constant evaluation, optimisation
and code generation all consume the same `Body`.

**Positions are compact.**  `rustc_span/src/span_encoding.rs` stores a
`Span` in a `u64`.  A diagnostic is one primary span plus labelled
context spans, not a formatted string built at the error site.

### The principle, stated in Bun's words

1. A function is a list of **straight-line blocks**, each ending in
   exactly **one terminator**; control leaves a block only through it.
2. Every edge is declared by a terminator, so the graph can be checked
   without running the program.
3. The graph answers **predecessors, reverse postorder and dominators**
   once, and every later question is built on those three.
4. A node carries a **compact source position**, and a diagnostic quotes
   it.

Nothing in the list is code.  It is the shape a compiler needs.  Bun
implements that shape with its own names and its own semantics.

---

## 2. What REA showed in an optimised Rust binary

The experiment is a real Rust program (`/root/work/rust_rea_lab/main.rs`):
`accumulate` has a `while` and a data-dependent `if/else`; `fibonacci` has
a counted `for`; `main` reads `n` from the command line so the optimiser
cannot fold the program away, then prints `acc wins` or `fib wins`.

```
rustc 1.93.0 (254b59607 2026-01-19)
rustc -O main.rs -o lab
./lab 10        ->  acc wins: 80 vs 55
```

REA (Ghidra 12.1.4, `rea-workflow` v1) read the ELF:

| Fact | Value |
|------|-------|
| format / arch | `elf` / `x86_64` |
| sha256 | `69a655a615233fe90837822bdb3fef5ce1276016afebcc95cf3b348c9318b374` |
| segments | 41 |
| procedures | 684 |
| strings | 1435 |
| `.text` | `0x114220` – `0x153330` (258320 bytes) |
| `main::main` | `0x1143e0` |
| `main` | `0x1147a0` |

The `function` command refused the name `main` as **ambiguous** and
listed both entry addresses:

> `Ghidra procedure name is ambiguous: main; select an exact entry address
> from [0x1143e0, 0x1147a0]`

That refusal is itself the finding: after optimisation, a Rust binary has
more than one symbol that a human would call `main`, and a tool that
guesses is a tool that lies.  The same rule is why Antar refuses a
construct by name instead of lowering it approximately.

The second finding is the one that shaped the design: **optimisation
removes instructions, not control-flow shape.**  `-O` inlines, folds and
reorders, but the binary still contains compare-and-branch chains and
backward jumps — blocks and edges.  A representation that models blocks
and edges survives every later stage; a representation that models
syntax does not.

REA's evidence ids for the run:

```
ev_f3d725307bff1d27249dee8f08d3ba233fd6b08eb24cd45a6ab26ae21d46a8fc  (binary_overview)
ev_67c875e6c2f0dea7db11173b445f9f288d22f1583b39c5bee1dc66f2cea56bea  (search_procedures)
```

---

## 3. What Bun built

`bun/bun/antar.py`.  One graph per function, built from `ast.Program`.

### Vocabulary

| Bun | Meaning | Rust counterpart (principle only) |
|-----|---------|-----------------------------------|
| `khand` | a basic block: kriya then one nirnaya | `BasicBlockData` |
| `kriya` | a straight-line action | `Statement` |
| `nirnaya` | the single terminator | `Terminator` |
| `sthan` | a source position packed in one integer | `Span` |
| `pravah` | the flow graph of one function | `Body` |
| `antar` | the whole program | `Mir` |

### Terminators

```
ja        go to one khand
chunav    choose between two khand by a test
laut      leave the flow with a value
samaapt   leave the flow with no value
viram     unreachable
```

A `chunav` always has both targets.  `laut` and `samaapt` have none.
`ja` has exactly one.  The verifier checks this; the engine relies on it.

### Actions

```
set      bind a name (let / var)
assign   store into a name
opset    read, apply an operator, store (`x += e`)
step     add or subtract one (`x++`, `x--`)
emit     evaluate an expression for its effect (`print(...)`)
check    assert a condition
```

### Lowering

`if` becomes `chunav` plus `then`/`else`/`join` khand.  `else if` is
lowered as the nested `if` the parser actually produces.  `while` becomes
`head`/`body`/`exit` with a back edge from the body to the head.  A
`for ... in range(...)` becomes `head`/`body`/`advance`/`exit`, with the
counted variable kept in a temporary so that assigning the loop name
inside the body cannot change the iteration.  `break` and `continue`
become `ja` to the exit or the advance khand of the loop they name.

A logical condition is **not** hidden inside an expression evaluator:

```
if (a and b) { ... }
```

becomes three khand — test `a`, then test `b`, then the branch — so the
short circuit is visible in the graph.  This is the one place where Antar
goes further than the older engines, which evaluate `and`/`or` inside
their expression code.

### The verifier

`verify(antar)` checks, for every flow:

* every khand has exactly one nirnaya of a known kind;
* every target names a khand that exists;
* a `chunav` has both targets;
* the entry khand exists;
* every kriya has a known kind.

A khand that no path reaches is reported as `dead` in the stats, not
silently deleted.  `if c { return 1 } else { return 2 }` legitimately
leaves a join with no predecessor; that is a fact about the source, and
the report says so.

### The analyses

```python
predecessors(flow)       # who can reach each khand
reverse_postorder(flow)  # the order data flow likes
dominators(flow)         # fixed point over predecessor sets
loops(flow)              # natural loops from back edges
```

A back edge is an edge `n -> h` where `h` dominates `n`.  The loop body
is `h` plus every khand that reaches `n` without passing through `h`.
These are the three questions Rust's `CfgCache` caches; Bun computes them
on its own graph, on demand, in pure Python.

### The engine

`bun --engine antar` runs the graph.  A khand is executed in order and
control leaves only through its nirnaya.  Expressions are evaluated by
the same evaluator the tree engine uses, so a value means exactly the
same thing.  A call to a function of the program runs that function's own
`pravah`, so the call stack is a stack of graphs.

### The command

```bash
bun antar program.bun              # the graph, in text
bun antar program.bun --json       # blocks, edges, RPO, loops
bun antar program.bun --dot        # Graphviz
bun antar program.bun --verify     # structural report
bun antar program.bun --stats      # counts
```

```
ANTAR: OK (4 pravah, 22 khand, 22 kinara, 0 dead)
```

---

## 4. What Antar deliberately does not do

It refuses, by name, with `Unsupported("antar", ...)`:

* `for` over anything that is not `range(...)`;
* a `range` step that is not a literal number;
* `try`, `match`, `with`, generators, `yield`;
* structs, enums, protocols, impls, imports;
* assignment to a field or an index;
* a declaration inside a block.

It also states one semantic difference: **a `pravah` has one
environment**, so a name declared inside a khand stays visible after it.
Block scoping belongs to the tree engine.  A program that depends on it
should run on `--engine vm`.

A refusal is a feature.  The alternative — lowering a construct
approximately and printing a wrong answer — is the failure mode the REA
ambiguity error warns about.

---

## 5. Why this is a step forward, not a seventh copy

Before Antar, seven engines each carried their own lowering of `if`,
`while`, `for`, `break`, `continue`, `return` and short-circuit
evaluation.  Six implementations had to agree on one meaning by
inspection.

After Antar, the control-flow meaning of a Bun program exists **once**, in
a structure that can be printed, drawn, verified and measured.  The
engine is one consumer; the verifier is another; the dump is a third.
The next backend — a new target, a data-flow pass, a coverage tool — can
consume the same graph instead of re-deriving control flow from the tree.

That is the whole return on reading Rust: not the code, the shape.
