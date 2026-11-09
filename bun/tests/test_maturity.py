"""Tests of the 0.2.0, 0.3.0 and 0.4.0 maturity waves.

These tests check the things a checklist cannot: that the six registries
really agree, that the runtime really carries every builtin, that both
front ends really understand the new escapes and the 0.4.0 syntax, that the
native bytes / typed-error values really execute, that the toolchain commands
really do their work, and that the external probe really runs (and that no
capability is measured by a broken placeholder).
"""

import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bun import __version__, cbackend, docs, maturity, types  # noqa: E402
from bun.builtins import register_builtins  # noqa: E402
from bun.environment import Environment  # noqa: E402


def cli(*args, timeout=120):
    return subprocess.run(
        [sys.executable, "-m", "bun"] + list(args),
        cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def program(source, *extra, timeout=60):
    return subprocess.run(
        [sys.executable, "-m", "bun"] + list(extra) + ["-"],
        cwd=ROOT, input=source + "\n", capture_output=True, text=True,
        timeout=timeout)


# ---------------------------------------------------------------------------
# Registries
# ---------------------------------------------------------------------------

def test_the_sync_script_reports_no_drift():
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "sync_maturity.py"),
         "--check"], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout
    assert "check: OK" in result.stdout


def test_every_builtin_is_in_the_checker_and_the_native_name_list():
    for name in maturity.SIGNATURES:
        assert name in types.BUILTIN_SIGNATURES, name
        assert name in cbackend.LANGUAGE_BUILTINS, name


def test_every_builtin_is_in_the_docs_registry():
    entries = docs.docs_data()
    for name in maturity.SIGNATURES:
        assert name in entries, name
        assert entries[name]["signature"].startswith(name + "("), name
        assert entries[name]["summary"], name


def test_every_builtin_really_lives_in_the_runtime_environment():
    env = Environment()
    register_builtins(env)
    for name in maturity.SIGNATURES:
        assert env.has(name), name


def test_the_bun_written_mirrors_carry_every_builtin():
    checker = open(os.path.join(ROOT, "selfhost", "checker.bun"),
                   encoding="utf-8").read()
    docsrc = open(os.path.join(ROOT, "selfhost", "docs.bun"),
                  encoding="utf-8").read()
    for name in maturity.SIGNATURES:
        assert '"%s"' % name in checker, name
        assert '"%s"' % name in docsrc, name


def test_the_new_builtins_are_refused_by_name_in_the_c_backend():
    # They are known to the language but not translated into C.
    for name in ("hmac_sha256_hex", "time_iso", "levenshtein"):
        assert name in cbackend.LANGUAGE_BUILTINS
        assert name not in cbackend.SUPPORTED_BUILTINS


# ---------------------------------------------------------------------------
# The language itself: Unicode escapes in both front ends
# ---------------------------------------------------------------------------

ESCAPE_CASES = [
    ('print(len(unicode_normalize("e\\u0301")))', "1"),
    ('print("\\u0041\\u0042")', "AB"),
    ('print("\\x41")', "A"),
    ('print(len(f"\\u0061"))', "1"),
    ('print("\\U0001F600")', "\U0001f600"),
    ('print("\\u00e9")', "\u00e9"),
]


@pytest.mark.parametrize("source,expected", ESCAPE_CASES)
def test_unicode_escapes_in_the_python_front_end(source, expected):
    result = program(source)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


def test_unicode_escapes_in_the_bun_written_front_end(tmp_path):
    path = tmp_path / "escapes.bun"
    path.write_text("\n".join(line for line, _ in ESCAPE_CASES) + "\n",
                    encoding="utf-8")
    expected = "\n".join(value for _, value in ESCAPE_CASES)
    python = cli(str(path))
    bun = cli("--front-end", "bun", "--engine", "vm", str(path))
    assert python.returncode == 0, python.stderr
    assert bun.returncode == 0, bun.stderr
    assert bun.stdout.strip() == expected
    assert bun.stdout == python.stdout


def test_an_invalid_unicode_escape_is_reported():
    result = program('print("\\u00ZZ")')
    assert result.returncode != 0
    assert "unicode escape" in result.stderr


# ---------------------------------------------------------------------------
# The standard library, executed rather than described
# ---------------------------------------------------------------------------

LIBRARY_CASES = [
    ('print(hmac_sha256_hex("key", "msg"))',
     "2d93cbc1be167bcb1637a4a23cbff01a7878f0c50ee833954ea5221bb1b8c628"),
    ('print(time_iso(0))', "1970-01-01T00:00:00Z"),
    ('print(decimal_add("0.1", "0.2"))', "0.3"),
    ('print(url_parse("https://example.com/a?q=1")["host"])', "example.com"),
    ('print(levenshtein("kitten", "sitting"))', "3"),
    ('print(hex_encode(struct_pack("<i", 1)))', "01000000"),
    ('print(toml_parse("[a]\\nb = 1\\n")["a"]["b"])', "1"),
    ('print(center("a", 5, "-"))', "--a--"),
    ('print(bitset_get(bitset_set(bitset_new(8), 3), 3))', "true"),
    ('print(len(uuid_v4()))', "36"),
    ('print(semver_compare("1.10.0", "1.2.0"))', "1"),
    ('print(semver_satisfies("1.2.3", "^1.0.0"))', "true"),
    ('print(semver_satisfies("2.0.0", "^1.0.0"))', "false"),
]


@pytest.mark.parametrize("source,expected", LIBRARY_CASES)
def test_standard_library_programs(source, expected):
    result = program(source)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


# ---------------------------------------------------------------------------
# The 0.3.0 wave — native bytes, typed errors, and Bun-original syntax
# ---------------------------------------------------------------------------

def test_the_registry_owns_64_builtins():
    # 55 from 0.2.0 plus 9 native-value builtins added in 0.3.0.
    assert len(maturity.SIGNATURES) == 64


V030_CASES = [
    # a native bytes value type, not a list of integers
    ('print(type_of(bytes_from_list([1, 2, 3])))', "bytes"),
    ('print(bytes_to_list(bytes_from_list([9, 8, 7])))', "[9, 8, 7]"),
    ('print(bytes_len(bytes_concat(bytes_from_list([1]), '
     'bytes_from_list([2, 3]))))', "3"),
    ('print(bytes_to_list(bytes_from_list([1, 2]) + '
     'bytes_from_list([3])))', "[1, 2, 3]"),
    ('print(bytes_from_list([1, 2]) == bytes_from_list([1, 2]))', "true"),
    ('print(bytes_from_list([1, 2]) == bytes_from_list([1, 3]))', "false"),
    ('print(bytes_to_list(bytes_slice(bytes_from_list([1, 2, 3]), '
     '1, 3)))', "[2, 3]"),
    # a typed error value that a program can hold and inspect
    ('print(type_of(fail_with("X")))', "error"),
    ('print(error_code(fail_with("E_NOPE")))', "E_NOPE"),
    ('print(error_message(fail_with_message("E_BAD", "went wrong")))',
     "went wrong"),
    ('print(error_code(fail_with_message("E_BAD", "went wrong")))', "E_BAD"),
    ('print(is_error(fail_with("X")))', "true"),
    ('print(is_error(3))', "false"),
    # string repeat, both operand orders
    ('print("ab" * 3)', "ababab"),
    ('print(3 * "xy")', "xyxyxy"),
    # optional semicolons are decorative statement separators
    ('var x = 6; x &= 3; print(x)', "2"),
    # `div` — Bun's own word operator for floor division
    ('print(7 div 2)', "3"),
    ('print(7.0 div 2.0)', "3.0"),
    ('print(2 + 12 div 2)', "8"),
    # triple-quoted multiline strings, both quote styles
    ('print("""a\nb""")', "a\nb"),
    ("print('''x\ny''')", "x\ny"),
]


@pytest.mark.parametrize("source,expected", V030_CASES)
def test_v030_features_in_the_python_front_end(source, expected):
    result = program(source)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


def test_v030_syntax_parity_across_front_ends_and_engines(tmp_path):
    source = ('var x = 6; x &= 3; print(x)\n'
              'print(7 div 2)\n'
              'print("ab" * 3)\n'
              'print("""a\nb""")')
    path = tmp_path / "v030.bun"
    path.write_text(source + "\n", encoding="utf-8")
    expected = "2\n3\nababab\na\nb"
    outputs = []
    for engine in ("tree", "vm", "register"):
        result = cli("--engine", engine, str(path))
        assert result.returncode == 0, result.stderr
        outputs.append(result.stdout.strip())
    bun_front = cli("--front-end", "bun", "--engine", "vm", str(path))
    assert bun_front.returncode == 0, bun_front.stderr
    outputs.append(bun_front.stdout.strip())
    assert all(out == expected for out in outputs), outputs


def test_the_c_backend_refuses_div_by_name():
    result = program('print(7 div 2)', "--engine", "c")
    assert result.returncode != 0
    assert "does not support the 'div' floor-division operator" in result.stderr


def test_floordiv_is_a_real_register_opcode():
    from bun import regcode, regvm
    assert regcode.FLOORDIV == "FLOORDIV"
    assert regcode.BINARY_OPCODES["//"] == regcode.FLOORDIV
    assert regcode.FLOORDIV in regcode.OPERANDS
    assert hasattr(regvm.RegisterVM, "_op_floordiv")


def test_native_value_classes_are_zero_copy_and_compare_by_content():
    from bun.values import BunBytes, BunErrorValue, values_equal
    buf = BunBytes(bytes([1, 2, 3, 4]))
    assert isinstance(buf.data, memoryview)
    part = BunBytes(buf.data[1:3])
    assert bytes(part.data) == b"\x02\x03"
    # A slice is a view onto the same payload, not a copy or a list.
    assert part.data.obj is buf.data.obj
    assert values_equal(BunBytes([1, 2]), BunBytes([1, 2]))
    assert not values_equal(BunBytes([1, 2]), BunBytes([1, 3]))
    assert values_equal(BunErrorValue("E", "m"), BunErrorValue("E", "m"))
    assert not values_equal(BunErrorValue("E", "m"), BunErrorValue("F", "m"))


# ---------------------------------------------------------------------------
# The toolchain
# ---------------------------------------------------------------------------

def test_version_matches_the_version_file_and_package():
    version_file = open(os.path.join(ROOT, "VERSION"),
                        encoding="utf-8").read().strip()
    assert __version__ == version_file == "0.4.0"
    assert cli("version", "--short").stdout.strip() == __version__
    assert "Bun %s" % __version__ in cli("version").stdout


def test_fmt_really_rewrites_and_checks(tmp_path):
    bad = tmp_path / "bad.bun"
    bad.write_text("fn f() -> int {\n      return 1\n  }\nprint(f())\n")
    assert cli("fmt", "--check", str(bad)).returncode != 0
    assert cli("fmt", str(bad)).returncode == 0
    assert cli("fmt", "--check", str(bad)).returncode == 0
    assert "    return 1" in bad.read_text()


def test_lint_reports_an_unused_binding_and_emits_json():
    human = cli("lint", "tools/maturity/lint_bad.bun")
    assert human.returncode == 0
    assert "unused variable 'unused'" in human.stdout
    structured = json.loads(cli(
        "lint", "--json", "tools/maturity/lint_bad.bun").stdout)
    assert structured["reports"][0]["diagnostics"][0]["rule"] == \
        "unused-variable"


def test_pkg_roundtrip(tmp_path):
    directory = str(tmp_path / "pkg")
    assert cli("pkg", "init", "--name", "round", "--dir",
               directory).returncode == 0
    assert "round" in cli("pkg", "list", "--dir", directory).stdout
    assert '"name": "round"' in cli("pkg", "list", "--json", "--dir",
                                    directory).stdout
    assert "lock" in cli("pkg", "lock", "--dir", directory).stdout
    assert "signature: sha256:" in cli("pkg", "verify", "--dir",
                                       directory).stdout
    assert "offline:" in cli("pkg", "install", "--offline", "--dir",
                             directory).stdout
    assert "result:" in cli("pkg", "search", "text").stdout


def test_docs_html_and_exports(tmp_path):
    page = tmp_path / "api.html"
    result = cli("doc", "--html", str(page))
    assert result.returncode == 0
    text = page.read_text(encoding="utf-8")
    assert "hmac_sha256_hex" in text and "<table>" in text
    assert "export fn greet" in cli("doc", "bun:maturity_demo",
                                    "--exports").stdout


def test_compile_cache_and_wat_target():
    first = cli("compile", "--cache", "tools/maturity/format_ok.bun")
    second = cli("compile", "--cache", "tools/maturity/format_ok.bun")
    assert "cached:" in first.stdout and "cached:" in second.stdout
    assert "reused" in second.stdout
    assert "wasm:" in cli("compile", "--target", "wasm",
                          "tools/maturity/format_ok.bun").stdout


def test_check_finds_an_import_cycle():
    result = cli("check", "--cycles", "tools/maturity/cycle_a.bun")
    assert result.returncode == 0
    assert "cycle: tools/maturity/cycle_a.bun -> " in result.stdout


def test_engines_reports_what_is_and_is_not_implemented():
    data = json.loads(cli("engines", "--json").stdout)
    names = {item["name"] for item in data["engines"]}
    assert {"tree", "vm", "register", "c", "wasm", "jit"} <= names
    wasm = [item for item in data["engines"] if item["name"] == "wasm"][0]
    assert wasm["status"] == "not-implemented"


def test_engineering_commands_do_real_work():
    assert "ms" in cli("startup").stdout
    assert "workers: 2" in cli("parallel", "--workers", "2",
                               "tools/maturity/format_ok.bun").stdout
    assert "benchmark:" in cli("bench", "--list").stdout
    assert "security: audit scanned" in cli("audit").stdout
    assert "fuzz:" in cli("fuzz", "--iterations", "10").stdout
    assert "coverage:" in cli("coverage").stdout
    assert "pytest" in cli("ci").stdout
    assert "release: dry-run OK" in cli("release", "--dry-run").stdout
    assert "## 0.4.0" in cli("changelog").stdout
    assert "## 0.2.0" in cli("changelog").stdout
    assert "doctor: ok" in cli("doctor").stdout
    assert "MATURITY:" in cli("maturity").stdout


# ---------------------------------------------------------------------------
# The external, falsifiable probe
# ---------------------------------------------------------------------------

def test_no_capability_probe_is_an_undefined_helper_call():
    # A capability must be measured by a real program, never by a call to an
    # undefined `*_probe()` helper (the "tests written != tests executed"
    # trap that made part of the 0.2.0 D area a false negative).
    source = open(os.path.join(ROOT, "tools", "maturity_probe.py"),
                  encoding="utf-8").read()
    for helper in ("match_pattern_probe()", "nested_generic_probe()",
                   "fn_type_arg_probe()", "labelled_break_probe()",
                   "multiline_probe()"):
        assert helper not in source, "broken placeholder probe: " + helper


def test_the_remaining_failures_are_the_documented_gaps():
    # The two open items are genuine, honestly-measured gaps, not broken
    # instruments.  Lock this in so a future wave cannot silently "pass"
    # them by editing the ledger into something easier to satisfy.
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "maturity_probe.py"),
         "--json"], cwd=ROOT, capture_output=True, text=True, timeout=600)
    data = json.loads(result.stdout)
    failed = {item["id"] for item in data["results"]
              if not item["passed"]}
    assert failed == {"E06", "E07"}, failed
    assert data["passed"] == 98, data["passed"]


def test_the_maturity_probe_reports_a_real_score():
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "maturity_probe.py"),
         "--json"], cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["selftest_passed"] is True
    assert data["total"] == 100
    assert len(data["results"]) == 100
    assert len({item["id"] for item in data["results"]}) == 100
    assert data["passed"] >= 10, data["passed"]
    assert all(isinstance(item["passed"], bool) for item in data["results"])
