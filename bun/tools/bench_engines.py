#!/usr/bin/env python3
"""The interpreter-vs-compiler trade-off, measured on the same program.

Bun ships five engines on purpose:

  tree      a direct walk of the syntax tree — the fastest to start,
            the easiest to debug, the slowest to run a hot loop
  vm        a stack machine over the bytecode — the default
  register  a register machine, plus the tier of superinstructions
  c         the whole program lowered to C and compiled — the fastest
            to run, the slowest to start

An interpreter is not a slower compiler: it is the engine that lets you
change a line and run it again in milliseconds.  The compiler is the
engine that makes the finished program fast.  This script shows both
sides of that trade on one workload.

Usage: python3 tools/bench_engines.py [--n 2000000] [--repeat 3]
"""

import argparse
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROGRAM = """\
fn work(n) {
    var total = 0
    var i = 0
    while i < n {
        total = total + (i * 3) % 7
        i = i + 1
    }
    return total
}
print(work(__N__))
"""

ENGINES = [
    ("tree", ["--engine", "tree"]),
    ("vm", ["--engine", "vm"]),
    ("register", ["--engine", "register"]),
    ("register+tier", ["--engine", "register", "--tier"]),
    ("c", ["--engine", "c"]),
]


def measure(command, repeat):
    """Fastest of `repeat` runs, in milliseconds, plus the output."""
    best, output = None, ""
    for _ in range(repeat):
        start = time.perf_counter()
        done = subprocess.run(command, cwd=ROOT, capture_output=True,
                              text=True)
        elapsed = (time.perf_counter() - start) * 1000.0
        if done.returncode != 0:
            return None, done.stderr.strip()
        output = done.stdout.strip()
        if best is None or elapsed < best:
            best = elapsed
    return best, output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=2000000)
    parser.add_argument("--repeat", type=int, default=3)
    options = parser.parse_args()

    source = PROGRAM.replace("__N__", str(options.n))
    handle = tempfile.NamedTemporaryFile("w", suffix=".bun", delete=False)
    handle.write(source)
    handle.close()
    try:
        rows = []
        for name, flags in ENGINES:
            command = [sys.executable, "-m", "bun"] + flags + [handle.name]
            elapsed, output = measure(command, options.repeat)
            rows.append((name, elapsed, output))

        base = next((row[1] for row in rows if row[0] == "vm"), None)
        print("workload: %d loop steps, fastest of %d runs"
              % (options.n, options.repeat))
        print("%-14s %10s %10s  %s" % ("engine", "ms", "vs vm", "output"))
        for name, elapsed, output in rows:
            if elapsed is None:
                print("%-14s %10s %10s  %s" % (name, "-", "-", output[:40]))
                continue
            ratio = "-" if not base or name == "vm" else \
                "%.2fx" % (elapsed / base)
            print("%-14s %10.1f %10s  %s" % (name, elapsed, ratio, output))
    finally:
        os.unlink(handle.name)


if __name__ == "__main__":
    main()
