# The C Backend of Bun — Research Notes

Date: 2026-10-20
Status: Research input to the Phase 13 design of the C backend.

This document records the survey work behind the C backend of Bun. It is
not a design document — it is the *evidence* behind the decisions in the
plan `2026-10-20-bun-phase-13.md`.

---

## 1. What the backend has to prove

Bun's headline is *"Python-like ease and C++-like speed"*. Everything
built so far — the tree walker, the stack VM, the register VM — runs on
the Python host, so the speed half of the headline is a claim about the
*shape* of the language, not about the wall clock of the runtime. The
register tier made the shape right: the values of an expression live in
registers, the code is verified, and the semantics are the reference
semantics of the stack VM.

What is missing is the last step: **a program that runs at the speed of
the machine it is on**. That is what an ahead-of-time backend is, and the
design document already named two of them — the C backend and the WASM
backend (§7.3).

The C backend is the one that matters here, for three reasons:

1. **The system compiler does the hard work.** Register allocation,
   instruction selection, vectorisation and inlining are the C
   compiler's job. A backend that emits C inherits all of it for free.
2. **It is the smallest backend that can be complete.** The WASM backend
   needs a WASM toolchain to be useful, and a toolchain that the
   developer may not have.
3. **It is checkable.** The golden corpus of the test suite is the
   oracle: a program that prints something different under the backend
   is a bug in the backend, never a difference in the language.

---

## 2. The precedent survey

### 2.1 CPython — the C extension

CPython compiles nothing. Every function of the standard library is
written in C and exposed to the interpreter. The result is a language
whose hot paths are machine code and whose cold paths are a tree
walker — the same split Bun's `--engine` flag already has.

The lesson for Bun is not to copy the split but to learn the *boundary*:
the C code is reached through a small, fixed interface — a value in, a
value out — and everything above it stays in the language.

### 2.2 Nim, Crystal, V — the "compile to C" school

Nim, Crystal and V compile to C and let the system compiler finish the
job. All three keep the *semantics* of the source language and delegate
the *optimisation* to the C compiler. All three have a reference
implementation — the interpreter or the compiler's own tree — that the
generated code is tested against.

The lesson: a backend needs an oracle, and the oracle is the interpreter.
Bun already has three: the tree walker, the stack VM and the register VM.
The C backend is the fourth implementation of the same semantics, and the
golden corpus compares all four.

### 2.3 WebAssembly — the portable backend

The WASM backend gives a portable, sandboxed artifact with no system
toolchain. It is the right answer for a *deployment* target and the wrong
answer for a *speed* target: the WASM engines of today are slower than
native code for exactly the workloads a numeric program wants.

The decision: the WASM backend stays deferred, and the C backend comes
first. The register code is the same either way, so the WASM backend
becomes a second emitter over the same input when it is written.

### 2.4 LuaJIT — the tracing JIT

LuaJIT compiles a hot loop into machine code with a tracing JIT. It is
the fastest option and the most fragile: the tracer has to understand the
whole language, and a construct it does not understand makes the program
fall back to the interpreter.

The decision: no tracer. The register code is already a flat, verified
form; emitting it is a mechanical translation, and the translation can be
checked by the golden corpus. A tracer would be a project of its own,
with its own risk, and the C backend gives most of the benefit for a
fraction of the work.

---

## 3. The shape of the translation

### 3.1 The input is the register code

The emitter reads the register code, not the AST. The reasons:

- **The register code is flat.** Every instruction is four cells, and the
  verifier has already proved that the jumps land, that the registers are
  inside the file, and that the depth of the expression is the same on
  every path. The emitter does not have to reconstruct any of that.
- **The semantics are already defined.** The register VM is the
  definition, and it is tested against the stack VM over the whole
  golden corpus. The C backend that mirrors the register VM mirrors the
  language.
- **The functions are already separated.** `MAKE_FUNCTION` carries a code
  object, so the emitter writes one C function per Bun function and one
  closure structure to tie them together.

The alternative — emitting from the AST — would mean re-deciding the
order of the evaluation, the scope of a name, the layout of an
expression, and every other decision the registerizer has already made.
That is work without information.

### 3.2 The instruction set of the backend

The register code has about fifty opcodes. The backend supports the
subset that covers the core of the language:

| Group | Opcodes |
|-------|---------|
| The values | `CONST`, `LOAD_NAME`, `STORE_NAME`, `DEFINE_NAME` |
| The shape | `POP`, `DUP` |
| The arithmetic | `ADD`, `SUB`, `MUL`, `DIV`, `MOD`, `NEG`, `INVERT`, `NOT` |
| The comparison | `EQ`, `NE`, `LT`, `LE`, `GT`, `GE` |
| The bits | `BAND`, `BOR`, `BXOR`, `SHL`, `SHR` |
| The containers | `BUILD_LIST`, `BUILD_DICT`, `BUILD_STRING`, `LIST_APPEND`, `DICT_SET`, `INDEX`, `STORE_INDEX`, `SLICE`, `STORE_SLICE` |
| The calls | `MAKE_FUNCTION`, `CALL`, `METHOD_CALL`, `RETURN`, `HALT` |
| The control | `JUMP`, `JUMP_IF_FALSE`, `JUMP_IF_TRUE` |
| The scopes | `ENTER_SCOPE`, `EXIT_SCOPE`, `FOR_SETUP`, `FOR_NEXT`, `FOR_POP` |
| The errors | `TRY`, `TRY_FINALLY`, `END_TRY`, `FINALLY_END`, `THROW`, `ASSERT` |

The opcodes that are **not** in the list — the modules, the `with`
statement, the `scope` statement, the `match` statement — are refused
with a clear message rather than mistranslated. A backend that guesses is
worse than a backend that says no.

### 3.3 The value model

The C runtime needs the value model of the language:

- `null`, `true`/`false`, an integer (64 bit), a float (double), a
  string, a list, a dictionary, a function and a builtin.
- A tagged union, with the heap objects behind a reference count.

The integer is 64 bit because the language has no small integers: the
arithmetic of the runtime is Python's, and Python's integers are exact.
The float is a double, and the *printing* of a float has to be the
*shortest* repr that round-trips, exactly like Python's, because the
golden corpus compares the output byte for byte.

### 3.4 The errors

`throw` and `try`/`catch` become `setjmp`/`longjmp`. The message of the
error is a string, exactly like the runtime's: `catch (err)` binds the
message, not an object.

The stack VM reports the line of the error and prints a little picture of
the source. The C backend has no source at run time — the program is a
binary — so it reports the message and the function, and the *line* when
the emitter can keep it. A backend that prints a different picture is a
difference in the *reporting*, not in the language, and the golden
corpus compares the output of a successful run, not the picture of a
failure.

### 3.5 The builtins

The backend has its own implementation of the builtins of the core
language: `print`, `len`, `str`, `int`, `float`, `bool`, `type_of`,
`abs`, `min`, `max`, `range`. A program that uses another builtin is
refused at compile time with the name of the builtin, so the developer
knows what is missing instead of finding a strange error at run time.

The scan for the used builtins is done on the AST: every identifier whose
name is a builtin of the language is collected, and the ones the backend
does not have are refused. The scan is conservative — a local variable
that hides a builtin is still counted — and a false positive only costs
the program a builtin it did not really use.

---

## 4. The rules of the phase

1. **The backend never changes the language.** A program that runs under
   the backend prints the same bytes as under the stack VM. The golden
   corpus is the check, and it runs under every engine.
2. **The backend says no rather than guessing.** A construct it cannot
   translate is refused with a message that names it.
3. **The reference stays the reference.** The stack VM is still the
   default engine; the backend is opt-in with `--engine c`.
4. **The numbers are published.** The speed of the backend against the
   stack VM is a number in the documentation, measured on the machine
   that runs the benchmark, not an adjective.

---

## 5. The acceptance criteria

1. **The same bytes.** A program of the golden corpus that the backend
   supports prints exactly what the stack VM prints.
2. **The same errors.** A program that fails fails with the same
   message.
3. **A clear refusal.** A program that uses a builtin the backend does
   not have is refused at compile time, with the name of the builtin.
4. **A number.** A numeric loop runs faster under the backend than
   under the stack VM, and the factor is measured by a tool and printed.
