# Bun and Python — the differences

Bun is not a Python clone. It borrows the shape of Python — the
indentation-free braces, the `let`/`var` pair, the `fn` keyword, the
f-strings — and changes the parts where Python is either unsafe or slow.
This page records every difference that a Python programmer meets in the
first hour.

The rule of the language: **one obvious way**. Where Bun differs from
Python, the difference is deliberate and documented here.

---

## 1. Comments and division

| Python | Bun |
|--------|-----|
| `# a comment` | `// a comment` |
| `7 / 2` → `3.5` | `7 / 2` → `3` |
| `7 // 2` → `3` | `7 // 2` is a **comment** |
| `7 % 2` → `1` | `7 % 2` → `1` |

Bun has no float division between two integers: `/` is the integer
division and the result of `7 / 2` is `3`. A float is written `7.0 / 2`
and the result is `3.5`.

The modulo follows Python, not C: `-7 % 5` is `3` and not `-2`.

The floor division of two negative integers follows Python as well:
`-7 / 5` is `-2`.

## 2. Booleans

| Python | Bun |
|--------|-----|
| `not x` | `!x` |
| `x and y` | `x and y` |
| `x or y` | `x or y` |
| `True` / `False` | `true` / `false` |

`and` and `or` return one of their operands, exactly as in Python. `!`
returns a boolean.

There is no ternary `a if c else b`. The match as an expression is the
answer of the language to that question, and `??` fills a null:

```bun
var label = match title {
    "" => "none"
    _ => title
}
print(maybe ?? 7)
```

## 3. Mutability

`let` binds an immutable name, `var` binds a mutable one. The difference
is checked before the program runs, and the error names the variable.

```bun
let name = "bun"    // immutable
name = "other"      // error: cannot assign to immutable variable 'name'
```

Python has one kind of binding and a convention about which names are
constants. Bun has two.

## 4. Types

Bun is statically typed and the checker is part of the compiler. A type
error is an error before the first line runs.

```bun
let n: int = "text"    // error: cannot assign value of type 'string' to
                       // variable 'n' of type 'int'
```

The builtin types are `int`, `float`, `string`, `bool`, `null`, `list`,
`dict`, `fn` and `any`. There is no `isinstance` and there are no classes:
a value is one of these types or it is `any`.

The builtin `type_of` names the type of a value at run time. It names a
list an `array`, a function a `fn`, and a value of a type the language
does not know an `any`. The answer is the same under every engine, the
native backend included.

Python's `int` is unbounded; Bun's `int` is a 64 bit integer. The
`bigint_*` builtins work on lists of bytes when the exact arithmetic
matters.

An operation that leaves the 64 bit range is an error and not a number
that wraps around. The error is `integer overflow`, and it is the same
under every engine. A literal that does not fit is refused by the lexer
with `integer literal out of range`, and `int()` of a value that does
not fit is refused with `integer out of range`.

## 5. Numbers

`7 / 2` is `3` and `7.0 / 2` is `3.5`. A float that has no fraction is
still a float for the type checker, but it compares equal to the
corresponding integer: `7.0 == 7` is `true`.

The `+` operator follows JavaScript, not Python: it joins a number and a
string instead of raising an error.

```bun
print(1 + "2")    // "12"
print("a" + 1)    // "a1"
```

The `+` of two lists joins them, as in Python.

## 6. Dictionaries

A dict is a literal with `[]` access. A missing key is `null`, not an
error, and `.get()` returns `null` as well.

```bun
let counts = { "apple": 2 }
print(counts["pear"])      // null
print(counts.get("pear"))  // null
```

Python raises a `KeyError` for a missing key. Bun returns `null` because
a missing key is a normal state and the language has a value for it.

A dict is not iterable. Use `keys()` and `values()`:

```bun
for key in counts.keys() {
    print(key)
}
```

## 7. Functions

| Python | Bun |
|--------|-----|
| `def f(a, b=1):` | `fn f(a, b = 1) {` |
| `*args` | `*args` |
| `**kwargs` | `**kwargs` |
| `lambda x: x` | `fn(x) { return x }` |
| `f(x=1)` | `f(x = 1)` |

A function returns `null` when it has no `return`. Python returns `None`;
Bun has no `None`, it has `null`.

The parameters may be declared with a type: `fn f(a: int, b: string)`.
The types are checked at the call.

A call may pass the arguments by name, in any order.

## 8. Errors

| Python | Bun |
|--------|-----|
| `raise ValueError("x")` | `throw "x"` |
| `except ValueError as e:` | `catch (e) {` |
| `finally:` | `finally {` |
| `raise ... from e` | `throw "..." from e` |

Bun has no error classes. A value is thrown, and the `catch` parameter
binds it. The builtin failures throw a string that names the value that
went wrong, for example `cannot convert 'x' to int`.

```bun
try {
    let n = int("x")
} catch err {
    print(err)    // cannot convert 'x' to int
}
```

The errors of the *program itself* — a name that does not exist, a type
that does not match, a syntax error — are found before the program runs.
Those errors are not catchable, because the program never starts.

### The hint of an error

Every error that the runtime raises (and every static error, because both
travel through the same presentation layer) carries a hint: a line under
the message that says what to do about it. The message itself never
changes — it is the contract of the language.

```console
$ bun program.bun
error: index 3 out of range
  --> program.bun:2:12
   |
 2 | let item = xs[3]
   |            ^
  hint: the index is past the end of the container; the first index is 0 and the last one is len(container) - 1
```

The table lives in `bun/errors.py` (`HINTS`); the patterns are matched in
order and the first one that is in the message wins. The machine surface
carries the same hint in `data.hint` of the error.

## 9. Modules

| Python | Bun |
|--------|-----|
| `import os` | `import { read_file } from "./fs.bun"` |
| `from x import y` | `import { y } from "./x.bun"` |
| `__all__` | `export` |

An import always names the symbols it takes. There is no `import x` that
only runs the module, because a module without an import statement is a
statement that has no effect.

A path is always relative and always names a file. `./x.bun` is a file in
the same directory, `../x.bun` is a file one directory up. An absolute
path is refused, because a program that depends on where it lives is not
a program.

## 10. What Bun does not have

- Classes, and with them `self`, inheritance and `isinstance`.
- `try/except/else` — `finally` and `catch` are enough.
- The `global` and `nonlocal` keywords.
- `None`; the value is `null`.
- Class patterns; a value of a class is matched on its type.
- `with` on an arbitrary object; a context manager is a dict with an
  `__enter__` and an `__exit__`.

## 11. What Bun adds

- **Static types** that the checker verifies before the program runs.
- **`f-strings`** with a format spec, as in Python.
- **Slices** on strings and lists, with a step.
- **Comprehensions** for lists and dicts.
- **Unpacking** in an assignment, with a `*rest` catch-all.
- **`with`**, `finally` and exception chaining.
- **The `Secret` type**, which cannot be printed by accident.
- **A documentation registry**: `bun doc`, `bun api --json` and
  `bun test --doc`.
- **`eval`**, which runs a piece of Bun source and returns the value of
  its last expression.
- **`scope`**, a structured concurrency statement: the body runs in a task
  group, and the scope joins every task it spawned before it ends. The
  `with` and the `scope` run under every engine of the language, the C
  backend included.
- **Byte lists** as the type for binary data, and the builtins that work
  on them: `sha256`, `md5`, `aes_ige_encrypt`, `aes_ctr_crypt`,
  `rsa_encrypt`, `utf8_bytes`, `bytes_slice`, `bytes_append`, `bigint_*`.
- **Exponent notation** in the number literals: `1e-8`, `2.5E+3`.
- **The native stacks**: `bun:tensor`, `bun:sec`, `bun:game`, `bun:web` and
  `bun:ai`. They are written in Bun and live in `lib/bun/`; the `bun:`
  prefix finds them.
- **A model stack**: `bun:ai` has the layers, the model, the format, the
  losses, the optimisers, the training loop, the tokenisers and the
  sampler, so a Bun program can build, train, save, load and run a model
  without leaving the language.
- **A listening socket**: `tcp_listen`, `tcp_accept` and `tcp_close`, so a
  Bun program can serve HTTP without a C library.
- **An HTTP/1.1 server** with a kept-alive connection: two requests that
  arrive in one write are both served, and an answer may ask for the
  close.
- **A streamed answer** with the chunked encoding of HTTP/1.1, built with
  `chunked(pieces)`.
- **The bit operators** `&`, `|`, `^`, `~`, `<<` and `>>`, with the
  spelling and the precedence of Python.
- **A loop over pairs** (`for name, value in pairs`) and **a loop over a
  dict**, which walks the keys in the order they were put in.
- **The `del` statement**, which removes a name from the scope that holds
  it, or an item from a dict or a list. The native backend has it too.
- **The generators**: a function that gives a value with `yield` gives its
  values one at a time. `next(generator)` asks for the next one, and
  `send(generator, value)` sends a value into the generator, which is the
  answer of its `yield`. The body of a generator runs in a thread of its
  own, and it never runs ahead of the program that reads it.
- **The power operator `**`**, with the precedence of Python.
- **A `bun:math` stack**, written in Bun: the square root, the exponential,
  the logarithm, the circle, the angles, the powers and the rounding.
- **The `else` of a loop**: the block that runs when the loop ends
  without a `break`.
- **`assert`**, with an optional message.
- **`match`**, a dispatch on the shape of a value: a literal, a binding, a
  wildcard, a type, a range, a list or a dict. A case may name more than
  one pattern: `301, 302 => print("moved")`, it may have a guard:
  `n if n > 0 => print(n)`, and a list pattern may have a tail:
  `[first, *rest]`. A **struct pattern** names a struct and its fields:
  `Point(x: 0, y)` answers for a value of that struct alone, tests the
  field `x` against the literal `0` and binds the field `y`, and a field
  pattern is any pattern, a nested struct included. An unknown struct or
  an unknown field is a checker error and not a failed match.
- **The `enum`**, a named choice: a variant holds no fields or the fields
  of a struct, the name of the enum is not a value, and a `match` pattern
  binds the fields of a variant. The value is a dict that holds the name of
  the enum, the name of the variant and the fields, so a `match` of a dict
  pattern answers for a variant too.
- **The `option`**, a value that may be missing: `some(value)` holds one
  and `none()` holds the missing one, `is_some` and `is_none` tell the two
  apart, the `?` gives the value in a function that answers an option and
  passes a `none` along, and a `for` refuses to walk one.
- **The iterator protocol**: a `for` walks any struct that answers `next`
  with `some(item)` and `none()`. The receiver is borrowed across the loop,
  so a `next` that writes to a field keeps walking, and the value keeps its
  place when the loop stops early.
- **The word `not`**, beside the mark `!`, with Python's precedence: the
  word binds looser than a comparison and tighter than `and`.
- **A set**: `set([1, 2, 3])` holds the values that are not equal to each
  other. A set has the methods `len`, `add`, `remove`, `contains`,
  `values`, `union`, `intersection` and `difference`, the operators `|`,
  `&` and `-` join two sets, a set can be walked, and the checker knows
  its type.
- **The names `number` and `text`**: a `number` is a `float` and a `text`
  is a `string`. An alias is kept in the message of an error, so a
  program that says `number` is told about a `number`.
- **Decorators**: a function may have decorators in front of it. Each of
  them receives the function and returns the value that the name of the
  function holds afterwards. The decorator that is written last is the
  one that is called first, the name of the function is bound before the
  decorators run, and the checker knows the name of a decorator before
  the program starts.
- **A register machine** beside the stack VM: `--engine register` runs the
  same program with the values of an expression in the registers of a
  frame, and `--tier` fuses the pairs of loads that sit next to each
  other into one instruction. The language is the same under every
  engine, down to the message of the errors.
- **A native backend**: `--engine c` turns the register code of the
  register machine into C and leaves the optimisation to the compiler of the
  system. The backend never changes the language, and it refuses the
  constructs it cannot translate — the `scope`, the `yield` and the
  builtins it does not have — by name, at compile time. The builtins it
  does have are the ones a program reaches for on the first line:
  `print`, `len`, `range`, `str`, `int`, `chr`, `ord`, `float`,
  `type_of`, `bool`, `abs`, `sum`, `any`, `all`, `min`, `max`, `zip`,
  `enumerate`, `sorted`, `reversed`, `set`, `secret` and `dump`. A builtin
  takes no keyword argument, and the backend refuses a call that gives it
  one, with the same message and the same place as the machine.
- **The native backend has the `with` of the language**: the target of the
  statement is a dictionary that holds `__enter__` and `__exit__`, the
  target is entered, the body runs, and the target is left. A target that
  fails is left with the message of the failure, and a target that
  swallows the failure swallows it. The name of the statement lives in the
  environment of the scope that holds it, and the counters of a function
  that catches an error live in the memory, because an error jumps into
  the frame of the function.
- **The native backend reads and writes the files**: `read_file`,
  `write_file`, `append_file`, `file_exists` and `getenv` work under the
  backend, and a file that cannot be read fails with the message of the
  machine and the place of the machine.
- **The native backend has the set of the language**: the values of a set,
  the order of the values, the methods of a set and the operators of two
  sets are the same under the backend and under the machine, and the
  builtin `set` is a call of the C function of the runtime.
- **The native backend has the secret and the dump of the language**: a
  secret is a value of its own kind, every rendering of it is `***`, and
  only the method `reveal` gives the value back. The dump of a value is
  the dump of the machine: the keys of a dictionary are in order, the
  values of a set are in the order of the set, and a secret inside a dump
  is `"***"`. A value that cannot be canonicalized is refused with the
  message of the machine.
- **The native backend links its modules**: a module of a program is
  compiled with the compiler of the language and linked into the C
  program. Its body becomes functions of the C program, the values it
  exports live in a table, and a module runs once, the first time it is
  imported.
- **The native backend has the `match` of the language**: a case is a
  plan, the plan is filled when the program starts, and the matcher of
  the runtime walks it. The bindings of a case are collected first and
  applied after, so a case that does not match leaves nothing behind. A
  case has a scope of its own, so the names that its pattern binds leave
  the program when the case ends, and a name of a pattern hides the name
  of the module for the case, the same way the machine hides it.
- **A build cache for the native backend**: the binary of a program is
  kept under `~/.cache/bun/c`, so the second run of the same program does
  not pay for the compiler of the system (the key covers the program, the
  runtime of C and the compiler).
- **The names of the native backend live in the frame**: a name that no
  closure takes is a slot of the frame of its function, and a name that a
  closure takes, or that a jump may skip, stays in the table of the scope.
  A scope builds a table only when it needs one, and a function with no
  closure builds none. A loop of ten million turns takes 23 ms under the
  backend and 11 MB of memory, where it took 56.9 s and 4.7 GB before.
- **The registers of the native backend are variables**: the registers of
  a function that catches no error are plain variables of C, so the
  compiler keeps them in the registers of the machine and a loop does not
  write them to the memory on every step. A function that catches an
  error keeps its frame in the memory, because the error jumps into it.
- **The names of the native backend that never change are static**: a name
  of a module that the program defines once and never changes is read
  from a static variable instead of from the table of the scope, and the
  lookup of a name is the most expensive part of a call. A call of such a
  name is a call of the C function of the name, so the compiler of the
  system can inline it. The recursion of `fib(30)` takes 26 ms under the
  backend, where it took 198 ms when the names were looked up every time.
- **The strings of the native backend are built once**: a string of the
  program is a variable of the program, and the program builds it when it
  starts. A loop of ten million turns that uses a string took 6.7 seconds
  when the string was built at every use, and takes 0.77 seconds now.
- **The calls of a builtin of the native backend are direct**: a name of the
  language that the program never defines and never changes always holds
  the builtin of the language, so the call does not look the builtin up in
  the environment. A loop of ten million calls of a builtin went from
  765.8 ms to 509.7 ms with this change alone.
- **The builtins of the native backend are static**: a builtin that the
  program reads is copied into a static variable when the program starts, so
  a read of the name does not look it up in the table of the globals. A
  program that defines the name, that changes it, that removes it, or that
  a pattern of a `match` binds, reads the table of the globals as before. A
  loop of ten million calls of a builtin went from 509.7 ms to 286.7 ms with
  this change alone.
- **The keys of a dictionary of the native backend are in a table**: a lookup
  of a key is a hash and a probe, and not a walk of the keys. The values of
  a set are kept in a table of the same kind. A program that fills a
  dictionary of a hundred thousand keys and reads it back took more than two
  minutes under the backend before the table, and takes 291 ms now, where the
  machine takes 5202 ms.
- **The methods of the native backend are found by their first letter**: the
  name of a method is compared with the names of the methods that begin with
  the same letter only, and not with the name of every method of every type.
  A million calls of a method went from 58.4 ms to 7.9 ms with this change
  alone.
- **A refusal of the native backend has a place**: a program that the
  backend does not support is refused at compile time, and the refusal says
  the line of the program and the column of it.
- **A failure of the native backend has a picture**: the message, the place
  of the source, the caret and the advice, and they are the same as the ones
  of the machine. The table of the advice is the table of `bun/errors.py`.
- **A test command**: `bun test` runs the golden corpus and prints the
  report, `bun test --json` prints it as a JSON document, and `bun test
  --doc` runs the examples of the documentation.
- **A machine surface**: `bun repl --json` starts a session that speaks
  JSON-RPC 2.0 on the standard input and the standard output. An
  assistant can evaluate an expression, keep a name between two calls,
  check a source and read the bytecode of it. A value comes back as a
  value, and a failure comes back with the kind of the error, the
  message, the line and the column.

## 12. The integer division trap

The one difference that surprises people the most:

```bun
print(7 / 2)      // 3
print(7.0 / 2)    // 3.5
```

In Python `7 / 2` is `3.5`. In Bun it is `3`, because an integer division
that quietly produces a float is a source of slow programs, and Bun
wants the fast path to be the default.

## 13. Containers that work

A list has the methods Python's list comprehensions and `map`/`filter`
give you, and a dict has the method `items()`:

| Python | Bun |
|--------|-----|
| `[x * 2 for x in values]` | `values.map(double)` |
| `[x for x in values if x % 2 == 0]` | `values.filter(is_even)` |
| `functools.reduce(add, values, 0)` | `values.reduce(0, add)` |
| `next(x for x in values if x > 0)` | `values.find(is_positive)` |
| `any(x > 0 for x in values)` | `values.any(is_positive)` |
| `all(x > 0 for x in values)` | `values.all(is_positive)` |
| `for x in values: f(x)` | `values.each(f)` |
| `sorted(values, key=f)` | `values.sort_by(f)` |
| `dict.items()` | `d.items()` |
| `len(d)` | `len(d)` |

The function is always the last argument, and the accumulator of `reduce`
comes first, because a call in Bun has no keyword arguments:

```bun
fn double(n) { return n * 2 }
fn is_even(n) { return n % 2 == 0 }
fn add(acc, value) { return acc + value }

print([1, 2, 3].map(double))        // [2, 4, 6]
print([1, 2, 3].filter(is_even))    // [2]
print([1, 2, 3].reduce(0, add))     // 6
print([1, 2, 3].find(is_even))      // 2
print([1, 2, 3].any(is_even))       // true
print([1, 2, 3].all(is_even))       // false
```

`find` answers `null` when nothing is kept, and `each` answers `null`.
`sort` without an argument keeps its old meaning, the list in order of
its values; with a comparator it sorts the way the comparator says, and
the comparator answers a number. `sort_by` sorts by the key of every
value, and the keys must be all numbers or all strings.

`print` takes any number of arguments and writes them with a space
between them, where Python's `print` separates its arguments by a space
as well.

The pairs of `d.items()` are two-element lists, because Bun has no
tuple:

```bun
let d = { "a": 1, "b": 2 }
print(d.items())   // [[a, 1], [b, 2]]
```
