# The C Backend of Bun against Rust, CPython and C++ — Research Notes

Date: 2026-10-26
Status: Research input to the phases after Phase 20.

This document compares the native tier of Bun with three backends that
are known to work: the Rust compiler (LLVM), the CPython bytecode
machine and the C++ compiler (gcc/clang). The evidence comes from the
same program written four times and inspected with REA.

It is not a design document. It is the *evidence* behind the order of the
work that follows.

---

## 1. The method

One program, four languages. It holds the three features that the type
spine of Bun added — a struct with a method, a generic function, and a
result with the `?` operator:

```bun
struct Point { var x: int, var y: int }
impl Point { fn sum(self) -> int { return self.x + self.y } }
fn first<T>(xs: list<T>) -> T { return xs[0] }
fn parse(text: string) -> result {
    if text == "" { return Err("empty") }
    return Ok(len(text))
}
fn twice(text: string) -> result {
    let n = parse(text)?
    return Ok(n * 2)
}
```

The Rust, C++ and Python versions are the same program with the same
shape: a `struct` with an `impl`, a generic function, and a result type
with an error path. All four print the same four lines:

```
7
1
6
empty
```

The images were built and then inspected with REA:

| what | REA command | provider |
|------|-------------|----------|
| the layout of an image | `rea inspect-binary-layout` | needs pwntools — not installed |
| the layout of an image | `rea inspect-with-objdump <file> section_headers` | GNU objdump |
| the symbols of an image | `rea inspect-with-objdump <file> symbols` | GNU objdump |
| the header of an image | `rea inspect-with-objdump <file> file_headers` | GNU objdump |
| the Rust build | `rea inspect-rust-binary` | REA rust-auditable reader |
| the Python build | `rea inspect-python-pyc` | REA CPython pyc parser |

The deep analysis commands of REA (`inspect`, `decompile`, `analyze`)
need Ghidra or Hopper, and the analysis that drives them needs a model
provider. Neither is installed here, so the evidence of this document is
the *static* evidence: the layout, the symbols, the dependency inventory
and the code objects.

---

## 2. What the images look like

| | Bun (C backend) | Rust (rustc, LLVM) | C++ (g++) |
|---|---|---|---|
| size of the binary | 78 960 B | 445 912 B | 17 992 B |
| size of `.text` | 40 997 B | 242 275 B | 1 633 B |
| size of `.rodata` | 6 576 B | 21 516 B | 312 B |
| size of `.eh_frame` | 5 040 B | 20 968 B | 476 B |
| `.gcc_except_table` | absent | 13 328 B | 54 B |
| functions in the table | 79 | 564 | 17 |
| symbols in the table | 121 | 1 042 | 42 |
| external symbols | 34 | 68 | 21 |

The C++ image is the smallest because the standard library of C++ is
linked as a shared object and the program itself is tiny. The Rust image
is the biggest because it carries the whole standard library, the panic
machinery and one copy of every generic instantiation.

**The Bun image is in the middle, and that is the finding.** The Bun
binary is 595 lines of generated C plus the runtime of the language
(4 456 lines of `c_runtime.h`), and it compiles with `-O3`:

```c
CFLAGS = ("-std=c11", "-O3", "-falign-loops=32",
          "-fno-guess-branch-probability", "-w")
```

The Bun binary holds 79 functions where the Rust binary holds 564 for
the same program. The reason is that the Rust compiler *specialises*:
every generic instantiation is its own function, and every function of
the standard library that the program touches is pulled in. The Bun
backend erases the types instead, so one function serves every type.

---

## 3. What the evidence says about the memory

### 3.1 The Python side

The REA pyc parser reads the marshal code objects of the compiled
module:

| fact | value |
|------|-------|
| Python version | 3.11 (`py311` layout) |
| code objects | 9 |
| marshal objects | 189 |
| marshal bytes | 2 654 |
| largest stack | 7 slots |

Nine code objects for nine functions and classes. Every value of an
expression lives in the slots of the frame, and the machine is a stack of
those frames. There is no compiler in this path: the program is carried
as data.

### 3.2 The native side

The C runtime of Bun has one allocator and no collector:

```c
static void bun_throw(const char *format, ...) {
    ...
    if (!bun_handler) {
        bun_report_error(bun_error_message);
        bun_arena_release();
        exit(1);
    }
    longjmp(bun_handler->buf, 1);
}
```

Two things follow from these fifteen lines.

1. **The memory of a program is an arena.** The arena is released when
   the program ends. Nothing is freed while the program runs, and there
   is no collector. A program that runs for a long time and builds a lot
   of values grows without bound. CPython has a collector, Rust owns
   every value and drops it at the end of its life, and C++ frees with
   the destructors of the values. **Bun has none of the three.**
2. **The errors are a `longjmp`.** The handler stack is global, so the
   runtime walks it to find the frame that catches the error. There is no
   unwinding table of the language's own, and there is no `.gcc_except_table`
   in the image — the C compiler cannot unwind through a Bun frame,
   because a Bun frame is not a C frame.

---

## 4. The gaps, one by one

### 4.1 The builtins the backend refuses by name

The backend carries 32 builtins. The language has 122. A program that
calls one of the other 90 is refused at compile time, by name, so the
error names the builtin:

```python
SUPPORTED_BUILTINS = frozenset([
    "print", "len", "range", "str", "int", "chr", "ord", "float",
    "type_of", "abs", "min", "max", "bool", "sum", "any", "all",
    ...
    "Ok", "Err", "is_ok", "is_err",
])
```

The refusal is the right design — a mistranslated builtin would fail at
run time with a confusing message — but it means the native tier of the
language is a *subset* of the language today. `json_parse`, `http_get`,
`spawn`, `mutex`, `ffi_load` and the rest of the list of 122 are not
there. **This is the largest gap between the engines, and it is the one
that hurts the user first.**

### 4.2 The statements the backend refuses

```python
REFUSED = {
    regcode.SCOPE_ENTER: "the scope statement",
    regcode.SCOPE_EXIT: "the scope statement",
    regcode.YIELD: "the yield statement",
}
```

The `scope` statement and the generators (`yield`) are refused. The
`try`/`catch`/`finally` and the `with` statement are there, because the
runtime has a handler stack for them.

### 4.3 The types are erased

The generics of Bun are a checker-level feature: the body of a generic
function is checked once, and the register code and the C code carry no
type information. One function serves every type.

Rust does the opposite: `first::<i32>` and `first::<String>` are two
functions, each one specialised, each one inlined by LLVM into the
caller when the call site is known. C++ does the same with its
templates.

The cost of erasure in Bun is measurable in the image: the Rust binary
holds 564 functions where the Bun binary holds 79. The benefit is that
the Bun backend stays small and that the type arguments never reach the
machine — the same decision the spec of Phase 19 records.

**The gap that this leaves is not the speed of a call. It is the speed
of a *value*.** Every value of Bun is a tagged union at run time, so
every arithmetic operation of the native tier is a switch on the tag.
Rust knows the type of every value at compile time and emits a plain
`add` instruction; C++ does the same for a value that is not a
polymorphic object. The `-O3` of the system compiler cannot remove the
switch, because the tag is a run-time value.

### 4.4 There is no unwinding through a Bun frame

The `.gcc_except_table` is absent from the Bun image, and it is 13 328
bytes in the Rust image. Rust uses it for the `?` operator and for
`panic`; C++ uses it for `throw` and `catch`.

Bun's `?` does not need it: the `UNWRAP_OR_RETURN` instruction returns
the result from the function directly, and the handler stack of the
runtime carries the `try`. But the gap is real for anything that wants
to leave a frame from the outside: a foreign function that throws a C
exception cannot be caught by a Bun `try`, and a Bun error cannot
travel through a C frame. The FFI of the language (`ffi_load`) therefore
has to agree on a calling convention of its own.

### 4.5 There is no collector, and there is no owner

The arena of the runtime never gives memory back while the program runs.
CPython has a reference count and a cycle collector, Rust has the
borrow checker and the drop of every value, C++ has RAII. Bun has
neither: a value lives until the program ends.

The values that the language copies — a struct is a value, so an
assignment copies it — are copied by the runtime with `bun_copy_value`,
which walks the value. There is no sharing, so there is no cycle, so
there is nothing for a collector to find. The price is memory, not
time.

### 4.6 The parallel and the dynamic parts are missing

Rust has a thread per task, an async runtime and a `Send`/`Sync` proof
that keeps the data of one task away from the data of another. CPython
has the GIL, the `threading` module and the `asyncio` loop. C++ has
`std::thread` and `std::async`. Bun has `spawn`, which runs a function
in a thread of the host, and the `task_*` builtins — but only in the
Python engines; the C backend refuses `spawn` by name, so **the native
tier of Bun is single-threaded**.

### 4.7 The backend depends on the system compiler

The last mile of the Bun backend is `cc`:

```python
command = [compiler] + list(CFLAGS) + ["-I",
           os.path.dirname(RUNTIME_HEADER), "-o", binary, c_path, "-lm"]
```

Rust ships its own backend (LLVM) and its own linker, so a Rust program
does not need a system compiler. C++ needs one, like Bun. The practical
difference: the build of Bun is as portable as the build of C++, and the
build of Rust is not.

---

## 5. The order the gaps suggest

The gaps are not of the same kind, so they do not have the same price.

| gap | what it costs the user | what it costs the work | order |
|-----|----------------------|----------------------|-------|
| the 90 refused builtins | a program that runs on the tree does not run on the native tier | a builtin is one function in the runtime | first |
| the generators and the `scope` | the same | a generator is a frame of its own | second |
| the collector | a long program grows without bound | a collector is a root set and a mark | third |
| the unwinding through a frame | the FFI has to agree on its own convention | a table of the frames of the language | fourth |
| the erasure of the types | every arithmetic operation checks the tag at run time | a monomorphisation pass in the compiler | last, and it is a *design* decision, not a bug |
| the threads | the native tier is single-threaded | the runtime of the tasks in C | with the builtin `spawn` |

The first three are work. The fifth is a decision that the spec of
Phase 19 already took, and the evidence of this document says the
decision was the right one for the size of the backend: 79 functions
instead of 564, and a backend that stays small enough to be correct.

---

## 6. The numbers to keep

| | Bun | Rust | CPython | C++ |
|---|-----|------|---------|-----|
| the image of the same program | 78 960 B | 445 912 B | 2 654 B of marshal | 17 992 B |
| functions | 79 | 564 | 9 code objects | 17 |
| the types at run time | erased | specialised | erased | specialised |
| the memory | one arena | owned values | counted and collected | owned values |
| the errors | `longjmp` | unwinding table | exceptions | exceptions |
| the threads | none on the native tier | one per task | the GIL | `std::thread` |
| the last mile | the system `cc` | LLVM and a linker | the interpreter of the host | the system `cc` |
