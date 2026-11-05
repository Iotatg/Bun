# `bun:nyaya` — SUTRA स्तर 3: न्याय (the self-challenging verifier)

> **ETH: UNRESOLVED.** स्तर 3 भी ETH को सिद्ध या खंडित **नहीं** करता।
> यह **theorem-statements** की जाँच करता है — और सबसे अहम बात: यह स्तर 2
> और **खुद अपने** द्वारा जारी किए गए certificates को reject करता है।
> एक verifier जो अपने निष्कर्ष को चुनौती न दे सके, verifier नहीं, cheerleader है।

| स्तर | मॉड्यूल | सवाल |
|---|---|---|
| 1 | `bun:sutra` | इस नियम का **आकार** क्या है? |
| 2 | `bun:pramana` | इस दावे को कौन-सा **प्रमाण** तय कर सकता है? |
| **3** | **`bun:nyaya`** | **क्या मेरा निष्कर्ष खुद सही है?** |

लैब: `bun tools/nyaya_lab.bun` (345-पंक्ति end-to-end रिकॉर्ड) · उदाहरण:
`examples/nyaya.bun` · tests: `tests/test_nyaya.py` (28 tests, चारों engines पर
byte-for-byte समान)।

---

## 1. यह मॉड्यूल क्यों बना

सार्वजनिक commit [`d43dec0`](https://github.com/Iotatg/Bun) (`Main`, 8 files,
1538 insertions, 2 deletions, `pramana.bun` 549 lines, 25 parity tests) की एक
स्वतंत्र AI code-review में चार बातें कही गईं। उनमें से **पहली एक सच्ची
गणितीय त्रुटि** थी:

> "ETH ⟺ ∀A, liminf s(n) > 0 — यह ज़रूरत से ज़्यादा मज़बूत formulation है।
> हर algorithm के लिए positive liminf आवश्यक होने का दावा अलग से justify
> करना होगा।"

यह सही है, और इससे भी बुरा: Level 2 के `eth_statement()` की अपनी दो पंक्तियाँ
एक-दूसरे की **logical complement नहीं** थीं।

| फ़ील्ड | स्ट्रिंग (`d43dec0`) |
|---|---|
| `invariant` | `ETH true <=> liminf s > 0 for every correct algorithm` |
| `equivalent` | `ETH false <=> some algorithm has s(n) -> 0 (T = 2^o(n))` |

`liminf s > 0` का negation `liminf s = 0` है, `s(n) → 0` **नहीं**। यानी दोनों
पंक्तियाँ मिलकर कोई valid equivalence नहीं बनाती थीं।

---

## 2. De Morgan: गलती को हाथ से नहीं, machine से पकड़ना

`s(n) ≥ 0` के लिए हर asymptotic statement तीन quantifiers `(eps, N, n≥N)`
और एक relation से बनता है। Negation = **हर quantifier पलटो + relation पलटो**।

| statement | prefix | अर्थ |
|---|---|---|
| `liminf s > 0` | `E eps  E N  A n : s(n) >= eps` | हर बड़े n पर कठिनाई |
| `limsup s > 0` | `E eps  A N  E n : s(n) >= eps` | अनंत lengths पर कठिनाई |
| `s(n) → 0` | `A eps  E N  A n : s(n) < eps` | सचमुच `2^o(n)` |
| `liminf s = 0` | `A eps  A N  E n : s(n) < eps` | सिर्फ़ एक subsequence आसान |

```bun
import { complement_check, level2_review, level3_fix_check } from "bun:nyaya"

print(complement_check("liminf-positive", "s-to-zero")["verdict"])
print(level2_review()["verdict"])
print(level3_fix_check()["verdict"])
```

```
NOT_COMPLEMENTARY
REJECTED
COMPLEMENTARY
```

**सही formulation:**

```
ETH true   ⟺  हर सही A के लिए  limsup_n s_A(n) > 0   (s(n) → 0 नहीं)
ETH false  ⟺  कोई A जिसका  s_A(n) → 0, अर्थात T = 2^o(n)
```

ETH `limsup` पर बोलता है: कोई algorithm sparse input-lengths पर तेज़ हो और
बाकी अनंत lengths पर धीमा, तो ETH **नहीं** टूटता। `liminf > 0` हर बड़े n पर
कठिनाई माँगता है — यह ETH से ज़्यादा मज़बूत है और ETH का axiom नहीं है।
`monotone-runtime` assumption को `assumptions()` में स्पष्ट रूप से
`eth_grants: false` चिह्नित किया गया है।

**Uniformity** (review का "अलग से justify करना होगा"): `∀A limsup > 0` से
`∃eps>0 ∀A limsup ≥ eps` पाने के लिए **triangular diagonalisation** चाहिए —
`A_k` लो जो `n ≥ N_k` पर `s ≤ 1/k` दे, और size n पर सबसे बड़ा `k` चलाओ।
`uniformity_lemma()` इसके तीन assumptions (`worst-case`, `enumeration`,
`triangular`) को ledger में दर्ज करता है।

---

## 3. Counterexample witness — वैचारिक गलती अलग, measurement artifact अलग

पहले कोशिश थी finite window से `liminf` का अंदाज़ा लगाने की। वह **गलत** निकली:
धीरे-धीरे घटने वाली sequence (`soft-exp`) पर numeric threshold भी फेल होता है,
जो एक measurement artifact है, वैचारिक त्रुटि नहीं। इसलिए अंतिम डिज़ाइन:

- **निर्णय नियम** विश्लेषणात्मक लेबल (`liminf`, `tends_zero`, `truth`) पर चलते हैं — ये गणितीय तथ्य हैं, अनुमान नहीं।
- `sequence_stats()` **स्वतंत्र numeric साक्षी** है; `numeric_agrees()` जाँचता है कि proxies लेबल से मेल खाते हैं।
- `finite-bench` witness `UNDECIDABLE` लौटाता है — छह माप-बिंदुओं से asymptotic फैसला नहीं होता (review का point 5)।

| witness | truth | `liminf` rule | `limsup` rule |
|---|---|---|---|
| `constant-0.99` | ETH_TRUE | ETH_TRUE | ETH_TRUE |
| `grover-0.50` | ETH_TRUE | ETH_TRUE | ETH_TRUE |
| **`sparse-dips`** | **ETH_TRUE** | **ETH_FALSE ✗** | **ETH_TRUE** |
| `finite-bench` | UNDECIDABLE | UNDECIDABLE | UNDECIDABLE |
| `soft-exp` | ETH_FALSE | ETH_FALSE | ETH_FALSE |
| `polynomial-3` | ETH_FALSE | ETH_FALSE | ETH_FALSE |

`sparse-dips`: `s = 0.5`, सिवाय `k = j²` पर जहाँ `s = 1/k`। तब
`liminf = 0` पर `limsup = 0.5`, यानी `s(n) → 0` नहीं — कोई `2^o(n)` algorithm
नहीं। `liminf` rule इसे ETH-खंडन बताता है (false positive), `limsup` rule नहीं।

```bun
import { challenge_rules } from "bun:nyaya"

let c = challenge_rules()
print(c["old_errors"], c["new_errors"], c["breaking_witness"])
print(c["verdict"])
```

```
1 0 sparse-dips
CORRECTED_RULE_SURVIVES
```

---

## 4. Reduction correctness और quantum model-bound

`reduction_check()` सात अलग-अलग जाँचें करता है: `total-map`,
`answer-preserving`, `linear-size`, `subexp-reduction`, `all-eps`,
`model-restriction`, `worst-case`।

| reduction | verdict | कारण |
|---|---|---|
| `sparsification` (IPZ 2001) | **VALID** | `≤ 2^(eps·n)` sparse formulas, **हर** `eps>0` के लिए |
| `naive-branching` | INVALID | fixed `eps = 0.5`; `all-eps` और `subexp-reduction` फेल |
| `bbbv-to-3sat` | INVALID | black-box model से structured 3SAT पर अवैध transfer |
| `grover-to-3sat` | INVALID | वही, और `s = 0.5 > 0` |
| `eth-implies-pneqnp` | VALID | एक-तरफ़ा implication; converse इस्तेमाल नहीं हुआ |

BBBV 1997 का `Ω(√N)` सच्चा सार्वत्रिक प्रमेय है — पर **सिर्फ़ unstructured
black-box search** के लिए। Grover `2^(n/2)` देता है यानी `s = 0.5 > 0`; कोई
भी quantum speedup ETH का आकार नहीं बदलता। Review का point 4 यहीं enforce हुआ।

---

## 5. Formal proof ↔ natural-language theorem

एक Lean file **premises से derivation** जाँचती है; वह यह नहीं जाँचती कि premises
अंग्रेज़ी वाले theorem से मेल खाते हैं, न ही कि theorem `∀ algorithms` के बारे
में है। `translation_table()` में चार phrases के पास कोई formal counterpart नहीं:

| phrase | gap |
|---|---|
| "Lean 4 verified" | premises / NL↔formal bridge unchecked |
| "press release / news coverage" | testimony, `can_settle` false |
| "review panel participation certifies" | authority ≠ proof |
| "benchmarks show" | finite `∃ runs` ≠ `∀ algorithms` |

Review के point 2 (`CERTIFIED 10/10` = दस module self-checks, ETH का प्रमाण नहीं)
और point 3 (2026 AI claims `UNDER_REVIEW`) यहीं false-positive cases बने हैं।

---

## 6. False-positive certificate detection — self-challenge

`certificates()` में 11 certificates हैं, जिनमें **दो स्तर 2 द्वारा** और **एक
`bun:nyaya` खुद द्वारा** जारी। `adjudicate_certificate()` हर एक को computed
checks से फैसला देता है (कोई hardcoded verdict नहीं):

```bun
import { false_positive_scan, self_challenge, audit } from "bun:nyaya"

print(false_positive_scan()["verdict"])
print(self_challenge()["verdict"])
print(audit()["verdict"], audit()["passed"], audit()["total"])
```

```
ALL_FALSE_POSITIVES_CAUGHT
SELF_CHALLENGE_PASSED
CERTIFIED 13 13
```

- **10/10 false positives पकड़े गए**; 11वाँ (सही invariant) `ACCEPTED`।
- `nyaya-self-certified` → `REJECTED`: कोई verifier अपनी correctness खुद
  certify नहीं कर सकता।
- `audit()` के 13 checks में से एक **"execution-not-self-verified"** है:
  `execution_receipt()["self_verifiable"] = false`।

---

## 7. लिखे गए tests और चलाए गए tests अलग हैं

> "GitHub diff में tests लिखे हुए दिखना और उनका वास्तव में execute होकर pass
> होना अलग बातें हैं।" — review का अंतिम बिंदु, स्वीकार।

`bun:nyaya` इस बात को **code में मानता है**: execution का certificate
`pratyaksha` (माप) है, और verifier एक ही साथ witness और judge नहीं हो सकता।
इसलिए डिलीवर किया गया `NYAYA_LAB_OUTPUT.txt` मॉड्यूल के अंदर से नहीं, बल्कि
बाहर से चलाए गए `python3 -m pytest -q` के **वास्तविक output** को append करता
है। रिपोर्ट में वही अंक दर्ज हैं।

---

## 8. अंतिम उत्तर

| सवाल | उत्तर |
|---|---|
| ETH सिद्ध/खंडित हुआ? | **नहीं — UNRESOLVED** |
| `d43dec0` का `liminf` theorem-statement? | **SOLVED** (limsup, De Morgan से सत्यापित) |
| स्तर 3 का `audit()` | `CERTIFIED 13/13` — **module self-checks**, ETH प्रमाण नहीं |
| 2026 AI दावे | `UNDER_REVIEW` |
| क्या चाहिए? | explicit algorithm + हर instance पर worst-case `2^o(n)` का स्वतंत्र रूप से जाँचा proof (`settle_conditions()`) |

ETH पर नहीं, **अपनी गलती पर** फैसला मिला। यही स्तर 3 की power है।
