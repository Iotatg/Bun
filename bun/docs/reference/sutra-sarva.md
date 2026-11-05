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

`calc()` एक शुद्ध-Bun shunting-yard evaluator है (`+ - * / ^ ( )`, decimals)।
**डिज़ाइन से** unary minus नहीं है — इसे छिपाया नहीं गया, दर्ज किया गया है।

हर `SOLVED` जवाब के साथ `certificate` मिलता है: `CERTIFIED 4/4`, लेकिन उसमें
स्पष्ट `scope` लिखा है:

```
"4 module self-checks; THIS IS NOT A PROOF of any theorem"
```

`check_answer(q, 999.0)` जैसे गलत जवाब को `REJECTED 3/4` मिलता है — यानी
certificate खुद को भी गलत साबित कर सकता है (`bun:nyaya` का सबक)।

---

## 3. API

| Function | क्या देता है |
|---|---|
| `alphabet()`, `charter()`, `lesson()` | 5-कदम विधि |
| `shapes()`, `seven_moves()`, `four_checks()` | 5 / 7 / 4 |
| `strip(text)`, `shape_of(text)`, `choose_move(shape, kind)` | S, U, T |
| `calc(expr)` | arithmetic evaluator |
| `solve(q)`, `check_answer(q, ans)` | जवाब + 4 जाँचें |
| `parse_question(text)`, `ask(text)`, `steps(q)` | एक-लाइन + 5 कदम |
| `course()`, `teach(i)` | 10 काम किए उदाहरण (class 1 → research) |
| `parse_catalogue(text)`, `catalogue(path)`, `catalogue_summary(cards)` | पूरा corpus |
| `status_rules()`, `measurement_notes()` | मापों की सीमा |
| `eth_evidence(root)`, `eth_bound_check()` | ETH दावे की जाँच |
| `verdict()`, `audit()` | ईमानदार निष्कर्ष + 17 self-checks |

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

## 6. अंतिम निष्कर्ष

```bun
import { verdict, audit } from "bun:sutra_sarva"
print(verdict()["research_theorems_solved_by_sutra"])   // 0
print(verdict()["research_families_mapped"])            // 373
print(audit()["verdict"])                               // CERTIFIED 17/17
```

| सवाल | उत्तर |
|---|---|
| "सब कुछ SUTRA से solve हो गया?" | **नहीं** — 373 research theorems में से 0 |
| तो क्या हुआ? | **एक आसान विधि** + **9/10 आसान सवालों के exact जवाब** + **पूरे corpus का ईमानदार नक्शा** |
| `CERTIFIED 17/17` | 17 module self-checks, किसी theorem का प्रमाण नहीं |
| ETH | **UNDER_REVIEW** |
| SUTRA है | आसान तरीका + ईमानदार नक्शा |
| SUTRA नहीं है | research mathematics का proof engine |

> **नियम:** जो solve कर सकते हैं उसका exact जवाब दो; जो नहीं, उसका साफ़
> `OUT_OF_SCOPE` **और कारण** दो।

---

## 7. चलाने के तरीके

```sh
./bin/bun examples/sutra_sarva.bun          # छोटा उदाहरण
./bin/bun tools/sutra_sarva_lab.bun         # पूरा 373-family record
python3 -m pytest -q tests/test_sutra_sarva.py   # 34 four-engine parity tests
python3 tools/check.py lib/bun/sutra_sarva.bun
```

Lab की डिलीवरी `SUTRA_SARVA_LAB_OUTPUT.txt` में **373/373 cards** और बाहर से
चलाए गए pytest का वास्तविक output append है — क्योंकि tests लिखे होना और
execute होकर pass होना अलग बातें हैं (`bun:nyaya` review point 5)।

वास्तविक बाहरी run:

```
2206 passed, 2 skipped in 1010.34s (0:16:50)   PYTEST_EXIT=0
```

पिछली public suite 2164 थी; **+34** नई parity tests और **+8**
`tests/test_selfhost.py` के auto-corpus से (नया `examples/` और `tools/` file
अपने आप 4-4 मौजूदा parity tests में जुड़े)। Lab का 612-पंक्ति output चारों
engines पर byte-for-byte समान है (`md5 6cb6c78d…`)।
