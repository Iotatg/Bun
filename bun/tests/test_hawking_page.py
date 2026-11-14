"""Tests for bun:hawking_page — the subject whose answer is one minus sign.

The module is a two-branch free-energy model of the Hawking-Page transition.
These tests do two jobs: they check that the model reproduces the 1983 result
(first order at 3/(2 pi L)), and they check that the certificate *fails* when
one sign is flipped.  A certificate that cannot fail is decoration.
"""

import pytest

from bun.cli import run_source

S = "import { transition_temperature, free_energy_difference, " \
    "entropy_difference, crossing_temperature, order_of, sign_audit, " \
    "certificate, claim_ledger, why_one_sign, report, latent_heat } " \
    "from \"bun:hawking_page\"\n"


def run_all(source, capsys):
    outputs = []
    for engine in ("tree", "vm", "register"):
        run_source(source, filename="<hole>.bun", check=True, engine=engine)
        outputs.append(capsys.readouterr().out)
    assert outputs[0] == outputs[1] == outputs[2]
    return outputs[0]


def number(source, capsys):
    return float(run_all(source, capsys).strip())


# --- the model -------------------------------------------------------------

def test_the_critical_temperature_is_three_over_two_pi(capsys):
    assert number(S + "print(transition_temperature(1.0))\n", capsys) == \
        pytest.approx(3.0 / (2.0 * 3.141592653589793), rel=1e-15)


def test_the_temperature_falls_as_the_universe_grows(capsys):
    out = run_all(S + "print(transition_temperature(1.0))\n"
                      "print(transition_temperature(2.0))\n"
                      "print(transition_temperature(4.0))\n", capsys)
    values = [float(line) for line in out.splitlines()]
    assert values[1] == pytest.approx(values[0] / 2.0, rel=1e-15)
    assert values[2] == pytest.approx(values[0] / 4.0, rel=1e-15)


def test_the_difference_vanishes_at_the_critical_temperature(capsys):
    assert abs(number(S + "print(free_energy_difference("
                          "transition_temperature(1.0), 1.0, 1.0, 1.0))\n",
                       capsys)) < 1e-15


def test_radiation_wins_below_and_the_black_hole_wins_above(capsys):
    out = run_all(S + "let tc = transition_temperature(1.0)\n"
                      "print(free_energy_difference(0.5 * tc, 1.0, 1.0, 1.0) > 0.0)\n"
                      "print(free_energy_difference(1.5 * tc, 1.0, 1.0, 1.0) < 0.0)\n",
                  capsys)
    assert out.split() == ["true", "true"]


def test_the_entropy_is_a_cubic(capsys):
    out = run_all(S + "print(entropy_difference(1.0, 1.0, 1.0, 1.0))\n"
                      "print(entropy_difference(2.0, 1.0, 1.0, 1.0))\n", capsys)
    one, two = [float(line) for line in out.splitlines()]
    assert two == pytest.approx(8.0 * one, rel=1e-12)


def test_latent_heat_is_times_the_entropy_jump(capsys):
    # q = T dS = 4 k Tc^4, so q / Tc = 4 k Tc^3 = dS at Tc.
    out = run_all(S + "let q = latent_heat(1.0, 1.0)\n"
                      "let tc = transition_temperature(1.0)\n"
                      "print(q / tc)\n"
                      "print(entropy_difference(tc, 1.0, 1.0, 1.0))\n", capsys)
    q_over_t, ds = [float(line) for line in out.splitlines()]
    assert q_over_t == pytest.approx(ds, rel=1e-12)


# --- the measurement -------------------------------------------------------

def test_bisection_finds_the_formula_crossing(capsys):
    out = run_all(S + "print(crossing_temperature(\"crossing\", 1.0, 1.0, 1.0))\n"
                      "print(transition_temperature(1.0))\n", capsys)
    found, formula = [float(line) for line in out.splitlines()]
    assert found == pytest.approx(formula, rel=1e-9)


def test_the_flipped_model_has_no_crossing(capsys):
    assert number(S + "print(crossing_temperature(\"flipped\", 1.0, 1.0, 1.0))\n",
                  capsys) == -1.0


def test_the_crossing_model_is_first_order(capsys):
    out = run_all(S + "print(order_of(\"crossing\", 1.0, 1.0, 1.0)[\"order\"])\n",
                  capsys)
    assert out.strip() == "first"


def test_the_control_model_is_second_order(capsys):
    out = run_all(S + "print(order_of(\"tangent\", 1.0, 1.0, 1.0)[\"order\"])\n",
                  capsys)
    assert out.strip() == "second"


def test_the_order_measurement_separates_the_two_models_by_more_than_a_threshold(
        capsys):
    out = run_all(S + "print(order_of(\"crossing\", 1.0, 1.0, 1.0)[\"ratio\"])\n"
                      "print(order_of(\"tangent\", 1.0, 1.0, 1.0)[\"ratio\"])\n",
                  capsys)
    first, second = [float(line) for line in out.splitlines()]
    # The ratio is a finite-difference measurement with h = Tc / 10000, so
    # neither number is exact: the crossing sits at 1 to about a part in a
    # thousand and the control has a floor of the same order.  The separation
    # between them, not the absolute value, is what the measurement claims.
    assert first == pytest.approx(1.0, abs=0.01)
    assert abs(second) < 0.01
    assert first / abs(second) > 100.0


# --- the four models -------------------------------------------------------

def test_the_sign_audit_has_four_models_with_four_different_answers(capsys):
    out = run_all(S + "for row in sign_audit() {\n"
                      "  print(row[\"model\"], row[\"crosses\"], row[\"order\"],"
                      " row[\"high_T_winner\"])\n"
                      "}\n", capsys)
    rows = [line.split() for line in out.splitlines()]
    assert rows == [
        ["crossing", "true", "first", "black", "hole"],
        ["flipped", "false", "second", "black", "hole"],
        ["reversed", "true", "first", "radiation"],
        ["tangent", "true", "second", "black", "hole"],
    ]


def test_one_sign_decides_whether_there_is_a_transition_at_all(capsys):
    out = run_all(S + "print(crossing_temperature(\"crossing\", 1.0, 1.0, 1.0) > 0.0)\n"
                      "print(crossing_temperature(\"flipped\", 1.0, 1.0, 1.0) > 0.0)\n",
                  capsys)
    assert out.split() == ["true", "false"]


def test_a_reversed_difference_keeps_the_shape_and_loses_the_physics(capsys):
    # Same Tc, same first-order jump, opposite winner: the shape checks pass
    # and only the direction check can catch it.
    out = run_all(S + "let a = order_of(\"crossing\", 1.0, 1.0, 1.0)\n"
                      "let b = order_of(\"reversed\", 1.0, 1.0, 1.0)\n"
                      "print(a[\"order\"] == b[\"order\"])\n", capsys)
    assert out.strip() == "true"


# --- the certificate -------------------------------------------------------

def test_the_certificate_passes_all_six_checks(capsys):
    out = run_all(S + "let c = certificate(1.0, 1.0, 1.0)\n"
                      "print(c[\"status\"], c[\"passed\"], c[\"total\"])\n", capsys)
    assert out.split() == ["CERTIFIED", "6", "6"]


def test_the_certificate_refuses_a_negative_coupling(capsys):
    # k < 0 turns the black hole into the loser at high temperature; the
    # direction check must fail even though the shape is untouched.
    out = run_all(S + "let c = certificate(1.0, -1.0, 1.0)\n"
                      "print(c[\"status\"])\n"
                      "for row in c[\"checks\"] {\n"
                      "  if !row[\"pass\"] { print(row[\"check\"]) }\n"
                      "}\n", capsys)
    lines = out.split()
    assert lines[0] == "REFUSED"
    assert "direction" in lines[1:]


def test_every_check_is_reported_even_when_it_passes(capsys):
    out = run_all(S + "let c = certificate(1.0, 1.0, 1.0)\n"
                      "for row in c[\"checks\"] { print(row[\"check\"]) }\n",
                  capsys)
    assert out.split() == ["shape", "number", "crossing", "direction",
                           "order", "entropy"]


# --- honesty ---------------------------------------------------------------

def test_the_ledger_keeps_the_open_question_open(capsys):
    out = run_all(S + "for row in claim_ledger() { print(row[\"status\"]) }\n",
                  capsys)
    assert out.split() == ["KNOWN", "KNOWN", "UNRESOLVED", "UNVERIFIED"]


def test_the_2026_claim_is_never_certified(capsys):
    out = run_all(S + "for row in claim_ledger() {\n"
                      "  if row[\"status\"] == \"CERTIFIED\" { print(\"bad\") }\n"
                      "}\n", capsys)
    assert out.strip() == ""


def test_the_ledger_names_who_asked_and_when(capsys):
    out = run_all(S + "for row in claim_ledger() { print(row[\"who\"]) }\n",
                  capsys)
    text = out
    assert "Hawking" in text
    assert "Aharony" in text
    assert "1983" in text and "2003" in text


def test_the_explanation_says_why_shape_is_not_enough(capsys):
    out = run_all(S + "print(why_one_sign())\n", capsys)
    assert "sign" in out
    assert "T^4" in out


def test_the_report_prints_one_row_per_model(capsys):
    out = run_all(S + "print(report())\n", capsys)
    lines = out.strip().splitlines()
    assert len(lines) == 5
    assert "crossing" in lines[1]
    assert "tangent" in lines[4]


def test_the_module_runs_on_the_three_interpreter_engines(capsys):
    source = S + "let c = certificate(1.0, 1.0, 1.0)\nprint(c[\"status\"])\n"
    for engine in ("tree", "vm", "register"):
        run_source(source, filename="<hole>.bun", check=True, engine=engine)
        assert capsys.readouterr().out.strip() == "CERTIFIED"


def test_the_c_backend_refuses_the_module_by_name(capsys):
    # The module calls ffi_load for pow and fabs.  The C backend does not
    # implement ffi_load, and it must say so instead of guessing.
    from bun.cbackend import CBackendError
    source = S + "print(transition_temperature(1.0))\n"
    with pytest.raises(CBackendError) as failure:
        run_source(source, filename="<hole>.bun", check=True, engine="c")
    assert "ffi_load" in str(failure.value)
