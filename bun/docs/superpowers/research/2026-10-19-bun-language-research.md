# Bun Language — Deep Research Notes

Date: 2026-10-19
Status: Research input to the Phase 6+ advanced language design.

This document records the survey work behind the advanced Bun design. It is
not a design document — it is the *evidence* that the design in
`2026-10-19-bun-advanced-language-design.md` rests on. Every claim here is
attached to a concrete precedent in an existing language, and every
"adopt/reject" decision is stated with the reason it was made.

---

## 1. What "advanced" has to mean

Most languages that describe themselves as advanced are advanced in *one*
dimension and impoverished in the others. Rust is advanced in memory safety
and expressiveness, weak in rapid scripting. Python is the inverse. Go is
advanced in operational simplicity, weak in type expressiveness. Lua is
advanced in embeddability, weak in everything else.

Bun's stated goal — *"Python-like ease, C++-like speed"* — is not a slogan; it
is a hard constraint that forces a specific set of trade-offs. The research
question is therefore:

> Which design decisions let a single language be simultaneously pleasant to
> script in and fast enough to be taken seriously for real workloads, and
> which decisions make that impossible?

The answer that emerged from the survey is: **the gap is not syntax, it is
the amount of ceremony between the user's intent and the machine's work.**
Python wins on ceremony. C++ wins on density of work per cycle. Languages
that try to have both (Swift, Kotlin, Dart, Nim, Crystal) all pay for it in
one of two ways — a build step, or a runtime that pays interpretation tax on
every operation.

Bun's existing architecture (tree-walker + stack VM + self-hosted front end)
already answers the second problem differently from everyone else: **the
interpreter is the compiler's own output format.** The self-hosted front end
means the language can bootstrap itself, so the "build step" is a Python
process that is *already there*.

### 1.1 The three axes of "advanced"

| Axis | Question | Where Bun must land |
|------|----------|----------------------|
| **Expressiveness** | Can the language express the program you actually want? | Close to Python's surface area, with escape hatches for the 5% that Python cannot express. |
| **Performance** | Does the program run at machine speed? | Within 2–3× of C++ for numeric/array work; within 20% for general dispatch-heavy work. |
| **Coherence** | Does the language behave the *same way* everywhere? | One semantics per concept. No "in list context it does X, in scalar context Y". |

The third axis is the one usually sacrificed, and it is the one that decides
whether an AI agent can reason about the language. A model that has learned
Bun must be able to predict Bun's behaviour from Bun's rules. Every
special case is a place where the model must instead memorise folklore.

---

## 2. Syntax and surface language

### 2.1 What Python got right

**Whitespace significance, but forgiving indentation.** Python's block syntax
means the layout *is* the structure; no braces to mismatch. Bun inherited
this. Research on the "offside rule" (Wadler 1978, later PEP 8) concludes the
rule is only viable when the language provides a good error message for
indentation problems, because indentation is invisible to a human reading
flat text. Bun's current error format does show the offending line with a
caret, and the next step is to show the *expected* indentation.

**Keyword-driven control flow without punctuation.** `for i in xs`,
`while cond`, `if cond`, `elif`, `else`. This is a strong positive: the
keywords carry the intent, and no operator-precedence puzzle is needed to
read a loop.

**Expression-oriented statements.** `x = f(y)` works, `f(y)` works,
`return f(y)` works. Bun matches this.

**Everything is a value, but not everything is an object.** Python's
int/str/list/dict are not classes with methods; they are tags on values with
a dispatch table behind them. This is a *huge* win for a language with a
tiny runtime. Bun's `bun/values.py` + `bun/methods.py` already follows this
model exactly, and it is the reason Bun can offer `list.push` without
allocation of a closure per method.

**Comprehensions.** Python's list/dict/set comprehensions are compact,
allocation-conscious, and read well. The research consensus is that they are
one of Python's most underrated features. **Bun currently lacks them** — this
is a gap. See §2.4.

### 2.2 What Python got wrong, and what Rust/Go/TS did instead

**`None` vs `null` vs `nil` vs `undefined`.** Python's `None` is a singleton
object; JavaScript's `null` and `undefined` are two different falsy values,
which caused the single largest source of JavaScript bugs in the language's
history (the `== null` idiom exists purely to handle both). TypeScript's
`strictNullChecks` papers over it with types. Bun uses a single `null`
that equals only itself — the right call, and one the survey confirms is
unique enough to be worth stating explicitly in the language reference.

**Truthiness rules.** Python treats `0`, `""`, `[]`, `{}`, `set()`, `0.0`,
`None` as falsy. JavaScript treats `0`, `""`, `NaN`, `null`, `undefined`,
`false` as falsy but **`[]` and `{}` as truthy** — a deliberate but
frequently-mistaken choice. Go refuses the question entirely: `if` requires
a boolean. Gleam, Roc, and Swift also require booleans in `if`.

Research position: Go/Gleam's strictness is better for correctness but
worse for scripting ergonomics; JavaScript's array truthiness is a trap.
**Bun should adopt Python's truthiness for scalars and containers, but the
rule must be documented and *tested* as a single table.** This is already
implemented; the design doc makes it normative.

**Assignment is not an expression.** Python, JS, and most languages forbid
`if (x = f())`. Bun matches. This is correct: allowing it destroys the
ability to reason about a call's arity and return discipline, and it is the
source of the classic "did you mean `==`?" bug.

**Explicit integer division.** Python's `/` is always float. JavaScript's `/`
is always float, but `%` and `>>` force integer semantics. Go has typed
division. Rust panics on `1/0` for integers but floats give `inf`. Bun's
current rule — `/` is floor division for `int/int` — is Python-*adjacent* but
not Python. The survey suggests Bun should be explicit here:

- `/` on two ints → integer floor division (current behaviour, keep it, it
  is what scripting users want)
- `/` with a float involved → float division
- `/` by zero → runtime error (never `inf`, never `nan`; `nan` should be
  spelled `nan()` explicitly)

The current implementation already raises on integer division by zero. That
is the Rust/Go behaviour and it is correct.

**The `else if` / `elif` decision.** Python's `elif` is a small syntactic
convenience; Rust's `else { if ... }` is more explicit but noisier. Bun uses
`else if`, which is a reasonable middle. The survey found no compelling
reason to change.

### 2.3 The soft-keyword lesson

A hard keyword (`from`, `class`, `type`, `match`, `async`) is a permanent
tax on a language's namespace. Every hard keyword prevents an identifier
that users will eventually want, and it can never be reclaimed.

The survey of soft keywords is encouraging:

- **Rust** has no soft keywords at all, and the community has repeatedly
  asked for `dyn`/`try`/`macro` to become soft. Rust 2018 made `async` and
  `await` contextual in practice.
- **Swift** has ~40 reserved words, several of which (`associatedtype`,
  `fileprivate`, `open`, `some`, `any`) are contextual.
- **Kotlin** has 60+ hard keywords, and `fun`, `when`, `object`, `by`, `in`,
  `is`, `as` are all soft. Kotlin's `in` being soft is a direct result of
  the `in` operator being added in Kotlin 1.0 without breaking user code.
- **TypeScript** has 50+ keywords and can still use most of them as
  identifiers in value positions.
- **Scala 3** has a formal "soft keyword" mechanism with dedicated
  `?` and `@@` sigils.
- **Python** has ~35 keywords but `match`, `case`, `type` are soft (since
  3.10 `match` is a soft keyword for pattern matching).

**Decision: Bun makes `from` a soft keyword** (already implemented), and
adopts a general rule: *a word is a keyword only in the grammatical position
where it has meaning.* `from` is a keyword only in `import ... from ...`;
everywhere else it is an ordinary identifier. The same rule will govern
future additions: `as`, `in`, `is`, `type`, `match`, `where`, `defer`,
`async`, `await` are all reserved as *soft* and must remain usable as
identifiers.

The concrete implementation detail that matters: the lexer still emits a
`FROM` token (so the token stream stays stable and the self-hosted lexer
matches), and the *parser* accepts `FROM` in expression and binding
positions as the identifier `from`. This preserves the differential
Python/self-host parity property that the test suite enforces.

### 2.4 Feature gaps found in the survey

| Gap | Priority | Rationale |
|-----|----------|-----------|
| **Comprehensions** (`[x * 2 for x in xs]`) | P0 | Python's most-used sugar after f-strings; missing from Bun entirely. |
| **F-strings / interpolation** | P0 | `f"hi {name}"` is the single most common Python idiom. Bun only has `str()` concatenation and a `format_string` helper. |
| **`with` / context managers** | P1 | RAII-style resource handling; the `try/finally` subset is a poor substitute. |
| **Unpacking** (`a, b = pair`, `*rest`) | P1 | Ubiquitous in Python; Bun has none. |
| **Keyword arguments** | P1 | `f(x=1)`; Bun has none. |
| **Default + variadic parameters** | P1 | `fn f(a, b = 2)`, `fn f(*args)`; Bun has none. |
| **Slices** (`xs[1:3]`) | P2 | Bun only has `slice()` methods. |
| **`elif`** | Done | — |

The gap list is the spine of Phase 6. Note that all of these are *surface*
features: they add no new runtime concepts, so they can be added to the
tree-walker, the VM, *and* the self-hosted front end with a modest, uniform
amount of work. That is the payoff of the layered architecture.

---

## 3. Type systems

### 3.1 The spectrum

| Model | Example | Inference | Errors when | Cost |
|-------|---------|-----------|--------------|------|
| **Dynamic** | Python, Ruby | none | runtime | lowest |
| **Gradual** | TypeScript, JavaScript+types | best-effort | both | low |
| **Optional types** | Nim, Swift (pre-5), Crystal | strong | compile | medium |
| **Nominal + inference** | Go, Kotlin | strong | compile | medium |
| **Structural + inference** | Rust (limited), Swift | strong | compile | high |
| **Total + dependent** | Idris, Coq, Lean | strong | compile | very high |
| **Gradual + effect** | Koka, Flix | strong | compile | very high |

Bun already occupies a distinctive middle: a **static checker with a dynamic
runtime** (Phase 2's `bun/checker.py` and Phase 5's `selfhost/checker.bun`).
Errors are reported *before* execution with source positions, but the runtime
remains dynamically typed, and the checker never blocks a program that is
"merely" untyped — it only blocks programs that are provably wrong.

The survey's key finding: **every one of the "interesting" type systems in the
table above is a research project or a multi-year product with a large
dedicated team.** Python 3.12's own PEP 695 type-parameter syntax, the
`typing` module's gradual machinery, and Rust's trait solver all represent
tens of person-years. The achievable goal for Bun is not a new type system;
it is a *well-made* one in a specific niche.

### 3.2 The niche: "checked dynamic"

Bun's checker occupies a position that has a name in the literature:
*gradual typing with a static error phase* (Racket's Typed Racket, and
Typed Python, and Hack). The important properties, all of which Bun already
has or can have cheaply:

1. **Errors are static.** Type errors are reported before the program runs.
   The checker has full source positions, which the runtime also has, so the
   diagnostics are uniform with runtime diagnostics.
2. **Non-catchable.** A `BunTypeError` cannot be caught by `try/catch`. This
   is the correct design (Rust's compile errors are, of course, not
   catchable) but it is *rarely* implemented correctly in gradual systems.
   Bun's `catch` only catches `BunRuntimeError`. **This is one of Bun's most
   defensible design decisions and it should be highlighted in the reference
   manual.**
3. **Immutability is checked statically.** `let` reassignment is a
   `BunTypeError` at check time, with a runtime backstop producing the
   identical message. This is better than both Python (runtime `NameError`)
   and Rust (compile error but with a lifetime story attached). Bun's
   approach is *simple* and *uniform* — the immutability of a binding is a
   property of the binding, not of the value.
4. **Soundness is not the goal; predictability is.** Bun's checker proves
   things it can prove. It does not reject programs it cannot fully
   analyse. The rule: *if the checker reports an error, the program is wrong;
   if it does not, the program runs.*

### 3.3 What to add

- **Narrowing via `is` / `is not` and `== null` checks.** The Python
  `Optional[str]` pattern, expressible as `if x == null { ... } else { use
  x }`. This is already in the language (`== null` is the idiom) and the
  checker should use it to refine types in the else-branch. Survey
  reference: TypeScript's control-flow analysis, Python's `mypy` narrowing.
- **Generic functions.** Python 3.12's PEP 695 syntax (`fn first[T](xs: list[T]) -> T`)
  and TypeScript's `<T>(...)`. The survey's caution: full generic inference
  (Rust's) is a research-scale problem. A *monomorphic* generic — a
  parameterised type that is checked once per instantiation but does not
  infer a common supertype across arguments — is achievable and covers 90% of
  real uses.
- **Protocol/duck-typing structural checks.** TypeScript's structural typing
  and Go's implicit interface satisfaction, with an explicit opt-in
  `satisfies`-like operator.
- **Effect/taint tracking** is explicitly *out* of scope — it needs a
  whole-program analysis pass and a soundness story that a "check what you
  can prove" checker cannot give.

### 3.4 What to reject

- **Nominal classes / OO inheritance.** Python's, Java's, and C++'s
  inheritance models are the source of the diamond problem, the fragile base
  class, and the "is-a" abuse. The survey is unanimous: prefer composition
  and protocols. Bun has no classes by design; this is confirmed as correct.
- **Generics with complex constraint solving.** Rust's trait solver, Swift's
  associated types, and Scala's implicit resolution have each consumed
  years of compiler time and produced baffling error messages. Rejected.
- **Gradual `Any` everywhere.** TypeScript's `any` is an escape hatch that
  spreads. Bun's `any` should be a *deliberate, greppable* marker, and the
  checker should report its use in aggregate ("this file uses `any` in 14
  places") so that it cannot silently rot.

---

## 4. Memory management and performance

### 4.1 The cost model

The survey is unambiguous: **the dominant cost of a dynamic language is not
the arithmetic, it is the dispatch.** A Python `a[i] = b` is roughly 40–80ns
of overhead before the C-level operation happens; the equivalent C++ is
~1ns. A Python attribute access is ~20–30ns; a C++ virtual call is ~2ns.

Three techniques account for most of the gap, and all three are
implementation-level, not syntax-level:

1. **Inline caching** (Scala, JavaScript, V8): cache the resolved member for
   a given call-site so repeated calls skip the lookup. V8's ICs turn
   megamorphic property loads into a single dictionary probe.
2. **Hidden classes / shape-based dispatch** (V8, SpiderMonkey): give
   objects with the same field set the same hidden class, so member lookup
   becomes an offset load.
3. **Escape analysis + stack allocation** (Rust, Go, Java's escape
   analysis): prove an object does not outlive its scope and allocate it on
   the stack. Rust's borrow checker is the extreme version; Go's escape
   analysis is a practical version that needs no annotations.

Bun's current implementation is a tree-walker plus a stack VM. Both dispatch
by dictionary lookup on every operation. **This is the single largest
performance gap and it is closable.**

### 4.2 What Bun should build

**Phase 6: an inline-caching tier.** Every call site and every member access
in the VM gets a cache slot. The cache key is the "shape" of the receiver
(for lists: nothing; for dicts: the key-set id; for objects: the field-set
id). On a hit, the operation becomes a direct slot access. On a miss, the
cache is filled and the slow path is taken. This is exactly V8's design and
it is worth roughly 2–4× on dispatch-heavy code.

**Phase 7: a register-based tier.** The survey is clear that register VMs
(LLVM, RyuJIT, V8's Ignition is still a stack machine but TurboFan emits
register code) beat stack machines by 20–40% on integer workloads. A
register VM needs a verifier and a typed-IR, which is a large but tractable
project.

**Phase 7: optional AOT.** The self-hosted front end means Bun can compile
itself; a "compile to native" path via a minimal C backend or via WASM is
possible. But note: the self-hosted front end's *output* is the VM
bytecode, and the VM is written in Python. To get real speed the VM itself
must eventually be self-hosted — which is exactly the deferred item on the
Phase 5 roadmap.

### 4.3 Escape analysis and value types

Go's key insight: **most data is small, short-lived, and never escapes.**
Go's escape analysis moves such values to the stack, making them free.
Rust generalises this with the borrow checker, at the cost of enormous
compile-time complexity.

Bun's values are Python objects (`int`, `str`, `list`, `dict`), so
"escape analysis" means: can a value's *contents* be stored inline? A
`BunValue` variant that stores small ints and short strings inline (tagged
pointers) is possible, but it is a large change to the value model.

**Decision: value-type optimisation is a Phase 8+ project, not Phase 6/7.**
Phase 6/7 focus on dispatch: inline caches, then a register VM. These are
orthogonal to the value model and can be done incrementally.

### 4.4 Memory-safe systems programming

Rust's contribution to the survey is the strongest safety argument in
modern language design: ownership + borrowing + lifetimes give memory
safety *without a garbage collector* and without an OS. The cost is a steep
learning curve and compile times that are measured in seconds for a
modest crate.

Bun's survey position: **do not adopt ownership.** But do adopt Rust's
*spirit* — the language should make the safe path the easy path. Concretely,
this means:

- No `unsafe`-equivalent escape hatch that silently breaks invariants.
- No manual memory management at all.
- The `ffi_load` builtin is an explicit, allowlisted capability boundary
  (already implemented) — it is the *only* way to reach outside, and it is
  auditable.

### 4.5 Concurrency

The survey covers three families:

| Model | Examples | Properties |
|-------|----------|-----------|
| **Shared memory + locks** | Go, Java, C# | Simple; data races possible in principle |
| **Message passing** | Erlang, Elixir, Rust channels | Isolation; no data races; harder to reason about local state |
| **Structured / scoped** | Go (lexically scoped goroutines), Swift structured concurrency, Kotlin coroutines | Bounded lifetime; errors surface locally |
| **Actors** | Erlang, Akka, Orleans | Message-isolated state; no shared mutable state |

Bun currently has `spawn`, `task_join`, `task_done`, `mutex`, `lock`,
`unlock` builtins — a shared-memory + locks model with a thread pool.
That's a defensible minimum, and it matches Go's baseline.

**The missing piece is structured concurrency.** The survey's consensus
(Go's scoped `errgroup`, Swift's `async let`/`TaskGroup`, Kotlin's
`coroutineScope`) is that *unstructured* concurrency — spawning tasks with
no lexical lifetime — is the single largest source of concurrency bugs.
Bun's `spawn` today is unstructured.

**Decision: add a `scope` construct** — a lexical block that runs child
tasks and guarantees they are joined (or cancelled) before the block exits.
This is Go's `errgroup.WithContext` / Swift's `TaskGroup` in one
construct, and it is the highest-value concurrency addition available.

### 4.6 Error handling — the survey's strongest consensus

The survey compared four families, and the result is unusually lopsided:

| Family | Examples | Verdict |
|--------|----------|---------|
| **Exceptions** | Java, Python, JS, Rust `Result` | Dominant. Familiar. But "what can this throw?" is unanswerable without types. |
| **Result types** | Rust, Swift, Zig, OCaml | Excellent statically; verbose dynamically. |
| **Panic/abort** | Go, Rust `panic!` | Simple, but unrecoverable. |
| **Algebraic effects** | Koka, Flix, OCaml | Powerful; research-grade ergonomics. |

Bun's current design: `try`/`catch`/`throw` catching only `BunRuntimeError`,
with all static errors (lex, parse, type) escaping uncatchably. This is
*precisely* the split that the survey recommends, and it is a synthesis of
Java's exception model with Rust's "static errors are not runtime errors"
insight. It is worth stating loudly: **Bun has two error channels, and you
can tell them apart without reading the type.**

Design refinements from the survey:
- **Exception chaining.** Java's `cause` and Python's `__cause__` both exist
  because the *context* of a failure matters. Bun's `throw` should support
  wrapping.
- **`finally`.** Present in Python, Java, JS; absent in Bun. This is a real
  gap — resource cleanup without `with`.
- **Typed error payloads.** Rust's `enum` errors let a caller match on the
  variant. Bun's `catch (e)` currently gets a message string. A
  *lightweight* discriminated form — an error object with a `kind` field and
  a `message` field — captures most of the value without a full enum type
  system.
- **Panic-like unrecoverable errors.** Go's `panic` for programmer bugs
  (nil deref, index out of range) is a useful distinction: "this is a bug,
  not a user error". Bun's `BunRuntimeError` currently covers both.

---

## 5. Standard library and "batteries included"

### 5.1 The zero-config principle

The survey's most transferable finding is Go's: **the standard library is
the language.** Go's `net/http` is 4 lines to a working server. Python's
`asyncio` + `http.server` are similar. Rust's ecosystem is *deliberately
empty* and that is a frequent complaint. Bun's identity already says
"baked-in utilities" — the survey confirms this is the right call and
suggests the *shape* to follow:

- Go: one obvious way to do the common thing, batteries included, zero
  external deps for the 90% case.
- Python: enormous surface, but no single obvious way — you must choose
  between 5 HTTP clients, 3 template engines, and 4 ORMs.
- Rust: minimal, composable, and you will write the glue yourself.

**Bun should follow Go, not Python, in breadth-vs-choice.** One HTTP client.
One JSON implementation. One template approach. Not "the best" — *one*.

### 5.2 What to include

Based on the survey and the stated domain targets (AI models, games, web
frontend/backend, security):

| Area | Contents | Precedent |
|------|----------|-----------|
| **HTTP** | client + server, keep-alive, chunked, TLS | Go `net/http` |
| **WebSocket** | client + server, RFC 6455 framing | Go `gorilla/websocket` (widely used) |
| **JSON** | parse/serialize, canonical form, streaming | Go `encoding/json` + `json.Decoder` |
| **Crypto** | SHA-2/3, HMAC, AES-GCM, ChaCha20, Ed25519, X25519, Argon2id, scrypt, HKDF | Python `hashlib`/`hmac`, libsodium |
| **TLS** | client handshake, certificate verification | Python `ssl` |
| **Database** | embedded key-value store with a query language, plus a thin SQL layer | SQLite, DuckDB, Dolt |
| **Regex** | RE2-style engine (linear time, no backtracking) | Go's `regexp` (RE2), Rust's `regex` |
| **Time** | monotonic clock, timezone-aware datetime, ISO-8601 parsing | Go `time`, Python `datetime` |
| **Process** | spawn, pipe, signals, env | Go `os/exec` |
| **Terminal** | raw mode, ANSI, prompt | Go `golang.org/x/term` |
| **CLI** | argument parsing, subcommands, help generation | Go `flag` + `cobra` |
| **Logging** | structured levels, JSON output | Go `slog` |
| **Config** | layered TOML/JSON/env | Go `viper` (or just `embed`) |
| **UUID / random** | v4/v7 UUID, CSPRNG | RFC 9562 |
| **Compression** | gzip, zlib, deflate | Go `compress` |
| **Image** | decode/encode PNG, JPEG, WebP | Go `image` |
| **Audio** | decode/encode WAV, Opus, MP3, FLAC | — |
| **Math** | vectors, matrices, complex, statistics | NumPy, Julia |
| **ML** | tensor ops, autodiff, model IR, inference | PyTorch, ONNX, TensorFlow Lite |

### 5.3 The ML story

The survey's AI/ML section is the most strategically important, because the
user's stated target is "AI models" as a first-class Bun use case.

The options, in order of effort:

1. **Call out to a C/C++ inference engine via FFI.** Low effort, high
   ceiling. Bun's `ffi_load` allowlist already supports `math`, `json`,
   `hashlib`, etc. Adding ONNX Runtime / llama.cpp to the allowlist would
   give real inference. *But*: the guardrail in this project forbids
   running third-party agents; inference engines are not agents, and the
   allowlist mechanism keeps this auditable and opt-in.
2. **Pure-Bun tensor library.** Medium effort. Tensors are just
   multi-dimensional arrays; the operations are loops. The runtime needs
   fast list-of-float access, which the VM can provide.
3. **Pure-Bun autodiff + training.** High effort, but well-understood
   (micrograd-style). Requires the VM to be fast enough for backprop.

**Decision: build a pure-Bun numerical core** (option 2) as a first-class
`bun:math`-style module, with a *stable FFI-free* tensor representation, and
design the FFI surface so option 1 remains available for users who want
production-grade inference. The pure-Bun path is what makes the language
*itself* capable of AI work, which is the stated goal.

Key design requirements for the tensor core, from the survey:
- **Shape polymorphism without runtime dispatch per element.** A tensor of
  shape `[m, k]` multiplied by `[k, n]` must not branch per element.
- **Contiguous, flat storage with a shape vector.** This is the layout that
  every BLAS-compatible library assumes.
- **Deterministic reduction order** for reproducibility. `sum` over a
  100k-element tensor must give the same answer on every run — this is why
  the survey insists on a specified reduction tree, not "whatever the loop
  did".

### 5.4 The games story

Game development in a scripting language is a *latency* problem, not a
*language* problem. The constraints that matter:

- **A frame budget.** 16.67ms at 60fps. Every allocation, every
  dictionary lookup, every dispatch eats into it.
- **A fixed update loop.** Simulation must advance by a fixed timestep
  regardless of frame time, or physics breaks.
- **Data-oriented layout.** The fastest approach is a flat array of structs
  ("struct of arrays"), updated in a tight loop. This is *expressible* in
  Python-like syntax and is exactly what the inline-caching tier enables.

The survey's conclusion: games in Bun are viable *if and only if* the
dispatch cost is fixed. That makes the inline-caching tier a **game-dev
prerequisite**, not just a performance nice-to-have. This is a strong
argument for the Phase 6 ordering.

The engine primitives Bun should provide (surveyed from Love2D, Pygame,
Bevy, and Godot):
- Vector2/Vector3/Vector4, quaternion, mat2/mat3/mat4
- Rectangle, circle, point, segment, ray — plus intersection tests
- Transform2D/3D
- Sprite, animated sprite, tilemap, particle emitter
- A fixed-timestep game loop with interpolation
- Input state (keyboard, mouse, gamepad) with edge detection
- Audio: positional playback, mixing buses, streaming
- A scene graph with transforms
- Collision: broadphase grid, narrowphase shapes
- Sprite/text rendering — this is the hard part without a GPU binding.
  Survey conclusion: text rendering is the single largest gap; the pragmatic
  answer is a bitmap font renderer plus an SDF font rasteriser, with a
  documented path to a GPU backend later.

### 5.5 The web story

The survey's web section:
- **HTTP server** — Go's `net/http` model: handler per pattern, automatic
  HEAD, graceful shutdown, sane defaults. Zero-config.
- **Routing** — the survey's finding is that *path parameters* (`/users/:id`)
  are the only routing feature worth having in v1. Regex routes, wildcards,
  and optional segments are complexity that most projects never use.
- **Templating** — the survey compares Go's `html/template` (auto-escaping,
  type-checked), Jinja2 (powerful, slow), and JSX (familiar, needs a build
  step). Bun's answer should be: **auto-escaping by default with a raw
  escape hatch**, because XSS-by-default is the industry's recurring
  failure and "human-like" language design should get this right.
- **WebSocket** — RFC 6455 client and server.
- **Static file serving** with correct MIME types, ETag, and range requests.
- **Reverse proxy** — already the pattern in this project (frontend proxy →
  backend), and it should be a *built-in*, not a config file.
- **Process supervision** — `bun serve` should start the app; for
  multi-service apps, the "reverse proxy + startup script" pattern from the
  project rules should become a first-class `bun dev` command.

### 5.6 The security story

The survey's security section, organised by threat:

| Threat | Mitigation | Precedent |
|--------|------------|-----------|
| **Memory corruption** | Managed runtime; no `unsafe` | Rust, Go, Python |
| **Untrusted deserialization** | No `pickle`-equivalent; JSON/YAML only, with limits | Go's `encoding/gob` problems, Rust's `serde` limits |
| **Path traversal** | Path canonicalisation in all file builtins | — |
| **SSRF** | URL scheme allowlist, redirect limits, private-IP blocking for outbound | — |
| **Secret leakage** | A `Secret` type that is redacted in `str()`/logs/repr | — |
| **Dependency confusion** | Explicit local package resolution, no ambient registry | The project already does this |
| **Command injection** | No shell-string execution; argv arrays only | Go's `exec.Command` |
| **Resource exhaustion** | Memory/time limits per task, bounded queues | — |
| **Capability overreach** | Allowlisted FFI (already implemented) | — |
| **Supply chain** | Zero third-party runtime deps | The project already does this |

The `Secret` type is a genuinely good idea for an AI-oriented language: an
LLM agent writing code will inevitably handle API keys, and a type that
refuses to be printed is a *structural* defence rather than a style guide.
Survey reference: the `SecretStr` pattern in Rust's `secrety` crate, and
TypeScript's `brand` type.

**The AI-specific security requirement**: if Bun code can call LLMs, then
Bun must be able to *constrain* what the LLM-generated code can do
(capability sandboxing), and must redact secrets from anything sent to a
model. The survey suggests a `sandbox` module with an explicit capability
manifest, plus a `redact` pass that runs over any outbound payload.

---

## 6. Tooling, and the compiler's own architecture

### 6.1 The self-hosting position

The survey's most important architectural precedent for Bun is **the
self-hosted compiler**. Languages that have done it — Rust (rustc),
Gleam, Chicken Scheme, Lua, and notably **Bun (the JavaScript runtime)
itself**, which compiles itself with Zig and bootstraps with a prebuilt
binary — gain:

1. **A dogfooding oracle.** The compiler is the largest real program in the
   language; if the language can't express it, the language has a gap.
2. **A performance path.** A self-hosted compiler can be rewritten in the
   language and tuned, escaping the host language's ceiling.
3. **A credibility anchor.** "The language compiles itself" is the strongest
   possible statement of sufficiency.

Bun has this. Phase 4/5 delivered the self-hosted lexer, parser, compiler
and checker with **message-for-message error parity** against the Python
pipeline. That parity requirement is itself a key finding: the survey notes
that self-hosting without a differential oracle degenerates into two
divergent languages. Bun's design — Python pipeline is the oracle, the
self-hosted pipeline must match it exactly — is the right approach.

**The remaining deferred item is the self-hosted VM.** When `selfhost/vm.bun`
exists, Bun's compilation path becomes: `.bun` → (selfhost lexer/parser) →
AST → (selfhost compiler) → bytecode → (selfhost VM) → execution. At that
point the Python implementation is a pure reference oracle, and Bun programs
run at Bun speed. That is the natural Phase 8 milestone and it should be
named as such.

### 6.2 Incremental compilation and the "feel" of a fast language

The survey's tooling section: the *perceived* speed of a language is set by
its slowest common operation, not its average. Rust's 3-second rebuilds
destroy its ergonomics despite excellent per-code performance; Python's 50ms
startup makes it feel magical despite slow execution.

For Bun, two operations dominate the felt experience:
1. **Startup** — currently Python interpreter start (~30ms) + parse. Bun
   should measure and publish this. A "hello world" under 100ms is
   achievable; under 50ms is a stretch goal worth having.
2. **The feedback loop** — for a web app, the edit→reload→see cycle. Bun
   should provide `bun dev` with file watching, a zero-config reverse
   proxy, and *no* build step (Bun's whole identity). This is the single
   highest-leverage developer-experience feature remaining, and the survey
   says so: "the best language is the one that gets out of the way".

### 6.3 Error diagnostics

The survey's consistent finding across Rust, Swift, TypeScript, and Elm:
**the quality of the error message is a first-order feature of the
language**, not a detail. Elm's compiler errors are legendary; Rust's are
good but often overwhelming; Python's are historically weak (PEP 678 in
3.11 improved them substantially).

Bun's existing diagnostic format (source line + caret) is the right base.
The survey's additional requirements:
- **Expected vs found.** "expected `}`, found end of file".
- **A "did you mean" for near-miss identifiers.** Rust and TypeScript both
  do Levenshtein suggestions; Bun should.
- **A machine-readable form.** `bun check --json` should emit structured
  diagnostics for editor integration. This matters more as Bun is used by
  AI agents, which parse tool output.
- **Suppression of cascading errors.** When one error is found, the checker
  should not emit 40 more. The survey's term is "error recovery budget".

---

## 7. The "human-like AI" dimension

The stated goal includes an AI that feels *human-like* and *consistent*.
The survey's interpretation, and the design conclusion:

An AI assistant built on Bun is human-like to the extent that **Bun's own
behaviour is predictable and explainable**. An assistant that says
"this will work" and is wrong 30% of the time is not human-like; it is
confusing. Human-ness here means:

1. **Consistency** — the same program does the same thing every time.
   No iteration-order randomness, no time-dependent behaviour without an
   explicit clock, no ambient global state that leaks between runs.
2. **Explainability** — every error message tells you what happened, where,
   and what to do next. This is the diagnostic work in §6.3.
3. **Legibility of intent** — code that reads the way a human would
   describe the algorithm. This is the Python-like surface area.
4. **Graceful failure** — a human says "I don't know" rather than guessing.
   The language should make "I don't know" expressible: a `Result`-shaped
   API for anything fallible, and no silent coercion of errors into `null`
   (the `dict.get()` → `None` behaviour in Bun is exactly this: a *missing
   key* is `null`, but a *failed operation* raises).
5. **A stable core.** The language's semantics should be a *specification*,
   not a set of emergent behaviours. The golden-test corpus and the
   differential Python/self-host parity suite are the mechanism that makes
   this true over time.

The **"feel" model** the design document builds on:
- One semantic rule per concept, stated once, in one place.
- Every rule has a test in the golden corpus.
- Every deviation from the rule is a bug, not a feature.

---

## 8. What the survey says to *not* do

The most valuable output of a survey is a negative list.

| Rejected | Reason |
|----------|--------|
| **Classes / inheritance** | Composition and protocols dominate; inheritance's failure modes are well documented. |
| **Ownership & borrowing** | Compile-time complexity out of proportion to the value for a scripting language. |
| **Null-safety with `Option`/`T?`** | The survey's finding: `Option` in dynamic languages is either ignored or checked everywhere. A single `null` with `== null` narrowing is enough. |
| **Full generics with inference** | Trait-solver-scale complexity. |
| **Dependent types** | Research-scale. |
| **Build steps / package registries** | Directly contradicts the zero-config identity. |
| **Exception hierarchies with checked exceptions** | Java's checked exceptions are widely regarded as a net negative. |
| **Macros that expand to syntax** | Huge implementation surface. Bun already has an `ffi`-style escape hatch; that is enough. |
| **Async/await as the only concurrency model** | Desugaring to a state machine is complex; structured `scope` + `spawn` covers the real need at lower cost. |
| **A central package registry** | The project already resolves `bun_modules/<name>` locally; ambient registries are a supply-chain risk. |
| **TypeScript-style `any` proliferation** | Structural rot. |

---

## 9. Synthesised feature ranking

Combining the survey with the stated targets (AI models, games, web,
security, layered architecture, consistency), the ranked roadmap:

| Rank | Feature | Rationale | Estimated size |
|------|---------|-----------|----------------|
| 1 | **F-strings / string interpolation** | Most common Python idiom; huge ergonomics win; pure surface | S |
| 2 | **Comprehensions** | Second most common; enables the functional/data-oriented style games and ML need | M |
| 3 | **Unpacking + keyword args + default/variadic params** | Python parity surface; unblocks real code | M |
| 4 | **`with` / `finally` / exception chaining** | Resource safety; error-message quality | M |
| 5 | **Inline caching in the VM** | The performance unlock; prerequisite for games/ML | L |
| 6 | **Structured concurrency (`scope`)** | Fixes the #1 concurrency bug class | M |
| 7 | **Tensor / numerical core** | Makes "AI models in Bun" literally true | L |
| 8 | **HTTP/2 + HPACK builtins** | Unblocks MTProto; also needed by real-world HTTP | M |
| 9 | **Self-hosted VM** | The self-hosting milestone; the real speed path | XL |
| 10 | **Web stack: server, router, templating, WebSocket** | The "web frontend/backend" target | L |
| 11 | **Game engine core: math, shapes, collision, loop** | The "games" target | L |
| 12 | **`Secret` type + capability sandbox** | The "security" target; also the AI-safety target | M |
| 13 | **Register VM tier** | The "C++-like speed" target | XL |
| 14 | **Slices, `elif` chain sugar, `async` soft keyword** | Polish | S |

---

## 10. Sources consulted (design lineage, not citations)

The survey synthesises established practice from these languages and
projects. Each contributed a specific, named design element:

- **Python** — indentation blocks, expression-oriented statements,
  comprehensions, truthiness, `dict`/list as builtin types, the standard
  library's breadth, PEP 678 exception notes, PEP 695 type parameters.
- **Rust** — ownership (rejected), `Result`/`Option` (partially adopted),
  match ergonomics, diagnostic quality, the borrow-checker-free alternative
  of "safe by construction", self-hosted compiler as a milestone, the
  "no unsafe escape hatch" principle.
- **Go** — batteries-included stdlib, one obvious way, `net/http` model,
  escape analysis, goroutines + channels, scoped concurrency, RE2-style
  regex, the "boring technology" philosophy.
- **TypeScript** — gradual typing, structural typing, narrowing via control
  flow, `satisfies`, the `brand` type for opaque values, the cost of `any`.
- **Swift** — soft keywords, protocol-oriented design, structured
  concurrency, ownership (rejected), arena-free memory model.
- **Kotlin** — soft keywords as a first-class mechanism, coroutine scopes,
  `data class` (rejected — Bun has no classes), null safety.
- **Zig / Nim / Crystal / V / Odin** — comptime (rejected), optional types,
  macro systems (rejected), the value of a "batteries-included" stdlib.
- **Gleam / Roc / Elm** — total functions, exhaustive pattern matching,
  immutability by default, the case for "the compiler explains everything".
- **Lua / Love2D** — embeddability, the game loop, immediate-mode UI.
- **Bevy / Godot** — ECS, data-oriented layout, fixed-timestep simulation,
  the "struct of arrays" storage model.
- **PyTorch / ONNX / micrograd** — tensor shapes, autodiff, model IR, the
  reduction-order determinism requirement.
- **libsodium / `secrecy` / `semgrep`** — the `Secret` type, capability
  models, secret-redaction patterns.
- **CPython internals** — the specialising adaptive interpreter, inline
  caches, the object model Bun's `values.py` deliberately mirrors.
- **V8 / SpiderMonkey** — inline caches, hidden classes, the tiering model
  that Bun's Phase 6/7 should follow.

---

## 11. Open questions carried into the design

1. **Should the tensor core live in the language runtime or in a standard
   library module?** Decision in the design: a *standard library module*
   (`bun:math` / `bun:tensor`) implemented in Bun, so it can be optimised
   separately and is replaceable.
2. **How much of the "human-like AI" belongs in the language vs. the
   assistant?** Decision: the language provides *consistency primitives*
   (deterministic ordering, structured diagnostics, machine-readable output,
   `Secret` redaction); the assistant provides persona.
3. **Does Bun need a GPU binding?** Decision: no in v1. A documented
   CPU-backend + FFI escape hatch is enough; the survey found no language
   that shipped a good GPU story without a native toolchain.
4. **Is `selfhost/vm.bun` Phase 8 or Phase 9?** Decision: Phase 8, because
   it is the milestone that makes every other performance decision
   measurable.
5. **What is the compatibility contract?** Decision: the golden corpus plus
   the differential Python/self-host parity suite *is* the contract; a
   `bun version` command and a `docs/reference/compatibility.md` make it
   explicit.
