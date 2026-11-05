"""Regression tests for the external code review of bun:sutra_sarva.

KEY RULE: every expected numeric value in this file is computed by PYTHON,
not copied from Bun output. `py_eval` uses Python's own arithmetic (including
its right-associative ** and unary-minus precedence) as an INDEPENDENT ORACLE.
Four-engine agreement is therefore meaningful: it is agreement with a third,
separate implementation, not four engines agreeing with each other.

All tests run on all four Bun engines (tree / vm / register / register+tier)
and compare output byte for byte, following the existing suite's convention.
Written tests vs executed tests remain separate evidence (bun:nyaya pt 5).
"""

import re
from fractions import Fraction

import pytest

from bun.cli import run_source

S = ("import { calc, calc_alt, tokenize, ask, solve, check_answer, "
     "certificate_probe, verification_levels, roadmap, review_ledger, "
     "audit, verdict, eth_bound_check } "
     "from \"bun:sutra_sarva\"\n")

SAFE_EXPR = re.compile(r"^[0-9+\-*/^(). ]+$")


def py_eval(expr):
    """Independent oracle: Python's own evaluator. ^ -> ** (right-assoc)."""
    assert SAFE_EXPR.match(expr), expr
    return eval(expr.replace("^", "**"), {"__builtins__": {}}, {})


def run_both(source, capsys):
    run_source(source, filename="<sutra_sarva_correctness>.bun", check=True,
               engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<sutra_sarva_correctness>.bun", check=True,
               engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    run_source(source, filename="<sutra_sarva_correctness>.bun", check=True,
               engine="register")
    assert capsys.readouterr().out == vm_out
    run_source(source, filename="<sutra_sarva_correctness>.bun", check=True,
               engine="register", tier=True)
    assert capsys.readouterr().out == vm_out
    return vm_out


def calc_lines(exprs):
    return "".join('print(calc("' + e + '")["value"])\n' for e in exprs)


# --- 1. exponent associativity (Bug 1) ------------------------------------

def test_exponent_is_right_associative_python_oracle(capsys):
    exprs = ["2^3^2", "(2^3)^2", "2^2^3", "3^2^2", "2^3^1"]
    out = run_both(S + calc_lines(exprs), capsys)
    got = [float(x) for x in out.split()]
    expected = [py_eval(e) for e in exprs]
    assert got == expected
    assert expected[0] == 512          # 2^(3^2), NOT (2^3)^2
    assert expected[1] == 64


# --- 2. unary minus (Bug 2) -----------------------------------------------

def test_unary_minus_python_oracle(capsys):
    exprs = ["-3+5", "-3^2", "2^-3", "3--5", "2*-3", "-(3+4)", "-2^2", "2^-2^2"]
    out = run_both(S + calc_lines(exprs), capsys)
    got = [float(x) for x in out.split()]
    expected = [py_eval(e) for e in exprs]
    assert got == expected
    assert expected[1] == -9           # unary minus binds looser than ^
    assert expected[2] == 0.125


# --- 3. general precedence, exact rationals --------------------------------

def test_precedence_python_oracle(capsys):
    exprs = ["2+3*4", "(2+3)*4^2", "1/2+1/4", "2^3*2", "10-4-3",
             "2+3*4^2", "100/4/5"]
    out = run_both(S + calc_lines(exprs), capsys)
    got = [float(x) for x in out.split()]
    assert got == [py_eval(e) for e in exprs]


def test_fraction_is_exact_python_fraction(capsys):
    out = run_both(S + 'print(calc("1/2+1/4")["value"])\n', capsys)
    assert Fraction(out.strip()) == Fraction(3, 4)


# --- 4. two independent Bun algorithms agree with Python ------------------

def test_two_evaluators_agree_with_python_oracle(capsys):
    exprs = ["2+3", "(2+3)*4^2", "2^3^2", "-3+5", "-3^2", "2^-3",
             "1/2+1/4", "2+3*4", "3--5", "2(3+4)"]
    src = "".join(
        'let a = calc("' + e + '")\n'
        'let b = calc_alt("' + e + '")\n'
        'print(a["value"], b["value"], a["value"] == b["value"])\n'
        for e in exprs)
    out = run_both(S + src, capsys)
    lines = out.splitlines()
    assert len(lines) == len(exprs)
    for e, line in zip(exprs, lines):
        a, b, agree = line.split()
        assert agree == "true", e
        assert float(a) == float(b), e
    # The first nine are also checked against Python itself.
    for e, line in zip(exprs[:9], lines[:9]):
        assert float(line.split()[0]) == py_eval(e), e
    assert float(lines[-1].split()[0]) == 2 * (3 + 4)  # implicit multiplication


# --- 5. malformed input -> controlled error, never a crash -----------------

ERROR_CASES = [
    ("2+*3", "operator '*' has no left operand"),
    ("2..3", "invalid number: multiple decimal points"),
    ("2*(3+4", "unmatched opening parenthesis"),
    ("2a+3", "unknown character 'a'"),
    ("1/0", "division by zero"),
    ("()", "empty parentheses or trailing operator"),
    ("2+", "expression ends with an operator"),
    ("*3", "operator '*' has no left operand"),
    ("2)", "unmatched closing parenthesis"),
]


def test_every_malformed_expression_is_rejected_cleanly(capsys):
    src = "".join(
        'let r = calc("' + e + '")\n'
        'print(r["ok"], "|", r["error"])\n'
        for e, _ in ERROR_CASES)
    out = run_both(S + src, capsys)
    lines = out.splitlines()
    assert len(lines) == len(ERROR_CASES)
    for (expr, expected_msg), line in zip(ERROR_CASES, lines):
        ok, _, msg = line.partition("|")
        assert ok.strip() == "false", expr
        assert msg.strip() == expected_msg, expr


def test_ask_never_crashes_on_malformed_input(capsys):
    src = "".join(
        'print(ask("' + e + '")["status"])\n'
        for e, _ in ERROR_CASES)
    out = run_both(S + src, capsys)
    statuses = out.split()
    assert all(s in ("INVALID_EXPRESSION", "OUT_OF_SCOPE_FOR_SUTRA")
               for s in statuses), statuses
    assert "INVALID_EXPRESSION" in statuses


def test_tokenize_exposes_the_reason(capsys):
    out = run_both(S + 'print(tokenize("2+*3")["error"])\n'
                       'print(tokenize("2^3^2")["ok"])\n', capsys)
    assert out.splitlines() == ["operator '*' has no left operand", "true"]


# --- 6. solver edge cases (Bug 4 / Bug 5 / new bug X1) --------------------

def test_sum_negative_input_is_rejected(capsys):
    out = run_both(S + 'print(ask("sum 1..-5")["status"])\n'
                       'print(ask("sum 1..0")["status"])\n'
                       'print(ask("sum 1..-5")["reason"])\n', capsys)
    lines = out.splitlines()
    assert lines[0] == "INVALID_INPUT"
    assert lines[1] == "INVALID_INPUT"
    assert "domain" in lines[2]


def test_sum_matches_python_loop(capsys):
    ns = [1, 2, 10, 100]
    src = "".join('print(ask("sum 1..' + str(n) + '")["answer"])\n' for n in ns)
    out = run_both(S + src, capsys)
    got = [float(x) for x in out.split()]
    assert got == [sum(range(1, n + 1)) for n in ns]   # Python oracle


def test_zero_coefficient_is_not_division_by_zero(capsys):
    src = ('print(ask("0*x + 7 = 7")["status"])\n'
           'print(ask("0*x + 7 = 10")["status"])\n'
           'print(ask("3*x + 7 = 7")["status"])\n'
           'print(ask("3*x + 7 = 7")["answer"])\n'
           'print(ask("0*x + 7 = 7")["certificate"]["verdict"])\n')
    out = run_both(S + src, capsys)
    lines = out.splitlines()
    assert lines == ["INFINITE_SOLUTIONS", "NO_SOLUTION", "SOLVED",
                     "0.0", "NOT_APPLICABLE"]


def test_negative_coefficient_python_oracle(capsys):
    # The old unsigned regex turned `2x-5=9` into `2x + 5 = 9` -> x=2.
    cases = ["2x-5=9", "-2*x + 3 = 9", "3*x + 7 = 22", "3*x + 7 = -4"]
    src = "".join('print(ask("' + c + '")["answer"])\n' for c in cases)
    out = run_both(S + src, capsys)
    got = [float(x) for x in out.split()]
    expected = [(9 - (-5)) / 2, (9 - 3) / (-2), (22 - 7) / 3,
                (-4 - 7) / 3]                       # Python oracle
    assert got == expected
    assert expected[0] == 7.0


def test_linear_answer_text_renders_negative_sign(capsys):
    out = run_both(S + 'print(ask("2x-5=9")["answer_text"])\n', capsys)
    assert out.strip() == "2x - 5 = 9  =>  x = 7"


# --- 7. certificate: no always-true checks --------------------------------

WRONG_CASES = [
    '{"kind":"sum","n":10.0}',
    '{"kind":"percent","a":50.0,"b":80.0}',
    '{"kind":"linear","a":3.0,"b":7.0,"c":22.0}',
    '{"kind":"calc","expr":"2+3"}',
    '{"kind":"ratio","a":7.0,"b":8.0,"c":11.0,"d":12.0}',
    '{"kind":"unit","a":3.0,"factor":1000.0,"from":"km","to":"m","unit":"m"}',
    '{"kind":"growth","exponent":1}',
]


def test_certificate_rejects_every_injected_wrong_answer(capsys):
    out = run_both(S + 'let p = certificate_probe()\n'
                       'print(p["verdict"], p["caught"], p["total"])\n'
                       'for r in p["cases"] { print(r["case"], r["rejected"], r["passed"]) }\n',
                   capsys)
    lines = out.splitlines()
    assert lines[0] == "ALL_WRONG_ANSWERS_REJECTED 7 7"
    for line in lines[1:]:
        name, rejected, passed = line.split()
        assert rejected == "true", name
        assert int(passed) <= 2, name      # at least 2 checks must flip


def test_every_kind_rejects_wrong_number_directly(capsys):
    src = "".join('print(check_answer(' + q + ', 999.0)["verdict"])\n'
                  for q in WRONG_CASES)
    out = run_both(S + src, capsys)
    assert out.split() == ["REJECTED"] * len(WRONG_CASES)


def test_checks_declare_method_and_falsifiability(capsys):
    out = run_both(S + 'let c = check_answer({"kind":"calc","expr":"2+3"}, 5.0)\n'
                       'for x in c["checks"] { print(x["check"], x["detects_wrong_answer"], "|", x["method"]) }\n',
                   capsys)
    lines = out.splitlines()
    assert len(lines) == 4
    assert "recursive-descent" in lines[1]
    assert "metamorphic" in lines[3]
    assert "ans - ans" not in out            # the old vacuous check is gone
    assert lines[0].startswith("shape false")
    assert lines[1].startswith("number true")
    assert lines[2].startswith("dimension false")
    assert lines[3].startswith("boundary true")


def test_certificate_reports_verification_level_not_proof(capsys):
    src = ('let r = solve({"kind":"sum","n":10.0})\n'
           'print(r["certificate"]["verdict"], r["certificate"]["verification_level"])\n'
           'print(r["verification_level"], r["proof_status"])\n'
           'print(r["certificate"]["independent_oracles"])\n'
           'print(r["certificate"]["scope"])\n')
    out = run_both(S + src, capsys)
    lines = out.splitlines()
    assert lines[0] == "CERTIFIED INDEPENDENTLY_CHECKED"
    assert lines[1] == "INDEPENDENTLY_CHECKED NOT_ESTABLISHED"
    assert lines[2] == "2"
    assert "NOT A PROOF" in lines[3]


def test_growth_honestly_reports_weaker_level(capsys):
    out = run_both(S + 'print(solve({"kind":"growth","exponent":1})["verification_level"])\n', capsys)
    assert out.strip() == "COMPUTED"      # only 1 distinct numeric oracle


# --- 8. verification levels / roadmap / ledger are honest ------------------

def test_verification_levels_status(capsys):
    out = run_both(S + 'for v in verification_levels() { print(v["level"], v["name"], v["status"]) }\n', capsys)
    lines = out.splitlines()
    assert lines == ["1 COMPUTED IMPLEMENTED",
                     "2 INDEPENDENTLY_CHECKED IMPLEMENTED",
                     "3 SYMBOLICALLY_VERIFIED NOT_IMPLEMENTED",
                     "4 FORMALLY_VERIFIED NOT_IMPLEMENTED",
                     "5 RESEARCH_REVIEWED NOT_IMPLEMENTED"]


def test_roadmap_phase_zero_only(capsys):
    out = run_both(S + 'for p in roadmap() { print(p["phase"], p["status"]) }\n', capsys)
    lines = out.splitlines()
    assert len(lines) == 10
    assert lines[0] == "0 DONE"
    assert all(line.endswith("NOT_IMPLEMENTED") for line in lines[1:])


def test_review_ledger_records_claim_vs_actual(capsys):
    out = run_both(S + 'for r in review_ledger() { print(r["id"], r["verdict"]) }\n', capsys)
    lines = out.splitlines()
    assert len(lines) == 11
    verdicts = dict(line.split() for line in lines)
    assert verdicts["B5"] == "CONFIRMED_WITH_CORRECTION"   # description differed
    assert verdicts["X1"] == "CONFIRMED_NEW_BUG"           # found while verifying


def test_eth_and_research_claims_unchanged(capsys):
    out = run_both(S + 'print(verdict()["research_theorems_solved_by_sutra"])\n'
                       'print(verdict()["eth_status"])\n'
                       'print(eth_bound_check()["shape_verdict"])\n'
                       'print(ask("Prove the quasi-Riemann hypothesis")["status"])\n', capsys)
    assert out.splitlines() == ["0", "UNDER_REVIEW",
                                "SUBEXPONENTIAL_IN_THE_LIMIT",
                                "OUT_OF_SCOPE_FOR_SUTRA"]


def test_audit_scope_says_self_checks_are_not_proof(capsys):
    out = run_both(S + 'let a = audit()\n'
                       'print(a["verdict"], a["passed"], a["total"])\n'
                       'print(a["scope"])\n', capsys)
    lines = out.splitlines()
    assert lines[0] == "CERTIFIED 34 34"
    assert "NOT a proof" in lines[1]
    assert "separate evidence" in lines[1]


# --- 9. full four-engine parity on one combined probe ---------------------

def test_combined_probe_is_byte_identical_on_four_engines(capsys):
    src = ('print(calc("2^3^2")["value"], calc("-3+5")["value"], calc("2(3+4)")["value"])\n'
           'print(ask("sum 1..-5")["status"], ask("0*x+7=7")["status"])\n'
           'print(ask("2x-5=9")["answer_text"])\n'
           'print(certificate_probe()["caught"])\n'
           'print(audit()["passed"])\n')
    out = run_both(S + src, capsys)
    assert out.splitlines() == ["512.0 2.0 14.0",
                                "INVALID_INPUT INFINITE_SOLUTIONS",
                                "2x - 5 = 9  =>  x = 7",
                                "7", "34"]
