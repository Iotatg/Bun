"""Tests for bun:nyaya — SUTRA Level 3 (the self-challenging verifier).

Every assertion runs on all four Bun engines and compares output byte for
byte. The point of this suite is not that the tests exist: the delivered
NYAYA_LAB_OUTPUT.txt appends the REAL output of an external pytest run,
because bun:nyaya itself refuses to certify that its tests were executed.
"""

from bun.cli import run_source

N = ("import { statements, negate, render, equivalent, complement_check, "
     "historical_records, level2_review, level3_fix_check, assumptions, "
     "assumption_check, uniformity_lemma, witnesses, sequence_stats, "
     "rule_liminf, rule_limsup, challenge_rules, reductions, reduction_all, "
     "bbbv_transfer, translation_table, translation_gaps, gap_lookup, "
     "certificates, adjudicate_certificate, adjudicate_all_certificates, "
     "false_positive_scan, self_challenge, review_response, "
     "execution_receipt, settle_conditions, nyaya_verdict, audit, lesson } "
     "from \"bun:nyaya\"\n")

E = "import { eth_statement } from \"bun:eth\"\n"


def run_both(source, capsys):
    run_source(source, filename="<nyaya>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<nyaya>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    run_source(source, filename="<nyaya>.bun", check=True, engine="register")
    assert capsys.readouterr().out == vm_out
    run_source(source, filename="<nyaya>.bun", check=True, engine="register",
               tier=True)
    assert capsys.readouterr().out == vm_out
    return vm_out


def test_quantifier_prefixes(capsys):
    out = run_both(N + "for s in statements() { print(s[\"id\"], \"|\", render(s)) }\n",
                   capsys)
    assert out.splitlines() == [
        "liminf-positive | E eps>0  E N  A n>=N   :   s(n) >= eps",
        "limsup-positive | E eps>0  A N  E n>=N   :   s(n) >= eps",
        "s-to-zero | A eps>0  E N  A n>=N   :   s(n) < eps",
        "liminf-zero | A eps>0  A N  E n>=N   :   s(n) < eps"]


def test_de_morgan_engine(capsys):
    out = run_both(N + "print(equivalent(negate(statements()[1]), statements()[2]))\n"
                       "print(complement_check(\"liminf-positive\", \"s-to-zero\")[\"verdict\"])\n"
                       "print(complement_check(\"limsup-positive\", \"s-to-zero\")[\"verdict\"])\n",
                   capsys)
    assert out.splitlines() == ["true", "NOT_COMPLEMENTARY", "COMPLEMENTARY"]


def test_negation_of_liminf_is_liminf_zero(capsys):
    out = run_both(N + "print(equivalent(negate(statements()[0]), statements()[3]))\n",
                   capsys)
    assert out.strip() == "true"


def test_level2_review_rejects_the_old_pair(capsys):
    out = run_both(N + "let r = level2_review()\n"
                       "print(r[\"verdict\"], r[\"stronger_than_eth\"])\n"
                       "print(r[\"claimed_negation_prefix\"])\n"
                       "print(r[\"correct_negation_prefix\"])\n", capsys)
    assert out.splitlines() == [
        "REJECTED true",
        "A eps>0  E N  A n>=N   :   s(n) < eps",
        "A eps>0  A N  E n>=N   :   s(n) < eps"]


def test_level3_fix_is_complementary(capsys):
    out = run_both(N + "let r = level3_fix_check()\n"
                       "print(r[\"verdict\"], r[\"complementary\"], r[\"pair\"])\n",
                   capsys)
    assert out.strip() == "COMPLEMENTARY true [limsup-positive, s-to-zero]"


def test_live_eth_statement_carries_the_fix(capsys):
    out = run_both(N + E + "let e = eth_statement()\n"
                           "print(e[\"statement_pair\"])\n"
                           "print(e[\"invariant\"])\n", capsys)
    assert out.splitlines() == [
        "[limsup-positive, s-to-zero]",
        "s = log2(T)/n; ETH true <=> limsup s > 0 for every correct algorithm "
        "(s does not tend to 0)"]


def test_historical_records_are_grounded_in_the_commit(capsys):
    out = run_both(N + "print(historical_records().len(), historical_records()[0][\"commit\"])\n",
                   capsys)
    assert out.strip() == "4 d43dec0"


def test_assumption_ledger(capsys):
    out = run_both(N + "for a in assumptions() { print(a[\"id\"], a[\"eth_grants\"]) }\n",
                   capsys)
    assert out.splitlines() == [
        "worst-case true", "all-instances true", "enumeration true",
        "triangular true", "forall-eps true", "monotone-runtime false",
        "black-box false", "independent-check false", "nl-formal-bridge false"]


def test_non_eth_assumptions_are_flagged(capsys):
    out = run_both(N + "print(assumption_check(\"monotone-runtime\")[\"eth_grants\"])\n"
                       "print(assumption_check(\"black-box\")[\"eth_grants\"])\n"
                       "print(assumption_check(\"nl-formal-bridge\")[\"eth_grants\"])\n",
                   capsys)
    assert out.splitlines() == ["false", "false", "false"]


def test_uniformity_lemma_lists_its_assumptions(capsys):
    out = run_both(N + "print(uniformity_lemma()[\"needs\"])\n"
                       "print(uniformity_lemma()[\"statement\"])\n", capsys)
    assert out.splitlines() == [
        "[worst-case, enumeration, triangular]",
        "inf_A limsup_n s_A(n) = 0  =>  exists a 2^o(n) algorithm"]


def test_witness_library(capsys):
    out = run_both(N + "print(witnesses().len())\n"
                       "for w in witnesses() { print(w[\"id\"], w[\"truth\"], w[\"liminf\"], w[\"tends_zero\"]) }\n",
                   capsys)
    assert out.splitlines() == [
        "6",
        "constant-0.99 ETH_TRUE positive false",
        "grover-0.50 ETH_TRUE positive false",
        "sparse-dips ETH_TRUE zero false",
        "finite-bench UNDECIDABLE undetermined false",
        "soft-exp ETH_FALSE zero true",
        "polynomial-3 ETH_FALSE zero true"]


def test_sparse_dips_is_the_conceptual_counterexample(capsys):
    out = run_both(N + "for w in witnesses() {\n"
                       "    if w[\"id\"] == \"sparse-dips\" {\n"
                       "        print(rule_liminf(w), rule_limsup(w), w[\"truth\"])\n"
                       "        let st = sequence_stats(w[\"points\"])\n"
                       "        print(st[\"liminf_proxy\"], st[\"limsup_proxy\"], st[\"tends_zero\"])\n"
                       "    }\n}\n", capsys)
    assert out.splitlines() == ["ETH_FALSE ETH_TRUE ETH_TRUE",
                               "0.015625 0.5 false"]


def test_finite_benchmark_is_undecidable(capsys):
    out = run_both(N + "for w in witnesses() {\n"
                       "    if w[\"id\"] == \"finite-bench\" { print(rule_liminf(w), rule_limsup(w)) }\n"
                       "}\n", capsys)
    assert out.strip() == "UNDECIDABLE UNDECIDABLE"


def test_corrected_rule_survives_all_witnesses(capsys):
    out = run_both(N + "let c = challenge_rules()\n"
                       "print(c[\"old_errors\"], c[\"new_errors\"], c[\"breaking_witness\"])\n"
                       "print(c[\"numeric_all_ok\"], c[\"verdict\"])\n", capsys)
    assert out.splitlines() == [
        "1 0 sparse-dips", "true CORRECTED_RULE_SURVIVES"]


def test_sequence_stats_numeric_proxies(capsys):
    out = run_both(N + "for w in witnesses() {\n"
                       "    let st = sequence_stats(w[\"points\"])\n"
                       "    print(w[\"id\"], st[\"tends_zero\"])\n"
                       "}\n", capsys)
    assert out.splitlines() == [
        "constant-0.99 false", "grover-0.50 false", "sparse-dips false",
        "finite-bench false", "soft-exp true", "polynomial-3 true"]


def test_reduction_correctness(capsys):
    out = run_both(N + "for r in reduction_all() {\n"
                       "    print(r[\"id\"], r[\"verdict\"], r[\"passed\"], r[\"total\"])\n"
                       "}\n", capsys)
    assert out.splitlines() == [
        "sparsification VALID 7 7", "naive-branching INVALID 5 7",
        "bbbv-to-3sat INVALID 3 7", "grover-to-3sat INVALID 3 7",
        "eth-implies-pneqnp VALID 7 7"]


def test_bbbv_is_model_restricted(capsys):
    out = run_both(N + "let q = bbbv_transfer()\n"
                       "print(q[\"model_ok\"], q[\"verdict\"], q[\"quantum_s\"])\n"
                       "print(q[\"restriction\"])\n", capsys)
    assert out.splitlines() == [
        "false INVALID 0.5",
        "valid ONLY in the black-box model; it is not a lower bound for structured 3SAT"]


def test_translation_gaps(capsys):
    out = run_both(N + "print(translation_gaps().len())\n"
                       "for g in translation_gaps() { print(g[\"id\"]) }\n"
                       "print(gap_lookup(\"bbbv\")[\"gap\"])\n", capsys)
    assert out.splitlines() == ["4", "lean", "press", "panel", "benchmark", "false"]


def test_certificate_ledger(capsys):
    out = run_both(N + "print(certificates().len())\n"
                       "for r in adjudicate_all_certificates() {\n"
                       "    print(r[\"id\"], r[\"verdict\"], r[\"passed\"], r[\"total\"], r[\"caught\"])\n"
                       "}\n", capsys)
    assert out.splitlines() == [
        "11",
        "l2-eth-equivalence REJECTED 2 2 true",
        "l2-audit-proves-eth REJECTED 2 2 true",
        "lean-verifies-theorem REJECTED 1 1 true",
        "journalism-settles REJECTED 1 1 true",
        "panel-certified REJECTED 1 1 true",
        "benchmark-decides REJECTED 1 1 true",
        "bbbv-structured REJECTED 1 1 true",
        "grover-refutes REJECTED 1 1 true",
        "one-percent-refutes REJECTED 1 1 true",
        "nyaya-self-certified REJECTED 1 1 true",
        "l3-correct-invariant ACCEPTED 2 2 true"]


def test_false_positive_scan(capsys):
    out = run_both(N + "let f = false_positive_scan()\n"
                       "print(f[\"caught\"], f[\"total\"], f[\"all_caught\"], f[\"verdict\"])\n",
                   capsys)
    assert out.strip() == "10 10 true ALL_FALSE_POSITIVES_CAUGHT"


def test_self_challenge_rejects_own_certificate(capsys):
    out = run_both(N + "let s = self_challenge()\n"
                       "print(s[\"passed\"], s[\"total\"], s[\"verdict\"])\n"
                       "for c in s[\"checks\"] { print(c[\"check\"], c[\"pass\"]) }\n", capsys)
    assert out.splitlines() == [
        "3 3 SELF_CHALLENGE_PASSED",
        "rejects-level-2-certificate true",
        "rejects-own-certificate true",
        "accepts-corrected-theorem true"]


def test_review_response_all_accepted(capsys):
    out = run_both(N + "print(review_response().len())\n"
                       "for r in review_response() { print(r[\"point\"], r[\"response\"]) }\n",
                   capsys)
    assert out.splitlines() == [
        "5", "1 ACCEPTED — real bug", "2 ACCEPTED — clarified",
        "3 ACCEPTED — kept", "4 ACCEPTED — enforced", "5 ACCEPTED — externalised"]


def test_execution_receipt_refuses_self_verification(capsys):
    out = run_both(N + "print(execution_receipt()[\"self_verifiable\"])\n"
                       "print(settle_conditions().len())\n", capsys)
    assert out.splitlines() == ["false", "6"]


def test_audit_is_certified_but_scoped(capsys):
    out = run_both(N + "let a = audit()\n"
                       "print(a[\"verdict\"], a[\"passed\"], a[\"total\"])\n"
                       "for c in a[\"checks\"] { print(c[\"check\"], c[\"pass\"]) }\n",
                   capsys)
    lines = out.splitlines()
    assert lines[0] == "CERTIFIED 13 13"
    assert len(lines) == 14
    assert all(line.endswith("true") for line in lines[1:])


def test_nyaya_verdict_keeps_eth_unresolved(capsys):
    out = run_both(N + "let v = nyaya_verdict()\n"
                       "print(v[\"eth\"], v[\"level3\"], v[\"self_challenged\"])\n"
                       "print(v[\"level2_bug\"])\n"
                       "print(v[\"not_solved\"].len())\n", capsys)
    assert out.splitlines() == [
        "UNRESOLVED CERTIFIED 13/13 true",
        "SOLVED (liminf -> limsup, De Morgan verified)", "4"]


def test_lesson_adds_one_year(capsys):
    out = run_both(N + "print(lesson().len())\n"
                       "print(lesson()[0])\n", capsys)
    assert out.splitlines() == [
        "9",
        "Level 3 (grad year 4): पहले अपने निष्कर्ष पर शक करो, फिर दूसरों पर।"]


def test_adjudicate_one_certificate_directly(capsys):
    out = run_both(N + "let c = certificates()[0]\n"
                       "let r = adjudicate_certificate(c)\n"
                       "print(r[\"verdict\"], r[\"reason\"])\n", capsys)
    assert out.strip() == ("REJECTED De Morgan: not(liminf>0) = liminf=0, "
                           "not s->0; also stronger than ETH")


def test_specific_false_positives_are_caught(capsys):
    out = run_both(N + "for r in adjudicate_all_certificates() {\n"
                       "    if r[\"id\"] == \"nyaya-self-certified\" or r[\"id\"] == \"bbbv-structured\" or r[\"id\"] == \"one-percent-refutes\" {\n"
                       "        print(r[\"id\"], r[\"verdict\"], r[\"reason\"])\n"
                       "    }\n"
                       "}\n", capsys)
    assert out.splitlines() == [
        "bbbv-structured REJECTED BBBV is proved only in the black-box model; "
        "structured 3SAT is not an oracle",
        "one-percent-refutes REJECTED s > 0: the exponent density does not tend "
        "to 0, so ETH survives",
        "nyaya-self-certified REJECTED a verifier cannot certify its own "
        "correctness; that is the self-challenge rule"]
