# Bun Language — Phase 3.5 Design: Bytecode Compiler and Stack VM

Date: 2026-10-15

## Goal and Motivation

The Phase 3 spec deferred the original "bytecode compiler + VM" phase because
startup-speed motivation did not hold: a Python-hosted interpreter's startup is
dominated by the Python runtime itself (~30-50 ms), and a VM does not change
that. The VM is now taken up for a different, concrete reason:

**Phase 3.5 exists to make Phase 4 (self-hosting — rewriting Bun in Bun)
possible.** Phase 4's Bun-written compiler must run on an engine, and it must
emit code that the engine executes. A stack VM is that engine, and a plain-data
bytecode format is that emission target. The tree-walker could technically run
a Bun compiler too, but the VM gives self-hosting a stable, documented
compile/run interface and removes AST-node construction from the runtime path.

Deferred-motivation context that still stands and shapes this design:

- Throughput gain (~2-5x) is a welcome side effect, not the goal.
- The VM is a third AST consumer (interpreter, checker, compiler) and must
  replicate the tree-walker's semantics exactly; differential testing is
  mandatory and is the acceptance gate.

## 1. Architecture and Data Model

### New modules

- `bun/compiler.py` — compiles an AST into code objects. Pure: it holds no
  execution state and performs no I/O.
- `bun/vm.py` — the execution engine: dispatch loop, call frames, operand
  stack. Consumes code objects; imports nothing from `bun/interpreter.py`
  except shared semantic helpers.

### CodeObject (the Phase 4 emission interface)

A plain dict, so a Bun-written compiler in Phase 4 can construct one directly
from Bun values:

```python
{
    "name": str,               # function name, or "<module>" for top level
    "params": [str, ...],      # parameter names, in order
    "code": [Instruction, ...] # instruction tuples, see below
    "filename": str,
    "source": str,
}
```

The dict shape is the stable interface between any compiler (this phase's
Python one, Phase 4's Bun one) and the VM.

### Instruction

A 4-tuple: `(op, arg, line, col)`.

- `op` — opcode string constant.
- `arg` — the instruction's single operand field: `None`, a scalar (name,
  constant value, jump target, count), or a tuple for multi-field operands
  (e.g. `("name", nargs)` for method calls).
- `line`, `col` — source position of the AST node that produced the
  instruction; used for `BunError` fidelity. Present on every instruction,
  including non-raising ones, so emission code stays uniform.

### Environment

The existing `bun/environment.py` is reused unchanged: name-based scopes with
parent chain and per-binding mutability. No new value model is introduced.

### Frames

A call frame carries `(code, ip, env, stack, base_dir)` plus bookkeeping: `handlers` (try/catch handler stack), `iterators` (for-loop iterator stack), `caller` (previous frame), and `depth` (recursion depth for the frame limit). The VM is a single flat
`while` loop over frames, so deep Bun recursion consumes no Python stack
(unlike the tree-walker's `_evaluate` recursion). A frame limit (10000) raises
`BunRuntimeError("stack overflow")` with the calling instruction's line/col.
This is the one place the VM is intentionally stricter than the tree-walker,
which can hit Python's `RecursionError` on the same program. `base_dir` is the
directory that relative `IMPORT` paths resolve against: the main frame gets it
from `run_source`; each module frame gets `module_dir(full_path)`.

### CLI wiring

- `run_source(source, filename, check=True, engine="vm")` — `engine` accepts
  `"vm"` and `"tree"` from day one; the default is `"tree"` until the cutover
  gate in section 4 passes, after which it flips to `"vm"`.
- The checker runs before either engine, unchanged.
- `bun --engine tree|vm file.bun` for operator rollback.
- The REPL keeps one persistent environment across lines; its engine follows
  the CLI default.

## 2. Instruction Set and Compilation Strategy

### Strategy

Every expression compiles to instructions that leave exactly one value on the
stack. Statements leave nothing. Control flow uses jumps with two-pass
backpatching (emit placeholder, patch target after the body is compiled).

Semantics deliberately delegate to the tree-walker's existing helpers
(`_binary`, `_method_call`, `_index`, `Environment`, `stringify`) so the VM
cannot drift from the oracle. The VM's speedup comes from flat dispatch, not
from reimplementing semantics.

### Opcodes

| Group | Opcode | arg | Semantics |
|---|---|---|---|
| Constants | `LOAD_CONST` | value | Pushes a literal; `null`, numbers, strings, bools |
| | `BUILD_LIST` | n | Pops n values, pushes list |
| | `BUILD_DICT` | n | Pops n pairs, pushes dict |
| Names | `LOAD_NAME` | name | `Environment.get` semantics |
| | `DEFINE_NAME` | name | `Environment.define` — `let`, `fn` decls, params, catch bindings |
| | `STORE_NAME` | name | `Environment.assign` — assignment statements |
| | `STORE_INDEX` | — | Pops index, object, value — the reverse of the compiler's push order (value, object, index); list bounds check / dict set (tree-walker `_assign` Index branch) |
| Operators | `BINARY` | op | Tree-walker `_binary` (covers `+` concat, comparisons, `values_equal`) |
| | `UNARY` | op | Tree-walker unary handling (`-`, `!`) |
| Jumps | `JUMP` | target | Unconditional |
| | `JUMP_IF_FALSE` | target | Pops condition |
| | `JUMP_IF_TRUE` | target | Pops condition |
| Calls | `CALL` | nargs | Pops nargs args + callee; builtin direct, function → new frame |
| | `METHOD_CALL` | (name, nargs) | Pops receiver + args; delegates to `_method_call` |
| | `INDEX` | — | Delegates to `_index` |
| Functions | `MAKE_FUNCTION` | CodeObject | Creates `BunFunction` with closure env = current frame env |
| | `RETURN` | — | Returns top of stack to caller frame; on the top-level frame raises "'return' outside of a function" |
| Modules | `IMPORT` | (path, names) | Resolve, load (same run-once cache), compile, run, bind exports; `names` is the imported-name list from the AST |
| | `RECORD_EXPORT` | name | Records the just-defined binding into the module export stack (tree-walker `_record_export`) |
| Stack mgmt | `POP`, `DUP`, `HALT` | — | `HALT` ends a frame with result null |
| Scopes | `ENTER_SCOPE`, `EXIT_SCOPE` | — | Push/pop a child `Environment` for blocks (tree-walker `_execute_block`) |
| Iteration | `FOR_SETUP`, `FOR_NEXT` | — | `FOR_SETUP` pops the iterable (must be list/string), stores a Python iterator on the frame; `FOR_NEXT exit` pushes the next item or jumps to `exit` when exhausted |
| Exceptions | `TRY` | catch_ip | Pushes (catch_ip, env, stack_depth, iterator_depth) on the frame's handler stack; the unwind truncates the stack AND the iterator stack to the recorded depths |
| | `END_TRY` | — | Pops the handler; executed after try block completes |
| | `THROW` | — | Pops value, raises `BunRuntimeError(stringify(value))` |

### Compilation notes

- Scoping: every block (function body, if/while/for body, try and catch
  blocks) compiles inside `ENTER_SCOPE`/`EXIT_SCOPE`, matching the
  tree-walker's `_execute_block` child environments.
- `if`: condition + `JUMP_IF_FALSE` → then-block → `JUMP` end; patch both.
- `while`: loop-head, condition + `JUMP_IF_FALSE` → exit; `ENTER_SCOPE` body
  `EXIT_SCOPE`; `JUMP` head.
- `for ... in`: iterable + `FOR_SETUP`; loop-head `FOR_NEXT exit`;
  `ENTER_SCOPE`, `DEFINE_NAME var`, body, `EXIT_SCOPE`; `JUMP` head. The
  iterator is a Python iterator over the list/string, so iteration semantics
  (including mutation during iteration) match the tree-walker exactly.
- `and`/`or`: compile left, `DUP` + `JUMP_IF_FALSE`/`JUMP_IF_TRUE` keep the
  left value; otherwise `POP` and right is evaluated. Result matches the
  tree-walker's operand values (not coerced booleans).
- `try`: `TRY catch_ip` → `ENTER_SCOPE` try block `EXIT_SCOPE` → `END_TRY` +
  `JUMP` over catch → catch target: the pushed message value is `DEFINE_NAME`d
  into the catch block's scope (one binding per name in `catch_params`), then
  the catch block.
- Index assignment (`a[i] = v`): compile value, target, index, `STORE_INDEX` (value first, matching the tree-walker's evaluation order).
- `export`: `let`/`fn` declarations with `export` emit `RECORD_EXPORT` right
  after `DEFINE_NAME`, recording the value at definition time exactly like the
  tree-walker.
- Function declarations: compile body as a child CodeObject first (hoisting
  semantics: declarations bind before surrounding statements run, matching the
  tree-walker's statement order), then `MAKE_FUNCTION` + `DEFINE_NAME`.
- `return` without a value compiles `LOAD_CONST None` first (null is `None`).

## 3. Execution Semantics

### Calls and closures

`CALL` pops nargs arguments and the callee. `Builtin` values are called
directly. A `BunFunction` gets a new frame: a child
`Environment(parent=fn.env)` where parameters are `DEFINE_NAME`d, then the
function's code runs until `RETURN` (result = stack top) or implicit `HALT`
(result = null). `ReturnSignal` becomes unnecessary — control flow is
bytecode. `MAKE_FUNCTION` captures the current frame's environment, so
closures and block scoping behave exactly like the tree-walker's
`_execute_block` child scopes.

### Modules

`IMPORT path` resolves and loads source through the existing
`bun/modules.py` helpers and the interpreter's run-once cache (shared: a module
imported under either engine executes once per process). The module's
top-level AST compiles to a CodeObject with `"name": "<module>"`, runs in a
fresh environment, and after `HALT` the requested export names are read from
that environment and `DEFINE_NAME`d into the importer's scope. Circular
imports follow whatever the tree-walker's cache already yields.

### Error parity

- Every error the VM raises is a `BunRuntimeError(message, line, col)` with
  line/col from the currently executing instruction, raised through the
  existing `BunError` formatting path in `bun/errors.py`.
- Errors during a module's top-level execution get the same module-frame
  attachment as the tree-walker (`_attach_module_frame`), so messages show
  `module.bun:line:col` identically.
- `LexError`, `ParseError`, and `BunTypeError` are raised before the VM starts
  and are never catchable — the non-catchable static-error invariant is
  preserved structurally, exactly as in Phase 3.
- `try`/`catch` translates to the handler stack: any `BunRuntimeError` from a
  VM operation unwinds frames to the nearest handler, restores that frame's ip
  to the catch target, and pushes the message string for the catch binding.
  Non-runtime errors cannot exist mid-execution, so the catchable set is
  identical to the tree-walker's by construction.

## 4. Testing and Acceptance

- **Differential goldens**: `tests/test_golden.py` parametrizes every golden
  case over both engines; each run must match the stored `.out` byte-exactly.
  The existing goldens (216-test suite) become the differential gate.
- **VM unit tests**: a new `tests/test_vm.py` mirrors the interpreter suites'
  scenarios through the VM — closures, recursion, `try`/`catch`/`throw`,
  module imports and error frames, list/string methods, operators — each also
  asserted to match the tree-walker where feasible.
- **Cutover gate**: the full suite passes with `engine="vm"` and zero
  skips; only then does the CLI default flip to `vm` (the flag remains for
  rollback). The tree-walker stays in the tree as the differential oracle.

## 5. Out of Scope

- Serialized bytecode files (`.bunb`) — code objects are in-memory only; the
  Phase 4 compiler emits them as plain data.
- Slot-based frames, upvalue capture, register allocation — name-based
  environments are sufficient for Phase 4 and keep emission from a Bun-written
  compiler trivial.
- JIT, native compilation.
- Removing the tree-walker (differential oracle; deletion would need explicit
  approval anyway).
- A Bun-level emit library — Phase 4's compiler is written in Bun and
  constructs the documented CodeObject dicts itself.
