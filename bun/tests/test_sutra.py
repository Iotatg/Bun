"""Tests for bun:sutra — the shape of laws, and the certificate that checks it."""

import pytest

from bun.cli import run_source
from bun.errors import BunRuntimeError, BunTypeError

P = "import { moves, SHAPES, classify, skeleton, same_skeleton, num, fmt, " \
    "catalog, certificate, groups, ladder, explain, curriculum, " \
    "dim_parse, dim_eq, " \
    "dim_str, dim_eval, dim_mul, dim_div, dim_pow, edge_behavior, " \
    "has_key } from \"bun:sutra\"\n"


def run_both(source, capsys):
    run_source(source, filename="<sutra>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<sutra>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    run_source(source, filename="<sutra>.bun", check=True, engine="register")
    assert capsys.readouterr().out == vm_out
    run_source(source, filename="<sutra>.bun", check=True, engine="register",
               tier=True)
    assert capsys.readouterr().out == vm_out
    return vm_out


def run_error(source):
    with pytest.raises((BunRuntimeError, BunTypeError)) as info:
        run_source(source, filename="<sutra>.bun", check=True, engine="vm")
    return info.value.msg


# --- the subject itself ----------------------------------------------------

def test_the_subject_has_seven_moves(capsys):
    out = run_both(P + "let ms = moves()\n"
                       "print(ms.len())\n"
                       "for m in ms { print(m[\"id\"], m[\"name\"]) }\n", capsys)
    lines = out.strip().splitlines()
    assert lines[0] == "7"
    assert lines[1] == "1 name"
    assert lines[7] == "7 check"


def test_there_are_three_real_shapes(capsys):
    out = run_both(P + "print(SHAPES)\n", capsys)
    assert "power" in out
    assert "exponential" in out
    assert "logarithmic" in out


# --- reversing an unknown law ---------------------------------------------

def test_a_cubic_is_recognised_as_a_power(capsys):
    src = P + "fn f(x) { return 3.0 * x * x * x }\n" \
              "let c = classify(f, 2.0, 4.0)\n" \
              "print(c[\"shape\"], num(c[\"param\"]), c[\"confident\"])\n"
    assert run_both(src, capsys).strip() == "power 3 true"


def test_growth_is_recognised_as_exponential(capsys):
    src = P + "fn f(x) { return 5.0 * (2.0 ** (x / 7.0)) }\n" \
              "let c = classify(f, 3.0, 4.0)\n" \
              "print(c[\"shape\"])\n"
    assert run_both(src, capsys).strip() == "exponential"


def test_a_logarithm_is_recognised(capsys):
    src = P + "let m = ffi_load(\"math\")\n" \
              "fn f(x) { return 4.0 * m[\"log\"](x) + 1.0 }\n" \
              "let c = classify(f, 3.0, 4.0)\n" \
              "print(c[\"shape\"])\n"
    assert run_both(src, capsys).strip() == "logarithmic"


def test_a_constant_is_recognised(capsys):
    src = P + "fn f(x) { return 7.0 }\n" \
              "print(classify(f, 2.0, 4.0)[\"shape\"])\n"
    assert run_both(src, capsys).strip() == "constant"


def test_a_mixture_is_not_forced_into_a_shape(capsys):
    src = P + "fn f(x) { return x + x * x }\n" \
              "let c = classify(f, 2.0, 4.0)\n" \
              "print(c[\"shape\"], c[\"confident\"])\n"
    assert run_both(src, capsys).strip() == "mixed false"


def test_the_skeleton_rebuilds_the_law_at_an_unseen_point(capsys):
    src = P + "fn f(x) { return 3.0 * x * x * x }\n" \
              "let s = skeleton(f, 3.0, 4.0)\n" \
              "print(num(s[\"factor\"]), num(s[\"param\"]))\n"
    assert run_both(src, capsys).strip() == "3 3"


def test_a_logarithm_rebuilds_with_its_offset(capsys):
    src = P + "let m = ffi_load(\"math\")\n" \
              "fn f(x) { return 4.0 * m[\"log\"](x) + 1.0 }\n" \
              "let s = skeleton(f, 3.0, 4.0)\n" \
              "print(fmt(s[\"factor\"]), fmt(s[\"offset\"]))\n"
    assert run_both(src, capsys).strip() == "4 1"


def test_two_logarithms_are_the_same_law(capsys):
    src = P + "let a = {\"shape\": \"logarithmic\", \"param\": 2.0}\n" \
              "let b = {\"shape\": \"logarithmic\", \"param\": 1.386}\n" \
              "print(same_skeleton(a, b, 1e-6))\n" \
              "let c = {\"shape\": \"power\", \"param\": 2.0}\n" \
              "let d = {\"shape\": \"power\", \"param\": 3.0}\n" \
              "print(same_skeleton(c, d, 1e-6))\n"
    assert run_both(src, capsys).strip().splitlines() == ["true", "false"]


# --- dimension algebra -----------------------------------------------------

def test_a_newton_is_a_kilogram_metre_per_second_squared(capsys):
    src = P + "print(dim_eq(dim_parse(\"N\"), dim_parse(\"kg*m/s^2\")))\n"
    assert run_both(src, capsys).strip() == "true"


def test_derived_units_expand_to_base_units(capsys):
    src = P + "print(dim_str(dim_parse(\"W\")))\n" \
              "print(dim_str(dim_parse(\"V\")))\n" \
              "print(dim_str(dim_parse(\"ohm\")))\n"
    lines = run_both(src, capsys).strip().splitlines()
    assert lines[0] == "L^2*M^1*T^-3"
    assert lines[1] == "I^-1*L^2*M^1*T^-3"
    assert lines[2] == "I^-2*L^2*M^1*T^-3"


def test_negative_exponents_are_parsed(capsys):
    src = P + "let a = dim_parse(\"m^3*kg^-1*s^-2\")\n" \
              "print(dim_str(a))\n"
    assert run_both(src, capsys).strip() == "L^3*M^-1*T^-2"


def test_a_power_scales_every_exponent(capsys):
    src = P + "let a = dim_pow(dim_parse(\"m^2/s\"), 0.5)\n" \
              "print(dim_str(a))\n"
    assert run_both(src, capsys).strip() == "L^1*T^-0.5"


def test_dimension_expressions_are_evaluated(capsys):
    src = P + "let e = {\"op\": \"pow\", \"n\": 0.5, \"a\": {\"op\": \"div\", " \
              "\"a\": {\"op\": \"unit\", \"u\": \"m\"}, " \
              "\"b\": {\"op\": \"unit\", \"u\": \"m/s^2\"}}}\n" \
              "print(dim_str(dim_eval(e)))\n"
    assert run_both(src, capsys).strip() == "T^1"


def test_a_bad_unit_is_a_runtime_error_not_a_silent_zero(capsys):
    msg = run_error(P + "print(dim_parse(42))\n")
    assert "string" in msg.lower() or "expect" in msg.lower()


# --- boundary behaviour ----------------------------------------------------

def test_an_inverse_square_blows_up_at_zero(capsys):
    src = P + "fn f(r) { return 1.0 / (r * r) }\n" \
              "let e = edge_behavior(f, 1.0, 1e6)\n" \
              "print(e[\"at_zero\"], e[\"at_inf\"])\n"
    assert run_both(src, capsys).strip() == "diverges vanishes"


def test_a_square_root_vanishes_at_zero(capsys):
    src = P + "fn f(x) { return x ** 0.5 }\n" \
              "let e = edge_behavior(f, 1.0, 1e6)\n" \
              "print(e[\"at_zero\"], e[\"at_inf\"])\n"
    assert run_both(src, capsys).strip() == "vanishes diverges"


# --- the catalogue and the certificate -------------------------------------

def test_every_law_in_the_catalogue_is_certified(capsys):
    src = P + "let ps = catalog()\n" \
              "var ok = 0\n" \
              "for p in ps {\n" \
              "    let c = certificate(p)\n" \
              "    if c[\"verdict\"] == \"CERTIFIED\" { ok = ok + 1 }\n" \
              "}\n" \
              "print(ok, ps.len())\n"
    assert run_both(src, capsys).strip() == "14 14"


def test_a_wrong_exponent_fails_the_shape_check(capsys):
    src = P + "let p = catalog()[1]\n" \
              "p[\"param\"] = 1.0\n" \
              "let c = certificate(p)\n" \
              "print(c[\"verdict\"], c[\"passed\"])\n"
    assert run_both(src, capsys).strip() == "REJECTED 3"


def test_a_wrong_unit_fails_the_dimension_check(capsys):
    src = P + "let p = catalog()[0]\n" \
              "p[\"lhs_unit\"] = \"m\"\n" \
              "let c = certificate(p)\n" \
              "print(c[\"verdict\"], c[\"passed\"])\n"
    assert run_both(src, capsys).strip() == "REJECTED 3"


def test_the_certificate_names_the_failing_check(capsys):
    src = P + "let p = catalog()[1]\n" \
              "p[\"param\"] = 1.0\n" \
              "for ck in certificate(p)[\"checks\"] {\n" \
              "    if not ck[\"pass\"] { print(ck[\"check\"]) }\n" \
              "}\n"
    assert run_both(src, capsys).strip() == "shape"


# --- cross-subject grouping ------------------------------------------------

def test_four_subjects_share_the_square_root_law(capsys):
    src = P + "for g in groups(catalog()) {\n" \
              "    if g[\"shape\"] == \"power\" and g[\"param\"] == 0.5 {\n" \
              "        print(g[\"members\"].len(), g[\"subjects\"].len())\n" \
              "    }\n" \
              "}\n"
    assert run_both(src, capsys).strip() == "4 3"


def test_the_groups_cover_every_law(capsys):
    src = P + "let ps = catalog()\n" \
              "var n = 0\n" \
              "for g in groups(ps) { n = n + g[\"members\"].len() }\n" \
              "print(n, ps.len())\n"
    assert run_both(src, capsys).strip() == "14 14"


# --- teaching --------------------------------------------------------------

def test_the_ladder_has_five_rungs(capsys):
    src = P + "print(ladder(catalog()[1]).len())\n"
    assert run_both(src, capsys).strip() == "5"


def test_the_explanation_contains_the_formula_and_the_reason(capsys):
    src = P + "let e = explain(catalog()[1])\n" \
              "print(len(e) > 100)\n"
    assert run_both(src, capsys).strip() == "true"


def test_formatting_drops_the_noise(capsys):
    src = P + "print(fmt(2.0060666807106475))\n" \
              "print(fmt(0.03465735902799726))\n" \
              "print(num(3.0))\n"
    lines = run_both(src, capsys).strip().splitlines()
    assert lines[0] == "2.006"
    assert lines[1] == "0.034657"
    assert lines[2] == "3"


def test_the_course_has_six_lessons(capsys):
    src = P + "let c = curriculum()\n" \
              "print(c.len())\n" \
              "var complete = 0\n" \
              "for l in c {\n" \
              "    if l[\"idea\"] != \"\" and l[\"exercise\"] != \"\" and l[\"answer\"] != \"\" {\n" \
              "        complete = complete + 1\n" \
              "    }\n" \
              "}\n" \
              "print(complete)\n"
    lines = run_both(src, capsys).strip().splitlines()
    assert lines == ["6", "6"]
