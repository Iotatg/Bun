"""Tests for bun:discovery — arbitrary-precision experimental mathematics.

Every test runs the same source on the tree, vm, register and register+tier
engines and asserts identical output, as the other stack tests do.
"""

import pytest

from bun.cli import run_source
from bun.errors import BunRuntimeError

P = "import { set_precision, precision, fx_int, fx_parse, fx_str, fx_add, " \
    "fx_sub, fx_mul, fx_div, fx_div_int, fx_sqrt, fx_sqrt2, fx_pi, " \
    "pi_digits, fx_hex_digits, fx_hex_digits_at, bbp_hex, machin_search, " \
    "irrationality_measure, liouville, liouville_correlation, flint_hills, " \
    "mahler_bounds, packing_density, corpus_stats } from \"bun:discovery\"\n"


def run_both(source, capsys):
    """Run the same source on every engine and assert identical output."""
    run_source(source, filename="<discovery>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<discovery>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    run_source(source, filename="<discovery>.bun", check=True, engine="register")
    assert capsys.readouterr().out == vm_out
    run_source(source, filename="<discovery>.bun", check=True, engine="register",
               tier=True)
    assert capsys.readouterr().out == vm_out
    return vm_out


def number(text):
    return float(text.strip())


# ---------------------------------------------------------------------------
# The fixed-point layer
# ---------------------------------------------------------------------------

def test_fixed_point_arithmetic(capsys):
    out = run_both(P + "print(fx_str(fx_add(fx_parse(\"1.25\"), "
                        "fx_parse(\"2.5\")), 10))\n"
                        "print(fx_str(fx_div(fx_int(1), fx_int(3)), 12))\n"
                        "print(fx_str(fx_mul(fx_parse(\"1.5\"), "
                        "fx_parse(\"1.5\")), 10))\n", capsys)
    lines = out.strip().splitlines()
    assert lines[0] == "3.75"
    assert lines[1] == "0.333333333333"
    assert lines[2] == "2.25"


def test_precision_is_visible(capsys):
    out = run_both(P + "print(precision())\n"
                        "print(set_precision(40))\n"
                        "print(precision())\n", capsys)
    assert [v.strip() for v in out.strip().splitlines()] == ["60", "40", "40"]


def test_division_by_zero_is_an_error(capsys):
    with pytest.raises(BunRuntimeError) as info:
        run_source(P + "print(fx_div(fx_int(1), fx_int(0)))\n",
                   filename="<discovery>.bun", check=True, engine="vm")
    assert "zero" in info.value.msg.lower()


# ---------------------------------------------------------------------------
# Constants and the two independent pi paths
# ---------------------------------------------------------------------------

def test_pi_to_thirty_places(capsys):
    out = run_both(P + "print(pi_digits(30))\n", capsys)
    assert out.strip() == "3.141592653589793238462643383279"


def test_sqrt2_to_thirty_places(capsys):
    out = run_both(P + "print(fx_str(fx_sqrt2(), 30))\n", capsys)
    assert out.strip() == "1.414213562373095048801688724209"


def test_bbp_agrees_with_machin(capsys):
    out = run_both(P + "print(fx_hex_digits(fx_pi(), 24))\n"
                        "print(bbp_hex(0, 24))\n"
                        "print(bbp_hex(8, 8))\n", capsys)
    lines = [v.strip() for v in out.strip().splitlines()]
    assert lines[0] == "243F6A8885A308D313198A2E"
    assert lines[1] == lines[0]
    assert lines[2] == "85A308D3"


def test_hex_digits_at_offset(capsys):
    out = run_both(P + "print(fx_hex_digits_at(fx_pi(), 16, 8))\n"
                        "print(bbp_hex(16, 8))\n", capsys)
    lines = [v.strip() for v in out.strip().splitlines()]
    assert lines[0] == lines[1]


# ---------------------------------------------------------------------------
# Discovery 1 — Machin-like formulas
# ---------------------------------------------------------------------------

def test_machin_search_finds_exact_formulas(capsys):
    out = run_both(P + "let hits = machin_search(3, 2, 8, 2)\n"
                        "print(hits.len())\n"
                        "for h in hits { print(h[\"x\"], h[\"m\"], "
                        "h[\"y\"], h[\"n\"], h[\"err\"]) }\n", capsys)
    lines = out.strip().splitlines()
    assert int(lines[0]) >= 1
    # The classic atan(1/2) + atan(1/3) = pi/4 must appear with zero residual.
    assert any(v.startswith("2 1 3 1 0") for v in lines[1:])


# ---------------------------------------------------------------------------
# Discovery 3 — empirical irrationality exponent
# ---------------------------------------------------------------------------

def test_irrationality_measure_stays_near_two(capsys):
    out = run_both(P + "let mus = irrationality_measure(8)\n"
                        "for m in mus { print(m[\"q\"], m[\"mu\"]) }\n", capsys)
    rows = [v.split() for v in out.strip().splitlines()]
    assert len(rows) == 8
    assert rows[1][0] == "106"                      # 333/106 convergent
    assert rows[2][0] == "113"                      # 355/113 convergent
    values = [float(v[1]) for v in rows]
    assert all(1.9 < v < 3.5 for v in values)
    assert abs(values[1] - 2.0) < 0.1              # 333/106 is near the limit


# ---------------------------------------------------------------------------
# Discovery 4/5 — Liouville and Flint-Hills
# ---------------------------------------------------------------------------

def test_liouville_values(capsys):
    out = run_both(P + "for n in range(1, 13) { print(liouville(n)) }\n", capsys)
    assert [v.strip() for v in out.strip().splitlines()] == [
        "1", "-1", "-1", "1", "-1", "1", "-1", "-1", "1", "1", "-1", "-1"]


def test_liouville_correlation_decays(capsys):
    out = run_both(P + "let c = liouville_correlation(100)\n"
                        "print(c[\"sum\"])\n"
                        "print(c[\"C\"])\n", capsys)
    lines = [v.strip() for v in out.strip().splitlines()]
    assert lines[0] == "6"
    assert abs(number(lines[1]) - 0.06) < 1e-12


def test_flint_hills_spike_at_355(capsys):
    out = run_both(P + "let f = flint_hills(400)\n"
                        "print(f[\"max_n\"])\n"
                        "print(f[\"max_term\"])\n", capsys)
    lines = [v.strip() for v in out.strip().splitlines()]
    assert lines[0] == "355"       # 355/113 is a convergent of pi
    assert number(lines[1]) > 20.0


# ---------------------------------------------------------------------------
# Discovery 6/7/8 — Mahler, packing density, corpus mining
# ---------------------------------------------------------------------------

def test_mahler_bounds(capsys):
    out = run_both(P + "for n in range(1, 4) {\n"
                        "    let b = mahler_bounds(n)\n"
                        "    print(b[\"symmetric_bound\"], b[\"general_bound\"])\n"
                        "}\n", capsys)
    rows = [v.split() for v in out.strip().splitlines()]
    assert abs(float(rows[0][0]) - 4.0) < 1e-12
    assert abs(float(rows[1][0]) - 8.0) < 1e-12
    assert abs(float(rows[1][1]) - 6.75) < 1e-12
    assert abs(float(rows[2][0]) - 32.0 / 3.0) < 1e-12


def test_packing_density(capsys):
    out = run_both(P + "print(packing_density(20))\n", capsys)
    assert out.strip() == "0.90689968211710892529"


def test_corpus_stats_reads_a_catalogue(tmp_path, capsys):
    catalogue = tmp_path / "CONTENTS.md"
    catalogue.write_text(
        "**001.** first result ([Lean](lean/docs/001.md))\n"
        "  [paper](preprints/a/paper.pdf)\n"
        "**002.** second result\n"
        "  [paper](preprints/b/paper.pdf)\n"
        "**003.** third ([Lean](lean/docs/003.md))\n")
    src = P + "print(corpus_stats(\"" + str(catalogue) + "\"))\n"
    out = run_both(src, capsys)
    assert "indexed_families: 3" in out
    assert "preprint_pdfs: 2" in out
    assert "lean_docs: 2" in out
    assert "lean_families: 2" in out
    assert "lean_family_pct: 66.66" in out
    assert "lean_coverage_pct" in out
