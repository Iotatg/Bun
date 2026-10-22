"""Tests for the AI stack: bun:ai."""

import pytest

from bun.cli import run_source
from bun.errors import BunRuntimeError, BunTypeError


def run_both(source, capsys):
    """Run the same source on both engines and assert identical output."""
    run_source(source, filename="<ai>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<ai>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    return vm_out


def run_error(source, capsys):
    """Run a source that must fail, and return the error message."""
    with pytest.raises((BunRuntimeError, BunTypeError)) as info:
        run_source(source, filename="<ai>.bun", check=True, engine="vm")
    return info.value.msg


# ---------------------------------------------------------------------------
# The layers
# ---------------------------------------------------------------------------

def test_the_linear_layer_multiplies_and_adds(capsys):
    out = run_both(
        "import { linear } from \"bun:ai\"\n"
        "import { from_list, zeros, shape_str } from \"bun:tensor\"\n"
        "let w = from_list([1.0, 0.0, 0.0, 1.0], [2, 2])\n"
        "let b = zeros([2])\n"
        "let x = from_list([1.0, 2.0, 3.0, 4.0], [2, 2])\n"
        "let y = linear(x, w, b)\n"
        "print(shape_str(y))\n"
        "print(str(y[\"data\"]))\n", capsys)
    assert out == "[2, 2]\n[1.0, 2.0, 3.0, 4.0]\n"


def test_the_gradient_of_the_linear_layer_is_the_number_by_hand(capsys):
    out = run_both(
        "import { linear, mse_loss } from \"bun:ai\"\n"
        "import { from_list, zeros, start_tape, backward, gradients, stop_tape }"
        " from \"bun:tensor\"\n"
        "let x = from_list([1.0, 2.0], [1, 2])\n"
        "let w = from_list([1.0, 0.0, 0.0, 1.0], [2, 2])\n"
        "let b = zeros([2])\n"
        "let t = from_list([0.0, 0.0], [1, 2])\n"
        "start_tape()\n"
        "let loss = mse_loss(linear(x, w, b), t)\n"
        "backward(loss)\n"
        "stop_tape()\n"
        "let g = gradients({\"w\": w, \"b\": b})\n"
        "print(str(loss[\"data\"][0]))\n"
        "print(str(g[\"w\"][\"data\"]))\n"
        "print(str(g[\"b\"][\"data\"]))\n", capsys)
    assert out == "2.5\n[1.0, 2.0, 2.0, 4.0]\n[1.0, 2.0]\n"


def test_the_cross_entropy_gradient_is_the_number_by_hand(capsys):
    out = run_both(
        "import { cross_entropy } from \"bun:ai\"\n"
        "import { from_list, start_tape, backward, gradients, stop_tape }"
        " from \"bun:tensor\"\n"
        "let logits = from_list([0.0, 0.0], [1, 2])\n"
        "start_tape()\n"
        "let loss = cross_entropy(logits, [0])\n"
        "backward(loss)\n"
        "stop_tape()\n"
        "let g = gradients({\"l\": logits})\n"
        "print(str(loss[\"data\"][0]))\n"
        "print(str(g[\"l\"][\"data\"]))\n", capsys)
    assert out == "0.6931471805599453\n[-0.5, 0.5]\n"


def test_the_embedding_picks_the_rows_of_the_table(capsys):
    out = run_both(
        "import { embedding } from \"bun:ai\"\n"
        "import { from_list, shape_str } from \"bun:tensor\"\n"
        "let table = from_list([1.0, 2.0, 3.0, 4.0], [2, 2])\n"
        "let e = embedding(table, [1, 1, 0])\n"
        "print(shape_str(e))\n"
        "print(str(e[\"data\"]))\n", capsys)
    assert out == "[3, 2]\n[3.0, 4.0, 3.0, 4.0, 1.0, 2.0]\n"


def test_the_gradient_of_the_embedding_gathers_the_rows(capsys):
    out = run_both(
        "import { embedding, mse_loss } from \"bun:ai\"\n"
        "import { from_list, zeros, start_tape, backward, gradients, stop_tape }"
        " from \"bun:tensor\"\n"
        "let table = from_list([1.0, 2.0, 3.0, 4.0], [2, 2])\n"
        "table[\"grad\"] = null\n"
        "start_tape()\n"
        "let loss = mse_loss(embedding(table, [0, 1]), zeros([2, 2]))\n"
        "backward(loss)\n"
        "stop_tape()\n"
        "let g = gradients({\"t\": table})\n"
        "print(str(g[\"t\"][\"data\"]))\n", capsys)
    # the gradient of the table is half of the values of the rows
    assert out == "[0.5, 1.0, 1.5, 2.0]\n"


def test_the_layer_normalisation_centres_the_row(capsys):
    out = run_both(
        "import { layernorm } from \"bun:ai\"\n"
        "import { from_list, ones, zeros } from \"bun:tensor\"\n"
        "let x = from_list([1.0, 2.0, 3.0, 4.0], [2, 2])\n"
        "let y = layernorm(x, ones([2]), zeros([2]), 1e-5)\n"
        "print(str(y[\"data\"]))\n", capsys)
    values = [float(item) for item in out.strip()[1:-1].split(", ")]
    assert values[0] == pytest.approx(-1.0, abs=1e-3)
    assert values[1] == pytest.approx(1.0, abs=1e-3)
    assert values[2] == pytest.approx(-1.0, abs=1e-3)
    assert values[3] == pytest.approx(1.0, abs=1e-3)


def test_the_gelu_is_the_exact_formula(capsys):
    out = run_both(
        "import { gelu } from \"bun:ai\"\n"
        "import { from_list } from \"bun:tensor\"\n"
        "let y = gelu(from_list([0.0, 1.0], [2]))\n"
        "print(str(y[\"data\"]))\n", capsys)
    # 0.5 * x * (1 + erf(x / sqrt(2))): 0.0 and 0.8413447460685429
    assert out == "[0.0, 0.8413447460685429]\n"


def test_the_linear_layer_refuses_a_bias_of_the_wrong_size(capsys):
    message = run_error(
        "import { linear } from \"bun:ai\"\n"
        "import { from_list, zeros } from \"bun:tensor\"\n"
        "let y = linear(from_list([1.0, 2.0], [1, 2]),"
        " from_list([1.0, 0.0, 0.0, 1.0], [2, 2]), zeros([3]))\n"
        "print(str(y))\n", capsys)
    assert "bias of 2 values" in message


# ---------------------------------------------------------------------------
# The model and the format
# ---------------------------------------------------------------------------

def test_the_model_runs_its_layers(capsys):
    out = run_both(
        "import { model, forward } from \"bun:ai\"\n"
        "import { from_list, zeros, shape_str } from \"bun:tensor\"\n"
        "let w = from_list([1.0, 0.0, 0.0, 1.0], [2, 2])\n"
        "let b = zeros([2])\n"
        "let m = model({\"w\": w, \"b\": b},"
        " [{\"op\": \"linear\", \"w\": \"w\", \"b\": \"b\"}])\n"
        "let y = forward(m, from_list([1.0, 2.0, 3.0, 4.0], [2, 2]))\n"
        "print(shape_str(y))\n"
        "print(str(y[\"data\"]))\n", capsys)
    assert out == "[2, 2]\n[1.0, 2.0, 3.0, 4.0]\n"


def test_the_model_counts_its_parameters(capsys):
    out = run_both(
        "import { model, param_count } from \"bun:ai\"\n"
        "import { from_list } from \"bun:tensor\"\n"
        "let m = model({\"w\": from_list([1.0, 2.0, 3.0, 4.0], [2, 2])}, [])\n"
        "print(param_count(m))\n", capsys)
    assert out == "4\n"


def test_the_model_survives_a_round_trip_through_json(capsys):
    out = run_both(
        "import { model, model_to_json, model_from_json } from \"bun:ai\"\n"
        "import { from_list, zeros } from \"bun:tensor\"\n"
        "let w = from_list([1.0, 0.0, 0.0, 1.0], [2, 2])\n"
        "let b = zeros([2])\n"
        "let m = model({\"w\": w, \"b\": b},"
        " [{\"op\": \"linear\", \"w\": \"w\", \"b\": \"b\"}])\n"
        "let back = model_from_json(model_to_json(m))\n"
        "print(str(back[\"params\"][\"w\"][\"data\"]))\n"
        "print(str(back[\"layers\"][0][\"op\"]))\n"
        "print(str(back[\"params\"][\"w\"][\"shape\"]))\n", capsys)
    assert out == "[1.0, 0.0, 0.0, 1.0]\nlinear\n[2, 2]\n"


def test_the_model_file_is_the_model_itself(capsys):
    out = run_both(
        "import { model, model_to_json } from \"bun:ai\"\n"
        "import { from_list } from \"bun:tensor\"\n"
        "let m = model({\"w\": from_list([1.0, 2.0], [2])}, [])\n"
        "print(model_to_json(m))\n", capsys)
    assert out == ("{\"kind\": \"model\", \"name\": \"model\", \"params\": {\"w\": "
                   "{\"kind\": \"tensor\", \"data\": [1.0, 2.0], \"shape\": [2]}}, "
                   "\"layers\": [], \"seed\": 0}\n")


# ---------------------------------------------------------------------------
# The training loop
# ---------------------------------------------------------------------------

XOR_X = "from_list([0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0], [4, 2])"
XOR_MODEL = (
    "let w1 = from_list([0.3, 0.4, 0.5, 0.6], [2, 2])\n"
    "let b1 = zeros([2])\n"
    "let w2 = from_list([0.1, 0.2, 0.3, 0.4], [2, 2])\n"
    "let b2 = zeros([2])\n"
    "let m = model({\"w1\": w1, \"b1\": b1, \"w2\": w2, \"b2\": b2},\n"
    "  [{\"op\": \"linear\", \"w\": \"w1\", \"b\": \"b1\"}, {\"op\": \"tanh\"},\n"
    "   {\"op\": \"linear\", \"w\": \"w2\", \"b\": \"b2\"}])\n")


def test_a_training_run_makes_the_loss_go_down(capsys):
    out = run_both(
        "import { train, model, forward } from \"bun:ai\"\n"
        "import { from_list, zeros } from \"bun:tensor\"\n"
        "let x = " + XOR_X + "\n"
        + XOR_MODEL +
        "let h = train(m, x, [0, 1, 1, 0], {\"epochs\": 120, \"batch_size\": 4,\n"
        "  \"rate\": 0.05, \"loss\": \"cross_entropy\", \"optimizer\": \"adam\","
        " \"seed\": 7})\n"
        "print(str(h[\"loss\"][0]))\n"
        "print(str(h[\"loss\"][h[\"loss\"].len() - 1]))\n"
        "let y = forward(m, x)\n"
        "print(str(y[\"data\"][0] > 0.0))\n"
        "print(str(y[\"data\"][3] > y[\"data\"][2]))\n", capsys)
    first, last, high, low = out.split("\n")[:4]
    assert float(first) > 0.6
    assert float(last) < float(first)
    # the first row is of the class zero and the second of the class one
    assert high == "true"
    assert low == "true"


def test_two_runs_with_the_same_seed_give_the_same_losses(capsys):
    source = (
        "import { train, model } from \"bun:ai\"\n"
        "import { from_list, zeros } from \"bun:tensor\"\n"
        "let x = " + XOR_X + "\n"
        + XOR_MODEL +
        "let h = train(m, x, [0, 1, 1, 0], {\"epochs\": 5, \"batch_size\": 2,\n"
        "  \"rate\": 0.05, \"loss\": \"cross_entropy\", \"optimizer\": \"adam\","
        " \"seed\": 11})\n"
        "print(str(h[\"loss\"]))\n")
    first = run_both(source, capsys)
    second = run_both(source, capsys)
    assert first == second
    assert first.count(",") == 4


def test_the_optimizer_of_the_run_is_the_one_that_was_asked_for(capsys):
    out = run_both(
        "import { train, model } from \"bun:ai\"\n"
        "import { from_list, zeros } from \"bun:tensor\"\n"
        "let x = " + XOR_X + "\n"
        + XOR_MODEL +
        "let h = train(m, x, [0, 1, 1, 0], {\"epochs\": 3, \"batch_size\": 4,\n"
        "  \"rate\": 0.01, \"loss\": \"cross_entropy\", \"optimizer\": \"sgd\","
        " \"seed\": 3})\n"
        "print(str(h[\"epoch\"]))\n", capsys)
    assert out == "[0, 1, 2]\n"


def test_the_training_loop_refuses_a_loss_it_does_not_know(capsys):
    message = run_error(
        "import { train, model } from \"bun:ai\"\n"
        "import { from_list, zeros } from \"bun:tensor\"\n"
        "let x = " + XOR_X + "\n"
        + XOR_MODEL +
        "let h = train(m, x, [0, 1, 1, 0], {\"loss\": \"hinge\"})\n"
        "print(str(h))\n", capsys)
    assert "does not know the loss 'hinge'" in message


# ---------------------------------------------------------------------------
# The tokenisers and the sampler
# ---------------------------------------------------------------------------

def test_the_word_tokeniser_counts_the_words(capsys):
    out = run_both(
        "import { word_tokenizer, encode, decode } from \"bun:ai\"\n"
        "let t = word_tokenizer(\"the cat sat\")\n"
        "print(str(t[\"ids\"]))\n"
        "print(str(t[\"vocab\"][\"cat\"]))\n"
        "print(decode(t, encode(t, \"the cat\")))\n", capsys)
    assert out == "[0, 1, 2]\n1\nthe cat\n"


def test_the_character_tokeniser_counts_the_characters(capsys):
    out = run_both(
        "import { char_tokenizer, decode } from \"bun:ai\"\n"
        "let t = char_tokenizer(\"abca\")\n"
        "print(str(t[\"ids\"]))\n"
        "print(decode(t, [0, 1, 2, 0]))\n", capsys)
    assert out == "[0, 1, 2, 0]\nabca\n"


def test_the_sampler_is_a_function_of_the_seed(capsys):
    out = run_both(
        "import { sample_sequence } from \"bun:ai\"\n"
        "let probs = [0.1, 0.2, 0.3, 0.4]\n"
        "let dists = [probs, probs, probs, probs, probs, probs]\n"
        "print(str(sample_sequence(dists, 1.0, 42)))\n"
        "print(str(sample_sequence(dists, 1.0, 42)))\n"
        "print(str(sample_sequence(dists, 1.0, 43)))\n", capsys)
    first, same, other = out.split("\n")[:3]
    assert first == same
    assert first != other


def test_the_sampler_at_zero_takes_the_most_likely_token(capsys):
    out = run_both(
        "import { sample } from \"bun:ai\"\n"
        "print(str(sample([0.1, 0.2, 0.7], 0.0, 1)))\n", capsys)
    assert out == "2\n"


# ---------------------------------------------------------------------------
# The language model
# ---------------------------------------------------------------------------

def test_the_language_model_learns_and_writes(capsys):
    out = run_both(
        "import { word_tokenizer, train_language_model, generate } from \"bun:ai\"\n"
        "let text = \"the cat sat on the mat the cat sat on the mat\"\n"
        "let tokenizer = word_tokenizer(text)\n"
        "let m = train_language_model(tokenizer, 4, 0.05, 10)\n"
        "let first = m[\"history\"][\"loss\"][0]\n"
        "let last = m[\"history\"][\"loss\"][m[\"history\"][\"loss\"].len() - 1]\n"
        "print(str(first > last))\n"
        "let out = generate(m, tokenizer, 4, 42)\n"
        "print(str(out.len() > 0))\n", capsys)
    assert out == "true\ntrue\n"


def test_the_language_model_is_a_function_of_its_seed(capsys):
    source = (
        "import { word_tokenizer, train_language_model, generate } from \"bun:ai\"\n"
        "let tokenizer = word_tokenizer(\"the cat sat on the mat\")\n"
        "let m = train_language_model(tokenizer, 4, 0.05, 5)\n"
        "print(generate(m, tokenizer, 4, 42))\n")
    first = run_both(source, capsys)
    second = run_both(source, capsys)
    assert first == second


def test_the_language_model_refuses_a_text_of_one_word(capsys):
    message = run_error(
        "import { word_tokenizer, train_language_model } from \"bun:ai\"\n"
        "let m = train_language_model(word_tokenizer(\"cat\"), 4, 0.05, 2)\n"
        "print(str(m))\n", capsys)
    assert "at least two words" in message


def test_the_language_model_takes_the_seed_of_its_tokenizer(capsys):
    """The seed of the tokenizer decides the numbers of the run."""
    out = run_both(
        "import { word_tokenizer, train_language_model } from \"bun:ai\"\n"
        "let tokenizer = word_tokenizer(\"the cat sat on the mat\")\n"
        "tokenizer[\"seed\"] = 11\n"
        "let m = train_language_model(tokenizer, 4, 0.05, 3)\n"
        "print(m[\"history\"][\"loss\"].len())\n", capsys)
    assert out == "3\n"


# ---------------------------------------------------------------------------
# The register tier
# ---------------------------------------------------------------------------

def test_the_stack_runs_on_the_register_tier(capsys):
    source = (
        "import { linear, model, forward } from \"bun:ai\"\n"
        "import { from_list, zeros } from \"bun:tensor\"\n"
        "let w = from_list([1.0, 0.0, 0.0, 1.0], [2, 2])\n"
        "let b = zeros([2])\n"
        "let m = model({\"w\": w, \"b\": b},"
        " [{\"op\": \"linear\", \"w\": \"w\", \"b\": \"b\"}])\n"
        "let y = forward(m, from_list([1.0, 2.0, 3.0, 4.0], [2, 2]))\n"
        "print(str(y[\"data\"]))\n")
    run_source(source, filename="<ai>.bun", check=True, engine="register")
    register_out = capsys.readouterr().out
    run_source(source, filename="<ai>.bun", check=True, engine="register",
               tier=True)
    tier_out = capsys.readouterr().out
    assert register_out == tier_out
    assert register_out == "[1.0, 2.0, 3.0, 4.0]\n"


# ---------------------------------------------------------------------------
# The attention
# ---------------------------------------------------------------------------

def test_the_attention_keeps_the_shape(capsys):
    out = run_both(
        "import { attention } from \"bun:ai\"\n"
        "import { from_list, shape_str } from \"bun:tensor\"\n"
        "let x = from_list([1.0, 0.0, 0.0, 1.0], [2, 2])\n"
        "let w = from_list([1.0, 0.0, 0.0, 1.0], [2, 2])\n"
        "let y = attention(x, w, w, w, 1, true)\n"
        "print(shape_str(y))\n", capsys)
    assert out == "[2, 2]\n"


def test_the_attention_of_a_causal_model_looks_backwards_only(capsys):
    """The answer of a position does not change with the positions after it."""
    out = run_both(
        "import { attention } from \"bun:ai\"\n"
        "import { from_list } from \"bun:tensor\"\n"
        "let w = from_list([1.0, 0.0, 0.0, 1.0], [2, 2])\n"
        "let first = from_list([1.0, 0.0, 0.0, 1.0], [2, 2])\n"
        "let second = from_list([1.0, 0.0, 0.5, 1.0], [2, 2])\n"
        "let a = attention(first, w, w, w, 1, true)\n"
        "let b = attention(second, w, w, w, 1, true)\n"
        "print(str(a[\"data\"][0]) + \" \" + str(a[\"data\"][1]))\n"
        "print(str(b[\"data\"][0]) + \" \" + str(b[\"data\"][1]))\n"
        "print(str(a[\"data\"][2]) + \" \" + str(b[\"data\"][2]))\n", capsys)
    lines = out.splitlines()
    # The first row does not move when the second row of the input moves.
    assert lines[0] == lines[1]
    # The second row does.
    assert lines[2].split()[0] != lines[2].split()[1]


def test_the_gradient_of_the_attention_matches_the_numbers(capsys):
    """The gradient of the attention is the number of the difference."""
    out = run_both(
        "import { attention } from \"bun:ai\"\n"
        "import { from_list, sum_tensor, start_tape, stop_tape, backward, grad }"
        " from \"bun:tensor\"\n"
        "fn loss_of(x: any, wq: any, wk: any, wv: any) -> float {\n"
        "    start_tape()\n"
        "    let total = sum_tensor(attention(x, wq, wk, wv, 2, true))\n"
        "    backward(total)\n"
        "    stop_tape()\n"
        "    return total[\"data\"][0]\n"
        "}\n"
        "let x = from_list([0.3, -0.2, 0.7, 0.1], [2, 2])\n"
        "let wq = from_list([0.5, -0.3, 0.2, 0.4], [2, 2])\n"
        "let wk = from_list([0.1, 0.6, -0.2, 0.3], [2, 2])\n"
        "let wv = from_list([0.7, 0.2, -0.4, 0.9], [2, 2])\n"
        "start_tape()\n"
        "let total = sum_tensor(attention(x, wq, wk, wv, 2, true))\n"
        "backward(total)\n"
        "stop_tape()\n"
        "let g = grad(wq)[\"data\"]\n"
        "let epsilon = 0.0001\n"
        "var index = 0\n"
        "while index < 4 {\n"
        "    let original = wq[\"data\"][index]\n"
        "    wq[\"data\"][index] = original + epsilon\n"
        "    let up = loss_of(x, wq, wk, wv)\n"
        "    wq[\"data\"][index] = original - epsilon\n"
        "    let down = loss_of(x, wq, wk, wv)\n"
        "    wq[\"data\"][index] = original\n"
        "    let numerical = (up - down) / (2.0 * epsilon)\n"
        "    let analytic = g[index]\n"
        "    var difference = numerical - analytic\n"
        "    if difference < 0.0 { difference = 0.0 - difference }\n"
        "    print(str(difference < 0.000001))\n"
        "    index = index + 1\n"
        "}\n", capsys)
    assert out == "true\ntrue\ntrue\ntrue\n"


def test_the_block_of_a_transformer_trains(capsys):
    """The loss of a block goes down when the block is trained."""
    out = run_both(
        "import { model, forward, train } from \"bun:ai\"\n"
        "import { from_list, ones } from \"bun:tensor\"\n"
        "let params = {\n"
        "    \"wq\": from_list([0.5, -0.3, 0.2, 0.4, 0.1, 0.6, -0.2, 0.3,\n"
        "                    0.7, 0.2, -0.4, 0.9, 0.3, -0.1, 0.5, 0.2], [4, 4]),\n"
        "    \"wk\": from_list([0.1, -0.2, 0.4, 0.5, 0.3, 0.1, -0.5, 0.2,\n"
        "                    0.2, 0.7, 0.1, -0.3, 0.6, 0.4, -0.1, 0.2], [4, 4]),\n"
        "    \"wv\": from_list([0.4, 0.1, -0.2, 0.6, 0.2, 0.3, 0.5, -0.1,\n"
        "                    -0.3, 0.2, 0.7, 0.4, 0.5, -0.2, 0.3, 0.1], [4, 4]),\n"
        "    \"ln1g\": ones([4]),\n"
        "    \"ln1b\": ones([4]),\n"
        "    \"ff1w\": from_list([0.2, -0.1, 0.4, 0.3, -0.2, 0.5, 0.1, 0.2,\n"
        "                     0.3, 0.1, -0.4, 0.2, 0.1, 0.3, 0.2, -0.1], [4, 4]),\n"
        "    \"ff1b\": ones([4]),\n"
        "    \"ff2w\": from_list([0.1, 0.3, -0.2, 0.4, 0.2, -0.1, 0.5, 0.3,\n"
        "                     -0.3, 0.2, 0.1, 0.6, 0.4, 0.1, -0.2, 0.3], [4, 4]),\n"
        "    \"ff2b\": ones([4]),\n"
        "    \"ln2g\": ones([4]),\n"
        "    \"ln2b\": ones([4])\n"
        "}\n"
        "let layers = [{ \"op\": \"block\", \"wq\": \"wq\", \"wk\": \"wk\","
        " \"wv\": \"wv\", \"ln1g\": \"ln1g\", \"ln1b\": \"ln1b\","
        " \"ff1w\": \"ff1w\", \"ff1b\": \"ff1b\", \"ff2w\": \"ff2w\","
        " \"ff2b\": \"ff2b\", \"ln2g\": \"ln2g\", \"ln2b\": \"ln2b\","
        " \"heads\": 2, \"causal\": true }]\n"
        "let m = model(params, layers)\n"
        "let x = from_list([0.3, -0.2, 0.7, 0.1, 0.4, 0.2, -0.1, 0.3], [2, 4])\n"
        "let target = ones([2, 4])\n"
        "let report = train(m, x, target, { \"epochs\": 3, \"rate\": 0.1 })\n"
        "let losses = report[\"loss\"]\n"
        "print(losses[losses.len() - 1] < losses[0])\n", capsys)
    assert out == "true\n"


def test_the_gradient_of_the_block_matches_the_numbers(capsys):
    """The gradient of a whole block is the number of the difference."""
    out = run_both(
        "import { model, forward } from \"bun:ai\"\n"
        "import { from_list, ones, sum_tensor, start_tape, stop_tape,"
        " backward, grad } from \"bun:tensor\"\n"
        "fn make_params() -> any {\n"
        "    return {\n"
        "        \"wq\": from_list([0.5, -0.3, 0.2, 0.4, 0.1, 0.6, -0.2, 0.3,\n"
        "                        0.7, 0.2, -0.4, 0.9, 0.3, -0.1, 0.5, 0.2], [4, 4]),\n"
        "        \"wk\": from_list([0.1, -0.2, 0.4, 0.5, 0.3, 0.1, -0.5, 0.2,\n"
        "                        0.2, 0.7, 0.1, -0.3, 0.6, 0.4, -0.1, 0.2], [4, 4]),\n"
        "        \"wv\": from_list([0.4, 0.1, -0.2, 0.6, 0.2, 0.3, 0.5, -0.1,\n"
        "                        -0.3, 0.2, 0.7, 0.4, 0.5, -0.2, 0.3, 0.1], [4, 4]),\n"
        "        \"ln1g\": ones([4]),\n"
        "        \"ln1b\": ones([4]),\n"
        "        \"ff1w\": from_list([0.2, -0.1, 0.4, 0.3, -0.2, 0.5, 0.1, 0.2,\n"
        "                         0.3, 0.1, -0.4, 0.2, 0.1, 0.3, 0.2, -0.1], [4, 4]),\n"
        "        \"ff1b\": ones([4]),\n"
        "        \"ff2w\": from_list([0.1, 0.3, -0.2, 0.4, 0.2, -0.1, 0.5, 0.3,\n"
        "                         -0.3, 0.2, 0.1, 0.6, 0.4, 0.1, -0.2, 0.3], [4, 4]),\n"
        "        \"ff2b\": ones([4]),\n"
        "        \"ln2g\": ones([4]),\n"
        "        \"ln2b\": ones([4])\n"
        "    }\n"
        "}\n"
        "fn layers() -> any {\n"
        "    return [{ \"op\": \"block\", \"wq\": \"wq\", \"wk\": \"wk\","
        " \"wv\": \"wv\", \"ln1g\": \"ln1g\", \"ln1b\": \"ln1b\","
        " \"ff1w\": \"ff1w\", \"ff1b\": \"ff1b\", \"ff2w\": \"ff2w\","
        " \"ff2b\": \"ff2b\", \"ln2g\": \"ln2g\", \"ln2b\": \"ln2b\","
        " \"heads\": 2, \"causal\": true }]\n"
        "}\n"
        "fn loss_of(x: any, params: any) -> float {\n"
        "    start_tape()\n"
        "    let m = model(params, layers())\n"
        "    let total = sum_tensor(forward(m, x))\n"
        "    backward(total)\n"
        "    stop_tape()\n"
        "    return total[\"data\"][0]\n"
        "}\n"
        "let x = from_list([0.3, -0.2, 0.7, 0.1, 0.4, 0.2, -0.1, 0.3], [2, 4])\n"
        "let params = make_params()\n"
        "start_tape()\n"
        "let m = model(params, layers())\n"
        "let total = sum_tensor(forward(m, x))\n"
        "backward(total)\n"
        "stop_tape()\n"
        "let g = grad(params[\"wq\"])[\"data\"]\n"
        "let epsilon = 0.0001\n"
        "var index = 0\n"
        "while index < 4 {\n"
        "    let original = params[\"wq\"][\"data\"][index]\n"
        "    params[\"wq\"][\"data\"][index] = original + epsilon\n"
        "    let up = loss_of(x, params)\n"
        "    params[\"wq\"][\"data\"][index] = original - epsilon\n"
        "    let down = loss_of(x, params)\n"
        "    params[\"wq\"][\"data\"][index] = original\n"
        "    let numerical = (up - down) / (2.0 * epsilon)\n"
        "    let analytic = g[index]\n"
        "    var difference = numerical - analytic\n"
        "    if difference < 0.0 { difference = 0.0 - difference }\n"
        "    print(str(difference < 0.001))\n"
        "    index = index + 1\n"
        "}\n", capsys)
    assert out == "true\ntrue\ntrue\ntrue\n"
