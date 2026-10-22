#!/usr/bin/env python3
"""Measure the startup time of the language.

The startup is the most felt performance property of a language, so the
budget is published and measured. The numbers of this script are the
numbers of the README.

Usage: python3 tools/bench.py [--repeat 7]
"""

import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BUDGETS = {
    "tree": 120.0,
    "vm": 140.0,
}


def measure(command, repeat):
    """Return the fastest run of a command, in milliseconds."""
    # The first run pays for the file cache of the interpreter, so it is
    # a warmup and not a measurement.
    subprocess.run(command, cwd=ROOT, capture_output=True)
    best = None
    for _ in range(repeat):
        start = time.perf_counter()
        subprocess.run(command, cwd=ROOT, capture_output=True)
        elapsed = (time.perf_counter() - start) * 1000.0
        if best is None or elapsed < best:
            best = elapsed
    return best


def main():
    repeat = 7
    if "--repeat" in sys.argv:
        repeat = int(sys.argv[sys.argv.index("--repeat") + 1])
    hello = os.path.join(ROOT, "tools", "hello.bun")
    with open(hello, "w") as handle:
        handle.write('print("hello")\n')
    results = {}
    for engine in ("tree", "vm"):
        command = [sys.executable, "-m", "bun", "--engine", engine, hello]
        results[engine] = measure(command, repeat)
    print("startup of a hello program (the fastest of %d runs)" % repeat)
    failures = 0
    for engine in ("tree", "vm"):
        value = results[engine]
        budget = BUDGETS[engine]
        state = "ok" if value <= budget else "OVER BUDGET"
        print("  %-5s %6.1f ms   budget %5.1f ms   %s"
              % (engine, value, budget, state))
        if value > budget:
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
