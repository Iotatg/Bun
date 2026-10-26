# Bun

Bun is an original, dynamically-typed programming language with Rust/Go/Python-inspired
syntax. This repository contains the v0.1 implementation, written in Python: a bytecode
compiler and stack VM execute programs by default, with the tree-walking interpreter
retained as the differential oracle.

## Requirements

- Python 3.8 or newer

## Run a program

```bash
python3 -m bun examples/hello.bun
```

A program may also come from the standard input:

```bash
echo 'print("hello")' | python3 -m bun -
```

## Start the REPL

```bash
python3 -m bun
```

Or use the launcher:

```bash
./bin/bun examples/hello.bun
```

## Performance

The startup of the language is published and measured by
`python3 tools/bench.py`:

| Metric | Budget | Measured |
|--------|--------|----------|
| `bun` hello program, tree engine | 120 ms | ~55 ms |
| `bun` hello program, VM engine | 140 ms | ~55 ms |
| import of the language | 120 ms | ~35 ms |

The numbers are the fastest of seven runs on a warm cache.
`tests/test_startup.py` keeps the budget honest.

Inside a program the VM is the fast path. The method dispatch is cached per
receiver type, and the dispatch loop keeps the instruction pointer, the code
array and the operand stack in local variables instead of looking them up on
the frame for every instruction.

`bun compile --profile <file.bun>` runs a program with the instruction
profiler and reports the hot instructions. The counts are the measurement
the register VM design needs.

```
$ bun compile --profile hot.bun
instruction profile: 26013 instructions
 15.39%       4003  LOAD_NAME
 15.38%       4000  ENTER_SCOPE
 ...
```

## Language tour

```bun
// line comment
# also a comment

let x = 10          // immutable
var count = 0       // mutable
let name = "Bun"

fn add(a, b) {
    return a + b
}

if x > 5 { print("big") } else { print("small") }

while count < 3 { count = count + 1 }

for i in range(0, 5) { print(i) }

let nums = [1, 2, 3]
nums[0] = 99
print(len(nums))
```

Built-in functions: `print`, `len`, `range`, `str`, `int`, `float`.

## Methods, dicts, and files (Phase 1.5)

Bun uses method-call syntax, so text processing reads left to right:

```bun
let names = " bob , alice , carol ".split(",")
let trimmed = []
for n in names {
    trimmed.push(n.trim())
}
print(trimmed.join(", "))
```

Dictionaries are literals with `[]` access:

```bun
let counts = {}
counts["apple"] = 2
counts["banana"] = 1
print(counts.len())
print(counts.keys())
```

String methods: `trim`, `lower`, `upper`, `split`, `contains`, `starts_with`,
`ends_with`, `replace`, `repeat`, `slice`, `index_of`, `len`.
List methods: `push`, `pop`, `shift`, `len`, `join`, `contains`, `reverse`,
`slice`, `sort`, `splice`, `insert`.
Dict methods: `len`, `has`, `get`, `keys`, `values`, `remove`.

File I/O built-ins: `read_file(path)`, `write_file(path, text)`,
`append_file(path, text)`, `file_exists(path)`.

## Modules (Phase 1.6)

Any Bun file can be imported as a module. Mark declarations with `export` and
import them by relative path:

```bun
// greeting.bun
export fn hello(name) {
    return "Hello, " + name
}

export let punctuation = "!"
```

```bun
import { hello, punctuation } from "./greeting"

print(hello("Bun") + punctuation)
```

Rules:
- `export` marks module-level `fn`, `let`, or `var` declarations; it is only
  allowed while a module is loading, not in the file you run.
- Module paths are relative to the importing file (`./` or `../`); the `.bun`
  suffix is optional.
- Each module runs once per program; importers share its state.
- Imported bindings cannot be reassigned.
- Circular imports are an error.

Anonymous functions are expressions, so they can be stored in dicts or passed
around:

```bun
var ctx = {}
ctx["get"] = fn(x) {
    return x * 2
}
print(ctx["get"](21))
```

See `tools/unicode/` for a real conversion: the table generator from the Bun
runtime's own tooling, ported from TypeScript.

## Static types (Phase 2)

Type annotations are optional. Anything unannotated is dynamic (`any`), so old
programs run unchanged:

```bun
let x: int = 5
var count: float = 0

fn add(a: int, b: int) -> int {
    return a + b
}

let ok: bool = add(1, 2) == 3
```

The checker runs before your program and blocks type errors. Rules:

- Types: `int`, `float`, `string`, `bool`, `null`, `any`, `list`, `dict`, `fn`.
- `any` is assignable both directions; `int` widens to `float`; `null` fits
  any type.
- Checked: annotated declarations and assignments, function returns, and
  direct calls (argument types and arity).
- Unchecked: operators, method calls, indexing, and unannotated code.

Skip the checker with `--no-check`:

```bash
python3 -m bun --no-check program.bun
```

Choose the execution engine with `--engine tree|vm|register|c` (default: `vm`):

```bash
python3 -m bun --engine vm program.bun
python3 -m bun --engine tree program.bun
python3 -m bun --engine register program.bun
python3 -m bun --engine c program.bun
```

The `c` engine is the native backend of Phase 13: it turns the program into
C and lets the compiler of the system do the work. It refuses the constructs
it cannot translate, by name, at compile time.

The register engine runs the same program with the values of an expression
in the registers of a frame instead of on an operand stack. It has the same
environments, the same builtins, the same errors and the same messages as
the stack VM — it is the same language, run by a different machine. The
flag `--tier` adds the superinstructions on top of it, the pairs of loads
that the code holds fused into one instruction:

```bash
python3 -m bun --engine register --tier program.bun
```

The default stays the stack VM: it is the reference semantics of the
language, and the lowering of the register tier costs more time than the
tier saves on a small program.

The front end can also be self-hosted: `--front-end bun` tokenizes, parses, type-checks, and compiles the program with Bun code in `selfhost/`, then runs the resulting code object on the VM. The Python front end stays the default:

```bash
python3 -m bun --front-end bun program.bun
```

`--front-end bun` requires `--engine vm`. Type errors come from `selfhost/checker.bun` and match the Python checker message-for-message. Imported modules are still compiled by the Python compiler; self-hosting covers the entry program and module type checking.

## Pythonic surface (Phase 6)

Phase 6 closes the gap between Bun and the surface language of Python.

### f-strings

```bun
let name = "Bun"
let version = 1.0
print(f"hello {name} in {version:.1f}")
```

### Slices

```bun
let xs = [1, 2, 3, 4, 5]
print(xs[1:3])     // [2, 3]
print(xs[::2])     // [1, 3, 5]
print(xs[::-1])    // [5, 4, 3, 2, 1]
```

### Comprehensions

```bun
let squares = [x * x for x in range(0, 5) if x % 2 == 0]
let lengths = { word: len(word) for word in ["a", "bb"] }
```

### Function parameters

```bun
fn greet(name, greeting = "hello") {
    return greeting + ", " + name
}

fn total(base, *extra, factor = 1) {
    var result = base
    for value in extra {
        result = result + value
    }
    return result * factor
}

greet("bun")
greet("bun", greeting = "hi")
total(1, 2, 3)
```

- Defaults, `*args`, keyword-only parameters and `**kwargs` are supported.
- A call may pass arguments by name: `greet(greeting = "hi")`.

### Unpacking

```bun
let first, *rest = [1, 2, 3]
let [x, y] = [7, 8]
let [[a, b], [c, d]] = [[1, 2], [3, 4]]
```

### `finally` and exception chaining

```bun
try {
    throw "boom"
} catch err {
    print(err)
} finally {
    print("always")
}

try {
    risky()
} catch err {
    throw "wrapped" from err
}
```

### `with`

```bun
fn reader(text) {
    return {
        "__enter__": fn() { return text },
        "__exit__": fn(err) { return null }
    }
}

with reader("hello") as handle {
    print(handle)
}
```

A context manager is a dict with an `__enter__` and an `__exit__` function.

### The `Secret` type

```bun
let token = secret("s3cr3t")
print(type_of(token))   // secret
```

A secret never shows up in `dump` and never in an error message.

### Undefined names are a static error

The checker reports a name that is not bound anywhere, before the program
starts:

```bun
print(not_defined)
// error: undefined variable 'not_defined'
```

The name of a function is known even when the function is defined further
down, so a program may call a helper that is written at the end of the file.

### The documentation registry

```bash
bun <file.bun>                  run a Bun program
bun -                           run a Bun program from the standard input
bun --no-check <file.bun>       run without type checking
bun --engine tree|vm|register|c <file.bun> choose the execution engine (default: vm)
bun --engine register --tier <file.bun> run with the superinstructions
bun --front-end python|bun <file.bun> choose the front end (default: python)
bun api [--json]                list the builtin signatures
bun doc [<symbol>] [--json]     show the documentation
bun test --doc [<symbol>]       run the documentation examples
bun check [--json] <file.bun>   type check a file without running it
bun compile [--profile] <file>  show the bytecode, or profile the run
bun                             start the interactive REPL
bun -h | --help                 show this help
```

The examples of the registry never touch the network or the filesystem, so
`bun test --doc` is hermetic.

`bun check --json` reports the diagnostics as data:

```json
{"ok": false,
 "diagnostics": [{"file": "a.bun", "severity": "error", "kind": "type",
                  "message": "cannot assign value of type 'string' to
                              variable 'n' of type 'int'",
                  "line": 1, "col": 1}]}
```

The `kind` is `type`, `syntax` or `lex`, so a tool can tell a type error
from a syntax error without reading the message.

### New builtins

| Builtin | Purpose |
|---------|---------|
| `bool(value)` | the truth of a value |
| `abs(value)` | the size of a number, without its sign |
| `sum(values)` | the total of a list of numbers |
| `any(values)` / `all(values)` | the truth of the values of a list |
| `min(values)` / `max(values)` | the smallest or the largest value of a list |
| `zip(left, right)` | the pairs of two lists |
| `enumerate(values)` | the pairs of a list and the numbers of its values |
| `sorted(values)` | a new list, in order |
| `reversed(values)` | a new list, backwards |
| `input(prompt)` | read one line from the standard input |
| `random()` | a random number between zero and one |
| `random_int(low, high)` | a random integer between two bounds |
| `eval(source)` | run a piece of Bun source, return the value of its last expression |
| `exec(command, timeout)` | run a command, with an optional timeout |
| `http_get_bytes(url, headers, timeout)` | download the bytes of a resource |
| `write_bytes(path, data)` / `read_bytes(path)` | binary files |
| `sha256(data)` / `sha1(data)` | digests as lists of bytes |
| `md5(data)` | the digest of MD5, as marks of numbers |
| `aes_ige_encrypt(data, key, iv)` / `aes_ige_decrypt(...)` | AES in IGE mode |
| `aes_ctr_crypt(data, key, iv)` | AES in counter mode |
| `bytes_slice(data, start, end)` / `bytes_append(data, payload)` | the bytes of a list, moved fast |
| `rsa_encrypt(data, modulus, exponent)` | RSA without padding |
| `utf8_bytes(text)` / `utf8_string(data)` | UTF-8 encoding |
| `bigint_*` | arbitrary precision integers over byte lists |
| `h2_connect` / `h2_request` / `h2_close` | HTTP/2 with HPACK |
| `tcp_connect` / `tcp_tls_connect` / `tcp_write` / `tcp_read` | raw sockets |
| `task_*`, `mutex`, `lock`, `unlock` | threads and locks |
| `ffi_load(module)` | a call into a native library (allow-list) |

The cipher of the runtime takes its blocks from the library of OpenSSL when
the system has it, because that library works in the language of the machine.
The tables of the cipher stay the way of it when the library is not there,
and both ways give the same bytes.

### `eval`

```bun
print(eval("1 + 1"))          // 2
print(eval("let a = 5\na * 2")) // 10
```

The source is checked before it runs, so a name that does not exist is an
error and not a surprise at runtime. The source runs in a fresh scope with
the builtins available; the variables of the caller are not visible. A
syntax error of the evaluated source is a runtime error and can be caught.

```bun
try {
    eval("1 +")
} catch err {
    print(err)    // eval() failed: unexpected token EOF
}
```

## Structured concurrency (Phase 7)

A `scope` statement runs its body inside a task group. Every task that the
body spawns belongs to that group, and the scope joins all of them before it
ends — on the normal path and on the error path.

```bun
scope {
    let a = spawn { return 21 * 2 }
    let b = spawn { return 7 }
    print(task_join(a))   // 42
    print(task_join(b))   // 7
}
print("after scope")
```

`spawn` takes a block directly; `spawn(fn() { ... })` still works. A task
that fails raises its error in the parent when the scope ends:

```bun
try {
    scope {
        let bad = spawn { throw "child failed" }
    }
} catch err {
    print(err)   // child failed
}
```

The error of the body wins over the error of a child, because the body is
the code that asked for the work. An error of the body never leaves tasks
running behind it: the group is joined first, then the error is raised.

Cancellation is cooperative, because a thread cannot be killed safely:

```bun
scope {
    let t = spawn {
        while !task_cancelled() {
            sleep(0.01)
        }
        return "stopped"
    }
    sleep(0.05)
    cancel(t)
    print(task_join(t))   // stopped
}
```

- `task_cancelled()` reports whether the running task was asked to stop.
- `task_cancelled(handle)` reports it for another task.
- `cancel(handle)` asks a task to stop; the task decides when to notice.

`scope` is a soft keyword: it only starts a scope when a block follows it
on the same line, so `let scope = 3` is still a valid program.

## Error handling (Phase 3)

`try`/`catch`/`throw` handle runtime errors, JavaScript-style:

```bun
fn parse_age(text) {
    try {
        return int(text)
    } catch e {
        return -1
    }
}

print(parse_age("42"))
print(parse_age("abc"))
```

- One `catch` per `try`; the parameter is optional (`catch (e)` or `catch {}`).
- `throw` takes any value; the catch parameter receives its message string.
- Catchable: runtime errors (undefined variables, bad indexes, division by
  zero, ...).
- Not catchable: lexer, parser, and type errors — they run before your code.

Lists also sort in place:

```bun
var names = ["cherry", "apple", "banana"]
names.sort()
print(names.join(", "))
```

### Errors say what to do next

Every error that the runtime raises carries a hint: a second line under
the message that says what to do about it. The message never changes —
it is the contract of the language — and the hint is the advice.

```console
$ bun program.bun
error: index 3 out of range
  --> program.bun:2:12
   |
 2 | let item = xs[3]
   |            ^
  hint: the index is past the end of the container; the first index is 0 and the last one is len(container) - 1
```

The hints live in `bun/errors.py` (`HINTS`), and they are matched in order:
the first pattern that is in the message wins. The same hint is in the data
of a protocol error, so a tool that speaks the machine surface (§ "The
machine surface") gets the advice as well.

## Native stacks (Phase 9)

Bun ships six stacks that are written in Bun itself. They are ordinary
modules in `lib/bun/`, and the `bun:` prefix finds them:

```bun
import { tensor, matmul, softmax } from "bun:tensor"
import { capability, sandbox, redact } from "bun:sec"
import { Game, vec2, on_update, advance } from "bun:game"
import { Router, get, serve, serve_forever, html } from "bun:web"
import { model, train, word_tokenizer } from "bun:ai"
import { sqrt, exp, log, sin, cos, pi } from "bun:math"
```

| Stack | What it gives |
|-------|---------------|
| `bun:tensor` | tensors, `matmul`, `softmax`, the reductions, `adam` and a reverse-mode tape for the gradients |
| `bun:sec` | the capability manifest, the sandbox that the runtime enforces, and the redaction of secrets |
| `bun:game` | vectors and quaternions, the shapes and their tests, the entity store, the broadphase grid and the fixed timestep loop |
| `bun:web` | the router with path names, the templates that escape every value, the HTTP server and the websocket frames |
| `bun:ai` | the layers, the attention, the block of a transformer, the model, the format, the losses, the optimisers, the training loop, the tokenisers and the sampler |
| `bun:math` | the square root, the exponential, the logarithm, the circle, the angles, the powers and the rounding |

A stack is a library, not a language feature. The user can read it, change
it and write a stack of their own. The tensors are plain dictionaries, the
entities are plain dictionaries, and the routes are plain dictionaries:
Bun has no classes, so the shape of the data is the shape of the code.

The web stack needed three new builtins: `tcp_listen`, `tcp_accept` and
`tcp_close`. The runtime also gained `base64_encode` and `base64_decode`,
which the websocket handshake uses.

```bun
import { Router, get, serve, serve_forever, html } from "bun:web"

let app = Router()
get(app, "/users/:id", fn (req) {
    return html("<p>{{ name }}</p>", { "name": req["params"]["id"] })
})
let server = serve(app, 3000, "0.0.0.0")
serve_forever(server)
```

The value of a template is escaped, so a value that comes from a user can
never become markup. A fragment that is already markup is marked with
`raw(...)`.

### The HTTP/1.1 server

The server speaks HTTP/1.1 and keeps the connection open for the next
request. The connection closes when the client asks for the close, when the
answer asks for the close, or when the client speaks HTTP/1.0 without
asking to keep the connection open. Two requests that arrive in one write
are both served, and the answer of the first one does not disturb the
second.

An answer that streams sends its pieces instead of a body, and the server
writes them with the chunked encoding of HTTP/1.1:

```bun
import { Router, get, serve, serve_forever, chunked } from "bun:web"

let app = Router()
get(app, "/stream", fn (req) {
    return chunked(["first ", "second ", "third"])
})
```

```http
HTTP/1.1 200 OK
Transfer-Encoding: chunked
Connection: keep-alive

10\r\nfirst second \r\n
6\r\nthird\r\n
0\r\n
```

## The model stack (Phase 12)

`bun:ai` gives a Bun program the whole model loop without leaving the
language: build a model, train it, save it, load it, run it.

A model is data. It is a dictionary with the weights, the list of the
layers and the seed it was trained with, so a model can be printed,
compared and written to a file without anything that has to know about
it. The layers are functions, the way they are in the other stacks.

```bun
import { word_tokenizer, train_language_model, generate } from "bun:ai"

let tokenizer = word_tokenizer("the cat sat on the mat the cat sat on the mat")
let model = train_language_model(tokenizer, 8, 0.05, 30)
print(generate(model, tokenizer, 8, 42))
```

```
the mat the cat sat on the mat
```

The gradient is the reverse-mode tape of `bun:tensor`, and every layer of
the stack records its rule on that one tape, so a model made of these
layers trains with one backward pass. The random generator is explicit and
seeded: a draw is a function of the seed and the counter, never of the
clock. Two runs with the same seed give the same numbers, down to the
last digit, and that is what makes a training run a test.

A classifier is a model with a linear layer and a loss:

```bun
import { model, train, forward } from "bun:ai"
import { from_list, zeros } from "bun:tensor"

let x = from_list([0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0], [4, 2])
let w = from_list([0.3, 0.4, 0.5, 0.6], [2, 2])
let b = zeros([2])
let m = model({ "w": w, "b": b },
              [{ "op": "linear", "w": "w", "b": "b" }])
let history = train(m, x, [0, 1, 1, 0], {
    "epochs": 120, "batch_size": 4, "rate": 0.05,
    "loss": "cross_entropy", "optimizer": "adam", "seed": 7
})
print(history["loss"][0])
print(history["loss"][119])
```

The file of a model is the model itself: a JSON object whose tensors are
in their own shape, so a binary format is a walk over that shape and not
a new format.

```bun
import { save_model, load_model } from "bun:ai"

save_model(m, "model.json")
let same = load_model("model.json")
```

The stack has the attention and the block of a transformer too. The
attention is one operation with one rule on the tape, and its loops are
written by hand, because the matrix multiply of the runtime is
interpreted and a wide model would take minutes per step. The block is
the layer of a transformer: the attention, the residual around it, the
normalisation, the feed-forward network, the residual around that and
the normalisation again.

```bun
import { model, forward, train } from "bun:ai"
import { from_list, ones } from "bun:tensor"

let params = {
    "wq": from_list([0.5, -0.3, 0.2, 0.4, 0.1, 0.6, -0.2, 0.3,
                     0.7, 0.2, -0.4, 0.9, 0.3, -0.1, 0.5, 0.2], [4, 4]),
    "wk": from_list([0.1, -0.2, 0.4, 0.5, 0.3, 0.1, -0.5, 0.2,
                     0.2, 0.7, 0.1, -0.3, 0.6, 0.4, -0.1, 0.2], [4, 4]),
    "wv": from_list([0.4, 0.1, -0.2, 0.6, 0.2, 0.3, 0.5, -0.1,
                     -0.3, 0.2, 0.7, 0.4, 0.5, -0.2, 0.3, 0.1], [4, 4]),
    "ln1g": ones([4]), "ln1b": ones([4]),
    "ff1w": from_list([0.2, -0.1, 0.4, 0.3, -0.2, 0.5, 0.1, 0.2,
                      0.3, 0.1, -0.4, 0.2, 0.1, 0.3, 0.2, -0.1], [4, 4]),
    "ff1b": ones([4]),
    "ff2w": from_list([0.1, 0.3, -0.2, 0.4, 0.2, -0.1, 0.5, 0.3,
                      -0.3, 0.2, 0.1, 0.6, 0.4, 0.1, -0.2, 0.3], [4, 4]),
    "ff2b": ones([4]),
    "ln2g": ones([4]), "ln2b": ones([4])
}
let layers = [{ "op": "block", "wq": "wq", "wk": "wk", "wv": "wv",
                "ln1g": "ln1g", "ln1b": "ln1b",
                "ff1w": "ff1w", "ff1b": "ff1b",
                "ff2w": "ff2w", "ff2b": "ff2b",
                "ln2g": "ln2g", "ln2b": "ln2b",
                "heads": 2, "causal": true }]
let m = model(params, layers)
let x = from_list([0.3, -0.2, 0.7, 0.1, 0.4, 0.2, -0.1, 0.3], [2, 4])
let history = train(m, x, ones([2, 4]), { "epochs": 20, "rate": 0.05 })
print(history["loss"][0])
print(history["loss"][19])
```

The gradient of the attention is checked against the difference of the
numbers, in the tests: the rule of the layer has to be the derivative
and not an approximation of it.

## The language surface (Phase 10)

Phase 10 closes the last gaps between Bun and the surface language of
Python: the operators that work on bits, a loop over pairs, a loop over a
dict, an assertion, and a dispatch on the shape of a value.

The set and the type aliases came later: a set is the container the
language was missing, and `number` and `text` are the names the type
system was missing. The decorators came with them: they are the way a
function is wrapped in another function without a name for the wrapper.

### The bit operators

The spelling and the precedence are Python's, and the operands are
integers:

```bun
print(12 & 10)    // 8
print(12 | 10)    // 14
print(12 ^ 10)    // 6
print(~12)        // -13
print(1 << 4)     // 16
print(16 >> 2)    // 4
```

A float or a string is an error, in the same way it is an error for `+`.

### The power

The operator `**` raises a number to the power of another number, with the
precedence of Python.

```bun
print(2 ** 3)      // 8
print(2 ** 0.5)    // 1.4142135623730951
print(2 ** -1)     // 0.5
```

Two integers give an integer, and an integer that leaves the 64 bit range
is an error. A negative base with a fractional exponent is an error as
well, because Bun has no complex numbers.

The mathematics of the language is a stack of its own, `bun:math`, and it
is written in Bun, so a program that uses it needs nothing but the
language.

```bun
import { sqrt, exp, log, sin, cos, pi } from "bun:math"

print(sqrt(2.0))     // 1.4142135623730951
print(exp(1.0))      // 2.7182818284590455
print(log(2.0))      // 0.6931471805599456
print(sin(pi / 2.0)) // 1.0000000000000002
```

### The word `not`

The negation has two spellings: the mark `!` and the word `not`, which is
Python's spelling.

```bun
print(not true)      // false
print(!true)         // false
print(not 1 == 2)    // true
```

The word binds looser than a comparison and tighter than `and`, exactly as
in Python, so `not a == b` means `not (a == b)`.

### A loop over pairs, and a loop over a dict

```bun
for name, value in pairs {
    print(name + " is " + str(value))
}

for key in data {
    print(key + " = " + str(data[key]))
}
```

A dict is walked by its keys, in the order the keys were put in. A list
that is walked with more than one name must have that many items, and the
rule is the rule of the unpacking in an assignment.

### The `else` of a loop

A loop may have an `else`: the block that runs when the loop ends
without a `break`.

```bun
for track in tracks {
    if track is broken {
        break
    }
    play(track)
} else {
    print("the queue is empty")
}
```

A loop has a scope of its own, so the name of the loop is gone when the
`else` runs.

### `assert`

```bun
assert count > 0, "the count must be positive"
```

The message is optional. A failed assertion raises `assertion failed` or
`assertion failed: <message>`, and it can be caught like any other error.

### `match`

```bun
match response {
    200 => print("ok"),
    404 => print("not there"),
    _ => print("something else"),
}
```

The first case that matches wins, and the cases are tried in the order
they are written. A `match` without a matching case is an error that says
what was matched against.

| Pattern | Matches |
|---------|---------|
| `200`, `"text"`, `true`, `null` | the value equals the pattern |
| `x` | anything, and `x` is bound to the value |
| `_` | anything, and nothing is bound |
| `int`, `float`, `string`, `bool`, `list`, `dict`, `null`, `fn` | the type of the value |
| `1 to 9` | the value is in the range |
| `[a, b]` | a list of two items, and the items are bound |
| `[a, *rest]` | a list of two or more items, and the rest is bound |
| `{"id": id}` | a dict with the key, and the value is bound |
| `301, 302` | one of the patterns, the first one that matches |

A case may name more than one pattern. The alternatives are tried in the
order they are written, and the names of the one that matches are the
names of the case:

```bun
match status {
    301, 302 => print("moved"),
    404 => print("not there"),
    _ => print("something else"),
}
```

A case may also have a guard: a condition that has to hold for the case
to match. A guard that does not hold sends the case on to the next one,
and it sees the names the pattern binds:

```bun
match size {
    n if n > 100 => print("big"),
    n if n > 10 => print("medium"),
    _ => print("small"),
}
```

A list pattern may have a tail: the rest of the list, bound to a name.

```bun
match [1, 2, 3] {
    [first, *rest] => print(str(first) + " and " + str(len(rest))),
    _ => print("no match"),
}
```

The body of a case is one statement, or a block of statements:

```bun
match value {
    [x, y] => {
        print(x)
        print(y)
    },
    _ => print("not a pair"),
}
```

A dict literal as the body of a case needs parentheses, because a `{`
after `=>` always starts a block.

`match` is a soft keyword: it only starts a match statement when a
subject and a block follow it, so `let match = 3` is still a valid
program.

### The set

A set holds the values that are not equal to each other. The values of a
set are numbers, strings and null, the values a dict can use as a key.

```bun
let s = set([1, 2, 3, 2])
print(s.len())              // 3
print(s.contains(2))        // true
s.add(4)
s.remove(1)
print(s.values().join(",")) // 2,3,4
```

Two sets are joined with the operators of Python: `|` is the union, `&` is
the intersection and `-` is the difference.

```bun
let a = set([1, 2])
let b = set([2, 3])
print((a | b).len())   // 3
print((a & b).len())   // 1
print((a - b).len())   // 1
```

A set is a value like a list and a dict: it can be walked, printed and
compared, and the checker knows its type.

```bun
for value in s {
    print(value)
}
print(type_of(s))    // set
```

### The names `number` and `text`

A program may say `number` where it means `float`, and `text` where it
means `string`.

```bun
let price: number = 1.5
let name: text = "bun"
```

An alias is kept in the message of an error, so a program that says
`number` is told about a `number`.

```bash
$ bun program.bun
error: cannot assign value of type 'string' to variable 'price' of type 'number'
```

### The integers are 64 bits wide

The integers of Bun are 64 bits wide, in every engine. A program that
leaves the range is an error and not a number that wraps around.

```bun
print(9223372036854775807)   // 9223372036854775807
print(9223372036854775807 + 1)
```

```bash
$ bun program.bun
error: integer overflow
  --> program.bun:1:26
   |
 1 | print(9223372036854775807 + 1)
   |                          ^
  hint: the integers of Bun are 64 bits wide, and the operation left the range
```

A literal that does not fit is refused by the lexer, before the program
runs.

```bash
$ bun program.bun
error: integer literal out of range
```

The width is a promise of the language and not a detail of the native
backend: the machine, the tree, the register tier and the native backend
all draw the same picture for the same program.

### The decorators

A function may have decorators in front of it. A decorator is a function
that receives the function and returns the value that the name of the
function holds afterwards.

```bun
fn tagged(f) {
    return fn (a, b) {
        return f(a, b) + 1
    }
}

@tagged
fn add(a, b) {
    return a + b
}

print(add(1, 2))    // 4
```

The decorator that is written last is the one that is called first, so
the decorators run from the function outwards:

```bun
@logged
@tagged
fn add(a, b) {
    return a + b
}
```

Here `tagged` is applied to the function first, and `logged` receives the
result of `tagged`.

The name of the function is bound before the decorators run, so a
decorator may call the function it decorates:

```bun
fn again(f) {
    return fn (a) {
        return f(f(a))
    }
}

@again
fn add_one(a) {
    return a + 1
}
```

A decorator is written as a name, so the checker knows the name before
the program runs. A name that is not bound is an error that says which
decorator is missing, and a name that is not a function is an error that
says so.

```bash
$ bun program.bun
error: undefined decorator 'missing'
  --> program.bun:1:2
   |
 1 | @missing
   |  ^
```

A decorated function may be exported, and the `export` may be written
before the decorators or after them.

```bun
@tagged
export fn add(a, b) {
    return a + b
}
```

### `del`

`del` removes a name from the scope that holds it.

```bun
var x = 1
print(x)      // 1
del x
try {
    print(x)
} catch err {
    print(err) // undefined variable 'x'
}
```

A name that is not bound is an error before the program runs, like any
other use of a name that does not exist.

`del` also removes an item from a dict or a list.

```bun
let d = {"a": 1, "b": 2}
del d["a"]
print(d.keys().join(","))   // b

var items = [1, 2, 3]
del items[1]
print(items.join(","))      // 1,3
```

The native backend has `del` too: the removal of a name, of a key of a dict
and of an item of a list all work, and the failures read like the failures
of the machine.

### The generators

A function that gives a value with `yield` is a generator. It gives its
values one at a time, and the program asks for the next one.

```bun
fn counter(start) {
    var value = start
    while true {
        yield value
        value = value + 1
    }
}

let g = counter(1)
print(next(g))    // 1
print(next(g))    // 2
```

A generator works in a `for` loop as well, and the loop ends when the
generator is over.

```bun
fn steps() {
    yield 1
    yield 2
}

for value in steps() {
    print(value)
}
```

The body of a generator does not run until the program asks for the first
value, and it never runs ahead of the program that reads it: the value of
a `yield` is the value that the program sends back into the generator.

```bun
fn echo() {
    let answer = yield 1
    yield answer
}

let g = echo()
print(next(g))       // 1
print(send(g, 7))    // 7
```

`next(generator)` gives the next value of a generator, and
`next(generator, default)` gives the default value when the generator is
over. `send(generator, value)` sends a value into the generator and
gives its next value.

The native backend does not have generators yet and refuses a program
that uses them, by name.

## Structs and methods (Phase 17)

A `struct` is a type of value that holds named fields. It is the first
half of the type-system spine of the language: the pieces a program
builds its own types with.

```bun
struct Point {
    var x: int,
    var y: int
}

impl Point {
    fn sum(self) -> int {
        return self.x + self.y
    }

    fn bump(self, by: int) {
        self.x = self.x + by
        self.y = self.y + by
    }
}

var p = Point(3, 4)
print(p.x)       // 3
print(p.sum())   // 7
p.bump(1)
print(p.y)       // 5
```

The rules of the language:

- A field is written `let` (read-only), `var` (writable), or with neither
  (writable). A field may carry a type and a default value:
  `var count: int = 0`.
- The constructor is the name of the struct: `Point(3, 4)`. The arguments
  are positional and follow the order of the fields. A field with a default
  may be left out.
- A struct is a **value**: an assignment or an argument copies it, and the
  copy does not share its fields with the original.
- A method call **borrows** the receiver: `p.bump(1)` changes `p` itself.
  The receiver is the first parameter of the method, and it is named `self`.
- A method that writes to `self.<field>` is a mutating method, and it may
  only be called on a `var` name. A `let` name cannot be changed, through a
  method or otherwise.
- Two structs with the same fields are two different types.
- An `impl` block may come after the `struct` it names, and several `impl`
  blocks for one struct are merged.

The checker knows the fields of a struct, the methods of an `impl`, and the
types of their arguments, so a wrong field, a wrong argument, or a write to
a read-only field is an error before the program runs:

```bun
struct Point {
    let x: int
}

var p = Point(1)
p.x = 2        // error: cannot assign to immutable field 'x'
```

Every engine of the language runs the same program the same way: the tree
walker, the stack VM, the register VM, the native backend, and the
self-hosted front end.

## Protocols (Phase 18)

A `protocol` names the methods a value must have. It is how a program says
"any value of this shape" without saying what the shape is made of.

```bun
protocol Shape {
    fn area(self) -> float
    fn name(self) -> string
}

struct Circle {
    var r: float
}

impl Circle {
    fn area(self) -> float {
        return 3.0 * self.r * self.r
    }

    fn name(self) -> string {
        return "circle"
    }
}

fn show(shape: Shape) {
    print(shape.name())
    print(shape.area())
}

show(Circle(2.0))
```

The rules of the language:

- A protocol holds method signatures without a body. The first parameter of a
  signature is the receiver, and it is named `self`.
- A type satisfies a protocol when it has **every** method of the protocol.
  The check is structural: there is no `impl Shape for Circle`, and a type
  does not say that it satisfies a protocol.
- A protocol may be written as the type of a parameter, of a field, or of a
  variable. The value is then checked against the methods of the protocol.
- A protocol is a type, so it is not a value: `let s = Shape` is an error.
- A method call on a protocol is checked against the signature of the
  protocol: the number of the arguments and their types.

The checker names the method that is missing, because that is the part the
program has to add:

```bun
protocol Shape {
    fn area(self) -> float
}

struct Point {
    var x: int
}

fn show(shape: Shape) {
    print(shape.area())
}

show(Point(1))
// error: type 'Point' does not satisfy protocol 'Shape': missing method 'area'
```

## Generics (Phase 19)

A type parameter stands for a type that is not known yet. The checker finds
the type from the arguments of the call, and the type of the call is the
return type with the type arguments in place of the type parameters.

```bun
fn first<T>(xs: list<T>) -> T {
    return xs[0]
}

fn total<T: Num>(xs: list<T>) -> T {
    var sum = 0
    for x in xs {
        sum = sum + x
    }
    return sum
}

print(first([1, 2]))
print(first(["a", "b"]))
print(total([1, 2, 3]))
```

The rules of the language:

- A name between angle brackets after the name of the function is a type
  parameter: `fn first<T>(...)`. It is a type inside the function, so it may
  be written as the type of a parameter, of a variable or of the result.
- The body of a function with type parameters is checked **once**, on its
  own: the checker does not walk the program once per type.
- A bound says which types the type parameter may not leave: `fn total<T: Num>`.
  The bounds are `Num` (the numbers), `Ord` (the numbers and the strings),
  `Eq` and `Hash` (the types that can be compared or used as a key) and
  `Show` (every type). A bound that the argument does not satisfy is an error
  at the call.
- A type parameter may stand for the type of the elements of a list:
  `list<T>`. The checker keeps the type of a list, so `first([1, 2])` is an
  `int` and `first(["a"])` is a `string`.
- The types are **erased** when the program runs. There is one function for
  every type parameter, not one copy per type: the register code and the C
  backend carry no type information, so a generic function is the same code
  for every type and the phase adds no opcode.
- A type parameter outside a function is an unknown type: `let x: T = 1` is an
  error.
- Only one level of type arguments is written: `list<T>`. A function type as a
  type argument (`fn(T) -> U`) and the nested generics (`list<list<T>>`) are
  deferred to a later phase.

The checker names the type that does not fit and the bound it does not
satisfy, because that is the part the program has to change:

```bun
fn total<T: Num>(xs: list<T>) -> T {
    var sum = 0
    for x in xs {
        sum = sum + x
    }
    return sum
}

print(total(["a"]))
// error: type 'string' does not satisfy the bound 'Num' of type parameter 'T'
```

## Results and the `?` operator (Phase 20)

A result is a value that holds either a success or a failure. `Ok(value)`
makes a success and `Err(error)` makes a failure. A result is data, so it
may sit in a list, in a field or in a dict.

```bun
fn parse(s: string) -> result {
    if s == "" {
        return Err("the text is empty")
    }
    return Ok(len(s))
}
```

The `?` operator takes the value out of a success and passes a failure
along. The value of `parse(s)?` is the number of characters when the text
is not empty, and the enclosing function returns the failure unchanged
when it is.

```bun
fn twice(s: string) -> result {
    let n = parse(s)?
    return Ok(n * 2)
}

print(twice("bun")["ok"])
print(twice("")["err"])
```

The rules of the language:

- `result` is the name of the type. A function that returns a result says
  `-> result`.
- `Ok` and `Err` take one argument each and make a result. The value of a
  success sits under the key `ok`, and the error of a failure under `err`.
- `is_ok(value)` and `is_err(value)` are **functions**, not methods, so
  they do not collide with the methods of a program. A value is a success
  when it is a dict with the key `ok`, and a failure when it is a dict with
  the key `err` and without the key `ok`.
- The `?` is only allowed **inside a function**, and the function has to
  return a result. The checker says so when it does not.
- A value whose type is known and is not a result cannot carry a `?`: the
  checker names the type that is wrong.
- A value whose type is not known yet (`any` or `dict`) is left to the
  runtime. A value that is not a result at all is a runtime error.

The checker names the part of the program that has to change:

```bun
fn f() -> int {
    return Ok(1)?
}
// error: the '?' operator needs a function that returns 'result'
```

Every engine of the language runs the same program: the tree, the stack VM,
the register VM, the C backend and the self-hosted front end.

## The native tier (Phase 11)

The stack VM is the reference semantics of the language. The register VM is
a second machine that runs the same programs: the values of an expression
live in the registers of a frame instead of on an operand stack, and every
instruction names its operands.

```
source ──> stack bytecode ──> registerizer ──> register code ──> register VM
                │                                        │
                └──────── the golden corpus ───────────┘
```

The register code is verified before it runs. The verifier proves that the
registers are inside the file, that the jumps land on an instruction of the
same function, that the depth of the expression is the same on every path
that reaches an instruction, and that every function ends with a return or
a halt. A program that does not pass the verifier is a runtime error that
says which function and which instruction are wrong.

The superinstruction tier fuses the pairs of loads that sit next to each
other, so the program pays for one dispatch instead of two. The fusion
happens at load time, on the code that the verifier has already checked,
and the fused code goes through the verifier a second time.

```bash
bun --engine register program.bun          # the register tier
bun --engine register --tier program.bun   # with the superinstructions
```

The rule of the phase: a program that prints something different under
another engine is a bug in the tier, never a difference in the language.
The golden corpus of the test suite runs under every engine, and
`tests/test_tiers.py` runs the same program under every tier and compares
the output byte for byte.

## The native backend (Phase 13)

The backend reads the register code of the native tier and emits C. One C
function per Bun function, one label per instruction, and the jumps become
`goto`, so the shape of the code on the page is the shape of the code in the
register file.

```
source ──> stack bytecode ──> registerizer ──> register code ──> C ──> binary
```

The system compiler does the work of the optimisation, because the work of
the optimisation is the one thing a language should not write twice.

```bash
bun --engine c program.bun
```

The backend never changes the language. The stack VM stays the reference and
the default engine; the backend is opt-in, and it is measured against it.

```
a program with a loop and a recursion (the fastest of 3 runs)
  vm              8169.9 ms
  c (the run)      777.5 ms
  c (the build)   3892.9 ms
  the native backend is 10.5 times faster
```

The number comes from `python3 tools/bench_c.py`, and it is the run time and
the build time apart, because the build is a price of the backend and not a
part of the run. The run of the backend is about ten times faster than the
run of the stack VM on the machine of the phase.

The binary of a program is kept under `~/.cache/bun/c`, so the second run of
the same program starts at once instead of paying for the compiler again.

The backend says no rather than guessing. A construct it cannot translate is
refused at compile time, with the name of the construct:

```bash
$ bun --engine c program.bun
error: the C backend does not support the scope statement
```

The `scope` and the `yield` are refused that way, and so is a builtin the
backend does not have:

```bash
$ bun --engine c program.bun
error: the C backend does not support the builtin 'ffi_load'
```

The oracle is the golden corpus, the same as everywhere else: 33 programs
print the same bytes under the backend, 4 are refused by name, and none of
them prints something else.

### The backend links its modules

The backend links the modules of a program into the program itself. A module
is compiled with the compiler of the language, its body becomes functions of
the C program, and the values it exports live in a table that the import
fills. A module is run once, the first time it is imported, and the second
import finds the table of the first run, like the machine does.

```bun
import { add } from "./math.bun"
print(add(2, 3))
```

```bash
$ bun --engine c program.bun
5
```

A module that the backend cannot translate is refused by name, with the
name of the builtin or of the construct it does not have:

```bash
$ bun --engine c program.bun
error: the C backend does not support the builtin 'ffi_load'
```

The `match` of the language is a pattern of the backend too. A case is a
plan, the plan is filled when the program starts, and the matcher of the
runtime walks it. The bindings of a case are collected first and applied
after, so a case that does not match leaves nothing behind. A case has a
scope of its own, so the names that its pattern binds leave the program when
the case ends, and a name of a pattern hides the name of the module for the
case, the same way the machine hides it.

The files of a program are the files of the machine: `read_file`,
`write_file`, `append_file`, `file_exists` and `getenv` work under the
backend, and their failures say the same words as the failures of the
machine.

The set of the language is a set of the backend too. The values of a set,
the order of the values, the methods of a set and the operators of two sets
are the same under the backend and under the machine, and the builtin
`set` is a call of the C function of the runtime.

```bun
let a = set([1, 2, 3])
let b = set([2, 3, 4])
print(a | b)     // {1, 2, 3, 4}
print(a & b)     // {2, 3}
print(a - b)     // {1}
print(a.values()) // [1, 2, 3]
```

The `with` of the language is a `with` of the backend too. The target of the
statement is a dictionary that holds `__enter__` and `__exit__`, the target is
entered, the body runs, and the target is left. A target that fails is left
with the message of the failure, and a target that swallows the failure
swallows it.

```bun
with target("a") as value {
    print(value)
}
```

The name of the statement lives in the environment of the scope that holds
it, because the statement defines the name there, and the name leaves the
scope when the scope ends. The targets of the statements of a function wait
on a stack of their own, and the counters of a function that catches an
error live in the memory: an error jumps into the frame of the function, and
a counter that the compiler of the system keeps in a register would have a
value that nobody knows.

The secret and the dump of the language are the secret and the dump of the
backend too. A secret is a value of its own kind, every rendering of it is
`***`, and only the method `reveal` gives the value back. The dump of a value
is the dump of the machine: the keys of a dictionary are in order, the values
of a set are in the order of the set, and a secret inside a dump is `"***"`.

```bun
let token = secret("hunter2")
print(token)            // ***
print(dump({"key": token}))  // {"key": "***"}
print(token.reveal())   // hunter2
```

### The names live in the frame

The first version of the backend kept every name in a table of strings and
built a new table for every call and for every turn of a loop. A loop of ten
million turns paid ten million tables, and the memory of the run grew to
gigabytes.

The backend reads the register code and works out, for every name, whether a
closure ever needs it. A name that no closure takes lives in a slot of the
frame of the function that owns it, like a local variable of C. A name that a
closure takes, or a name that a jump may skip, stays in the table of the
scope, because a closure may look it up later. The table of a scope is built
only when the scope holds such a name, and a function that has no closure
builds no table at all.

The measurement of the change, on the machine of the phase:

```
a loop of ten million turns
  plain c         4.3 ms   peak     10.3 MB   10000000
  bun c         130.1 ms   peak     10.3 MB   10000000
  bun vm      102396.4 ms   peak     12.0 MB   10000000

the recursion of fib(30)
  plain c         6.0 ms   peak     10.4 MB   832040
  bun c         197.9 ms   peak     10.4 MB   832040
```

Before the change the loop took 56.9 seconds and 4.7 gigabytes of memory,
and the recursion of `fib(30)` took about 96 seconds. The loop is now 440
times faster and the memory of the run is the memory of the program, and the
recursion is 490 times faster.

The numbers come from `python3 tools/bench_c.py` and from the benchmark of
the frame, `/tmp/opencode/work/bench10m.py`, which measures the wall time and
the peak memory of every engine.

### The registers are variables

The registers of the expression were an array of the frame of the function.
An array lives in the memory, so a loop wrote every register to the memory
on every step, and the compiler could not keep a value in a register of the
machine.

The backend now gives every register of a function a variable of its own.
The compiler keeps the variables in the registers of the machine, and the
loop writes nothing to the memory but the name of the loop.

A function that catches an error is the exception: the error jumps into the
frame of the function, and the values of an automatic object would be lost
by the jump, so the frame of such a function lives in the memory.

### The names that never change are static

The lookup of a name in the table of the scope was the most expensive part
of a call: the recursion of `fib(30)` looks the name of the function up
twice per call, and the lookup is a hash and a comparison of the names.

The backend reads the program and finds the names that never change: a name
of a module that the program defines once, with a function, and never
assigns and never removes. Such a name is read from a static variable, and
the variable holds the function from the moment it is defined. A name that
an enclosing function binds, a name that is defined twice and a name that
the program assigns are looked up every time, as before.

### The calls of a known name are direct

A call of a name that never changes does not have to look the function up
either. The backend knows the function, so it writes the call of the C
function of the name, and the compiler of the system sees which function is
called: it can inline the call and keep the arguments in the registers of
the machine.

The environment of the function is a static variable too, so the call does
not look the environment of the closure up either.

### The strings of the program are built once

A string of the program is a string, and not one string for every use of
it. The backend writes the strings of the pool of the program into
variables, builds them when the program starts, and every use reads the
variable.

The difference is large: a loop of ten million turns that uses a string
took 6.7 seconds when the string was built at every use, and takes 0.77
seconds now.

### The calls of a builtin are direct

A name of the language that the program never defines and never changes
always holds the builtin of the language. The call of such a name does not
look the builtin up in the environment, and the compiler of the system sees
which builtin is called.

```c
BunValue call_args[1];
call_args[0] = r1;
BunValue result = bun_builtin_len(call_args, 1);
```

A loop of ten million calls of a builtin went from 765.8 ms to 509.7 ms
with this change alone.

### The builtins of the program are static

A builtin of the language lives in the table of the globals, and the lookup
of a name in that table is the most expensive part of a read. A builtin that
the program reads is therefore copied into a static variable once, when the
program starts, and a read of the name reads the variable.

```c
static BunValue bun_builtin_static_0;
...
bun_builtin_static_0 = bun_env_get(globals, "len");
...
r0 = bun_builtin_static_0;
if (r0.tag == BUN_NULL) {
    r0 = bun_env_get(env, "len");
}
```

The static holds nothing until the program starts, and the check of the
fallback keeps the read correct when the program runs before the setup.

Only a builtin that the program never defines and never changes is kept in a
static. A program that binds the name of a builtin, that changes it, that
removes it, or that a pattern of a `match` binds, reads the table of the
globals as before.

A loop of ten million calls of a builtin went from 509.7 ms to 286.7 ms
with this change alone.

### The keys of a dictionary are in a table

A dictionary of the machine is a table of the keys, and a lookup of a key is a
hash and a probe. The first version of the backend walked the keys of the
dictionary for every read, and a program that filled a dictionary of a hundred
thousand keys paid five billion comparisons.

The backend keeps the keys of a dictionary in a table of its own, and the
values of a set in the same way. The size of the table is always a power of
two, so the slot of a key is a mask and not a division, and a division costs
more than the rest of the lookup.

```
a dictionary of a hundred thousand keys, filled and read back
  bun c       291.2 ms
  bun vm      5202.0 ms
```

The same program took more than two minutes under the backend before the
table, and the machine never walked the keys.

### The methods of a type are found by their first letter

A call of a method looks the name of the method up in the list of the methods
of the type. The first version of the backend compared the name with the name
of every method of every type, one after the other, and a method of a string
was compared with thirty names before it was found.

The backend looks the first letter of the name up first, and compares the
name with the names that begin with that letter only.

```c
switch (method[0]) {
case 'p':
    if (strcmp(method, "push") == 0) {
        ...
    }
    break;
...
}
```

A million calls of a method went from 58.4 ms to 7.9 ms with this change
alone, and the call of a method of a list is now as cheap as the call of a
builtin.

### The flags of the compiler of the system

The backend builds the program with `-O3` and with two flags of its own.

`-falign-loops=32` puts the head of a loop on a boundary of 32 bytes. A
loop of a program is the place where the speed matters most, and an aligned
loop runs faster.

`-fno-guess-branch-probability` tells the compiler of the system not to
guess the way a branch goes. A guess makes the compiler lay the blocks of
the program out for the guess, and the guess is wrong for the loops of a
program often enough that the value of a loop stays in the memory instead
of the registers of the machine. Without the guess, every loop of a program
runs at the same speed: the loop of ten million turns took 12.1 ms with the
flag, and took between 4.6 ms and 21.0 ms without it, according to the
shape the compiler of the system happened to give it.

The measurement of the changes, on the machine of the phase:

```
a loop of ten million turns
  plain c         4.8 ms   peak     10.9 MB   10000000
  bun c          10.2 ms   peak     10.9 MB   10000000
  bun vm      109390.4 ms   peak     12.2 MB   10000000

the recursion of fib(30)
  plain c         6.6 ms   peak     11.0 MB   832040
  bun c          25.0 ms   peak     11.0 MB   832040

ten million calls of a builtin
  bun c         286.7 ms   peak    153.9 MB   30000000
  bun vm      192450.5 ms   peak    395.0 MB   30000000
```

The loop went from 130.1 ms to 10.2 ms, the recursion from 197.9 ms to
25.0 ms, and the calls of a builtin from 765.8 ms to 286.7 ms. The numbers
come from the same benchmark as the ones above.

Most of the time of the last case is the list of ten million numbers that
`range` builds: the list holds 160 MB, and the pages of that memory cost
more than the calls themselves. A loop of ten million calls of a builtin
that does not build a list takes 11 ms.

The measurement of the backend today, after the `with`, the secret and the
dump arrived, is the same:

```
a loop of ten million turns
  plain c         5.4 ms   peak     10.8 MB   10000000
  bun c          15.2 ms   peak     10.8 MB   10000000
  bun vm      111227.8 ms   peak     12.4 MB   10000000

the recursion of fib(30)
  plain c         6.4 ms   peak     10.9 MB   832040
  bun c          25.3 ms   peak     10.9 MB   832040

ten million calls of a builtin
  bun c         263.4 ms   peak    153.9 MB   30000000
  bun vm      203289.1 ms   peak    395.0 MB   30000000
```

### A failure of the backend has a picture

The backend writes the position of the source before the instructions that
can fail, and the program carries the lines of the source and the table of
the advice of the machine. A failure of the backend therefore reads like a
failure of the machine, down to the caret and the hint:

```
$ bun --engine c program.bun
error: index 7 out of range
  --> program.bun:2:7
   |
 2 | print(xs[7])
   |       ^
  hint: the index is past the end of the container; the first index is 0 and the last one is len(container) - 1
```

The table of the advice is the table of `bun/errors.py`, so the two never
drift apart.

## The machine surface (Phase 14)

The language is queryable, not just readable. An assistant drives a session
of Bun over JSON-RPC 2.0, one object per line, on the standard input and
the standard output.

```bash
bun repl --json
```

```json
{"jsonrpc": "2.0", "id": 1, "method": "eval", "params": {"source": "1 + 1"}}
{"jsonrpc": "2.0", "id": 1, "result": {"value": 2, "type": "int", "printed": "2"}}
```

The answer is a value, not a text: the caller asks for a number and gets a
number. The text of the value is there as well, because a human reads the
text.

| Method | What it does |
|--------|--------------|
| `eval` | run the source in the session and return the value |
| `check` | check the source and return the diagnostics |
| `compile` | return the bytecode of the source |
| `symbols` | return the names the session holds |
| `docs` | return the documentation of a symbol |
| `api` | return the table of the builtins |
| `reset` | empty the session |
| `shutdown` | end the session |

The session is a session: a name defined by one call is there for the next
one.

```json
{"jsonrpc": "2.0", "id": 1, "method": "eval", "params": {"source": "let x = 41"}}
{"jsonrpc": "2.0", "id": 2, "method": "eval", "params": {"source": "x + 1"}}
{"jsonrpc": "2.0", "id": 2, "result": {"value": 42, "type": "int", "printed": "42"}}
```

A failure is a failure of the protocol, and it keeps the two channels of the
language: the kind of the error is `lex`, `parse`, `type` or `runtime`, and
the data carries the message, the line and the column.

```json
{"jsonrpc": "2.0", "id": 3, "method": "eval", "params": {"source": "1 +"}}
{"jsonrpc": "2.0", "id": 3, "error": {"code": -32000, "message": "unexpected token EOF", "data": {"kind": "parse", "line": 1, "col": 4}}}
```

## The Ankita Music Bot

`ankita-music/` is the reference application of the language: a music bot
for Telegram, written in Bun, with the commands, the queue, the playlists,
the persistence layer and the playback of the tracks.

```bash
BOT_TOKEN=... API_ID=... API_HASH=... OWNER_ID=... \
    python3 -m bun ankita-music/bot/main.bun
```

The bot runs on the Bot API alone, and it needs two programs of the system
for the playback:

| Program | What it does | Without it |
|---------|--------------|------------|
| `yt-dlp` | fetches the audio of a track, and deciphers the protected formats | the bot cannot download a track |
| `ffmpeg` | turns the track into the voice message of Telegram | the bot cannot send a voice message |

Both are optional: the bot starts without them, and it says what it cannot
do. With them, a `/play` in a chat resolves the track, downloads it,
converts it and sends it as a voice message of the chat.

```bash
pip install --break-system-packages yt-dlp
apt-get install -y ffmpeg
```

The voice *chat* of a group is a different thing: it needs the user side
of the protocol, a phone number and the group call itself. That part
lives in `ankita-music/bot/mtproto/` and it waits for the credentials of
an account:

```bash
BOT_TOKEN=... PHONE_NUMBER=... API_ID=... API_HASH=... \
    python3 -m bun ankita-music/bot/mtproto_login.bun
```

## Tests

The golden corpus is the normative specification of the language: every
program of `tests/golden/` prints the bytes of its `.out` file, under
every engine.

```bash
bun test                 # the golden corpus
bun test --json          # the same, as a JSON report
bun test --doc           # the examples of the documentation
```

The suite of the language itself runs under pytest:

```bash
pip install --break-system-packages pytest
python3 -m pytest -v
```

## Roadmap

- Phase 1: tree-walking interpreter — DONE
- Phase 1.5: methods, dicts, file I/O — DONE
- Phase 1.6: module system (`import`/`export`) and converted tools — DONE
- Phase 2: static type checker — DONE
- Phase 3: error handling (`try`/`catch`/`throw`), `list.sort()`, mime tool conversion — DONE
- Phase 3.5: bytecode compiler + stack VM; tree-walker retained as the differential oracle; `--engine tree|vm` to select — DONE
- Phase 4: front-end self-hosting (lexer, parser, compiler in Bun; `--front-end bun`) — DONE
- Phase 5: self-hosted type checker (`selfhost/checker.bun`) with error parity — DONE
- Phase 6: Pythonic surface — f-strings, slices, comprehensions, defaults and variadic parameters, unpacking, `finally` and exception chaining, `with`, the `Secret` type, undefined-name detection, the documentation registry (`bun doc`, `bun test --doc`, `bun api --json`) — DONE
  - Deferred to a later phase: Bun-written VM, serialized bytecode, default front end, self-hosted REPL and runtime module loading
- Phase 7: performance and structured concurrency — the `scope` statement (task groups, cooperative cancellation, `spawn { ... }`), a cached method dispatch, a leaner VM dispatch loop, a published startup budget, an instruction profiler (`bun compile --profile`) — DONE
  - Deferred to a later phase: a Bun-written VM, serialized bytecode, shape-based inline caches
- Phase 9: the native stacks — `bun:tensor`, `bun:sec`, `bun:game` and `bun:web`, all written in Bun — DONE
  - Deferred to a later phase: the GPU backend of the game stack
- Phase 10: the language surface — the bit operators, a loop over pairs, a loop over a dict, `assert` and `match` (with the alternatives, the guards and the tails of a case), and the `else` of a loop — DONE
  - Deferred to a later phase: class patterns
- Phase 11: the native tier — the register VM, the verifier, the superinstruction tier — DONE
  - Deferred to a later phase: the WASM backend, a counted fusion, a full optimising JIT
- Phase 12: the model stack — `bun:ai`, with the layers, the attention, the block of a transformer, the model, the format, the losses, the optimisers, the training loop, the tokenisers and the sampler — DONE
  - Deferred to a later phase: attention and the transformer, a binary model format, a subword tokeniser, a compiled backend for the kernels
- Phase 13: the C backend — the register code becomes C, the system compiler does the optimisation, the unsupported constructs are refused by name at compile time, the run of the native backend is about ten times faster than the run of the stack VM — DONE
  - DONE since: the `match` of the language, the linker of the modules, a picture of the failure like the one of the VM, a cache of the compiled programs
  - Deferred to a later phase: the `with` and the `scope` under the backend
- Phase 14: the machine surface — `bun repl --json`, the session of the language over JSON-RPC 2.0, a value comes back as a value — DONE
  - Deferred to a later phase: the completion of a name in the middle of a line, a picture of the failure in the data of the error
- Phase 16: the everyday language — the set, the type aliases `number` and `text`, the decorators — DONE
  - Deferred to a later phase: the `del` statement, the generators
- Phase 17: the first half of the type-system spine — `struct`, `impl`, the field access, the methods of a struct, and the value semantics of a struct — DONE
  - Deferred to a later phase: the `enum` (Phase 21)
- Phase 18: the protocols — a `protocol` names the methods a value must have, the check is structural, and a protocol may be the type of a parameter, of a field or of a variable — DONE
  - Deferred to a later phase: the `enum` (Phase 21)
- Phase 19: the generics — a type parameter stands for a type that the checker finds from the arguments, a bound says which types the parameter may not leave, and the types are erased when the program runs — DONE
  - Deferred to a later phase: the function type as a type argument, the nested generics, the `enum` (Phase 21)
- Phase 20: the results — `result` names a value that is either a success or a failure, `Ok` and `Err` make one, and the `?` takes the value out of a success and passes a failure along — DONE
  - Deferred to a later phase: the `enum` (Phase 21), the `?` on a value of a type that is not known yet at the checker