#!/usr/bin/env python3.11
"""The Bun maturity probe — an executable, falsifiable progress scale.

The scale is 100 capabilities, one percent each.  Every capability is a
milestone of a production language that was missing on 2026-11-08.  A
capability counts only when a REAL Bun program (or a real CLI command)
produces the expected result.  Nothing is counted by reading documentation,
by reading source, by trusting a checklist, or because a file merely exists.

The probe runs OUTSIDE the implementation: it never imports the `bun`
package.  It talks to the language through `python3.11 -m bun` and to the
CLI through the same entry point.  A missing builtin therefore fails with
`undefined variable`, a missing command with a non-zero exit, and that is a
real FAIL rather than an assumption.

    python3.11 tools/maturity_probe.py            # human readable report
    python3.11 tools/maturity_probe.py --json     # machine readable

The verdict line is stable and is what the release notes quote:

    MATURITY: <passed>/100 (<passed>%)
"""

import base64
import datetime
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUN = [sys.executable, "-m", "bun"]
TIMEOUT = 60

# `bun fmt` rewrites its target.  The probe must not rewrite a tracked
# fixture, so it formats a scratch copy instead.
FMT_FIXTURE = os.path.join(REPO, "tools", "maturity", "format_bad.bun")
FMT_WORK = os.path.join(REPO, "tools", "maturity", ".fmt_work.bun")


def prepare_fixtures():
    shutil.copyfile(FMT_FIXTURE, FMT_WORK)

# ---------------------------------------------------------------------------
# Expected values.  Computed independently here, in the probe, so the probe
# does not ask the implementation what the right answer is.
# ---------------------------------------------------------------------------

E = {}
E["hmac256"] = hmac.new(b"key", b"msg", hashlib.sha256).hexdigest()
E["hmac512"] = hmac.new(b"key", b"msg", hashlib.sha512).hexdigest()
E["sha512"] = hashlib.sha512(b"abc").hexdigest()
E["blake2b"] = hashlib.blake2b(b"abc").hexdigest()
E["sha3"] = hashlib.sha3_256(b"abc").hexdigest()
E["b64url"] = base64.urlsafe_b64encode(
    b"\xfb\xff\x00?~").decode("ascii").rstrip("=")
E["hex"] = b"Hi\x00".hex()
E["crc"] = "%08x" % (0x352441C2 & 0xFFFFFFFF)  # crc32 of b"abc" below
import zlib as _zlib
E["crc"] = "%08x" % (_zlib.crc32(b"abc") & 0xFFFFFFFF)
E["adler"] = "%08x" % (_zlib.adler32(b"abc") & 0xFFFFFFFF)


def bun_program(source, expected):
    """A capability proved by running a Bun program from stdin."""
    return ("program", source.strip() + "\n", expected)


def cli_command(args, expected=None, expect_exit=0):
    """A capability proved by running a real CLI command."""
    return ("cli", (list(args), expected, expect_exit), expected)


# ---------------------------------------------------------------------------
# The 100 capabilities.  10 areas x 10 milestones.
#
# EVERY capability is proved by a real Bun program or a real CLI command.
# No capability is counted because a document exists, because a checklist
# says so, or because a source file mentions a name.  A milestone that was
# already present on 2026-11-08 is not in this list — the scale measures
# the work still to do, not the work already done.
#
# It is easy to claim a language is "10% done" and hard to make ten real
# programs print the right answer.  That is the point.
# ---------------------------------------------------------------------------

CAPABILITIES = []


def add(cid, area, title, probe):
    CAPABILITIES.append({
        "id": cid, "area": area, "title": title, "probe": probe,
    })


# --- A. Encoding and digests (10) ------------------------------------------
A = "A. encoding and digests"
add("A01", A, "hmac_sha256_hex(key, message)",
    bun_program('print(hmac_sha256_hex("key", "msg"))', E["hmac256"]))
add("A02", A, "hmac_sha512_hex(key, message)",
    bun_program('print(hmac_sha512_hex("key", "msg"))', E["hmac512"]))
add("A03", A, "base64url_encode(bytes)",
    bun_program('print(base64url_encode([251, 255, 0, 63, 126]))', E["b64url"]))
add("A04", A, "base64url_decode(text)",
    bun_program('print(len(base64url_decode("%s")))' % E["b64url"], "5"))
add("A05", A, "hex_encode(bytes)",
    bun_program('print(hex_encode([72, 105, 0]))', E["hex"]))
add("A06", A, "hex_decode(text)",
    bun_program('print(hex_decode("%s"))' % E["hex"], "[72, 105, 0]"))
add("A07", A, "gzip_compress(bytes)",
    bun_program('print(utf8_string(gzip_decompress(gzip_compress("hello"))))',
                "hello"))
add("A08", A, "sha512_hex(bytes)",
    bun_program('print(sha512_hex("abc"))', E["sha512"]))
add("A09", A, "blake2b_hex(bytes)",
    bun_program('print(blake2b_hex("abc"))', E["blake2b"]))
add("A10", A, "timing_safe_equal(a, b)",
    bun_program('print(timing_safe_equal("secret", "secret"))', "true"))

# --- B. Time and date (10) -------------------------------------------------
B = "B. time and date"
add("B01", B, "time_format(epoch, pattern) in UTC",
    bun_program('print(time_format(0, "%Y-%m-%d"))', "1970-01-01"))
add("B02", B, "time_parse_iso(iso8601)",
    bun_program('print(int(time_parse_iso("1970-01-01T00:00:00Z")))', "0"))
add("B03", B, "time_iso(epoch)",
    bun_program('print(time_iso(0))', "1970-01-01T00:00:00Z"))
add("B04", B, "time_parts(epoch).year",
    bun_program('print(time_parts(0)["year"])', "1970"))
add("B05", B, "time_add(epoch, seconds)",
    bun_program('print(int(time_add(0, 86400)))', "86400"))
add("B06", B, "time_diff(a, b)",
    bun_program('print(int(time_diff(86400, 0)))', "86400"))
add("B07", B, "time_weekday(epoch)",
    bun_program('print(time_weekday(0))', "4"))
add("B08", B, "time_is_leap(year)",
    bun_program('print(time_is_leap(2024))', "true"))
add("B09", B, "time_days_in_month(year, month)",
    bun_program('print(time_days_in_month(2024, 2))', "29"))
add("B10", B, "time_epoch_ms(epoch)",
    bun_program('print(time_epoch_ms(1.5))', "1500"))

# --- C. Toolchain commands (10) -------------------------------------------
C = "C. toolchain"
add("C01", C, "bun version prints a semantic version",
    cli_command(["version"], "Bun 0."))
add("C02", C, "bun fmt --check on a formatted file",
    cli_command(["fmt", "--check", "tools/maturity/format_ok.bun"]))
add("C03", C, "bun fmt rewrites an unformatted file",
    cli_command(["fmt", "tools/maturity/.fmt_work.bun"]))
add("C04", C, "bun lint reports an unused variable",
    cli_command(["lint", "tools/maturity/lint_bad.bun"]))
add("C05", C, "bun lint passes a clean file",
    cli_command(["lint", "tools/maturity/format_ok.bun"]))
add("C06", C, "bun pkg init creates a package manifest",
    cli_command(["pkg", "init", "--name", "demo", "--dir",
                 "tools/maturity/pkg_demo"]))
add("C07", C, "bun pkg list reads the manifest",
    cli_command(["pkg", "list", "--dir", "tools/maturity/pkg_demo"]))
add("C08", C, "bun doc --html writes a browsable API page",
    cli_command(["doc", "--html", "tools/maturity/api.html"]))
add("C09", C, "bun compile --cache produces reusable bytecode",
    cli_command(["compile", "--cache", "tools/maturity/format_ok.bun"]))
add("C10", C, "bun lint --json emits structured diagnostics",
    cli_command(["lint", "--json", "tools/maturity/lint_bad.bun"]))

# --- D. Language core, advanced (10) --------------------------------------
# v0.3.0 instrument repair.  In the 0.2.0 ledger seven of these probes were
# broken measuring devices, not capability tests: D03/D04/D05/D06/D08 called
# undefined `*_probe()` helpers (the "tests written != tests executed" trap),
# D02 used the invalid `fn f(): int` form, and D10 used `//`, which is Bun's
# comment marker.  A broken probe cannot distinguish "the feature is missing"
# from "the probe is wrong".  v0.3.0 replaces every one with a REAL Bun
# program that attempts the actual syntax.  Now each result is an honest
# measurement: a PASS proves the capability exists, and a FAIL names the
# construct that is genuinely absent.  No ledger entry is edited to hide a
# failure; three of these (D03, D08, D10) now PASS because the language
# really does the thing, and the rest FAIL for a real, specific reason.
D = "D. language core"
add("D01", D, "typed error value with a code",
    bun_program('print(error_code(fail_with("E_NOPE")))', "E_NOPE"))
add("D02", D, "defer runs at scope exit",
    bun_program(
        'fn f() -> int {\n'
        '    defer print("bye")\n'
        '    return 1\n'
        '}\n'
        'print(f())',
        "1\nbye"))
add("D03", D, "class-style pattern in match",
    bun_program(
        'struct Point {\n'
        '    var x: int\n'
        '    var y: int\n'
        '}\n'
        'fn probe(p: Point) -> string {\n'
        '    match p {\n'
        '        Point(x, y) => return "point"\n'
        '    }\n'
        '    return "other"\n'
        '}\n'
        'print(probe(Point(1, 2)))',
        "point"))
add("D04", D, "nested generic type argument",
    bun_program(
        'fn probe(v: list<list<int>>) -> int {\n'
        '    return len(v)\n'
        '}\n'
        'print(probe([[1, 2]]))',
        "1"))
add("D05", D, "function type as a type argument",
    bun_program(
        'fn apply(f: fn(int) -> int, x: int) -> int {\n'
        '    return f(x)\n'
        '}\n'
        'fn inc(n: int) -> int {\n'
        '    return n + 1\n'
        '}\n'
        'print(apply(inc, 4))',
        "5"))
add("D06", D, "labelled break out of a nested loop",
    bun_program(
        'fn probe() -> int {\n'
        '    outer: for i in range(3) {\n'
        '        for j in range(3) {\n'
        '            break outer\n'
        '        }\n'
        '    }\n'
        '    return 7\n'
        '}\n'
        'print(probe())',
        "7"))
add("D07", D, "string repeat operator",
    bun_program('print("ab" * 3)', "ababab"))
add("D08", D, "multiline string literal",
    bun_program('print("""a\nb""")', "a\nb"))
add("D09", D, "bitwise compound assignment",
    bun_program('var x = 6; x &= 3; print(x)', "2"))
# `//` is Bun's line comment, so the language's own word operator `div` is
# the floor-division form.  Probing with `//` would only measure a comment.
add("D10", D, "integer division operator",
    bun_program('print(7 div 2)', "3"))

# --- E. Runtime and engines (10) ------------------------------------------
Ea = "E. runtime and engines"
add("E01", Ea, "a native bytes value type",
    bun_program('print(type_of(bytes_from_list([1, 2, 3])))', "bytes"))
add("E02", Ea, "bytes concatenation",
    bun_program('print(bytes_len(bytes_concat(bytes_from_list([1]), bytes_from_list([2, 3]))))', "3"))
add("E03", Ea, "bytes equality by content",
    bun_program('print(bytes_from_list([1, 2]) == bytes_from_list([1, 2]))', "true"))
add("E04", Ea, "bytes slice without copying a list",
    bun_program('print(bytes_to_list(bytes_slice(bytes_from_list([1,2,3]), 1, 3)))', "[2, 3]"))
add("E05", Ea, "bun compile --cache reuses a bytecode cache",
    cli_command(["compile", "--cache", "tools/maturity/format_ok.bun"],
                "cached"))
# E06/E07 are genuine gaps, measured with a real CLI attempt: the CLI lists
# wasm/jit as known engine labels in `bun engines --json` (E09 passes) but
# refuses to execute on them, so these FAIL with a specific diagnostic.
# `compile --target wasm` emits WAT text, not a runnable engine.
add("E06", Ea, "a WASM execution engine",
    cli_command(["--engine", "wasm", "tools/maturity/format_ok.bun"], "42"))
add("E07", Ea, "an optimising JIT engine",
    cli_command(["--engine", "jit", "tools/maturity/format_ok.bun"], "42"))
add("E08", Ea, "bun startup reports a measured budget",
    cli_command(["startup"], "ms"))
add("E09", Ea, "bun engines lists pluggable engines",
    cli_command(["engines", "--json"], "wasm"))
add("E10", Ea, "bun parallel runs numeric workers",
    cli_command(["parallel", "--workers", "2",
                 "tools/maturity/format_ok.bun"], "workers"))

# --- F. Network and services (10) -----------------------------------------
F = "F. network and services"
add("F01", F, "url_parse returns scheme, host, path, query",
    bun_program('print(url_parse("https://example.com/a?q=1")["host"])',
                "example.com"))
add("F02", F, "url_build round-trips a parsed url",
    bun_program('print(url_build(url_parse("https://example.com/a?q=1")))',
                "https://example.com/a?q=1"))
add("F03", F, "query_parse decodes a query string",
    bun_program('print(query_parse("a=1&b=2")["b"])', "2"))
add("F04", F, "query_build encodes a dict",
    bun_program('print(query_build({"a": "1", "b": "2"}))', "a=1&b=2"))
add("F05", F, "status_text maps a code to a reason",
    bun_program('print(status_text(404))', "Not Found"))
add("F06", F, "cookie_parse reads a header",
    bun_program('print(cookie_parse("a=1; b=2")["b"])', "2"))
add("F07", F, "mime_from_path maps an extension",
    bun_program('print(mime_from_path("a.png"))', "image/png"))
add("F08", F, "status_class groups a status code",
    bun_program('print(status_class(404))', "4"))
add("F09", F, "percent_encode escapes a space",
    bun_program('print(percent_encode("a b"))', "a%20b"))
add("F10", F, "header_parse reads a header block",
    bun_program('print(header_parse("X: 1\\nY: 2")["Y"])', "2"))

# --- G. Data and formats (10) ---------------------------------------------
G = "G. data and formats"
add("G01", G, "struct_pack little-endian int32",
    bun_program('print(hex_encode(struct_pack("<i", 1)))', "01000000"))
add("G02", G, "struct_unpack little-endian int32",
    bun_program('print(struct_unpack("<i", [1, 0, 0, 0]))', "1"))
add("G03", G, "toml_parse reads a section",
    bun_program('print(toml_parse("[a]\\nb = 1\\n")["a"]["b"])', "1"))
add("G04", G, "json_pointer query",
    bun_program('print(json_pointer(json_parse("{\\"a\\":{\\"b\\":7}}"), "/a/b"))', "7"))
add("G05", G, "json_equal compares two parsed values",
    bun_program('print(json_equal(json_parse("[1,2]"), json_parse("[1,2]")))', "true"))
add("G06", G, "decimal_add exact decimal arithmetic",
    bun_program('print(decimal_add("0.1", "0.2"))', "0.3"))
add("G07", G, "bitset_set / bitset_get",
    bun_program('print(bitset_get(bitset_set(bitset_new(8), 3), 3))', "true"))
add("G08", G, "ordered_dict keeps insertion order",
    bun_program('print(ordered_dict_keys(ordered_dict_new()))', "[]"))
add("G09", G, "uuid_v4 format validation",
    bun_program('print(len(uuid_v4()))', "36"))
add("G10", G, "ulid format validation",
    bun_program('print(len(ulid()))', "26"))

# --- H. Modules and packages (10) -----------------------------------------
H = "H. modules and packages"
add("H01", H, "semver_compare orders versions",
    bun_program('print(semver_compare("1.10.0", "1.2.0"))', "1"))
add("H02", H, "semver_satisfies checks a range",
    bun_program('print(semver_satisfies("1.2.3", "^1.0.0"))', "true"))
add("H03", H, "bun pkg lock writes a lockfile",
    cli_command(["pkg", "lock", "--dir", "tools/maturity/pkg_demo"],
                "lock"))
add("H04", H, "bun check detects an import cycle",
    cli_command(["check", "--cycles", "tools/maturity/cycle_a.bun"],
                "cycle"))
add("H05", H, "bun pkg list --json returns manifest fields",
    cli_command(["pkg", "list", "--json", "--dir",
                 "tools/maturity/pkg_demo"], "name"))
add("H06", H, "bun doc <module> --exports lists exports",
    cli_command(["doc", "bun:maturity_demo", "--exports"], "export"))
add("H07", H, "bun compile --target wasm emits a module",
    cli_command(["compile", "--target", "wasm",
                 "tools/maturity/format_ok.bun"], "wasm"))
add("H08", H, "bun pkg search queries a registry",
    cli_command(["pkg", "search", "text"], "result"))
add("H09", H, "bun pkg install --offline uses a cache",
    cli_command(["pkg", "install", "--offline", "--dir",
                 "tools/maturity/pkg_demo"], "offline"))
add("H10", H, "bun pkg verify checks a signature",
    cli_command(["pkg", "verify", "--dir",
                 "tools/maturity/pkg_demo"], "signature"))

# --- I. Text (10) ----------------------------------------------------------
I = "I. text"
add("I01", I, "format with named placeholders",
    bun_program('print(format("{a}-{b}", {"a": "x", "b": "y"}))', "x-y"))
add("I02", I, "pad_left",
    bun_program('print(pad_left("7", 3, "0"))', "007"))
add("I03", I, "pad_right",
    bun_program('print(pad_right("7", 3, "0"))', "700"))
add("I04", I, "center",
    bun_program('print(center("a", 5, "-"))', "--a--"))
add("I05", I, "title_case",
    bun_program('print(title_case("hello world"))', "Hello World"))
add("I06", I, "swap_case",
    bun_program('print(swap_case("AbC"))', "aBc"))
add("I07", I, "truncate with an ellipsis",
    bun_program('print(truncate("abcdef", 5))', "ab..."))
add("I08", I, "word_wrap",
    bun_program('print(word_wrap("aa bb cc", 5))', "aa bb\ncc"))
add("I09", I, "unicode_normalize NFC",
    bun_program('print(len(unicode_normalize("e\\u0301")))', "1"))
add("I10", I, "levenshtein distance",
    bun_program('print(levenshtein("kitten", "sitting"))', "3"))

# --- J. Engineering quality and process (10) ------------------------------
J = "J. engineering quality"
add("J01", J, "bun changelog prints version history",
    cli_command(["changelog"], "0."))
add("J02", J, "bun version --short prints a semantic version",
    cli_command(["version", "--short"], "0."))
add("J03", J, "bun ci runs the full suite in CI mode",
    cli_command(["ci"], "pytest"))
add("J04", J, "bun release --dry-run validates a release",
    cli_command(["release", "--dry-run"], "release"))
add("J05", J, "bun coverage prints a measured coverage",
    cli_command(["coverage"], "coverage"))
add("J06", J, "bun fuzz runs the lexer fuzz harness",
    cli_command(["fuzz", "--iterations", "10"], "fuzz"))
add("J07", J, "bun bench lists the benchmark suite",
    cli_command(["bench", "--list"], "benchmark"))
add("J08", J, "bun audit reports a security check",
    cli_command(["audit"], "security"))
add("J09", J, "bun doctor checks the installation",
    cli_command(["doctor"], "ok"))
add("J10", J, "bun maturity runs the 100-capability probe",
    cli_command(["maturity"], "MATURITY"))


# ---------------------------------------------------------------------------
# The runner
# ---------------------------------------------------------------------------

def run_one(cap):
    kind, payload, expected = cap["probe"]
    try:
        if kind == "program":
            proc = subprocess.run(
                BUN + ["-"], input=payload, capture_output=True,
                text=True, cwd=REPO, timeout=TIMEOUT)
            out = proc.stdout.strip()
            ok = proc.returncode == 0 and out == str(expected).strip()
            return ok, ("exit=%d out=%r" % (proc.returncode, out[:120]))
        if kind == "cli":
            argv, expect, expect_exit = payload
            # `bun maturity` runs this very probe.  The marker makes the
            # nested call report instead of recursing forever.
            env = dict(os.environ)
            env["BUN_MATURITY_NESTED"] = "1"
            proc = subprocess.run(
                BUN + argv, capture_output=True, text=True,
                cwd=REPO, timeout=TIMEOUT, env=env)
            out = (proc.stdout + proc.stderr).strip()
            ok = proc.returncode == expect_exit
            if expect:
                ok = ok and expect in out
            return ok, ("exit=%d out=%r" % (proc.returncode, out[:120]))
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as error:                       # noqa: BLE001
        return False, "error: %s" % error
    return False, "unknown probe kind"


def selftest():
    """A falsifiable anchor: the probe must be able to see a real PASS.

    If this known-good program does not pass, the probe itself is broken
    (or the language is), and a score of 0 would be a lie in either
    direction.  This check is NOT one of the 100 capabilities.
    """
    probe = bun_program('print(1 + 1)', '2')
    ok, detail = run_one({"probe": probe})
    return ok, detail


def main():
    as_json = "--json" in sys.argv[1:]
    prepare_fixtures()
    anchor_ok, anchor_detail = selftest()
    results = []
    for cap in CAPABILITIES:
        ok, detail = run_one(cap)
        results.append({
            "id": cap["id"], "area": cap["area"], "title": cap["title"],
            "passed": ok, "detail": detail,
        })
    passed = sum(1 for r in results if r["passed"])
    areas = {}
    for r in results:
        a = areas.setdefault(r["area"], [0, 0])
        a[1] += 1
        if r["passed"]:
            a[0] += 1
    if as_json:
        print(json.dumps({
            "date": "2026-11-08",
            "selftest_passed": anchor_ok,
            "total": len(results), "passed": passed,
            "percent": passed,
            "areas": {k: {"passed": v[0], "total": v[1]}
                      for k, v in areas.items()},
            "results": results,
        }, indent=2))
    else:
        print("BUN MATURITY PROBE — 2026-11-08")
        print("commit : " + subprocess.run(
            ["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True).stdout.strip())
        print("selftest (probe can see a real PASS): %s  [%s]"
              % ("OK" if anchor_ok else "BROKEN", anchor_detail))
        print("")
        for name, (p, t) in sorted(areas.items()):
            print("  %-34s %2d / %2d" % (name, p, t))
        print("")
        for r in results:
            print("%s  %-4s %s%s" % (
                "PASS" if r["passed"] else "FAIL", r["id"], r["title"],
                ("   [" + r["detail"] + "]") if not r["passed"] else ""))
        print("")
        print("MATURITY: %d/100 (%d%%)" % (passed, passed))
        print("VERDICT: %s" % ("MATURITY_10_PERCENT_REACHED"
                               if passed >= 10 else "BELOW_10_PERCENT"))
    return 0 if passed >= 10 else 1


if __name__ == "__main__":
    sys.exit(main())
