"""The tests of the `bun:math` module.

The module is written in Bun, so the values it gives are computed by
the language itself.  They are compared with the values of the
mathematics of Python, with a tolerance of a few units in the last
place, because the two answers are computed in a different order.
"""

import math
import shutil

import pytest

from bun.cli import run_source

ENGINES = ("tree", "vm", "register")


def _has_compiler():
    return shutil.which("cc") is not None


needs_compiler = pytest.mark.skipif(not _has_compiler(),
                                    reason="no C compiler")


def bun(source, capsys, engine="vm"):
    run_source(source, filename="<math>.bun", check=True, engine=engine)
    return capsys.readouterr().out.strip()


def bun_native(source, capfd):
    """Run a source with the native backend and read what it printed."""
    run_source(source, filename="<math>.bun", check=True, engine="c")
    return capfd.readouterr().out.strip()


def close(got, wanted, tolerance=1e-12):
    assert abs(got - wanted) <= tolerance * max(1.0, abs(wanted)), \
        "%r is not %r" % (got, wanted)


def test_the_square_root(capsys):
    out = bun('import { sqrt } from "bun:math"\n'
              "print(sqrt(2.0))\n"
              "print(sqrt(16.0))\n"
              "print(sqrt(0.0))\n", capsys)
    values = [float(line) for line in out.split("\n")]
    close(values[0], math.sqrt(2.0))
    close(values[1], 4.0)
    close(values[2], 0.0)


def test_the_exponential(capsys):
    out = bun('import { exp } from "bun:math"\n'
              "print(exp(0.0))\n"
              "print(exp(1.0))\n"
              "print(exp(-3.25))\n"
              "print(exp(10.0))\n", capsys)
    values = [float(line) for line in out.split("\n")]
    close(values[0], math.exp(0.0))
    close(values[1], math.exp(1.0))
    close(values[2], math.exp(-3.25))
    close(values[3], math.exp(10.0))


def test_the_logarithm(capsys):
    out = bun('import { log } from "bun:math"\n'
              "print(log(1.0))\n"
              "print(log(2.0))\n"
              "print(log(1000.0))\n", capsys)
    values = [float(line) for line in out.split("\n")]
    close(values[0], math.log(1.0))
    close(values[1], math.log(2.0))
    close(values[2], math.log(1000.0))


def test_the_circle(capsys):
    out = bun('import { sin, cos, tan } from "bun:math"\n'
              "print(sin(0.0))\n"
              "print(sin(1.0))\n"
              "print(cos(0.0))\n"
              "print(cos(1.0))\n"
              "print(tan(0.5))\n", capsys)
    values = [float(line) for line in out.split("\n")]
    close(values[0], math.sin(0.0))
    close(values[1], math.sin(1.0))
    close(values[2], math.cos(0.0))
    close(values[3], math.cos(1.0))
    close(values[4], math.tan(0.5))


def test_the_angles(capsys):
    out = bun('import { asin, atan, atan2 } from "bun:math"\n'
              "print(asin(0.5))\n"
              "print(atan(1.0))\n"
              "print(atan(-1.0))\n"
              "print(atan(10.0))\n"
              "print(atan2(1.0, 1.0))\n"
              "print(atan2(-1.0, -1.0))\n", capsys)
    values = [float(line) for line in out.split("\n")]
    close(values[0], math.asin(0.5))
    close(values[1], math.atan(1.0))
    close(values[2], math.atan(-1.0))
    close(values[3], math.atan(10.0))
    close(values[4], math.atan2(1.0, 1.0))
    close(values[5], math.atan2(-1.0, -1.0))


def test_the_powers(capsys):
    out = bun('import { pow } from "bun:math"\n'
              "print(pow(2.0, 10.0))\n"
              "print(pow(2.0, -2.0))\n"
              "print(pow(2.0, 0.5))\n"
              "print(pow(3.0, 3.0))\n", capsys)
    values = [float(line) for line in out.split("\n")]
    close(values[0], math.pow(2.0, 10.0))
    close(values[1], math.pow(2.0, -2.0))
    close(values[2], math.pow(2.0, 0.5))
    close(values[3], math.pow(3.0, 3.0))


def test_the_rounding(capsys):
    out = bun('import { floor, ceil, round, abs, min, max } from "bun:math"\n'
              "print(floor(2.7))\n"
              "print(floor(-2.1))\n"
              "print(ceil(2.1))\n"
              "print(ceil(-2.7))\n"
              "print(round(2.5))\n"
              "print(round(3.5))\n"
              "print(round(-2.5))\n"
              "print(abs(-3.0))\n"
              "print(min(2.0, 3.0))\n"
              "print(max(2.0, 3.0))\n", capsys)
    values = [float(line) for line in out.split("\n")]
    assert values == [2.0, -3.0, 3.0, -2.0, 2.0, 4.0, -2.0, 3.0, 2.0, 3.0]


def test_the_constants(capsys):
    out = bun('import { pi, e, tau } from "bun:math"\n'
              "print(pi)\n"
              "print(e)\n"
              "print(tau)\n", capsys)
    values = [float(line) for line in out.split("\n")]
    close(values[0], math.pi)
    close(values[1], math.e)
    close(values[2], math.tau)


def test_a_negative_number_has_no_square_root(capsys):
    from bun.errors import BunError
    with pytest.raises(BunError) as info:
        bun('import { sqrt } from "bun:math"\nprint(sqrt(-1.0))\n', capsys)
    assert "not negative" in info.value.msg


def test_every_engine_gives_the_same_answers(capsys):
    source = ('import { sqrt, exp, log, sin, cos } from "bun:math"\n'
              "print(sqrt(2.0))\n"
              "print(exp(1.0))\n"
              "print(log(2.0))\n"
              "print(sin(1.0))\n"
              "print(cos(1.0))\n")
    outputs = []
    for engine in ENGINES:
        outputs.append(bun(source, capsys, engine=engine))
    assert len(set(outputs)) == 1, outputs


@needs_compiler
def test_the_native_backend_gives_the_same_answers(capfd):
    source = ('import { sqrt, exp, log, sin, cos } from "bun:math"\n'
              "print(sqrt(2.0))\n"
              "print(exp(1.0))\n"
              "print(log(2.0))\n"
              "print(sin(1.0))\n"
              "print(cos(1.0))\n")
    expected = bun(source, capfd, engine="vm")
    assert bun_native(source, capfd) == expected
