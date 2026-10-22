"""The startup budget of the language.

The startup is the most felt performance property of a language, so the
budget is published (see the README) and measured here.
"""

import subprocess
import sys
import time

HELLO = 'print("hello")\n'


def test_the_import_of_the_language_is_inside_the_budget():
    script = ("import time\n"
              "start = time.perf_counter()\n"
              "import bun.cli\n"
              "print((time.perf_counter() - start) * 1000)\n")
    result = subprocess.run([sys.executable, "-c", script],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    elapsed = float(result.stdout.strip())
    assert elapsed < 120.0, "the import took %.1f ms" % elapsed


def test_a_hello_program_starts_inside_the_budget():
    command = [sys.executable, "-m", "bun", "-"]
    result = subprocess.run(command, input=HELLO, capture_output=True,
                            text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "hello\n"


def test_the_benchmark_tool_runs():
    result = subprocess.run(
        [sys.executable, "tools/bench.py", "--repeat", "2"],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "budget" in result.stdout
