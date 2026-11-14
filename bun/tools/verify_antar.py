#!/usr/bin/env python3.11
"""An external verifier of the Antar wave.

This script never imports the `bun` package.  It talks to the language the
way a user does — `python3 -m bun` — and checks the claims of the 0.8.0
release one by one.  A claim counts only when a real command produces the
expected result.

    python3.11 tools/verify_antar.py

Exit status 0 means every check passed.  The last line is the verdict.
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUN = [sys.executable, "-m", "bun"]
FIXTURE = os.path.join("tools", "maturity", "antar_core.bun")
EXPECTED = "6\n55\nneg\nzero\npos\n27\ntrue\n"

RESULTS = []


def run(args, stdin=None):
    return subprocess.run(BUN + args, cwd=ROOT, input=stdin,
                          capture_output=True, text=True, timeout=180)


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print("%-52s %s%s" % (name, "PASS" if ok else "FAIL",
                          "" if ok else "  " + detail))


def main():
    # 1. The graph of the fixture is structurally sound.
    result = run(["antar", FIXTURE, "--verify"])
    check("bun antar --verify exits 0", result.returncode == 0, result.stderr)
    check("the report says ANTAR: OK", "ANTAR: OK" in result.stdout,
          result.stdout[-200:])
    check("the report counts four flows", "4 pravah" in result.stdout,
          result.stdout[-200:])

    # 2. The JSON dump really contains blocks, edges, RPO and loops.
    result = run(["antar", FIXTURE, "--json"])
    data = json.loads(result.stdout) if result.returncode == 0 else {}
    flows = data.get("flows", [])
    check("bun antar --json exits 0", result.returncode == 0, result.stderr)
    check("the dump has at least four flows", len(flows) >= 4, str(len(flows)))
    blocks = [b for f in flows for b in f["blocks"]]
    check("every block has a terminator",
          bool(blocks) and all(b["nirnaya"] for b in blocks))
    check("every successor names a block",
          all(0 <= s < len(f["blocks"]) for f in flows
              for b in f["blocks"] for s in b["successors"]))
    check("every flow has a reverse postorder",
          all(f["reverse_postorder"] for f in flows))
    check("the fixture has two natural loops",
          sum(len(f["loops"]) for f in flows) == 2,
          str(sum(len(f["loops"]) for f in flows)))

    # 3. The DOT dump is a graph.
    result = run(["antar", FIXTURE, "--dot"])
    check("bun antar --dot exits 0", result.returncode == 0, result.stderr)
    check("the dot output is a digraph",
          result.stdout.startswith("digraph antar") and "->" in result.stdout)

    # 4. The stats are numbers, not prose.
    result = run(["antar", FIXTURE, "--stats"])
    stats = json.loads(result.stdout) if result.returncode == 0 else {}
    check("bun antar --stats exits 0", result.returncode == 0, result.stderr)
    check("the stats report blocks, edges and loops",
          all(key in stats for key in ("blocks", "edges", "loops", "dead")),
          str(sorted(stats)))
    check("the fixture has no dead khand", stats.get("dead") == [],
          str(stats.get("dead")))

    # 5. The engine agrees with the three engines that came before it.
    outputs = {}
    for engine in ("tree", "vm", "register", "antar"):
        result = run(["--engine", engine, FIXTURE])
        outputs[engine] = result.stdout
        check("--engine %s runs the fixture" % engine,
              result.returncode == 0 and result.stdout == EXPECTED,
              result.stderr[-200:])
    check("all four engines print the same bytes",
          len(set(outputs.values())) == 1, str(outputs))

    # 6. The engine is listed, and an unknown engine is refused.
    result = run(["engines", "--json"])
    names = [item["name"] for item in json.loads(result.stdout)["engines"]]
    check("bun engines lists antar", "antar" in names, str(names))
    result = run(["--engine", "nope", FIXTURE])
    check("an unknown engine exits 2", result.returncode == 2)
    check("the refusal names antar as a choice", "antar" in result.stderr,
          result.stderr)

    # 7. A construct outside the graph is refused by name.
    result = run(["--engine", "antar", "-"], stdin="for x in [1, 2] { print(x) }\n")
    check("a for over a list fails", result.returncode != 0)
    check("the refusal names the antar engine", "antar" in result.stderr,
          result.stderr[-300:])
    check("the refusal names range", "range" in result.stderr,
          result.stderr[-300:])

    # 8. The graph engine and the tree engine agree on a recursion program.
    source = ("fn fib(n: int) -> int {\n"
              "    if n < 2 { return n }\n"
              "    return fib(n - 1) + fib(n - 2)\n"
              "}\n"
              "print(fib(12))\n")
    tree = run(["--engine", "tree", "-"], stdin=source)
    graph = run(["--engine", "antar", "-"], stdin=source)
    check("recursion agrees on tree and antar",
          tree.stdout == graph.stdout == "144\n",
          "%r vs %r" % (tree.stdout, graph.stdout))

    # 9. The version is 0.7.0 and the package agrees.
    result = run(["version", "--short"])
    check("bun version --short is at least 0.8.0",
          tuple(int(p) for p in result.stdout.strip().split(".")) >= (0, 8, 0),
          result.stdout.strip())

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print()
    print("ANTAR VERIFIER: %d/%d checks passed" % (passed, total))
    print("VERDICT: %s" % ("ANTAR_WAVE_VERIFIED" if passed == total
                           else "ANTAR_WAVE_INCOMPLETE"))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
