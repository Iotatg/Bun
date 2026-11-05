# `bun:sutra_school` — SUTRA, class 1 to graduation

`bun:sutra` defines the subject: four shapes, seven moves, four checks.
`bun:sutra_school` answers a different question — *in what order should a
person meet them?* — and refuses to answer it by assertion.

> Fifteen years, fifteen new ideas. Each year introduces exactly one atom,
> uses only atoms already taught, and carries a real law from that year's
> syllabus which `classify` must measure as the shape the year claims to
> teach. If any of that fails, `audit()` says `REJECTED`.

```bun
import { audit, path, teach, place } from "bun:sutra_school"

print(path())
let a = audit()
print(a["verdict"], a["passed"], a["total"])   // CERTIFIED 7 7
print(teach(1))
print(place(8, 12)["stage"])                  // class 11
```

The full run is `bun tools/sutra_school_lab.bun`; the short tour is
`examples/sutra_school.bun`; the tests are `tests/test_sutra_school.py`
(15 tests, identical output on all four engines).

---

## 1. What the basics actually are

A six-year-old does not meet a formula. The first lesson is one sentence:

> One thing changes, another does not. Name the one that does not.

That is `constant`, the degenerate shape. Everything after it is the same
question asked at a higher level: **how does the answer move when the input
moves?**

| shape | defining property | child's version |
|-------|-------------------|-----------------|
| `constant` | `f(Lx) = f(x)` | the glass does not change when you add marbles |
| `power` | `f(Lx)/f(x) = L^k` | double the pencils, double the price |
| `exponential` | `f(x+d)/f(x) = r` | every year the money is multiplied again |
| `logarithmic` | `f(Lx)-f(x) = c` | every doubling adds one more step |

Seven moves take a question to a shape (`name`, `shrink`, `change`,
`invariant`, `bound`, `compose`, `check`) and four checks certify the answer
(`shape`, `number`, `dimension`, `boundary`). Those are the entire subject.
The school is just the order in which they become usable.

## 2. The 15-year path

| level | stage | one new atom | that year's law | measured shape |
|-------|-------|--------------|-----------------|----------------|
| 1 | class 1 | `shape:constant` | a fixed glass of 5 marbles | `constant` |
| 2 | class 2 | `shape:power` | cost = 3 × pencils | `power(1)` |
| 3 | class 3 | `move:shrink` | 120/n sweets each | `power(-1)` |
| 4 | class 4 | `move:name` | `A = s²`, in m² | `power(2)` |
| 5 | class 5 | `tool:dimension` | `s = 5t²` | `power(2)` |
| 6 | class 6 | `move:change` | `V = x³` | `power(3)` |
| 7 | class 7 | `move:invariant` | `F = 6/r²` | `power(-2)` |
| 8 | class 8 | `move:bound` | `√x` | `power(0.5)` |
| 9 | class 9 | `tool:graph` | `T ∝ a^1.5` | `power(1.5)` |
| 10 | class 10 | `shape:exponential` | `N = 1000·2^(t/20)` | `exponential` |
| 11 | class 11 | `shape:logarithmic` | `log₂ x` | `logarithmic` |
| 12 | class 12 | `move:compose` | `n³/3` | `power(3)` |
| 13 | graduation 1 | `tool:derivative` | `3x²` | `power(2)` |
| 14 | graduation 2 | `tool:ode` | `e^(-0.3t)` | `exponential` |
| 15 | graduation 3 | `move:check` | `2^n` | `exponential` |

Total: **2280 hours**. The four shapes appear by class 11; the last four years
are instruments, not new laws. The final year ends on the boundary: a
certificate is about one law, while a theorem is about all of them.

## 3. Why the syllabus is executable

Each level is a dict with a `sample` function, `sample_at`, `sample_lam`,
`expect` and `expect_param`. `audit()` loops over them and calls
`classify(sample, at, lam)`. A year cannot claim to teach `exponential` while
showing a power law. It also checks:

| check | what it proves |
|-------|----------------|
| `count` | exactly 15 contiguous levels, numbered 1–15 |
| `one-new-atom` | one new atom per year, all 15 distinct |
| `core-covered` | all 4 shapes and all 7 moves are taught somewhere |
| `prerequisites` | every `uses` entry was taught in an earlier year |
| `samples-measure-true` | 15/15 laws measure as the declared shape and parameter |
| `teachable` | idea, exercise, answer, unlocks and hours are all present |
| `hours` | the total is a plausible 15-year load |

The registry is 4 shapes + 7 moves + 4 tools = 15 atoms. That is not a
coincidence: it is the constraint that makes the audit meaningful.

## 4. API

| function | returns |
|----------|---------|
| `atoms()` | the 15-atom registry, with Hindi labels |
| `syllabus()` | 15 level dicts |
| `audit()` | `{"checks", "passed", "total", "verdict", "hours"}` |
| `path()` | the 15-line ladder |
| `teach(level)` | a complete lesson, including the measured shape of its law |
| `place(score, total)` | the year a diagnostic score places the learner in |
| `unlocks(level)` | the real-world things that year makes explainable |

`place` is monotone by construction: more correct answers never move a learner
backwards. 0/12 → class 1, 12/12 → graduation 3.

## 5. What comes immediately after graduation

Year 15 is where `bun:eth` starts. The last exercise asks what to do with the
claim "our solver is faster than 2^n, so ETH is false", and the answer is the
fifth check: the claim quantifies over *all* algorithms, so measurement cannot
settle it. See [`eth.md`](eth.md).
