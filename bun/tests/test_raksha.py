"""Tests of the 0.7.0 wave: Raksha, Bun's own memory-safety analysis.

The wave is checked the way the Antar wave is checked: one program is run
on the engines that came before it and the bytes must agree, the graph is
checked as a graph (bindu, kinara, kaal, drops), each of the fourteen
nidan codes gets a real positive and a clean negative, and the command
line is exercised through ``python3 -m bun`` so a passing test cannot be
a Python helper quietly agreeing with itself.

Rust's *principles* were borrowed; none of its syntax was.  Every new word
in these tests is an ordinary module function name, and every cleanup is
Bun's own ``with`` statement.
"""

import json
import os
import subprocess
import sys
from contextlib import redirect_stdout
import io

import pytest

from bun.cli import run_source
from bun.intcore import Unsupported

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "raksha.bun")
HINDI = os.path.join(ROOT, "examples", "raksha_hi.bun")
MATURITY = os.path.join(ROOT, "tools", "maturity", "raksha_core.bun")
CORE = os.path.join(ROOT, "bun", "raksha.py")
LIB = os.path.join(ROOT, "lib", "bun", "raksha.bun")

ALL_CODES = ["RK%02d" % number for number in range(1, 15)]
HEADER = 'import "bun:raksha" as rk\n'

# A legal program: one owner, one shared loan, one read, one __exit__ drop.
CLEAN = HEADER + (
    "with rk.swatva(7) as a {\n"
    "    let l = rk.udhaar(a)\n"
    "    print(rk.padh(l))\n"
    "}\n")

ENGINES = ("tree", "vm", "register")
ENGINES4 = [("tree", False), ("vm", False),
            ("register", False), ("register", True)]


def core():
    """Import the new pass lazily, so collection never depends on order."""
    from bun import raksha
    return raksha


def plain(value):
    """A BunDict is not a Python dict; normalise it for assertions."""
    if hasattr(value, "keys") and not isinstance(value, dict):
        return {key: plain(value.get(key)) for key in value.keys()}
    if isinstance(value, list):
        return [plain(item) for item in value]
    return value


def run_engine(source, engine, capsys, tier=False):
    run_source(source, filename="<test>.bun", check=True, engine=engine,
               tier=tier)
    return capsys.readouterr().out


def parity(source, capsys, engines=ENGINES):
    outputs = [run_engine(source, engine, capsys) for engine in engines]
    assert len(set(outputs)) == 1, outputs
    return outputs[0]


def analyze(source):
    return core().analyze_source(source, "<test>.bun")


def codes_of(source):
    return {item.code for item in analyze(source).diagnostics}


def cli(*args):
    return subprocess.run([sys.executable, "-m", "bun"] + list(args),
                          cwd=ROOT, capture_output=True, text=True,
                          timeout=180)


# ---------------------------------------------------------------------------
# §5.10 — one positive (bad) and one negative (clean) source per code.
# The bad sources follow §3.2 literally; the clean ones are the same
# shapes with the violation removed, so a checker that only ever says
# "yes" fails fourteen tests and a checker that only ever says "no" fails
# fourteen more.
# ---------------------------------------------------------------------------

BAD = {
    "RK01": HEADER + ("let a = rk.swatva(1)\n"
                      "let b = rk.sanchay(a)\n"
                      "print(rk.padh(rk.udhaar(a)))\n"),
    "RK02": HEADER + ("let a = rk.swatva(1)\n"
                      "let b = rk.sanchay(a)\n"
                      "let c = rk.sanchay(a)\n"),
    "RK03": HEADER + ("let a = rk.swatva(1)\n"
                      "let x = rk.adhikar(a)\n"
                      "let y = rk.udhaar(a)\n"
                      "print(rk.padh(x))\n"
                      "print(rk.padh(y))\n"),
    "RK04": HEADER + ("let a = rk.swatva(1)\n"
                      "let x = rk.udhaar(a)\n"
                      "rk.likh(x, 2)\n"),
    "RK05": HEADER + ("let a = rk.swatva(1)\n"
                      "let x = rk.udhaar(a)\n"
                      "rk.visarjan(a)\n"
                      "print(rk.padh(x))\n"),
    "RK06": HEADER + ("let a = rk.swatva(1)\n"
                      "rk.visarjan(a)\n"
                      "print(rk.padh(rk.udhaar(a)))\n"),
    "RK07": HEADER + ("let a = rk.swatva(1)\n"
                      "rk.visarjan(a)\n"
                      "rk.visarjan(a)\n"),
    "RK08": HEADER + ("fn f() {\n"
                      "    let a = rk.swatva(1)\n"
                      "    let x = rk.udhaar(a)\n"
                      "    return x\n"
                      "}\n"),
    "RK09": HEADER + "let a = rk.swatva(1)\n",
    "RK10": HEADER + "Ok(1)\n",
    "RK11": HEADER + "some(1)\n",
    "RK12": HEADER + "let p = raw_pointer(1)\n",
    # `spawn(x)` is the direct form; the nested form also reaches the
    # implementation that only flags a loan while a spawn frame is open.
    "RK13": HEADER + ("let a = rk.swatva(1)\n"
                      "let x = rk.udhaar(a)\n"
                      "let t = spawn(x)\n"
                      "let u = spawn(spawn(x))\n"),
    "RK14": HEADER + ("with rk.swatva(1) as a, rk.swatva(2) as b {\n"
                      "    rk.visarjan(a)\n"
                      "}\n"),
}

GOOD = {
    "RK01": HEADER + ("let a = rk.swatva(1)\n"
                      "let b = rk.sanchay(a)\n"
                      "print(rk.padh(rk.udhaar(b)))\n"
                      "rk.visarjan(b)\n"),
    "RK02": HEADER + ("let a = rk.swatva(1)\n"
                      "let b = rk.sanchay(a)\n"
                      "rk.visarjan(b)\n"),
    "RK03": HEADER + ("with rk.swatva(1) as a {\n"
                      "    let x = rk.udhaar(a)\n"
                      "    let y = rk.udhaar(a)\n"
                      "    print(rk.padh(x))\n"
                      "    print(rk.padh(y))\n"
                      "}\n"),
    "RK04": HEADER + ("with rk.swatva(1) as a {\n"
                      "    let x = rk.adhikar(a)\n"
                      "    print(rk.likh(x, 2))\n"
                      "}\n"),
    "RK05": HEADER + ("let a = rk.swatva(1)\n"
                      "let x = rk.udhaar(a)\n"
                      "print(rk.padh(x))\n"
                      "rk.visarjan(a)\n"),
    "RK06": HEADER + ("let a = rk.swatva(1)\n"
                      "print(rk.padh(rk.udhaar(a)))\n"
                      "rk.visarjan(a)\n"),
    "RK07": HEADER + ("let a = rk.swatva(1)\n"
                      "rk.visarjan(a)\n"),
    "RK08": HEADER + ("fn f() {\n"
                      "    let a = rk.swatva(1)\n"
                      "    let x = rk.udhaar(a)\n"
                      "    let v = rk.padh(x)\n"
                      "    rk.visarjan(a)\n"
                      "    return v\n"
                      "}\n"),
    "RK09": HEADER + ("let a = rk.swatva(1)\n"
                      "rk.visarjan(a)\n"),
    "RK10": HEADER + ("let r = rk.parinam_or(Ok(1), 0)\n"
                      "print(r)\n"),
    "RK11": HEADER + ("let o = rk.vikalp_or(some(1), 0)\n"
                      "print(o)\n"),
    "RK12": HEADER + ("let p = rk.swatva(1)\n"
                      "rk.visarjan(p)\n"),
    "RK13": HEADER + "let t = spawn { print(1) }\n",
    "RK14": HEADER + ("with rk.swatva(1) as a, rk.swatva(2) as b {\n"
                      "    print(1)\n"
                      "}\n"),
}

# §2.4: the seven runtime refusals, each with its mandatory message prefix.
REFUSALS = [
    ("moved_value",
     "let a = rk.swatva(1)\nlet b = rk.sanchay(a)\nrk.udhaar(a)\n",
     "RAKSHA: moved value"),
    ("dropped_value",
     "let a = rk.swatva(1)\nrk.visarjan(a)\nrk.udhaar(a)\n",
     "RAKSHA: dropped value"),
    ("loan_conflict",
     "let a = rk.swatva(1)\nlet x = rk.adhikar(a)\nrk.udhaar(a)\n",
     "RAKSHA: loan conflict"),
    ("shared_read_only",
     "let a = rk.swatva(1)\nlet x = rk.udhaar(a)\nrk.likh(x, 2)\n",
     "RAKSHA: shared loan is read-only"),
    ("owner_is_loaned",
     "let a = rk.swatva(1)\nlet x = rk.udhaar(a)\nrk.visarjan(a)\n",
     "RAKSHA: owner is loaned"),
    ("double_release",
     "let a = rk.swatva(1)\nrk.visarjan(a)\nrk.visarjan(a)\n",
     "RAKSHA: double release"),
    ("cell_conflict",
     'let c = rk.kosh(1)\nc["active"] = -1\nrk.kosh_padh(c)\n',
     "RAKSHA: cell conflict"),
]


# ---------------------------------------------------------------------------
# §5.1–§5.4 — the runtime library, `with` cleanup and reverse drop order
# ---------------------------------------------------------------------------

def test_import_and_audit_agree_on_three_engines(capsys):
    source = HEADER + ("print(rk.padh(rk.udhaar(rk.swatva(7))))\n"
                       "print(rk.audit()[\"verdict\"])\n")
    out = parity(source, capsys)
    assert out.startswith("7\n")
    assert "RAKSHA_LEDGER_CERTIFIED" in out


def test_with_releases_the_owner_on_the_normal_path(capsys):
    source = HEADER + (
        "var kept = null\n"
        "with rk.swatva(7) as a {\n"
        "    kept = a\n"
        "    print(rk.padh(rk.udhaar(a)))\n"
        "}\n"
        "try {\n"
        "    print(rk.padh(rk.udhaar(kept)))\n"
        '    print("UNEXPECTED_OK")\n'
        "} catch e { print(e) }\n")
    out = parity(source, capsys)
    assert out.startswith("7\n")
    assert "RAKSHA: dropped value" in out
    assert "UNEXPECTED_OK" not in out


def test_with_releases_the_owner_on_the_exception_path(capsys):
    source = HEADER + (
        "var kept = null\n"
        "try {\n"
        "    with rk.swatva(7) as a {\n"
        "        kept = a\n"
        '        throw "boom"\n'
        "    }\n"
        "} catch e { print(\"caught \" + e) }\n"
        "try {\n"
        "    print(rk.padh(rk.udhaar(kept)))\n"
        '    print("UNEXPECTED_OK")\n'
        "} catch e { print(e) }\n")
    out = parity(source, capsys)
    assert "caught boom" in out
    assert "RAKSHA: dropped value" in out
    assert "UNEXPECTED_OK" not in out


def test_with_exit_receives_the_error_text(capsys):
    # A tracing wrapper delegates to the owner's own __exit__, so both the
    # err argument and the library's automatic visarjan are observable.
    source = HEADER + (
        "var trace = []\n"
        "fn traced(owner) {\n"
        '    let exit_fn = owner["__exit__"]\n'
        "    return {\n"
        '        "__enter__": fn() { return owner },\n'
        '        "__exit__": fn(err) {\n'
        '            trace.push("err=" + str(err))\n'
        "            return exit_fn(err)\n"
        "        }\n"
        "    }\n"
        "}\n"
        "with traced(rk.swatva(7)) as a { print(1) }\n"
        "try {\n"
        "    with traced(rk.swatva(8)) as b { throw \"boom\" }\n"
        "} catch e { print(\"caught \" + e) }\n"
        "print(trace.join(\",\"))\n")
    out = parity(source, capsys)
    assert "err=null" in out
    assert "err=boom" in out
    assert "caught boom" in out


def test_nested_with_releases_in_reverse_declaration_order(capsys):
    source = HEADER + (
        "var trace = []\n"
        "fn traced(owner, label) {\n"
        '    let exit_fn = owner["__exit__"]\n'
        "    return {\n"
        '        "__enter__": fn() { return owner },\n'
        '        "__exit__": fn(err) {\n'
        '            trace.push("exit " + label)\n'
        "            return exit_fn(err)\n"
        "        }\n"
        "    }\n"
        "}\n"
        'with traced(rk.swatva(1), "a") as x {\n'
        '    with traced(rk.swatva(2), "b") as y { print("body") }\n'
        "}\n"
        "print(trace.join(\",\"))\n")
    out = parity(source, capsys)
    assert out.startswith("body\n")
    assert out.rstrip().endswith("exit b,exit a")


@pytest.mark.parametrize("name,body,prefix", REFUSALS,
                         ids=[item[0] for item in REFUSALS])
def test_runtime_refusal_prefix(name, body, prefix, capsys):
    source = HEADER + (
        "fn show(f) {\n"
        "    try { f(); print(\"NO_ERROR\") } catch e { print(e) }\n"
        "}\n"
        "show(fn() {\n" + body + "})\n")
    out = parity(source, capsys)
    assert "NO_ERROR" not in out
    assert prefix in out, out


def test_kosh_interior_mutability_and_runtime_conflict(capsys):
    source = HEADER + (
        "let c = rk.kosh(40)\n"
        "print(rk.kosh_padh(c))\n"
        "print(rk.kosh_likh(c, 41))\n"
        "print(rk.kosh_padh(c))\n"
        'c["borrows"].push({"kind": "adhikar", "id": 1})\n'
        "try { rk.kosh_likh(c, 42) } catch e { print(e) }\n"
        'c["borrows"] = []\n'
        "print(rk.kosh_padh(c))\n")
    out = parity(source, capsys)
    assert out.startswith("40\n41\n41\n")
    assert "RAKSHA: cell conflict" in out
    assert out.rstrip().endswith("41")


def test_parinam_and_vikalp_channels(capsys):
    source = HEADER + (
        "fn twice(x) { return x * 2 }\n"
        "print(rk.parinam_map(Ok(2), twice)[\"ok\"])\n"
        'print(rk.parinam_map(Err("bad"), twice)["err"])\n'
        "print(rk.parinam_chain(Ok(2), fn(x) { return Ok(x + 1) })[\"ok\"])\n"
        'print(rk.parinam_or(Err("bad"), 9))\n'
        'print(rk.vikalp_map(some(3), twice)["some"])\n'
        "print(rk.vikalp_or(none(), 9))\n")
    out = parity(source, capsys)
    assert out == "4\nbad\n3\n9\n6\n9\n"


@pytest.mark.parametrize("engine,tier", ENGINES4,
                         ids=["tree", "vm", "register", "register+tier"])
def test_audit_is_certified_on_every_engine(engine, tier):
    source = HEADER + "let RESULT = rk.audit()\n"
    env = run_source(source, filename="<test>.bun", check=True,
                     engine=engine, tier=tier)
    audit = plain(env.get("RESULT"))
    assert audit["ok"] is True
    assert audit["verdict"] == "RAKSHA_LEDGER_CERTIFIED"
    assert audit["passed"] == audit["total"] >= 12
    assert len(audit["checks"]) == audit["total"]
    assert all(check["ok"] for check in audit["checks"])


def test_niyam_and_codes_ledgers_are_complete():
    source = HEADER + ("let RULES = rk.niyam()\n"
                       "let CODES = rk.codes()\n"
                       "let SUMMARY = rk.summary()\n")
    env = run_source(source, filename="<test>.bun", check=True, engine="vm")
    rules = plain(env.get("RULES"))
    codes = plain(env.get("CODES"))
    summary = plain(env.get("SUMMARY"))
    assert len(rules) >= 12
    assert {rule["id"] for rule in rules} >= set(ALL_CODES)
    for rule in rules:
        assert rule["name"] and rule["text"] and rule["bun_rule"]
        assert "Rust" in rule["rust_seed"] or "原理借用" in rule["rust_seed"]
        assert ("语法未借用" in rule["rust_seed"]
                or "no Rust syntax" in rule["rust_seed"]
                or "syntax" in rule["rust_seed"].lower())
    assert {code["code"] for code in codes} == set(ALL_CODES)
    for code in codes:
        assert code["name"] and code["message"] and code["hint"]
    assert summary["verdict"] == "RAKSHA_LEDGER_CERTIFIED"
    assert summary["codes"] == len(codes)


def test_examples_english_and_hindi_are_byte_identical():
    assert os.path.exists(EXAMPLE) and os.path.exists(HINDI)
    english = cli(EXAMPLE)
    hindi = cli(HINDI)
    assert english.returncode == 0, english.stderr
    assert hindi.returncode == 0, hindi.stderr
    assert english.stdout == hindi.stdout
    assert english.stdout.rstrip().endswith("RAKSHA LEDGER CERTIFIED")


def test_example_output_is_deterministic():
    first = cli(EXAMPLE)
    second = cli(EXAMPLE)
    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout
    assert "RAKSHA_LEDGER_CERTIFIED" in first.stdout


def test_maturity_fixture_is_byte_identical_on_four_engines():
    assert os.path.exists(MATURITY)
    outputs = []
    for engine in ("tree", "vm", "register", "antar"):
        result = cli("--engine", engine, MATURITY)
        assert result.returncode == 0, result.stderr
        outputs.append(result.stdout)
    assert len(set(outputs)) == 1, outputs
    assert outputs[0]


# ---------------------------------------------------------------------------
# §5.10 — fourteen codes, each with a positive and a negative case
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("code", ALL_CODES)
def test_each_error_code_has_a_positive_case(code):
    result = analyze(BAD[code])
    found = {item.code for item in result.diagnostics}
    assert code in found, (code, sorted(found))
    for nidan in result.diagnostics:
        assert nidan.code in ALL_CODES
        assert nidan.primary is not None
        assert nidan.labels and nidan.hint and nidan.notes


@pytest.mark.parametrize("code", ALL_CODES)
def test_each_error_code_has_a_clean_negative_case(code):
    result = analyze(GOOD[code])
    assert result.diagnostics == [], [item.code for item in result.diagnostics]
    assert core().verify(result).ok


def test_nidan_carries_primary_labels_hint_notes_and_renders_them():
    result = analyze(BAD["RK03"])
    nidan = next(item for item in result.diagnostics if item.code == "RK03")
    payload = nidan.to_dict()
    for key in ("code", "name", "message", "primary", "labels", "hint",
                "notes"):
        assert key in payload
    assert payload["labels"] and payload["hint"] and payload["notes"]
    rendered = nidan.render(BAD["RK03"])
    assert "raksha[RK03]" in rendered
    assert "-->" in rendered
    assert "nidan" in rendered and ("sulabh" in rendered or
                                   payload["hint"] in rendered)


def test_codes_table_has_fourteen_entries():
    codes = core().CODES
    assert set(codes) == set(ALL_CODES)
    assert len(codes) == 14
    for code, entry in codes.items():
        assert entry["name"] and entry["message"] and entry["hint"], code


def test_rules_table_matches_the_codes_and_declares_no_syntax_borrowing():
    rules = core().RULES
    assert len(rules) >= 12
    assert {rule["id"] for rule in rules} >= set(ALL_CODES)
    for rule in rules:
        for key in ("id", "name", "text", "rust_seed", "bun_rule"):
            assert rule[key], (rule["id"], key)
        seed = rule["rust_seed"].lower()
        assert "rust" in seed or "原理" in seed
        assert "borrow" in seed or "借用" in rule["rust_seed"]
        assert "no rust syntax" in seed or "语法未借用" in rule["rust_seed"] \
            or "syntax" in seed


# ---------------------------------------------------------------------------
# §5.11 — verify() checks the analysis itself, not just the program
# ---------------------------------------------------------------------------

def test_verify_accepts_a_clean_program_and_reports_real_stats():
    result = analyze(CLEAN)
    check = core().verify(result)
    assert check.ok, check.problems
    assert check.problems == []
    stats = result.stats()
    for key in ("flows", "points", "edges", "owners", "loans", "drops",
                "diagnostics", "loops"):
        assert key in stats, key
        assert isinstance(stats[key], int) and stats[key] >= 0
    assert stats["flows"] >= 1 and stats["points"] > 0
    assert stats["owners"] >= 1 and stats["loans"] >= 1
    assert stats["drops"] >= 1 and stats["diagnostics"] == 0


def test_verify_rejects_an_unknown_nidan_code():
    result = analyze(CLEAN)
    fake = type(result.diagnostics[0])("RK99") if result.diagnostics else None
    if fake is None:
        from bun.raksha import Nidan
        fake = Nidan("RK99")
    result.diagnostics.append(fake)
    check = core().verify(result)
    assert not check.ok
    assert any("CODES" in problem or "hint" in problem or "label" in problem
               for problem in check.problems)


def test_verify_rejects_an_empty_kaal():
    result = analyze(GOOD["RK05"])
    loans = [loan for flow in result.all_flows() for loan in flow.loans]
    assert loans, "the clean program must really issue a loan"
    loans[0].region = set()
    check = core().verify(result)
    assert not check.ok
    assert any("kaal" in problem for problem in check.problems)


def test_verify_rejects_a_release_of_a_missing_owner():
    result = analyze(GOOD["RK07"])
    flow = next(iter(result.all_flows()))
    assert flow.drops, "the clean program must really release an owner"
    key, _ = flow.drops[0]
    flow.drops[0] = (key, 9999)
    check = core().verify(result)
    assert not check.ok
    assert any("release" in problem or "owner" in problem
               for problem in check.problems)


def test_stats_count_a_real_loop_and_a_real_function_flow():
    source = HEADER + (
        "fn total(n: int) -> int {\n"
        "    let sum = 0\n"
        "    for i in range(n) { sum += i }\n"
        "    return sum\n"
        "}\n"
        "print(total(4))\n")
    result = analyze(source)
    stats = result.stats()
    assert stats["flows"] >= 2
    assert stats["loops"] >= 1
    assert stats["points"] > stats["flows"]


def test_regions_are_sets_of_program_points():
    result = analyze(CLEAN)
    regions = result.regions()
    assert regions, "a shared loan must have a kaal"
    for loan_id, points in regions.items():
        assert isinstance(loan_id, int) or isinstance(loan_id, str)
        assert points
        for point in points:
            assert isinstance(point, str) and point.count(":") == 2
            assert all(part.isdigit() for part in point.split(":")[1:])


def test_render_json_contains_stats_regions_diagnostics_check_and_flows():
    payload = json.loads(core().render_json(analyze(CLEAN)))
    for key in ("stats", "regions", "diagnostics", "check", "flows",
                "verdict"):
        assert key in payload, key
    assert payload["stats"]["points"] > 0
    assert payload["check"]["ok"] is True
    assert payload["verdict"] == "RAKSHA_CLEAN"


def test_render_dot_is_a_digraph_with_edges():
    out = core().render_dot(analyze(CLEAN))
    assert out.startswith("digraph")
    assert "->" in out


def test_render_text_names_the_flow_and_its_points():
    out = core().render_text(analyze(CLEAN))
    assert out.startswith("RAKSHA")
    assert "pravah" in out and "bindu" in out
    assert "swatva" in out and "udhaar" in out


def test_render_explain_names_the_rules_and_the_self_check():
    out = core().render_explain(analyze(CLEAN), CLEAN)
    assert "niyam" in out
    assert "praman" in out
    assert "RK01" in out and "RK14" in out


def test_a_plain_program_without_the_import_analyses_empty_and_never_throws():
    source = ("fn fib(n: int) -> int {\n"
              "    if n < 2 { return n }\n"
              "    return fib(n - 1) + fib(n - 2)\n"
              "}\n"
              "print(fib(8))\n")
    result = analyze(source)
    assert result.diagnostics == []
    assert result.stats()["diagnostics"] == 0
    assert core().verify(result).ok


@pytest.mark.parametrize("body,name", [
    ("fn f() {\n    yield 1\n    return 1\n}\n", "yield"),
    ("fn f() {\n    struct P { x: int }\n    return 1\n}\n", "struct"),
    ("fn f() {\n    enum E { A }\n    return 1\n}\n", "enum"),
], ids=["yield", "struct", "enum"])
def test_unsupported_construct_is_refused_by_name(body, name):
    with pytest.raises(Unsupported) as failure:
        analyze(HEADER + body)
    message = str(failure.value)
    assert name in message
    assert "raksha" in message


# ---------------------------------------------------------------------------
# §5.12–§5.14 — command line, check --raksha, and the boundaries
# ---------------------------------------------------------------------------

def _write_program(tmp_path, name, source):
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return str(path)


def test_cli_verify_prints_the_counts(tmp_path):
    path = _write_program(tmp_path, "clean.bun", CLEAN)
    result = cli("raksha", path, "--verify")
    assert result.returncode == 0, result.stderr
    assert "RAKSHA: OK" in result.stdout
    for word in ("pravah", "bindu", "swatva", "udhaar", "visarjan", "nidan"):
        assert word in result.stdout


def test_cli_json_parses_and_reports_the_self_check(tmp_path):
    path = _write_program(tmp_path, "clean.bun", CLEAN)
    result = cli("raksha", path, "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["stats"]["points"] > 0
    assert payload["check"]["ok"] is True
    assert "regions" in payload and "diagnostics" in payload


def test_cli_dot_is_a_digraph(tmp_path):
    path = _write_program(tmp_path, "clean.bun", CLEAN)
    result = cli("raksha", path, "--dot")
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("digraph")
    assert "->" in result.stdout


def test_cli_stats_are_json_with_points_owners_and_loans(tmp_path):
    path = _write_program(tmp_path, "clean.bun", CLEAN)
    result = cli("raksha", path, "--stats")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    for key in ("points", "owners", "loans", "flows", "edges", "drops"):
        assert key in payload, key
    assert payload["points"] > 0 and payload["loans"] >= 1


def test_cli_explain_names_the_rule_ledger(tmp_path):
    path = _write_program(tmp_path, "clean.bun", CLEAN)
    result = cli("raksha", path, "--explain")
    assert result.returncode == 0, result.stderr
    assert "niyam" in result.stdout
    assert "praman" in result.stdout


def test_cli_without_a_flag_renders_text(tmp_path):
    path = _write_program(tmp_path, "clean.bun", CLEAN)
    result = cli("raksha", path)
    assert result.returncode == 0, result.stderr
    assert "RAKSHA" in result.stdout
    assert "pravah" in result.stdout


def test_cli_returns_nonzero_for_a_program_with_nidan(tmp_path):
    path = _write_program(tmp_path, "bad.bun", BAD["RK09"])
    result = cli("raksha", path, "--verify")
    assert result.returncode != 0
    assert "RAKSHA:" in result.stdout
    assert "RK09" in result.stdout


def test_check_raksha_rejects_a_program_with_nidan(tmp_path):
    path = _write_program(tmp_path, "bad.bun", BAD["RK01"])
    result = cli("check", "--raksha", path)
    assert result.returncode != 0
    assert "RK01" in result.stdout + result.stderr


def test_check_raksha_json_names_the_code(tmp_path):
    path = _write_program(tmp_path, "bad.bun", BAD["RK01"])
    result = cli("check", "--raksha", "--json", path)
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert any(item["code"].startswith("RK") and item["kind"] == "raksha"
               for item in payload["diagnostics"])


def test_check_raksha_accepts_a_clean_program(tmp_path):
    path = _write_program(tmp_path, "clean.bun", CLEAN)
    result = cli("check", "--raksha", "--json", path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"] is True


def test_default_check_behaviour_is_unchanged(tmp_path):
    path = _write_program(tmp_path, "type_error.bun",
                          'let x: int = "s"\n')
    result = cli("check", "--json", path)
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["diagnostics"][0]["kind"] == "type"
    assert "code" not in payload["diagnostics"][0]


def test_no_check_flag_does_not_break_the_example():
    result = cli("--no-check", EXAMPLE)
    assert result.returncode == 0, result.stderr
    assert result.stdout.rstrip().endswith("RAKSHA LEDGER CERTIFIED")


def test_antar_refuses_with_but_raksha_does_not(tmp_path):
    source = ("fn ctx(label) {\n"
              "    return {\"__enter__\": fn() { return label },\n"
              '            "__exit__": fn(err) { return false }}\n'
              "}\n"
              'with ctx("a") as x { print(x) }\n')
    path = _write_program(tmp_path, "with_only.bun", source)
    antar = cli("antar", path, "--stats")
    assert antar.returncode != 0
    assert "antar" in antar.stderr
    assert "WithStmt" in antar.stderr
    raksha = cli("raksha", path, "--verify")
    assert raksha.returncode == 0, raksha.stderr
    assert "RAKSHA: OK" in raksha.stdout


def test_usage_and_version_announce_the_wave():
    help_result = cli("-h")
    assert help_result.returncode == 0
    assert "bun raksha" in help_result.stdout
    version = cli("version", "--short")
    assert version.returncode == 0
    assert version.stdout.strip() == "0.7.0"


# ---------------------------------------------------------------------------
# §6b — anumati: a named, one-line, auditable exception (not a syntax borrow)
# ---------------------------------------------------------------------------

ANUMATI_CLEAN = (
    'import "bun:raksha" as rk\n'
    'let a = rk.swatva(1)\n'
    'let b = rk.sanchay(a)\n'
    '// raksha:allow RK01: the demo deliberately calls a moved owner\n'
    'rk.udhaar(a)\n'
    'rk.visarjan(b)\n')


def test_anumati_suppresses_only_the_named_code_on_the_next_line():
    result = analyze(ANUMATI_CLEAN)
    assert result.diagnostics == [], [d.code for d in result.diagnostics]
    assert result.allowed and all(d.code == "RK01" for d in result.allowed)
    assert len(result.allowances) == 1
    assert result.allowances[0].code == "RK01"
    assert result.allowances[0].used == len(result.allowed)
    assert "deliberately" in result.allowances[0].reason
    assert core().verify(result).ok


def test_anumati_is_recorded_in_every_renderer():
    result = analyze(ANUMATI_CLEAN)
    payload = json.loads(core().render_json(result))
    assert len(payload["allowed"]) >= 1
    assert len(payload["allowances"]) == 1
    assert payload["allowances"][0]["used"] == len(payload["allowed"])
    assert payload["verdict"] == "RAKSHA_CLEAN"
    assert "anumati" in core().render_text(result)
    assert "anumati" in core().render_explain(result, ANUMATI_CLEAN)
    assert result.stats()["allowed"] >= 1
    assert result.stats()["allowances"] == 1


def test_anumati_does_not_suppress_a_different_code_or_line():
    source = ('import "bun:raksha" as rk\n'
              '// raksha:allow RK07: wrong code for this line\n'
              'let a = rk.swatva(1)\n'
              'let b = rk.sanchay(a)\n'
              'rk.udhaar(a)\n'
              'rk.visarjan(b)\n')
    result = analyze(source)
    assert result.diagnostics, "the nidan must remain visible"
    assert all(d.code != "RK07" for d in result.diagnostics)
    assert not core().verify(result).ok


def test_an_unused_anumati_is_refused_by_verify():
    source = ('import "bun:raksha" as rk\n'
              '// raksha:allow RK01: nothing bad happens on the next line\n'
              'let x = 1\n')
    result = analyze(source)
    assert result.diagnostics == []
    assert result.allowed == []
    check = core().verify(result)
    assert not check.ok
    assert any("suppressed nothing" in p for p in check.problems)
    payload = json.loads(core().render_json(result))
    assert payload["check"]["ok"] is False
    assert payload["check"]["problems"]


def test_an_unknown_anumati_code_is_refused_by_verify():
    source = ('import "bun:raksha" as rk\n'
              'let a = rk.swatva(1)\n'
              'let b = rk.sanchay(a)\n'
              '// raksha:allow RK99: no such code\n'
              'rk.udhaar(a)\n'
              'rk.visarjan(b)\n')
    result = analyze(source)
    check = core().verify(result)
    assert not check.ok
    assert any("not in CODES" in p for p in check.problems)


def test_example_declares_exactly_one_used_anumati(tmp_path):
    with open(EXAMPLE, "r", encoding="utf-8") as handle:
        source = handle.read()
    result = analyze(source)
    assert result.diagnostics == [], [d.code for d in result.diagnostics]
    assert len(result.allowances) == 1
    assert result.allowances[0].used >= 1
    assert core().verify(result).ok


def test_anumati_is_a_comment_not_a_keyword_or_attribute():
    with open(LIB, "r", encoding="utf-8") as handle:
        library = handle.read()
    with open(EXAMPLE, "r", encoding="utf-8") as handle:
        example = handle.read()
    assert "#[allow" not in library + example
    assert "// raksha:allow" in example
    # The library still exports the same functions: no new keyword needed.
    assert "export fn swatva" in library
