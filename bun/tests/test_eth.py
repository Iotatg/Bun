"""Tests for bun:eth — growth shapes, the discrimination limit, certificates.

The solver tests deliberately use tiny n so the four-engine parity runs stay
fast; the long measurement lives in tools/eth_lab.bun, not in the test suite.
"""

from bun.cli import run_source

E = "import { eth_statement, growth, worlds, synthetic, fit_compare, " \
    "local_exponents, drift, measure, table_to_points, solve_result, " \
    "brute_sat, crossover, crossover_rule, claims, certificate_growth } " \
    "from \"bun:eth\"\n"


def run_both(source, capsys):
    run_source(source, filename="<eth>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<eth>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    run_source(source, filename="<eth>.bun", check=True, engine="register")
    assert capsys.readouterr().out == vm_out
    run_source(source, filename="<eth>.bun", check=True, engine="register",
               tier=True)
    assert capsys.readouterr().out == vm_out
    return vm_out


def test_eth_is_a_universal_statement(capsys):
    out = run_both(E + "let e = eth_statement()\n"
                       "print(e[\"measurable\"], e[\"kind\"])\n"
                       "print(e[\"sutra_form\"])\n", capsys)
    assert out.splitlines()[0] == "false universal"
    assert "not power(k)" in out.splitlines()[1]


def test_three_worlds(capsys):
    out = run_both(E + "for w in worlds() { print(w[\"name\"], w[\"alpha\"]) }\n",
                   capsys)
    assert out.splitlines() == ["polynomial 0.0", "subexponential 0.5",
                                "exponential 1.0"]


def test_growth_recovers_the_three_alphas(capsys):
    out = run_both(E + "let ns = [8.0, 16.0, 32.0, 64.0, 128.0, 256.0]\n"
                       "let a = growth(synthetic(ns, \"polynomial\", 3.0))\n"
                       "let b = growth(synthetic(ns, \"subexponential\", 0.5))\n"
                       "let c = growth(synthetic(ns, \"exponential\", 0.1))\n"
                       "print(a[\"kind\"], b[\"kind\"], c[\"kind\"])\n"
                       "print(b[\"alpha\"], c[\"alpha\"])\n", capsys)
    lines = out.splitlines()
    assert lines[0] == "polynomial subexponential exponential"
    # alpha recovers the exponent of the exponent to numerical precision
    vals = [float(x) for x in lines[1].split()]
    assert abs(vals[0] - 0.5) < 1e-9
    assert abs(vals[1] - 1.0) < 1e-9


def test_local_exponents_of_a_power_law_are_constant(capsys):
    out = run_both(E + "let ns = [8.0, 16.0, 32.0, 64.0, 128.0]\n"
                       "let ks = local_exponents(synthetic(ns, \"polynomial\", 3.0))\n"
                       "for p in ks { print(p[\"k\"]) }\n", capsys)
    vals = [float(x) for x in out.split()]
    assert all(abs(v - 3.0) < 1e-9 for v in vals), vals


def test_drift_of_a_power_law_is_zero(capsys):
    out = run_both(E + "let ns = [8.0, 16.0, 32.0, 64.0, 128.0]\n"
                       "print(drift(local_exponents(synthetic(ns, \"polynomial\", 3.0))))\n",
                   capsys)
    assert abs(float(out.strip())) < 1e-9


def test_fit_compare_recognises_clean_polynomial(capsys):
    out = run_both(E + "let ns = [8.0, 16.0, 32.0, 64.0, 128.0]\n"
                       "print(fit_compare(synthetic(ns, \"polynomial\", 3.0))[\"verdict\"])\n",
                   capsys)
    assert out.strip() == "POLYNOMIAL_FITS_BETTER"


def test_fit_compare_recognises_clean_exponential(capsys):
    out = run_both(E + "let ns = [8.0, 16.0, 32.0, 64.0, 128.0, 256.0]\n"
                       "print(fit_compare(synthetic(ns, \"exponential\", 0.1))[\"verdict\"])\n",
                   capsys)
    assert out.strip() == "EXPONENTIAL_FITS_BETTER"


def test_narrow_noisy_data_cannot_discriminate(capsys):
    # The measured DPLL table from tools/eth_lab.bun: both models fit equally.
    out = run_both(E + "let pts = [[12.0, 10.0], [16.0, 28.0], [20.0, 39.3333],\n"
                       "           [24.0, 49.1666], [28.0, 50.5], [32.0, 175.0]]\n"
                       "let f = fit_compare(pts)\n"
                       "print(f[\"verdict\"], f[\"measurable\"])\n", capsys)
    assert out.strip() == "UNDETERMINED false"


def test_solver_agrees_with_exhaustive_enumeration(capsys):
    out = run_both(E + "var agree = 0\n"
                       "for s in range(0, 25) {\n"
                       "  let r = solve_result(6, 4.26, 900 + s, 100000)\n"
                       "  let b = brute_sat(6, 4.26, 900 + s)\n"
                       "  if r[\"sat\"] == b { agree = agree + 1 }\n"
                       "}\n"
                       "print(agree)\n", capsys)
    assert out.strip() == "25"


def test_measure_returns_positive_node_counts(capsys):
    out = run_both(E + "let rows = measure([8, 10, 12], 4.26, 2, 100000)\n"
                       "var bad = 0\n"
                       "for r in rows {\n"
                       "  if r[\"nodes\"] <= 0.0 { bad = bad + 1 }\n"
                       "  if r[\"truncated\"] != 0 { bad = bad + 1 }\n"
                       "}\n"
                       "print(rows.len(), bad)\n", capsys)
    assert out.strip() == "3 0"


def test_crossover_rule_is_one_over_delta_squared(capsys):
    out = run_both(E + "let ds = [0.1, 0.05, 0.01, 0.005, 0.001]\n"
                       "for d in ds { print(crossover(d, 0.5, 1.0), crossover_rule(d)) }\n",
                   capsys)
    for line in out.strip().splitlines():
        a, b = [float(x) for x in line.split()]
        assert abs(a - b) < 1.0, (a, b)
    assert len(out.strip().splitlines()) == 5


def test_constant_factor_delays_the_win(capsys):
    out = run_both(E + "let a = crossover(0.01, 0.5, 1.0)\n"
                       "let b = crossover(0.01, 0.5, 1000.0)\n"
                       "print(b > a)\n", capsys)
    assert out.strip() == "true"


def test_five_claims_have_five_intended_verdicts(capsys):
    out = run_both(E + "for c in claims() {\n"
                       "  let r = certificate_growth(c)\n"
                       "  print(r[\"id\"], r[\"verdict\"], r[\"passed\"], r[\"total\"])\n"
                       "}\n", capsys)
    lines = out.strip().splitlines()
    assert len(lines) == 5
    assert lines[0] == "brute-force CERTIFIED 5 5"
    assert lines[1] == "subexponential-refutes OUT_OF_REACH 4 5"
    assert all("REJECTED 4 5" in line for line in lines[2:])


def test_rejections_name_the_failed_check(capsys):
    out = run_both(E + "for c in claims() {\n"
                       "  let r = certificate_growth(c)\n"
                       "  for ck in r[\"checks\"] {\n"
                       "    if not ck[\"pass\"] { print(r[\"id\"], ck[\"check\"]) }\n"
                       "  }\n"
                       "}\n", capsys)
    assert out.splitlines() == [
        "subexponential-refutes quantifier",
        "one-percent shape",
        "subexp-is-polynomial shape",
        "quadratic-3sat number",
    ]


def test_engine_independent_summary(capsys):
    out = run_both(E + "let e = eth_statement()\n"
                       "print(e[\"sutra_form\"])\n"
                       "print(worlds().len(), claims().len())\n"
                       "print(crossover(0.01, 0.5, 1.0), crossover_rule(0.01))\n"
                       "print(growth(synthetic([8.0, 16.0, 32.0, 64.0, 128.0], "
                       "\"subexponential\", 0.5))[\"kind\"])\n", capsys)
    assert "not power(k)" in out
    assert "3 5" in out
    assert "10000" in out
    assert "subexponential" in out
