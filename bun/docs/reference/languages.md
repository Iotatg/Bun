# Writing Bun in 118 languages, and calling 23 others

Two separate features, often confused:

- **Language packs** — the *keywords of Bun itself* in another human
  language. `let` becomes `मानी`, `if` becomes `अगर`, `struct` becomes
  `संरचना`. The program is still Bun, compiled by the same engines.
- **Polyglot interop** — Bun code *calling another programming
  language* (`run_language("python", ...)`) and reading its answer back.

## 1. Language packs

```bash
bun langs                 # the list, 118 packs
bun langs --json          # the same, machine readable
bun --lang hi  program.bun
bun --lang auto program.bun
```

A program can also declare its language on the first line:

```bun
#lang: hi
मानी नाम = "दुनिया"
print("नमस्ते " + नाम)
```

```bun
#lang: zh
让 名字 = "世界"
print("你好 " + 名字)
```

The pack translates **keywords only**. The builtins (`print`, `len`,
`run_language`) keep their English names on purpose: a reader who knows
Bun can read a Hindi program, and a Hindi speaker can move to English
without relearning the library.

### Tiers

| Tier | Packs | Keywords |
|------|-------|----------|
| full | 45 | all 33, including `struct`/`enum`/`impl`/`protocol` |
| wide | ~50 | the 29 core keywords |
| core | ~23 | the 12 indispensable keywords |

A keyword that a pack does not translate simply stays English, so a
partial pack is always usable.

### How a keyword is translated

`bun/langpacks.py` holds `code → (name, "let=मानी if=अगर ...")`. The
parser accepts any identifier-clean word: letters of any script,
digits, underscores, and combining marks (`Mn`, `Mc`, `Me`) so that
Devanagari matras and Arabic harakat stay attached to their base letter.
One localized word may mean only one thing inside a pack; a collision is
resolved in favour of the earlier slot, never silently.

### Detection

`--lang auto` counts the distinct localized keywords it sees and picks
the pack with the most hits (three by default). It is a heuristic, and
the `#lang:` directive always wins.

## 2. Polyglot interop

```bun
let answer = run_language("python", "print(6 * 7)")
print(answer["stdout"])        // 42
print(answer["ok"])            // true

print(installed_languages())   // what this machine can run
```

`run_language(language, code, args?, timeout?)` returns a dictionary:

| key | meaning |
|-----|---------|
| `ok` | the program exited with status 0 |
| `status` | the exit status |
| `stdout`, `stderr` | what the program wrote |
| `build_failed` | the compiler refused the source |
| `seconds` | wall time |

An unknown language is not an exception: `ok` is `false` and `stderr`
explains which languages are installed.

### The 23 languages

Interpreted: python, javascript, bash, sh, ruby, perl, php, lua, tcl, r,
elixir, dart, julia, haskell, awk, sed.

Compiled: c, cpp, rust, go, java, fortran, zig. These are built once and
cached by the SHA-256 of the source under `/tmp/bun-polyglot/`, so the
second call pays only the run.

### The Bun-native stack

```bun
import { python, javascript, languages, can } from "bun:polyglot"

print(python("print(2 ** 10)"))
print(javascript("console.log([1,2,3].map(x => x * 2))"))
```

## 3. Reverse engineering any binary

`bun reverse` and the `bun:rea` stack put [REA](https://github.com/morluto/rea)
behind Bun: Ghidra does the analysis, Bun does the asking.

```bash
bun reverse ./program              # overview
bun reverse ./program calc         # decompile one procedure
```

```bun
import { overview, functions, decompile } from "bun:rea"

let look = overview("rust_app")
print(look["normalized_result.procedure_count"])

print(decompile("c_app", "calc"))
```

The language of the binary does not matter: ELF, PE, Mach-O; C, C++,
Rust, Go, Zig, or a stripped release build. The work is done by the
disassembler, not by a per-language parser, which is why the same three
lines work on a 16 KB C binary and a 3.9 MB Rust binary.

Measured on the demo binaries in `examples/reverse/`:

| binary | size | procedures | strings |
|--------|------|-----------|---------|
| c_app | 16 KB | 24 | 73 |
| rust_app | 3.9 MB | 679 | 1427 |
| go_app | 1.8 MB | 1500 | 5534 |

The C backend refuses `run_language`/`installed_languages` with a clear
message instead of failing at link time: a program that needs a host
interpreter must run on an interpreter engine.
