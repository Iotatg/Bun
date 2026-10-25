# Bun Language — Type-System Spine Design (Phases 17–21)

**Date:** 2026-10-25
**Status:** Approved
**Scope:** Close the type-system gap versus Rust without abandoning Bun's own rules.

This document is the normative specification for Phases 17–21. Every rule has a
golden-corpus test. Every engine (tree, stack VM, register VM, C backend) and
both front ends (Python, `selfhost/*.bun`) must agree byte-for-byte.

---

## 0. Decision table

| Phase | Surface | What it is | What it is not |
|-------|---------|------------|----------------|
| 17 | `struct` + `impl` + field access | Value types with methods | Classes, inheritance, `self` as a keyword outside methods |
| 18 | `protocol` | Structural interface, compile-time when types are known | Rust traits with associated types, coherence, orphan rules |
| 19 | Generics `<T>` + bounds | Monomorphised at known call sites | Boxed trait objects, const generics, GATs |
| 20 | `Result` + `?` | Dict protocol `{"ok":v}` / `{"err":e}` plus early return | Replacing exceptions; exceptions stay |
| 21 | `enum` + match extension | Tagged union, "a model is data" | Class patterns (still deferred) |

Out of this round (Phases 22+): move/borrow checker, `unsafe`, async, channels,
atomics, iterators protocol, formatter/linter/LSP, packaging, WASM/JIT.

---

## 1. Design rules (from Bun itself)

1. One semantic rule per concept, stated once.
2. Every rule has a test in `tests/golden/`.
3. Every deviation is a bug.
4. The tree-walker is the differential oracle. VM, register VM and C backend
   must produce identical bytes and identical errors.
5. The self-hosted front end (`selfhost/*.bun`) must reproduce the Python front
   end's output exactly.
6. The C backend refuses unsupported constructs **by name**.
7. Composition over inheritance. No `class`, no `extends`.
8. `let` is immutable; `var` is mutable. The checker already enforces this.
9. "A model is data": structs, enums and Results are plain values with a
   discriminant, not class instances.
10. Zero-config. No build step. No central registry.

---

## 2. Phase 17 — `struct` + `impl` + field access

### 2.1 Syntax

```bun
struct Point {
    var x: float
    var y: float
}

impl Point {
    fn new(x: float, y: float) -> Point {
        return Point(x, y)
    }
    fn norm(self) -> float {
        return (self.x * self.x + self.y * self.y)
    }
    fn bump(self, by: float) {
        self.x = self.x + by
    }
}

var p = Point(3.0, 4.0)
print(p.x)
print(p.norm())
p.bump(1.0)
```

Field declarations follow the `let`/`var` rule of the language: `var` fields
are writable, `let` fields are not. A field without `let`/`var` defaults to
`var`. Type annotations are optional (gradual typing). Default values are
allowed: `var x: float = 0.0`.

Constructor: `Point(3.0, 4.0)` is a call whose callee is the struct name.
Arguments are positional, in field-declaration order. Keyword arguments are
not supported in this phase.

### 2.2 Semantics

1. **Value type.** Assignment and argument passing **copy** a struct
   (recursive copy of nested structs; other values are shared as today).
2. **Method call borrows the receiver.** `p.bump(1.0)` passes `p` by
   reference, so mutations are visible on `p`. A plain function call
   `f(p)` copies.
3. **`self` is the first parameter** of an impl method. It is bound to the
   receiver. Its type is the impl's struct. `self` is not a keyword outside
   methods; using it as an identifier elsewhere is allowed.
4. **`let` bindings cannot be mutated through methods.** If a method assigns
   to `self.<field>`, the checker marks it mutating. A mutating method call
   on a `let` binding is an error. This reuses the existing `let`/`var`
   immutability rule; there is no `mutating` keyword.
5. **Field access** `p.x` is a new expression form (today `.` only parses a
   method call that requires `(`). Assignment `p.x = 1.0` is an
   `AssignStmt` whose target is an `Attribute`.
6. Unknown fields, unknown methods, and assigning to a `let` field are
   checker errors when the receiver's type is known; otherwise they are
   runtime errors.
7. Two structs with the same field names are distinct types.
8. `impl` may appear after the `struct` it names, including in a later
   statement of the same module. Multiple `impl` blocks for one struct
   merge. An `impl` for an unknown type is a checker error.
9. Static methods (no `self` parameter) are called as `Point.new(1.0, 2.0)`
   — a method call whose receiver is the struct type itself, represented as
   a type value. In this phase, the constructor `Point(...)` is the only
   static call form required; named static methods are called as
   `Point.new(...)` where `Point` in expression position evaluates to a
   type object.

### 2.3 AST

New nodes in `bun/ast.py`:

```
StructField  name, type_ann, mutable, default, line, col
StructDecl   name, fields, line, col
ImplDecl     type_name, methods (list of FnDecl), line, col
Attribute    object, name, line, col
```

`AssignStmt.target` may be an `Attribute`. `FnDecl` is reused for impl
methods; the first parameter named `self` is the receiver.

### 2.4 Lexer / tokens

New keywords in `bun/lexer.py` `KEYWORDS` and `bun/tokens.py` `TokenType`:

- `STRUCT = "STRUCT"`
- `IMPL = "IMPL"`

Mirrored in `selfhost/lexer.bun`.

`DOT` already exists. Parser change: after `.` + `IDENT`, if the next token
is `LPAREN` emit `MethodCall`; otherwise emit `Attribute`.

### 2.5 Parser

- `_statement` dispatches `STRUCT` → `_struct_decl`, `IMPL` → `_impl_decl`.
- `_struct_decl`: `struct Name { (let|var)? name (: type)? (= expr)? ,? }*`
- `_impl_decl`: `impl Name { fn ... }*`
- Postfix `.`: look ahead one token after the identifier.

### 2.6 Checker

- `_collect_functions` also collects `StructDecl` names into the scope as
  type `struct` (the type of the constructor) and records the field table
  on the checker (`self.structs[name] = fields`).
- `ImplDecl` methods are recorded in `self.impls[type_name][method] = FnDecl`.
  A method that contains an `AssignStmt` whose target is `self.<field>` is
  marked `mutating = True`.
- `Attribute` expression: if the object's type is a known struct, the field
  must exist; the expression's type is the field's `type_ann` or `any`.
- `AssignStmt` to an `Attribute`: the field must exist and be `mutable`;
  the object's binding, if it is an identifier, must itself be mutable.
- `MethodCall` on a known struct: look up the method in `self.impls`; check
  arity and argument types as for a function; if the method is mutating,
  the receiver binding must be mutable.
- Constructor call `Point(...)`: if the callee is a known struct name,
  check arity against field count and argument types against field types.

### 2.7 Runtime value

`bun/values.py`:

```
class BunStruct:
    type_name: str
    fields: dict          # name -> value
    field_order: list     # declaration order
```

`copy_struct(value)` recursively copies nested `BunStruct`s and returns a
new `BunStruct`. Other values are shared (Bun's existing sharing model).

`ops.type_name` reports the struct's `type_name` (not `"BunStruct"`).

`ops._resolve_method` grows a branch:

```
elif isinstance(receiver, BunStruct):
    table = STRUCT_METHODS.get(receiver.type_name, {})
    name = receiver.type_name
```

`STRUCT_METHODS` is a module-level dict `{type_name: {method: handler}}`
populated when an `impl` is executed. A handler is a `BunFunction` whose
first parameter is the receiver.

The dispatch cache key for structs is `(receiver.type_name, method)`, not
`(type(receiver), method)`, so distinct struct types do not collide.

### 2.8 Copying

Copy on:

- `DEFINE_NAME` / `STORE_NAME` of a `BunStruct`
- argument passing into a non-method call
- `return` of a `BunStruct`

Do **not** copy on:

- method-call receiver
- field read (`GET_FIELD` returns the field value as-is; nested structs
  are shared until assigned)

### 2.9 Stack opcodes

New opcodes, following the existing `(op, arg, line, col)` convention:

| Opcode | Arg | Stack effect |
|--------|-----|--------------|
| `MAKE_STRUCT` | `(type_name, field_names)` | pops `len(field_names)` values, pushes struct |
| `GET_FIELD` | `field_name` | pops object, pushes field |
| `SET_FIELD` | `field_name` | pops value, pops object, stores, pushes nothing |
| `REGISTER_IMPL` | `(type_name, method_name, code_object)` | records the method |

`OP_METHOD_CALL` is unchanged. The receiver of a method call is not copied.

`AssignStmt` whose target is `Attribute` compiles to: compile object,
compile value, `SET_FIELD`.

Constructor `Point(a, b)` compiles to: compile args in field order,
`MAKE_STRUCT ("Point", ["x", "y"])`.

### 2.10 Register IR (`bun/regcode.py`)

```
MAKE_STRUCT   ("slot", "pool", "count")   # dest, type_name, N fields
GET_FIELD     ("slot", "slot", "pool")    # dest, object, field_name
SET_FIELD     ("slot", "slot", "pool")    # object, value, field_name
REGISTER_IMPL ("pool", "pool", "pool")    # type, method, code (executed at load)
```

Verifier: pool indices in range; slots non-negative; `count` ≤ 64.

### 2.11 C backend + `c_runtime.h`

New tag `BUN_STRUCT`. `BunObj` reuses `name` (the type name), `keys` (field
names as interned strings), `values` (field values), `count`.

```
BunValue bun_struct_new(const char *type, const char **names, BunValue *vals, int n);
BunValue bun_get_field(BunValue obj, const char *name);
void     bun_set_field(BunValue obj, const char *name, BunValue value);
BunValue bun_copy_struct(BunValue obj);
```

Method dispatch in `bun_method_call`: if `tag == BUN_STRUCT`, look up
`(obj->name, method)` in a static table the emitter writes per `impl`.
Each impl method is emitted as a `BunFn`. The receiver is `args[0]`.

Copying: `bun_env_set` / argument binding copy a `BUN_STRUCT`. Method
dispatch does not.

Unsupported in this phase under the C backend: none of the new opcodes.
`REGISTER_IMPL` is a compile-time action of the emitter, not a runtime
opcode in C (the table is static).

### 2.12 Self-hosted front end

`selfhost/lexer.bun`: add `struct`, `impl` to the keyword table.
`selfhost/parser.bun`: `_struct_decl`, `_impl_decl`, attribute vs method
call on `.`.
`selfhost/checker.bun`: same rules as the Python checker, including
mutating-method-on-`let`.
`selfhost/compiler.bun`: emit `MAKE_STRUCT`, `GET_FIELD`, `SET_FIELD`,
`REGISTER_IMPL`.

Parity tests in `tests/test_selfhost.py` cover the new golden programs.

### 2.13 Tests

Golden corpus:

- `tests/golden/struct_basic.bun` — construct, field read, print
- `tests/golden/struct_method.bun` — impl method, `self` field read
- `tests/golden/struct_mutate.bun` — mutating method on `var`
- `tests/golden/struct_copy.bun` — assignment copies; mutation of copy
  does not affect original
- `tests/golden/struct_static.bun` — `Point.new(...)` if implemented;
  otherwise constructor only

Checker tests (`tests/test_struct.py`):

- mutating method on `let` → error
- unknown field → error
- assign to `let` field → error
- wrong constructor arity → error
- `impl` of unknown type → error

All four engines plus `--front-end bun` must agree.

### 2.14 Documentation

`bun/docs.py` entries for `struct`, `impl`, field access, constructor.
Regenerate `selfhost/docs.bun` with `python3 tools/gen_docs.py`.
README roadmap: Phase 17 DONE.

---

## 3. Phase 18 — `protocol`

```bun
protocol Shape {
    fn area(self) -> float
}

impl Circle {
    fn area(self) -> float { return 3.14159 * self.r * self.r }
}

fn show(s: Shape) {
    print(s.area())
}
```

A protocol is a set of method signatures. A value satisfies it if it has
every listed method. Satisfaction is structural (no `impl Shape for T`).

Checker: a parameter annotated `Shape` accepts any known struct whose
`impl` provides those methods, and `any`. At a call site with a known
struct type, missing methods are a compile-time error. At a call site
with `any`, the existing runtime `unknown method` error applies.

A protocol is not a value. Using a protocol name as an expression is a
checker error.

New AST: `ProtocolDecl` (name, methods: list of signatures). A signature
is a `FnDecl` with an empty body.

Lexer keyword: `protocol`.

No new opcodes. The checker is the whole feature. Runtime is unchanged.

Tests: a golden program that calls `show(Circle(1.0))`; a checker test
that `show(Point(1.0, 2.0))` fails if `Point` has no `area`.

---

## 4. Phase 19 — generics

```bun
fn identity<T>(value: T) -> T {
    return value
}

fn map<T, U>(xs: list<T>, f: fn(T) -> U) -> list<U> {
    var out = []
    for x in xs {
        out.push(f(x))
    }
    return out
}

fn sum<T: Num>(xs: list<T>) -> T {
    var total = 0
    for x in xs { total = total + x }
    return total
}
```

Type parameters live on `FnDecl` (`type_params: list[TypeParam]`) and,
later, on `StructDecl`. A `TypeParam` is `{name, bound}` where `bound` is
one of `Num`, `Ord`, `Eq`, `Hash`, `Show`, or none.

**Monomorphisation.** When a call site has known concrete type arguments
(from annotations or from the checker's inference of literals), the stack
compiler clones the function's `CodeObject` with the type parameters
substituted, names it `name__T1_T2`, and emits a call to the clone. The
C backend therefore sees a concrete function and can inline it.

When the type arguments are `any`, one shared instantiation is used
(dynamic, like today).

Bounds: `T: Num` means the concrete type must be `int` or `float`. `Ord`
means `int`, `float` or `string`. `Eq` means any type that `==` accepts.
`Hash` means `int`, `float`, `string`, `bool`. `Show` means anything
`str()` accepts (everything). A failed bound is a checker error.

No lifetime parameters. No const generics.

Tests: `identity(1)` prints `1`; `map([1, 2], fn(x) { return x * 2 })`
prints `[2, 4]`; `sum(["a"])` is a checker error (`string` is not `Num`).

---

## 5. Phase 20 — `Result` + `?`

`Result` is a dict protocol, consistent with "a model is data":

```
Ok(value)  => {"ok": value}
Err(error) => {"err": error}
```

Builtins `Ok` and `Err`. `is_ok(r)` / `is_err(r)` are functions, not
methods, so they do not collide with user methods.

The postfix operator `?`:

```bun
fn parse(s: string) -> any {
    let n = int_or_err(s)?
    return Ok(n * 2)
}
```

`expr?` evaluates `expr`. If the value has an `"ok"` key, the expression
yields that value. If it has an `"err"` key, the enclosing function
returns the Result unchanged. If it has neither, a runtime error.

Checker: `?` is only legal inside a function. (We do not yet require the
return type to be a Result, because Bun is gradual; a later phase may
tighten this.)

Lexer: `?` after an expression. Token: reuse `BANG` is wrong; add
`QUESTION = "QUESTION"` or parse `?` as a postfix in the parser from a
new token.

Stack opcode: `UNWRAP_OR_RETURN` (pops a Result, pushes the `ok` value
or returns the Result from the current function).

Tests: a successful `?` chain; an `Err` that propagates; `?` on a non-Result
is a runtime error.

---

## 6. Phase 21 — `enum` + match extension

```bun
enum Color { Red, Green, Blue }
enum Shape { Circle(float), Rect(float, float) }

let c = Color.Red
let s = Shape.Circle(2.0)

match s {
    Shape.Circle(r) => r * r,
    Shape.Rect(w, h) => w * h,
    _ => 0,
}
```

An enum value is a tagged dict: `{"kind": "Circle", "fields": [2.0]}`.
Variant construction `Shape.Circle(2.0)` is a call whose callee is an
attribute of the enum type object.

`match` already supports literal, wildcard, binding, type, range, list,
dict and or-patterns (`bun/patterns.py`). This phase adds:

- enum variant pattern `Shape.Circle(r)` — matches `kind == "Circle"` and
  unpacks `fields` into the bindings
- nested patterns
- `@binding` (`n @ Shape.Circle(_)`)

Class patterns remain deferred.

Lexer keyword: `enum`.

AST: `EnumDecl` (name, variants: list of `EnumVariant(name, types)`).

No new runtime type: an enum value is a dict. The checker knows the
enum's variants so `Color.Yellow` is a compile-time error.

Tests: construct, match a unit variant, match a tuple variant, unknown
variant is a checker error.

---

## 7. File map (Phase 17)

Touched files, in pipeline order:

| File | Change |
|------|--------|
| `bun/tokens.py` | `STRUCT`, `IMPL` |
| `bun/lexer.py` | keywords |
| `bun/ast.py` | `StructField`, `StructDecl`, `ImplDecl`, `Attribute` |
| `bun/parser.py` | `_struct_decl`, `_impl_decl`, attribute vs method |
| `bun/types.py` | `STRUCT = "struct"` in `TYPE_NAMES` |
| `bun/checker.py` | collect structs/impls, field/method/mutability rules |
| `bun/values.py` | `BunStruct`, `copy_struct` |
| `bun/ops.py` | `_resolve_method` branch, `type_name`, copy on bind |
| `bun/compiler.py` | `MAKE_STRUCT`, `GET_FIELD`, `SET_FIELD`, `REGISTER_IMPL` |
| `bun/interpreter.py` | tree-walker for new nodes |
| `bun/vm.py` | stack VM handlers |
| `bun/regcode.py` | opcodes + `OPERANDS` |
| `bun/regcompile.py` | registerizer |
| `bun/regverify.py` | verifier |
| `bun/regvm.py` | register VM handlers |
| `bun/cbackend.py` | C emission |
| `lib/bun/c_runtime.h` | `BUN_STRUCT`, helpers |
| `selfhost/lexer.bun` | keywords |
| `selfhost/parser.bun` | parse |
| `selfhost/checker.bun` | check |
| `selfhost/compiler.bun` | emit |
| `bun/docs.py` | entries |
| `selfhost/docs.bun` | regenerated |
| `tests/golden/struct_*.bun` | corpus |
| `tests/test_struct.py` | checker + engine tests |
| `README.md` | roadmap |

---

## 8. Verification contract

For every new golden program:

```
python3 -m bun --engine tree   tests/golden/struct_basic.bun
python3 -m bun --engine vm     tests/golden/struct_basic.bun
python3 -m bun --engine register tests/golden/struct_basic.bun
python3 -m bun --engine c      tests/golden/struct_basic.bun
python3 -m bun --front-end bun tests/golden/struct_basic.bun
```

All five print the same bytes as `tests/golden/struct_basic.out`.

`python3 -m bun test` includes the new files.
`python3 -m pytest tests/test_struct.py -v` is green.
`python3 -m pytest tests/test_selfhost.py -k struct -v` is green.

Existing 37 golden programs and the 1,453 pytest tests must still pass.
Startup-budget tests may remain environment-dependent.

---

## 9. Risks

| Risk | Mitigation |
|------|------------|
| Copy-on-assign vs method-borrow is easy to get wrong in the C backend | One golden program (`struct_copy.bun`) is the oracle; the C backend must match it |
| Dispatch-cache collision across struct types | Cache key includes `type_name` |
| Self-hosted front end lag | Parity tests; Python front end ships first, selfhost in the same phase |
| C backend `BunObj` field packing | Reuse `name`/`keys`/`values`; do not grow the struct in this phase |
| Gradual typing makes constructor arity the only hard check | Document; Phase 19 tightens this via generics |

---

## 10. What would make this fail

- Implementing structs as Python classes with inheritance. Rejected.
- Adding lifetime annotations. Rejected in this round.
- Making `self` a keyword. Rejected; it is an ordinary parameter name.
- Skipping the C backend or the self-hosted front end. The contract forbids it.
- Claiming "Rust-level memory safety" from this spine alone. Phases 17–21
  give types, not a borrow checker. That claim waits for Phase 22.
