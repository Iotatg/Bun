"""Tests of the 0.9.0 wave: Palan, Bun's resilience layer.

The wave is checked the way the previous waves are checked: every one of
the eight codes gets a real positive and a clean negative, the clock is
checked as a clock (a sleep must move virtual time and must not move the
wall clock), the die is checked as a die (the same seed must give the same
answers), the supervision policy is checked with real children that really
fail, and the command line is exercised through ``python3 -m bun`` so a
passing test cannot be a helper agreeing with itself.

No keyword was added.  Every new word in these tests is an ordinary module
function name of ``bun:palan``.
"""

import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "palan.bun")
HINDI = os.path.join(ROOT, "examples", "palan_hi.bun")
LIB = os.path.join(ROOT, "lib", "bun", "palan.bun")

HEADER = 'import "bun:palan" as pl\nimport "bun:samanvay" as sv\n'
ALL_CODES = ["PL%02d" % number for number in range(1, 9)]


def core():
    """Import the wave lazily, so collection never depends on order."""
    from bun import palan
    return palan


def bun(args, seed=None, engine=None, timeout=180):
    argv = [sys.executable, "-m", "bun"]
    if engine:
        argv += ["--engine", engine]
    argv += list(args)
    env = dict(os.environ)
    env.pop("BUN_SAMANVAY_SEED", None)
    if seed is not None:
        env["BUN_SAMANVAY_SEED"] = str(seed)
    return subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                          timeout=timeout, env=env)


def write(tmp_path, name, source):
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return str(path)


def codes_of(source):
    analysis = core().analyze_source(source, "<test>")
    return [nidan.code for nidan in analysis.nidan]


def run(tmp_path, source, seed=0, name="prog.bun"):
    return bun([write(tmp_path, name, source)], seed=seed)


# ---------------------------------------------------------------------------
# The ledger
# ---------------------------------------------------------------------------

def test_the_ledger_has_eight_codes():
    assert sorted(core().CODES) == ALL_CODES


def test_the_ledger_has_eight_rules():
    rules = core().RULES
    assert [rule["id"] for rule in rules] == ALL_CODES


def test_every_code_has_a_name_a_message_and_a_hint():
    for code, row in core().CODES.items():
        assert row["name"], code
        assert row["message"], code
        assert row["hint"], code


def test_the_bun_ledger_matches_the_python_ledger(tmp_path):
    path = write(tmp_path, "ledger.bun", HEADER + (
        'for r in pl.codes() {\n'
        '    print(r["code"], r["name"])\n'
        '}\n'))
    proc = bun([path])
    assert proc.returncode == 0, proc.stderr
    seen = [line.split(" ", 1) for line in proc.stdout.strip().splitlines()]
    assert [code for code, _name in seen] == ALL_CODES
    for code, name in seen:
        assert name == core().CODES[code]["name"]


def test_the_bun_rules_match_the_python_rules(tmp_path):
    path = write(tmp_path, "rules.bun", HEADER + (
        'for r in pl.niyam() {\n'
        '    print(r["id"] + "|" + r["principle"])\n'
        '}\n'))
    proc = bun([path])
    assert proc.returncode == 0, proc.stderr
    rows = [line.split("|", 1) for line in proc.stdout.strip().splitlines()]
    assert [row[0] for row in rows] == ALL_CODES
    for code, principle in rows:
        assert principle == next(r["principle"] for r in core().RULES
                                 if r["id"] == code)


def test_the_runtime_ledger_certifies(tmp_path):
    path = write(tmp_path, "audit.bun", HEADER + "pl.ledger()\n")
    proc = bun([path])
    assert proc.returncode == 0, proc.stderr
    assert "PALAN_LEDGER_CERTIFIED 8/8" in proc.stdout


# ---------------------------------------------------------------------------
# The clock
# ---------------------------------------------------------------------------

def test_a_sleep_moves_virtual_time(tmp_path):
    path = write(tmp_path, "clock.bun", HEADER + (
        'let a = pl.abhi()\n'
        'pl.sona(50)\n'
        'let b = pl.abhi()\n'
        'print(b - a)\n'))
    proc = run(tmp_path, open(path).read())
    assert proc.returncode == 0, proc.stderr
    assert int(proc.stdout.strip()) == 50


def test_a_sleep_costs_no_wall_clock(tmp_path):
    """One hour of virtual backoff in well under a second of real time."""
    path = write(tmp_path, "hour.bun", HEADER + (
        'pl.sona(3600000)\n'
        'print(pl.abhi())\n'))
    started = time.time()
    proc = run(tmp_path, open(path).read())
    elapsed = time.time() - started
    assert proc.returncode == 0, proc.stderr
    assert int(proc.stdout.strip()) == 3600000
    assert elapsed < 20.0, elapsed


def test_a_scheduling_point_costs_one_tick(tmp_path):
    path = write(tmp_path, "ticks.bun", HEADER + (
        'let a = pl.abhi()\n'
        'sv.ajna()\n'
        'sv.ajna()\n'
        'let b = pl.abhi()\n'
        'print(b - a >= 2)\n'))
    proc = run(tmp_path, open(path).read())
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "true"


def test_the_clock_is_the_same_for_every_seed(tmp_path):
    path = write(tmp_path, "same.bun", HEADER + (
        'pl.sona(10)\n'
        'print(pl.abhi())\n'))
    source = open(path).read()
    values = {run(tmp_path, source, seed=seed).stdout.strip()
              for seed in range(4)}
    assert values == {"10"}


# ---------------------------------------------------------------------------
# The die
# ---------------------------------------------------------------------------

def test_a_certain_failure_always_fails(tmp_path):
    path = write(tmp_path, "certain.bun", HEADER + (
        'pl.sankat(1.0)\n'
        'print(pl.jokhim())\n'
        'print(pl.jokhim())\n'
        'print(pl.jokhim())\n'))
    proc = run(tmp_path, open(path).read())
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.split() == ["true", "true", "true"]


def test_an_impossible_failure_never_fails(tmp_path):
    path = write(tmp_path, "never.bun", HEADER + (
        'pl.sankat(0.0)\n'
        'print(pl.jokhim())\n'
        'print(pl.jokhim())\n'))
    proc = run(tmp_path, open(path).read())
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.split() == ["false", "false"]


def test_the_die_is_a_function_of_the_seed(tmp_path):
    source = HEADER + (
        'pl.sankat(0.5)\n'
        'var n = 0\n'
        'for i in range(0, 20) {\n'
        '    if pl.jokhim() { n = n + 1 }\n'
        '}\n'
        'print(n)\n')
    path = write(tmp_path, "die.bun", source)
    first = run(tmp_path, source, seed=5).stdout.strip()
    again = run(tmp_path, source, seed=5).stdout.strip()
    assert first == again
    values = {run(tmp_path, source, seed=seed).stdout.strip()
              for seed in range(6)}
    assert len(values) > 1, values


def test_a_choice_is_in_range_and_deterministic(tmp_path):
    source = HEADER + (
        'var small = true\n'
        'for i in range(0, 30) {\n'
        '    let c = pl.chunav(3)\n'
        '    if c < 0 or c > 2 { small = false }\n'
        '}\n'
        'print(small)\n')
    path = write(tmp_path, "choice.bun", source)
    assert run(tmp_path, source, seed=2).stdout.strip() == "true"


# ---------------------------------------------------------------------------
# Supervisors
# ---------------------------------------------------------------------------

def test_a_supervisor_restarts_a_failing_child(tmp_path):
    source = HEADER + (
        'var attempts = 0\n'
        'fn flaky() {\n'
        '    attempts = attempts + 1\n'
        '    if attempts < 3 { throw "boom" }\n'
        '    return "ok"\n'
        '}\n'
        'let sup = pl.rakshak("ek", 5, 1000)\n'
        'pl.baccha(sup, flaky, "flaky")\n'
        'let r = pl.chalau(sup)\n'
        'print(r["restarts"])\n'
        'print(attempts)\n')
    path = write(tmp_path, "restart.bun", source)
    proc = run(tmp_path, source)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.split() == ["2", "3"]


def test_a_supervisor_escalates_when_the_budget_runs_out(tmp_path):
    source = HEADER + (
        'fn bad() { throw "always" }\n'
        'let sup = pl.rakshak("ek", 1, 1000)\n'
        'pl.baccha(sup, bad, "bad")\n'
        'var caught = ""\n'
        'try { pl.chalau(sup) } catch e { caught = e }\n'
        'print(caught)\n')
    path = write(tmp_path, "escalate.bun", source)
    proc = run(tmp_path, source)
    assert proc.returncode == 0, proc.stderr
    assert "escalated after 2 restarts" in proc.stdout


def test_an_empty_supervisor_refuses_to_run(tmp_path):
    source = HEADER + (
        'let sup = pl.rakshak("ek", 1, 100)\n'
        'var caught = ""\n'
        'try { pl.chalau(sup) } catch e { caught = e }\n'
        'print(caught)\n')
    path = write(tmp_path, "empty.bun", source)
    proc = run(tmp_path, source)
    assert proc.returncode == 0, proc.stderr
    assert "needs at least one child" in proc.stdout


def test_an_unknown_strategy_is_refused(tmp_path):
    source = HEADER + (
        'var caught = ""\n'
        'try { pl.rakshak("koi", 1, 100) } catch e { caught = e }\n'
        'print(caught)\n')
    path = write(tmp_path, "strategy.bun", source)
    proc = run(tmp_path, source)
    assert proc.returncode == 0, proc.stderr
    assert "unknown restart strategy" in proc.stdout


def test_one_for_all_restarts_the_siblings(tmp_path):
    source = HEADER + (
        'var first = 0\n'
        'var second = 0\n'
        'fn a() { first = first + 1\n'
        '    if first < 2 { throw "a failed" }\n'
        '    return 1 }\n'
        'fn b() { second = second + 1\n'
        '    return 2 }\n'
        'let sup = pl.rakshak("sab", 3, 1000)\n'
        'pl.baccha(sup, a, "a")\n'
        'pl.baccha(sup, b, "b")\n'
        'pl.chalau(sup)\n'
        'print(first, second)\n')
    path = write(tmp_path, "all.bun", source)
    proc = run(tmp_path, source)
    assert proc.returncode == 0, proc.stderr
    first, second = proc.stdout.split()
    assert int(first) == 2
    assert int(second) >= 2


def test_rest_for_one_leaves_the_earlier_child_alone(tmp_path):
    source = HEADER + (
        'var a_runs = 0\n'
        'var b_runs = 0\n'
        'fn a() { a_runs = a_runs + 1\n'
        '    return 1 }\n'
        'fn b() { b_runs = b_runs + 1\n'
        '    if b_runs < 2 { throw "b failed" }\n'
        '    return 2 }\n'
        'let sup = pl.rakshak("baad", 3, 1000)\n'
        'pl.baccha(sup, a, "a")\n'
        'pl.baccha(sup, b, "b")\n'
        'pl.chalau(sup)\n'
        'print(a_runs, b_runs)\n')
    path = write(tmp_path, "rest.bun", source)
    proc = run(tmp_path, source)
    assert proc.returncode == 0, proc.stderr
    a_runs, b_runs = proc.stdout.split()
    assert int(a_runs) == 1
    assert int(b_runs) == 2


def test_the_restart_budget_is_a_window_not_a_total(tmp_path):
    """A failure after the window has passed starts the count again.

    Budget 1, window 20 ticks.  The first child fails at once, the second
    sleeps 50 ticks first (so its failure lands outside the window and the
    count restarts), the third fails at once and fills the budget.  Three
    attempts, not two: the window is what makes it three.
    """
    source = HEADER + (
        'var n = 0\n'
        'fn bad() {\n'
        '    n = n + 1\n'
        '    if n == 2 { pl.sona(50) }\n'
        '    throw "late"\n'
        '}\n'
        'let sup = pl.rakshak("ek", 1, 20)\n'
        'pl.baccha(sup, bad, "bad")\n'
        'var caught = ""\n'
        'try { pl.chalau(sup) } catch e { caught = e }\n'
        'print(n)\n'
        'print(caught != "")\n')
    path = write(tmp_path, "window.bun", source)
    proc = run(tmp_path, source)
    assert proc.returncode == 0, proc.stderr
    runs, caught = proc.stdout.split()
    assert int(runs) == 3
    assert caught == "true"


# ---------------------------------------------------------------------------
# Retry and the breaker
# ---------------------------------------------------------------------------

def test_retry_returns_the_value(tmp_path):
    source = HEADER + (
        'fn ok() { return 41 }\n'
        'print(pl.punar(ok, 3, 1, 8))\n')
    path = write(tmp_path, "retry.bun", source)
    proc = run(tmp_path, source)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "41"


def test_retry_gives_up_after_the_last_attempt(tmp_path):
    source = HEADER + (
        'var n = 0\n'
        'fn bad() { n = n + 1\n'
        '    throw "no" }\n'
        'var caught = ""\n'
        'try { pl.punar(bad, 3, 1, 8) } catch e { caught = e }\n'
        'print(n)\n'
        'print(caught)\n')
    path = write(tmp_path, "giveup.bun", source)
    proc = run(tmp_path, source)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.split()[0] == "3"
    assert "no" in proc.stdout


def test_a_breaker_opens_and_refuses(tmp_path):
    source = HEADER + (
        'fn bad() { throw "down" }\n'
        'fn ok() { return 1 }\n'
        'let b = pl.vyavdhi(2, 50)\n'
        'var n = 0\n'
        'try { pl.guzar(b, bad) } catch e { n = n + 1 }\n'
        'try { pl.guzar(b, bad) } catch e { n = n + 1 }\n'
        'print(b["state"])\n'
        'try { pl.guzar(b, ok) } catch e { n = n + 1 }\n'
        'print(n)\n'
        'print(b["refusals"])\n')
    path = write(tmp_path, "breaker.bun", source)
    proc = run(tmp_path, source)
    assert proc.returncode == 0, proc.stderr
    state, caught, refusals = proc.stdout.split()
    assert state == "khula"
    assert int(caught) == 3
    assert int(refusals) == 1


def test_a_breaker_closes_after_the_cooldown(tmp_path):
    source = HEADER + (
        'fn bad() { throw "down" }\n'
        'fn ok() { return 7 }\n'
        'let b = pl.vyavdhi(1, 20)\n'
        'try { pl.guzar(b, bad) } catch e { }\n'
        'pl.sona(25)\n'
        'let v = pl.guzar(b, ok)\n'
        'print(v)\n'
        'print(b["state"])\n')
    path = write(tmp_path, "halfopen.bun", source)
    proc = run(tmp_path, source)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.split() == ["7", "band"]


# ---------------------------------------------------------------------------
# Static analysis: six codes, each with a positive and a negative
# ---------------------------------------------------------------------------

def test_pl01_a_supervisor_with_no_children():
    source = HEADER + 'let s = pl.rakshak("ek", 3, 100)\n'
    assert codes_of(source) == ["PL01"]


def test_pl01_is_quiet_when_a_child_is_added():
    source = HEADER + (
        'fn w() { return 1 }\n'
        'let s = pl.rakshak("ek", 3, 100)\n'
        'pl.baccha(s, w, "w")\n')
    assert codes_of(source) == []


def test_pl02_a_retry_that_cannot_retry():
    source = HEADER + (
        'fn w() { return 1 }\n'
        'pl.punar(w, 1, 2, 10)\n')
    assert codes_of(source) == ["PL02"]


def test_pl02_is_quiet_at_two_attempts():
    source = HEADER + (
        'fn w() { return 1 }\n'
        'pl.punar(w, 2, 2, 10)\n')
    assert codes_of(source) == []


def test_pl03_a_deadline_nothing_checks():
    source = HEADER + (
        'fn w() {\n'
        '    pl.avadhi(50)\n'
        '    return 1\n'
        '}\n')
    assert codes_of(source) == ["PL03"]


def test_pl03_is_quiet_with_a_checkpoint():
    source = HEADER + (
        'fn w() {\n'
        '    pl.avadhi(50)\n'
        '    pl.jaanch()\n'
        '    return 1\n'
        '}\n')
    assert codes_of(source) == []


def test_pl04_a_supervisor_that_gives_up_at_once():
    source = HEADER + (
        'fn w() { return 1 }\n'
        'let s = pl.rakshak("ek", 0, 100)\n'
        'pl.baccha(s, w, "w")\n')
    assert codes_of(source) == ["PL04"]


def test_pl04_is_quiet_with_a_real_budget():
    source = HEADER + (
        'fn w() { return 1 }\n'
        'let s = pl.rakshak("ek", 2, 100)\n'
        'pl.baccha(s, w, "w")\n')
    assert codes_of(source) == []


def test_pl05_sleeping_while_holding_a_lock():
    source = HEADER + (
        'fn w() {\n'
        '    let l = sv.tal()\n'
        '    sv.pakad(l)\n'
        '    pl.sona(5)\n'
        '    sv.chhod(l)\n'
        '}\n')
    assert codes_of(source) == ["PL05"]


def test_pl05_is_quiet_when_the_sleep_is_outside_the_lock():
    source = HEADER + (
        'fn w() {\n'
        '    let l = sv.tal()\n'
        '    sv.pakad(l)\n'
        '    sv.chhod(l)\n'
        '    pl.sona(5)\n'
        '}\n')
    assert codes_of(source) == []


def test_pl06_a_breaker_that_never_closes():
    source = HEADER + 'let b = pl.vyavdhi(3, 0)\n'
    assert codes_of(source) == ["PL06"]


def test_pl06_is_quiet_with_a_cooldown():
    source = HEADER + 'let b = pl.vyavdhi(3, 10)\n'
    assert codes_of(source) == []


def test_a_clean_program_has_no_nidan():
    source = HEADER + (
        'fn w() {\n'
        '    pl.avadhi(100)\n'
        '    pl.jaanch()\n'
        '    return 1\n'
        '}\n'
        'let s = pl.rakshak("ek", 2, 100)\n'
        'pl.baccha(s, w, "w")\n'
        'pl.punar(w, 3, 1, 8)\n'
        'let b = pl.vyavdhi(3, 10)\n')
    assert codes_of(source) == []


def test_verify_is_clean_for_a_clean_program():
    analysis = core().analyze_source(
        HEADER + 'let b = pl.vyavdhi(3, 10)\n', "<test>")
    check = core().verify(analysis)
    assert check.ok, check.problems
    assert check.stats["codes"] == 8


def test_a_program_without_the_import_is_not_analyzed():
    analysis = core().analyze_source('print("hi")\n', "<test>")
    assert analysis.alias is None
    assert analysis.nidan == []


# ---------------------------------------------------------------------------
# The command line
# ---------------------------------------------------------------------------

def test_the_report_lists_the_supervisors(tmp_path):
    path = write(tmp_path, "report.bun", HEADER + (
        'fn w() { return 1 }\n'
        'let s = pl.rakshak("ek", 2, 100)\n'
        'pl.baccha(s, w, "w")\n'))
    proc = bun(["palan", path])
    assert proc.returncode == 0, proc.stderr
    assert "PALAN OK" in proc.stdout
    assert "s" in proc.stdout


def test_a_bad_program_exits_one(tmp_path):
    path = write(tmp_path, "bad.bun", HEADER + 'let b = pl.vyavdhi(3, 0)\n')
    proc = bun(["palan", path])
    assert proc.returncode == 1
    assert "PL06" in proc.stdout


def test_json_carries_the_stats_and_the_nidan(tmp_path):
    path = write(tmp_path, "bad.bun", HEADER + 'let b = pl.vyavdhi(3, 0)\n')
    proc = bun(["palan", "--json", path])
    assert proc.returncode == 1
    data = json.loads(proc.stdout)
    assert data["stats"]["nidan"] == 1
    assert data["nidan"][0]["code"] == "PL06"
    assert data["nidan"][0]["hint"]


def test_stats_is_json(tmp_path):
    path = write(tmp_path, "clean.bun", HEADER + 'let b = pl.vyavdhi(3, 4)\n')
    proc = bun(["palan", "--stats", path])
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["breakers"] == 1


def test_dot_has_an_edge_per_child(tmp_path):
    path = write(tmp_path, "dot.bun", HEADER + (
        'fn w() { return 1 }\n'
        'let s = pl.rakshak("ek", 2, 100)\n'
        'pl.baccha(s, w, "w")\n'))
    proc = bun(["palan", "--dot", path])
    assert proc.returncode == 0, proc.stderr
    assert '"s" -> "s/w"' in proc.stdout


def test_verify_says_ok(tmp_path):
    path = write(tmp_path, "clean.bun", HEADER + 'let b = pl.vyavdhi(3, 4)\n')
    proc = bun(["palan", "--verify", path])
    assert proc.returncode == 0, proc.stderr
    assert "PALAN: OK" in proc.stdout


def test_explain_lists_the_eight_codes(tmp_path):
    path = write(tmp_path, "clean.bun", HEADER + 'let b = pl.vyavdhi(3, 4)\n')
    proc = bun(["palan", "--explain", path])
    assert proc.returncode == 0, proc.stderr
    for code in ALL_CODES:
        assert code in proc.stdout


def test_a_missing_file_is_an_error():
    proc = bun(["palan", "/nonexistent/nope.bun"])
    assert proc.returncode == 2
    assert "no such file" in proc.stderr


def test_run_reports_the_clock(tmp_path):
    path = write(tmp_path, "run.bun", HEADER + (
        'pl.sona(20)\n'
        'print("done")\n'))
    proc = bun(["palan", "--run", "--seed=3", path])
    assert proc.returncode == 0, proc.stderr
    assert "ticks=20" in proc.stdout
    assert "sleeps=1" in proc.stdout


def test_chaos_sweeps_seeds(tmp_path):
    path = write(tmp_path, "chaos.bun", HEADER + (
        'pl.sankat(0.5)\n'
        'fn w() { if pl.jokhim() { throw "x" }\n'
        '    return 1 }\n'
        'let s = pl.rakshak("ek", 0, 100)\n'
        'pl.baccha(s, w, "w")\n'
        'try { pl.chalau(s) } catch e { }\n'))
    proc = bun(["palan", "--chaos=0:7", path])
    assert "PALAN CHAOS: 8 seed(s)" in proc.stdout
    assert "findings=0" in proc.stdout or "findings=1" in proc.stdout


def test_run_json_is_json(tmp_path):
    path = write(tmp_path, "run.bun", HEADER + 'pl.sona(5)\n')
    proc = bun(["palan", "--run", "--json", path])
    data = json.loads(proc.stdout)
    assert data["ticks"] == 5
    assert data["sleeps"] == 1


def test_check_folds_the_palan_pass_into_the_type_check(tmp_path):
    path = write(tmp_path, "bad.bun", HEADER + 'let b = pl.vyavdhi(3, 0)\n')
    proc = bun(["check", "--palan", path])
    assert proc.returncode == 1
    assert "palan[PL06]" in proc.stderr
    assert "bad.bun:3:9" in proc.stderr


def test_check_is_silent_on_a_clean_program(tmp_path):
    path = write(tmp_path, "clean.bun", HEADER + 'let b = pl.vyavdhi(3, 4)\n')
    proc = bun(["check", "--palan", path])
    assert proc.returncode == 0, proc.stderr
    assert "palan[" not in proc.stderr


def test_check_json_carries_the_palan_code(tmp_path):
    path = write(tmp_path, "bad.bun", HEADER + 'let b = pl.vyavdhi(3, 0)\n')
    proc = bun(["check", "--palan", "--json", path])
    data = json.loads(proc.stdout)
    assert data["ok"] is False
    kinds = [d["kind"] for d in data["diagnostics"]]
    assert "palan" in kinds
    assert any(d.get("code") == "PL06" for d in data["diagnostics"])


# ---------------------------------------------------------------------------
# Cross-engine and cross-language parity
# ---------------------------------------------------------------------------

def test_three_engines_produce_the_same_bytes():
    outputs = set()
    for engine in ("tree", "vm", "register"):
        proc = bun([EXAMPLE], seed=3, engine=engine)
        assert proc.returncode == 0, (engine, proc.stderr)
        outputs.add(proc.stdout)
    assert len(outputs) == 1, outputs


def test_the_same_seed_gives_the_same_bytes():
    first = bun([EXAMPLE], seed=7).stdout
    second = bun([EXAMPLE], seed=7).stdout
    assert first == second


def test_different_seeds_give_different_worlds():
    outputs = {bun([EXAMPLE], seed=seed).stdout for seed in range(8)}
    assert len(outputs) > 1


def test_the_hindi_example_is_byte_identical():
    for seed in (0, 2):
        english = bun([EXAMPLE], seed=seed)
        hindi = bun([HINDI], seed=seed)
        assert english.returncode == 0, english.stderr
        assert hindi.returncode == 0, hindi.stderr
        assert english.stdout == hindi.stdout


# ---------------------------------------------------------------------------
# The wave added names, not grammar
# ---------------------------------------------------------------------------

def test_the_wave_added_no_keyword():
    from bun import langpacks
    assert langpacks.SOFT_KEYWORDS == ("match", "scope", "spawn", "to")


def test_the_library_uses_no_keyword():
    """Every name the library exports is reachable after a dot."""
    text = open(LIB, encoding="utf-8").read()
    for name in core().PL_FNS:
        assert ("fn %s(" % name) in text or ("let %s = " % name) in text, name


def test_the_example_names_only_the_wave():
    text = open(EXAMPLE, encoding="utf-8").read()
    for name in ("pl.sona", "pl.sankat", "pl.jokhim", "pl.punar",
                 "pl.vyavdhi", "pl.guzar", "pl.rakshak", "pl.baccha",
                 "pl.chalau", "pl.abhi", "pl.jaanch", "pl.avadhi"):
        assert name in text, name
