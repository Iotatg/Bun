# The AI Stack of Bun — Research Notes

Date: 2026-10-20
Status: Research input to the Phase 12 design of `bun:ai`.

This document records the survey work behind the AI stack of Bun. It is
not a design document — it is the *evidence* behind the decisions in the
plan `2026-10-20-bun-phase-12.md`. Every decision names the precedent it
follows and the reason it was made, and the decisions that were rejected
are recorded with the reason they were rejected.

---

## 1. What "AI models in the language" has to mean

A programming language that can *describe* a neural network is not the
same thing as a language that can *run* one. The gap between the two is
where the real work is:

| Layer | What it is | Who owns it today |
|-------|-----------|-------------------|
| The tensor | the numbers | NumPy, TensorFlow, PyTorch, MLX |
| The gradient | how the numbers move | autodiff libraries (JAX, PyTorch, TinyGrad, Burn) |
| The layer | one function of the weights | the frameworks |
| The model | a set of weights and a way to run them | the frameworks |
| The format | how a model is written to disk | safetensors, GGUF, ONNX, pickle |
| The loop | how a model is trained | the frameworks |
| The token | how text becomes numbers | tokenizers, SentencePiece, BPE |

Bun already owns the first two rows: `bun:tensor` has a reverse-mode
tape, an Adam optimizer, and the usual element-wise and matrix
operations. What is missing is rows three to seven — and they are exactly
the rows that a *user of the language* has to touch. A Bun program that
wants to classify a sentence today has to leave Bun: call Python, or
write the layers by hand.

The design question is therefore narrow and specific:

> What is the smallest set of primitives that lets a Bun program build,
> train, save, load and run a model **without leaving the language**?

The word "smallest" matters. The frameworks are large because they serve
every case at once, and they serve hardware the developer may not have.
Bun's runtime is a single Python process with no third-party packages, so
a stack that needs a GPU, a BLAS, or a compiler is a stack nobody can
run.

---

## 2. The precedent survey

### 2.1 TinyGrad and Burn — the "small is a feature" school

TinyGrad (also used by Apple's MLX) is the clearest precedent for a
language-level stack. Its thesis: the whole framework is one file, the
tensors are a dict of arrays, and the backward pass is built by walking a
tape of closures. Burn takes the same idea into Rust: a `Tensor` type
with a `backward` that is a tape of closures, and a `Trainer` that is a
struct of state.

Both accept the same trade-off: **the backward pass is recorded, not
derived**. There is no graph compiler, no operator fusion, no kernel
selection. What you get is a system you can read in an afternoon and a
system that runs anywhere Python or Rust runs.

Bun sits exactly in this position, and `bun:tensor` already made the
choice: the tape is a list of closures, one per recorded operation.

### 2.2 JAX — the "function is the graph" school

JAX traces the function, builds a graph, and compiles it. The result is
fast and the failure modes are famous: the trace only sees the paths
that the concrete shapes take, so a program with a `if` on a tensor value
compiles and then fails at run time with a shape error far from the
branch.

Bun should not copy this. A language whose errors appear far from their
cause is a language that is hard to trust, and the "feel" model of the
design puts coherence first: *one semantics per concept*. The tape gives
that: the backward pass is a walk over the operations that actually ran,
in the order they ran.

### 2.3 PyTorch — the "graph is a first-class value" school

PyTorch's `nn.Module` is a class with parameters, a `forward`, and a
state dict. It is the most used design in the field, and it is the one
Bun cannot copy directly, because Bun has no classes.

The question is what replaces it. The options:

1. **A dict with a marker key.** A model is `{"kind": "model", "params": {...}}`.
2. **A closure with captured state.** A model is a function that closes
   over its weights.
3. **A record.** Bun has `bun/records.py`, a decorator that gives a class
   the behaviour of a record — but it is a *Python-side* facility, not a
   Bun language feature, so a Bun program cannot use it.

Option 1 is the one the rest of the language already chose: `bun:tensor`
makes a tensor a plain dict with a `"kind"` marker, and `bun:sec` makes a
manifest a plain dict. The AI stack should follow the convention that
already exists rather than invent a second one. The cost is that a model
has no methods; the benefit is that a model is *data*, so it can be
written to a file, compared, and printed.

Option 2 is not lost: the forward pass of a model is a plain function, and
`sequential()` can build it out of the layer list.

### 2.4 The model format

| Format | Shape | Verdict |
|--------|-------|---------|
| safetensors | a header of shapes plus a flat binary blob | The best answer, and out of reach today: it needs a real binary writer, and the format has to agree on the endianness and the alignment. Deferred. |
| GGUF | a binary container with typed metadata | The best answer for *quantized* models. Also binary, and also deferred. |
| ONNX | a protobuf graph | The best answer for *interoperability*. Needs protobuf. Deferred. |
| pickle | Python-specific and unsafe | Never. |
| JSON | text, inspectable, safe | The only format that fits the runtime as it is. |

The decision is JSON, with one rule that keeps the door open for
safetensors later: **the on-disk shape of a model is the on-disk shape of
its parts**. A model file is a JSON object whose values are either
numbers, strings, lists, or *tensors written in the tensor's own shape*:
`{"data": [...], "shape": [...]}`. A converter to safetensors is then a
walk over that object, not a redefinition of the model.

### 2.5 The tokenizer

The honest options for text are: **word level** (split on whitespace),
**character level**, and **subword** (BPE, SentencePiece, WordPiece).

Subword is the one every real model uses, and it is the one that needs a
vocabulary file, a merge table, and a trained vocabulary — a project in
itself. Word and character level are a few lines each and are enough to
train a small language model and to show the whole loop working.

The decision: word and character tokenizers now, subword deferred, with
the *interface* fixed (`encode`/`decode` over a vocabulary dict) so that
a subword tokenizer is a drop-in replacement later.

### 2.6 Determinism

Every framework has a "seed everything" ritual, and most of them still
give different results across machines because of non-deterministic
reductions and thread-order-dependent kernels. Bun's tensor stack already
fixed the reduction order (see the header comment of `lib/bun/tensor.bun`),
and the AI stack must keep that promise:

- The random number generator is **explicit and seeded**. It is a
  function of a seed and a counter, never of the clock.
- The seed is **stored in the model**, so a saved model says how it was
  trained.
- The training loop uses **a fixed order of the samples**, so two runs
  with the same seed and the same data give the same losses, down to the
  last digit.

This is a stronger promise than "seeded" in the usual sense, and it is
the one that makes the golden corpus meaningful: a Bun program that
trains a model can have its output in the test suite.

### 2.7 Attention

A transformer needs a matrix multiply whose result is the attention
matrix — quadratic in the sequence length. In the Bun runtime every
matrix multiply is a Python-level loop over lists, so a 128-token
attention is 16 384 dot products of 128 elements in interpreted code: a
few seconds per layer, per step. A training run of a real transformer is
out of reach.

The decision: the stack ships the **recurrent** family (an MLP
classifier, a word-level language model with an embedding and a hidden
layer), and attention is deferred to a future phase that has a real
matrix kernel. A stack that ships a transformer that takes an hour per
step on a laptop would be a stack nobody uses.

---

## 3. What the stack must provide

Derived from the survey, the minimum set of primitives that lets a Bun
program build, train, save, load and run a model:

1. **Layers as module functions.** `linear(x, w, b)`, `relu(x)`,
   `gelu(x)`, `layernorm(x, gamma, beta, eps)`, `embedding(table, ids)`.
   The convention of the other stacks: a layer is a function, not a
   method.
2. **A model as data.** A model is a dict with `"kind": "model"`, a
   `"params"` dict of tensors, and a `"layers"` list that says how to run
   it.
3. **A forward pass.** `forward(model, x)`.
4. **Losses.** `mse_loss`, `cross_entropy` (numerically stable, through
   log-sum-exp).
5. **Optimizers.** `sgd` and `adam` (the latter already in `bun:tensor`),
   both updating the parameters in place and both reporting the new
   value of the parameters.
6. **A training loop.** `train(model, x, y, options)` with the epochs, the
   batch size, the learning rate, the loss function and the seed all in
   the options dict, returning the history of the losses.
7. **A model format.** `model_to_json`, `model_from_json`, `save_model`,
   `load_model`.
8. **A tokenizer.** `word_tokenizer`, `encode`, `decode`, and a
   character-level variant.
9. **Sampling.** `sample(probs, temperature, seed)` — a deterministic
   draw from a distribution, with a temperature.

---

## 4. The rejected designs

| Design | Why it was rejected |
|--------|--------------------|
| A `Model` class in Bun | Bun has no classes. The convention of dicts with a `"kind"` marker already exists in two other stacks. |
| A `Model` record via `bun/records.py` | The record facility is a Python-side decorator; a Bun program cannot use it. |
| Tracing the forward pass (JAX style) | The error appears far from the cause; the tape keeps the cause and the effect together. |
| A compiler that fuses the layers (Burn's `burn-import`) | Needs a code generator and a foreign-function interface into a compiled backend that does not exist yet. The Phase 11 C backend is the natural host for it, and it is not written yet. |
| Shipping a transformer | Quadratic attention in an interpreted matrix multiply is not usable; the recurrent family teaches the same loop. |
| A binary model format (safetensors) | Needs a binary writer; the JSON shape is the same shape, so the converter comes later without a redesign. |
| A subword tokenizer (BPE) | Needs a trained vocabulary and a merge table; the interface is fixed now so it can be added later. |
| A GPU backend | The runtime has no GPU access, and the CPU path is not fast enough to hide the difference. |

---

## 5. The acceptance criteria

The stack is done when a Bun program can do all of this, with no package
outside the language:

```bun
import { word_tokenizer, train_language_model, generate } from "bun:ai"

let tokenizer = word_tokenizer("the cat sat on the mat the cat saw the mat")
let model = train_language_model(tokenizer, 40, 0.05, 8)
print(generate(model, tokenizer, 10, 1))
```

and the result is:

- **Correct**: the gradient of a linear layer matches the value computed
  by hand (the test states the number, not a tolerance against itself).
- **Learning**: the loss of a training run on a separable dataset goes
  down, and the test asserts the first loss is above the last one.
- **Reproducible**: two runs with the same seed give the same losses, and
  the test asserts the exact list.
- **Portable**: the model survives a round trip through JSON, and the
  inference after the round trip gives the same answer.

These four criteria are the whole of the acceptance test, and each one
is a test in `tests/test_ai.py`.
