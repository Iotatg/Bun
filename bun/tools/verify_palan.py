#!/usr/bin/env python3.11
"""An external verifier of the 0.9.0 "Palan" wave.

This script never imports `bun.palan` or any other `bun` implementation
module.  It talks to the language the way a user does — `python3 -m bun` —
and checks the claims of the release one by one.  A claim counts only when
a real command produces the expected result; every number printed at the
end comes from actual subprocess output, never from a hardcoded
expectation.

    python3.11 tools/verify_palan.py

Exit status 0 means every check passed.  The last line is the verdict.
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUN = [sys.executable, "-m", "bun"]
EXAMPLE = os.path.join("examples", "palan.bun")
HINDI = os.path.join("examples", "palan_hi.bun")
LIB = os.path.join("lib", "bun", "palan.bun")
DOCS = os.path.join("docs", "reference", "palan.md")
ALL_CODES = ["PL%02d" % n for n in range(1, 9)]

HEADER = 'import "bun:palan" as pl\nimport "bun:samanvay" as sv\n'

CLEAN = HEADER + (
    'fn w() {\n'
    '    pl.avadhi(100)\n'
    '    pl.jaanch()\n'
    '    return 1\n'
    '}\n'
    'let s = pl.rakshak("ek", 2, 100)\n'
    'pl.baccha(s, w, "w")\n'
    'print(pl.chalau(s)["children"])\n')

BAD_PL01 = HEADER + 'let s = pl.rakshak("ek", 3, 100)\n'
BAD_PL02 = HEADER + 'fn w() { return 1 }\npl.punar(w, 1, 2, 10)\n'
BAD_PL03 = HEADER + 'fn w() {\n    pl.avadhi(50)\n    return 1\n}\n'
BAD_PL04 = HEADER + (
    'fn w() { return 1 }\n'
    'let s = pl.rakshak("ek", 0, 100)\npl.baccha(s, w, "w")\n')
BAD_PL05 = HEADER + (
    'fn w() {\n    let l = sv.tal()\n    sv.pakad(l)\n'
    '    pl.sona(5)\n    sv.chhod(l)\n}\n')
BAD_PL06 = HEADER + 'let b = pl.vyavdhi(3, 0)\n'

RESULTS = []


def run(args, stdin=None, seed=None, timeout=240):
    env = dict(os.environ)
    env.pop("BUN_SAMANVAY_SEED", None)
    if seed is not None:
        env["BUN_SAMANVAY_SEED"] = str(seed)
    return subprocess.run(BUN + args, cwd=ROOT, input=stdin,
                          capture_output=True, text=True, timeout=timeout,
                          env=env)


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print("%-58s %s%s" % (name, "PASS" if ok else "FAIL",
                          "" if ok else "  " + str(detail)[:220]))


def source_of(rel):
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as handle:
        return handle.read()


def write_temp(name, text):
    path = os.path.join(ROOT, "tools", "maturity", name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return os.path.join("tools", "maturity", name)


def codes_of(rel):
    out = run(["palan", "--json", rel])
    try:
        return [n["code"] for n in json.loads(out.stdout)["nidan"]]
    except (ValueError, KeyError):
        return ["<bad json: %s>" % (out.stdout + out.stderr)[:80]]


def main():
    # -- 1. The release exists and is internally consistent -----------------
    result = run(["version", "--short"])
    check("bun version --short is at least 0.9.0",
          tuple(int(p) for p in result.stdout.strip().split(".")) >= (0, 9, 0),
          result.stdout.strip())
    version_files = ["VERSION", "pyproject.toml",
                     os.path.join("bun", "__init__.py")]
    check("VERSION / pyproject / __init__ all say 0.9.0",
          all("0.9.0" in source_of(p) for p in version_files))

    # -- 2. The ledger is eight and eight -----------------------------------
    out = run(["-"], stdin=HEADER + (
        'for r in pl.codes() {\n    print(r["code"])\n}\n'))
    codes = out.stdout.split()
    check("codes() returns PL01..PL08", codes == ALL_CODES, codes)

    out = run(["-"], stdin=HEADER + (
        'for r in pl.niyam() {\n    print(r["id"] + "|" + r["name"])\n}\n'))
    rows = [line.split("|") for line in out.stdout.strip().splitlines()]
    check("niyam() returns eight rows", [r[0] for r in rows] == ALL_CODES)
    check("every rule has a name", all(len(r) == 2 and r[1] for r in rows))

    out = run(["-"], stdin=HEADER + "pl.ledger()\n")
    check("the runtime ledger certifies 8/8",
          "PALAN_LEDGER_CERTIFIED 8/8" in out.stdout,
          (out.stdout + out.stderr)[-200:])

    # -- 3. Every static code fires, and only where it should ---------------
    for code, source in (("PL01", BAD_PL01), ("PL02", BAD_PL02),
                         ("PL03", BAD_PL03), ("PL04", BAD_PL04),
                         ("PL05", BAD_PL05), ("PL06", BAD_PL06)):
        rel = write_temp("palan_%s.bun" % code, source)
        found = codes_of(rel)
        check("%s is reported on a real program" % code, found == [code], found)

    rel = write_temp("palan_clean.bun", CLEAN)
    out = run(["palan", "--json", rel])
    check("a clean program has no nidan",
          json.loads(out.stdout)["nidan"] == [], out.stdout[:200])
    check("a clean program exits 0", out.returncode == 0, out.returncode)

    # -- 4. The clock is a clock --------------------------------------------
    out = run(["-"], stdin=HEADER + (
        'let a = pl.abhi()\npl.sona(50)\nprint(pl.abhi() - a)\n'))
    check("sona(50) moves the clock by 50", out.stdout.strip() == "50",
          out.stdout + out.stderr)

    out = run(["-"], stdin=HEADER + (
        'pl.sona(3600000)\nprint(pl.abhi())\n'))
    check("an hour of virtual time costs no wall clock",
          out.stdout.strip() == "3600000", (out.stdout + out.stderr)[-160:])

    out = run(["-"], stdin=HEADER + (
        'let a = pl.abhi()\nsv.ajna()\nsv.ajna()\nprint(pl.abhi() - a)\n'))
    check("two scheduling points cost two ticks", out.stdout.strip() == "2",
          out.stdout + out.stderr)

    out = run(["-"], stdin=HEADER + (
        'pl.avadhi(3)\nvar caught = ""\ntry {\n    pl.sona(5)\n'
        '    pl.jaanch()\n} catch e { caught = e }\nprint(caught)\n'))
    check("a deadline that passes is reported",
          "deadline exceeded" in out.stdout, out.stdout + out.stderr)

    # -- 5. The die is a die ------------------------------------------------
    out = run(["-"], stdin=HEADER + (
        'pl.sankat(1.0)\nprint(pl.jokhim())\npl.sankat(0.0)\n'
        'print(pl.jokhim())\n'))
    check("sankat(1.0) always fails and sankat(0.0) never does",
          out.stdout.split() == ["true", "false"], out.stdout)

    first = run(["-"], stdin=HEADER + (
        'pl.sankat(0.5)\nvar n = 0\n'
        'for i in range(0, 20) {\n    if pl.jokhim() { n = n + 1 }\n}\n'
        'print(n)\n'), seed=4).stdout
    again = run(["-"], stdin=HEADER + (
        'pl.sankat(0.5)\nvar n = 0\n'
        'for i in range(0, 20) {\n    if pl.jokhim() { n = n + 1 }\n}\n'
        'print(n)\n'), seed=4).stdout
    check("the die gives the same answers for the same seed", first == again,
          (first, again))

    # -- 6. Supervision -----------------------------------------------------
    out = run(["-"], stdin=HEADER + (
        'var n = 0\n'
        'fn flaky() {\n    n = n + 1\n    if n < 3 { throw "boom" }\n'
        '    return "ok"\n}\n'
        'let s = pl.rakshak("ek", 5, 1000)\npl.baccha(s, flaky, "f")\n'
        'let r = pl.chalau(s)\nprint(r["restarts"], n)\n'))
    check("a supervisor restarts a failing child twice",
          out.stdout.split() == ["2", "3"], out.stdout + out.stderr)

    out = run(["-"], stdin=HEADER + (
        'fn bad() { throw "always" }\n'
        'let s = pl.rakshak("ek", 1, 1000)\npl.baccha(s, bad, "b")\n'
        'var caught = ""\ntry { pl.chalau(s) } catch e { caught = e }\n'
        'print(caught)\n'))
    check("a supervisor escalates when the budget runs out",
          "escalated after 2 restarts" in out.stdout, out.stdout + out.stderr)

    out = run(["-"], stdin=HEADER + (
        'let s = pl.rakshak("ek", 1, 100)\nvar caught = ""\n'
        'try { pl.chalau(s) } catch e { caught = e }\nprint(caught)\n'))
    check("an empty supervisor refuses to run",
          "needs at least one child" in out.stdout, out.stdout)

    # -- 7. Retry and the breaker -------------------------------------------
    out = run(["-"], stdin=HEADER + (
        'var n = 0\nfn bad() {\n    n = n + 1\n    throw "no"\n}\n'
        'try { pl.punar(bad, 3, 1, 8) } catch e { }\nprint(n)\n'))
    check("punar tries exactly three times", out.stdout.strip() == "3",
          out.stdout + out.stderr)

    out = run(["-"], stdin=HEADER + (
        'fn bad() { throw "down" }\nfn ok() { return 7 }\n'
        'let b = pl.vyavdhi(1, 20)\n'
        'try { pl.guzar(b, bad) } catch e { }\n'
        'var refused = false\n'
        'try { pl.guzar(b, ok) } catch e { refused = true }\n'
        'print(b["state"], refused)\n'))
    check("a breaker opens and refuses", out.stdout.split() == ["khula", "true"],
          out.stdout + out.stderr)

    out = run(["-"], stdin=HEADER + (
        'fn bad() { throw "down" }\nfn ok() { return 7 }\n'
        'let b = pl.vyavdhi(1, 20)\n'
        'try { pl.guzar(b, bad) } catch e { }\npl.sona(25)\n'
        'print(pl.guzar(b, ok), b["state"])\n'))
    check("a breaker closes after its cooldown",
          out.stdout.split() == ["7", "band"], out.stdout + out.stderr)

    # -- 8. The example is a service with a bad disk ------------------------
    worlds = {run([EXAMPLE], seed=seed).stdout for seed in range(8)}
    check("the example produces more than one world in 8 seeds",
          len(worlds) > 1, len(worlds))
    one = run([EXAMPLE], seed=3)
    check("the example exits 0", one.returncode == 0, one.stderr[-200:])
    check("the example prints a verdict",
          "PALAN SERVICE" in one.stdout, one.stdout[-160:])

    same = run([EXAMPLE], seed=5).stdout
    again = run([EXAMPLE], seed=5).stdout
    check("the same seed replays the same bytes", same == again)

    # -- 9. Three engines, one answer ---------------------------------------
    outputs = set()
    for engine in ("tree", "vm", "register"):
        out = run(["--engine", engine, EXAMPLE], seed=3)
        outputs.add(out.stdout)
    check("tree, vm and register agree byte for byte", len(outputs) == 1,
          len(outputs))

    # -- 10. The wave is writable in every language pack ---------------------
    english = run([EXAMPLE], seed=0)
    hindi = run([HINDI], seed=0)
    check("the Hindi example runs", hindi.returncode == 0, hindi.stderr[-200:])
    check("the Hindi example is byte-identical to the English one",
          english.stdout == hindi.stdout)

    packs = source_of(os.path.join("bun", "langpacks.py"))
    check("no keyword was added",
          'SOFT_KEYWORDS = ("match", "scope", "spawn", "to")' in packs,
          packs[:0])

    # -- 11. The command answers five questions -----------------------------
    rel = write_temp("palan_cli.bun", BAD_PL06)
    out = run(["palan", "--json", rel])
    data = json.loads(out.stdout)
    check("--json carries the stats and the nidan",
          data["stats"]["nidan"] == 1 and data["nidan"][0]["code"] == "PL06")
    check("--json carries a hint",
          bool(data["nidan"][0]["hint"]))
    out = run(["palan", "--stats", rel])
    check("--stats is json", json.loads(out.stdout)["breakers"] == 1)
    out = run(["palan", "--explain", rel])
    check("--explain lists the eight codes",
          all(code in out.stdout for code in ALL_CODES))
    out = run(["palan", "--verify", rel])
    check("--verify exits 1 on a nidan", out.returncode == 1, out.returncode)
    out = run(["palan", "--dot", write_temp("palan_dot.bun", CLEAN)])
    check("--dot has an edge per child", '"s" -> "s/w"' in out.stdout,
          out.stdout[:200])
    out = run(["palan", "/nonexistent/nope.bun"])
    check("a missing file exits 2", out.returncode == 2, out.returncode)

    out = run(["check", "--palan", rel])
    check("bun check --palan reports the nidan", "palan[PL06]" in out.stderr,
          (out.stdout + out.stderr)[:200])
    check("bun check --palan exits 1", out.returncode == 1, out.returncode)
    out = run(["check", "--palan", write_temp("palan_check_clean.bun", CLEAN)])
    check("bun check --palan is silent on a clean program",
          out.returncode == 0 and "palan[" not in out.stderr,
          (out.stdout + out.stderr)[:200])

    # -- 12. --run and --chaos ---------------------------------------------
    rel = write_temp("palan_run.bun", HEADER + (
        'pl.sona(20)\nprint("done")\n'))
    out = run(["palan", "--run", "--seed=3", rel])
    check("--run reports the clock", "ticks=20" in out.stdout, out.stdout)
    check("--run reports the sleeps", "sleeps=1" in out.stdout, out.stdout)
    out = run(["palan", "--run", "--json", rel])
    check("--run --json is json", json.loads(out.stdout)["ticks"] == 20)

    rel = write_temp("palan_chaos.bun", HEADER + (
        'pl.sankat(0.5)\n'
        'fn w() {\n    if pl.jokhim() { throw "x" }\n    return 1\n}\n'
        'let s = pl.rakshak("ek", 0, 100)\npl.baccha(s, w, "w")\n'
        'try { pl.chalau(s) } catch e { }\n'))
    out = run(["palan", "--chaos=0:7", rel])
    check("--chaos sweeps eight seeds", "PALAN CHAOS: 8 seed(s)" in out.stdout,
          out.stdout[-200:])
    check("--chaos prints one line per seed",
          len([line for line in out.stdout.splitlines()
               if line.startswith("seed ")]) == 8)

    # -- 13. The documentation exists and says the hard parts ---------------
    text = source_of(DOCS)
    for phrase in ("virtual clock", "one tick per scheduling point",
                   "Bun joins, it does not kill", "PL01", "PL08",
                   "What the static pass does not see"):
        check("docs mention %r" % phrase, phrase in text)
    research = source_of(os.path.join("research", "failure_semantics.md"))
    for phrase in ("erlang.org", "exponential-backoff-and-jitter",
                   "martinfowler.com/bliki/CircuitBreaker",
                   "principlesofchaos.org"):
        check("research cites %s" % phrase, phrase in research)

    # -- 14. The library is Bun, and it is in the ledger --------------------
    lib = source_of(LIB)
    check("the policy is written in Bun", "export fn chalau(" in lib)
    check("the library declares its contract", "CONTRACT FOR THE OTHER AGENTS"
          in lib)
    check("the library names the five refusals",
          all(text in lib for text in (
              "palan: deadline exceeded", "palan: circuit breaker is open",
              "palan: supervisor escalated", "needs at least one child",
              "unknown restart strategy")))

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print()
    print("PALAN VERIFIER: %d/%d checks passed" % (passed, total))
    print("VERDICT: %s" % ("PALAN_WAVE_VERIFIED" if passed == total
                           else "PALAN_WAVE_FAILED"))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
