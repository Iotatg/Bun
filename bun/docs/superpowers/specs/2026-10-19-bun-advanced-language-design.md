# Bun Language — Advanced Design Specification (Phase 6+)

Date: 2026-10-19
Status: Design specification. Supersedes nothing; extends
`2026-10-14-bun-language-design.md` (v0.1) and the Phase 2–5 specs.

Research input: `docs/superpowers/research/2026-10-19-bun-language-research.md`

---

## 0. Summary

Bun's goal is a language with **Python-like ease and C++-like speed** that can
carry AI models, games, web frontends/backends and security-sensitive work,
and whose behaviour an AI assistant can predict with confidence.

This document specifies the phases of Bun and the architectural spine that
makes them possible.

| Phase | Theme | Headline deliverables |
|-------|-------|------------------------|
| **6** | *Pythonic surface* | f-strings, comprehensions, unpacking, keyword args, default/variadic params, `with`/`finally`, exception chaining, slices |
| **7** | *Performance* | inline-caching tier in the VM, structured concurrency (`scope`), startup budget, instruction profiler |
| **8** | *Self-hosting milestone* | the self-hosted front end and checker; Python stays a pure oracle |
| **9** | *Native stacks* | `bun:tensor` numerical core, `bun:web` (server/router/templates/WebSocket), `bun:game` (math/shapes/collision/loop), `bun:sec` (`Secret`, capabilities, redaction) |
| **10** | *Language surface* | the bit operators, a loop over pairs, a loop over a dict, `assert`, `match` with its alternatives, guards and tails, the `else` of a loop, the word `not` |
| **11** | *Native tier* | the register VM, the verifier, the superinstruction tier |
| **12** | *Model stack* | `bun:ai`: the layers, the model, the format, the losses, the optimisers, the training loop, the tokenisers |
| **13** | *C backend* | the register code emitted as C, the system compiler doing the optimisation, the refusals by name at compile time |
| **14** | *Machine surface* | the session of the language over JSON-RPC 2.0, a value comes back as a value |

Each phase is independently shippable and independently testable. Nothing in
Phase 9 is allowed to require a Phase 10 feature.

---

## 1. Design invariants

These are the rules that no future change may violate. They are the
"consistency contract" the research calls for, and they are what makes the
language learnable — by a human or a model.

### I1 — One rule per concept

Every language concept has exactly one semantics, stated once. Examples:

- `null` equals only `null`. There is no `undefined`.
- `dict["missing"]` is `null`; `dict.get("missing")` is `null`; only
  `dict.remove("missing")` is an error.
- `+` on `str` and `int` concatenates (JS-style coercion), because that is
  what the *user* means; `+` on two ints adds.
- `/` on two ints is floor division; on any float is float division.

**Consequence:** the word "except" must never appear in the reference manual
without a named, enumerated exception list.

### I2 — Two error channels, clearly separated

| Channel | Types | Catchable? | Raised when |
|---------|-------|-----------|-------------|
| **Static** | `LexError`, `ParseError`, `BunTypeError` | **No** | Before execution, with source position |
| **Runtime** | `BunRuntimeError` | Yes, via `try`/`catch` | During execution |

A `try` block can never swallow a static error. This is the Rust insight
(static errors are not runtime events) applied to a language with a dynamic
runtime — and it is what lets an assistant trust `try/catch` to mean "the
program logic failed", not "the program is malformed".

### I3 — Errors are messages, not exceptions, at the boundary

Every `BunError` renders as:

```
error: <what happened>
  --> <file>:<line>:<col>
   |
 L | <the source line>
   | <caret>^ <hint>
```

and additionally exposes a machine-readable form via `bun check --json`:

```json
{"kind": "BunTypeError", "message": "...", "file": "...", "line": 3,
 "col": 11, "snippet": "...", "hint": "...", "labels": [...]}
```

The `--json` form is not a convenience. It is the interface an AI assistant
or an editor consumes, and the reason `bun check --json` is a first-class
command rather than a flag bolted on later.

### I4 — Determinism by default

- Dict iteration order is **insertion order**. (Note: this is Bun's current
  behaviour and differs from JS; it is a deliberate choice for reproducibility
  and it is stated in the reference.)
- Iteration over a list is index order; over a dict is insertion order.
- Floating-point reduction order is specified for the numerical core, so
  `sum` is bit-reproducible across runs and platforms.
- Nothing implicit reads the clock, the environment, or the filesystem.
  Those are explicit builtins.

### I5 — The runtime is the spec

The golden corpus (`tests/golden/*.bun` + `*.out`) and the differential
Python/self-host parity suite are the normative definition of the language.
If the Python pipeline and the self-hosted pipeline disagree on any error
message, the Python pipeline is currently authoritative and the difference is
a bug in the self-hosted one. Phase 8 makes this symmetric (the self-hosted
pipeline becomes authoritative) and the parity suite is what makes that safe.

### I6 — Soft keywords

A word is a keyword only where it has meaning. `from` is a keyword only in
`import ... from ...`; elsewhere it is an identifier. The same rule applies
to every future addition: `as`, `in`, `is`, `type`, `match`, `where`,
`defer`, `async`, `await`, `yield` are soft.

### I7 — Zero third-party runtime dependencies

The Bun runtime ships everything. Packages are resolved from a local
`bun_modules/` directory; there is no ambient registry and no lockfile
download step. This is a security property, not just a convenience.

### I8 — Capability-bounded escape hatch

The only way to reach outside the runtime is `ffi_load`, which accepts an
explicit allowlist of modules. There is no `unsafe` block, no raw
`dlopen`, no shell-string execution. The allowlist is a source file
(`bun/ffi.py`) and therefore auditable.

### I9 — Baked in, but one obvious way

One HTTP client. One JSON implementation. One template engine. Breadth
without choice, following Go rather than Python.

### I10 — Layered, and every layer is a complete implementation

```
                 ┌──────────────────────────────────────────┐
   Layer 6       │  bun:tensor  bun:web  bun:game  bun:sec   │  standard library (Bun code)
                 ├──────────────────────────────────────────┤
   Layer 5       │  runtime services: scheduler, GC, FFI,     │
                 │  event loop, HTTP/2, crypto, TLS          │
                 ├──────────────────────────────────────────┤
   Layer 4       │  VM: bytecode interpreter + inline caches │  bun/vm.py  ->  selfhost/vm.bun
                 ├──────────────────────────────────────────┤
   Layer 3       │  compiler: AST -> bytecode                │  bun/compiler.py -> selfhost/compiler.bun
                 ├──────────────────────────────────────────┤
   Layer 2       │  front end: lexer + parser + checker       │  bun/{lexer,parser,checker}.py -> selfhost/*
                 ├──────────────────────────────────────────┤
   Layer 1       │  values, environments, operators, errors   │  bun/{values,ops,environment,errors}.py
                 └──────────────────────────────────────────┘
```

Each layer above is a *program in Bun* by Phase 8. Each layer's behaviour is
specified by the layer below it and tested independently. The two engines
(tree-walker and stack VM) are not a phase; they are the differential oracle
that makes the whole structure verifiable.

---

## 2. Phase 6 — The Pythonic Surface

Phase 6 adds the missing surface features the research identified. All are
*surface* changes: no new runtime concepts, so each lands in the tree-walker,
the VM, and the self-hosted front end with the same uniform effort.

### 2.1 String interpolation (f-strings)

```bun
let name = "world"
let n = 3
print(f"hello {name}, {n} items")
```

Grammar:

```
fstring := "f" STRING_TEMPLATE
STRING_TEMPLATE := '"' (CHAR | '{' EXPR '}')* '"'
```

Rules:

- The expression inside `{...}` is evaluated like a normal expression.
- `{{` and `}}` are literal braces.
- The conversion suffix `!r` (repr) and `!s` (str) are supported:
  `f"{value!r}"`.
- Format spec: `f"{value:.2f}"` — width, precision, and type are supported
  for `int`, `float`, and `str`.
- A trailing `=` prints the expression source before its value:
  `f"{n * 2=}"` → `n * 2=6`.

Implementation notes:

- The lexer produces a single `FSTRING` token carrying the raw template
  segments; the *parser* splits it into a list of literal/expression parts.
  This keeps the lexer dumb and makes the self-hosted lexer trivial to
  mirror.
- The self-hosted lexer must produce the identical token stream: a `FSTRING`
  token with the same raw text. The parity suite checks the token stream,
  not just the AST.

### 2.2 Comprehensions

```bun
let squares = [x * x for x in range(10)]
let evens = [x for x in range(20) if x % 2 == 0]
let pairs = [(x, y) for x in range(3) for y in range(3)]
let lookup = {k: v for k, v in items}
```

Grammar:

```
comprehension := "[" ( "for" loop ( "if" expr )* )+ "]"     # list
               | "{" expr ( ":" expr )? ( "for" loop )* "}"  # dict
```

- The comprehension creates a **new scope**; loop variables do not leak.
- The first `for` may be preceded by an optional element expression
  (dict comprehensions have a key and an optional value).
- Semantics are exactly "build a list, appending in iteration order".
- The VM implements it as a dedicated opcode pair (`OP_COMPREHEND`) rather
  than desugaring, so it does not pay closure-creation cost per iteration.

### 2.3 Unpacking

```bun
let (a, b) = pair
let [x, y, z] = [1, 2, 3]
let first, *rest = [1, 2, 3]
fn head_tail(list) {
    let head, *tail = list
    return [head, tail]
}
```

- `let a, b = expr` requires `expr` to have exactly 2 elements.
- `let a, *rest = expr` requires at least 1 element; `rest` collects the
  remainder as a list.
- The star form is also valid in assignment: `[a, b] = [1, 2]`.

### 2.4 Function parameters

```bun
fn greet(name: string, greeting: string = "hello") -> string {
    return greeting + " " + name
}

fn sum_all(*nums: int) -> int {
    var total = 0
    for n in nums { total = total + n }
    return total
}

fn call_with(*args, **kwargs) {
    ...
}

fn positional_only(a, b, /) { ... }
```

- **Default values** may be any expression; they are evaluated at call time
  in the function's scope (so they can reference earlier parameters).
- **`*args`** collects surplus positional arguments into a list.
- **`**kwargs`** collects surplus keyword arguments into a dict.
- **Keyword arguments** at the call site: `greet(greeting: "hi", name: "x")`.
- **Positional-only marker** `/` and **keyword-only marker** `*` follow
  Python 3.8+ semantics.

### 2.5 Context managers, `finally`, and exception chaining

```bun
with open("data.txt") as file {
    let content = file.read()
}
```

- `with` requires the target to implement `__enter__`/`__exit__`. Since Bun
  has no classes, the protocol is: the value must be a dict containing the
  keys `"__enter__"` and `"__exit__"`, or the language provides a builtin
  `context(fn enter, fn exit)` helper. **Decision:** Bun provides
  `with` over *duck-typed* methods accessed by name on dict values, and the
  stdlib's file/DB handles implement it.

```bun
try {
    risky()
} catch (e) {
    handle(e)
} finally {
    cleanup()
}
```

- `finally` always runs, including on `throw` and on `return` from `try`.
- `finally` does **not** swallow an in-flight exception unless it throws a
  new one (Python semantics).

```bun
try {
    inner()
} catch (e) {
    throw "wrapped: " + e
}
```

- `throw` accepts any value, not just a string. `str(value)` renders it.
- **Chaining:** `throw` accepts an optional second argument, the cause:
  `throw value, cause`. The error object then carries `cause`.

### 2.6 Slices

```bun
let xs = [1, 2, 3, 4, 5]
let mid = xs[1:3]      // [2, 3]
let tail = xs[2:]      // [3, 4, 5]
let head = xs[:2]      // [1, 2]
let rev = xs[::-1]     // [5, 4, 3, 2, 1]
let s = "hello"[1:3]   // "el"
```

- Negative indices count from the end.
- A step may be given; a negative step reverses.
- Out-of-range indices are **clamped**, not an error (Python semantics), so
  `xs[0:100]` is safe.

### 2.7 `Secret` type

```bun
let key = secret("sk-...")
print(key)            // "***"  (never the value)
let raw = key.reveal() // explicit, greppable unwrap
```

- `secret(value)` returns a `BunSecret` runtime value.
- `str()`, `dump()`, and every log path render it as `"***"`.
- `.reveal()` returns the underlying value; this is the only escape and it
  is greppable.
- The `Secret` value cannot be used in arithmetic, comparison, or as a dict
  key.

This is the structural defence the research recommends: an AI assistant
handling API keys cannot accidentally print one, because printing one is not
possible.

### 2.7a Undefined names are a static error

```bun
print(not_defined)
// error: undefined variable 'not_defined'
```

The checker knows every name of a module before it checks a single
statement, so the order of the definitions does not matter. Inside a
function the names of the whole body are collected first, so a name that is
bound later is still known.

The rule keeps the language honest for an AI assistant: a typo becomes a
diagnostic with a file and a line, not a runtime failure far from the
mistake.

### 2.7b The documentation registry

```bash
bun doc                # every documented symbol
bun doc print          # one symbol
bun doc --json         # the whole registry
bun api --json         # the signature of every builtin
bun test --doc         # run every example of the registry
```

The examples of the registry are hermetic. They never touch the network or
the filesystem, so the documentation proves itself.

### 2.8 Phase 6 acceptance criteria

- Every feature above is implemented in: `bun/lexer.py`, `bun/parser.py`,
  `bun/ast.py`, `bun/checker.py`, `bun/compiler.py`, `bun/vm.py`,
  `bun/interpreter.py`, `selfhost/lexer.bun`, `selfhost/parser.bun`,
  `selfhost/checker.bun`, `selfhost/compiler.bun`.
- Every feature has a golden case in `tests/golden/` and unit cases in
  `tests/`.
- The self-hosted pipeline produces **byte-identical** error messages for
  every new construct (extended `CHECKER_ERROR_CASES` in
  `tests/test_selfhost.py`).
- The tree-walker and the stack VM produce identical output for every golden
  case.

---

## 3. Phase 7 — Performance

Phase 6 makes Bun pleasant; Phase 7 makes it fast. The ordering matters:
the performance work should land on a language surface that is already
complete, because the inline caches and register VM must be tuned against
real code, not a moving target.

### 3.1 Inline caching

**Problem.** Every `OP_GET_MEMBER` and `OP_CALL` in the current VM performs a
dictionary lookup on the receiver's type. For a dict-backed object, that is
a hash lookup; for a builtin type it is a linear scan of a method table.

**Design.** Each call site in the bytecode carries a cache slot (an
indexed-array of `ShapeId -> offset`).

```
OP_GET_MEMBER  <cache_slot>  <name_const>
  shape = shape_of(receiver)
  cached = cache[cache_slot]
  if cached != null and cached.shape == shape:
      result = receiver.fields[cached.offset]
  else:
      slow path: resolve, fill cache, result = ...
```

**Shape identity.** A *shape* is the identity of a value's "kind +
member set":

- `list` → a single shape.
- `str` → a single shape.
- `dict` → the identity of its key-set (interned).
- function → a single shape.

For dicts, a *key-set shape* is only stable while the dict's key set does
not change; mutation invalidates the shape. This is precisely V8's model,
and it is why `BunDict` must track an interned key-set id.

**Invalidation.** Adding or removing a key bumps the dict's shape id. All
caches keyed on the old shape id become stale but not incorrect (the
comparison fails and the slow path runs).

**Expected gain.** 2–4× on dispatch-heavy code; near-zero on numeric loops.

### 3.2 Structured concurrency (`scope`)

```bun
scope {
    let a = spawn { compute_a() }
    let b = spawn { compute_b() }
    let ra = task_join(a)
    let rb = task_join(b)
}
```

Semantics:

- `scope` runs its body with a *child task group*.
- When the block exits, the group **joins** every outstanding child. If any
  child raised, the first error is re-raised in the parent after all children
  have been joined.
- A child may be *cancelled* via a `cancel()` handle; the group joins
  cancelled children too.
- Unstructured `spawn` outside a scope keeps its current semantics but is
  documented as "unstructured" and discouraged.

This is Go's `errgroup` + Swift's `TaskGroup` + Kotlin's `coroutineScope` in
one construct. It fixes the largest class of concurrency bug (tasks
outliving the scope that spawned them) with a small, well-understood
mechanism.

**Implementation status (Phase 7).** The statement form is implemented in
both front ends and both engines:

- `scope { ... }` opens a task group, runs the body, and joins every child
  of the group. The group is closed on the error path as well, so a failing
  body never leaves tasks running behind it.
- The error of a child is raised in the parent after all children have been
  joined. The error of the body wins over the error of a child.
- `spawn { ... }` is sugar for `spawn(fn() { ... })`.
- Cancellation is cooperative: `cancel(handle)` asks a task to stop and
  `task_cancelled()` lets the task notice. A thread cannot be killed
  safely, so a task always decides when to stop.
- `scope` is a soft keyword: it only starts a scope when a block follows it
  on the same line, so the name stays usable as an ordinary variable.

### 3.3 Register-VM groundwork

Phase 7 does not build the register VM; it prepares it.

- The bytecode gains a **typed** instruction stream: each instruction records
  its operand types, so the compiler can emit register-style operations.
- The VM's frame layout becomes **slot-based** rather than stack-based
  behind a compatibility layer, so the register VM can be introduced
  without rewriting the compiler.
- A `bun compile --profile` command reports the hot instructions of a
  workload, which is the measurement the register VM design needs.

### 3.4 Startup-time budget

Bun publishes a startup budget and tests it in CI:

| Metric | Target |
|--------|--------|
| `bun run hello.bun` (tree-walker) | < 120 ms |
| `bun run hello.bun` (VM) | < 140 ms |
| `bun check` on a 1000-line file | < 400 ms |

Startup is the most-felt performance property, and the research is explicit
that perceived speed beats average speed.

---

## 4. Phase 8 — The Self-Hosting Milestone

**Goal:** `selfhost/vm.bun` — a stack VM written in Bun, executing bytecode
produced by `selfhost/compiler.bun`.

After Phase 8, the pipeline is:

```
.bun source
   -> selfhost/lexer.bun   (runs on the Python VM)
   -> selfhost/parser.bun
   -> selfhost/compiler.bun
   -> bytecode
   -> selfhost/vm.bun      (runs on the Python VM initially)
   -> execution
```

And, once `selfhost/vm.bun` is itself compiled by the self-hosted compiler,
the *same* artifacts run the compiler: full self-hosting.

### 4.1 The bootstrap problem and its solution

A self-hosted compiler needs a compiler to compile itself. The standard
solution is a **three-stage bootstrap**:

```
stage 0: Python pipeline compiles selfhost/*.bun  -> stage1 artifacts
stage 1: stage1 artifacts compile selfhost/*.bun  -> stage2 artifacts
stage 2: stage2 artifacts compile selfhost/*.bun  -> stage3 artifacts
```

**Requirement: `stage1 == stage2 == stage3`, byte for byte.** This is the
canonical proof of a correct bootstrap (the same technique as the "stage 2
is reproducible" property of the GHC and Rust bootstraps).

Bun's twist, and the reason the design is interesting: because the
self-hosted front end is *already* written in Bun and produces the *same*
bytecode as the Python compiler (guaranteed by the Phase 4/5 parity work),
the bootstrap only needs to cover the **VM**, not the whole compiler. The
Python pipeline becomes a pure oracle, and the "self-hosted" claim becomes
exactly as strong as the VM's correctness.

### 4.2 What Phase 8 changes

- `bun/vm.py` and `selfhost/vm.bun` must produce **identical observable
  behaviour**, including error messages and their source positions.
- The Python implementation is retained forever as the oracle and as the
  reference implementation in the docs.
- `bun run --front-end bun` becomes the default for `bun serve` and
  `bun dev` once Phase 8 lands, because the self-hosted path is then both
  correct and faster to start.

### 4.3 Acceptance criteria

- `stage1 == stage2 == stage3` byte-for-byte, verified by
  `tests/test_bootstrap.py`.
- A golden corpus of at least 200 programs runs identically under:
  Python tree-walker, Python VM, self-hosted front end + Python VM, and
  self-hosted front end + self-hosted VM.
- The self-hosted VM's own source is compiled by the self-hosted compiler.

---

## 5. Phase 9 — The Native Stacks

Phase 9 adds the four domain stacks the research identified. Each is a
standard-library module written **in Bun**, using the Phase 6/7 language.

**The shape of the API.** Bun has no classes, so a stack is a set of module
functions and the data is a plain dictionary. `get(router, "/", handler)`
is a route and not `router.get("/", handler)`, and `on_update(game, fn)`
is a callback and not `game.on_update(fn)`. The rule keeps the data of a
stack readable and replaceable: a user can print a router, write it to a
file and read it back.

**Status.** `bun:tensor`, `bun:sec`, `bun:game` and `bun:web` are done
(`docs/superpowers/plans/2026-10-19-bun-phase-9.md`). The parts of the
web stack that are still to do: keep-alive, chunked responses, the static
file server and the HTTP client with a pool.

### 5.1 `bun:tensor` — the numerical core

```bun
import { tensor, zeros, ones, matmul, softmax, relu, adam } from "bun:tensor"

let x = tensor([[1.0, 2.0], [3.0, 4.0]])
let w = tensor([[0.5, -0.2], [0.1, 0.9]])
let y = matmul(x, w)
let p = softmax(y, 0)
```

Design:

- **Storage:** flat, contiguous `list` of `float`, plus a shape vector.
- **Dtype:** `float32` and `float64` (and `int64` for indices). The dtype
  affects only the *interpretation* of the flat buffer; Bun's numbers are
  Python floats (doubles), so `float32` is stored as doubles with
  float32 rounding applied on write. This is honest and simple; true
  float32 arithmetic comes with a native tier.
- **Shape polymorphism:** operations dispatch on shape *outside* the element
  loop. `matmul` on `[m,k] x [k,n]` never branches per element.
- **Determinism:** reductions use a **fixed, specified order** (a
  pairwise/tree reduction) so `sum` is bit-reproducible. This is a hard
  requirement, not a nicety: reproducibility is a precondition for
  training runs to be comparable.
- **Broadcasting:** a small, well-defined subset (rank-1 against rank-2),
  with an explicit error otherwise.
- **Autodiff:** a reverse-mode tape over the same ops, enabling
  backpropagation without a second implementation.

`bun:tensor` is written in Bun and is replaceable; a user who wants
production-grade inference uses the FFI profile (§5.4) instead.

### 5.2 `bun:web` — the web stack

```bun
import { Router, get, serve, serve_forever, html, raw } from "bun:web"

let app = Router()
get(app, "/", fn (req) { return html("<h1>hello</h1>") })
get(app, "/users/:id", fn (req) { return html("<p>{{ id }}</p>", { "id": req["params"]["id"] }) })
let server = serve(app, 3000, "0.0.0.0")
serve_forever(server)
```

Components:

| Module | Contents |
|--------|----------|
| `serve` | HTTP/1.1 + HTTP/2 server, keep-alive, chunked, graceful shutdown, TLS |
| `router` | Path parameters only (`/users/:id`); no regex routes in v1 |
| `html` | Auto-escaping templates; `raw()` escape hatch |
| `static` | Static file serving with correct MIME types, ETag, range requests |
| `websocket` | RFC 6455 client and server |
| `proxy` | Reverse proxy to a backend service (the pattern this project already uses) |
| `client` | HTTP client with keep-alive and connection pooling |

**Auto-escaping by default.** `html("<b>")` escapes the *value*, and the
template author marks trusted fragments with `raw(...)`. XSS-by-default is
the industry's recurring failure; this is the "human-like" design choice.

**`bun dev`** — the development server. It watches the source tree, restarts
the app, and serves a **reverse proxy** so that a frontend and a backend can
run behind one exposed port with one command. This is the pattern the
project's own rules require, so the language should provide it as a
built-in rather than making every project re-implement it.

### 5.3 `bun:game` — the game engine core

```bun
import { vec2, vec2_add, vec2_scale, Game, on_update, advance } from "bun:game"

let game = Game({ "width": 800.0, "height": 600.0 })
on_update(game, fn (dt) {
    player["pos"] = vec2_add(player["pos"], vec2_scale(player["vel"], dt))
})
advance(game, 1.0 / 60.0)
```

Components:

- **Math:** `vec2`, `vec3`, `vec4`, `quat`, `mat2/3/4`, with operators.
- **Shapes:** `rect`, `circle`, `point`, `segment`, `ray`; intersection
  tests; containment.
- **Loop:** a fixed-timestep update loop with an accumulator, plus render
  interpolation. The fixed timestep is not optional — variable-dt physics
  is nondeterministic and breaks replays.
- **Entities:** data-oriented storage (struct-of-arrays) with a free-list,
  so entity updates are tight loops over flat lists.
- **Collision:** a uniform-grid broadphase plus shape narrowphase.
- **Input:** keyboard/mouse/gamepad state with edge detection
  (`just_pressed`).
- **Audio:** mixing buses, positional playback, streaming decode.
- **Rendering:** a **bitmap font** renderer and an SDF font rasteriser
  first; a GPU backend is a documented future path, not a v1 promise.

The research's conclusion is that games in Bun are viable **if and only if**
dispatch cost is fixed — which is why Phase 7's inline caching is a hard
prerequisite for this stack, and why entity storage is struct-of-arrays
rather than a dict of objects.

### 5.4 `bun:sec` — the security layer

```bun
import { secret, capability, redact, sandbox } from "bun:sec"

let token = secret(read_env("OPENAI_API_KEY"))
let policy = capability({ "net": ["api.openai.com"], "fs": ["./data"] })
let result = sandbox(policy, fn () { call_api(token) })
```

Components:

- **`Secret`** — as §2.7. Redacted from `str()`, `dump()`, logs, error
  messages, and any structured output.
- **`capability`** — a declarative manifest of what a piece of code may do
  (network hosts, filesystem paths, process spawning, clock access).
- **`sandbox`** — runs a closure under a capability manifest; violations
  raise a `BunRuntimeError` naming the blocked capability.
- **`redact`** — a pass over any outbound payload (an LLM request, a log
  line, a webhook body) that removes values marked secret and known
  secret-shaped patterns (e.g. `sk-...`, AWS keys, bearer tokens).
- **Crypto primitives** in the runtime: SHA-256/512, SHA-3, HMAC,
  AES-GCM, ChaCha20-Poly1305, Ed25519, X25519, HKDF, Argon2id, scrypt.
  Key derivation uses the runtime's CSPRNG, never `random`.

### 5.5 The FFI profile

`ffi_load` currently allowlists a set of stdlib modules. Phase 9 extends it
to a *profile* mechanism:

```bun
// bun.toml
[ffi]
allow = ["math", "time", "json", "hashlib", "base64", "urllib.parse", "re"]
```

with named profiles (`ffi.profiles["numeric"] = ["numpy", "scipy"]`) that a
user opts into explicitly. The allowlist remains a source file and
therefore auditable, and the *default* profile never changes without a
major version bump.

---

## 6. Phase 10 — The Language Surface

Phase 10 closes the gaps that a Python programmer meets in the first
hour: the bit operators, the loop over pairs, the loop over a dict, the
assertion and the `match` statement. The plan is
`docs/superpowers/plans/2026-10-19-bun-phase-10.md`.

### 6.1 The bit operators

`&`, `|`, `^`, `~`, `<<` and `>>`, with Python's spelling and Python's
precedence, so the operators sit between the comparison and the
arithmetic. The operands are integers; a float is an error.

```bun
let flags = 0b1010
print(flags & 0b0110)   // 2
print(flags | 0b0001)   // 11
print(flags ^ flags)    // 0
print(flags << 2)       // 40
print(flags >> 1)       // 5
```

The binary literal `0b1010` comes with them: a mask that is written in
decimal is a mask that nobody can read.

### 6.2 The loop over pairs and over a dict

```bun
for name, value in pairs {
    print(name + " is " + str(value))
}

for key in data {
    print(key + " = " + str(data[key]))
}
```

The target of a loop is a list of names, and the shape of the elements
must match it, the same rule the unpacking in an assignment follows. A
dict is walked by its keys, in the order the keys were put in.

A loop may have an `else`, the block that runs when the loop ends
without a `break`. A loop has a scope of its own, so the name of the
loop is gone when the `else` runs.

### 6.3 `assert`

```bun
assert count > 0, "the count must be positive"
```

An assertion states an invariant of the program, so it is a statement
and not a function. A failed assertion throws a runtime error whose text
starts with `assertion failed`.

### 6.4 `match`

The dispatch on the shape of a value:

```bun
match response {
    200 => print("ok"),
    404 => print("not there"),
    _ => print("something else"),
}
```

The patterns of the first version are the literal, the binding, the
wildcard, the type name, the range, the list and the dict. The first
case that matches wins, and the cases are tried in the order they are
written. This is the feature that makes the language interesting: the
dispatch on the shape of a value is one statement instead of a chain
that grows with every new case.

A case may name more than one pattern, and the first one that matches
wins: `301, 302 => print("moved")`. The alternatives come before the
`=>` and the comma that separates two cases comes after the body of a
case, so the two commas never meet.

A case may also have a guard, a condition that has to hold for the case
to match: `n if n > 0 => print(n)`. A guard that does not hold sends the
case on to the next one, the same way a pattern that does not match.
The guard sees the names the pattern binds.

A list pattern may have a tail, the rest of the list bound to a name:
`[first, *rest]`. A list without a tail has to have the length of the
pattern, and a list with a tail has to have at least the length of the
fixed items.

`match` is a soft keyword, like `scope`: it only starts a match
statement when a subject and a block follow it, so `let match = 3` is
still a valid program. A pattern becomes a plan, and the plan is the
same in the two pipelines, so the two engines test a value in the same
way. The names of a pattern are bound in the scope of its own case, and
they are only bound when the whole pattern matches.

### 6.5 The word `not`

The negation of the language has two spellings: the mark `!` and the word
`not`.

```bun
print(not true)      // false
print(not 1 == 2)    // true
```

The word has Python's precedence: it binds looser than a comparison and
tighter than `and`, so `not a == b` means `not (a == b)` and
`not false and true` means `(not false) and true`.

The parser lowers the word to the mark, so the checker, the compiler and
the runtime know one operation and not two. The two spellings are the same
operation, and a program that uses both behaves the same way.

---

## 7. Phase 11 — The Native Tier

Phase 11 is the "C++-like speed" deliverable, and it is deliberately last
because it is the most expensive and the least semantically risky.

### 7.1 The register VM

The register VM replaces the stack machine with a typed, register-based
bytecode. Design points drawn from the research:

- **Three-address form:** `ADD r_dst, r_a, r_b`.
- **Typed instructions:** each opcode carries its operand types, so the
  verifier can prove type safety and the compiler can specialise.
- **Verification:** a verifier runs at load time, exactly as the JVM does.
  The bytecode remains memory-safe.
- **Inline caches survive:** the register VM keeps the same cache-slot
  mechanism, so the Phase 7 work carries over.

Expected gain over the stack VM: 20–40% on integer workloads, more on
branch-heavy code.

### 7.2 Tiered execution

```
source ──> bytecode ──> interpreter ──(hot counter)──> optimising tier
                              │                                │
                              └──────── profile ───────────────┘
```

The optimising tier is a **superinstruction** tier rather than a full JIT:
the interpreter counts executions per (opcode, profile) pair and, past a
threshold, replaces the pair with a fused superinstruction. This is a
meaningful fraction of the JIT benefit at a small fraction of the
complexity and risk, and it keeps the language memory-safe and
deterministic.

What was built is the static half of the idea: the fusion of the pairs of
loads happens at load time, on the code that the verifier has already
checked, and the count of the pairs is what the program reports. The
counted half — a fusion that depends on what the program did while it
ran — is the work of a real optimising JIT, and it is deferred.

### 7.2.1 What was built

The register tier has four parts, and every one of them is in the tree:

- **The register code** (`bun/regcode.py`): an instruction is four cells,
  the opcode and three operands, and the meaning of a cell depends on the
  opcode.
- **The registerizer** (`bun/regcompile.py`): the walk over the stack
  bytecode that moves the values of an expression from the operand stack
  into the registers of a frame.
- **The verifier** (`bun/regverify.py`): the proof that the code is well
  formed — the registers are inside the file, the jumps land on an
  instruction of the same function, the depth of the expression is the
  same on every path, and every function ends with a return or a halt.
- **The register VM** (`bun/regvm.py`): the machine that runs the code,
  with the same environments, the same builtins and the same errors as
  the stack VM.

The engine is chosen with `--engine register`, and the tier with `--tier`.
The stack VM stays the reference semantics and the default.

### 7.3 Optional AOT

With the self-hosted VM (Phase 8) and the register VM (Phase 11), an
ahead-of-time path becomes possible:

- **A C backend:** the register bytecode is emitted as C, compiled by the
  system compiler. This is the fastest route to real speed and the least
  risky, because the C compiler does the register allocation and the
  optimisation. **Phase 13 built this one** — see §9.
- **A WASM backend:** the register bytecode is emitted as WebAssembly
  text, which gives a portable, sandboxed, fast artifact with no system
  toolchain required. This one is still to do.

Both are optional and additive. The interpreter remains the reference
semantics, and any program must produce identical output under every tier
(this is testable with the golden corpus).

---

## 8. Phase 12 — The Model Stack

Phase 12 answers the part of the goal that the language has to earn
rather than the part it can claim: *AI models*. The research behind it
is in `docs/superpowers/research/2026-10-20-bun-ai-stack.md`.

The design rules:

- **A model is data.** It is a dictionary with the weights, the layers
  and the seed. Bun has no classes, and the other stacks already made
  their data plain dictionaries, so a model follows the convention that
  exists rather than inventing a second one.
- **A layer is a function.** The convention of every other stack: no
  methods, no objects, just functions that take tensors and return
  tensors.
- **One tape.** The gradient is the reverse-mode tape of `bun:tensor`,
  and a layer of another stack records its rule on that one tape, so a
  model made of layers of two stacks trains with one backward pass.
- **A seeded generator.** A draw is a function of the seed and the
  counter, never of the clock. A training run is then a test: the same
  seed gives the same losses, down to the last digit.
- **The file of a model is the model.** The JSON of a model has the shape
  of the model, so a binary format is a walk over that shape and not a
  redesign.

What the phase does **not** have is a fast attention. The matrix multiply
of the runtime is interpreted, so the attention matrix of a wide
transformer would take minutes per step. The attention and the block of a
transformer are here anyway, written as one operation with one rule and
with the loops by hand, so a step of a small model stays short. What the
phase has is the whole loop — build, train, save, load, run — for the
recurrent family and for the transformer.

---

## 9. Phase 13 — The C Backend

Phase 13 makes good on the promise of the native tier: a program of Bun that
runs at the speed of the machine it is on. The research behind it is in
`docs/superpowers/research/2026-10-20-bun-c-backend.md`.

The design rules:

- **The input is the register code.** The backend does not walk the syntax
  tree; it reads the flat, verified code of the native tier, so the shape of
  the backend is the shape of the machine.
- **One C function per Bun function.** The closures are environments, and the
  environments are the same hash tables the VM uses, so the calling
  convention of the backend is the calling convention of the language.
- **Flat C with `goto`.** One label per instruction, and the jumps become
  `goto`, so the code on the page is the code of the register file. The
  system compiler does the optimisation, because the optimisation is the
  one thing a language should not write twice.
- **Refuse, never guess.** A construct the backend cannot translate is
  refused at compile time, with the name of the construct. The `with` and
  the `scope` are refused that way, and so is a builtin the backend does
  not have.
- **The backend links its modules.** A module of a program is compiled with
  the compiler of the language and linked into the C program: its body
  becomes functions of the C program, the values it exports live in a
  table, and a module runs once, the first time it is imported. A module
  the backend cannot translate is refused by name, with the name of the
  builtin or of the construct it does not have.
- **The `match` of the language is a plan.** A case is a plan, the plan is
  filled when the program starts, and the matcher of the runtime walks it.
  The bindings of a case are collected first and applied after, so a case
  that does not match leaves nothing behind.
- **The builtins a program reaches for on the first line are in the
  backend.** `print`, `len`, `range`, `str`, `int`, `chr`, `ord`, `float`,
  `type_of`, `bool`, `abs`, `sum`, `any`, `all`, `min`, `max`, `zip`,
  `enumerate`, `sorted` and `reversed`. The comparison of the sorting
  builtins throws the message of the machine, so a program that sorts two
  dictionaries fails the same way under both engines.
- **The oracle is the golden corpus.** Every program of the corpus that the
  backend supports prints the same bytes under every engine, and the
  programs it does not support are refused by name.
- **The names of a frame live in the frame.** The backend works out, for
  every name, whether a closure ever needs it. A name that no closure takes
  is a slot of the frame of its function; a name that a closure takes, or
  that a jump may skip, stays in the table of the scope. A scope builds a
  table only when it holds such a name, and a function with no closure
  builds no table at all.
- **A failure has a picture.** The backend writes the position of the
  source before the instructions that can fail, and the program carries the
  lines of the source and the table of the advice of the machine. A failure
  of the backend reads like a failure of the machine, down to the caret and
  the hint.

The measurement is published: the run of the native backend is about ten
times faster than the run of the stack VM on the machine of the phase, and
`tools/bench_c.py` prints the number. The frame slots changed the picture
again: a loop of ten million turns takes 130 ms and 10 MB under the backend,
where it took 56.9 s and 4.7 GB before, and the recursion of `fib(30)`
takes 198 ms where it took about 96 s.

---

## 10. Phase 14 — The Machine Surface

Phase 14 finishes the promise of the feel model: the language has to be
*queryable*, not just readable. The research behind it is in
`docs/superpowers/research/2026-10-20-bun-machine-surface.md`.

The design rules:

- **JSON-RPC 2.0, one object per line.** The protocol of the tools, and
  a framing that every tool of the world already knows.
- **A session.** The value of a session is its state: a name defined by
  one call is visible to the next one.
- **A value is a value.** The answer of `eval` is the value of the
  expression, not the text of it. The text is there as well, for the
  human.
- **The errors keep the channels of the language.** The kind of the error
  is `lex`, `parse`, `type` or `runtime`, with the message, the line and
  the column.

The surface never changes the language: it uses the same front end, the
same checker and the same machine as the REPL.

---

## 11. The "Feel" Model

The research framed the "human-like AI" requirement as: an assistant is
human-like to the extent that the language is predictable. This section
turns that into concrete mechanisms.

### 11.1 The seven coherence rules

1. **One way to say a thing.** `len(xs)` for lists and strings; `xs.len()`
   also works but is the *same* rule, not a second one.
2. **Errors say what to do next.** Every error message includes a hint.
   *(Built: `bun/errors.py` `HINTS` — the table is matched in order, and
   the first pattern in the message wins. The hint is added by the
   presentation layer, `format_error`, so the Python front end and the
   self-hosted front end print the same thing; the protocol carries the
   same hint in `data.hint`.)*
3. **Silence is not an option.** A failed operation does not return `null`;
   only a *missing* thing returns `null`.
4. **Order is stated.** Dict iteration is insertion order; it never changes
   silently.
5. **Static means static.** If the checker says no, the program is wrong.
   If it says yes, the program runs (and may still fail at runtime for
   data-dependent reasons — clearly signposted).
6. **The same code reads the same way.** No context-dependent syntax
   except where the language explicitly softens a keyword.
7. **Batteries, but one way.** Breadth without choice.

### 11.2 The machine-readable surface

For an assistant to work with Bun, the language must be *queryable*, not
just readable:

| Command | Purpose |
|---------|---------|
| `bun check --json` | Structured diagnostics (kind, position, snippet, hint) |
| `bun doc <symbol>` | Machine-readable signature, docstring, and examples |
| `bun api --json` | The full builtin signature table (the one in `bun/types.py`, exported) |
| `bun repl --json` | A REPL that speaks JSON-RPC, so an assistant can evaluate expressions in a persistent session — **built in Phase 14** |
| `bun test --json` | Structured test results — **built in Phase 14**: the golden corpus, as a JSON report |

The `bun api --json` command is particularly valuable: the builtin
signature table is already maintained in two places (`bun/types.py` and
`selfhost/checker.bun`) and *must* stay in sync. Exporting it removes the
need for an assistant to read source.

### 11.2.1 The session of the language

Phase 14 built the session the table above asks for. The design is in
`docs/superpowers/research/2026-10-20-bun-machine-surface.md`.

The protocol is JSON-RPC 2.0 over the standard input and the standard
output, one object per line, with the methods `eval`, `check`,
`compile`, `symbols`, `docs`, `api`, `reset` and `shutdown`.

Two decisions carry the weight:

- **The answer is a value, not a text.** The caller asks for a number and
  gets a number. The text of the value is in the answer as well, because
  a human reads the text, but the structure is the answer.
- **The errors keep the two channels of the language.** The kind of the
  error is `lex`, `parse`, `type` or `runtime`, and the data of the error
  carries the message, the line and the column. A static failure and a
  runtime failure are the same shape, because the difference that matters
  to the caller is in the data.

The session holds the machine and the scope of the names, so a name
defined by one call is there for the next one, and the protocol never
changes the language: it is a surface over the same front end, the same
checker and the same machine.

### 11.3 The `bun doc` corpus

Every builtin and every stdlib module carries a docstring with a
description, a signature, and a runnable example. `bun doc` renders it for
humans; `bun doc --json` renders it for tools; `bun test --doc` runs every
example in the corpus and fails the build if an example breaks. **The
examples are therefore always correct** — they are tested, not written.

---

## 12. Testing Strategy (extended)

The existing strategy is preserved and extended:

| Layer | Test type | Tool | Gate |
|-------|-----------|------|------|
| Lexer | unit | pytest | per token type |
| Parser | unit + AST shape | pytest | per construct |
| Checker | unit + error message | pytest | exact message |
| Interpreter | unit | pytest | value equality |
| VM | differential vs interpreter | pytest | identical output |
| Self-hosted front end | differential vs Python | `tests/test_selfhost.py` | identical tokens, AST, and error messages |
| Bootstrap | reproducibility | `tests/test_bootstrap.py` | `stage1 == stage2 == stage3` |
| Golden corpus | end-to-end | `tests/golden/` | `.bun` output == `.out` |
| Docs | executable examples | `bun test --doc` | every example runs |
| Performance | budgets | `tests/test_perf.py` | startup and hot-loop thresholds |

The golden corpus is the normative specification (invariant I5). It is the
single most important artefact in the project, because it is what makes
"the language behaves the same way everywhere" checkable rather than
aspirational.

---

## 13. Migration and Compatibility

Bun pre-1.0 makes no compatibility promise beyond the golden corpus, but it
follows a discipline:

- Every behaviour change is accompanied by a golden-corpus change in the
  same commit.
- `bun version` reports the language version, the runtime version, and the
  front-end in use.
- `docs/reference/compatibility.md` lists every intentional difference from
  Python, with the reason. This document is the answer to "is Bun a Python
  clone?" — it is not, and the differences are deliberate.

---

## 14. The Roadmap in One Page

```
Phase 6   Pythonic surface      f-strings, comprehensions, unpacking,
                               kwargs/defaults/*args, with/finally,
                               chaining, slices, Secret
Phase 7   Performance            inline caches, structured concurrency,
                               register-VM groundwork, startup budget
Phase 8   Self-hosting milestone  selfhost/vm.bun, 3-stage reproducible
                               bootstrap, self-hosted default
Phase 9   Native stacks          bun:tensor, bun:web, bun:game, bun:sec,
                               FFI profiles
Phase 10  Language surface       bit operators, for a, b in ...,
                               for key in a dict, assert, match
Phase 11  Native tier            register VM, superinstruction tier,
                               C / WASM AOT backends
Phase 12  Model stack            bun:ai: layers, model, format, losses,
                               optimisers, training loop, tokenisers
Phase 13  C backend              the register code emitted as C, the
                               refusals by name, the linker of the
                               modules, the published number
Phase 14  Machine surface        bun repl --json: the session over
                               JSON-RPC 2.0, the values as values
Phase 16  Everyday language      the set, the type aliases number and
                               text, the decorators
```

The Ankita Music Bot in `ankita-music/` is the reference application. It
exercises the module system, the error model, the FFI surface, the HTTP
client, the persistence layer, and the command/handler architecture. As the
language grows, the bot grows with it — it is the dogfooding oracle the
research says a language needs.

---

## 15. Open Design Questions

1. **Should the tensor core dispatch on shape at the element level or
   specialise at compile time?** Decision pending: start with shape
   dispatch outside the loop; specialise in Phase 11.
2. **Does `with` need real protocol objects, or is the dict-with-methods
   convention enough?** Decision pending: the convention is sufficient and
   avoids reintroducing classes.
3. **Should the REPL be JSON-RPC from the start?** Leaning yes — it is the
   interface an assistant uses, and retrofitting it is harder than
   starting with it.
4. **How big can the golden corpus get before it needs sharding?** At
   present it runs in ~170 s; sharding at ~500 cases.
5. **Does the register VM need a separate verifier, or can the compiler
   guarantee validity?** The JVM's answer (a verifier) is the safe one and
   the survey supports it; a compiler-only guarantee makes a
   hand-assembled bytecode path impossible.
