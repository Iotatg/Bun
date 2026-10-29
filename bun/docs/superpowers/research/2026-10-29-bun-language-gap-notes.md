# The gap notes of the Bamboo-api project

Date: 2026-10-29
Status: research input to the phases 26 to 32

This document is the field report of a project of about 4,500 lines of Bun
code: an HTTP server, three protocols, billing and a console. Every claim
in it was checked by running the code of the language, not by reading the
documentation. The claims were verified again against the implementation
before the phases of the fix were designed; the verification confirmed
every claim of the report, with two corrections that the report itself
records:

- `dict.values()` exists in the language; `dict.items()` does not.
- The list of the builtins holds 130 names, not 153.

The report is kept as it was written, in the language it was written in.

---

# Bun भाषा: क्या कमी है, कहाँ फँसा, और आगे क्या चाहिए

यह नोट `Bamboo-api` बनाते समय का है — लगभग 4,500 लाइन `.bun` कोड, एक HTTP सर्वर,
तीन प्रोटोकॉल, बिलिंग और एक कंसोल। नीचे हर दावा उसी रेपो पर चलाकर जाँचा गया है,
सिर्फ़ डॉक्यूमेंट पढ़कर नहीं लिखा गया।

संदर्भ: `Iotatg/Bun` — यह JavaScript का Bun रनटाइम **नहीं** है। यह Python में लिखी
एक अलग भाषा है (lexer → parser → checker → bytecode VM, और एक C बैकएंड)।
नाम की समानता सबसे पहली उलझन है।

---

## 1. जो सिंटैक्स ही नहीं है

| चीज़ | स्थिति | मुझे क्या करना पड़ा |
|---|---|---|
| `x += 1`, `-=`, `*=`, `++` | नहीं है (`unexpected token ASSIGN`) | हर जगह `x = x + 1`, `i = i + 1` |
| `a ? b : c` | नहीं है | `var out = ...` + `if/else` |
| `a ?? b` | नहीं है | `if x == null { ... }` |
| `a?.b` | नहीं है (`?` सिर्फ़ Result/Option का ऑपरेटर है) | हर जगह null-जाँच |
| backtick template literal | नहीं है | शुरू में सैकड़ों string जोड़े |
| f-string `f"{x:.2f}"` | **है** — पर मुझे देर से पता चला | बाद में जोड़ों को f-string में बदला जा सकता था |
| `switch` | नहीं है, `match` है | `match` statement है, expression नहीं — `let x = match ...` नहीं चलता |
| `import * as ns from "..."` | नहीं है | हर मॉड्यूल के exports पर हाथ से प्रीफ़िक्स (`store_`, `http_`, `billing_`) |
| class | नहीं है, `struct` + `impl` है | — |
| `"ab" * 3` | नहीं है | `.repeat(3)` |

`import` वाली कमी सबसे महँगी पड़ी: 12 मॉड्यूल, ~90 exports — सबके नाम हाथ से
बदलने पड़े, वरना `get()` जैसे नाम आपस में टकराते।

## 2. जो चुपचाप गलत नतीजा देता है (सबसे खतरनाक)

1. **`/` पूर्णांकों पर truncate करता है।** `7 / 2 == 3`, `1 / 3 == 0`।
   बिलिंग में डॉलर निकालते समय यह पैसा गायब कर देता है। मुझे `float()` डालना पड़ा।
2. **`len(str)` अक्षर गिनता है, बाइट नहीं।** `len("नमस्ते") == 6`, बाइट 18।
   HTTP में `Content-Length` बाइट्स में चाहिए — `utf8_bytes(s)` का `len` लेना पड़ा।
   यही गलती साइलेंट रूप से कटा हुआ रिस्पॉन्स देती है।
3. **`let` immutable है।** `let` से बाँधा नाम दोबारा assign नहीं हो सकता — यह
   compile-time error है। लूप काउंटर, accumulator, `let` से लिखा हर वह वेरिएबल
   जो बाद में बदलता है — सब `var` होने चाहिए। मुझे 40+ जगह `let`→`var` करना पड़ा।
4. **`+` नंबर को string बना देता है** (`"a" + 1 == "a1"`), पर `*` string पर error है।
5. **`len(dict)` type error है।** `dict.keys()` का `len` लेना पड़ा। `values()`/`items()`
   मेथड ही नहीं हैं (हाँ, `for k, v in d` चलता है)।
6. **struct बनाना positional है:** `Point(3, 4)` — `Point { x: 3 }` **नहीं**।
   enum variant `Shape.Circle(r)` है, `Shape::Circle` नहीं। Rust की आदत दो बार लड़खड़ाई।
7. **`print()` ठीक एक आर्ग्युमेंट लेता है।** `print(a, b)` error है।
8. **`sort()` बिना key/comparator के है** (`sort` की arity 0 है)। "नई से पुरानी" या
   "कीमत से" छाँटना है तो खुद लिखो — मैंने अपना insertion sort लिखा।
9. **`list.map/filter/reduce/find/forEach` कुछ नहीं है।** सब `for` लूप।
10. **error string है, टाइप नहीं।** `catch err` में सिर्फ़ संदेश मिलता है — "यह 429 है
    या 500" पहचानने के लिए मैंने संदेश में prefix डाले और उन्हें parse किया।

## 3. स्टैंडर्ड लाइब्रेरी में जो नहीं मिला

153 builtins हैं, फिर भी ये नहीं:

| कमी | असर |
|---|---|
| **regex** | रूट पैटर्न, ईमेल/की-फ़ॉर्मैट जाँच — सब हाथ से `split`/`starts_with` |
| **HMAC-SHA256** | Stripe webhook verify, JWT (HS256) असंभव; `sha256` है तो HMAC खुद बनाना पड़ेगा |
| **date/time** | सिर्फ़ `now()` → epoch float। कोई `strftime`, कोई timezone, कोई "5 मिनट पहले" नहीं। सारे टाइमस्टैम्प epoch int में रखे, फ़ॉर्मैटिंग ब्राउज़र के JS में |
| **UUID** | `random_bytes` से खुद बनाया |
| **base64url** | `base64_encode` + `-`/`_` बदलकर |
| **gzip compress** | सिर्फ़ `gzip_decompress` है — रिस्पॉन्स compress नहीं कर सकते |
| **bytes/buffer टाइप** | बाइट्स `list[int]` हैं (नीचे परफ़ॉर्मेंस देखें) |
| **HTTP client में streaming** | `http_post` पूरा बफ़र करता है; SSE के लिए मुझे raw `tcp_*` + chunked decoder खुद लिखना पड़ा (~250 लाइन) |
| **TLS server** | `tcp_tls_connect` है, `tcp_tls_listen` नहीं — HTTPS सीधे सर्व नहीं कर सकते, nginx आगे लगाना पड़ेगा |
| **HTTP/2 server** | h2 सिर्फ़ client की तरफ़ |
| **package manager** | कोई रजिस्ट्री/डिपेंडेंसी नहीं — सब कुछ stdlib + खुद का कोड |

`ffi_load()` से Python मॉड्यूल मिलते हैं, पर allowlist में `datetime` नहीं है
(`re`, `uuid`, `hashlib` हैं)। यानी तारीख़ के लिए वह रास्ता भी बंद है, और जो
रास्ता खुला है वह C बैकएंड पर काम नहीं करेगा — यानी वह भाषा का हिस्सा नहीं, बच निकलना है।

## 4. परफ़ॉर्मेंस (नापा हुआ, अंदाज़ा नहीं)

| माप | नतीजा |
|---|---|
| 3,00,000 बार का `while` लूप | **1.03 s** (CPython में वही लूप 0.049 s → ~21× धीमा) |
| 10 KB बाइट-दर-बाइट कॉपी | **39 ms** (वही 10 KB encode सिर्फ़ 0.1 ms) |
| सर्वर: `/login` (2.5 KB) | ~13 ms प्रति रिक्वेस्ट, **~75 req/s** सिंगल थ्रेड |
| 20 concurrent | **74 req/s** — बढ़ा नहीं, p95 **1.07 s** (GIL) |
| `/v1/chat/completions` (mock upstream) | ~92 req/s, p50 95 ms |
| 10 KB CSS फ़ाइल | **46 ms** प्रति रिक्वेस्ट (~250 KB/s) |
| ठंडा स्टार्ट → पहला 200 | **666 ms** (type-check + 12 मॉड्यूल) |
| 100 idle कनेक्शन | +5 MB RSS (~50 KB प्रति कनेक्शन) |
| `--engine register` | मेरे लूप पर 1.95 s — **VM से धीमा** |
| `--engine c` | `now()` को ही refuse कर दिया |

दो बातें साफ़ हैं:

- **बाइट्स `list[int]` होना सबसे बड़ी परफ़ॉर्मेंस दीवार है।** हर बाइट एक इंटरप्रेटेड
  `push` है। इसीलिए 10 KB फ़ाइल 46 ms लेती है। `bytes_append` builtin मौजूद है
  (जो `bun api` में दिखता है, मेथड टेबल में नहीं) — उससे यह 39 ms लगभग शून्य हो जाता है।
- **थ्रेड-पर-कनेक्शन + GIL = concurrency बेकार।** 20 क्लाइंट लगाने से थ्रूपुट नहीं
  बढ़ा, बस लेटेंसी बिगड़ी।

## 5. सर्वर की असली कमज़ोरी (मेरे कोड की, भाषा की भी)

- **कोई read timeout नहीं।** मैंने `tcp_set_timeout` कहीं नहीं लगाया। 20 आधे-अधूरे
  कनेक्शन भेजे → 20 थ्रेड हमेशा के लिए अटके रहे (जाँचा गया)। यह सीधा slowloris DoS है।
- **हर कनेक्शन = एक OS थ्रेड।** 1,000 क्लाइंट = 1,000 थ्रेड। यह मॉडल 100 req/s पर टिकता है,
  10,000 पर नहीं।
- **`scope`/`spawn` मौजूद हैं** पर ये असली async नहीं, थ्रेड्स हैं — इसलिए `await` जैसा
  कुछ नहीं और GIL से छुटकारा नहीं।

## 6. डॉक्स और टूलिंग

- README **2,300+ लाइन** का है और "Phase 1…25" के हिसाब से लिखा गया है। सिंटैक्स ढूँढना
  archaeological काम है। मुझे f-strings, `match`, structs, comprehensions, `with`,
  `?` ऑपरेटर — ये सब **काम करने के बाद** पता चले। इसीलिए कोड में जगह-जगह हाथ से जोड़े
  गए string और `if/else` हैं जो f-string और `match` से आधे हो सकते थे।
- `bun api` 153 builtins की सिग्नेचर देता है — **सिंटैक्स कुछ नहीं**। नए इंसान को
  भाषा का आकार ही नहीं दिखता।
- कोई LSP/editor support, कोई formatter, कोई linter नहीं। 4,500 लाइन हाथ से सजाई।
- अच्छी बात: **error messages बहुत अच्छे हैं** — लाइन, कॉलम, कारण और "hint"।
  `undefined variable`, `cannot assign to immutable variable` — ये शुरू में ही पकड़ लेते हैं।

## 7. आगे के लिए: क्या चाहिए, प्राथमिकता के क्रम में

**भाषा (छोटा काम, बड़ा फ़ायदा)**
1. `+=`, `-=`, `*=`, `/=`, `++`, `--`
2. ternary `?:` और `??`
3. `match` को expression बनाना (`let x = match ...`) — अभी हर जगह `var` + assignment
4. `import * as ns` (या `use`), वरना हर मॉड्यूल के नाम हाथ से प्रीफ़िक्स करने पड़ते हैं
5. `len(dict)`, `dict.values()`, `dict.items()`, `list.map/filter/find`, `sort(key=...)`

**स्टैंडर्ड लाइब्रेरी (प्रोडक्शन के लिए ज़रूरी)**
6. असली `bytes` टाइप + `bytes_concat`/`bytes_slice` (आज ही 100× फ़र्क़ पड़ेगा)
7. HMAC-SHA256, base64url, JWT helpers
8. date/time: `strftime`, timezone, ISO-8601 parse
9. regex
10. gzip **compress**, UUID
11. HTTP client में streaming + timeout पहले क्लास नागरिक के रूप में

**सर्वर**
12. `tcp_tls_listen` (HTTPS सीधे)
13. stdlib सर्वर में default read/write timeout, body limit, और graceful shutdown
14. HTTP/2 server

**टूलिंग**
15. LSP + formatter (4,000 लाइन के बाद यह विलासिता नहीं, ज़रूरत है)
16. serialized bytecode cache — 666 ms स्टार्टअप में से type-check हटे
17. `bun api --json` में syntax/short example भी हो, सिर्फ़ सिग्नेचर नहीं

**रोडमैप जो खुद भाषा ने टाला है** (README से): Bun में लिखा VM, serialized bytecode,
shape-based inline caches, WASM बैकएंड, optimising JIT, class patterns, nested generics।
यानी भाषा के लेखक भी जानते हैं कि रफ़्तार और टाइप सिस्टम अभी अधूरे हैं।

## 8. एक लाइन में

भाषा **सोच** में अच्छी है — static checker, struct/enum/match, Result/Option, अच्छे
error messages, और एक ही प्रोग्राम पाँच इंजनों पर। पर **रोज़मर्रा की सुविधाएँ**
(`+=`, ternary, dict/list methods, regex, date, HMAC, bytes) गायब हैं, और
इंटरप्रेटर होने की वजह से यह ~100 req/s और ~250 KB/s पर रुक जाती है।
यानी: प्रोटोटाइप, टूल, और अंदरूनी सर्विस — हाँ। बिना nginx + बिना timeout के
सार्वजनिक गेटवे — अभी नहीं।
