"""Tests for bun:pramana — SUTRA level 2 (the evidence layer).

Every assertion runs on all four Bun engines and compares the output byte for
byte, so the ETH record is engine-independent. The tests deliberately avoid
long measurements: the numbers come from pure arithmetic in log space.
"""

from bun.cli import run_source

P = ("import { pramanas, claim_types, can_settle, lattice, "
     "measurement_theorem, grover_queries, bbbv_lower_bound, quantum_s, "
     "quantum_certificate, quantum_worlds, barriers, asymmetries, sources, "
     "timeline, claims, adjudicate, adjudicate_all, verdict_counts, "
     "settle_conditions, mystery_verdict, audit, lesson } "
     "from \"bun:pramana\"\n")

E = ("import { alpha_blindspot, eth_worlds, s_of_ln, soft_ln, soft_points, "
     "local_exponents_ln, growth_ln, s_series, eth_shape, eth_statement } "
     "from \"bun:eth\"\n")


def run_both(source, capsys):
    run_source(source, filename="<pramana>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<pramana>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    run_source(source, filename="<pramana>.bun", check=True, engine="register")
    assert capsys.readouterr().out == vm_out
    run_source(source, filename="<pramana>.bun", check=True, engine="register",
               tier=True)
    assert capsys.readouterr().out == vm_out
    return vm_out


def test_six_pramanas(capsys):
    out = run_both(P + "for p in pramanas() { print(p[\"id\"], p[\"english\"]) }\n",
                   capsys)
    assert out.splitlines() == [
        "pratyaksha perception", "anumana inference", "upamana comparison",
        "shabda testimony", "arthapatti implication", "anupalabdhi absence"]


def test_measurement_cannot_settle_universal_claim(capsys):
    out = run_both(P + "print(can_settle(\"pratyaksha\", \"universal-algorithm\"))\n"
                       "print(can_settle(\"anumana\", \"universal-algorithm\"))\n"
                       "print(can_settle(\"upamana\", \"model-bound\"))\n"
                       "print(can_settle(\"shabda\", \"universal-algorithm\"))\n",
                   capsys)
    assert out.splitlines() == ["false", "true", "true", "false"]


def test_measurement_theorem_status(capsys):
    out = run_both(P + "let m = measurement_theorem()\n"
                       "print(m[\"can_settle\"], m[\"status\"])\n"
                       "print(m[\"what_would\"])\n", capsys)
    assert out.splitlines()[0] == "false PROVED (by logical type, not by experiment)"
    assert "anumana" in out.splitlines()[1]


def test_lattice_has_six_rows_and_seven_columns(capsys):
    out = run_both(P + "let l = lattice()\n"
                       "print(l.len(), l[0][\"row\"].len(), claim_types().len())\n",
                   capsys)
    assert out.strip() == "6 7 7"


def test_grover_is_square_root_of_brute_force(capsys):
    out = run_both(P + "print(grover_queries(20))\n"
                       "print(bbbv_lower_bound(20))\n"
                       "print(grover_queries(40) / grover_queries(20))\n", capsys)
    lines = out.splitlines()
    assert abs(float(lines[0]) - 1024.0) < 1e-9
    assert abs(float(lines[1]) - 1024.0) < 1e-9
    assert abs(float(lines[2]) - 1024.0) < 1e-9


def test_quantum_s_is_positive(capsys):
    out = run_both(P + "print(quantum_s(100))\n"
                       "for w in quantum_worlds() { print(w[\"name\"], w[\"s\"]) }\n",
                   capsys)
    assert out.splitlines()[0] == "0.5"
    assert "Grover / BBBV 0.5" in out


def test_quantum_certificate_passes_all_five_checks(capsys):
    out = run_both(P + "let q = quantum_certificate()\n"
                       "print(q[\"verdict\"], q[\"passed\"], q[\"total\"])\n", capsys)
    assert out.strip() == "CERTIFIED (model-bound) 5 5"


def test_barriers_include_the_three_classic_ones(capsys):
    out = run_both(P + "for b in barriers() { print(b[\"id\"], b[\"year\"]) }\n",
                   capsys)
    text = out.strip()
    assert "relativization 1975" in text
    assert "natural-proofs 1997" in text
    assert "algebrization 2009" in text
    assert "sparsification 2001" in text


def test_asymmetry_one_witness_falsifies(capsys):
    out = run_both(P + "print(asymmetries()[\"why_asymmetric\"])\n", capsys)
    assert "one witness falsifies" in out


def test_sources_all_have_urls(capsys):
    out = run_both(P + "for s in sources() {\n"
                       "  print(s[\"id\"], s[\"url\"])\n"
                       "}\n", capsys)
    lines = out.strip().splitlines()
    assert len(lines) == 5
    for line in lines:
        assert "https://" in line


def test_timeline_is_dated_and_ends_today(capsys):
    out = run_both(P + "print(timeline().len())\n"
                       "print(timeline()[0][\"date\"])\n"
                       "print(timeline()[timeline().len() - 1][\"date\"])\n"
                       "print(timeline()[timeline().len() - 1][\"event\"])\n",
                   capsys)
    lines = out.strip().splitlines()
    assert lines[0] == "10"
    assert lines[1] == "1955"
    assert lines[2] == "2026-11-05"
    assert "UNRESOLVED" in lines[3]


def test_thirteen_claims_are_all_consistently_adjudicated(capsys):
    out = run_both(P + "let a = adjudicate_all()\n"
                       "print(a.len())\n"
                       "var bad = 0\n"
                       "for x in a { if x[\"verdict\"] == \"INCONSISTENT\" { bad = bad + 1 } }\n"
                       "print(bad)\n", capsys)
    assert out.splitlines() == ["13", "0"]


def test_key_claim_verdicts(capsys):
    out = run_both(P + "for c in adjudicate_all() { print(c[\"id\"], c[\"verdict\"]) }\n",
                   capsys)
    d = dict(line.split(" ", 1) for line in out.strip().splitlines())
    assert d["eth-is-open"] == "CERTIFIED"
    assert d["benchmark-decides-eth"] == "REFUTED"
    assert d["video-valueless"] == "REFUTED"
    assert d["lean-verifies-claim"] == "REFUTED"
    assert d["panel-certified"] == "REFUTED"
    assert d["eth-false-implies-p-equals-np"] == "REFUTED"
    assert d["ai-disproof-accepted"] == "UNDER_REVIEW"
    assert d["soft-exponential-refutes"] == "OUT_OF_REACH"
    assert d["quantum-refutes"] == "REFUTED"
    assert d["bbbv-is-a-proof"] == "CERTIFIED"
    assert d["sutra-solved-eth"] == "REFUTED"


def test_verdict_counts_sum_to_thirteen(capsys):
    out = run_both(P + "let d = verdict_counts()\n"
                       "var total = 0\n"
                       "for k in d { total = total + d[k] }\n"
                       "print(total)\n", capsys)
    assert out.strip() == "13"


def test_settle_conditions_name_both_directions(capsys):
    out = run_both(P + "for s in settle_conditions() { print(s[\"direction\"]) }\n",
                   capsys)
    assert out.splitlines() == [
        "ETH is FALSE", "ETH is TRUE", "ETH is UNRESOLVED (current)"]


def test_mystery_verdict_is_honest(capsys):
    out = run_both(P + "let m = mystery_verdict()\n"
                       "print(m[\"eth\"], m[\"mystery\"])\n"
                       "print(m[\"measurement_can_settle_eth\"])\n"
                       "print(m[\"user_correction\"])\n", capsys)
    lines = out.strip().splitlines()
    assert lines[0] == "UNRESOLVED SOLVED"
    assert lines[1] == "false"
    assert "did not solve ETH" in lines[2]


def test_audit_passes_every_check(capsys):
    out = run_both(P + "let a = audit()\n"
                       "print(a[\"verdict\"], a[\"passed\"], a[\"total\"])\n", capsys)
    assert out.strip() == "CERTIFIED 10 10"


def test_lesson_has_eight_steps(capsys):
    out = run_both(P + "print(lesson().len())\n", capsys)
    assert out.strip() == "8"


# --- bun:eth corrected invariant -------------------------------------------

def test_correct_invariant_is_s_not_alpha(capsys):
    out = run_both(E + "print(eth_statement()[\"invariant\"])\n"
                       "print(eth_statement()[\"caution\"])\n", capsys)
    assert "log2(T)/n" in out.splitlines()[0]
    assert "NOT this invariant" in out.splitlines()[1]


def test_alpha_blindspot_reproduces_the_contradiction(capsys):
    out = run_both(E + "let b = alpha_blindspot()\n"
                       "print(b[\"contradiction\"], b[\"alpha_verdict\"], b[\"s_shape\"])\n"
                       "print(b[\"s_first\"], b[\"s_last\"])\n", capsys)
    lines = out.strip().splitlines()
    assert lines[0] == "true exponential suggests-2^o(n)"
    a, b = [float(x) for x in lines[1].split()]
    assert abs(a - 0.8664266713284088) < 1e-9
    assert abs(b - 0.48060704460064047) < 1e-9


def test_s_series_is_monotonically_decreasing(capsys):
    out = run_both(E + "let ns = [16.0, 32.0, 64.0, 128.0, 256.0, 512.0,\n"
                       "          1024.0, 2048.0, 4096.0, 8192.0]\n"
                       "let ss = s_series(soft_points(ns))\n"
                       "var bad = 0\n"
                       "for i in range(1, ss.len()) {\n"
                       "  if ss[i][\"s\"] >= ss[i-1][\"s\"] { bad = bad + 1 }\n"
                       "}\n"
                       "print(ss.len(), bad, eth_shape(ss))\n", capsys)
    assert out.strip() == "10 0 suggests-2^o(n)"


def test_growth_ln_matches_independent_python_alpha(capsys):
    # Independent value computed in /tmp with Python's math (0.929517...).
    out = run_both(E + "let ns = [16.0, 32.0, 64.0, 128.0, 256.0, 512.0,\n"
                       "          1024.0, 2048.0, 4096.0, 8192.0]\n"
                       "print(growth_ln(soft_points(ns))[\"alpha\"])\n", capsys)
    assert abs(float(out.strip()) - 0.9295174545228192) < 1e-9


def test_exponential_has_constant_positive_s(capsys):
    # T = 2^(0.99 n): s is constant 0.99, so ETH survives.
    out = run_both(E + "var pts = []\n"
                       "for n in [16.0, 32.0, 64.0, 128.0, 256.0] {\n"
                       "  pts.push([n, 0.99 * n * 0.6931471805599453])\n"
                       "}\n"
                       "print(s_of_ln(256.0, 0.99 * 256.0 * 0.6931471805599453))\n"
                       "print(eth_shape(s_series(pts)))\n", capsys)
    lines = out.strip().splitlines()
    assert abs(float(lines[0]) - 0.99) < 1e-9
    assert lines[1] == "suggests-2^Omega(n)"


def test_five_eth_worlds_under_correct_invariant(capsys):
    out = run_both(E + "for w in eth_worlds() { print(w[\"name\"], w[\"eth\"]) }\n",
                   capsys)
    assert out.splitlines() == [
        "polynomial false", "soft-exponential false", "subexponential false",
        "exponential true", "quantum-search true"]


def test_engine_independent_summary(capsys):
    out = run_both(P + E + "let a = audit()\n"
                           "let m = mystery_verdict()\n"
                           "print(a[\"verdict\"], a[\"passed\"], a[\"total\"])\n"
                           "print(m[\"eth\"])\n"
                           "print(can_settle(\"pratyaksha\", \"universal-algorithm\"))\n"
                           "print(grover_queries(20))\n"
                           "print(alpha_blindspot()[\"contradiction\"])\n", capsys)
    assert out.splitlines() == [
        "CERTIFIED 10 10", "UNRESOLVED", "false", "1024.0", "true"]
