# Design: the LLVM architecture study and the Bun performance roadmap

Date: 2026-10-29
Status: approved by the user (full authority given for every decision and
every install)

## 1. The goal

Bun's native backend turns the register code of the language into C and
lets the compiler of the system optimise it. The run of that backend is
fast: 9.6 ms on the benchmark of the phase 13, against 1.6 ms for the same
program written in C. The gap of six times is the whole subject of this
study.

LLVM is the reference for that gap. It is the compiler infrastructure that
Rust, C++ through Clang, Swift and many other languages use to reach the
speed of the machine, and it is open source under the Apache license with
the LLVM exceptions, so it can be read, measured and copied from. The
purpose of this project is to read it, measure it, and turn what it does
into concrete changes of Bun.

The study is exhaustive on purpose. Every small part matters: the value
representation, the pass pipeline, the instruction selection, the register
allocation, the inlining cost model, the way a loop is vectorised. A
detail that looks small in isolation is often the one that explains a
measured number.

### What the study is not

It is not a port of LLVM into Bun, and it is not a new backend written
during the study. The study produces knowledge, evidence and a ranked map
of the techniques Bun can take. The implementation of the techniques is a
separate project with its own design, its own plan and its own tests.

## 2. The sub-projects

The request has four independent parts. Each part gets its own design and
its own plan, and they run in this order.

| Project | Subject | Output |
|---|---|---|
| SP1 | the LLVM architecture study | twelve chapters, a research document, an adoption map |
| SP2 | the performance phases of Bun | three measured performance phases, 26 to 28 |
| SP3 | the power of the language | the design of traits, generics, macros and async |
| SP4 | a native backend on LLVM IR | a decision, taken after SP1 and SP2 |

SP1 is the subject of this document. SP2 starts only when the adoption map
of SP1 is written, because the map decides which phases are worth their
cost. SP4 stays a candidate: the study measures what an LLVM IR backend
would give and what it would cost, and the decision is taken with the
numbers in hand, not with a guess.

## 3. The method

A study that only reads code produces beliefs. This study produces
measurements, and every claim in the chapters is attached to one.

### Layer one: the source

The `llvm-project` repository is cloned with a shallow history into
`/opt/llvm-project`, and the Rust compiler, which is already cloned into
`/workspace/rust`, is read at the boundary where it hands its code to
LLVM. Every chapter names the files and the lines of the source that
carry the claim, so a reader can open the file and see the mechanism.

### Layer two: the binary truth

The tools of the system, `opt`, `llc` and `clang`, are the optimiser and
the code generator that the study describes. They are used to see the
passes that run, the machine code that comes out, and the time each part
takes. A statement about the pass pipeline is checked by running the pass
with the pass-timing output, and a statement about code generation is
checked by reading the assembly that `llc` writes.

### Layer three: the binary spot-checks with REA

Some questions cannot be answered by the source alone: how a particular
decision of the code generator looks in the machine, which branch of the
code is really taken, how large a function is on disk. For those, REA
analyses the binaries of the tools with Ghidra as the engine.

REA is used as a command line tool with its JSON output. Its MCP server is
not connected to the agent runtime: the tool is called from the shell, the
answers are read as files, and the platform keeps its own control over
the tools of the session. Every REA answer that enters a chapter is
recorded with the command that produced it, so the answer can be
reproduced.

### Layer four: the proof on the Bun side

A technique that LLVM uses is worth nothing to Bun if it does not help the
code Bun generates. Every candidate technique is therefore tested against
the Bun side before it enters the adoption map: the instruction profiler
of Bun (`bun compile --profile`) shows where the time goes, the
benchmarks of `tools/` show the change, and the golden corpus shows that
the language did not change.

## 4. The toolchain

The installs are approved by the user. They go outside the repository, so
the working tree of the project stays small and the git status stays
readable.

| Tool | Version | Place | Size |
|---|---|---|---|
| OpenJDK headless | 17 | apt | about 250 MB |
| LLVM and Clang | 14.0 | apt | about 700 MB |
| Ghidra | latest release | `/opt/ghidra` | about 2.2 GB |
| `llvm-project` | shallow clone | `/opt/llvm-project` | about 400 MB |

REA is already cloned and built in `/workspace/rea`, and its command line
entry point runs, so no package is installed for it. The system keeps
8.1 GB free; the installs take about 3.6 GB of it, and the archive of
Ghidra is extracted while it is downloaded, so no second copy of it is
stored.

The Node version of the system is 22.22.0 and REA declares 22.23.4 as the
floor of its engine. The command line works, and if a native analysis
needs the newer version, the version is replaced then, with the global
installation rules of the environment.

## 5. The deliverables

### The chapters

`docs/llvm/` holds the chapters and an index. Each chapter names the
mechanism, the data structures, the algorithms, the source of LLVM that
carries it, the measurement that confirms it, and the part of Bun it
touches.

| Chapter | Subject | The questions it answers |
|---|---|---|
| 1 | the three layers | where does the work of a compiler happen, and why is it split |
| 2 | the intermediate representation | how is a program written in SSA, what does a type mean, what does an instruction cost |
| 3 | the pass manager | how are passes scheduled, what is an analysis, how is a result invalidated, what runs in parallel |
| 4 | the optimisation pipeline | what does `-O2` actually run, what does the inliner decide, how is a loop vectorised |
| 5 | the target and the selection DAG | how is the code matched to the instructions of the machine, what is a legalisation |
| 6 | the machine IR and the register allocation | how does a virtual register become a register, how does a hot loop keep its values in registers |
| 7 | Clang | how does a C program become IR, what does the AST buy, what is the new Clang IR |
| 8 | the Rust bridge | how does a Rust program reach LLVM, what does Rust do before LLVM and what after |
| 9 | the linker, LTO, PGO, BOLT, the JIT and MLIR | how does the program get faster after the code is generated |
| 10 | the infrastructure | the value, the type, the use list, the dense map, TableGen, the bitcode |
| 11 | the diagnostics and the debug information | how does the compiler explain itself, how does the debugger see the program |
| 12 | the synthesis for Bun | the ranked techniques, the phases they belong to, the risks |

### The research documents

Two documents follow the convention of `docs/superpowers/research/`.

`2026-10-29-llvm-architecture-study.md` holds the evidence: every claim
with its precedent in LLVM, its measurement, and an adopt or reject
decision with the reason for it.

`2026-10-29-bun-llvm-adoption-map.md` holds the ranking: every technique
that Bun can take, with the part of Bun it touches, the expected gain
against the measurement of the phase 13, the risk, the effort, and the
phase it belongs to.

### The measurements

`docs/llvm/measurements/` holds the raw output of the tools and the
scripts that produced it, so every number in the chapters can be
reproduced on the machine of the study.

## 6. The discipline of the evidence

- A claim about a mechanism names the file and the line of the LLVM source
  that carries it.
- A claim about a performance names the command, the machine and the
  number.
- A claim about Bun names the file of Bun and the number of the benchmark
  before and after.
- A statement that could not be checked is written as unknown, not as
  fact.

The chapters are written in the voice of the repository: plain technical
prose, no marketing, no number without its measurement.

## 7. The gate to the changes of Bun

The study changes no line of the language. When SP2 starts, the rules of
the repository hold without exception.

- The golden corpus is the oracle: a program prints the same under the
  tree engine, the stack VM, the register VM, the C backend and the
  self-hosted front end.
- Every performance phase publishes the number before and after, with the
  command that produced both.
- Bun keeps its promise of no dependency at run time. A technique that
  needs a library at run time is rejected unless the user decides
  otherwise.
- The startup budget of the language stays honest: the cost of a new
  phase at start-up is part of the measurement.

## 8. The risks and the fallbacks

| Risk | Fallback |
|---|---|
| the download of Ghidra fails or is too slow | the study runs on the source, on `opt` and on `llc`; the binary spot-checks move to a later phase |
| the disk fills up | the install of the tools that are not needed for the current chapter waits |
| a chapter takes longer than expected | the chapter ships with the parts that are checked and the rest marked as open, and the work continues |
| the REA analysis needs a newer Node | the version of Node is replaced with the global installation rules of the environment |
| the adoption map shows that the useful techniques are few | the map says so; SP2 is then smaller and honest about it |

## 9. The plan of the work

| Phase | Work | Checkpoint |
|---|---|---|
| A | the toolchain: JDK, LLVM, Clang, Ghidra, the REA doctor | `rea doctor` reports the engine as ready |
| B | the map of the source: the layout of `llvm-project`, the boundary of `rustc` | the map is written as the first chapter |
| C | the chapters 1 to 6: the IR, the pass manager, the pipeline, the selection, the register allocation | each chapter is committed as it is finished |
| D | the chapters 7 to 11: Clang, the Rust bridge, the linker and the tools, the infrastructure, the diagnostics | each chapter is committed as it is finished |
| E | the measured case studies: the lowering of a switch, the decision of the inliner, the vectorisation of a loop, the allocation of a hot loop | the raw output is in `docs/llvm/measurements/` |
| F | the adoption map and the design of the phases 26 to 28 | the map and the design are written and reviewed |

The commits of the study are documentation commits. The push to the
`Main` branch of the remote happens at the end of a phase, with the
confirmation of the user.

## 10. What "done" means for SP1

- The twelve chapters are written, and every claim in them carries a
  source reference or a measurement.
- The research document and the adoption map are written and reviewed.
- The measurements reproduce.
- The design of the phases 26 to 28 is written, with the phase of each
  technique, the expected gain and the risk.
- The repository still passes its own tests, and the working tree holds
  no build artefact of the study.
