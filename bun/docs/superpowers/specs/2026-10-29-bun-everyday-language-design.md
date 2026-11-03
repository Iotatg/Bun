# Design: the everyday language (Phases 26 to 28)

Date: 2026-10-29
Status: approved by the user (full authority given)
Research: `docs/superpowers/research/2026-10-29-bun-language-gap-notes.md`

## 1. The rule of this program

The language is Bun, and every change here is a change of Bun. A construct
of another language is not taken because it is convenient there. It is
taken only when it fits the grammar of Bun, when the checker of Bun can
hold it, when the errors of Bun can say it, and when the language would be
poorer without it. The test of every addition is simple: does the result
read like Bun, does it refuse the unclear instead of guessing, and does it
behave the same under the five engines?

The gap notes are the evidence. They are a list of symptoms from a real
project of about 4,500 lines, and this program fixes the causes behind the
symptoms. The notes also record the mistakes of their own author, and
those are fixed in the project of the author, not in the language.

## 2. The shape of the language that answers

Five properties of Bun decide every question of this program.

- **The checker knows before the run.** A thing that can be refused before
  the program runs is refused before the program runs, with the line, the
  column, the reason and the hint.
- **The language refuses rather than guesses.** The backend refuses a
  construct by name; the checker refuses a program; the runtime refuses a
  value that does not fit the type. Nothing is converted quietly.
- **A result is a value with keys.** `half["ok"]`, `odd["err"]`. The new
  work follows this shape: the caught error is a value with keys too.
- **One program, five engines.** The tree, the stack VM, the register VM,
  the C backend and the self-hosted front end. A construct that works in
  one engine and not in another is a bug of the construct.
- **The error message is the face of the language.** Every new refusal is
  written in the voice of the existing messages.

## 3. Phase 26 — the everyday expressions

### 3.1 The compound assignment

`x += 1`, `x -= 1`, `x *= 2`, `x /= 2`, `x %= 2`, `x &= m`, `x |= m`,
`x ^= m`, `x <<= n`, `x >>= n`.

- The compound assignment is an assignment: `x += 1` is `x = x + 1` with
  one lookup of `x`, one check of the type, one store.
- The target is a name, an index or a field, exactly as the target of `=`.
- A `let` name is refused with the message the language already uses for
  an assignment to an immutable name.
- The result of the statement is the result of the assignment.

### 3.2 The increment and the decrement

`x++` and `x--`, before or after the name.

- They are statements, not expressions. A language that answers a value
  for `x++` keeps two rules for one name; Bun keeps one.
- The name has to be mutable, and the value has to be a number. The
  checker says which of the two is wrong.
- The canonical form stays `x += 1`. The two signs are the short way of
  it, and they do not replace it.

### 3.3 The match as an expression

The notes ask for the ternary of other languages. Bun already holds the
answer to "one of these values": the `match`. So the `match` becomes an
expression, and no second construct is added.

```
var word = match n {
    1 => "one"
    _ => "many"
}
```

- Every arm answers a value, and the arms have to answer the same type.
  The checker knows the type of the arms and refuses the `match` that
  mixes them.
- The `match` without a subject stays a statement.
- A value that answers no arm raises the error of the language, the same
  error a `match` statement raises.
- The `match` expression is the answer to the ternary of every other
  language: one construct for one idea, not two.

### 3.4 The null coalescing

`a ?? b` — the value of `a` when it is not null, else the value of `b`.

- The operator of the null stands beside the `?` of the result and the
  option: `?` asks a question, `??` answers the missing value.
- The right side is computed only when it is needed.
- The left side is evaluated once.

### 3.5 What Phase 26 does not add

The optional access `a?.b` and the namespace import `import * as ns` are
Phase 31. Both change the shape of a path and of a name, and they are
designed together with the bytes of Phase 29, so that the rules of a path
are written once.

## 4. Phase 27 — the containers speak

The notes list the methods of the other languages. Bun has its own table
of methods, and the additions follow its rules: a method of a list takes
the receiver and the arguments positionally, and the language has no
keyword arguments at all.

| Method | What it does |
|---|---|
| `l.map(fn)` | a new list of the results |
| `l.filter(fn)` | a new list of the values the predicate keeps |
| `l.reduce(init, fn)` | the fold of the list, the accumulator first |
| `l.find(fn)` | the first value the predicate keeps, else null |
| `l.any(fn)`, `l.all(fn)` | the questions about the list |
| `l.each(fn)` | the call of the function for every value, in place |
| `l.sort(comparator)` | the sort, the comparator takes two values and answers a number |
| `l.sort_by(key)` | the sort by the key of every value |
| `d.items()` | a list of `[key, value]` pairs |

- `sort` keeps its old meaning when it has no argument, so the old code
  keeps its meaning.
- `sort_by` is the answer to the `key=` of other languages: the key
  function is an argument, not a keyword, because Bun has no keywords in
  a call.
- `items()` answers a list of two-element lists. Bun has no tuple, and a
  list of two is the pair of the language.
- `len(d)` answers the number of the entries of a dict, the way `len(l)`
  answers the number of the values of a list.
- `print(a, b)` writes the values with a space between them and a
  newline at the end. `print()` writes an empty line.

Every one of these is a method of the table of the runtime, so it works
the same under the five engines, and the checker knows the receiver.

## 5. Phase 28 — the divisions, the additions and the kinds of the errors

These are the three findings of the notes that cost money when they are
wrong, because they answer a value that looks right.

### 5.1 The division

`/` answers the mathematical division and always answers a float when
both operands are integers. `//` asks for the whole quotient and answers
an integer when both operands are integers.

- The rule is the rule of the language, not of another language: the sign
  `/` is the sign of the division, and a division of two whole numbers
  is not a whole number.
- `a / b` with two integers of the notes becomes `a // b`, and a program
  that wants the fraction asks for `/` or for `float(a) / b`.
- The golden programs of the corpus that divide are changed, and the
  change is written in the reference of the language as a break of the
  version 0.1.

### 5.2 The addition of a string and a number

`"a" + 1` is refused. The language does not join a string and a number
quietly, because the result of the quiet join is a string that no one
asked for. The refusal carries the hint of the language: use `str(value)`
to write the number as a string, or `value.to_string()`? — the hint names
the function of the language, `str`.

### 5.3 The kinds of the errors

The caught error is a value with keys, the way a result is a value with
keys.

| Key | What it holds |
|---|---|
| `message` | the text of the error, the text the language prints today |
| `code` | the stable name of the kind: `error`, `type_error`, `io_error`, `http_error`, `timeout_error` |
| `status` | the status of an http error, when there is one |

- `print(err)` writes the message, so the code that prints an error keeps
  its meaning.
- `err["code"]` answers the kind, and the program asks the kind instead
  of reading the message. A message is for a human; a code is for a
  program.
- The HTTP builtins set `code` to `http_error` and `status` to the
  status of the answer.

## 6. The roadmap after this program

| Phase | Subject | The decision that is already taken |
|---|---|---|
| 29 | the bytes type | a byte buffer of its own, not a list of numbers; `utf8_bytes` answers bytes; `len` of bytes is bytes |
| 30 | the library of production | the HMAC, the base64url, the UUID, the gzip compression, the regex, the time of the day |
| 31 | the paths and the names | the optional access `?.`, the namespace import `import * as ns` |
| 32 | the native path | the C backend that carries a whole program, the register VM, the cache of the byte code |
| 33 | the server | the default timeouts, the limit of the body, the shutdown, the streaming client |
| 34 | the tools | `bun api` with examples, the reference of the syntax, the formatter |

Every phase of the roadmap is a design of its own, with the same rule:
the language stays Bun.

## 7. The rules of the work

- The Python front end is the reference of the shape of the tree. The
  self-hosted front end follows it, and the two answer the same errors.
- The golden corpus is the oracle: a program prints the same under the
  tree, the stack VM, the register VM, the C backend and the self-hosted
  front end.
- The reference of the language and the registry of the documentation are
  kept in parity: `bun/docs.py` and `selfhost/docs.bun`.
- A change of the semantics of the language is written in
  `docs/reference/compatibility.md` with the break it makes and the way
  to write the old program.
- Every phase is a commit of its own, and the tests of the phase run
  before the commit.

## 8. What "done" means for this program

- The expressions of Phase 26 work under the five engines, with the
  errors of the language.
- The containers of Phase 27 speak, and the old programs keep their
  meaning.
- The division, the addition and the kinds of the errors of Phase 28 are
  right, and the corpus and the reference say so.
- The tests of the repository pass, and the documentation of the language
  tells the truth about all of it.
