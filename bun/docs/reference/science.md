# The science stacks — `bun:quantum`, `bun:physics`, `bun:science`

Three stacks turn Bun into a workbench for the physical world. All three
are written in Bun itself, in `lib/bun/`, and need nothing but the
language: no wheel, no native extension, no network.

The design rule is the same in all three. A quantity is a number and a
unit; a conversion is refused when the dimensions disagree; a formula is
parsed, not looked up; a state is an exact vector of doubles. A program
that asks for something impossible — a metre converted into a kilogram, a
gate on a qubit that does not exist, a bracket left open in a chemical
formula — stops with a message that names the mistake.

---

## `bun:quantum` — a statevector simulator

A state of `n` qubits is a list of `2^n` complex amplitudes. A complex
number is a list of two floats, `[real, imaginary]`. Nothing is
approximated except the last bit of a double.

```bun
import { bell, probabilities, run, to_string } from "bun:quantum"

let q = bell()
print(probabilities(q))     // [0.4999999999999999, 0.0, 0.0, 0.4999999999999999]
print(run(q, 1000))         // {11: 514, 00: 486} — never 01 or 10
```

### Gates

| call | what it does |
|------|--------------|
| `state(n)` | the state \|0…0⟩ of `n` qubits |
| `apply(st, name, q)` | a named gate on one qubit |
| `apply_matrix(st, m, q)` | any 2×2 complex matrix |
| `h`, `x`, `y`, `z`, `s_gate`, `t_gate` | the named one-qubit gates |
| `phase(st, q, θ)` | \|1⟩ picks up `e^{iθ}` |
| `rotate_x/y/z(st, q, θ)` | a rotation of the Bloch sphere |
| `cnot`, `cz`, `cy` | a controlled gate, control first |
| `swap`, `toffoli` | two and three qubits |
| `circuit(n, ops)` | a list of operations, run in order |

The named gates are `i`, `x`, `y`, `z`, `h`, `s`, `sdg`, `t`, `tdg`. An
unknown name is an error rather than an identity, so a typo in a circuit
cannot pass silently.

### Measurement

`measure(st, q)` answers a dictionary, not a state: the collapsed state,
the outcome, and the probability that produced it. The shape is on
purpose — a collapse is not a gate, and a caller should not be able to
confuse the two.

```bun
import { h, state, measure, probabilities } from "bun:quantum"

let m = measure(h(state(1), 0), 0)
print(m["outcome"])              // 0 or 1
print(probabilities(m["state"])) // [1.0, 0.0] or [0.0, 1.0]
```

`run(st, shots)` measures the whole register `shots` times and answers a
dictionary of bit strings: `{"00": 503, "11": 497}`. `bit_string(i, n)`
writes an index the way a circuit diagram is read, top qubit first.

### The states and the algorithms

| call | the state |
|------|-----------|
| `bell()` | `(|00⟩ + |11⟩)/√2` |
| `ghz(n)` | all zeros in superposition with all ones |
| `w_state(n)` | exactly one qubit set, nobody knows which |
| `qft(st)` | the quantum Fourier transform, by the textbook circuit |
| `grover(n, marked, rounds)` | the search, `rounds` iterations |
| `grover_rounds(n)` | `floor(π/4 · √(2^n))`, the best number of rounds |

Grover is the one place where the numbers can be checked against
arithmetic rather than against a feeling. For three qubits and the index
5 marked, two rounds give

```
p(5) = 0.9453125
```

and the closed form `sin²(3θ)` with `sin θ = 1/√8` gives the same
0.9453125. For four items, one round lands exactly on the answer.

### Reading a state

`probabilities`, `probability(st, i)`, `probability_one(st, q)`, `norm`,
`normalize`, `fidelity(a, b)`, `bloch(st, q)`, `expectation(st, m, q)`,
`entropy(st)`. The entropy is the Shannon entropy of the measurement
distribution in bits: zero for a basis state, `n` for a uniform
superposition, one for a Bell pair.

The cost is the memory. Twelve qubits is 4096 amplitudes and immediate;
twenty is a million and takes a moment; `state()` refuses more than 24,
which is sixteen million amplitudes, rather than letting a program swap
until the machine gives up.

---

## `bun:physics` — units, constants and the laws

The unit table carries a dimension vector for each unit:
`[length, mass, time, current, temperature, amount, luminous intensity]`.
A joule is `[2, 1, -2, 0, 0, 0, 0]`, a pascal is `[-1, 1, -2, 0, 0, 0, 0]`,
and `convert()` compares the vectors before it multiplies anything.

```bun
import { convert, dimension_of } from "bun:physics"

convert(1.0, "km", "m")      // 1000.0
convert(1.0, "eV", "J")      // 1.602176634e-19, exact
convert(100.0, "degC", "K")  // 373.15
convert(1.0, "m", "kg")      // error: different dimensions
dimension_of("J")            // "L2 M1 T-2"
```

The temperature scales are affine, so they go through kelvin rather than
through a factor; `degC`, `degF` and `K` are the three names.

### The constants

`c`, `h`, `hbar`, `e_charge`, `kB`, `NA`, `R_gas`, `G`, `eps0`, `mu0`,
`k_e`, `m_electron`, `m_proton`, `m_neutron`, `u_atomic`, `sigma_sb`,
`alpha`, `a0`, `Ry`, `g_earth`, `atm`, `phi0`, `G0`, `M_sun`, `M_earth`,
`AU`, `parsec`, `H0`.

They are the SI 2019 values. `c`, `h`, `e_charge`, `kB` and `NA` are exact
by definition; `G` is the least certain at about 2.2·10⁻⁵ relative, and
the file says so.

### The laws

| family | calls |
|--------|-------|
| motion | `velocity`, `acceleration`, `free_fall`, `projectile`, `centripetal_force` |
| force and energy | `force`, `momentum`, `kinetic_energy`, `potential_energy`, `work`, `power`, `spring_force`, `spring_energy` |
| gravity | `weight`, `gravitational_force`, `orbital_velocity`, `escape_velocity`, `orbital_period`, `synchronous_radius` |
| relativity | `lorentz`, `time_dilation`, `length_contraction`, `rest_energy`, `total_energy`, `relativistic_energy`, `relativistic_momentum`, `speed_from_energy`, `redshift` |
| the quantum | `photon_energy`, `photon_wavelength`, `photon_frequency`, `photon_momentum`, `de_broglie`, `hydrogen_level`, `hydrogen_wavelength`, `uncertainty_position`, `uncertainty_momentum`, `fermi_dirac`, `planck_radiance`, `wien_peak` |
| heat | `ideal_gas_pressure`, `ideal_gas_volume`, `heat`, `radiated_power`, `carnot_efficiency`, `entropy_change`, `rms_speed`, `mean_speed` |
| electricity | `coulomb_force`, `electric_field`, `electric_potential`, `ohm_law`, `electric_power`, `lorentz_force` |
| waves | `wave_speed`, `wave_frequency`, `doppler_frequency` |
| the sky | `schwarzschild_radius`, `hawking_temperature`, `hubble_speed`, `hubble_time`, `luminosity_distance` |

A few numbers the tests pin down, because they are the ones a physicist
knows by heart:

| quantity | value |
|----------|-------|
| orbital speed at the Earth's surface | 7.91 km/s |
| escape speed from the Earth | 11.19 km/s |
| Lorentz factor at 0.99 c | 7.0888 |
| energy of one kilogram at rest | 8.9876·10¹⁶ J |
| Hα line (3 → 2, vacuum) | 656.11 nm |
| Wien peak of a 5778 K black body | 501.5 nm |
| Schwarzschild radius of the Earth | 8.87 mm |
| the Hubble time | 13.97 Gyr |

The speed of light is a wall, not a suggestion: `lorentz(c)` raises rather
than returning infinity.

---

## `bun:science` — chemistry and the molecules of life

The centre is a formula parser. It reads a formula the way a chemist
writes it: element symbols, counts, groups in brackets with a multiplier,
nested as deep as the formula goes.

```bun
import { molar_mass, composition, mass_percent } from "bun:science"

molar_mass("H2O")             // 18.015
molar_mass("C6H12O6")         // 180.156
molar_mass("Ca(OH)2")         // 74.092
molar_mass("Al2(SO4)3")       // 342.131077
composition("Ca(OH)2")        // {Ca: 1, O: 2, H: 2}
mass_percent("H2O", "H")      // 11.19
```

The masses are the standard atomic weights. The table holds the elements
a general program touches — 51 of them, from hydrogen to uranium — and an
unknown symbol is an error that names the symbol.

| family | calls |
|--------|-------|
| solutions | `moles`, `mass_of`, `molecules`, `molarity`, `dilution`, `dilution_volume`, `density`, `ppm` |
| acids | `ph`, `poh`, `hydrogen_concentration`, `buffer_ph` |
| radioactivity | `decay_constant`, `decay`, `decay_time`, `activity`, `activity_mass` |
| DNA and RNA | `dna_complement`, `reverse_complement`, `transcribe`, `gc_content` |
| protein | `translate`, `protein_mass`, `isoelectric_point` |

```bun
import { translate, gc_content, protein_mass } from "bun:science"

translate("AUGUUUUAA")        // "MF" — the stop codon ends the chain
translate("ATGAAATTT")        // "MKF" — DNA goes through RNA
gc_content("ATGCGC")          // 0.666…
protein_mass("MKWVTFISLL")    // 1237.57 Da
```

The genetic code is the standard one, all 64 codons. A codon that is not
in the table stops the translation with an error rather than being read
as an unknown amino acid.

---

## What the three stacks share

- **No dependency.** Every stack is Bun source in `lib/bun/`, loaded by
  `import ... from "bun:quantum"`.
- **Errors that name the mistake.** A bad unit, a bad element, a bad
  codon, a qubit out of range — each says what was wrong and what was
  expected.
- **The same answer on every engine.** The tests run each example on the
  tree, the bytecode VM, the register VM and the register VM with the
  tier, and compare the bytes.
- **Refusals instead of infinities.** A speed at `c`, a zero volume, a
  negative wavelength: the function raises instead of returning `inf` or
  `nan` that a later step would carry into a wrong answer.
