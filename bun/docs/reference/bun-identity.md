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

`bun:identity` → `families()` records 15 families. This is the honest count,
not a score to be proud of:

| Origin | Families | Meaning |
|--------|----------|---------|
| `bun` | 7 | Bun's own answer: literals (one `null`), the error channels, structured concurrency, language packs, the multi-engine oracle, the queryable diagnostic surface, and the 0.7.0 safety pass (`safety`). |
| `borrowed` | 7 | Bindings, functions, control flow, modules, data types, patterns, resources. Each names the languages it came from and the reason it was kept. |
| `shared` | 1 | Operators — the shared alphabet of arithmetic. |

`bun:identity` → `keywords()` maps **all 37 keywords** (33 hard keywords
from `bun/lexer.py` plus the 4 soft keywords from `bun/langpacks.py`) to one
of those families. The 0.7.0 wave added a family and three forms without
touching this table: every new safety word is a module function name, not a
keyword. `forms()` records 17 sentence shapes with an origin, a reason, a
rule and a status (`canonical`, `compatibility`, `rejected`); 14 are
canonical, 1 is compatibility and 2 are rejected.

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

### 4.1 The front end reads its own language

R7 says a new form must be writable in the reader's own language. That is
only half true if the front end written in Bun cannot read those programs.
Until this change, `--front-end bun` treated `#lang: hi` as a comment and
then reported `undefined variable 'आयात'` for the Hindi word for `import`.
A Bun front end that cannot read Bun's own language packs is a copy-shaped
gap in the self-hosting claim, so it is now closed.

`selfhost/lexer.bun` owns the whole word logic: hard aliases keep their own
spelling in the token value but take the English keyword's type, soft
keywords become an `IDENT` carrying the English name, and a keyword glued
to a name in a script without spaces (Chinese, Japanese, Thai and friends)
is peeled off longest-first. Without a `#lang:` directive no word is ever
split, so a CJK identifier stays one name. `selfhost/main.bun` passes the
pack to `tokenize_lang()`; the older `tokenize()` remains the plain-English
entry point used by the parser and checker for source fragments.

**Where the data comes from.** `bun/lexer.py` → `Lexer.lang_aliases()` hands
the Bun lexer the exact hard/soft/split tables that the Python lexer built
for that file. This is one source of truth, so the two front ends cannot
drift. It is also a real boundary: the host still owns the language-pack
data, just as it owns module resolution (`module_path`, `read_module`).
The grammar and the splitting rules are Bun code; the dictionary is not.
Self-hosting here means *both front ends read one grammar*, not that the
language packs have been reimplemented in Bun.

**Known boundary, recorded rather than hidden.** The directive (or the
CLI `--lang` flag, which now reaches both front ends) selects a pack for
the program being run. A *module* that carries its own `#lang:` directive
is still read as plain English by the Bun-written checker's module pass
(`selfhost/checker.bun` tokenizes imported sources with `tokenize()`),
while the Python checker's `modules.load_module_source()` detects it.
So the two front ends agree on the entry program, not yet on a per-module
pack. That is a separate gap and is not claimed as closed here.

`tests/test_selfhost_langpacks.py` holds the contract: twelve programs
(Hindi with a soft keyword, Chinese glued and spaced, Japanese, Thai,
French, Hinglish, plain English, no directive, unknown directive) each
compared for tokens, AST, bytecode, static errors and actual execution on
both front ends. `examples/identity_hi.bun` is also in the shared corpus,
so the general parity suite guards it too.

### 4.2 The four language-core forms of 0.4.0

The 0.4.0 wave had to close four capabilities that the maturity ledger
measured: a scope-exit action, nested type arguments, a function type as a
parameter, and a labelled `break`.  A capability is not a spelling, so each
one was written in Bun's own grammar rather than imported with its
neighbouring language's punctuation:

| Capability | Bun form | Origin | Why it is Bun's |
|---|---|---|---|
| scope-exit action | `on leave { ... }` | bun | A soft keyword pair; lowered to the `try`/`finally` the language already has, so all engines share one semantics and no opcode was added. |
| nested type argument | `list of list of int`, `dict of string to int` | bun | The type reads as the sentence it describes; `of` and `to` are only type words, so they stay ordinary names in expressions. |
| function type | `fn(int) -> int` | borrowed (Rust, TypeScript) | The arrow is the common spelling; Bun keeps its own `fn` and checks the whole signature, including the types inside it, before the run. |
| named loop | `for i in range(3) as outer { ... }` | bun | The name lives in the loop header and uses `as`, a word every pack already translates. `outer: for` remains as compatibility. |

`bun originality` prints the lexical audit behind this table: the keywords
Bun shares with Python, JavaScript, Go, Rust, C and Java, the one keyword no
compared language has (`protocol`), and the constructs Bun spells in its own
way.  The command states its own limit in the output: a keyword is a word,
not a grammar, so the overlap can neither prove nor disprove a copy.

### 4.3 The 0.7.0 safety forms

The Raksha wave adds **one family** and **three forms**, and adds **no
keyword**. The family is `safety`, held to R5 (`own_grammar_not_a_copy`):
its reason is that memory safety is expressed with the `with` and `on leave`
statements Bun already has plus universal `bun:raksha` module names, so no
language pack needs a new translation. The three forms are:

| Form | Origin | Rule | Why it is Bun's |
|---|---|---|---|
| `with rk.swatva(v) as a { ... }` | bun | R5 | The existing `with` calls `__enter__`/`__exit__`; `swatva` returns an owner dict carrying both. No `Drop` trait, no new statement. |
| `on leave { rk.visarjan(a) }` | bun | R5 | The existing scope-exit block (already lowered to `try`/`finally`) is the explicit cleanup spelling; the pass reads it as a cleanup drop point. |
| `import "bun:raksha" as rk` | bun | R5 | Only `import` and `as` appear, both translated by all 118 packs; `rk.swatva` and friends are function names, not keywords. |

`keywords()` is unchanged (37 entries), `audit()` still runs exactly 15
falsifiable checks, and the current result is
`IDENTITY_LEDGER_CERTIFIED 15 / 15` on tree, vm, register and
register+tier. The safety wave is a case of §5 step 1 with **no** step 3:
no keyword form was introduced, so no new translation had to ship. The
normative reference is `docs/reference/raksha.md`.

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

- It does not claim Bun is 100% original. Seven of fifteen families are
  borrowed and are named as such.
- It does not claim the borrowed surface has been removed. It has been
  attributed and is no longer being extended.
- It does not claim a performance figure, a completeness percentage, or a
  proof about any mathematical conjecture.
- It does not change the semantics of any existing program except the
  module-binding spelling described in section 4, which was one commit old
  when it was corrected.
- It does not claim the language packs are self-hosted. The Bun front end
  reads them using tables supplied by the host (section 4.1); the pack
  dictionaries themselves still live in `bun/langpacks.py`.
- It does not claim per-module language packs work on the Bun front end.
  Only the entry program's directive or `--lang` flag is honoured there
  (section 4.1).
