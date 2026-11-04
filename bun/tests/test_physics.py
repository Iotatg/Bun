"""Tests for bun:physics — units, constants and the laws that use them."""

import pytest

from bun.cli import run_source
from bun.errors import BunRuntimeError, BunTypeError

P = "import { convert, convert_temperature, dimension_of, c, h, hbar, kB, G, " \
    "NA, R_gas, eps0, k_e, m_electron, m_proton, u_atomic, sigma_sb, alpha, " \
    "a0, Ry, g_earth, atm, phi0, M_sun, AU, parsec, H0, M_earth, pi, " \
    "velocity, acceleration, free_fall, free_fall_speed, projectile, " \
    "centripetal_force, force, momentum, kinetic_energy, potential_energy, " \
    "work, power, spring_force, spring_energy, weight, gravitational_force, " \
    "orbital_velocity, escape_velocity, orbital_period, synchronous_radius, " \
    "lorentz, time_dilation, length_contraction, rest_energy, total_energy, " \
    "relativistic_energy, relativistic_momentum, speed_from_energy, " \
    "redshift, photon_energy, photon_wavelength, photon_frequency, " \
    "photon_momentum, de_broglie, hydrogen_level, hydrogen_wavelength, " \
    "uncertainty_position, uncertainty_momentum, fermi_dirac, " \
    "planck_radiance, wien_peak, ideal_gas_pressure, ideal_gas_volume, " \
    "heat, radiated_power, carnot_efficiency, entropy_change, rms_speed, " \
    "mean_speed, coulomb_force, electric_field, electric_potential, ohm_law, " \
    "electric_power, lorentz_force, wave_speed, wave_frequency, " \
    "doppler_frequency, schwarzschild_radius, hawking_temperature, " \
    "hubble_speed, hubble_time, luminosity_distance } from \"bun:physics\"\n"


def run_both(source, capsys):
    run_source(source, filename="<physics>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<physics>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    run_source(source, filename="<physics>.bun", check=True, engine="register")
    assert capsys.readouterr().out == vm_out
    run_source(source, filename="<physics>.bun", check=True, engine="register",
               tier=True)
    assert capsys.readouterr().out == vm_out
    return vm_out


def run_error(source):
    with pytest.raises((BunRuntimeError, BunTypeError)) as info:
        run_source(source, filename="<physics>.bun", check=True, engine="vm")
    return info.value.msg


def number(text):
    return float(text.strip())


def test_a_kilometre_is_a_thousand_metres(capsys):
    out = run_both(P + "print(convert(1.0, \"km\", \"m\"))\n", capsys)
    assert number(out) == 1000.0


def test_an_electron_volt_is_the_exact_charge(capsys):
    out = run_both(P + "print(convert(1.0, \"eV\", \"J\"))\n", capsys)
    assert out.strip() == "1.602176634e-19"


def test_energy_units_agree(capsys):
    out = run_both(P + "print(convert(1.0, \"cal\", \"J\"))\n"
                        "print(convert(1.0, \"kWh\", \"J\"))\n"
                        "print(convert(1.0, \"hp\", \"W\"))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[0] - 4.184) < 1e-12
    assert abs(lines[1] - 3.6e6) < 1e-6
    assert abs(lines[2] - 745.6998715822702) < 1e-9


def test_a_length_cannot_become_a_mass():
    message = run_error(P + "print(convert(1.0, \"m\", \"kg\"))\n")
    assert "different dimensions" in message


def test_an_unknown_unit_names_itself():
    message = run_error(P + "print(convert(1.0, \"smoot\", \"m\"))\n")
    assert "smoot" in message


def test_temperature_scales_are_affine(capsys):
    out = run_both(P + "print(convert(100.0, \"degC\", \"K\"))\n"
                        "print(convert(32.0, \"degF\", \"K\"))\n"
                        "print(convert(0.0, \"degC\", \"degF\"))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[0] - 373.15) < 1e-12
    assert abs(lines[1] - 273.15) < 1e-12
    assert abs(lines[2] - 32.0) < 1e-12


def test_the_dimension_of_a_joule(capsys):
    out = run_both(P + "print(dimension_of(\"J\"))\n"
                        "print(dimension_of(\"Pa\"))\n"
                        "print(dimension_of(\"rad\"))\n", capsys)
    assert out.strip().splitlines() == ["L2 M1 T-2", "L-1 M1 T-2", "dimensionless"]


# ---------------------------------------------------------------------------
# Motion and force
# ---------------------------------------------------------------------------

def test_speed_is_distance_over_time(capsys):
    out = run_both(P + "print(velocity(100.0, 9.58))\n", capsys)
    assert abs(number(out) - 10.438413361169102) < 1e-12


def test_a_fall_goes_as_the_square_of_the_time(capsys):
    out = run_both(P + "print(free_fall(3.0, g_earth))\n"
                        "print(free_fall_speed(3.0, g_earth))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[0] - 44.129925) < 1e-9
    assert abs(lines[1] - 29.41995) < 1e-9


def test_a_projectile_at_forty_five_degrees(capsys):
    out = run_both(P + "let p = projectile(20.0, pi / 4.0, g_earth)\n"
                        "print(p[\"range\"])\n"
                        "print(p[\"height\"])\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[0] - 40.78864851911713) < 1e-9
    assert abs(lines[1] - 10.197162129779281) < 1e-9


def test_energy_and_work_agree(capsys):
    out = run_both(P + "print(kinetic_energy(2.0, 3.0))\n"
                        "print(potential_energy(2.0, 5.0, g_earth))\n"
                        "print(work(10.0, 3.0))\n"
                        "print(power(300.0, 3.0))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert lines[0] == 9.0
    assert abs(lines[1] - 98.0665) < 1e-12
    assert lines[2] == 30.0
    assert lines[3] == 100.0


def test_a_spring_pulls_back(capsys):
    out = run_both(P + "print(spring_force(200.0, 0.1))\n"
                        "print(spring_energy(200.0, 0.1))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert lines[0] == -20.0
    assert abs(lines[1] - 1.0) < 1e-12


# ---------------------------------------------------------------------------
# Gravity
# ---------------------------------------------------------------------------

def test_the_orbit_of_the_earth(capsys):
    out = run_both(P + "print(orbital_velocity(M_earth, 6.371e6))\n"
                        "print(escape_velocity(M_earth, 6.371e6))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[0] - 7910.0) < 20.0
    assert abs(lines[1] - 11186.0) < 30.0
    assert abs(lines[1] / lines[0] - 1.4142135623730951) < 1e-9


def test_keplers_third_law_gives_a_year(capsys):
    out = run_both(P + "print(orbital_period(M_sun, AU) / 86400.0)\n", capsys)
    assert abs(number(out) - 365.2) < 1.0


def test_a_geostationary_orbit_is_about_forty_two_thousand_kilometres(capsys):
    out = run_both(P + "print(synchronous_radius(M_earth, 86164.0) / 1000.0)\n",
                   capsys)
    assert abs(number(out) - 42164.0) < 200.0


def test_weight_is_mass_times_g(capsys):
    out = run_both(P + "print(weight(70.0, g_earth))\n", capsys)
    assert abs(number(out) - 686.4655) < 1e-9


# ---------------------------------------------------------------------------
# Relativity
# ---------------------------------------------------------------------------

def test_the_lorentz_factor_at_rest_is_one(capsys):
    out = run_both(P + "print(lorentz(0.0))\n", capsys)
    assert number(out) == 1.0


def test_the_lorentz_factor_at_ninety_nine_percent(capsys):
    out = run_both(P + "print(lorentz(0.99 * c))\n", capsys)
    assert abs(number(out) - 7.088812050083359) < 1e-9


def test_the_speed_of_light_is_a_wall():
    message = run_error(P + "print(lorentz(c))\n")
    assert "below the speed of light" in message


def test_time_dilation_and_length_contraction_are_reciprocal(capsys):
    out = run_both(P + "let v = 0.8 * c\n"
                        "print(time_dilation(1.0, v))\n"
                        "print(length_contraction(1.0, v))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[0] - 1.6666666666666667) < 1e-12
    assert abs(lines[1] - 0.6) < 1e-12


def test_a_kilogram_is_ninety_petajoules(capsys):
    out = run_both(P + "print(rest_energy(1.0))\n", capsys)
    assert out.strip() == "8.987551787368176e+16"


def test_speed_from_energy_returns_the_speed(capsys):
    out = run_both(P + "let v = 0.5 * c\n"
                        "let e = relativistic_energy(1.0, v)\n"
                        "print(speed_from_energy(1.0, e) / c)\n", capsys)
    assert abs(number(out) - 0.5) < 1e-9


def test_redshift_of_a_receding_source(capsys):
    out = run_both(P + "print(redshift(0.5 * c))\n", capsys)
    assert abs(number(out) - 1.7320508075688772) < 1e-12


# ---------------------------------------------------------------------------
# The quantum
# ---------------------------------------------------------------------------

def test_a_green_photon(capsys):
    out = run_both(P + "print(photon_energy(500e-9))\n"
                        "print(photon_frequency(500e-9))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[0] - 3.972891714297857e-19) < 1e-24
    assert abs(lines[1] - 5.99584916e14) < 1e8


def test_wavelength_and_energy_are_inverse(capsys):
    out = run_both(P + "print(photon_wavelength(photon_energy(500e-9)))\n", capsys)
    assert abs(number(out) - 500e-9) < 1e-18


def test_the_ground_state_of_hydrogen(capsys):
    out = run_both(P + "print(hydrogen_level(1))\n"
                        "print(hydrogen_level(2))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[0] + 2.1798723611035e-18) < 1e-30
    assert abs(lines[1] + 5.44968090275875e-19) < 1e-30


def test_the_h_alpha_line_is_656_nanometres(capsys):
    out = run_both(P + "print(hydrogen_wavelength(3, 2) * 1e9)\n", capsys)
    assert abs(number(out) - 656.11) < 0.05


def test_the_uncertainty_principle(capsys):
    out = run_both(P + "print(uncertainty_position(1e-24))\n"
                        "print(uncertainty_momentum(1e-9))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[0] - hbar_value() / 2e-24) < 1e-20
    assert abs(lines[1] - hbar_value() / 2e-9) < 1e-24


def hbar_value():
    return 1.054571817e-34


def test_wien_finds_the_sun_at_five_hundred_nanometres(capsys):
    out = run_both(P + "print(wien_peak(5778.0) * 1e9)\n", capsys)
    assert abs(number(out) - 501.5) < 1.0


def test_the_fermi_level_is_half_occupied(capsys):
    out = run_both(P + "print(fermi_dirac(0.0, 300.0))\n", capsys)
    assert abs(number(out) - 0.5) < 1e-12


# ---------------------------------------------------------------------------
# Heat
# ---------------------------------------------------------------------------

def test_a_mole_of_gas_at_stp_is_one_atmosphere(capsys):
    out = run_both(P + "print(ideal_gas_pressure(1.0, 273.15, 0.022413969545014137))\n",
                   capsys)
    assert abs(number(out) - 101325.0) < 0.5


def test_carnot_efficiency(capsys):
    out = run_both(P + "print(carnot_efficiency(500.0, 300.0))\n", capsys)
    assert abs(number(out) - 0.4) < 1e-12


def test_a_black_body_radiates_as_the_fourth_power(capsys):
    out = run_both(P + "print(radiated_power(1.0, 300.0, 1.0))\n"
                        "print(radiated_power(1.0, 600.0, 1.0))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[1] / lines[0] - 16.0) < 1e-9


def test_the_rms_speed_of_air(capsys):
    out = run_both(P + "print(rms_speed(300.0, 0.02897))\n", capsys)
    assert abs(number(out) - 508.0) < 5.0


# ---------------------------------------------------------------------------
# Electricity, waves and the sky
# ---------------------------------------------------------------------------

def test_two_coulombs_at_one_metre(capsys):
    out = run_both(P + "print(coulomb_force(1.0, 1.0, 1.0))\n", capsys)
    assert abs(number(out) - 8.9875517923e9) < 1e-3


def test_ohms_law_and_power(capsys):
    out = run_both(P + "print(ohm_law(12.0, 4.0))\n"
                        "print(electric_power(12.0, 3.0))\n", capsys)
    assert out.strip().splitlines() == ["3.0", "36.0"]


def test_a_wave_keeps_its_speed(capsys):
    out = run_both(P + "print(wave_speed(440.0, 0.78))\n"
                        "print(wave_frequency(343.0, 0.78))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[0] - 343.2) < 1e-9
    assert abs(lines[1] - 439.74358974358972) < 1e-9


def test_the_horizon_of_the_earth(capsys):
    out = run_both(P + "print(schwarzschild_radius(M_earth) * 1000.0)\n", capsys)
    assert abs(number(out) - 8.870) < 0.01


def test_a_black_hole_of_one_solar_mass(capsys):
    out = run_both(P + "print(schwarzschild_radius(M_sun) / 1000.0)\n"
                        "print(hawking_temperature(M_sun))\n", capsys)
    lines = [number(v) for v in out.strip().splitlines()]
    assert abs(lines[0] - 2.953) < 0.01
    assert abs(lines[1] - 6.17e-8) < 1e-9


def test_the_hubble_flow(capsys):
    out = run_both(P + "print(hubble_speed(1e6 * parsec) / 1000.0)\n", capsys)
    assert abs(number(out) - 70.0) < 0.01


def test_the_hubble_time_is_about_fourteen_billion_years(capsys):
    out = run_both(P + "print(hubble_time() / 31557600.0 / 1e9)\n", capsys)
    assert abs(number(out) - 13.97) < 0.2
