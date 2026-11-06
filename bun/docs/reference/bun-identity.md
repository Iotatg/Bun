# Bun in its own voice

Status: normative reference. The executable form of this document is
`lib/bun/identity.bun` (`bun:identity`), and `tests/test_bun_identity.py`
enforces it against the real lexer. `tools/identity_lab.bun` prints the
whole ledger; it is byte-identical on every engine.

## 1. The rule

> **A construct of another language is not taken because it is convenient
> there.** It is taken only when it fits the grammar of Bun, when the checker
> of Bun can hold it, when the errors of Bun can say it, and when the
> language would be poorer without it.

That sentence is not new. It is section 1 of
`docs/superpowers/specs/2026-10-29-bun-everyday-language-design.md`, and it
was already the rule of Phases 26–28. This document makes it the rule of
the whole language, gives it an id (**R5**), and makes it executable.

Bun did **not** invent everything, and this document does not claim it did.
Several families of its syntax are borrowed. What Bun refuses is the
*unexamined* copy: a construct that arrives with no attribution, no reason,
and no rule holding it in place.

## 2. The eight rules

These are the rules in `bun:identity` → `rules()`. Every family and every
form in the ledger names the rule it satisfies.

| Id | Rule | Where it comes from |
|----|------|---------------------|
| R1 | `one_rule_per_concept` — one semantics per concept, stated once; no unnamed exceptions. | Advanced design I1 |
| R2 | `refuse_dont_guess` — a construct the checker or a backend cannot hold is refused by name. | Everyday design §2 |
| R3 | `static_before_run` — anything refusable before the run is refused before the run, with line, column, reason and hint. | I2, I3 |
| R4 | `one_program_all_engines` — tree, vm, register, register+tier and both front ends must agree; the C backend either agrees or refuses by name (R2). | Everyday §2, I10 |
| R5 | `own_grammar_not_a_copy` — the rule quoted above. | Everyday §1 |
| R6 | `one_obvious_way` — one way to say a thing; a borrowed spelling is compatibility, never the definition. | I9, coherence rule 1 |
| R7 | `writable_in_any_language` — a new keyword form uses words the language packs can already translate, or ships translations with it. | `languages.md` |
| R8 | `runtime_is_the_spec` — the golden corpus and front-end parity define the language; a disagreement is a bug. | I5 |

The ten design invariants (I1–I10) and the seven coherence rules in
`docs/superpowers/specs/2026-10-19-bun-advanced-language-design.md` remain
in force. R1–R8 are the short list a new construct is checked against.

## 3. The origin ledger

`bun:identity` → `families()` records 14 families. This is the honest count,
not a score to be proud of:

| Origin | Families | Meaning |
|--------|----------|---------|
| `bun` | 6 | Bun's own answer: literals (one `null`), the error channels, structured concurrency, language packs, the multi-engine oracle, the queryable diagnostic surface. |
| `borrowed` | 7 | Bindings, functions, control flow, modules, data types, patterns, resources. Each names the languages it came from and the reason it was kept. |
| `shared` | 1 | Operators — the shared alphabet of arithmetic. |

`bun:identity` → `keywords()` maps **all 37 keywords** (33 hard keywords
from `bun/lexer.py` plus the 4 soft keywords from `bun/langpacks.py`) to one
of those families. `forms()` records 10 sentence shapes with an origin, a
reason, a rule and a status (`canonical`, `compatibility`, `rejected`).

`audit()` runs 15 falsifiable checks over these tables: complete
attribution, unique names, valid origins, borrowed entries naming their
source, Bun entries claiming none, every rule reference existing, the
canonical module form present, and the copied module form rejected. The
current result is `IDENTITY_LEDGER_CERTIFIED 15 / 15`.

**A ledger is not a proof of originality.** A family marked `borrowed` stays
borrowed no matter how many rules it satisfies.

## 4. What was done about one real copy

The first implementation of whole-module imports used the ECMAScript
spelling verbatim:

```bun
import * as ns from "./greeting.bun"     // ECMAScript, not Bun
```

That was a copy. It was replaced before release by Bun's own form:

```bun
import "./greeting.bun" as greet         // Bun

print(greet.hello("Bun") + greet.punctuation)
```

Why this reads like Bun:

- **The path comes first.** A module path in Bun is always a string that
  names a file (`compatibility.md` §9); it is not a name to be resolved, so
  it needs no `from` in front of it.
- **The local name follows, once.** There is no `{}` list, no `*`, and no
  third position for the path.
- **Only `import` and `as` appear.** Both are already translated by every
  one of the 118 language packs, so the form is writable in the reader's own
  language on the day it is introduced (R7). See
  `examples/identity_hi.bun`, which writes the whole ledger call in Hindi
  keywords and runs on every engine.
- **The copy is refused, not silently accepted.** The parser raises a
  `ParseError` saying `"'import * as ns from ...' is not Bun syntax; bind a
  whole module with import \"path\" as ns"`. Errors say what to do next.

`import { a, b } from "path"` remains. It is borrowed too, but it is used
by hundreds of existing programs, so it is recorded as `compatibility` and
is **not** extended: no new module syntax is modelled on it. Removing it
would be a breaking migration and is not done here.

See `README.md` → Modules and `compatibility.md` §9 for the user-facing
description; `tests/test_namespace_import.py` for the refusal test.

## 5. Adding a construct

A change that adds a keyword, a statement shape or an operator must:

1. Add an entry to `bun:identity` → `keywords()`, `families()` or `forms()`
   with `origin`, `from`, `reason`, `bun_rule` and `status`.
2. Name the Bun rule it satisfies. If none of R1–R8 fits, the construct
   does not belong in the language yet — the rule list must be argued
   first, not bent afterwards.
3. If it is a keyword form, satisfy R7: use words the packs already
   translate, or add translations to the packs in the same change.
4. Make it work on every engine, or have the C backend refuse it **by name**
   (R2, R4).
5. Add golden output and tests. The guard test
   `test_identity_ledger_covers_every_keyword` compares
   `bun:identity` → `keywords()` to the real `bun/lexer.py` tables; a new
   keyword without an entry fails the suite.

## 6. What is deliberately refused

`forms()` records these as `rejected`:

- `import * as ns from "path"` — ECMAScript (section 4).
- `class` / `None` / `undefined` / `unsafe` — Bun has `struct`/`impl`/
  `protocol`, one `null`, and a capability-bounded `ffi_load` allowlist (I8).

The compatibility document `compatibility.md` is a **bridge** for a reader
arriving from Python. It is not the definition of Bun, and it says so.

## 7. What this document does not claim

- It does not claim Bun is 100% original. Seven of fourteen families are
  borrowed and are named as such.
- It does not claim the borrowed surface has been removed. It has been
  attributed and is no longer being extended.
- It does not claim a performance figure, a completeness percentage, or a
  proof about any mathematical conjecture.
- It does not change the semantics of any existing program except the
  module-binding spelling described in section 4, which was one commit old
  when it was corrected.
