"""Compare the golden corpus under the machine and under the native backend.

Every program of the corpus must print the same thing under the native
backend, or the backend must refuse it by name.  A program that prints
something else is a bug in the backend.

    python3 tools/corpus_c.py
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN = os.path.join(ROOT, "tests", "golden")


def run(engine, path):
    """Run a program and return (output, error)."""
    result = subprocess.run(
        [sys.executable, "-m", "bun", "--engine", engine, path],
        cwd=ROOT, capture_output=True, text=True, timeout=300)
    return result.stdout, result.stderr, result.returncode


def main():
    same = []
    refused = []
    different = []
    for name in sorted(os.listdir(GOLDEN)):
        if not name.endswith(".bun"):
            continue
        path = os.path.join(GOLDEN, name)
        out_path = path[:-4] + ".out"
        if not os.path.exists(out_path):
            continue
        source = open(path).read()
        wanted = open(out_path).read()
        input_path = path[:-4] + ".in"
        target = path
        if os.path.exists(input_path):
            source = source.replace("__INPUT__", open(input_path).read().strip())
            target = os.path.join("/tmp", "bun_corpus_" + name)
            with open(target, "w") as handle:
                handle.write(source)
        got, err, code = run("c", target)
        if "the C backend does not support" in err:
            refused.append(name)
            continue
        if code != 0:
            different.append(name + " (failed)")
            continue
        if got != wanted:
            different.append(name + " (different)")
            continue
        same.append(name)
    print("the same:   %d" % len(same))
    print("refused:    %d  %s" % (len(refused), ", ".join(refused)))
    print("different:  %d  %s" % (len(different), ", ".join(different)))
    return 1 if different else 0


if __name__ == "__main__":
    sys.exit(main())
