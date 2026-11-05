# `bun:pramana` — SUTRA स्तर 2: प्रमाण (the evidence layer)

> **ETH: UNRESOLVED.** यह मॉड्यूल ETH को सिद्ध या खंडित **नहीं** करता।
> यह हर दावे को बताता है कि उसे कौन-सा प्रमाण सिद्ध कर सकता है — और कौन नहीं।
> "Mystery" जो solve हुई है वह यह है: ETH क्यों unresolved है, benchmarks क्यों
> फैसला नहीं दे सकते, 2026 के AI दावों की वास्तविक स्थिति क्या है, और पिछले
> `bun:eth` में कौन-सी गणितीय त्रुटि थी।

`bun:sutra` (स्तर 1) पूछता है: **इस नियम का आकार क्या है?**
`bun:pramana` (स्तर 2) पूछता है: **इस दावे को किस प्रमाण से तय किया जा सकता है?**

लैब: `bun tools/eth_mystery_lab.bun` · उदाहरण: `examples/pramana.bun` ·
टेस्ट: `tests/test_pramana.py` (25 tests, चारों engines पर identical output)।

```bun
import { audit, can_settle, mystery_verdict } from "bun:pramana"

print(can_settle("pratyaksha", "universal-algorithm"))  // false
print(mystery_verdict()["eth"])                        // UNRESOLVED
print(audit()["verdict"])                             // CERTIFIED
```

---

## 1. छह प्रमाण

| प्रमाण | अर्थ | क्या है | किस पर quantify करता है |
|---|---|---|---|
| `pratyaksha` प्रत्यक्ष | perception | एक माप, एक run, एक सीमित table | सिर्फ ये runs |
| `anumana` अनुमान | inference | worst-case bound के साथ proof | सभी algorithms, सभी instances |
| `upamana` उपमान | comparison | किसी प्रतिबंधित model में प्रमेय | उसी model के सभी algorithms |
| `shabda` शब्द | testimony | paper, review panel, प्रेस विज्ञप्ति | सामाजिक रिकॉर्ड |
| `arthapatti` अर्थापत्ति | implication | reduction | जो reduction preserve करे |
| `anupalabdhi` अनुपलब्धि | absence | barrier | proof-विधियाँ |

`can_settle(pramana, claim_type)` यह lattice **compute** करता है, assert नहीं।
`lattice()` पूरी 6×7 तालिका देता है।

```bun
import { lattice, claim_types } from "bun:pramana"

for r in lattice() { print(r["pramana"], r["row"].len()) }
```

### केन्द्रीय प्रमेय

ETH का logical type `universal-algorithm` है ("हर algorithm के लिए, हर instance")।
`pratyaksha` का scope सिर्फ "ये runs" है। इसलिए:

```
can_settle("pratyaksha", "universal-algorithm") = false
```

यह **प्रयोग की कमज़ोरी नहीं, दावे के logical type की बात है**। सीमित table चाहे
कितनी बड़ी हो, वह `∀ algorithms` तक नहीं पहुँचती। `measurement_theorem()`
इसे `PROVED (by logical type, not by experiment)` कहता है — ईमानदार नाम, क्योंकि
यह तर्क से सिद्ध है, माप से नहीं।

---

## 2. पिछली त्रुटि: `alpha` सही invariant नहीं है

`bun:eth` ने `alpha = d(log k)/d(log n)` ("घात की घात") को ETH का निर्णायक माना।
ETH वास्तव में इसके बारे में है:

```
s(n) = log₂ T(n) / n
ETH true  ⟺  हर सही algorithm के लिए liminf s(n) > 0
ETH false ⟺  किसी एक algorithm का s(n) → 0, अर्थात T = 2^o(n)
```

2026 के AI दावों का runtime `exp(O(n/√log n))` है ([S1], [S4])। इस पर दोनों
invariant **विपरीत** उत्तर देते हैं:

| | `alpha` | `s = log₂T/n` |
|---|---|---|
| `T = exp(n/√ln n)` | `0.9295` → `exponential` | `0.866 → 0.481 → 0` → `2^o(n)` |
| पुराना निष्कर्ष | "ETH बच गया" | "ETH गिरता है" |

कारण: `k ~ n/√ln n` अब भी `n` में लगभग linear दिखता है, इसलिए `alpha → 1`;
पर `1/√ln n` धीरे-धीरे शून्य जाता है, इसलिए `s → 0`। `alpha_blindspot()` यह
विरोध machine-checked बनाता है (`contradiction: true`)।

**व्यावहारिक परिणाम**: वीडियो का "सिर्फ़ थोड़ा बेहतर than exponential ⇒ बाधा
बनी रहेगी, नतीजा valueless" वाला तर्क **गलत** है। `2^(0.99n)` में `s = 0.99 > 0`
(ETH बचा), पर `2^(n/√log n)` में `s → 0` (ETH गिरा)। दिखने में छोटा, किस्म में
बड़ा अंतर।

सभी गणनाएँ **log space** में हैं: `2^(n/√ln n)` `n = 2048` पर float overflow
करता है, `ln T` नहीं। `soft_points()`, `s_series()`, `growth_ln()` इसीलिए
`[n, ln T]` tables पर काम करते हैं।

`eth_worlds()` सही invariant के अनुसार पाँच worlds देता है; `worlds()` (तीन
`alpha`-आधारित worlds) backward compatibility के लिए रखा गया है।

---

## 3. Quantum: Grover, BBBV, और model का अंतर

| | `T` | `s` | ETH-shape | प्रमाण |
|---|---|---|---|---|
| classical brute force | `2^n` | `1.0` | true | `pratyaksha` |
| Grover / BBBV | `2^(n/2)` | `0.5` | true | `upamana` (model में सिद्ध) |
| काल्पनिक `2^o(n)` | `exp(n/√log n)` | `→ 0` | false | `anumana` आवश्यक, अभी नहीं |

Grover `2^n` assignments में `√N = 2^(n/2)` queries लेता है (`n=20` पर 1024)।
BBBV (Bennett–Bernstein–Brassard–Vazirani, *SIAM J. Comput.* 26(5):1510–1523,
1997, [S5]) सिद्ध करता है कि black-box model में `Ω(√N)` queries **आवश्यक** हैं।

यह एक सच्चा सार्वत्रिक प्रमेय है — पर **सिर्फ़ black-box model में**। 3SAT
structured है, इसलिए यह `upamana` है, real 3SAT पर `anumana` नहीं। यही स्तर 2
का मुख्य संदेश है: **model बदलने से universal claim सिद्ध हो सकता है, पर उसी
model तक सीमित रहता है**। `quantum_certificate()` में पाँच checks हैं, पाँचवाँ
`model` यह सीमा नाम देता है।

Quadratic speedup घातक को आधा करता है, आकार नहीं बदलता: `s = 0.5 > 0`।

---

## 4. Barriers और asymmetry

| वर्ष | barrier | प्रभाव |
|---|---|---|
| 1975 | Relativization (Baker–Gill–Solovay) | diagonalisation/simulation proofs नहीं चलेंगे |
| 1997 | Natural proofs (Razborov–Rudich) | "natural" circuit lower bounds अवरुद्ध |
| 2009 | Algebrization (Aaronson–Wigderson) | algebraic तरीकों तक barrier फैला |
| 1999 | `ETH ⟹ P ≠ NP` | ETH **सिद्ध** करने का मतलब P≠NP सिद्ध करना — तीनों barriers पार |
| 2001 | Sparsification (Impagliazzo–Paturi–Zane) | `m = O(n)` वाले 3SAT पर `2^o(n)` algorithm ETH गिराएगा |

2026 के दावे sparsification वाली जगह पर हैं: linear-size CNF पर
`exp(O(n/√log n))`। इसलिए **यदि** worst-case bound सिद्ध हो, तो यह वास्तव में
ETH को खंडित करता है — "सिर्फ़ थोड़ा बेहतर" नहीं।

`asymmetries()`: एक witness (`∃ algorithm + ∀ instances` proof) universal claim
को झुठला सकता है; कोई भी संख्या witnesses उसे सिद्ध नहीं कर सकती। यही कारण है
कि ETH 1999 से खुला है।

---

## 5. 2026 claim ledger

`timeline()` में 10 तारीखवार घटनाएँ (1955 Nash पत्र → 2026-11-05) और
`sources()` में 5 URL-सहित स्रोत हैं। `claims()` में 13 दावे; `adjudicate_all()`
हर एक का निर्णय **lattice से** निकालता है, hard-coded string से नहीं।

| Verdict | अर्थ |
|---|---|
| `CERTIFIED` | प्रमाण दावे के type तक पहुँचता है |
| `REFUTED` | तार्किक त्रुटि, या प्रमाण गलत type का |
| `OUT_OF_REACH` | गणितीय रूप से सही, पर सिर्फ़ proof से — माप से नहीं |
| `UNDER_REVIEW` | दावा मौजूद, स्वतंत्र सत्यापन अधूरा |
| `INCONSISTENT` | adjudicator की self-check विफल (किसी claim पर नहीं आना चाहिए) |

मुख्य निर्णय: `ai-disproof-accepted` → **UNDER_REVIEW**; `panel-certified` →
**REFUTED** ([S1] की खुली चिट्ठी: "हमारी भागीदारी को प्रमाणन न समझा जाए");
`lean-verifies-claim` → **REFUTED** (Lean derivation जाँचता है, premises का
वास्तविक समस्या से मेल नहीं); `sutra-solved-eth` → **REFUTED** (आपका सुधार)।

---

## 6. ETH settle करने के लिए ठीक क्या चाहिए

`ETH is FALSE`: एक explicit algorithm + **हर instance** के लिए worst-case
`2^o(n)` का proof + समुदाय द्वारा स्वतंत्र जाँच + formal derivation का informal
statement से मेल + raw data सार्वजनिक। स्थिति: 2026-10-16/26 को दावा,
2026-11-05 तक UNDER_REVIEW।

`ETH is TRUE`: **हर** algorithm के लिए `2^(sn), s>0` lower bound, non-relativizing /
non-natural / non-algebrizing तकनीक से — जो P≠NP भी सिद्ध करे। कोई ज्ञात रास्ता नहीं।

`ETH is UNRESOLVED`: यही वर्तमान, **CERTIFIED** स्थिति।

---

## 7. अंतिम निष्कर्ष

```
mystery_verdict()["eth"]     = "UNRESOLVED"
mystery_verdict()["mystery"] = "SOLVED"
```

ये दो अलग प्रश्न हैं। SUTRA ने ETH को solve नहीं किया — उसने ETH से जुड़े
दावों का विश्लेषण और परीक्षण किया। जो **solve** हुआ वह है: क्यों unresolved है,
कौन-सा प्रमाण क्या तय कर सकता है, वीडियो और हमारे अपने कोड की `alpha` त्रुटि,
quantum की सीमा, और 2026 के दावों की सही स्थिति।

`audit()` दस checks चलाता है (छह प्रमाण, measurement limit, alpha contradiction,
Grover संख्या, quantum shape, ledger consistency, honesty, timeline, sources) →
`CERTIFIED 10/10`। `lesson()` यह विधि आठ कदमों में सिखाता है।

---

## 8. स्रोत

| ID | तारीख | स्रोत |
|---|---|---|
| S1 | 2026-10-28 | [Titanium Media — OpenAI宣布推翻ETH，科学家没有鼓掌](https://www.tmtpost.com/agent/ai-article/21665) |
| S2 | 2026-10-30 | [Zhihu — 两个AI同一天宣称证伪ETH](https://zhuanlan.zhihu.com/p/2100499549123102602) |
| S3 | 2026-10-28 | [Sina — OpenAI和Anthropic都推翻ETH，哪家证明更靠谱?](https://cj.sina.com.cn/articles/view/9053721674/21ba4d44a07201ewz8) |
| S4 | 2026-10-28 | [Bilibili — Anthropic《A 2^o(n) Time Algorithm for 3-SAT》](https://www.bilibili.com/video/BV176sZ6tECa/) |
| S5 | 1997 | [Bennett et al., *Strengths and weaknesses of quantum computing*](https://cims.nyu.edu/~regev/toc/articles/v002a001/bibliography.html) |

> **नोट**: S1–S4 पत्रकारिता/सामुदायिक स्रोत हैं, स्वयं peer-reviewed papers नहीं।
> इसीलिए ledger में इनका type `social-record` है और कोई भी दावा `CERTIFIED`
> नहीं हुआ — सिवाय उन statements के जो तर्क या स्थापित प्रमेय से सिद्ध हैं।
