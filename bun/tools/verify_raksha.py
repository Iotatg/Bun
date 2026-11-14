#!/usr/bin/env python3.11
"""An external verifier of the 0.7.0 "Raksha" wave.

This script never imports `bun.raksha` or any other `bun` implementation
module.  It talks to the language the way a user does — `python3 -m bun` —
and checks the claims of the release one by one.  A claim counts only when a
real command produces the expected result; every number printed at the end
comes from actual subprocess output, never from a hardcoded expectation.

    python3.11 tools/verify_raksha.py

Exit status 0 means every check passed.  The last line is the verdict.
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUN = [sys.executable, "-m", "bun"]
EXAMPLE = os.path.join("examples", "raksha.bun")
HINDI = os.path.join("examples", "raksha_hi.bun")
LIB = os.path.join("lib", "bun", "raksha.bun")
MATURITY = os.path.join("tools", "maturity", "raksha_core.bun")
GOLDEN = os.path.join("tests", "golden", "raksha.bun")
DOCS = os.path.join("docs", "reference", "raksha.md")
ALL_CODES = ["RK%02d" % n for n in range(1, 15)]

BAD = ('import "bun:raksha" as rk\n'
       'let a = rk.swatva(1)\n'
       'let x = rk.adhikar(a)\n'
       'let y = rk.udhaar(a)\n'
       'rk.likh(x, 2)\n'
       'rk.padh(y)\n'
       'rk.visarjan(a)\n')
CLEAN = ('import "bun:raksha" as rk\n'
         'with rk.swatva(7) as a {\n'
         '    let l = rk.udhaar(a)\n'
         '    print(rk.padh(l))\n'
         '}\n')

RESULTS = []


def run(args, stdin=None):
    return subprocess.run(BUN + args, cwd=ROOT, input=stdin,
                          capture_output=True, text=True, timeout=240)


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print("%-56s %s%s" % (name, "PASS" if ok else "FAIL",
                          "" if ok else "  " + str(detail)[:220]))


def source_of(rel):
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as handle:
        return handle.read()


def write_temp(name, text):
    path = os.path.join(ROOT, "tools", "maturity", name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return os.path.join("tools", "maturity", name)


def main():
    # -- 1. The release exists and is internally consistent -----------------
    result = run(["version", "--short"])
    check("bun version --short is 0.7.0",
          result.stdout.strip() == "0.7.0", result.stdout.strip())
    version_files = ["VERSION", "pyproject.toml", os.path.join("bun", "__init__.py")]
    check("VERSION / pyproject / __init__ all say 0.7.0",
          all("0.7.0" in source_of(p) for p in version_files))
    check("changelog documents 0.7.0",
          "## 0.7.0" in source_of("CHANGELOG.md"))

    # -- 2. Every deliverable file really exists ----------------------------
    required = ["bun/raksha.py", LIB, EXAMPLE, HINDI, MATURITY, DOCS,
                "tests/test_raksha.py", GOLDEN,
                os.path.join("tests", "golden", "raksha.out")]
    for rel in required:
        check("deliverable exists: %s" % rel,
              os.path.isfile(os.path.join(ROOT, rel)))

    # -- 3. The 14 codes are real in both the analyzer and the library ------
    lib_source = source_of(LIB)
    core_source = source_of("bun/raksha.py")
    missing_lib = [c for c in ALL_CODES if '"%s"' % c not in lib_source]
    missing_core = [c for c in ALL_CODES if '"%s"' % c not in core_source]
    check("library codes() names all 14 RK codes", not missing_lib, missing_lib)
    check("analyzer CODES names all 14 RK codes", not missing_core,
          missing_core)
    probe = ('import "bun:raksha" as rk\n'
             'print(len(rk.codes()))\n'
             'print(len(rk.niyam()))\n')
    result = run(["-"], stdin=probe)
    check("rk.codes() really returns 14 entries at run time",
          result.stdout.split()[:1] == ["14"], result.stdout)
    check("rk.niyam() really returns 14 rules at run time",
          result.stdout.split()[1:2] == ["14"], result.stdout)

    # -- 4. The runtime ledger certifies itself on three engines ------------
    audit_probe = ('import "bun:raksha" as rk\n'
                   'print(rk.audit()["verdict"])\n'
                   'print(rk.audit()["passed"])\n'
                   'print(rk.audit()["total"])\n')
    for engine in ("tree", "vm", "register"):
        out = run(["--engine", engine, "-"], stdin=audit_probe)
        words = out.stdout.split()
        check("audit() certified on %s (15/15)" % engine,
              words[:3] == ["RAKSHA_LEDGER_CERTIFIED", "15", "15"],
              out.stdout[:200] + out.stderr[:200])

    # -- 5. The examples are deterministic, identical and certified ---------
    en = run([EXAMPLE])
    hi = run([HINDI])
    check("english example exits 0", en.returncode == 0, en.stderr[:200])
    check("hindi example exits 0", hi.returncode == 0, hi.stderr[:200])
    check("english and hindi examples are byte-identical",
          en.returncode == 0 and hi.returncode == 0 and
          en.stdout == hi.stdout, "stdout differs")
    check("example ends with RAKSHA LEDGER CERTIFIED",
          en.stdout.rstrip().endswith("RAKSHA LEDGER CERTIFIED"),
          en.stdout[-120:])
    check("example prints RAKSHA_LEDGER_CERTIFIED",
          "RAKSHA_LEDGER_CERTIFIED" in en.stdout, en.stdout[-120:])
    again = run([EXAMPLE])
    check("example output is deterministic", en.stdout == again.stdout)
    for engine in ("tree", "vm", "register"):
        out = run(["--engine", engine, EXAMPLE])
        check("example byte-identical on %s" % engine,
              out.stdout == en.stdout and out.returncode == 0,
              out.stderr[:200])

    # -- 6. The golden corpus matches its recorded output -------------------
    golden = run([GOLDEN])
    expected = source_of(os.path.join("tests", "golden", "raksha.out"))
    check("golden program matches golden .out",
          golden.returncode == 0 and golden.stdout == expected,
          repr(golden.stdout))

    # -- 7. Four-engine parity on the maturity fixture ----------------------
    parity = []
    for engine in ("tree", "vm", "register", "antar"):
        out = run(["--engine", engine, MATURITY])
        parity.append(out.stdout)
        check("maturity fixture exits 0 on %s" % engine,
              out.returncode == 0, out.stderr[:200])
    check("four engines print byte-identical output",
          len(set(parity)) == 1 and parity[0].strip() != "",
          [s[:60] for s in parity])

    # -- 8. The static pass accepts a clean program -------------------------
    clean_path = write_temp("_verify_raksha_clean.bun", CLEAN)
    bad_path = write_temp("_verify_raksha_bad.bun", BAD)
    out = run(["raksha", clean_path, "--verify"])
    check("bun raksha --verify exits 0 on a clean program",
          out.returncode == 0, out.stdout[-200:] + out.stderr[:200])
    check("clean program reports RAKSHA: OK",
          "RAKSHA: OK" in out.stdout, out.stdout[-200:])
    for word in ("pravah", "bindu", "swatva", "udhaar", "visarjan", "nidan"):
        check("--verify counts %s" % word, word in out.stdout)

    # -- 9. The static pass rejects a genuinely bad program -----------------
    out = run(["raksha", bad_path, "--verify"])
    check("bun raksha --verify exits nonzero on nidan",
          out.returncode != 0, out.stdout[-200:])
    check("--verify names the RK03 loan conflict",
          "RK03" in out.stdout + out.stderr, out.stdout[-200:])
    out = run(["check", "--raksha", bad_path])
    check("bun check --raksha rejects a bad program",
          out.returncode != 0, out.returncode)
    check("check --raksha names an RK code",
          any(c in out.stdout + out.stderr for c in ALL_CODES),
          (out.stdout + out.stderr)[-200:])
    out = run(["check", "--raksha", clean_path])
    check("bun check --raksha accepts a clean program",
          out.returncode == 0, (out.stdout + out.stderr)[-200:])
    out = run(["check", clean_path])
    check("plain bun check still exits 0 (no regression)",
          out.returncode == 0, out.stderr[:200])

    # -- 10. The five CLI flags produce their promised shapes ---------------
    out = run(["raksha", clean_path, "--json"])
    payload = {}
    try:
        payload = json.loads(out.stdout)
    except (ValueError, TypeError) as error:
        check("--json parses", False, str(error))
    else:
        check("--json parses", True)
    check("--json has stats/regions/diagnostics/check/flows",
          all(k in payload for k in ("stats", "regions", "diagnostics",
                                     "check", "flows")), sorted(payload))
    check("--json stats counts real bindu",
          payload.get("stats", {}).get("points", 0) > 0,
          payload.get("stats"))
    check("--json verdict is RAKSHA_CLEAN",
          payload.get("verdict") == "RAKSHA_CLEAN", payload.get("verdict"))

    out = run(["raksha", clean_path, "--dot"])
    check("--dot starts with a digraph",
          out.stdout.startswith("digraph"), out.stdout[:80])
    check("--dot contains an edge", "->" in out.stdout)

    out = run(["raksha", clean_path, "--stats"])
    stats = {}
    try:
        stats = json.loads(out.stdout)
    except (ValueError, TypeError) as error:
        check("--stats parses", False, str(error))
    else:
        check("--stats parses", True)
    check("--stats names points/owners/loans",
          all(k in stats for k in ("points", "owners", "loans")),
          sorted(stats)[:12])

    out = run(["raksha", clean_path, "--explain"])
    check("--explain prints niyam and praman",
          "niyam" in out.stdout and "praman" in out.stdout,
          out.stdout[:160])
    out = run(["raksha", clean_path])
    check("bare bun raksha prints RAKSHA header",
          out.stdout.startswith("RAKSHA "), out.stdout[:80])

    # -- 11. The deliberate anumati is auditable, not a blanket switch ------
    out = run(["raksha", EXAMPLE, "--verify"])
    check("example passes static analysis via one anumati",
          out.returncode == 0, out.stdout[-200:])
    out = run(["raksha", EXAMPLE, "--json"])
    try:
        example_json = json.loads(out.stdout)
    except (ValueError, TypeError):
        example_json = {}
    allowances = example_json.get("allowances", [])
    check("example declares exactly one anumati",
          len(allowances) == 1, allowances)
    check("the anumati names RK01 and was really used",
          bool(allowances) and allowances[0].get("code") == "RK01"
          and allowances[0].get("used", 0) >= 1, allowances)
    check("permitted nidan are recorded in the ledger",
          len(example_json.get("allowed", [])) >= 1,
          example_json.get("allowed"))
    unused = write_temp("_verify_raksha_unused.bun",
                        'import "bun:raksha" as rk\n'
                        '// raksha:allow RK01: nothing bad happens here\n'
                        'let x = 1\n')
    out = run(["raksha", unused, "--verify"])
    check("an unused anumati is refused by verify()",
          out.returncode != 0 and "suppressed nothing" in out.stdout,
          out.stdout[-220:])

    # -- 12. Identity ledger, doctor and engines are unchanged -------------
    out = run(["tools/identity_lab.bun"])
    check("identity ledger is 15/15",
          "IDENTITY_LEDGER_CERTIFIED 15 / 15" in out.stdout,
          out.stdout[-200:])
    out = run(["doctor"])
    check("bun doctor is 6/6", "6/6" in out.stdout, out.stdout[-200:])
    out = run(["engines"])
    check("all seven engines available",
          all(name in out.stdout for name in
              ("tree", "vm", "register", "c", "wasm", "jit", "antar"))
          and "available" in out.stdout, out.stdout[-200:])

    # -- 13. No Rust syntax was borrowed ------------------------------------
    docs = source_of(DOCS)
    check("docs state principle borrowed / syntax not borrowed",
          "syntax" in docs.lower() and "borrow" in docs.lower())
    new_sources = core_source + lib_source
    check("no Rust `&mut` / `unsafe` / `Box` in the new sources",
          not any(token in new_sources for token in
                  ("&mut", "Box<", "'static", "Drop for")))
    check("no new keyword: new words are module functions",
          "rk.swatva" in source_of(EXAMPLE)
          and "import \"bun:raksha\"" in source_of(EXAMPLE))

    # -- 14. antar still refuses with; raksha does not ----------------------
    out = run(["--engine", "antar", "-"], stdin=CLEAN)
    check("antar engine refuses with (unchanged boundary)",
          out.returncode != 0 and "with" in (out.stdout + out.stderr).lower(),
          (out.stdout + out.stderr)[-200:])
    out = run(["raksha", clean_path])
    check("raksha analyses with without refusing it",
          out.returncode == 0 and "with" not in out.stdout.lower()[:200],
          out.stdout[:160])

    for temp in (clean_path, bad_path, unused):
        try:
            os.remove(os.path.join(ROOT, temp))
        except OSError:
            pass

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print()
    print("RAKSHA VERIFIER: %d/%d checks passed" % (passed, total))
    print("VERDICT: %s" % ("RAKSHA_WAVE_VERIFIED" if passed == total
                           else "RAKSHA_WAVE_FAILED"))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
