# `bun:sutra_sarva` — SUTRA Level 4: ek hi raasta, har sawaal

> **ईमानदारी पहले:** यह मॉड्यूल `openai/math` के **373 research theorems में से
> एक का भी प्रमाण नहीं देता**। SUTRA Level 1 का नियम आज भी सच है —
> *"SUTRA is a filter, not a solver"*।
> यह मॉड्यूल देता है: **एक आसान 5-कदम तरीका**, एक **वास्तविक solver** (एक परिभाषित
> आसान वर्ग के सवालों के लिए exact जवाब + 4 जाँचें), और **पूरे corpus का ईमानदार
> नक्शा** (373/373 families) — जिसमें हर परिवार को साफ़ बताया गया है कि SUTRA उसका
> क्या कर सकता है और क्या नहीं।

---

## 0. `openai/math` असल में है क्या? (clone से मापा गया)

बहुत लोग इसे "math questions का dataset" समझते हैं। यह वैसा नहीं है।

| माप | अंक | स्रोत |
|---|---|---|
| Result families | **373** | `CONTENTS.md` की `**NNN.` headings |
| Manuscripts (PDF links) | **721** | `](preprints/...pdf)` links |
| Families with a `lean/docs/` link | **245** | उसी catalogue से |
| Comparator challenges | **418** | `lean/ComparatorChallenges/*.lean` |
| README का दावा | **~42% top-line results formalized** | `README.md` |

> **दो अलग माप को जोड़ना गलत है:** 245 = *families जिनके block में Lean link है*;
> README का ~42% = *top-line results formalized*। Denominator अलग है। यह वही
> सबक है जो `bun:discovery.corpus_stats()` ने सिखाया था।

Repo `README.md` खुद कहता है: *"Not all have accompanying Lean formalizations…
Some of the unformalized results could have issues"* और *"best understood as raw
research data, rather than polished academic papers"*। यानी यहाँ **सवालों की
किताब** नहीं, **शोध-पत्रों का संग्रह** है।

---

## 1. S-U-T-R-A — बस इतना ही याद रखना है

SUTRA के **पाँच अक्षर ही पाँच कदम** हैं। हर सवाल पर वही पाँच।

| | कदम | आसान भाषा में | क्या हटता है |
|---|---|---|---|
| **S** | **S**aaf karo (Strip) | शब्द हटाओ; अंक, चिह्न, मात्रा रखो | डरावनी vocabulary |
| **U** | **U**ska roop (Shape) | 5 में से कौन-सा आकार | "कौन-सा फ़ॉर्मूला?" की उलझन |
| **T** | **T**areeka (Move) | 7 moves में से एक चुनो | बड़े सवाल का भय |
| **R** | **R**akh-jaanch (Checks) | 4 अलग-अलग जाँचें | चुपचाप रह जाने वाली गलती |
| **A** | **A**nswer + Admit | जवाब दो, **सीमा भी बताओ** | झूठा `CERTIFIED` |

**पाँच आकार:** `constant`, `power`, `exponential`, `logarithmic`, `structural`।

**सात moves** (`bun:sutra.moves()` से विरासत में): `name`, `shrink`, `change`,
`invariant`, `bound`, `compose`, `check`।

**चार जाँचें:** आकार, संख्या (स्वतंत्र recompute), मात्रा/unit, छोर (छोटा case)।

### सबसे आसान उदाहरण — class 1

```
सवाल: 2+3

S  शब्द कोई नहीं; दिया 2, 3; पूछा जोड़।
U  आकार constant (कुछ नहीं बदल रहा n के साथ)।
T  move 4 "invariant" — जो नहीं बदलता, वही पकड़ो।
R  आकार ✓, संख्या: दोबारा गिना 5 ✓, मात्रा/token ✓, छोर ✓।
A  जवाब 5, certificate CERTIFIED 4/4 — scope: "ये 4 self-checks हैं, प्रमाण नहीं"।
```

### उसी तरीके से research सवाल

```
सवाल: Prove the quasi-Riemann hypothesis Re(s)>7/8

S  दिया 2 अंक, शब्द "Prove" → goal = PROVE (COMPUTE नहीं)।
U  आकार structural (बनावत का सवाल, वृद्धि का नहीं)।
T  move 7 "check" — जाँच लो कि प्रमाण क्या माँगता है।
R  चारों जाँचें यहाँ लागू नहीं — इन्हें चलाने के लिए जवाब ही नहीं है।
A  OUT_OF_SCOPE_FOR_SUTRA: "प्रमाण चाहिए (Lean / mathlib /
   independent review); shape और move बताना प्रमाण नहीं है"।
```

> **यही "आसान तरीका" की असली कीमत है:** वह यह भी साफ़ बता देता है कि कब
> जवाब **देना बंद** करना है।

---

## 2. वास्तविक solver — परिभाषित, ईमानदार सीमा के साथ

`ask(text)` एक लाइन लेता है और `solve()` चलाता है:

| लिखा | पहचाना | जवाब |
|---|---|---|
| `2+3` | arithmetic | `5` |
| `(2+3)*4^2` | arithmetic (precedence सही) | `80` |
| `1/2+1/4` | arithmetic | `0.75` |
| `50% of 80` | percent | `40` |
| `sum 1..100` | series | `5050` |
| `3*x + 7 = 22` | linear equation | `x = 5` |
| `7/8 vs 11/12` | ratio | `7/8 < 11/12` (cross-multiply, exact) |
| `Prove ...` | theorem | `OUT_OF_SCOPE_FOR_SUTRA` |

### दो स्वतंत्र evaluators, एक नहीं

`calc()` शुद्ध-Bun **shunting-yard** है, `calc_alt()` शुद्ध-Bun **recursive
descent** है। दोनों एक ही strict tokenizer (`tokenize()`) से token लेते हैं,
पर मूल्यांकन के अलग-अलग algorithms हैं। Certificate इनकी तुलना करता है —
चार engines का आपसी मेल नहीं, **एक दूसरे algorithm से मेल**।

बाहरी code review के बाद ठीक की गई बातें (सब `review_ledger()` में दर्ज हैं):

| Input | पहले | अब |
|---|---|---|
| `2^3^2` | `64` | **`512`** (`^` right-associative) |
| `-3+5` | `pop on empty list` crash | **`2`** (unary `±`) |
| `-3^2` | crash | **`-9`** (unary minus `^` से ढीला) |
| `2^-3` | crash | **`0.125`** |
| `2(3+4)` | `2.0` (चुपचाप गलत) | **`14`** (implicit `*`) |
| `2+*3`, `2..3`, `2a+3`, `2*(3+4`, `1/0`, `()` | crash या silent | **`INVALID_EXPRESSION` + कारण**, कोई crash नहीं |
| `sum 1..-5` | `15` (गलत) | **`INVALID_INPUT`** |
| `0*x+7=7` | `division by zero` crash | **`INFINITE_SOLUTIONS`** |
| `0*x+7=10` | crash | **`NO_SOLUTION`** |
| `2x-5=9` | `x = 2` (गलत) | **`x = 7`** (signed coefficient) |

### Certificate — अब कोई हमेशा-सच्ची जाँच नहीं

पहले `boundary_ok()` की तीन शाखाएँ **कभी fail ही नहीं हो सकती थीं**:
`f_abs(ans - ans)`, `f_abs(0.0*b/100)` और hardcoded `1*2/2-1`। बाहरी review
ने यह सही पकड़ा। अब हर check के पास `method` और `detects_wrong_answer` है,
और हर पहचान ऐसी identity है जो गलत जवाब पर टूटती है:

| Check | स्वतंत्र रास्ता |
|---|---|
| shape | `expected_shape` table बनाम keyword-shape route (वर्गीकरण) |
| number | `calc_alt` (calc), loop `1..n` (sum), substitution `a*x+b` (linear), `(b/100)*a` (percent), cross-multiply (ratio) |
| dimension | operand domain + पूरी तरह parse हुआ expression |
| boundary | complement identity, shift invariant, loop recurrence, metamorphic `2*(expr)=2*ans`, decimal-division sign |

हर `SOLVED` जवाब के साथ `certificate` मिलता है: `CERTIFIED 4/4`, लेकिन उसमें
`verification_level`, `proof_status: NOT_ESTABLISHED` और स्पष्ट `scope` है:

```
"4 checks, 2 can detect a wrong numeric answer (2 distinct oracles);
 computation, NOT A PROOF of any theorem"
```

`certificate_probe()` सातों kinds में जान-बूझकर गलत जवाब (`999.0`) डालता है और
**7/7 `REJECTED`** पाता है। `check_answer(q, 999.0)` को अब `REJECTED 2/4`
मिलता है (पहले `3/4` था — certificate **सख़्त** हुआ है, कमज़ोर नहीं)।

---

## 3. API

| Function | क्या देता है |
|---|---|
| `alphabet()`, `charter()`, `lesson()` | 5-कदम विधि |
| `shapes()`, `seven_moves()`, `four_checks()` | 5 / 7 / 4 |
| `strip(text)`, `shape_of(text)`, `choose_move(shape, kind)` | S, U, T |
| `calc(expr)`, `calc_alt(expr)`, `tokenize(expr)` | shunting-yard / recursive-descent / strict tokenizer |
| `solve(q)`, `check_answer(q, ans)`, `certificate_probe()` | जवाब + 4 जाँचें + false-positive scan |
| `parse_question(text)`, `ask(text)`, `steps(q)` | एक-लाइन + 5 कदम |
| `course()`, `teach(i)` | 10 काम किए उदाहरण (class 1 → research) |
| `parse_catalogue(text)`, `catalogue(path)`, `catalogue_summary(cards)` | पूरा corpus |
| `status_rules()`, `measurement_notes()` | मापों की सीमा |
| `eth_evidence(root)`, `eth_bound_check()` | ETH दावे की जाँच |
| `review_ledger()` | बाहरी review के 11 दावे: claim / reproduced / verdict / fix |
| `verification_levels()` | 5 स्तर, जिनमें **सिर्फ़ 1–2 IMPLEMENTED** हैं |
| `roadmap()` | 10 phases, जिनमें **सिर्फ़ Phase 0 DONE** है |
| `verdict()`, `audit()` | ईमानदार निष्कर्ष + 34 self-checks |

`course()` में 10 सवाल हैं: **9 `SOLVED`** (exact जवाब, 4/4 checks) और **1
`OUT_OF_SCOPE`** (research theorem)। `course()` class 1 से graduation होते हुए
research तक जाता है — **पाँच कदम वही रहते हैं**।

---

## 4. पूरा corpus: 373/373 families का नक्शा

`tools/sutra_sarva_lab.bun` असली clone का `CONTENTS.md` पढ़कर हर परिवार का
card बनाता है। वास्तविक परिणाम (`SUTRA_SARVA_LAB_OUTPUT.txt`):

| Shape | Families |
|---|---|
| power | 119 |
| structural | 101 |
| constant | 75 |
| logarithmic | 50 |
| exponential | 28 |
| **कुल** | **373** |

| Status | Families |
|---|---|
| `FORMALIZED_IN_LEAN` | 244 |
| `MANUSCRIPT_ONLY` | 128 |
| `CLAIM_UNDER_REVIEW` | 1 |
| **कुल** | **373** |

- `mapped by SUTRA` = **373/373**
- `sutra_can_prove` = **0**
- `lean-link families` = **245** = 244 + 1 (ETH वाले परिवार का भी Lean link है,
  पर उसका status अलग रखा गया)।

> हर card में `sutra_can_prove: false` और `sutra_can_do: "shape + move +
> 4 checks + verification map"` लिखा है। कोई भी card "सिद्ध हो गया" नहीं कहता।

---

## 5. इसी repo में ETH का नया दावा — SUTRA क्या तय करता है

`history.md` (26 Oct 2026) में **"The Exponential Time Hypothesis is False"**
जोड़ा गया, साथ में लिखा है कि Impagliazzo, Paturi और Ryan Williams की स्वतंत्र
टीम प्रमाण की *"examine and explain"* करेगी। इंटरनेट पर भी यही स्थिति है:
OpenAI/Anthropic के 26 Oct 2026 के दो प्रकाशन, और OpenAI का प्रमाण **अभी भी
स्वतंत्र समीक्षा में** है। कोई समाचार / panel / manuscript किसी theorem का
विकल्प नहीं है (`bun:pramana.can_settle()`)।

### Primary evidence — clone से मापा, खबर से नहीं

| तथ्य | अंक |
|---|---|
| `history.md` में manuscript घोषित | `true` |
| review group के तीनों नाम | `true` |
| `ComparatorChallenges/SubexponentialSAT.lean` में `sorry` | **1** (stub) |
| `OAI/.../SqrtLogSpace/Final.lean` में `sorry` | **0** |
| वहाँ `exact_count_eth` theorem | `true` (5 theorems) |

> **Translation gap:** challenge फ़ाइल में `:= by sorry` है — वह **प्रमाण नहीं,
> स्टब** है। प्रमाण `OAI/Algorithms/SubexponentialSAT/` के **दूसरे** module में है।
> `.lean` फ़ाइल का होना और सही theorem का औपचारिक रूप से सिद्ध होना अलग-अलग
> जाँचें हैं (`bun:nyaya.translation_gaps()`)।

### SUTRA bound का **आकार** जाँचता है, प्रमाण नहीं

Repo के अपने `SqrtLog.Statement` से:

```
runtimeScale(n) = n * (log(log(n+16)))^2 / sqrt(log(n+16))
T              <= C * poly(n) * 2^(A * runtimeScale(n))
```

`bun:eth` के **सुधरे** invariant `s = log2(T)/n` (Level 3 ने `liminf → limsup`
ठीक किया था) के साथ:

```
s(n) = A * (log log n)^2 / sqrt(log n) + d*log2(poly)/n  ->  0
```

| n | s(n) |
|---|---|
| 1e3 | 1.423 |
| 1e6 | 1.855 |
| 1e12 | 2.096 |
| 1e20 | 2.161 |
| 1e40 | 2.132 |
| 1e100 | 1.950 |
| 1e300 | 1.626 |

`s(n) → 0` ⇒ `T = 2^o(n)` ⇒ **यदि theorem स्वीकार हो तो ETH असत्य**।
`shape_verdict = SUBEXPONENTIAL_IN_THE_LIMIT`।

**दो साफ़ चेतावनियाँ:**

1. s(n) बहुत धीरे घटता है — `n = 10^20` तक तो बढ़ता है। "asymptotic रूप से
   तेज़" और "व्यवहार में तेज़" अलग बातें हैं।
2. SUTRA ने **bound का आकार** जाँचा, **प्रमाण की correctness नहीं**। Lean
   theorem का अस्तित्व, स्वतंत्र समीक्षा पास होना, और mathematical community
   द्वारा ETH को खंडित मान लेना — तीन अलग चीज़ें हैं।

**इसलिए `eth_status = UNDER_REVIEW (not SOLVED_BY_SUTRA)`।** पिछले commits में
ETH को `UNRESOLVED` कहा गया था; अब repo में एक औपचारिक theorem है, तो स्थिति
`UNDER_REVIEW` है — **`SOLVED` कभी नहीं कहा गया**।

---

## 6. बाहरी roadmap का ईमानदार जवाब

बाहरी review ने 12–18 महीने का 10-phase roadmap, 5 verification levels,
~100 नई files, Lean bridge, symbolic algebra, calculus, science engines और
एक unified `SutraResult` protocol propose किया। **Direction सही है और स्वीकार
है; delivery नहीं हुई।** लिखा हुआ phase बनाया हुआ phase नहीं होता — यही
`bun:nyaya` का *"tests लिखे होना / execute होना अलग"* वाला सबक है, अब roadmap
पर भी लागू।

### Verification levels

| Level | नाम | SUTRA की स्थिति |
|---|---|---|
| 1 | COMPUTED | **IMPLEMENTED** |
| 2 | INDEPENDENTLY_CHECKED | **IMPLEMENTED** (7 elementary kinds, दो algorithms / identities) |
| 3 | SYMBOLICALLY_VERIFIED | `NOT_IMPLEMENTED` |
| 4 | FORMALLY_VERIFIED (Lean kernel) | `NOT_IMPLEMENTED` |
| 5 | RESEARCH_REVIEWED | `NOT_IMPLEMENTED` (ETH `UNDER_REVIEW` ही रहेगा) |

`verification_levels()` यही table machine-readable लौटाता है। `growth` जैसे
scalar passthrough पर सिर्फ़ **एक** distinct oracle है, इसलिए वह ईमानदारी से
`COMPUTED` कहता है, `INDEPENDENTLY_CHECKED` नहीं।

### Phase status

| Phase | स्थिति |
|---|---|
| 0 — correctness audit, parser / solver / certificate fix | **DONE** (यह commit; `certificate_probe()` 7/7) |
| 1–9 — AST/rational, symbolic, advanced math, science, Lean, research, router, reliability, release | **`NOT_IMPLEMENTED`** |

`roadmap()` में `phase_0 = DONE`, बाकी नौ `NOT_IMPLEMENTED` हैं। कोई 12–18
महीने की delivery date नहीं दी गई — वह review का planning estimate था, कोई
commitment नहीं।

### इस commit में क्या वाकई बना

- **P0 (पूरा):** expression parser correctness, unary/invalid handling,
  zero-coefficient equations, negative summation, negative coefficients.
- **P1 (आंशिक):** genuine independent four checks + **independent Python
  oracle** वाली 24 regression tests. **Exact rational arithmetic अभी नहीं** —
  `1/2+1/4 = 0.75` floating point पर सही है, पर यह exact rational engine नहीं।
- **P2/P3: कुछ नहीं।** Symbolic algebra, Lean integration, research theorem
  verification — सब `NOT_IMPLEMENTED`।

> **नियम नहीं बदला:** SUTRA अपनी confidence को कभी mathematical proof के रूप
> में पेश नहीं करेगा। हर result में `proof_status: NOT_ESTABLISHED` है।

---

## 7. अंतिम निष्कर्ष

```bun
import { verdict, audit } from "bun:sutra_sarva"
print(verdict()["research_theorems_solved_by_sutra"])   // 0
print(verdict()["research_families_mapped"])            // 373
print(audit()["passed"])                                // 34
```

| सवाल | उत्तर |
|---|---|
| "सब कुछ SUTRA से solve हो गया?" | **नहीं** — 373 research theorems में से 0 |
| तो क्या हुआ? | **एक आसान विधि** + **9/10 आसान सवालों के exact जवाब** + **पूरे corpus का ईमानदार नक्शा** |
| `CERTIFIED 34/34` | 34 module self-checks, किसी theorem का प्रमाण नहीं |
| ETH | **UNDER_REVIEW** |
| SUTRA है | आसान तरीका + ईमानदार नक्शा |
| SUTRA नहीं है | research mathematics का proof engine |

> **नियम:** जो solve कर सकते हैं उसका exact जवाब दो; जो नहीं, उसका साफ़
> `OUT_OF_SCOPE` **और कारण** दो।

---

## 8. चलाने के तरीके

```sh
./bin/bun examples/sutra_sarva.bun                  # छोटा उदाहरण
./bin/bun tools/sutra_sarva_lab.bun                 # पूरा 373-family record
./bin/bun tools/sutra_sarva_review_lab.bun          # बाहरी review के corrections
python3 -m pytest -q tests/test_sutra_sarva.py tests/test_sutra_sarva_correctness.py
python3 tools/check.py lib/bun/sutra_sarva.bun
```

Lab की डिलीवरी `SUTRA_SARVA_LAB_OUTPUT.txt` में **373/373 cards** और बाहर से
चलाए गए pytest का वास्तविक output append है — क्योंकि tests लिखे होना और
execute होकर pass होना अलग बातें हैं (`bun:nyaya` review point 5)।

**Correction commit का वास्तविक बाहरी run**
(`SUTRA_SARVA_CORRECTION_PYTEST.txt`, और `SUTRA_SARVA_REVIEW_LAB_OUTPUT.txt`
के अंत में append):

```
2234 passed, 2 skipped in 1070.09s (0:17:50)   PYTEST_EXIT=0
```

पिछली public suite (`fe6cc9c`) 2206 थी. Is commit में **+24** नई regression
tests (`tests/test_sutra_sarva_correctness.py`, independent Python oracle) और
**+4** `tests/test_selfhost.py` के auto-corpus से (नया
`tools/sutra_sarva_review_lab.bun` अपने आप 4 parity tests में जुड़ा) =
**2234**. 373-card lab अछूता रहा — uska 612-पंक्ति output चारों engines पर
byte-for-byte समान है (`md5 6cb6c78d…`). Naya review lab का 142-पंक्ति output
भी चारों engines पर समान है (`md5 0265618d…`)।

> Receipt code tree पर चलाई गई है; ऊपर की docs/README edits सिर्फ
> documentation हैं, tests उन्हें import नहीं करते (`bun:nyaya` point 5:
> लिखना और चलाना अलग)।
