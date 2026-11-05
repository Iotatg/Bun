"""Tests for bun:sutra_sarva — SUTRA Level 4 (one easy recipe, whole catalogue).

Every assertion runs on all four Bun engines and compares output byte for byte.
The catalogue tests use a small inline sample so the suite is hermetic; the
REAL 373-family openai/math run is in SUTRA_SARVA_LAB_OUTPUT.txt, produced by
`./bin/bun tools/sutra_sarva_lab.bun`. Written tests and executed tests are
deliberately kept as two different pieces of evidence (bun:nyaya review point 5).
"""

from bun.cli import run_source

S = ("import { alphabet, charter, shapes, seven_moves, four_checks, "
     "calc, solve, check_answer, ask, steps, course, teach, "
     "parse_catalogue, catalogue_summary, status_rules, measurement_notes, "
     "eth_bound_check, verdict, lesson, audit } "
     "from \"bun:sutra_sarva\"\n")

# A tiny catalogue with the same shape as CONTENTS.md: a family heading that
# carries its Lean link on the SAME line, and a second family with no link.
SAMPLE = ('"**001. Alpha.** Proves a constant bound. '
          '([Lean](lean/docs/001.md))\\n'
          '&emsp;[Paper](preprints/a/paper.pdf)\\n'
          '**002. Beta.** exponential growth 2^n.\\n'
          '&emsp;[Paper](preprints/b/paper.pdf)\\n"')


def run_both(source, capsys):
    run_source(source, filename="<sutra_sarva>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<sutra_sarva>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    run_source(source, filename="<sutra_sarva>.bun", check=True, engine="register")
    assert capsys.readouterr().out == vm_out
    run_source(source, filename="<sutra_sarva>.bun", check=True, engine="register",
               tier=True)
    assert capsys.readouterr().out == vm_out
    return vm_out


# --- 1. the recipe ---------------------------------------------------------

def test_alphabet_is_five_steps(capsys):
    out = run_both(S + 'for a in alphabet() { print(a["letter"], a["english"]) }\n',
                   capsys)
    assert out.splitlines() == ["S Strip", "U Uncover shape", "T Transform / Move",
                                "R Run checks", "A Answer with scope"]


def test_charter(capsys):
    out = run_both(S + 'let c = charter()\n'
                       'print(c["level"], c["recipe"], c["solves"])\n'
                       'print(c["does_not_solve"])\n', capsys)
    assert out.splitlines() == [
        "4 S-U-T-R-A arithmetic, percent, linear equation, sum, ratio, growth-shape, unit",
        "research theorems, conjectures, formal proofs"]


def test_shapes_moves_checks(capsys):
    out = run_both(S + "print(shapes().len(), seven_moves().len(), four_checks().len())\n"
                       "print(shapes())\n", capsys)
    assert out.splitlines() == [
        "5 7 4",
        "[constant, power, exponential, logarithmic, structural]"]


# --- 2. the real solver ----------------------------------------------------

def test_calc_simple(capsys):
    out = run_both(S + 'print(calc("2+3")["value"], calc("10-4")["value"])\n', capsys)
    assert out.strip() == "5.0 6.0"


def test_calc_precedence(capsys):
    out = run_both(S + 'print(calc("(2+3)*4^2")["value"], calc("2+3*4")["value"])\n', capsys)
    assert out.strip() == "80.0 14.0"


def test_calc_fraction(capsys):
    out = run_both(S + 'print(calc("1/2+1/4")["value"])\n', capsys)
    assert out.strip() == "0.75"


def test_solve_percent(capsys):
    out = run_both(S + 'print(solve({"kind":"percent","a":50.0,"b":80.0})["answer_text"])\n', capsys)
    assert out.strip() == "50% of 80 = 40"


def test_solve_linear(capsys):
    out = run_both(S + 'print(solve({"kind":"linear","a":3.0,"b":7.0,"c":22.0})["answer_text"])\n', capsys)
    assert out.strip() == "3x + 7 = 22  =>  x = 5"


def test_solve_sum(capsys):
    out = run_both(S + 'print(solve({"kind":"sum","n":100.0})["answer_text"])\n', capsys)
    assert out.strip() == "1+2+...+100 = 5050"


def test_solve_ratio(capsys):
    out = run_both(S + 'print(solve({"kind":"ratio","a":7.0,"b":8.0,"c":11.0,"d":12.0})["answer_text"])\n'
                       'print(solve({"kind":"ratio","a":1.0,"b":2.0,"c":1.0,"d":2.0})["answer_text"])\n', capsys)
    assert out.splitlines() == ["7/8 < 11/12", "1/2 = 1/2"]


def test_solve_growth_and_unit(capsys):
    out = run_both(S + 'print(solve({"kind":"growth","exponent":1})["answer_text"])\n'
                       'print(solve({"kind":"unit","a":3.0,"factor":1000.0,"from":"km","to":"m","unit":"m"})["answer_text"])\n', capsys)
    assert out.splitlines() == ["growth exponent 1", "3 km = 3000 m"]


def test_certificate_four_of_four(capsys):
    out = run_both(S + 'let c = solve({"kind":"sum","n":10.0})["certificate"]\n'
                       'print(c["verdict"], c["passed"], c["total"])\n', capsys)
    assert out.strip() == "CERTIFIED 4 4"


def test_certificate_declares_scope(capsys):
    out = run_both(S + 'print(solve({"kind":"sum","n":10.0})["certificate"]["scope"])\n', capsys)
    assert "NOT A PROOF" in out


def test_check_answer_rejects_wrong_number(capsys):
    # UPDATED after the external code review: the old boundary check for `sum`
    # was hardcoded `1*2/2-1` and could never fail. It is now the loop
    # recurrence f(n)=f(n-1)+n, which ALSO rejects a wrong answer. So a wrong
    # answer now passes 2 checks instead of 3 -- the certificate got stricter,
    # not weaker. Kept this assertion explicit rather than hiding the change.
    out = run_both(S + 'let c = check_answer({"kind":"sum","n":10.0}, 999.0)\n'
                       'print(c["verdict"], c["passed"])\n', capsys)
    assert out.strip() == "REJECTED 2"


# --- 3. one-line questions -------------------------------------------------

def test_ask_percent(capsys):
    out = run_both(S + 'print(ask("50% of 80")["answer_text"])\n', capsys)
    assert out.strip() == "50% of 80 = 40"


def test_ask_sum(capsys):
    out = run_both(S + 'print(ask("sum 1..100")["answer_text"])\n', capsys)
    assert out.strip() == "1+2+...+100 = 5050"


def test_ask_linear(capsys):
    out = run_both(S + 'print(ask("3*x + 7 = 22")["answer_text"])\n', capsys)
    assert out.strip() == "3x + 7 = 22  =>  x = 5"


def test_ask_calc(capsys):
    out = run_both(S + 'print(ask("2+3")["answer_text"], ask("(2+3)*4^2")["answer_text"])\n', capsys)
    assert out.strip() == "5 80"


def test_ask_ratio(capsys):
    out = run_both(S + 'print(ask("7/8 vs 11/12")["answer_text"])\n', capsys)
    assert out.strip() == "7/8 < 11/12"


def test_ask_theorem_is_out_of_scope(capsys):
    out = run_both(S + 'let r = ask("Prove the quasi-Riemann hypothesis Re(s)>7/8")\n'
                       'print(r["status"], r["answer"])\n'
                       'print(r["certificate"]["verdict"])\n', capsys)
    assert out.splitlines() == ["OUT_OF_SCOPE_FOR_SUTRA UNSOLVED_BY_SUTRA",
                                "NOT_APPLICABLE"]


# --- 4. teaching and the five steps ---------------------------------------

def test_steps_are_five(capsys):
    out = run_both(S + 'print(steps(course()[0]["q"]).len())\n'
                       'for l in steps(course()[4]["q"]) { print(l) }\n', capsys)
    lines = out.splitlines()
    assert lines[0] == "5"
    assert len(lines) == 6
    assert lines[1].startswith("S  Saaf karo")
    assert lines[5].startswith("A  Answer")


def test_course_ten_and_last_is_theorem(capsys):
    out = run_both(S + 'print(course().len(), course()[9]["q"]["kind"])\n'
                       'print(course()[0]["level"], course()[9]["level"])\n', capsys)
    assert out.splitlines() == ["10 theorem", "class 1 research theorem"]


def test_teach_first_problem(capsys):
    out = run_both(S + 'for l in teach(0) { print(l) }\n', capsys)
    lines = out.splitlines()
    assert lines[0] == "class 1  |  2+3"
    assert lines[-1] == "   => 5"


def test_teach_research_theorem_is_honest(capsys):
    out = run_both(S + 'for l in teach(9) { print(l) }\n', capsys)
    assert "OUT_OF_SCOPE" in out
    assert "pramaan" in out


# --- 5. the whole catalogue (hermetic sample) ------------------------------

def test_parse_catalogue_synthetic(capsys):
    out = run_both(S + 'let cards = parse_catalogue(' + SAMPLE + ')\n'
                       'print(cards.len())\n'
                       'for c in cards { print(c["id"], c["shape"], c["status"], c["lean"], c["pdfs"]) }\n',
                   capsys)
    assert out.splitlines() == [
        "2",
        "001 constant FORMALIZED_IN_LEAN true 1",
        "002 exponential MANUSCRIPT_ONLY false 1"]


def test_catalogue_summary_synthetic(capsys):
    out = run_both(S + 'let s = catalogue_summary(parse_catalogue(' + SAMPLE + '))\n'
                       'print(s["families"], s["manuscripts"], s["lean_families"], s["sutra_can_prove"], s["sutra_maps"])\n',
                   capsys)
    assert out.strip() == "2 2 1 0 2"


def test_every_card_admits_no_proof(capsys):
    out = run_both(S + 'let cards = parse_catalogue(' + SAMPLE + ')\n'
                       'for c in cards { print(c["sutra_can_prove"], c["sutra_can_do"]) }\n',
                   capsys)
    assert out.splitlines() == [
        "false shape + move + 4 checks + verification map",
        "false shape + move + 4 checks + verification map"]


def test_status_rules(capsys):
    out = run_both(S + 'print(status_rules().len())\n'
                       'for r in status_rules() { print(r["status"]) }\n', capsys)
    assert out.splitlines() == ["5", "SOLVED", "FORMALIZED_IN_LEAN",
                                "MANUSCRIPT_ONLY", "CLAIM_UNDER_REVIEW",
                                "OUT_OF_SCOPE_FOR_SUTRA"]


def test_measurement_notes(capsys):
    out = run_both(S + 'print(measurement_notes().len())\n'
                       'print(measurement_notes()[0]["caveat"])\n', capsys)
    assert out.splitlines()[0] == "4"
    assert "42%" in out


# --- 6. the ETH claim inside the corpus ------------------------------------

def test_eth_bound_shape(capsys):
    out = run_both(S + 'let e = eth_bound_check()\n'
                       'print(e["shape_verdict"], e["rows"].len())\n'
                       'print(e["invariant"])\n'
                       'print(e["eth_status"])\n', capsys)
    assert out.splitlines() == [
        "SUBEXPONENTIAL_IN_THE_LIMIT 8",
        "s = log2(T)/n   (bun:eth, limsup-corrected)",
        "UNDER_REVIEW (not SOLVED_BY_SUTRA)"]


def test_eth_bound_only_checks_shape(capsys):
    out = run_both(S + 'print(eth_bound_check()["honest_scope"])\n', capsys)
    assert "correctness NAHI" in out


def test_verdict_is_honest(capsys):
    out = run_both(S + 'let v = verdict()\n'
                       'print(v["elementary_solved"], v["elementary_total"])\n'
                       'print(v["research_theorems_solved_by_sutra"], v["research_families_mapped"])\n'
                       'print(v["eth_status"])\n', capsys)
    assert out.splitlines() == ["9 10", "0 373", "UNDER_REVIEW"]


# --- 7. self-audit and lesson ----------------------------------------------

def test_audit_certified_with_scope(capsys):
    out = run_both(S + 'let a = audit()\n'
                       'print(a["verdict"], a["passed"], a["total"])\n'
                       'print(a["scope"])\n', capsys)
    # 17 -> 34: 17 new regression checks for the parser/solver/certificate
    # fixes came from the external code review. Scope sentence now also says
    # that the external pytest run is a SEPARATE piece of evidence.
    assert out.splitlines() == ["CERTIFIED 34 34",
                                "module self-checks only — NOT a proof of any theorem; external pytest is separate evidence"]


def test_lesson(capsys):
    out = run_both(S + "print(lesson())\n", capsys)
    assert out.strip().startswith("SUTRA = S saaf karo")
    assert "admit scope" in out
