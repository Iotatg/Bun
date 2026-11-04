"""The native fast path of `bun:quantum`.

The simulator in `lib/bun/quantum.bun` is written in Bun, which is the
point: the algorithm is readable and the language proves it can carry it.
But every amplitude is a walk through the interpreter, and a gate costs
2^n of those walks. At eight qubits that is fine, at twelve it is
seconds, at fourteen it is minutes.

These functions are the same arithmetic with the loop in Python. They do
not change a single result — the tests run both paths and compare — they
only move the inner loop out of the interpreter. A stack asks whether the
path is here with `has_builtin("quantum_apply")` and falls back to its
own Bun version when it is not.

An amplitude is a pair `[re, im]`, so a state of n qubits is a list of
2^n pairs. Nothing here imports anything: the runtime stays free of
dependencies.
"""

import math

from .dict import BunDict
from .errors import BunRuntimeError
from .values import Builtin


def _pairs(amp, name):
    if not isinstance(amp, list):
        raise BunRuntimeError("%s() expects the amplitudes of a state" % name)
    return amp


def _complex(value, name):
    if not isinstance(value, list) or len(value) != 2:
        raise BunRuntimeError("%s() expects a complex number as [re, im]" % name)
    return float(value[0]), float(value[1])


def _matrix(value, name):
    if not isinstance(value, list) or len(value) != 2:
        raise BunRuntimeError("%s() expects a 2x2 matrix" % name)
    row0 = value[0]
    row1 = value[1]
    if not isinstance(row0, list) or not isinstance(row1, list):
        raise BunRuntimeError("%s() expects a 2x2 matrix" % name)
    return (_complex(row0[0], name), _complex(row0[1], name),
            _complex(row1[0], name), _complex(row1[1], name))


def _width(amp):
    size = len(amp)
    if size == 0 or size & (size - 1):
        raise BunRuntimeError("the amplitudes must number a power of two")
    return size


def _apply(amp, m, q):
    """One gate on qubit q, as a flat list of reals."""
    size = _width(amp)
    if q < 0 or (1 << q) >= size:
        raise BunRuntimeError("qubit out of range: %d" % q)
    step = 1 << q
    (a_re, a_im), (b_re, b_im), (c_re, c_im), (d_re, d_im) = m

    flat = []
    for pair in amp:
        flat.append(float(pair[0]))
        flat.append(float(pair[1]))

    out = [0.0] * (size * 2)
    block = step * 2
    for base in range(0, size, block):
        for offset in range(step):
            i0 = base + offset
            i1 = i0 + step
            r0 = flat[2 * i0]
            m0 = flat[2 * i0 + 1]
            r1 = flat[2 * i1]
            m1 = flat[2 * i1 + 1]
            # row 0: a * x0 + b * x1
            out[2 * i0] = a_re * r0 - a_im * m0 + b_re * r1 - b_im * m1
            out[2 * i0 + 1] = a_re * m0 + a_im * r0 + b_re * m1 + b_im * r1
            # row 1: c * x0 + d * x1
            out[2 * i1] = c_re * r0 - c_im * m0 + d_re * r1 - d_im * m1
            out[2 * i1 + 1] = c_re * m0 + c_im * r0 + d_re * m1 + d_im * r1

    return [[out[2 * i], out[2 * i + 1]] for i in range(size)]


def _quantum_apply(args):
    if len(args) != 3:
        raise BunRuntimeError("quantum_apply() expects amplitudes, a matrix and a qubit")
    amp = _pairs(args[0], "quantum_apply")
    matrix = _matrix(args[1], "quantum_apply")
    if not isinstance(args[2], int) or isinstance(args[2], bool):
        raise BunRuntimeError("quantum_apply() expects a qubit number")
    return _apply(amp, matrix, args[2])


def _controlled(amp, m, control, target):
    size = _width(amp)
    if control == target:
        raise BunRuntimeError("controlled() needs two different qubits")
    if control < 0 or target < 0 or (1 << control) >= size or (1 << target) >= size:
        raise BunRuntimeError("controlled() qubit out of range")
    cbit = 1 << control
    tbit = 1 << target
    (a_re, a_im), (b_re, b_im), (c_re, c_im), (d_re, d_im) = m

    flat = []
    for pair in amp:
        flat.append(float(pair[0]))
        flat.append(float(pair[1]))
    out = list(flat)

    for i in range(size):
        if not (i & cbit) or (i & tbit):
            continue
        i1 = i | tbit
        r0 = flat[2 * i]
        m0 = flat[2 * i + 1]
        r1 = flat[2 * i1]
        m1 = flat[2 * i1 + 1]
        out[2 * i] = a_re * r0 - a_im * m0 + b_re * r1 - b_im * m1
        out[2 * i + 1] = a_re * m0 + a_im * r0 + b_re * m1 + b_im * r1
        out[2 * i1] = c_re * r0 - c_im * m0 + d_re * r1 - d_im * m1
        out[2 * i1 + 1] = c_re * m0 + c_im * r0 + d_re * m1 + d_im * r1

    return [[out[2 * i], out[2 * i + 1]] for i in range(size)]


def _quantum_controlled(args):
    if len(args) != 4:
        raise BunRuntimeError(
            "quantum_controlled() expects amplitudes, a matrix, a control and a target")
    amp = _pairs(args[0], "quantum_controlled")
    matrix = _matrix(args[1], "quantum_controlled")
    for index in (2, 3):
        if not isinstance(args[index], int) or isinstance(args[index], bool):
            raise BunRuntimeError("quantum_controlled() expects qubit numbers")
    return _controlled(amp, matrix, args[2], args[3])


def _quantum_probabilities(args):
    if len(args) != 1:
        raise BunRuntimeError("quantum_probabilities() expects the amplitudes")
    amp = _pairs(args[0], "quantum_probabilities")
    return [float(pair[0]) * float(pair[0]) + float(pair[1]) * float(pair[1])
            for pair in amp]


def _quantum_norm(args):
    if len(args) != 1:
        raise BunRuntimeError("quantum_norm() expects the amplitudes")
    amp = _pairs(args[0], "quantum_norm")
    total = 0.0
    for pair in amp:
        total += float(pair[0]) * float(pair[0]) + float(pair[1]) * float(pair[1])
    return math.sqrt(total)


def _quantum_sample(args):
    if len(args) != 2:
        raise BunRuntimeError("quantum_sample() expects the amplitudes and a draw")
    amp = _pairs(args[0], "quantum_sample")
    draw = float(args[1])
    running = 0.0
    last = 0
    for index, pair in enumerate(amp):
        running += float(pair[0]) * float(pair[0]) + float(pair[1]) * float(pair[1])
        last = index
        if draw <= running:
            return index
    return last


def _quantum_measure(args):
    if len(args) != 3:
        raise BunRuntimeError(
            "quantum_measure() expects the amplitudes, a qubit and a draw")
    amp = _pairs(args[0], "quantum_measure")
    q = args[1]
    draw = float(args[2])
    size = _width(amp)
    if not isinstance(q, int) or isinstance(q, bool) or q < 0 or (1 << q) >= size:
        raise BunRuntimeError("qubit out of range: %s" % q)
    bit = 1 << q
    p1 = 0.0
    for i in range(size):
        if i & bit:
            pair = amp[i]
            p1 += float(pair[0]) * float(pair[0]) + float(pair[1]) * float(pair[1])
    outcome = 1 if draw < p1 else 0
    keep = p1 if outcome == 1 else 1.0 - p1
    scale = 1.0 / math.sqrt(keep) if keep > 0.0 else 0.0
    out = []
    for i in range(size):
        pair = amp[i]
        is_one = bool(i & bit)
        if (outcome == 1) == is_one:
            out.append([float(pair[0]) * scale, float(pair[1]) * scale])
        else:
            out.append([0.0, 0.0])
    answer = BunDict()
    answer.set("amp", out)
    answer.set("outcome", outcome)
    answer.set("probability", keep)
    return answer


def _quantum_expectation(args):
    if len(args) != 3:
        raise BunRuntimeError(
            "quantum_expectation() expects the amplitudes, a matrix and a qubit")
    amp = _pairs(args[0], "quantum_expectation")
    m = _matrix(args[1], "quantum_expectation")
    q = args[2]
    size = _width(amp)
    if not isinstance(q, int) or isinstance(q, bool) or q < 0 or (1 << q) >= size:
        raise BunRuntimeError("qubit out of range: %s" % q)
    bit = 1 << q
    (a_re, a_im), (b_re, b_im), (c_re, c_im), (d_re, d_im) = m
    total = 0.0
    for i in range(size):
        i0 = i & ~bit
        i1 = i0 | bit
        r0 = float(amp[i0][0])
        m0 = float(amp[i0][1])
        r1 = float(amp[i1][0])
        m1 = float(amp[i1][1])
        if i & bit:
            t_re = c_re * r0 - c_im * m0 + d_re * r1 - d_im * m1
            t_im = c_re * m0 + c_im * r0 + d_re * m1 + d_im * r1
        else:
            t_re = a_re * r0 - a_im * m0 + b_re * r1 - b_im * m1
            t_im = a_re * m0 + a_im * r0 + b_re * m1 + b_im * r1
        # <i|psi> = conj(amp[i]) * t
        total += float(amp[i][0]) * t_re + float(amp[i][1]) * t_im
    return total


def _quantum_fidelity(args):
    if len(args) != 2:
        raise BunRuntimeError("quantum_fidelity() expects two states")
    left = _pairs(args[0], "quantum_fidelity")
    right = _pairs(args[1], "quantum_fidelity")
    if len(left) != len(right):
        raise BunRuntimeError("quantum_fidelity() needs two states of the same width")
    re = 0.0
    im = 0.0
    for i in range(len(left)):
        ar = float(left[i][0])
        ai = -float(left[i][1])
        br = float(right[i][0])
        bi = float(right[i][1])
        re += ar * br - ai * bi
        im += ar * bi + ai * br
    return re * re + im * im


def _quantum_flip_sign(args):
    if len(args) != 2:
        raise BunRuntimeError("quantum_flip_sign() expects the amplitudes and an index")
    amp = _pairs(args[0], "quantum_flip_sign")
    index = args[1]
    if not isinstance(index, int) or isinstance(index, bool):
        raise BunRuntimeError("quantum_flip_sign() expects an index")
    if index < 0 or index >= len(amp):
        raise BunRuntimeError("quantum_flip_sign() index out of range: %d" % index)
    out = [[float(pair[0]), float(pair[1])] for pair in amp]
    out[index] = [-out[index][0], -out[index][1]]
    return out


def _quantum_swap(args):
    if len(args) != 3:
        raise BunRuntimeError("quantum_swap() expects the amplitudes and two qubits")
    amp = _pairs(args[0], "quantum_swap")
    a, b = args[1], args[2]
    size = _width(amp)
    for q in (a, b):
        if not isinstance(q, int) or isinstance(q, bool) or q < 0 or (1 << q) >= size:
            raise BunRuntimeError("quantum_swap() qubit out of range: %s" % q)
    if a == b:
        return [[float(p[0]), float(p[1])] for p in amp]
    abit = 1 << a
    bbit = 1 << b
    out = [[0.0, 0.0] for _ in range(size)]
    for i in range(size):
        j = i
        if bool(i & abit) != bool(i & bbit):
            j = i ^ abit ^ bbit
        out[j] = [float(amp[i][0]), float(amp[i][1])]
    return out


SIGNATURES = {
    "quantum_apply": [((["any", "any", "int"]), "list")],
    "quantum_controlled": [((["any", "any", "int", "int"]), "list")],
    "quantum_probabilities": [((["any"], ), "list")],
    "quantum_norm": [((["any"], ), "float")],
    "quantum_sample": [((["any", "float"], ), "int")],
    "quantum_measure": [((["any", "int", "float"], ), "dict")],
    "quantum_expectation": [((["any", "any", "int"], ), "float")],
    "quantum_fidelity": [((["any", "any"], ), "float")],
}


def register_quantum(env):
    """Put the native fast path of the simulator into the environment."""
    table = {
        "quantum_apply": _quantum_apply,
        "quantum_controlled": _quantum_controlled,
        "quantum_probabilities": _quantum_probabilities,
        "quantum_norm": _quantum_norm,
        "quantum_sample": _quantum_sample,
        "quantum_measure": _quantum_measure,
        "quantum_expectation": _quantum_expectation,
        "quantum_fidelity": _quantum_fidelity,
        "quantum_flip_sign": _quantum_flip_sign,
        "quantum_swap": _quantum_swap,
    }
    for name, function in table.items():
        env.define(name, Builtin(name, function), False)
    return env
