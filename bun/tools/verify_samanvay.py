#!/usr/bin/env python3.11
"""An external verifier of the 0.8.0 "Samanvay" wave.

This script never imports `bun.samanvay` or any other `bun` implementation
module.  It talks to the language the way a user does — `python3 -m bun` —
and checks the claims of the release one by one.  A claim counts only when
a real command produces the expected result; every number printed at the
end comes from actual subprocess output, never from a hardcoded
expectation.

    python3.11 tools/verify_samanvay.py

Exit status 0 means every check passed.  The last line is the verdict.
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUN = [sys.executable, "-m", "bun"]
EXAMPLE = os.path.join("examples", "samanvay.bun")
HINDI = os.path.join("examples", "samanvay_hi.bun")
RACE = os.path.join("examples", "samanvay_race.bun")
LIB = os.path.join("lib", "bun", "samanvay.bun")
DOCS = os.path.join("docs", "reference", "samanvay.md")
ALL_CODES = ["SV%02d" % n for n in range(1, 9)]

HEADER = 'import "bun:samanvay" as sv\n'

CLEAN = HEADER + (
    'let c = sv.sajha(0, "c")\n'
    'let l = sv.tal()\n'
    'fn w() {\n'
    '    sv.pakad(l)\n'
    '    sv.likh(c, sv.padh(c) + 1)\n'
    '    sv.chhod(l)\n'
    '}\n'
    'let h = sv.kary(w)\n'
    'sv.mel(h)\n'
    'print(sv.padh(c))\n')

BAD_SV01 = HEADER + (
    'var total = 0\n'
    'fn w() {\n    total = total + 1\n}\n'
    'let h = sv.kary(w)\nsv.mel(h)\n')

BAD_SV02 = HEADER + 'fn w() {\n    sv.ajna()\n}\nsv.kary(w)\n'

BAD_SV05 = HEADER + (
    'let ch = sv.kanal(1)\n'
    'fn w() {\n    sv.band(ch)\n    sv.band(ch)\n}\n'
    'let h = sv.kary(w)\nsv.mel(h)\n')

BAD_SV06 = HEADER + (
    'var shared = 0\n'
    'fn w() {\n    sv.ajna()\n    print(shared)\n}\n'
    'let h = sv.kary(w)\nshared = 1\nsv.mel(h)\n')

BAD_SV07 = HEADER + (
    'let a = sv.tal()\nlet b = sv.tal()\n'
    'fn left() {\n    sv.pakad(a)\n    sv.pakad(b)\n'
    '    sv.chhod(b)\n    sv.chhod(a)\n}\n'
    'fn right() {\n    sv.pakad(b)\n    sv.pakad(a)\n'
    '    sv.chhod(a)\n    sv.chhod(b)\n}\n'
    'let h1 = sv.kary(left)\nlet h2 = sv.kary(right)\n'
    'sv.mel(h1)\nsv.mel(h2)\n')

BAD_SV08 = HEADER + (
    'fn w() {\n    sv.ajna()\n}\n'
    'for i in range(0, 3) {\n    sv.kary(w)\n}\n')

RACY = HEADER + (
    'let c = sv.sajha(0, "c")\n'
    'fn w() {\n    let v = sv.padh(c)\n    sv.ajna()\n'
    '    sv.likh(c, v + 1)\n}\n'
    'let a = sv.kary(w)\nlet b = sv.kary(w)\n'
    'sv.mel(a)\nsv.mel(b)\n'
    'let t = sv.trace()\n'
    'print(sv.padh(c), len(t["races"]) > 0, t["schedule_hash"])\n')

DEADLOCK = HEADER + (
    'let a = sv.tal()\nlet b = sv.tal()\n'
    'fn left() {\n    sv.pakad(a)\n    sv.ajna()\n    sv.pakad(b)\n'
    '    sv.chhod(b)\n    sv.chhod(a)\n}\n'
    'fn right() {\n    sv.pakad(b)\n    sv.ajna()\n    sv.pakad(a)\n'
    '    sv.chhod(a)\n    sv.chhod(b)\n}\n'
    'let h1 = sv.kary(left)\nlet h2 = sv.kary(right)\n'
    'sv.mel(h1)\nsv.mel(h2)\n')

RESULTS = []


def run(args, stdin=None, seed=None):
    env = dict(os.environ)
    env.pop("BUN_SAMANVAY_SEED", None)
    if seed is not None:
        env["BUN_SAMANVAY_SEED"] = str(seed)
    return subprocess.run(BUN + args, cwd=ROOT, input=stdin,
                          capture_output=True, text=True, timeout=240,
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


def main():
    # -- 1. The release exists and is internally consistent -----------------
    result = run(["version", "--short"])
    check("bun version --short is at least 0.8.0",
          tuple(int(p) for p in result.stdout.strip().split(".")) >= (0, 8, 0),
          result.stdout.strip())
    version_files = ["VERSION", "pyproject.toml",
                     os.path.join("bun", "__init__.py")]
    check("VERSION / pyproject / __init__ all say 0.8.0",
          all("0.8.0" in source_of(p) for p in version_files))
    check("changelog documents 0.8.0", "## 0.8.0" in source_of("CHANGELOG.md"))
    for rel in (EXAMPLE, HINDI, RACE, LIB, DOCS,
                os.path.join("bun", "samanvay.py"),
                os.path.join("tests", "test_samanvay.py")):
        check("file exists: %s" % rel, os.path.exists(os.path.join(ROOT, rel)))

    # -- 2. The ledger is the same in three places --------------------------
    docs = source_of(DOCS)
    lib = source_of(LIB)
    py = source_of(os.path.join("bun", "samanvay.py"))
    for code in ALL_CODES:
        check("docs name %s" % code, code in docs)
        check("library names %s" % code, code in lib)
        check("python names %s" % code, code in py)

    # -- 3. The static pass: one real positive per code ---------------------
    cases = [("SV01", BAD_SV01), ("SV02", BAD_SV02), ("SV05", BAD_SV05),
             ("SV06", BAD_SV06), ("SV07", BAD_SV07), ("SV08", BAD_SV08)]
    temp_paths = []
    for code, text in cases:
        path = write_temp("samanvay_%s.bun" % code, text)
        temp_paths.append(path)
        out = run(["samanvay", "--json", path])
        try:
            payload = json.loads(out.stdout)
        except ValueError:
            payload = {"nidan": []}
        codes = [item["code"] for item in payload.get("nidan", [])]
        check("static pass reports %s" % code, code in codes, codes)
        check("%s exits 1" % code, out.returncode == 1, out.returncode)

    clean_path = write_temp("samanvay_clean.bun", CLEAN)
    temp_paths.append(clean_path)
    out = run(["samanvay", clean_path])
    check("a clean program has no nidan",
          out.returncode == 0 and "SAMANVAY: OK" in out.stdout,
          out.stdout[-160:])
    check("a clean program is not reported as SV01",
          "SV01" not in out.stdout)

    # -- 4. The command line -----------------------------------------------
    out = run(["samanvay", EXAMPLE])
    check("static report on the example is OK",
          out.returncode == 0 and "SAMANVAY: OK" in out.stdout,
          out.stdout[-160:])
    out = run(["samanvay", "--json", EXAMPLE])
    payload = json.loads(out.stdout)
    check("--json parses and has three tasks",
          payload["ok"] is True and len(payload["karies"]) == 3,
          len(payload.get("karies", [])))
    check("--json stats agree with the task list",
          payload["stats"]["karies"] == len(payload["karies"]))
    out = run(["samanvay", "--dot", EXAMPLE])
    check("--dot is a digraph", out.stdout.startswith("digraph samanvay {"))
    out = run(["samanvay", "--stats", EXAMPLE])
    check("--stats is json", json.loads(out.stdout)["karies"] == 3)
    out = run(["samanvay", "--verify", EXAMPLE])
    check("--verify says OK", out.returncode == 0 and "SAMANVAY: OK" in out.stdout)
    out = run(["samanvay", "--explain", EXAMPLE])
    check("--explain lists eight rules",
          all(code in out.stdout for code in ALL_CODES))
    out = run(["samanvay", "no-such-file.bun"])
    check("a missing file exits 2", out.returncode == 2, out.returncode)

    # -- 5. The scheduler: determinism is the claim ------------------------
    racy_path = write_temp("samanvay_racy.bun", RACY)
    temp_paths.append(racy_path)
    first = run([racy_path], seed=3)
    second = run([racy_path], seed=3)
    check("the same seed gives the same bytes",
          first.stdout == second.stdout and first.stdout.strip() != "",
          first.stdout.strip())
    check("a race is reported at seed 3", "true" in first.stdout)
    check("the update is lost at seed 3", first.stdout.startswith("1 "),
          first.stdout.strip())
    hashes = set()
    lost = set()
    for seed in range(8):
        out = run([racy_path], seed=seed)
        parts = out.stdout.strip().split()
        if parts:
            lost.add(parts[0])
            hashes.add(parts[2])
    check("different seeds explore different interleavings", len(hashes) >= 2,
          len(hashes))
    check("at least one seed keeps both increments", "2" in lost, lost)
    check("at least one seed loses one increment", "1" in lost, lost)

    # -- 6. Locks remove the race ------------------------------------------
    out = run(["samanvay", "--run", "--seed=0", clean_path])
    check("a locked program has no race",
          "races=0" in out.stdout and "SAMANVAY: 0 finding(s)" in out.stdout,
          out.stdout[-200:])

    # -- 7. Deadlock --------------------------------------------------------
    dead_path = write_temp("samanvay_dead.bun", DEADLOCK)
    temp_paths.append(dead_path)
    out = run(["samanvay", "--run", "--seed=0", dead_path])
    check("a deadlock is reported", "SV04 bandh" in out.stdout, out.stdout[-200:])
    check("the deadlock names a cycle", "cycle:" in out.stdout)
    check("the deadlock exits 1", out.returncode == 1)
    out = run(["samanvay", "--seeds=0:3", dead_path])
    check("the sweep finds a deadlock seed",
          "SAMANVAY SWEEP" in out.stdout and out.returncode == 1)

    # -- 8. The runtime refusals -------------------------------------------
    closed = write_temp("samanvay_closed.bun", HEADER + (
        'let ch = sv.kanal(1)\nsv.band(ch)\nsv.bhej(ch, 1)\n'))
    temp_paths.append(closed)
    out = run([closed])
    check("send after close is refused",
          out.returncode == 1 and "send on a closed channel" in out.stderr,
          out.stderr[-160:])
    twice = write_temp("samanvay_twice.bun", HEADER + (
        'let ch = sv.kanal(1)\nsv.band(ch)\nsv.band(ch)\n'))
    temp_paths.append(twice)
    out = run([twice])
    check("double close is refused",
          out.returncode == 1 and "already closed" in out.stderr,
          out.stderr[-160:])
    joined = write_temp("samanvay_join.bun", HEADER + (
        'fn w(n) {\n    return n * 2\n}\n'
        'let h = sv.kary(w, "w", [21])\nprint(sv.mel(h))\n'))
    temp_paths.append(joined)
    out = run([joined])
    check("join returns the child value", out.stdout.strip() == "42",
          out.stdout.strip())
    cancel = write_temp("samanvay_cancel.bun", HEADER + (
        'fn w() {\n    sv.ajna()\n    sv.ajna()\n}\n'
        'let h = sv.kary(w)\nsv.chhodo(h)\nsv.mel(h)\n'))
    temp_paths.append(cancel)
    out = run([cancel])
    check("a cancelled task refuses at a checkpoint",
          out.returncode == 1 and "cancelled" in out.stderr, out.stderr[-160:])

    # -- 9. The examples ----------------------------------------------------
    out = run([EXAMPLE])
    check("the pipeline example certifies",
          out.returncode == 0 and "SAMANVAY PIPELINE OK" in out.stdout,
          out.stdout[-160:])
    check("the pipeline reports no race", "races 0" in out.stdout)
    check("the pipeline reports the right total", "total 91" in out.stdout)
    english = run([EXAMPLE]).stdout
    hindi = run([HINDI]).stdout
    check("the Hindi example is byte-identical", english == hindi)
    engines = []
    for engine in ("tree", "vm", "register"):
        out = run(["--engine", engine, EXAMPLE], seed=3)
        engines.append(out.stdout)
    check("tree / vm / register agree byte for byte",
          engines[0] == engines[1] == engines[2] and engines[0] != "")
    zero = run([RACE], seed=0).stdout
    three = run([RACE], seed=3).stdout
    check("the race example keeps both increments at seed 0",
          "counter 2" in zero, zero.strip())
    check("the race example loses one at seed 3", "counter 1" in three,
          three.strip())

    # -- 10. The library, written in Bun -----------------------------------
    audit = write_temp("samanvay_audit.bun", HEADER + "sv.ledger()\n")
    temp_paths.append(audit)
    out = run([audit])
    check("the Bun-written audit certifies eight checks",
          "SAMANVAY_LEDGER_CERTIFIED 8/8" in out.stdout, out.stdout.strip())
    ledger = write_temp("samanvay_ledger.bun", HEADER + (
        'for r in sv.niyam() {\n    print(r["id"])\n}\n'))
    temp_paths.append(ledger)
    out = run([ledger])
    check("niyam() lists SV01..SV08",
          out.stdout.split() == ALL_CODES, out.stdout.split())

    # -- 11. The wave added no keyword -------------------------------------
    out = run(["langs", "--json"])
    try:
        packs = json.loads(out.stdout)
    except ValueError:
        packs = []
    rows = packs if isinstance(packs, list) else packs.get("languages", [])
    hindi_row = [row for row in rows
                 if (row.get("code") if isinstance(row, dict) else None) == "hi"]
    check("the Hindi pack still has 37 keywords",
          bool(hindi_row) and hindi_row[0].get("keywords") == 37,
          hindi_row[:1])
    check("the wave is not in the lexer as a keyword",
          "samanvay" not in source_of(os.path.join("bun", "lexer.py")).lower())

    # -- 12. The register-engine task bug is fixed -------------------------
    named = write_temp("samanvay_register.bun", HEADER + (
        'fn w() {\n    return 7\n}\n'
        'let h = sv.kary(w)\nprint(sv.mel(h))\n'))
    temp_paths.append(named)
    out = run(["--engine", "register", named])
    check("a task body compiled by the register engine runs",
          out.returncode == 0 and out.stdout.strip() == "7",
          (out.stdout + out.stderr)[-200:])

    # -- 13. The identity ledger grew without a keyword --------------------
    out = run(["tools/identity_lab.bun"])
    check("the identity ledger certifies",
          "IDENTITY_LEDGER_CERTIFIED" in out.stdout, out.stdout[-160:])
    check("the ledger has 16 families", "families         : 16" in out.stdout)
    check("the ledger has 20 forms", "forms            : 20" in out.stdout)
    check("the ledger still has 37 keywords",
          "keywords         : 37" in out.stdout)

    for temp in temp_paths:
        try:
            os.remove(os.path.join(ROOT, temp))
        except OSError:
            pass

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print()
    print("SAMANVAY VERIFIER: %d/%d checks passed" % (passed, total))
    print("VERDICT: %s" % ("SAMANVAY_WAVE_VERIFIED" if passed == total
                           else "SAMANVAY_WAVE_FAILED"))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
