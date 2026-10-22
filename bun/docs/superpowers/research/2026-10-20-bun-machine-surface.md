# The Machine Surface of Bun

Date: 2026-10-20
Phase: 14

## The question

The goal of the language is that an assistant can work with it with
confidence. The feel model of the specification (§11) says that this is
a question of *predictability*: the assistant has to be able to ask the
language what it means, and get an answer it can trust.

The language already answers three of the questions an assistant asks:

- `bun check --json` gives the diagnostics of a file;
- `bun doc <symbol>` gives the signature and the examples of a builtin;
- `bun api --json` gives the whole table of the builtins.

What the language does **not** have is a *session*. An assistant that
wants to try an expression, look at the result and try another one has
nothing to talk to: the REPL reads from a terminal and prints for a
human.

The question of this phase is therefore narrow and concrete:

> What is the smallest protocol that lets an assistant drive a session of
> the language, with the same guarantees the rest of the language gives?

## What the precedents do

**LSP (the Language Server Protocol).** The protocol of the editors. It
is JSON-RPC over a pipe, with the requests `initialize`,
`textDocument/didOpen`, `textDocument/completion` and the rest. Two
things of it are worth copying:

- the session is *stateful*: the client opens a document, the server
  keeps it, and the client changes it;
- the answers carry *structured data*, not text: a completion is a list
  of items with a kind, a range and a detail, not a blob of text.

Two things of it are worth **not** copying: the protocol is large, and
it was designed for an editor that already has a document model. An
assistant that drives a *session* does not have a document.

**The REPL of Python.** `>>> ` prompts, `help()`, `dir()`. Good for a
human, bad for a machine: the output of an expression is printed, not
returned, so a caller has to read the text.

**The REPL of Node.** `vm.runInContext(code, context)` returns the
*value* of the last expression, and the context is a live object the
caller can read. The value comes back as a real value, not as text. This
is the shape the protocol wants.

**The `eval` of Bun.** `eval(source)` already exists in the language
(Phase 6): the source is lexed, parsed and checked, then run in a fresh
scope, and a static failure becomes a catchable error. That is exactly
the semantics a session wants, and it is already tested.

## The decision

A **JSON-RPC 2.0 session over the standard input and output**, one JSON
object per line, with these methods:

| Method | What it does |
|--------|--------------|
| `eval` | run the source in the session, return the value |
| `check` | check the source, return the diagnostics |
| `compile` | return the bytecode of the source |
| `symbols` | return the names the session holds |
| `docs` | return the documentation of a symbol |
| `api` | return the table of the builtins |
| `reset` | empty the session |
| `shutdown` | end the session |

The reasons:

- **JSON-RPC, because it is the protocol of the tools.** It has an id, a
  method, a result and an error, and every assistant and every editor
  already knows it.
- **One object per line, because the pipe is a pipe.** A stream of
  length-prefixed frames is a framing protocol; a stream of lines is a
  convention that every tool of the world already knows.
- **A session, because one call is not enough.** The value of a session
  is the state: a name defined by one call is visible to the next. The
  REPL of the language already keeps that state, and the protocol keeps
  it too.
- **The value comes back as a value, not as text.** The caller asks for
  a number and gets a number. The text of the value is there as well,
  because a human reads the text, but the structure is the answer.

## The errors

The language has two error channels (invariant I2): the static errors
that cannot be caught, and the runtime errors that can. The protocol
keeps that split:

- a static failure is a JSON-RPC error with the kind of the failure
  (`lex`, `parse`, `type`), the message, the line and the column;
- a runtime failure is a JSON-RPC error with the kind `runtime` and the
  same fields.

The code of the error is the same for both (`-32000`), because the
distinction that matters to the caller is in the data, not in the code.

## The rules

- The protocol never changes the language. It is a surface over the
  same front end, the same checker and the same machine.
- The session is the session of the REPL: the same scope, the same
  builtins, the same errors.
- Every answer is a value, and every failure is a value too.
- The protocol is documented, and its examples are tested like every
  other example of the language.

## The acceptance criteria

1. `bun repl --json` starts a session that speaks the protocol.
2. A value comes back as a value: `eval` of `1 + 1` gives the number
   `2`, not the text `"2"`.
3. The session keeps its state: a name defined by one call is there for
   the next one.
4. A failure is a JSON-RPC error with the kind, the message, the line
   and the column.
5. `shutdown` ends the session with the status `0`.
6. A malformed line is answered with the parse error of the protocol,
   and the session survives it.
7. The protocol is tested: the tests drive it over a pipe and compare
   the answers.
