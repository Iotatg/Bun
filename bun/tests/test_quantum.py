"""Tests for bun:quantum — the statevector simulator."""

import pytest

from bun.cli import run_source
from bun.errors import BunRuntimeError, BunTypeError

Q = "import { state, h, x, y, z, apply, apply_matrix, controlled, cnot, cz, " \
    "swap, toffoli, phase, rotate_x, rotate_y, rotate_z, probabilities, " \
    "probability, probability_one, norm, normalize, amplitudes, measure, " \
    "sample, run, bit_string, bell, ghz, w_state, circuit, qft, grover, " \
    "grover_rounds, expectation, bloch, entropy, fidelity, to_string, " \
    "gate, complex, cadd, cmul, cabs2, cphase, qubits, dimension, " \
    "slow_apply_matrix, slow_controlled, phase_flip_all_ones } " \
    "from \"bun:quantum\"\n"


def run_both(source, capsys):
    """Run the same source on every engine and assert identical output."""
    run_source(source, filename="<quantum>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<quantum>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    run_source(source, filename="<quantum>.bun", check=True, engine="register")
    assert capsys.readouterr().out == vm_out
    run_source(source, filename="<quantum>.bun", check=True, engine="register",
               tier=True)
    assert capsys.readouterr().out == vm_out
    return vm_out


def run_error(source):
    with pytest.raises((BunRuntimeError, BunTypeError)) as info:
        run_source(source, filename="<quantum>.bun", check=True, engine="vm")
    return info.value.msg


def number(text):
    return float(text.strip())


# ---------------------------------------------------------------------------
# The gates
# ---------------------------------------------------------------------------

def test_a_fresh_state_is_all_zeros(capsys):
    out = run_both(Q + "let s = state(3)\nprint(probabilities(s))\n", capsys)
    assert out.strip() == "[1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]"


def test_x_flips_a_qubit(capsys):
    out = run_both(Q + "print(probabilities(x(state(1), 0)))\n", capsys)
    assert out.strip() == "[0.0, 1.0]"


def test_hadamard_twice_is_the_identity(capsys):
    out = run_both(Q + "let s = h(h(state(1), 0), 0)\nprint(probability(s, 0))\n",
                   capsys)
    assert abs(number(out) - 1.0) < 1e-12


def test_the_hadamard_makes_an_even_split(capsys):
    out = run_both(Q + "print(probability(h(state(1), 0), 0))\n", capsys)
    assert abs(number(out) - 0.5) < 1e-12


def test_the_phase_gate_keeps_the_probability(capsys):
    out = run_both(Q + "let s = phase(x(state(1), 0), 0, 1.5)\n"
                        "print(probabilities(s))\n"
                        "print(cabs2(amplitudes(s)[1]))\n", capsys)
    first, second = out.strip().splitlines()
    assert first == "[0.0, 1.0]"
    assert abs(number(second) - 1.0) < 1e-12


def test_a_rotation_of_a_whole_turn_returns_the_state(capsys):
    out = run_both(Q + "let s = rotate_y(state(1), 0, 6.283185307179586)\n"
                        "print(probability(s, 0))\n", capsys)
    assert abs(number(out) - 1.0) < 1e-9


def test_a_half_turn_of_rotate_x_flips_the_bit(capsys):
    out = run_both(Q + "let s = rotate_x(state(1), 0, 3.141592653589793)\n"
                        "print(probability(s, 1))\n", capsys)
    assert abs(number(out) - 1.0) < 1e-9


def test_every_named_gate_is_a_matrix(capsys):
    out = run_both(Q + "for name in [\"i\", \"x\", \"y\", \"z\", \"h\", \"s\", "
                        "\"sdg\", \"t\", \"tdg\"] {\n"
                        "  print(name, gate(name).len())\n}\n", capsys)
    assert out.strip().splitlines() == ["%s 2" % n for n in
                                        ["i", "x", "y", "z", "h", "s", "sdg",
                                         "t", "tdg"]]


# ---------------------------------------------------------------------------
# Two qubits
# ---------------------------------------------------------------------------

def test_cnot_entangles(capsys):
    out = run_both(Q + "let s = bell()\n"
                        "print(probability(s, 0))\n"
                        "print(probability(s, 1))\n"
                        "print(probability(s, 2))\n"
                        "print(probability(s, 3))\n", capsys)
    p00, p01, p10, p11 = [number(v) for v in out.strip().splitlines()]
    assert abs(p00 - 0.5) < 1e-12
    assert abs(p11 - 0.5) < 1e-12
    assert p01 == 0.0 and p10 == 0.0


def test_cnot_does_nothing_when_the_control_is_zero(capsys):
    out = run_both(Q + "let s = cnot(state(2), 0, 1)\n"
                        "print(probabilities(s))\n", capsys)
    assert out.strip() == "[1.0, 0.0, 0.0, 0.0]"


def test_cnot_flips_when_the_control_is_one(capsys):
    out = run_both(Q + "let s = cnot(x(state(2), 0), 0, 1)\n"
                        "print(probabilities(s))\n", capsys)
    assert out.strip() == "[0.0, 0.0, 0.0, 1.0]"


def test_swap_exchanges_two_qubits(capsys):
    out = run_both(Q + "let s = x(state(2), 0)\n"
                        "print(bit_string(sample(s), 2))\n"
                        "let t = swap(s, 0, 1)\n"
                        "print(probabilities(t))\n", capsys)
    assert out.strip().splitlines() == ["01", "[0.0, 0.0, 1.0, 0.0]"]


def test_toffoli_needs_both_controls(capsys):
    out = run_both(Q + "let one = toffoli(x(state(3), 0), 0, 1, 2)\n"
                        "print(probability(one, 7))\n"
                        "let two = toffoli(x(x(state(3), 0), 1), 0, 1, 2)\n"
                        "print(probability(two, 7))\n", capsys)
    first, second = out.strip().splitlines()
    assert number(first) == 0.0
    assert abs(number(second) - 1.0) < 1e-12


def test_cz_adds_a_phase_only_on_eleven(capsys):
    out = run_both(Q + "let s = h(h(state(2), 0), 1)\n"
                        "let t = cz(s, 0, 1)\n"
                        "print(cabs2(amplitudes(t)[0]))\n"
                        "print(cabs2(amplitudes(t)[3]))\n"
                        "print(cphase(amplitudes(t)[3]))\n", capsys)
    lines = out.strip().splitlines()
    assert abs(number(lines[0]) - 0.25) < 1e-12
    assert abs(number(lines[1]) - 0.25) < 1e-12
    assert abs(abs(number(lines[2])) - 3.141592653589793) < 1e-9


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------

def test_measurement_collapses_and_renormalizes(capsys):
    # The outcome is random, so this runs once rather than on every engine.
    run_source(Q + "let s = h(state(1), 0)\n"
                   "let m = measure(s, 0)\n"
                   "let p = probabilities(m[\"state\"])\n"
                   "print(p[m[\"outcome\"]])\n",
               filename="<quantum>.bun", check=True, engine="vm")
    assert abs(number(capsys.readouterr().out) - 1.0) < 1e-12


def test_a_certain_qubit_always_reads_the_same(capsys):
    out = run_both(Q + "let s = x(state(2), 0)\n"
                        "var ones = 0\n"
                        "var i = 0\n"
                        "while i < 50 {\n"
                        "  let m = measure(s, 0)\n"
                        "  ones = ones + m[\"outcome\"]\n"
                        "  i = i + 1\n}\n"
                        "print(ones)\n", capsys)
    assert out.strip() == "50"


def test_shots_agree_with_the_amplitudes(capsys):
    out = run_both(Q + "let counts = run(bell(), 2000)\n"
                        "print(counts[\"00\"] + counts[\"11\"])\n", capsys)
    assert out.strip() == "2000"


def test_bell_never_produces_01_or_10(capsys):
    out = run_both(Q + "let counts = run(bell(), 500)\n"
                        "var other = 0\n"
                        "for key in counts {\n"
                        "  if key != \"00\" and key != \"11\" {\n"
                        "    other = other + counts[key]\n"
                        "  }\n}\n"
                        "print(other)\n", capsys)
    assert out.strip() == "0"


def test_bit_string_is_read_from_the_top_qubit(capsys):
    out = run_both(Q + "print(bit_string(5, 3))\nprint(bit_string(1, 4))\n",
                   capsys)
    assert out.strip().splitlines() == ["101", "0001"]


# ---------------------------------------------------------------------------
# The named states
# ---------------------------------------------------------------------------

def test_ghz_has_two_branches(capsys):
    out = run_both(Q + "let s = ghz(4)\n"
                        "print(probability(s, 0))\n"
                        "print(probability(s, 15))\n"
                        "print(probability(s, 7))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[0] - 0.5) < 1e-12
    assert abs(lines[1] - 0.5) < 1e-12
    assert lines[2] == 0.0


def test_w_state_has_one_qubit_set(capsys):
    out = run_both(Q + "let s = w_state(4)\n"
                        "print(probability(s, 1))\n"
                        "print(probability(s, 0))\n"
                        "print(probability(s, 3))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[0] - 0.25) < 1e-12
    assert lines[1] == 0.0
    assert lines[2] == 0.0


def test_entropy_counts_the_branches(capsys):
    out = run_both(Q + "print(entropy(state(3)))\n"
                        "print(entropy(ghz(3)))\n"
                        "var u = state(3)\n"
                        "var i = 0\n"
                        "while i < 3 {\n"
                        "  u = h(u, i)\n"
                        "  i = i + 1\n}\n"
                        "print(entropy(u))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert lines[0] == 0.0
    assert abs(lines[1] - 1.0) < 1e-12
    assert abs(lines[2] - 3.0) < 1e-12


# ---------------------------------------------------------------------------
# Circuits and algorithms
# ---------------------------------------------------------------------------

def test_a_circuit_runs_its_operations_in_order(capsys):
    out = run_both(Q + "let ops = [{\"gate\": \"h\", \"targets\": [0]}, "
                        "{\"gate\": \"cx\", \"targets\": [0, 1]}]\n"
                        "let s = circuit(2, ops)\n"
                        "print(probability(s, 0))\n"
                        "print(probability(s, 3))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[0] - 0.5) < 1e-12
    assert abs(lines[1] - 0.5) < 1e-12


def test_the_qft_of_a_basis_state_is_uniform(capsys):
    out = run_both(Q + "let s = qft(state(3))\n"
                        "for p in probabilities(s) { print(p) }\n", capsys)
    for value in out.strip().splitlines():
        assert abs(number(value) - 0.125) < 1e-12


def test_grover_finds_the_marked_index(capsys):
    out = run_both(Q + "let s = grover(3, 5, grover_rounds(3))\n"
                        "print(probability(s, 5))\n", capsys)
    assert abs(number(out) - 0.9453125) < 1e-6


def test_grover_rounds_follows_the_square_root(capsys):
    out = run_both(Q + "print(grover_rounds(3))\nprint(grover_rounds(10))\n",
                   capsys)
    assert out.strip().splitlines() == ["2", "25"]


def test_grover_reaches_certainty_when_the_space_is_four(capsys):
    # Four items, one round: the rotation lands exactly on the answer.
    out = run_both(Q + "let s = grover(2, 2, 1)\n"
                        "print(probability(s, 2))\n", capsys)
    assert abs(number(out) - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# What the state means
# ---------------------------------------------------------------------------

def test_the_bloch_vector_of_a_basis_state_points_up(capsys):
    out = run_both(Q + "print(bloch(state(1), 0))\n"
                        "print(bloch(x(state(1), 0), 0))\n", capsys)
    assert out.strip().splitlines() == ["[0.0, 0.0, 1.0]", "[0.0, 0.0, -1.0]"]


def test_the_bloch_vector_of_a_plus_state_points_along_x(capsys):
    out = run_both(Q + "let b = bloch(h(state(1), 0), 0)\n"
                        "print(b[0])\nprint(b[2])\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[0] - 1.0) < 1e-9
    assert abs(lines[1]) < 1e-9


def test_expectation_of_z_is_the_population_difference(capsys):
    out = run_both(Q + "let mz = [[[1.0, 0.0], [0.0, 0.0]], "
                        "[[0.0, 0.0], [-1.0, 0.0]]]\n"
                        "print(expectation(rotate_y(state(1), 0, 1.0471975512), mz, 0))\n",
                   capsys)
    assert abs(number(out) - 0.5) < 1e-6


def test_fidelity_is_one_for_one_state(capsys):
    out = run_both(Q + "print(fidelity(bell(), bell()))\n"
                        "print(fidelity(state(2), bell()))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[0] - 1.0) < 1e-12
    assert abs(lines[1] - 0.5) < 1e-12


def test_normalize_repairs_a_hand_written_state(capsys):
    out = run_both(Q + "var s = state(1)\n"
                        "s[\"amp\"][0] = [2.0, 0.0]\n"
                        "s[\"amp\"][1] = [2.0, 0.0]\n"
                        "print(norm(s))\n"
                        "print(probability(normalize(s), 0))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[0] - 2.8284271247461903) < 1e-12
    assert abs(lines[1] - 0.5) < 1e-12


def test_the_complex_helpers_multiply_like_complex_numbers(capsys):
    out = run_both(Q + "let a = complex(1.0, 2.0)\n"
                        "let b = complex(3.0, -1.0)\n"
                        "print(cmul(a, b))\n"
                        "print(cadd(a, b))\n"
                        "print(cabs2(a))\n", capsys)
    assert out.strip().splitlines() == ["[5.0, 5.0]", "[4.0, 1.0]", "5.0"]


def test_the_state_reports_its_width(capsys):
    out = run_both(Q + "print(qubits(state(5)))\nprint(dimension(state(5)))\n",
                   capsys)
    assert out.strip().splitlines() == ["5", "32"]


def test_to_string_lists_the_branches(capsys):
    out = run_both(Q + "print(to_string(bell()))\n", capsys)
    assert "|00>" in out and "|11>" in out and "p = 0.4" in out


# ---------------------------------------------------------------------------
# The errors
# ---------------------------------------------------------------------------

def test_an_unknown_gate_is_an_error():
    message = run_error(Q + "print(gate(\"hx\"))\n")
    assert "unknown gate" in message


def test_a_qubit_out_of_range_is_an_error():
    message = run_error(Q + "print(apply(state(2), \"h\", 5))\n")
    assert "out of range" in message


def test_a_gate_on_a_non_state_is_an_error():
    message = run_error(Q + "print(apply(3, \"h\", 0))\n")
    assert "quantum state" in message


def test_grover_refuses_a_marked_index_outside_the_space():
    message = run_error(Q + "print(grover(2, 9, 1))\n")
    assert "out of range" in message


# ---------------------------------------------------------------------------
# The native fast path
# ---------------------------------------------------------------------------

def test_the_runtime_carries_the_native_path(capsys):
    out = run_both(Q + "print(has_builtin(\"quantum_apply\"))\n"
                        "print(has_builtin(\"no_such_builtin\"))\n", capsys)
    assert out.strip().splitlines() == ["true", "false"]


def test_the_native_gate_matches_the_bun_gate(capsys):
    """The two paths must agree on every amplitude, not just on the shape."""
    out = run_both(Q +
                   "let s = h(h(state(3), 0), 2)\n"
                   "for name in [\"h\", \"t\", \"s\", \"x\", \"y\", \"z\"] {\n"
                   "  let m = gate(name)\n"
                   "  let slow = slow_apply_matrix(s, m, 1)\n"
                   "  let fast = apply_matrix(s, m, 1)\n"
                   "  print(name, str(amplitudes(slow)) == str(amplitudes(fast)))\n"
                   "}\n", capsys)
    for line in out.strip().splitlines():
        assert line.endswith("true"), line


def test_the_native_controlled_gate_matches_the_bun_gate(capsys):
    out = run_both(Q +
                   "let s = h(h(state(3), 0), 1)\n"
                   "let m = gate(\"x\")\n"
                   "let slow = slow_controlled(s, m, 0, 2)\n"
                   "let fast = controlled(s, m, 0, 2)\n"
                   "print(str(amplitudes(slow)) == str(amplitudes(fast)))\n"
                   "print(probability(fast, 5))\n", capsys)
    lines = out.strip().splitlines()
    assert lines[0] == "true"
    assert abs(number(lines[1]) - 0.25) < 1e-12


def test_a_twelve_qubit_state_still_normalizes(capsys):
    """The native path is what makes twelve qubits quick; it must still be right."""
    run_source(Q + "let s = ghz(12)\n"
                   "print(probability(s, 0))\n"
                   "print(probability(s, 4095))\n"
                   "print(entropy(s))\n",
               filename="<quantum>.bun", check=True, engine="vm")
    lines = [number(v) for v in capsys.readouterr().out.strip().splitlines()]
    assert abs(lines[0] - 0.5) < 1e-12
    assert abs(lines[1] - 0.5) < 1e-12
    assert abs(lines[2] - 1.0) < 1e-12
