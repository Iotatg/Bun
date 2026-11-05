"""Tests for bun:sutra_school — the 15-year syllabus that audits itself."""

from bun.cli import run_source

S = "import { syllabus, atoms, audit, teach, path, place, unlocks } " \
    "from \"bun:sutra_school\"\n"


def run_both(source, capsys):
    run_source(source, filename="<school>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<school>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    run_source(source, filename="<school>.bun", check=True, engine="register")
    assert capsys.readouterr().out == vm_out
    run_source(source, filename="<school>.bun", check=True, engine="register",
               tier=True)
    assert capsys.readouterr().out == vm_out
    return vm_out


# --- the shape of the syllabus ---------------------------------------------

def test_fifteen_years(capsys):
    out = run_both(S + "let lv = syllabus()\n"
                       "print(lv.len())\n"
                       "print(lv[0][\"stage\"], lv[14][\"stage\"])\n", capsys)
    assert out.splitlines()[:2] == ["15", "class 1 graduation 3"]


def test_atom_registry(capsys):
    out = run_both(S + "let a = atoms()\n"
                       "var sh = 0\nvar mv = 0\nvar tl = 0\n"
                       "for x in a {\n"
                       "  if x[\"kind\"] == \"shape\" { sh = sh + 1 }\n"
                       "  if x[\"kind\"] == \"move\" { mv = mv + 1 }\n"
                       "  if x[\"kind\"] == \"tool\" { tl = tl + 1 }\n"
                       "}\n"
                       "print(a.len(), sh, mv, tl)\n", capsys)
    assert out.strip() == "15 4 7 4"


def test_audit_is_certified(capsys):
    out = run_both(S + "let a = audit()\n"
                       "print(a[\"verdict\"], a[\"passed\"], a[\"total\"], a[\"hours\"])\n",
                   capsys)
    assert out.strip() == "CERTIFIED 7 7 2280"


def test_every_audit_check_passes(capsys):
    out = run_both(S + "let a = audit()\n"
                       "for c in a[\"checks\"] { print(c[\"check\"], c[\"pass\"]) }\n",
                   capsys)
    lines = out.strip().splitlines()
    assert len(lines) == 7
    assert all(line.endswith("true") for line in lines), lines


def test_one_new_atom_per_year_and_none_repeated(capsys):
    out = run_both(S + "let lv = syllabus()\n"
                       "let seen = {}\n"
                       "for x in lv { seen[x[\"new\"]] = 1 }\n"
                       "print(seen.keys().len())\n", capsys)
    assert out.strip() == "15"


def test_prerequisites_precede_use(capsys):
    out = run_both(S + "let lv = syllabus()\n"
                       "let seen = {}\n"
                       "for x in lv { seen[x[\"new\"]] = x[\"level\"] }\n"
                       "var bad = 0\n"
                       "for x in lv {\n"
                       "  for need in x[\"uses\"] {\n"
                       "    if seen[need] >= x[\"level\"] { bad = bad + 1 }\n"
                       "  }\n"
                       "}\n"
                       "print(bad)\n", capsys)
    assert out.strip() == "0"


def test_fifteen_sample_laws_measure_true(capsys):
    # This is the strong one: each year's own law must classify as the shape
    # that year claims to teach, measured by bun:sutra, not asserted.
    src = "import { classify } from \"bun:sutra\"\n" + S
    out = run_both(src + "let lv = syllabus()\n"
                         "var ok = 0\n"
                         "for x in lv {\n"
                         "  let c = classify(x[\"sample\"], x[\"sample_at\"], x[\"sample_lam\"])\n"
                         "  if c[\"shape\"] == x[\"expect\"] { ok = ok + 1 }\n"
                         "}\n"
                         "print(ok)\n", capsys)
    assert out.strip() == "15"


def test_sample_parameters_match(capsys):
    src = "import { classify } from \"bun:sutra\"\n" + S
    out = run_both(src + "let lv = syllabus()\n"
                         "var bad = 0\n"
                         "for x in lv {\n"
                         "  let c = classify(x[\"sample\"], x[\"sample_at\"], x[\"sample_lam\"])\n"
                         "  if x[\"expect\"] != \"constant\" {\n"
                         "    let d = c[\"param\"] - x[\"expect_param\"]\n"
                         "    if d > 1e-6 { bad = bad + 1 }\n"
                         "    if 0.0 - d > 1e-6 { bad = bad + 1 }\n"
                         "  }\n"
                         "}\n"
                         "print(bad)\n", capsys)
    assert out.strip() == "0"


def test_hours_add_up(capsys):
    out = run_both(S + "let lv = syllabus()\n"
                       "var h = 0\n"
                       "for x in lv { h = h + x[\"hours\"] }\n"
                       "print(h)\n", capsys)
    assert out.strip() == "2280"


def test_every_year_is_teachable(capsys):
    out = run_both(S + "let lv = syllabus()\n"
                       "var bad = 0\n"
                       "for x in lv {\n"
                       "  if x[\"exercise\"].len() < 10 { bad = bad + 1 }\n"
                       "  if x[\"answer\"].len() < 10 { bad = bad + 1 }\n"
                       "  if x[\"can_now\"].len() < 10 { bad = bad + 1 }\n"
                       "  if x[\"unlocks\"].len() < 2 { bad = bad + 1 }\n"
                       "}\n"
                       "print(bad)\n", capsys)
    assert out.strip() == "0"


# --- teaching tools --------------------------------------------------------

def test_path_has_fifteen_lines(capsys):
    out = run_both(S + "let p = split(path(), \"\\n\")\n"
                       "print(p.len())\n"
                       "print(p[0])\n"
                       "print(p[14])\n", capsys)
    lines = out.strip().splitlines()
    assert lines[0] == "15"
    assert "Same or different" in lines[1]
    assert "Certify" in lines[2]


def test_class_one_is_constant_and_class_ten_is_exponential(capsys):
    out = run_both(S + "print(syllabus()[0][\"expect\"])\n"
                       "print(syllabus()[9][\"expect\"])\n"
                       "print(syllabus()[10][\"expect\"])\n"
                       "print(syllabus()[14][\"expect\"])\n", capsys)
    assert out.splitlines() == ["constant", "exponential", "logarithmic",
                                "exponential"]


def test_teach_renders_a_complete_lesson(capsys):
    out = run_both(S + "print(teach(10))\n", capsys)
    assert "class 10" in out
    assert "IDEA" in out and "EXERCISE" in out and "ANSWER" in out
    assert "UNLOCKS" in out
    assert "exponential" in out
    assert "THIS YEAR'S LAW, MEASURED" in out


def test_placement_is_monotone_and_bounded(capsys):
    out = run_both(S + "var last = 0\n"
                       "var bad = 0\n"
                       "for s in range(0, 13) {\n"
                       "  let p = place(s, 12)\n"
                       "  if p[\"level\"] < last { bad = bad + 1 }\n"
                       "  last = p[\"level\"]\n"
                       "}\n"
                       "print(place(0, 12)[\"level\"], place(12, 12)[\"level\"], bad)\n",
                   capsys)
    assert out.strip() == "1 15 0"


def test_unlocks_are_real_world_items(capsys):
    out = run_both(S + "print(unlocks(10).len())\n"
                       "print(unlocks(11).len())\n", capsys)
    assert out.splitlines() == ["4", "4"]


def test_full_lab_output_is_engine_independent(capsys):
    # A single deterministic snapshot across all four engines.
    src = "import { classify } from \"bun:sutra\"\n" + S
    out = run_both(src + "print(path())\n"
                         "print(audit()[\"verdict\"], audit()[\"hours\"])\n"
                         "print(place(7, 12)[\"stage\"])\n"
                         "print(teach(1))\n"
                         "print(teach(15))\n", capsys)
    assert "CERTIFIED 2280" in out
    assert "class 1" in out and "graduation 3" in out
    assert "class 9" in out
    assert "constant" in out and "Certify" in out
