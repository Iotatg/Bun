#!/usr/bin/env python3
"""Measure the speed of the native backend against the machine.

The backend turns a program into C and leaves the work to the compiler
of the system.  The number of this script is the number of the README:
the native backend runs the work of the language in the speed of C,
and the startup of the program is the price of the compiler.

Usage: python3 tools/bench_c.py [--repeat 3]
"""

import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROGRAM = """
fn fib(n) {
    if n < 2 {
        return n
    }
    return fib(n - 1) + fib(n - 2)
}

var total = 0
var i = 0
while i < 300000 {
    total = total + (i % 7)
    i = i + 1
}

print("total " + str(total))
print("fib " + str(fib(24)))
"""


def measure(command, repeat):
    """Return the fastest run of a command, in milliseconds."""
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
    repeat = 3
    if "--repeat" in sys.argv:
        repeat = int(sys.argv[sys.argv.index("--repeat") + 1])
    path = os.path.join(ROOT, "tools", "bench_c.bun")
    with open(path, "w") as handle:
        handle.write(PROGRAM)

    # The work of the compiler of the system is a price of the backend
    # and not a part of the run, so it is measured on its own.
    sys.path.insert(0, ROOT)
    from bun import cbackend
    from bun.compiler import Compiler
    from bun.lexer import Lexer
    from bun.parser import Parser
    from bun.regcompile import registerize

    source = PROGRAM
    program = Parser(Lexer(source).tokenize()).parse()
    code = Compiler(path, source).compile_program(program)
    reg = registerize(code)
    start = time.perf_counter()
    binary, directory = cbackend.build_binary(reg, path)
    compile_time = (time.perf_counter() - start) * 1000.0
    try:
        native = measure([binary], repeat)
    finally:
        cbackend.cleanup(directory)

    command = [sys.executable, "-m", "bun", "--engine", "vm", path]
    vm = measure(command, repeat)

    print("a program with a loop and a recursion (the fastest of %d runs)"
          % repeat)
    print("  vm            %8.1f ms" % vm)
    print("  c (the run)   %8.1f ms" % native)
    print("  c (the build) %8.1f ms" % compile_time)
    if native > 0:
        print("  the native backend is %.1f times faster" % (vm / native))
    return 0


if __name__ == "__main__":
    sys.exit(main())
