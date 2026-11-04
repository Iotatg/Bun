"""Tests for bun:science — formulas, solutions and the molecules of life."""

import pytest

from bun.cli import run_source
from bun.errors import BunRuntimeError, BunTypeError

S = "import { atomic_number, atomic_mass, element_name, element_count, " \
    "composition, molar_mass, molecular_mass, atom_count, mass_percent, " \
    "moles, mass_of, molecules, molarity, dilution, dilution_volume, ph, " \
    "poh, hydrogen_concentration, buffer_ph, density, ppm, decay_constant, " \
    "decay, decay_time, activity, activity_mass, dna_complement, " \
    "reverse_complement, transcribe, gc_content, translate, protein_mass, " \
    "isoelectric_point } from \"bun:science\"\n"


def run_both(source, capsys):
    run_source(source, filename="<science>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<science>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    run_source(source, filename="<science>.bun", check=True, engine="register")
    assert capsys.readouterr().out == vm_out
    run_source(source, filename="<science>.bun", check=True, engine="register",
               tier=True)
    assert capsys.readouterr().out == vm_out
    return vm_out


def run_error(source):
    with pytest.raises((BunRuntimeError, BunTypeError)) as info:
        run_source(source, filename="<science>.bun", check=True, engine="vm")
    return info.value.msg


def number(text):
    return float(text.strip())


# ---------------------------------------------------------------------------
# The elements
# ---------------------------------------------------------------------------

def test_the_elements_carry_their_numbers(capsys):
    out = run_both(S + "print(atomic_number(\"H\"))\n"
                        "print(atomic_number(\"Au\"))\n"
                        "print(atomic_mass(\"C\"))\n"
                        "print(element_name(\"Fe\"))\n", capsys)
    assert out.strip().splitlines() == ["1", "79", "12.011", "iron"]


def test_an_unknown_element_is_an_error():
    message = run_error(S + "print(atomic_mass(\"Xx\"))\n")
    assert "Xx" in message


# ---------------------------------------------------------------------------
# The formula parser
# ---------------------------------------------------------------------------

def test_water_is_eighteen_grams(capsys):
    out = run_both(S + "print(molar_mass(\"H2O\"))\n", capsys)
    assert abs(number(out) - 18.015) < 1e-9


def test_glucose_is_one_hundred_and_eighty(capsys):
    out = run_both(S + "print(molar_mass(\"C6H12O6\"))\n", capsys)
    assert abs(number(out) - 180.156) < 1e-9


def test_a_bracket_carries_its_multiplier(capsys):
    out = run_both(S + "print(molar_mass(\"Ca(OH)2\"))\n"
                        "print(molar_mass(\"Al2(SO4)3\"))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[0] - 74.092) < 1e-9
    assert abs(lines[1] - 342.131077) < 1e-9


def test_a_nested_bracket_works(capsys):
    out = run_both(S + "print(molar_mass(\"K4(ON(SO3)2)2\"))\n", capsys)
    assert abs(number(out) - 536.6332) < 1e-6


def test_the_composition_is_a_count_of_atoms(capsys):
    out = run_both(S + "let c = composition(\"Ca(OH)2\")\n"
                        "print(c[\"Ca\"], c[\"O\"], c[\"H\"])\n"
                        "print(atom_count(\"Ca(OH)2\"))\n", capsys)
    assert out.strip().splitlines() == ["1 2 2", "5"]


def test_an_element_without_a_count_is_one(capsys):
    out = run_both(S + "print(composition(\"NaCl\"))\n", capsys)
    assert out.strip() == "{Na: 1, Cl: 1}"


def test_an_unclosed_bracket_is_an_error():
    message = run_error(S + "print(molar_mass(\"Ca(OH2\"))\n")
    assert "unclosed bracket" in message


def test_a_character_that_is_not_chemistry_is_an_error():
    message = run_error(S + "print(molar_mass(\"H2O!\"))\n")
    assert "cannot read" in message


def test_the_mass_of_one_molecule(capsys):
    out = run_both(S + "print(molecular_mass(\"H2O\"))\n", capsys)
    assert abs(number(out) - 2.9915e-26) < 1e-29


def test_the_share_of_an_element(capsys):
    out = run_both(S + "print(mass_percent(\"H2O\", \"H\"))\n"
                        "print(mass_percent(\"H2O\", \"C\"))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[0] - 11.19067443796836) < 1e-9
    assert lines[1] == 0.0


# ---------------------------------------------------------------------------
# Solutions
# ---------------------------------------------------------------------------

def test_a_mole_is_the_molar_mass_in_grams(capsys):
    out = run_both(S + "print(moles(180.156, \"C6H12O6\"))\n"
                        "print(mass_of(2.0, \"H2O\"))\n"
                        "print(molecules(1.0))\n", capsys)
    lines = out.strip().splitlines()
    assert abs(number(lines[0]) - 1.0) < 1e-9
    assert abs(number(lines[1]) - 36.03) < 1e-9
    assert abs(number(lines[2]) - 6.02214076e23) < 1e17


def test_molarity_is_moles_per_litre(capsys):
    out = run_both(S + "print(molarity(0.5, 2.0))\n", capsys)
    assert number(out) == 0.25


def test_dilution_conserves_the_solute(capsys):
    out = run_both(S + "print(dilution(1.0, 10.0, 100.0))\n"
                        "print(dilution_volume(1.0, 0.1, 100.0))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[0] - 0.1) < 1e-12
    assert abs(lines[1] - 10.0) < 1e-12


def test_the_ph_of_a_millimolar_acid(capsys):
    out = run_both(S + "print(ph(1e-3))\n"
                        "print(ph(1e-7))\n"
                        "print(hydrogen_concentration(3.0))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[0] - 3.0) < 1e-12
    assert abs(lines[1] - 7.0) < 1e-12
    assert abs(lines[2] - 1e-3) < 1e-15


def test_a_buffer_follows_henderson_hasselbalch(capsys):
    out = run_both(S + "print(buffer_ph(4.76, 0.1, 0.1))\n"
                        "print(buffer_ph(4.76, 1.0, 0.1))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[0] - 4.76) < 1e-12
    assert abs(lines[1] - 5.76) < 1e-12


def test_density_and_ppm(capsys):
    out = run_both(S + "print(density(1000.0, 1.0))\n"
                        "print(ppm(1.0, 1e6))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert lines[0] == 1000.0
    assert lines[1] == 1.0


# ---------------------------------------------------------------------------
# Radioactivity
# ---------------------------------------------------------------------------

def test_two_half_lives_leave_a_quarter(capsys):
    out = run_both(S + "print(decay(100.0, 5730.0, 11460.0))\n", capsys)
    assert abs(number(out) - 25.0) < 1e-12


def test_the_decay_constant_of_carbon_fourteen(capsys):
    out = run_both(S + "print(decay_constant(5730.0) * 5730.0)\n", capsys)
    assert abs(number(out) - 0.6931471805599453) < 1e-12


def test_the_time_to_fall_to_a_fraction(capsys):
    out = run_both(S + "print(decay_time(0.25, 10.0))\n", capsys)
    assert abs(number(out) - 20.0) < 1e-12


def test_activity_and_the_mass_that_carries_it(capsys):
    out = run_both(S + "let a = activity(6.02214076e23, 5730.0 * 31557600.0)\n"
                        "print(a)\n"
                        "print(activity_mass(a, 5730.0 * 31557600.0, 14.0))\n",
                   capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[0] - 2.3084356591621787e12) < 1e6
    assert abs(lines[1] - 14.0) < 0.5


# ---------------------------------------------------------------------------
# The molecules of life
# ---------------------------------------------------------------------------

def test_the_other_strand(capsys):
    out = run_both(S + "print(dna_complement(\"ATGC\"))\n"
                        "print(reverse_complement(\"ATGC\"))\n", capsys)
    assert out.strip().splitlines() == ["TACG", "GCAT"]


def test_transcription_turns_t_into_u(capsys):
    out = run_both(S + "print(transcribe(\"ATGCTT\"))\n", capsys)
    assert out.strip() == "AUGCUU"


def test_gc_content(capsys):
    out = run_both(S + "print(gc_content(\"ATGCGC\"))\n"
                        "print(gc_content(\"AAAA\"))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[0] - 0.6666666666666666) < 1e-12
    assert lines[1] == 0.0


def test_translation_of_a_known_sequence(capsys):
    out = run_both(S + "print(translate(\"AUGUUUUAA\"))\n"
                        "print(translate(\"AUGGCUUGG\"))\n", capsys)
    assert out.strip().splitlines() == ["MF", "MAW"]


def test_a_stop_codon_ends_the_chain(capsys):
    out = run_both(S + "print(translate(\"AUGUAAUUUUUU\"))\n", capsys)
    assert out.strip() == "M"


def test_a_dna_sequence_translates_through_rna(capsys):
    out = run_both(S + "print(translate(\"ATGAAATTT\"))\n", capsys)
    assert out.strip() == "MKF"


def test_a_bad_codon_is_an_error():
    message = run_error(S + "print(translate(\"AUGXXX\"))\n")
    assert "codon" in message


def test_the_mass_of_a_small_protein(capsys):
    out = run_both(S + "print(protein_mass(\"MKWVTFISLL\"))\n", capsys)
    assert abs(number(out) - 1237.5658400000002) < 1e-6


def test_the_isoelectric_point_leans_with_the_charges(capsys):
    out = run_both(S + "print(isoelectric_point(\"KKKK\"))\n"
                        "print(isoelectric_point(\"DDDD\"))\n"
                        "print(isoelectric_point(\"A\"))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert lines[0] == 10.5
    assert lines[1] == 4.0
    assert lines[2] == 7.0
