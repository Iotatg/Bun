# `bun:sutra` — one subject for every subject

SUTRA is a small, testable claim about how problems are solved, plus the Bun
code that makes the claim executable.

> A problem is hard because of vocabulary, not structure. Strip the vocabulary
> and what is left is a **shape**: how the answer moves when the input moves.
> Almost every law in every subject has one of three shapes. Identify the shape
> and you know the behaviour, the units, the limits and the failure modes before
> you solve anything.

The library does three things:

1. **reverses** an unknown law into a shape (`classify`, `skeleton`),
2. **certifies** an answer with four independent checks (`certificate`),
3. **groups** laws from different subjects that share a skeleton (`groups`).

Nothing is asserted. `classify` measures; `certificate` fails loudly.

---

## 1. The three shapes

| shape | defining property | what it means |
|-------|-------------------|---------------|
| `power` | `f(Lx) / f(x) = L^k` | a constant *relative* change; doubling the input multiplies the output by `2^k` |
| `exponential` | `f(x+d) / f(x) = r` | a constant *ratio* per step; equal steps multiply |
| `logarithmic` | `f(Lx) - f(x) = c` | a constant *absolute* gain; equal factors add |
| `constant` | `f(x)` does not move | the degenerate case |

A mixture is reported as `mixed` with `confident: false` — the classifier is
allowed to refuse.

`classify(f, x0, lam)` evaluates the function at `x0`, `lam*x0` and `lam^2*x0`
and tests the three properties. The parameter it returns means:

* `power` → the exponent `k`
* `exponential` → the rate per unit `x`
* `logarithmic` → the gain when the argument is multiplied by `lam`
* `constant` → the value

`skeleton(f, x0, lam)` returns the law as data: `shape`, `param`, `factor`
(and `offset` for logarithms), so `f` can be rebuilt elsewhere. The
reconstruction is tested at a *held-out* point, never at `x0`.

```bun
import { classify, skeleton, num } from "bun:sutra"

fn mystery(x) { return 3.0 * x * x * x }

let c = classify(mystery, 2.0, 4.0)
print(c["shape"], num(c["param"]))   // power 3
```

## 2. The seven moves

`moves()` returns the protocol. Each move removes one kind of confusion, and
you can stop as soon as the certificate passes.

| # | move | question it answers |
|---|------|---------------------|
| 1 | `name` | What exactly is unknown, and in what unit? |
| 2 | `shrink` | What is the smallest case you can compute by hand? |
| 3 | `change` | Which representation makes the structure visible? |
| 4 | `invariant` | What cannot change, whatever else changes? |
| 5 | `bound` | What are the two extreme cases? |
| 6 | `compose` | How is the whole built from the small case? |
| 7 | `check` | Does the answer survive four independent checks? |

## 3. The certificate

`certificate(problem)` runs four checks and returns
`{checks, passed, total, verdict}`. `verdict` is `CERTIFIED` only when all four
pass.

| check | what it catches | how it is computed |
|-------|-----------------|--------------------|
| `shape` | a wrong exponent or a wrong family | `classify` re-measures the function |
| `number` | an arithmetic error in the formula | the formula is evaluated at a probe point and compared with a value known by other means |
| `dimension` | a unit error | the formula's unit is built from a `dim_expr` tree and compared with the unknown's unit |
| `boundary` | a wrong limit or a wrong trend | the function is probed at `x0/scale` and `x0*scale` |

### Dimension algebra

Units are exponent vectors over `L, T, M, I, K, N, J, B`. Derived units are
expanded, so `N` and `kg*m/s^2` compare equal. Supported syntax:

```
m  s  kg  A  K  mol  cd  bit
N  J  W  Pa  C  V  ohm  Hz
"m/s^2"   "m^2/s"   "W/m^2"   "m^3*kg^-1*s^-2"
```

There are no parentheses: write `m^3*kg^-1*s^-2`, not `m^3/(kg*s^2)`.

`dim_eval` evaluates a small expression tree, so the dimension check is
computed rather than declared:

```bun
{"op": "pow", "n": 0.5,
 "a": {"op": "div", "a": {"op": "unit", "u": "m"},
                    "b": {"op": "unit", "u": "m/s^2"}}}
```

### Boundary behaviour

`edge_behavior(f, x0, scale)` probes at `x0/scale` and `x0*scale` and classifies
each end as `vanishes`, `finite` or `diverges`. The thresholds are
**exponent-based**, not absolute: a square root decays by only `1e-3` over six
decades and must still count as vanishing, while a constant must not. The
exponent at each end is returned as `k_zero` / `k_inf` for inspection.

`scale` defaults to `1e6` inside `certificate`; a problem may override it with
`edge_scale` to keep an exponential law inside the double range.

## 4. The catalogue

`catalog()` returns fourteen laws from six subjects. Each carries a real
formula, a value known by other means, a dimension expression, an edge claim
and the reason its shape had to be that shape.

| id | subject | law | shape |
|----|---------|-----|-------|
| `free-fall-time` | physics | `t = sqrt(2h/g)` | power 1/2 |
| `pendulum-period` | physics | `T = 2*pi*sqrt(L/g)` | power 1/2 |
| `random-walk-rms` | mathematics | `rms = sqrt(n)` | power 1/2 |
| `diffusion-distance` | chemistry | `x = sqrt(2Dt)` | power 1/2 |
| `gravity` | physics | `F = GMm/r^2` | power −2 |
| `coulomb` | physics | `F = kq1q2/r^2` | power −2 |
| `irradiance` | optics | `I = P/(4*pi*r^2)` | power −2 |
| `hooke` | physics | `F = kx` | power 1 |
| `ohm` | physics | `V = RI` | power 1 |
| `beer-lambert` | chemistry | `A = eps*l*c` | power 1 |
| `kepler-third-law` | astronomy | `T = 2*pi*sqrt(a^3/GM)` | power 3/2 |
| `binary-search` | computer science | `C = ceil(log2 n)` | logarithmic |
| `bacterial-growth` | biology | `N = N0*2^(t/tau)` | exponential |
| `harmonic-sum` | mathematics | `H(N) = ln N + gamma` | logarithmic |

## 5. Cross-subject groups

`groups(problems)` folds laws with the same skeleton into one entry. The
result is the evidence for the thesis:

```
power (0.5)     4 laws, 3 subjects   free fall, pendulum, random walk, diffusion
power (-2)      3 laws, 2 subjects   gravity, Coulomb, irradiance
power (1)       3 laws, 2 subjects   Hooke, Ohm, Beer-Lambert
logarithmic     2 laws, 2 subjects   binary search, harmonic sum
```

A logarithm's coefficient is a choice of base (`log2` vs `ln` differ by
`1/ln 2`), so `same_skeleton` treats every logarithm as the same law. Power and
exponential parameters are structural and must match.

## 6. Teaching

`ladder(p)` returns five rungs: guess, shape, smallest case, formula, reason.
`explain(p)` returns the question, the subject, the moves used and the ladder as
one string.

`curriculum()` returns six lessons. Each has an `idea`, a worked `example`, an
`exercise` and its `answer`, so the same text serves a person learning the
subject and a model being taught it.

```bun
import { catalog, explain } from "bun:sutra"
print(explain(catalog()[1]))
```

## 7. What this subject cannot do

This matters more than what it can do.

* **It is a filter, not a solver.** It tells you the shape and rejects wrong
  answers; it does not derive a new formula. The formula still has to come from
  somewhere — a small case, a symmetry, a known law.
* **Shape is necessary, not sufficient.** `x^2` and `2x^2` share a skeleton and
  differ by a constant the classifier cannot see. Constants carry physics.
* **Three shapes are not all shapes.** `sin`, Bessel functions, step functions
  and anything with a scale-dependent exponent come out as `mixed`. The
  classifier says so instead of guessing.
* **The checks are numerical.** They run in double precision at a few probe
  points. They catch structural errors, not 1e-15 drift, and a boundary claim
  is verified at a finite point, not in a limit.
* **Dimension checks only work if you supply the expression.** A wrong
  `dim_expr` certifies a wrong law.
* **It does not prove anything.** `CERTIFIED` means "four independent checks
  agree", not "true".
