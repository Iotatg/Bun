# Raksha — safety in Bun's own words

`raksha` (रक्षा) means *protection*.  It is Bun's static memory-safety
analysis and the runtime ledger that backs it, added in 0.7.0.  The
executable forms of this document are `bun/raksha.py` (the pass),
`lib/bun/raksha.bun` (the Bun-written library), `tests/test_raksha.py`
and `tools/verify_raksha.py`.  This is the normative reference: the names,
the codes and the boundaries below are the contract.

---

## 0. The one rule

> **原理借用、语法未借用** — *the principle is borrowed, the syntax is not
> borrowed.* (R5 `own_grammar_not_a_copy`.)

The useful half of Rust's ownership model — one owner, move semantics,
shared XOR exclusive borrowing, regions as sets of program points,
deterministic destruction, interior mutability, separated result/option
channels and labelled static diagnostics — is the **principle** Bun learned.

Rust's **syntax** is not used at all.  There is no `&`, no `'a`, no `mut`,
no `unsafe`, no `Box`, no `Drop` trait, no `Result<T,E>` and no lifetime
annotation.  `?` stays because it was already Bun's.  Every new word below
is a **module function name or a field name**, never a keyword: `keywords()`
in `lib/bun/identity.bun` is unchanged at 37 entries, the identity ledger
grew from 14 to 15 families and from 14 to 17 forms, and `audit()` still
runs exactly 15 falsifiable checks (`IDENTITY_LEDGER_CERTIFIED 15 / 15`).
That is why all 118 language packs can write a Raksha program on the day
the wave ships (R7).

---

## 1. Vocabulary (Bun's own words)

Every entry is a name of the `bun:raksha` module or of the
`bun/raksha.py` analysis — a function, a field or a record — never a
keyword.  The last column names only the Rust **principle** that was read;
the spelling is Bun's.

| Bun word | Meaning | Rust principle (principle only) |
|---|---|---|
| `raksha` रक्षा | the safety system and its static pass | borrow checker |
| `swatva` स्वत्व | ownership: a value has exactly one owner | ownership |
| `sanchay` संचय | transfer of ownership (a move) | move semantics |
| `udhaar` उधार | shared loan, read only | `&T` |
| `adhikar` अधिकार | exclusive loan, writable | `&mut T` |
| `padh` पढ़ | read through a loan | deref |
| `likh` लिख | write through an exclusive loan | deref mut |
| `visarjan` विसर्जन | release a value (drop) | `Drop` / drop glue |
| `kosh` कोष | interior-mutable cell, checked at run time | `RefCell` / `UnsafeCell` |
| `kaal` काल | the live region of a loan: a set of points | NLL region / lifetime |
| `bindu` बिंदु | one program point (flow, block, index) | MIR `Location` |
| `nidan` निदान | a labelled diagnostic | `Diagnostic` + labels |
| `chinh` चिन्ह | one text-bearing span inside a nidan | labelled span |
| `sthan` स्थान | a source position packed into one integer | `Span` in `u64` (reuses `antar.Sthan`) |
| `praman` प्रमाण | verification of the analysis itself | verifier |
| `parinam` परिणाम | result-channel helpers | `Result` |
| `vikalp` विकल्प | option helpers | `Option` |
| `niyam` नियम | the rule ledger | origin ledger's sister ledger |

`swatva`, `sanchay`, `udhaar`, `adhikar`, `padh`, `likh`, `visarjan`,
`kosh`, `kosh_padh`, `kosh_likh`, `parinam_map`, `parinam_chain`,
`parinam_or`, `vikalp_map`, `vikalp_or`, `niyam`, `codes`, `audit` and
`summary` are the exports of `lib/bun/raksha.bun`.  Its `niyam()` returns
≥ 12 rules, each declaring its `rust_seed` as *"principle borrowed, syntax
not borrowed"*, and its `audit()` certifies the ledger with real calls:
`RAKSHA_LEDGER_CERTIFIED`.

---

## 2. The Bun-written runtime library

`import "bun:raksha" as rk` resolves to `lib/bun/raksha.bun` through
`resolve_native`; the module is plain Bun dicts, lists and functions, so
tree, vm and register engines run it identically.  The dict shapes are
fixed:

```
owner = {"kind":"swatva", "id":<int>, "value":<any>, "sthiti":"live",
         "loans":[], "drop_log":[], "origin":"<string>"}
loan  = {"kind":"udhaar"|"adhikar", "id":<int>, "owner":<int>,
         "sthiti":"live", "reads":0, "writes":0}
cell  = {"kind":"kosh", "value":<any>, "active":<int>, "borrows":[]}
```

Runtime refusals are the second line of defence (R2 `refuse_dont_guess`):
`RAKSHA: moved value`, `RAKSHA: dropped value`, `RAKSHA: loan conflict`,
`RAKSHA: shared loan is read-only`, `RAKSHA: owner is loaned`,
`RAKSHA: double release`, `RAKSHA: cell conflict`.  What can be refused
statically is refused statically (R3).

---

## 3. The static pass (`bun/raksha.py`)

`bun raksha` never runs the program.  It parses, type-checks, then lowers
each function to a **memory flow** (`PravahR`): `points` of `Bindu`,
`edges`, `owners` of `Swatva`, `loans` of `Udhaar` and `drops`.  It computes
predecessors, reverse postorder, dominators and natural loops (back edge
`n → h` where `h` dominates `n`), and reports `loops` in the stats.

### 3.1 What it recognises

Only these shapes are recognised; anything else is refused **by name**
(`Unsupported("raksha", "<a named statement>", node)`, message containing
the construct name).  A program without `import "bun:raksha" as <alias>`
yields an empty analysis: 0 diagnostics, `ok == true`, no exception.

- `<alias>.swatva(...)`, `sanchay(x)`, `udhaar(x)`, `adhikar(x)`,
  `padh(l)`, `likh(l, v)`, `visarjan(x)`;
- `with <alias>.swatva(v) as name { ... }` → an automatic cleanup drop at
  the `with` exit;
- `try/finally` and `on leave` (already lowered by the parser to
  `TryStmt(finally_body=...)`) → cleanup drops;
- `spawn` / `scope` loans (RK13), escaped loans (RK08), discarded
  `Ok(...)`/`Err(...)` (RK10), unchecked `some`/`none` (RK11),
  leaked owners (RK09), and the names `unsafe`, `raw_pointer`,
  `deref_raw`, `ffi_load` (RK12).

### 3.2 `kaal` — a region is a set of points, not a scope

This is the NLL idea expressed in Bun's words.  For each loan, the pass
walks the CFG forward from its `issued` `bindu` along `edges` (including
back edges) and collects the `Bindu.key()` triples until `last_use`.  The
result, `Udhaar.region`, is a **set of program points**:

- a loan ends at its last use, not at the closing brace of the block
  that textually contains it (non-lexical);
- a loan issued in a loop has a `kaal` that covers the whole loop body,
  because the back edge is part of the reachable set;
- two loans whose `region` sets intersect, where at least one is
  `adhikar`, are a conflict (RK03) — the aliasing XOR mutability rule,
  checked on sets of points rather than on lexical scopes;
- drops in one scope must be in reverse declaration order (RK14), the
  same reverse-order destruction the principle asks for;
- `sthan` packs a position into one integer (`antar.Sthan`), and `nidan`
  quotes a primary span plus ≥ 1 `chinh` label, a hint and ≥ 1 note.

`verify()` checks the analysis itself: every owner has exactly one final
state (moved/dropped/transferred), every loan has a non-empty region,
every drop names an existing owner, cleanup edges exist, every diagnostic
code is in `CODES`, and no region contains a point after an exit.

### 3.3 What a nidan looks like

```
raksha[RK03]: loan conflict
  --> demo.bun:4:9
   |
 3 |   let a = rk.swatva(1)
   |           --------- swatva yahan bana
 4 |   let x = rk.adhikar(a)
   |           ^^^^^^^^^^^^^ adhikar yahan jaari
 5 |   let y = rk.udhaar(a)
   |           ---------- kaal overlap karta hai
   |
   = nidan: ek samay mein ek adhikar ya anek udhaar
   = sulabh: kaal chhota karo, ya udhaar pehle khatam karo
```

The structure is Bun's: primary `sthan`, labelled `chinh`, `nidan` notes,
`sulabh` hint.  It reads like a compiler diagnostic because that is the
useful shape, not because the wording or the grammar was copied.

### 3.4 The 14 error codes

`CODES` in `bun/raksha.py` and `codes()` in `lib/bun/raksha.bun` are
one-to-one.  Every code has a `name`, a `message` and a `hint`.

| code | name | Trigger |
|---|---|---|
| `RK01` | `use_after_sanchay` | use of an owner after it was moved |
| `RK02` | `double_sanchay` | moving an owner that was already moved |
| `RK03` | `loan_conflict` | an `adhikar` region intersects any other loan's region |
| `RK04` | `write_through_shared` | `likh` applied to an `udhaar` |
| `RK05` | `move_while_loaned` | moving/releasing an owner with a live loan |
| `RK06` | `use_after_visarjan` | use of an owner after its release |
| `RK07` | `double_visarjan` | releasing the same owner twice |
| `RK08` | `loan_escape` | a loan returned or stored in a container |
| `RK09` | `owner_leak` | an owner still `live` at the end of a function |
| `RK10` | `unhandled_parinam` | a result value discarded as an expression statement |
| `RK11` | `unchecked_vikalp` | an option read without an `is_some` check |
| `RK12` | `unsafe_refused` | `unsafe` / raw-pointer names refused by name |
| `RK13` | `spawn_loan` | a loan crossing into a `spawn` task |
| `RK14` | `drop_order` | destruction order is not the reverse of declaration |

---

## 4. `with` is Bun's RAII, not Rust's

`swatva(value)` returns an owner dict that carries two function fields:

```
"__enter__": fn() { return owner },
"__exit__":  fn(err) { visarjan(owner); return false }
```

So the `with` statement **Bun already had** becomes deterministic
destruction, with no new statement, keyword, trait or opcode:

```bun
import "bun:raksha" as rk

with rk.swatva([1, 2, 3]) as a {
    let l = rk.udhaar(a)
    print(rk.padh(l))
}   // normal exit OR a throw calls __exit__ -> rk.visarjan(a)
```

`__exit__` receives `err`: `null` on a normal exit, the error text on an
exceptional one.  That is Bun's spelling of Rust's `is_cleanup` path —
the drop that runs while unwinding — **but the syntax is completely not
Rust**: there is no `Drop` trait to implement, no `drop` keyword, no
`impl`, and no destructor declaration.  The value is an ordinary dict and
the protocol is two ordinary function fields.

The static pass inserts a **cleanup drop point** at the `with` exit and a
**cleanup edge** in the CFG for the exit path (the same shape `antar` uses
for `is_cleanup`).  `on leave { rk.visarjan(a) }` is the explicit cleanup
spelling; the parser lowers it to `try/finally`, so every engine already
has the semantics.  Reverse declaration order is enforced by RK14 and by
`verify()`.

---

## 5. Comparison with Rust: **原理借用、语法未借用**

| Rust | Principle borrowed | Bun word / form | Syntax **not** borrowed |
|---|---|---|---|
| ownership | one value, one owner | `swatva` | an owner is a dict, not a type-system mode |
| move semantics | transfer invalidates the old binding | `sanchay` | a function call, no move checker keyword |
| `&T` / `&mut T` | shared read XOR exclusive write | `udhaar` / `adhikar` | no `&`, no `mut`; loans are dicts |
| deref / deref mut | read / write through a loan | `padh` / `likh` | no `*` operator |
| `Drop`, drop glue | deterministic destruction | `visarjan` | no trait, no `drop` keyword |
| unwind drop / `is_cleanup` | cleanup on the exceptional path | `with ... __exit__(err)` | `with` already existed in Bun |
| `RefCell<T>` / `UnsafeCell` | run-time-checked interior mutability | `kosh` | a dict with `borrows`, no `unsafe` |
| NLL region / lifetime | a region is a set of program points ending at the last use | `kaal` over `bindu` | no `'a`, no annotations, no `'static` |
| MIR `Location` | a point is (flow, block, index) | `bindu` | Bun's own `PravahR` memory flow |
| `Span` in `u64` | compact source position | `sthan` | reuses `antar.Sthan` |
| `Diagnostic` + labels | primary span, labelled spans, notes, hint | `nidan` + `chinh` | Bun's words, Bun's layout |
| `Result<T,E>` / `Option<T>` | separated error / absence channels | `parinam_*` / `vikalp_*`, Bun's `Ok`/`Err`/`some`/`none`/`?` | no generics, no `unwrap` family |
| `unsafe`, raw pointers | unchecked aliasing must be refused | RK12 refuses those **names** | no `unsafe` block exists |

**原理借用、语法未借用**: every row borrows the principle in column 2 and
refuses the spelling in column 4.  The 0.7.0 identity ledger records this
as one `bun` family (`safety`, held to `R5`) and three canonical forms —
`with rk.swatva(v) as a { ... }`, `on leave { rk.visarjan(a) }` and
`import "bun:raksha" as rk` — while `keywords()` stays byte-for-byte
unchanged.

---

## 6. `bun raksha` — five flags

```
bun raksha <file.bun> [--json|--dot|--verify|--stats|--explain]
```

The command parses and type-checks with `_parse_program`, runs
`analyze_program(program, path)` and `verify(raksha)`.  It never executes
the program.  **Exit status is 1** when there is any nidan or when
`check.ok` is false; 0 otherwise.  No file argument gives status 2.

| Flag | Output |
|---|---|
| *(none)* | `render_text(raksha)` — the memory-flow report |
| `--json` | `render_json(raksha)` — stats, regions, diagnostics and the check |
| `--dot` | `render_dot(raksha)` — Graphviz of the memory flow |
| `--stats` | `json.dumps(check.stats, indent=2, sort_keys=True)` |
| `--verify` | `RAKSHA: OK (<n> pravah, <n> bindu, <n> swatva, <n> udhaar, <n> visarjan, <n> nidan)`; on failure each problem and each nidan is printed as `RAKSHA: ...` |
| `--explain` | `render_explain(raksha, source)` — the annotated source explanation |

## 7. `bun check --raksha`

```
bun check --raksha <file.bun>
bun check --raksha --json <file.bun>
```

`--raksha` is registered in `toolchain.SPECIAL["check"]`, so the command is
routed to the toolchain and then to the same checker `bun check` uses.
After the type check succeeds, `analyze_program` runs and every nidan is
converted into the ordinary diagnostic shape — `file`, `severity`, `kind`
(`raksha`), `code`, `hint`, `message`, `line`, `col` — so editors consume it
exactly as they consume a `type`, `syntax` or `lex` error.  `--json` uses
`canonical_dump` with `{"ok": ..., "diagnostics": [...]}`.

**`bun check` without `--raksha` is completely unchanged**, including its
JSON output (`{"ok": true, "diagnostics": []}` for a clean file) and its
exit status.

---

## 8. Boundary: `antar` refuses `with`, Raksha does not

`bun antar` lowers a program for the antar machine, which does **not**
implement `with`; it refuses the statement **by name** with
`Unsupported("antar", ...)` (R2).  Raksha does **not** refuse `with` — it is
the construct the cleanup edge is built on, and §4 is the protocol that
makes it deterministic.  The two commands answer different questions: one
asks "can this graph machine run it?", the other asks "is this program's
memory use safe?".

The boundary is recorded, not hidden:

- `tools/maturity/raksha_core.bun` deliberately uses **no `with`** so
  `tree`, `vm`, `register` and `antar` stay byte-identical on one program;
- `examples/raksha.bun` and `examples/raksha_hi.bun` do use `with` (the
  latter with `#!lang hi`) and must print identical output ending in
  `RAKSHA LEDGER CERTIFIED`;
- running a `with` program with `--engine antar` is still refused by
  antar at run time; the static analysis never claimed otherwise.

---

## 8b. `anumati` — a named, auditable exception

A demonstration program sometimes needs to do the very thing the analysis
forbids — for example `examples/raksha.bun` deliberately moves an owner and
then calls `rk.udhaar` on it inside `try`/`catch` to show the runtime
library's named refusal.  Suppressing that nidan with a global flag would
hide real bugs, so Bun uses a **one-line, one-code permission written as an
ordinary comment**:

```bun
// raksha:allow RK01: demo deliberately moves source and catches the runtime refusal
rk.udhaar(source)
```

`anumati` (अनुमति, "permission") is a comment, not an attribute, not a
keyword and not Rust's `#[allow(...)]`.  No new syntax was added and no
language pack had to change.  Its rules are deliberately narrow:

| Rule | Enforcement |
|---|---|
| The pragma names exactly one `RKxx` code and a non-empty reason | `verify()` refuses an unknown code or an empty reason |
| It applies only to the immediately following source line | matched against `nidan.primary.line` |
| It permits only the named code on that line | other codes stay visible |
| It must actually suppress something | `verify()` reports `anumati ... suppressed nothing` |
| Every suppressed nidan is recorded, not deleted | `Raksha.allowed`, `render_json().allowed`, `render_text()` and `--explain` all list it with its reason |

`bun raksha examples/raksha.bun --json` therefore reports
`"diagnostics": []` together with one `allowances` entry whose `used` is
`2`, and two `allowed` nidan.  The exception is visible in every renderer.
`tools/verify_raksha.py` checks both that the anumati was really used and
that a stale pragma (one permitting nothing) is refused.  This is the same
"make the escape hatch explicit and auditable" principle as an `unsafe`
block, expressed entirely in Bun's own vocabulary.

---

## 9. Reproducible commands

Every number in the 0.7.0 receipts comes from one of these commands, run
from the repository root:

```bash
python3 -m bun version --short                     # 0.7.0
python3 -m bun raksha examples/raksha.bun
python3 -m bun raksha examples/raksha.bun --json
python3 -m bun raksha examples/raksha.bun --dot
python3 -m bun raksha examples/raksha.bun --stats
python3 -m bun raksha examples/raksha.bun --verify
python3 -m bun raksha examples/raksha.bun --explain
python3 -m bun check --raksha examples/raksha.bun
python3 -m bun check --raksha --json examples/raksha.bun
python3 -m bun examples/raksha.bun                 # RAKSHA LEDGER CERTIFIED
python3 -m bun tools/identity_lab.bun             # IDENTITY_LEDGER_CERTIFIED 15 / 15

python3 -m pytest -q
python3.11 tools/maturity_probe.py                 # MATURITY: 100/100
python3.11 tools/verify_raksha.py                  # RAKSHA_WAVE_VERIFIED
bun doctor                                        # 6/6
bun engines                                       # 7 engines available
```

Receipts are written to `/workspace/`:
`BUN_0_7_0_PYTEST.txt`, `BUN_0_7_0_MATURITY.txt`,
`BUN_0_7_0_VERIFY.txt`, `BUN_0_7_0_RELEASE.md` and
`BUN_0_7_0_REA_EVIDENCE.md`.  A claim that is not measured by one of
these commands is not made here: a static pass, a ledger and a verifier
are evidence, not a proof of safety in general.
