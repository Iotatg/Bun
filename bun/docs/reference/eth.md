# `bun:eth` — the Exponential Time Hypothesis as a shape question

> **CORRECTION (2026-11-05).** The `alpha` invariant developed in sections 1–5
> below is **not** the invariant ETH is about. ETH is decided by
> `s(n) = log₂ T(n) / n`: `2^o(n)` ⟺ `s → 0`. For the runtime actually
> reported in October 2026, `exp(O(n/√log n))`, `alpha → 1` (this module says
> "exponential, ETH survives") while `s → 0` (ETH falls). See section 6 below
> and **`bun:pramana`** for the corrected, evidence-aware layer. Sections 1–5
> are kept because their measurements, DPLL solver and finite-data
> discrimination result remain valid; only the interpretation of `alpha` as an
> ETH decision rule was wrong.

ETH says 3SAT cannot be solved in `2^(o(n))` time. In SUTRA's language that is
not a claim about a number; it is a claim about a **shape**:

> ETH ⟺ the growth of 3SAT is not `power(k)` for any fixed `k`.

`bun:eth` turns that into something measurable, and then shows precisely where
measurement stops. `bun tools/eth_lab.bun` runs the whole analysis;
`examples/eth.bun` is the fast tour; `tests/test_eth.py` has 16 tests with
identical output on all four engines.

```bun
import { growth, synthetic, fit_compare, crossover } from "bun:eth"

let g = growth(synthetic([8.0, 16.0, 32.0, 64.0, 128.0],
                         "subexponential", 0.5))
print(g["kind"], g["alpha"])                 // subexponential 0.5
print(crossover(0.01, 0.5, 1.0))            // 10000
```

---

## 1. `alpha`, the exponent of the exponent

`classify` in `bun:sutra` works on a formula. A paper gives you a table. The
same idea applied to a table is the **local exponent**

```
k(n) = d log T / d log n
```

measured between neighbouring points, followed by the slope of `log k` against
`log n`. That slope is `alpha`:

| runtime | `k(n)` | `alpha` | world |
|---------|--------|---------|-------|
| `n^k` | constant | 0 | polynomial |
| `2^(n^a)` | `~ n^a` | `a` | subexponential, `0 < a < 1` |
| `2^(d·n)` | `~ d·n·ln2` | 1 | exponential |

`growth(points)` returns `{"kind", "alpha", "k_first", "k_last", "points"}`.
Thresholds: `alpha < 0.15` polynomial, `0.15–0.85` subexponential, `> 0.85`
exponential. On clean data it recovers 0, 0.5 and 1.0 exactly — the lab
calibrates the instrument before using it.

`worlds()` returns the three rows with their consequence for ETH. **Both**
polynomial and subexponential would refute ETH; an exponential with a smaller
base would not.

## 2. A real measurement, and why it cannot decide ETH

`solve_result(n, ratio, seed, budget)` runs a plain DPLL with unit propagation
on random 3SAT at the satisfiability threshold `m = 4.26n`, using xorshift32
with high bits only (a low-bit LCG produces correlated signs and quietly fakes
an easy instance). `brute_sat` is an exhaustive oracle; the solver agrees with
it on 25/25 small instances. `measure(ns, ratio, trials, budget)` averages node
counts over fixed seeds.

On the reachable window `n = 12 … 32`:

```
n = 12  nodes = 10      n = 24  nodes = 49.17
n = 16  nodes = 28      n = 28  nodes = 50.5
n = 20  nodes = 39.33   n = 32  nodes = 175
```

`fit_compare(points)` fits two models in log space — `ln T = a + k ln n` and
`ln T = b + d n` — and reports the RMS residual of each:

```
polynomial  k = 2.384  rms = 0.2965
exponential d = 0.168  rms = 0.2953
ratio = 1.004   -> UNDETERMINED
```

Both models fit equally well. `growth` reports an unstable `alpha` for the same
reason. **That is the numerical content of "ETH is a theorem, not an
experiment": with this window, no measurement can say which world the solver
lives in.** The data is also average-case over random instances, while ETH
quantifies over every instance.

On clean, wide synthetic data `fit_compare` is decisive
(`EXPONENTIAL_FITS_BETTER` / `POLYNOMIAL_FITS_BETTER`), which proves the
instrument works and the limitation belongs to the data, not the method.

## 3. When does a soft algorithm actually win?

`C · 2^√n < 2^(d·n)` first holds when `d·n − √n − log₂C ≥ 0`. `crossover`
finds that integer by exponential search and bisection; `crossover_rule(d)`
gives the closed form `n* = 1/d²` for `C = 1`.

| `d` | `n*` |
|-----|------|
| 0.1 | 100 |
| 0.05 | 400 |
| 0.01 | 10 000 |
| 0.005 | 40 000 |
| 0.001 | 1 000 000 |

With a 1000× constant factor and `d = 0.01`, the crossing moves to 11 910. A
one-percent asymptotic saving does not become a practical one until ten
thousand variables; a 0.1% saving waits until a million. This is the "no free
lunch" remark in the video, costed in variables.

## 4. Five checks, five verdicts

`certificate_growth(claim)` runs the four SUTRA checks plus a fifth one:

| check | question |
|-------|----------|
| `shape` | does the measured `alpha` place the runtime in the claimed world? |
| `number` | does the formula reproduce a value known by other means? |
| `dimension` | are all runtimes positive step counts? |
| `boundary` | finite at zero, divergent at infinity? |
| `quantifier` | is the claim about *this* algorithm, or about *all* algorithms? |

A claim that fails only `quantifier` gets `OUT_OF_REACH` — neither right nor
wrong, simply outside measurement. That verdict is the point of the module.

| claim | verdict | failed check |
|-------|---------|--------------|
| `checking all 2^n assignments grows exponentially` | `CERTIFIED` | — |
| `if 2^√n works for every instance, ETH is false` | `OUT_OF_REACH` | `quantifier` |
| `a 1% saving, 2^(0.99n), is subexponential and refutes ETH` | `REJECTED` | `shape` (still `alpha = 1`) |
| `2^√n is a polynomial-time algorithm` | `REJECTED` | `shape` (`alpha = 0.5`) |
| `3SAT is solvable in n² steps` | `REJECTED` | `number` (1024 vs 2³²) |

## 5. What SUTRA says about the video

The two paths in the video are both shape questions:

* **"Only slightly better than exponential."** Same shape (`alpha = 1`), smaller
  base. ETH is asymptotic, so this does **not** refute it. `REJECTED`.
* **"A genuine 2^(o(n)) algorithm."** `alpha < 1`. Mathematically this *would*
  refute ETH — provided the bound is proved for **all** instances and all
  algorithms, which is a theorem, not a run. `OUT_OF_REACH` for measurement;
  a Lean-checked proof is the only thing that settles it.

So the honest answer to "solve this with SUTRA" is: SUTRA measures the shape of
any stated runtime, rejects three plausible-but-wrong readings, computes when a
speedup would actually bite, and then draws the line at the universal
quantifier. It does not claim to have proved or disproved ETH.

## 6. API

| function | returns |
|----------|---------|
| `eth_statement()` | ETH as data, including why it is not measurable |
| `worlds()` | the three growth worlds and their ETH consequence |
| `local_exponents(points)`, `drift(ks)`, `growth(points)` | the alpha instrument |
| `synthetic(ns, kind, param)` | clean data for calibration |
| `linfit(xs, ys)`, `fit_compare(points)` | model comparison and `UNDETERMINED` |
| `solve_nodes`, `solve_result`, `brute_sat`, `measure`, `table_to_points` | the DPLL experiment |
| `crossover(d, a, C)`, `crossover_rule(d)` | when a subexponential algorithm wins |
| `claims()`, `certificate_growth(c)` | five claims, five verdicts |

All numbers in this document come from `bun tools/eth_lab.bun`; none are
asserted by hand. The module is pure Bun and uses `bun:sutra` only for `num`,
`fmt` and the `classify` contract.

## 7. Corrected invariant (added 2026-11-05)

The right invariant is the **exponent density**

```
s(n) = log₂ T(n) / n
ETH true  ⟺  limsup s(n) > 0 for every correct 3SAT algorithm
                (equivalently, s(n) does NOT tend to 0)
ETH false ⟺  some algorithm has s(n) → 0, i.e. T = 2^o(n)
```

`alpha` collapses to 1 for both `2^(0.99n)` and `exp(n/√ln n)`, but
`s = 0.99` in the first case and `s → 0` in the second. A smaller base keeps
ETH; a vanishing density refutes it. These are different *kinds*, not
different sizes — exactly the error in the video's "only slightly better than
exponential, so the barrier remains" reasoning.

| function | returns |
|----------|---------|
| `s_of_ln(n, ln_t)`, `soft_ln(n)`, `soft_points(ns)` | log-space `s` primitives (no overflow) |
| `s_series(points)`, `eth_shape(ss)` | the `s` curve and a **shape** verdict (never a proof) |
| `local_exponents_ln(points)`, `growth_ln(points)` | `alpha` from an `[n, ln T]` table |
| `alpha_blindspot()` | machine-checked contradiction: `alpha = 0.9295` says exponential, `s → 0` says `2^o(n)` |
| `eth_worlds()` | five worlds under the correct invariant |

```bun
import { alpha_blindspot, eth_worlds } from "bun:eth"

let b = alpha_blindspot()
print(b["contradiction"])          // true
print(eth_worlds().len())         // 5
```

`alpha_blindspot()["contradiction"]` is independently reproduced in Python
(`tests/test_pramana.py`, `tests/test_eth.py`) and on all four Bun engines.
The value `0.9295174545228192` agrees to the last printed digit.

`worlds()` is retained unchanged for backwards compatibility; it describes
`alpha`, not ETH. For the full evidence layer — six pramanas, the 2026 claim
ledger, quantum/BBBV, barriers and the final `UNRESOLVED` verdict — see
[`bun:pramana`](pramana.md) and `bun tools/eth_mystery_lab.bun`.

## Correction (2026-11-05): `liminf` → `limsup`

An external code review of commit `d43dec0` found that the first version of
this document stated

```
ETH true  ⟺  liminf s(n) > 0 for every correct algorithm      [WRONG]
```

That is **strictly stronger than ETH**. ETH (Impagliazzo–Paturi: `s_3 > 0`,
equivalently no correct algorithm decides 3SAT in `2^o(n)` worst-case time)
constrains the **limsup** of the exponent density, not its liminf: an
algorithm may be fast on a sparse set of input lengths and slow on infinitely
many others without refuting ETH. It also made the two halves of
`eth_statement()` logically inconsistent — the negation of `liminf s > 0` is
`liminf s = 0`, not `s(n) → 0`.

`bun:nyaya` (Level 3) verifies this mechanically: it encodes each statement
as a quantifier prefix over `(eps, N, n)` and computes the De Morgan negation
by flipping quantifiers. `level2_review()` rejects the old pair;
`level3_fix_check()` confirms the corrected pair is complementary. The
uniform form `∃eps>0 ∀A` also needs triangular diagonalisation over
algorithms, which `assumptions()` records as an explicit assumption.

ETH remains **UNRESOLVED**; this correction changes a theorem *statement*,
not the status of the conjecture.
