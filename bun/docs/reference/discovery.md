# `bun:discovery` — experimental mathematics

`bun:discovery` is a laboratory, not a theorem prover. It was built to probe
numerical claims in the [openai/math](https://github.com/openai/math)
manuscript collection (721 manuscripts, 373 result families) with arithmetic
that belongs to Bun itself: an arbitrary-precision fixed-point decimal layer
over the language's bigint builtins.

The distinction matters. A finite computation can *corroborate* a claim,
*find* a formula, or *measure* a constant. It cannot prove a statement about
all sufficiently large denominators, nor settle an open problem. Every probe
below says what it can and cannot establish.

Load it like the other stacks — no new builtins, no native extension:

```bun
import { pi_digits, bbp_hex, machin_search } from "bun:discovery"

print(pi_digits(30))       // 3.141592653589793238462643383279
print(bbp_hex(0, 8))       // 243F6A88
```

Run the full lab notebook with `bun tools/discover.bun`; a shorter tour is
`bun examples/discovery.bun`. The tests are `tests/test_discovery.py` and run
identically on all four engines.

---

## The fixed-point layer

A value is `{"s": sign, "m": mantissa}`, where the mantissa is a bigint (a
little-endian list of base-256 bytes) scaled by `10^PREC`. Addition,
subtraction, multiplication and division are exact to the chosen precision;
the only rounding is the final truncated bigint division. `set_precision(n)`
rebuilds the scale; `precision()` reports it. The default is 60 decimals.

| call | what it does |
|------|--------------|
| `set_precision(n)`, `precision()` | choose / read the number of decimals |
| `fx_int(n)`, `fx_parse(s)` | build a value from an int or a decimal string |
| `fx_add`, `fx_sub`, `fx_mul`, `fx_div` | the four operations |
| `fx_div_int(a, n)`, `fx_mul_int(a, n)` | scale by a machine integer |
| `fx_neg`, `fx_abs`, `fx_cmp` | sign and comparison |
| `fx_str(a, digits)`, `fx_float(a)`, `fx_trunc(a)` | render / hand to a double / integer part |
| `fx_sqrt(a)`, `fx_sqrt2()` | Newton's method in the fixed-point layer |
| `fx_pi()`, `fx_pi_quarter()`, `fx_e()`, `fx_ln2()` | constants by series |
| `fx_atan_inv(x)` | `atan(1/x)` by the alternating arctangent series |
| `pi_digits(n)`, `fx_hex_digits(x, n)`, `fx_hex_digits_at(x, start, n)` | digits out |

The arctangent and area-hyperbolic-tangent series stop when the term
underflows to zero in the scaled bigint; the loop ceiling is high enough for
precisions up to about 2500 decimals.

---

## Probe 1 — pi at arbitrary precision

`fx_pi()` uses Machin's formula `pi = 16*atan(1/5) - 4*atan(1/239)`, with
each arctangent summed in scaled bigints. `pi_digits(100)` widens the
precision first, so every requested digit is significant. The 100 digits
printed by the driver match the published expansion exactly.

## Probe 2 — two independent paths to the same hex digits

`bbp_hex(start, n)` implements the Bailey–Borwein–Plouffe spigot: the
fractional part of `16^d * pi` is assembled from modular powers
`16^(d-k) mod (8k+j)` (exact bigints via `bigint_pow_mod`) plus a fast
floating-point tail. It yields eight hex digits per block *without computing
the preceding digits of pi*.

The driver checks two things:

- the first 24 hex digits from BBP and from `fx_hex_digits(fx_pi(), 24)`
  agree: `243F6A8885A308D313198A2E`;
- at hex digit 1000, BBP (`49F1C09B`) agrees with pi computed to 1250
  decimals by the Machin path. This is a genuine cross-check: one path is
  modular arithmetic, the other is a global series, and they meet only in
  the answer.

## Probe 3 — Machin-like formulas, found in Bun

`machin_search(max_x, max_m, max_y, max_n)` screens candidates
`pi/4 = m*atan(1/x) + n*atan(1/y)` with a double, then **confirms each hit
exactly** in the fixed-point layer, reporting the residual. With the
driver's bounds the search returns 6 raw hits, 4 distinct after
normalising the two terms:

| formula | residual |
|---------|----------|
| `atan(1/2) + atan(1/3)` | 0 |
| `2*atan(1/2) - atan(1/7)` | 0 |
| `2*atan(1/3) + atan(1/7)` | 0 |
| `4*atan(1/5) - atan(1/239)` | 0 |

These are classical identities; the point is that Bun *re-discovered* them
by search and verified them to 50 decimals with zero residual, rather than
having them hard-coded.

## Probe 4 — the irrationality exponent of pi (family 017)

Family 017 claims `mu(pi) = 2`. `pi_convergents(count)` extracts the
continued fraction of pi in fixed point; `irrationality_measure(count)`
computes `mu_k = -log|pi - p_k/q_k| / log q_k` for each convergent.

Observed: `mu_k` hovers around 2 (2.014 at `q=106`, 2.044 at `q=33102`,
2.057 at `q=25510582`). The spike to 3.20 at `q=113` is the large partial
quotient 292 — `355/113` is an unusually good approximation. This is
*consistent* with the claim and with the known relation
`mu_k ~ 1 + log(q_{k+1})/log(q_k)`. It is not a proof: no finite list of
convergents bounds the exponent for all `q`.

## Probe 5 — Liouville two-point correlations (family 007)

`liouville(n)` is `(-1)^Omega(n)` by trial division;
`liouville_correlation(N)` computes `C(X) = (1/X) sum_{n<=X} lambda(n)lambda(n+1)`
with exact integers. Family 007 predicts a power-of-log saving.

Observed `C(100) = 0.06`, `C(1000) = 0.014`, `C(5000) = 0.0144`. The decay
is not monotone at these small cutoffs, which is expected. The data are
compatible with a slowly decaying correlation but are far too short to
measure the exponent `c`.

## Probe 6 — the Flint-Hills series (family 017)

`flint_hills(N)` sums `1/(n^3 sin^2 n)` in double precision. Family 017
deduces convergence from `mu(pi) = 2`.

The driver finds the mechanism directly: the largest term up to `N=5000`
occurs at `n = 355`, where `sin(355) = -3.0144e-05` because `355/113` is a
convergent of pi. That single term is `24.598`, about 80% of the partial sum
`30.314`. The sum grows only from `30.175` at `N=1000` to `30.314` at
`N=5000`. A double partial sum cannot prove convergence, but it shows
exactly which near-integer multiples of pi control the series.

## Probe 7 — Mahler volume products (family 087)

`mahler_bounds(n)` computes the two minimizers claimed by family 087:
`4^n/n!` for symmetric bodies (cube x cross-polytope) and
`(n+1)^(n+1)/(n!)^2` for general bodies (simplex). For `n=3` these are
`10.666...` and `7.111...`, ratio `2/3`. The table for `n=1..6` shows the
symmetric bound peaking at `n=3,4` and the general bound decreasing — a
concrete prediction that can be checked against any claimed equality case.

`packing_density(digits)` recomputes the Cohn–Elkies planar density
`pi/(2*sqrt(3)) = 0.906899682117108925297039128821` in fixed point.

## Probe 8 — mining the corpus

`corpus_stats(path)` reads a catalogue with `read_file` and `regex_findall`.
It returns `bytes`, `lines`, `indexed_families`, `preprint_pdfs`, `lean_docs`,
`lean_families`, `lean_coverage_pct` (doc links per family), `lean_family_pct`
(families carrying at least one Lean link) and `lean_docs_per_family`.

Attribution walks the file line by line: a `**NNN` heading opens a family, and
any `lean/docs/` link on a following line counts for that family. Note that
`regex_match` is a full-match, so heading detection uses `regex_search` — an
earlier version used `regex_match` and silently reported zero coverage.

Measured on the clone of `openai/math`:

| measurement | value |
|-------------|-------|
| `CONTENTS.md` size | 638,501 bytes, 9,167 lines |
| indexed result families | 373 |
| linked preprint PDFs | 721 |
| linked Lean docs | 245 |
| families with a Lean doc | 245 / 373 = 65.68% |
| Lean docs per covered family | 1.00 |

The 373 families and 721 PDF links reproduce the README's catalogue counts
exactly. The README also says "~42% of top-line results formalized"; that
uses a different denominator (top-line results, not families), so 65.68% is
not a contradiction — it is a measurement of a different quantity.

---

## What this does not do

- It does not prove any result in the corpus. Families 007, 017 and 087
  contain claims about infinite families of objects; finite numerics can
  only corroborate.
- The floating-point probes (Liouville checkpoints beyond the exact sums,
  Flint-Hills, BBP tails, Machin screening) are limited to double precision
  and are labelled as such.
- `bun:discovery` re-derives known constants and identities. Its "new"
  content is the *method* — pure-Bun arbitrary precision, an exact-verified
  formula search, an independent BBP/Machin cross-check at digit 1000, and
  corpus measurements — not a new theorem.

## Files

| path | content |
|------|---------|
| `lib/bun/discovery.bun` | the stack, written entirely in Bun |
| `tools/discover.bun` | the nine-probe lab notebook |
| `examples/discovery.bun` | short tour |
| `tests/test_discovery.py` | 15 tests, four-engine parity |
| `docs/reference/discovery.md` | this document |
