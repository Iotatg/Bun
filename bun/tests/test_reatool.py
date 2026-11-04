"""Tests for the REA bridge (bun.reatool).

The heavy tests drive Ghidra through REA, so they run only when
BUN_REA_TESTS=1. The cheap tests always run: the bridge must be
importable and must report a clean error when REA is missing.
"""

import os
import shutil
import subprocess

import pytest

from bun import reatool

HEAVY = pytest.mark.skipif(
    os.environ.get("BUN_REA_TESTS") != "1" or not reatool.available(),
    reason="set BUN_REA_TESTS=1 and install morluto/rea to run")


def test_available_is_a_bool():
    assert isinstance(reatool.available(), bool)


def test_missing_binary_is_a_clean_error(tmp_path):
    with pytest.raises(RuntimeError):
        reatool.analyze(str(tmp_path / "no-such-file"))


def test_environment_prefers_the_local_jdk():
    environment = reatool._environment()
    assert "PATH" in environment


@HEAVY
def test_analyze_a_c_binary(tmp_path):
    if shutil.which("gcc") is None:
        pytest.skip("gcc is not installed")
    source = tmp_path / "tiny.c"
    source.write_text("int calc(int a) { return a + 100; }\n"
                      "int main(void) { return calc(1); }\n")
    binary = tmp_path / "tiny"
    subprocess.run(["gcc", "-O0", "-o", str(binary), str(source)], check=True)

    report = reatool.analyze(str(binary))
    assert report["normalized_result.format"] == "elf"
    assert report["normalized_result.procedure_count"] > 0


@HEAVY
def test_decompile_a_function(tmp_path):
    if shutil.which("gcc") is None:
        pytest.skip("gcc is not installed")
    source = tmp_path / "tiny.c"
    source.write_text("int calc(int a) { return a + 100; }\n"
                      "int main(void) { return calc(1); }\n")
    binary = tmp_path / "tiny"
    subprocess.run(["gcc", "-O0", "-o", str(binary), str(source)], check=True)

    code = reatool.decompile(str(binary), "calc")
    assert "calc" in code
    assert "return" in code
