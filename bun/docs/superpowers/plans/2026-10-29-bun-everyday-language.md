# The everyday language — the plan of Phases 26 to 28

Date: 2026-10-29
Design: `docs/superpowers/specs/2026-10-29-bun-everyday-language-design.md`
Research: `docs/superpowers/research/2026-10-29-bun-language-gap-notes.md`
Status: in progress

## The goal

The expressions of every day, the containers that answer, and the three
findings of the notes that answer a value that looks right.

## The acceptance criteria

1. The compound assignment, the increment, the decrement, the null
   coalescing and the `match` expression work under the tree, the stack
   VM, the register VM, the C backend and the self-hosted front end.
2. The containers answer `len`, `items`, `map`, `filter`, `reduce`,
   `find`, `any`, `all`, `each`, `sort` with a comparator and `sort_by`,
   and `print` takes many arguments.
3. The division answers a float, the whole quotient has its own operator,
   the addition of a string and a number is refused, and the caught error
   carries a code.
4. The golden corpus, the reference and the registry of the documentation
   tell the truth about all of it.
5. The tests of the repository pass.

## The shape of the work

| # | Item | What it is |
|---|------|------------|
| 1 | The tokens | The operators of the compound assignment, the signs, the null coalescing |
| 2 | The tree | The nodes of the new expressions |
| 3 | The parser | The statements and the expressions of the new forms |
| 4 | The checker | The mutability, the numbers, the types of the arms |
| 5 | The semantics | The operations of the runtime |
| 6 | The stack VM | The code of the new expressions |
| 7 | The register VM | The register code of the new expressions |
| 8 | The C backend | The C of the new expressions |
| 9 | The self-hosted front end | The same tree, the same errors, in Bun |
| 10 | The containers | The methods of the lists and the dicts, the length, the print |
| 11 | The divisions | The float division, the whole quotient |
| 12 | The errors | The code of a caught error |
| 13 | The corpus | The golden programs of the new forms |
| 14 | The docs | The reference, the registry, the README, the compatibility |

## The rules

- The Python front end is the reference of the shape of the tree; the
  self-hosted front end follows it.
- The golden corpus is the oracle of the behaviour.
- Every new refusal is written in the voice of the existing messages.
- A phase is one commit, and the tests of the phase run before it.

## The steps

### Phase 26 — the everyday expressions

| # | Step | The files |
|---|---|---|
| 26.1 | the tokens | `bun/tokens.py`, `bun/lexer.py` |
| 26.2 | the tree | `bun/ast.py` |
| 26.3 | the parser | `bun/parser.py` |
| 26.4 | the checker | `bun/checker.py` |
| 26.5 | the semantics | `bun/ops.py` |
| 26.6 | the stack VM | `bun/compiler.py` |
| 26.7 | the register VM | `bun/regcompile.py`, `bun/regcode.py`, `bun/regvm.py` |
| 26.8 | the C backend | `bun/cbackend.py`, `lib/bun/c_runtime.h` |
| 26.9 | the self-hosted front end | `selfhost/lexer.bun`, `selfhost/parser.bun`, `selfhost/checker.bun`, `selfhost/compiler.bun` |
| 26.10 | the corpus | `tests/golden/*.bun`, `tests/golden/*.out` |
| 26.11 | the tests | `tests/test_everyday.py` |
| 26.12 | the docs | `bun/docs.py`, `selfhost/docs.bun`, `README.md`, `docs/reference/compatibility.md` |

### Phase 27 — the containers speak

| # | Step | The files |
|---|---|---|
| 27.1 | the methods of the lists | `bun/methods.py` |
| 27.2 | the methods of the dicts | `bun/dict.py` |
| 27.3 | the length and the print | `bun/builtins.py` |
| 27.4 | the C runtime | `lib/bun/c_runtime.h`, `bun/cbackend.py` |
| 27.5 | the self-hosted front end | `selfhost/checker.bun` |
| 27.6 | the corpus and the tests | `tests/golden/containers.bun`, `tests/test_containers.py` |
| 27.7 | the docs | `bun/docs.py`, `selfhost/docs.bun`, `README.md` |

### Phase 28 — the divisions, the additions and the kinds

| # | Step | The files |
|---|---|---|
| 28.1 | the division | `bun/ops.py`, `bun/compiler.py`, `bun/regcompile.py`, `bun/cbackend.py` |
| 28.2 | the whole quotient | the same files, and the lexer and the parser for `//` |
| 28.3 | the addition | `bun/ops.py`, `bun/checker.py` |
| 28.4 | the kinds of the errors | `bun/ops.py`, `bun/values.py`, `bun/builtins.py` |
| 28.5 | the corpus | `tests/golden/arithmetic.bun`, `tests/golden/options.bun` |
| 28.6 | the tests | `tests/test_everyday.py` |
| 28.7 | the docs | the reference, the compatibility, the README |

## The check of the work

- `python3 -m pytest tests/test_everyday.py tests/test_containers.py -q`
  passes.
- `python3 -m pytest tests/test_golden.py tests/test_selfhost.py -q`
  passes.
- `python3 -m pytest tests -x -q` passes before the push.
