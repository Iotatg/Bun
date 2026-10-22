import glob
import os

import pytest

from bun.cli import run_source

GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "golden")
ENGINES = ["tree", "vm", "register"]


def golden_cases():
    return sorted(glob.glob(os.path.join(GOLDEN_DIR, "*.bun")))


@pytest.mark.parametrize("path", golden_cases(), ids=os.path.basename)
@pytest.mark.parametrize("engine", ENGINES, ids=ENGINES)
def test_golden(path, capsys, engine):
    out_path = path[:-4] + ".out"
    if not os.path.exists(out_path):
        pytest.skip("golden module file, not a program")
    with open(path, "r") as handle:
        source = handle.read()
    with open(out_path, "r") as handle:
        expected = handle.read()
    input_path = path[:-4] + ".in"
    if os.path.exists(input_path):
        with open(input_path, "r") as handle:
            source = source.replace("__INPUT__", handle.read().strip())
    run_source(source, filename=path, engine=engine)
    assert capsys.readouterr().out == expected
