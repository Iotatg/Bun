# `bun:hawking_page` — a subject whose answer is one minus sign

This is SUTRA applied to a real physics claim, in the form the language can
actually check: a model with two branches, a certificate with six checks, and
a ledger that keeps the open question open.

> **What this module is not.** It is not a reproduction of the 2026 preprint,
> and it does not verify anyone's number. `bun:hawking_page` builds the
> two-branch free energy that the 1983 Hawking–Page result rests on, measures
> its shape and its order, and then runs the experiment the news story is
> about: flip one sign, and the answer changes from *jump* to *no jump*.

## 1. The subject, stripped

**S — Saaf karo.** Remove the vocabulary and three numbers remain:

| symbol | what it is | how it is fixed |
|--------|-----------|-----------------|
| `Tc = 3 / (2 pi L)` | the critical temperature of a large AdS universe of radius `L` | geometry only; `T = (d-1)/(2 pi L)` with `d = 3` |
| `dF = F_black - F_gas` | the free-energy difference | vanishes at `Tc`; falls as `T^4` because the radiation is four-dimensional |
| `sign(dF)` | which phase wins | **this** is the unknown the long calculation was for |

**U — Usko roop.** The answer is not a number; it is a *sign*. SUTRA calls that
`structural`: the behaviour is decided by which side of zero a smooth function
lands on. Its ingredients are still power laws, and they are measurable:

| quantity | shape | measured here |
|----------|-------|---------------|
| `Tc(L)` | `power(-1)` | doubling the universe halves the temperature |
| `S(T)` | `power(3)` | entropy of radiation |
| `q(T) = T dS/dV` | `power(4)` | latent heat per unit volume |

**T — Tareeka.** Two moves do the work. *Shrink*: keep only the difference of
the two branches, because the common part cannot change which one is lower.
*Change*: plot the **lower envelope** `min(F_gas, F_black)`, because a phase
transition is a property of the envelope, not of either branch.

**R — Rakh-jaanch.** Six checks, each able to fail — see §3.

**A — Answer + Admit.** See §4. The large case is `KNOWN`; the 2003 question
is `UNRESOLVED`; the 2026 claim is `UNVERIFIED`.

## 2. The four models

All four have the same `Tc`, the same `T^4` scale and the same code path. Only
signs differ. `bun lib` prints this table:

```
model      crosses  Tc        order   high-T winner
crossing   yes      0.47746   first   black hole
flipped    no       none      second  black hole
reversed   yes      0.47746   first   radiation
tangent    yes      0.47746   second  black hole
```

| model | `dF` | what it says | why it is in the table |
|-------|------|--------------|------------------------|
| `crossing` | `k V (Tc^4 - T^4)` | jump at `Tc`, black hole wins above | the physics |
| `flipped` | `k V (-Tc^4 - T^4)` | no crossing at all | **one sign** turns "jump" into "no jump" |
| `reversed` | `k V (T^4 - Tc^4)` | jump at `Tc`, radiation wins above | right shape, right order, wrong physics |
| `tangent` | `-k V (T - Tc)^3` | continuous slope, curvature jumps | the control: a genuine second-order transition |

The `flipped` row is the news story in one line: the same `T^4`, the same
`Tc`, and no transition. The `reversed` row is the warning: a sign error can
leave the *shape* and the *order* intact and still get the answer backwards.

## 3. The six checks

| # | check | what it measures | what it catches |
|---|-------|------------------|-----------------|
| 1 | shape | `classify(Tc)` is `power(-1)` | a wrong exponent in the geometry |
| 2 | number | `Tc(1) = 3/(2 pi)` | arithmetic |
| 3 | crossing | bisection lands on the formula | an offset in `dF` |
| 4 | **direction** | `dF(0.5 Tc) > 0`, `dF(1.5 Tc) < 0` | **a flipped sign** |
| 5 | order | the envelope slope jumps by `4 k V Tc^3` | a smooth model passed off as a jump |
| 6 | entropy | `classify(S)` is `power(3)` | a wrong temperature dependence |

Check 4 is the one that matters, and it is the one a shape-only argument
cannot make. `classify` measures how the output moves when the input moves;
`+T^4` and `-T^4` move identically. The sign is visible only in a *limit* —
which phase wins as `T` grows. That is why a proof of a phase transition that
stops at "the shape is `T^4`" has not proved anything about the transition.

The certificate refuses `k < 0` (`REFUSED`, with `direction` named as the
failing check) even though checks 1, 2, 3, 5 and 6 still pass. A certificate
that cannot fail is decoration.

## 4. The ledger

```bun
import { claim_ledger } from "bun:hawking_page"
for row in claim_ledger() { print(row["status"], row["claim"]) }
```

| claim | who | status | evidence |
|-------|-----|--------|----------|
| a large AdS universe has a critical temperature | Hawking & Page, 1983 | `KNOWN` | the branches cross at `3/(2 pi L)`; measured |
| the large-universe transition is first order | Hawking & Page, 1983 | `KNOWN` | the envelope slope jumps by `4 k V Tc^3`; measured |
| the small-universe case is a jump or a slide | Aharony et al., 2003 | `UNRESOLVED` | this two-branch model has no small-black-hole saddle, so it cannot answer it |
| the 2026 preprint's sign, hence its answer | external preprint | `UNVERIFIED` | this module checks the structure of the claim, not its number |

The third row is the honest boundary. The 2003 question is about the regime
where more than two saddles compete; a model with two branches cannot decide
it, and pretending otherwise would be the exact failure the ETH lab in
`bun:eth` exists to prevent.

## 5. Using it

```bun
import { certificate, sign_audit, report, why_one_sign } from "bun:hawking_page"

print(report())
let c = certificate(1.0, 1.0, 1.0)
print(c["status"], c["passed"], c["total"])   // CERTIFIED 6 6
print(why_one_sign())
```

`ffi_load` is used for `pow` and `fabs`, so the C backend refuses this module
by name (`the C backend does not support the builtin 'ffi_load'`) instead of
silently compiling something else. `tree`, `vm` and `register` agree on every
number in the table.

Reference: this file.  Tests: `tests/test_hawking_page.py` (24 cases).
Example: `examples/hawking_page.bun`.
