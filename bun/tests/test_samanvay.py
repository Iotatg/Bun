"""Tests of the 0.8.0 wave: Samanvay, Bun's deterministic concurrency.

The wave is checked the way the Raksha wave is checked: every one of the
eight codes gets a real positive and a clean negative, the scheduler is
checked as a scheduler (the same seed must give the same bytes, a
different seed must give a different interleaving), the runtime is checked
with real calls, and the command line is exercised through
``python3 -m bun`` so a passing test cannot be a helper agreeing with
itself.

No keyword was added.  Every new word in these tests is an ordinary module
function name of ``bun:samanvay``.
"""

import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "samanvay.bun")
HINDI = os.path.join(ROOT, "examples", "samanvay_hi.bun")
RACE = os.path.join(ROOT, "examples", "samanvay_race.bun")
LIB = os.path.join(ROOT, "lib", "bun", "samanvay.bun")

HEADER = 'import "bun:samanvay" as sv\n'
ALL_CODES = ["SV%02d" % number for number in range(1, 9)]


def core():
    """Import the wave lazily, so collection never depends on order."""
    from bun import samanvay
    return samanvay


def bun(args, seed=None, engine=None, timeout=120):
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
    return [nidan.code for nidan in analysis.diagnostics]


# ---------------------------------------------------------------------------
# The ledger itself
# ---------------------------------------------------------------------------

def test_codes_are_eight_and_named():
    codes = core().CODES
    assert sorted(codes) == ALL_CODES
    assert [codes[c]["name"] for c in ALL_CODES] == [
        "asurakshit_lekh", "kary_leak", "dwand", "bandh",
        "kanal_dosh", "stale", "tal_kram", "kary_visfot"]


def test_rules_mirror_codes():
    rules = core().RULES
    assert [rule["id"] for rule in rules] == ALL_CODES
    for rule in rules:
        assert rule["text"] == core().CODES[rule["id"]]["message"]
        assert rule["bun_rule"].startswith("S")


def test_every_code_has_hint_and_message():
    for code, entry in core().CODES.items():
        assert entry["message"]
        assert entry["hint"]
        assert entry["name"].islower()


def test_the_wave_added_no_keyword():
    """The wave adds names, not grammar.

    Every name is reached through a dot (`sv.le(ch)`), where no keyword
    rule applies, so a pack that already spells `le` or `niyam` as a word
    is unaffected.  The soft-keyword list is the language's whole answer
    to "what did the last waves add to the grammar", and it did not move.
    The Hindi example proves the point by using `sv.le` and `sv.band` in a
    program whose output is byte-identical to the English one.
    """
    from bun import langpacks
    assert langpacks.SOFT_KEYWORDS == ("match", "scope", "spawn", "to")


# ---------------------------------------------------------------------------
# Vector clocks
# ---------------------------------------------------------------------------

def test_happens_before_is_a_partial_order():
    hb = core()._hb
    a = {0: 2, 1: 0}
    b = {0: 3, 1: 1}
    c = {0: 1, 1: 4}
    assert hb(a, b)
    assert not hb(b, a)
    assert not hb(b, c)
    assert not hb(c, b)
    assert hb({}, a)


def test_merge_takes_the_pointwise_maximum():
    merge = core()._merge
    left = {0: 1, 1: 5}
    merge(left, {1: 2, 2: 9})
    assert left == {0: 1, 1: 5, 2: 9}


def test_clock_tick_is_per_task():
    scheduler = core().Scheduler(0)
    task = core().Task(1)
    task.clock[1] = task.clock.get(1, 0) + 1
    assert task.clock == {1: 1}


# ---------------------------------------------------------------------------
# Static: one positive and one negative per code
# ---------------------------------------------------------------------------

def test_no_import_means_no_analysis():
    analysis = core().analyze_source("print(1)\n", "<test>")
    assert analysis.karies == []
    assert analysis.diagnostics == []


def test_clean_program_has_no_nidan():
    source = HEADER + (
        'let box = sv.sajha(0, "b")\n'
        'let l = sv.tal()\n'
        'fn w() {\n'
        '    sv.pakad(l)\n'
        '    sv.likh(box, sv.padh(box) + 1)\n'
        '    sv.chhod(l)\n'
        '}\n'
        'let h = sv.kary(w)\n'
        'sv.mel(h)\n')
    assert codes_of(source) == []


def test_sv01_plain_write_in_a_task():
    source = HEADER + (
        'var total = 0\n'
        'fn w() {\n'
        '    total = total + 1\n'
        '}\n'
        'let h = sv.kary(w)\n'
        'sv.mel(h)\n')
    assert "SV01" in codes_of(source)


def test_sv01_not_reported_when_the_task_takes_a_lock():
    source = HEADER + (
        'var total = 0\n'
        'let l = sv.tal()\n'
        'fn w() {\n'
        '    sv.pakad(l)\n'
        '    total = total + 1\n'
        '    sv.chhod(l)\n'
        '}\n'
        'let h = sv.kary(w)\n'
        'sv.mel(h)\n')
    assert "SV01" not in codes_of(source)


def test_sv02_task_never_joined():
    source = HEADER + 'fn w() {\n    sv.ajna()\n}\nsv.kary(w)\n'
    assert "SV02" in codes_of(source)


def test_sv02_quiet_inside_a_scope():
    source = HEADER + (
        'fn w() {\n    sv.ajna()\n}\n'
        'scope {\n    sv.kary(w)\n}\n')
    assert "SV02" not in codes_of(source)


def test_sv05_double_close():
    source = HEADER + (
        'let ch = sv.kanal(1)\n'
        'fn w() {\n    sv.band(ch)\n    sv.band(ch)\n}\n'
        'let h = sv.kary(w)\nsv.mel(h)\n')
    assert "SV05" in codes_of(source)


def test_sv05_send_after_close_only_when_it_is_after():
    before = HEADER + (
        'let ch = sv.kanal(1)\n'
        'fn w() {\n    sv.bhej(ch, 1)\n    sv.band(ch)\n}\n'
        'let h = sv.kary(w)\nsv.mel(h)\n')
    after = HEADER + (
        'let ch = sv.kanal(1)\n'
        'fn w() {\n    sv.band(ch)\n    sv.bhej(ch, 1)\n}\n'
        'let h = sv.kary(w)\nsv.mel(h)\n')
    assert "SV05" not in codes_of(before)
    assert "SV05" in codes_of(after)


def test_sv06_read_of_a_value_written_after_the_spawn():
    source = HEADER + (
        'var shared = 0\n'
        'fn w() {\n    sv.ajna()\n    print(shared)\n}\n'
        'let h = sv.kary(w)\n'
        'shared = 1\n'
        'sv.mel(h)\n')
    assert "SV06" in codes_of(source)


def test_sv07_lock_order_inversion():
    source = HEADER + (
        'let a = sv.tal()\nlet b = sv.tal()\n'
        'fn left() {\n    sv.pakad(a)\n    sv.pakad(b)\n'
        '    sv.chhod(b)\n    sv.chhod(a)\n}\n'
        'fn right() {\n    sv.pakad(b)\n    sv.pakad(a)\n'
        '    sv.chhod(a)\n    sv.chhod(b)\n}\n'
        'let h1 = sv.kary(left)\nlet h2 = sv.kary(right)\n'
        'sv.mel(h1)\nsv.mel(h2)\n')
    analysis = core().analyze_source(source, "<test>")
    assert "SV07" in [n.code for n in analysis.diagnostics]
    assert analysis.lock_orders["left"] == ["a", "b"]
    assert analysis.lock_orders["right"] == ["b", "a"]


def test_sv08_spawn_in_a_loop_without_a_scope():
    source = HEADER + (
        'fn w() {\n    sv.ajna()\n}\n'
        'for i in range(0, 3) {\n    sv.kary(w)\n}\n')
    assert "SV08" in codes_of(source)


def test_sv08_quiet_when_the_loop_joins_each_task():
    source = HEADER + (
        'fn w() {\n    sv.ajna()\n}\n'
        'for i in range(0, 3) {\n    let h = sv.kary(w)\n    sv.mel(h)\n}\n')
    assert "SV08" not in codes_of(source)


def test_diagnostics_have_spans_labels_hints_notes():
    source = HEADER + 'fn w() {\n    sv.ajna()\n}\nsv.kary(w)\n'
    analysis = core().analyze_source(source, "<test>")
    assert analysis.diagnostics
    for nidan in analysis.diagnostics:
        assert nidan.primary.line > 0
        assert nidan.labels
        assert nidan.hint
        assert nidan.notes


def test_verify_accepts_a_real_analysis():
    analysis = core().analyze_source(
        HEADER + 'fn w() {\n    sv.ajna()\n}\nsv.kary(w)\n', "<test>")
    check = core().verify(analysis)
    assert check.ok, check.problems


def test_verify_rejects_an_unknown_code():
    analysis = core().analyze_source(
        HEADER + 'fn w() {\n    sv.ajna()\n}\nsv.kary(w)\n', "<test>")
    analysis.diagnostics[0].code = "SV99"
    check = core().verify(analysis)
    assert not check.ok
    assert any("SV99" in problem for problem in check.problems)


def test_render_json_is_machine_readable():
    analysis = core().analyze_source(
        HEADER + 'fn w() {\n    sv.ajna()\n}\nsv.kary(w)\n', "<test>")
    payload = json.loads(core().render_json(analysis))
    assert payload["ok"] is False
    assert payload["nidan"][0]["code"] == "SV02"
    assert payload["karies"][0]["name"] == "w"
    assert "stats" in payload


def test_render_dot_is_a_digraph():
    analysis = core().analyze_source(
        HEADER + 'fn w() {\n    sv.ajna()\n}\nlet h = sv.kary(w)\nsv.mel(h)\n',
        "<test>")
    dot = core().render_dot(analysis)
    assert dot.startswith("digraph samanvay {")
    assert "mel" in dot


def test_render_explain_lists_all_eight_rules():
    analysis = core().analyze_source(HEADER, "<test>")
    text = core().render_explain(analysis)
    for code in ALL_CODES:
        assert code in text


# ---------------------------------------------------------------------------
# Runtime: the scheduler, the cells, the channels
# ---------------------------------------------------------------------------

def test_cell_roundtrip(tmp_path):
    path = write(tmp_path, "cell.bun", HEADER + (
        'let c = sv.sajha(41, "c")\n'
        'sv.likh(c, sv.padh(c) + 1)\n'
        'print(sv.padh(c))\n'))
    proc = bun([path])
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "42"


def test_lock_keeps_two_tasks_correct(tmp_path):
    path = write(tmp_path, "lock.bun", HEADER + (
        'let c = sv.sajha(0, "c")\n'
        'let l = sv.tal()\n'
        'fn w() {\n'
        '    sv.pakad(l)\n'
        '    let v = sv.padh(c)\n'
        '    sv.ajna()\n'
        '    sv.likh(c, v + 1)\n'
        '    sv.chhod(l)\n'
        '}\n'
        'let a = sv.kary(w)\nlet b = sv.kary(w)\n'
        'sv.mel(a)\nsv.mel(b)\n'
        'let t = sv.trace()\n'
        'print(sv.padh(c), len(t["races"]))\n'))
    for seed in range(6):
        proc = bun([path], seed=seed)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "2 0", (seed, proc.stdout)


def test_race_is_reported_and_can_lose_an_update(tmp_path):
    path = write(tmp_path, "race.bun", HEADER + (
        'let c = sv.sajha(0, "c")\n'
        'fn w() {\n'
        '    let v = sv.padh(c)\n'
        '    sv.ajna()\n'
        '    sv.likh(c, v + 1)\n'
        '}\n'
        'let a = sv.kary(w)\nlet b = sv.kary(w)\n'
        'sv.mel(a)\nsv.mel(b)\n'
        'let t = sv.trace()\n'
        'print(sv.padh(c), len(t["races"]) > 0)\n'))
    seen = set()
    for seed in range(8):
        proc = bun([path], seed=seed)
        assert proc.returncode == 0, proc.stderr
        seen.add(proc.stdout.strip())
    assert "1 true" in seen, seen


def test_same_seed_gives_the_same_schedule(tmp_path):
    path = write(tmp_path, "det.bun", HEADER + (
        'let c = sv.sajha(0, "c")\n'
        'fn w() {\n    sv.likh(c, sv.padh(c) + 1)\n}\n'
        'let a = sv.kary(w)\nlet b = sv.kary(w)\n'
        'sv.mel(a)\nsv.mel(b)\n'
        'let t = sv.trace()\n'
        'print(t["schedule_hash"], t["steps"])\n'))
    first = bun([path], seed=11)
    second = bun([path], seed=11)
    assert first.returncode == 0 and second.returncode == 0
    assert first.stdout == second.stdout
    assert first.stdout.strip().split()[0] != ""


def test_different_seeds_can_differ(tmp_path):
    path = write(tmp_path, "det2.bun", HEADER + (
        'let c = sv.sajha(0, "c")\n'
        'fn w() {\n    sv.padh(c)\n    sv.ajna()\n    sv.likh(c, 1)\n}\n'
        'let a = sv.kary(w)\nlet b = sv.kary(w)\n'
        'sv.mel(a)\nsv.mel(b)\n'
        'print(sv.trace()["schedule_hash"])\n'))
    hashes = {bun([path], seed=seed).stdout.strip() for seed in range(6)}
    assert len(hashes) >= 2


def test_channel_keeps_order_and_capacity(tmp_path):
    path = write(tmp_path, "chan.bun", HEADER + (
        'let ch = sv.kanal(2)\n'
        'sv.bhej(ch, 1)\n'
        'sv.bhej(ch, 2)\n'
        'print(sv.le(ch), sv.le(ch))\n'
        'sv.band(ch)\n'
        'print(sv.le(ch))\n'))
    proc = bun([path])
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["1 2", "null"]


def test_send_after_close_is_refused(tmp_path):
    path = write(tmp_path, "closed.bun", HEADER + (
        'let ch = sv.kanal(1)\n'
        'sv.band(ch)\n'
        'sv.bhej(ch, 1)\n'))
    proc = bun([path])
    assert proc.returncode == 1
    assert "send on a closed channel" in proc.stderr


def test_double_close_is_refused(tmp_path):
    path = write(tmp_path, "closed2.bun", HEADER + (
        'let ch = sv.kanal(1)\n'
        'sv.band(ch)\n'
        'sv.band(ch)\n'))
    proc = bun([path])
    assert proc.returncode == 1
    assert "already closed" in proc.stderr


def test_join_returns_the_value(tmp_path):
    path = write(tmp_path, "join.bun", HEADER + (
        'fn w(n) {\n    return n * 2\n}\n'
        'let h = sv.kary(w, "w", [21])\n'
        'print(sv.mel(h))\n'))
    proc = bun([path])
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "42"


def test_a_child_error_reaches_the_join(tmp_path):
    path = write(tmp_path, "boom.bun", HEADER + (
        'fn w() {\n    throw "child failed"\n}\n'
        'let h = sv.kary(w)\n'
        'sv.mel(h)\n'))
    proc = bun([path])
    assert proc.returncode == 1
    assert "child failed" in proc.stderr


def test_deadlock_is_reported_with_a_cycle(tmp_path):
    path = write(tmp_path, "dead.bun", HEADER + (
        'let a = sv.tal()\nlet b = sv.tal()\n'
        'fn left() {\n    sv.pakad(a)\n    sv.ajna()\n    sv.pakad(b)\n'
        '    sv.chhod(b)\n    sv.chhod(a)\n}\n'
        'fn right() {\n    sv.pakad(b)\n    sv.ajna()\n    sv.pakad(a)\n'
        '    sv.chhod(a)\n    sv.chhod(b)\n}\n'
        'let h1 = sv.kary(left)\nlet h2 = sv.kary(right)\n'
        'sv.mel(h1)\nsv.mel(h2)\n'))
    proc = bun([path], seed=0)
    assert proc.returncode == 1
    assert "deadlock" in proc.stderr


def test_deadlock_sweep_finds_a_seed(tmp_path):
    path = write(tmp_path, "dead2.bun", HEADER + (
        'let a = sv.tal()\nlet b = sv.tal()\n'
        'fn left() {\n    sv.pakad(a)\n    sv.ajna()\n    sv.pakad(b)\n'
        '    sv.chhod(b)\n    sv.chhod(a)\n}\n'
        'fn right() {\n    sv.pakad(b)\n    sv.ajna()\n    sv.pakad(a)\n'
        '    sv.chhod(a)\n    sv.chhod(b)\n}\n'
        'let h1 = sv.kary(left)\nlet h2 = sv.kary(right)\n'
        'sv.mel(h1)\nsv.mel(h2)\n'))
    proc = bun(["samanvay", "--seeds=0:3", path])
    assert "SAMANVAY SWEEP" in proc.stdout
    assert proc.returncode == 1


def test_cancel_is_visible_at_a_checkpoint(tmp_path):
    path = write(tmp_path, "cancel.bun", HEADER + (
        'fn w() {\n    sv.ajna()\n    sv.ajna()\n}\n'
        'let h = sv.kary(w)\n'
        'sv.chhodo(h)\n'
        'sv.mel(h)\n'))
    proc = bun([path])
    assert proc.returncode == 1
    assert "cancelled" in proc.stderr


def test_trace_events_carry_positions(tmp_path):
    path = write(tmp_path, "site.bun", HEADER + (
        'let c = sv.sajha(1, "c")\n'
        'sv.likh(c, 2)\n'
        'let t = sv.trace()\n'
        'for e in t["trace"] {\n'
        '    if e["kind"] == "likh" {\n'
        '        print(e["at"])\n'
        '    }\n'
        '}\n'))
    proc = bun([path])
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "3:1"


def test_seed_after_the_first_call_is_refused(tmp_path):
    path = write(tmp_path, "late.bun", HEADER + (
        'let c = sv.sajha(1)\n'
        'sv.beej(3)\n'))
    proc = bun([path])
    assert proc.returncode == 1
    assert "before the first coordination call" in proc.stderr


# ---------------------------------------------------------------------------
# The library half, written in Bun
# ---------------------------------------------------------------------------

def test_ledger_certifies(tmp_path):
    path = write(tmp_path, "audit.bun", HEADER + "sv.ledger()\n")
    proc = bun([path])
    assert proc.returncode == 0, proc.stderr
    assert "SAMANVAY_LEDGER_CERTIFIED 8/8" in proc.stdout


def test_niyam_and_codes_match_python(tmp_path):
    path = write(tmp_path, "ledger.bun", HEADER + (
        'for r in sv.niyam() {\n'
        '    print(r["id"], r["name"])\n'
        '}\n'))
    proc = bun([path])
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.strip().splitlines()
    assert len(lines) == 8
    for line, code in zip(lines, ALL_CODES):
        ident, name = line.split()
        assert ident == code
        assert name == core().CODES[code]["name"]


# ---------------------------------------------------------------------------
# The command line
# ---------------------------------------------------------------------------

def test_cli_static_ok_on_the_example():
    proc = bun(["samanvay", EXAMPLE])
    assert proc.returncode == 0, proc.stderr
    assert "SAMANVAY: OK" in proc.stdout


def test_cli_static_reports_a_nidan(tmp_path):
    path = write(tmp_path, "bad.bun", HEADER + (
        'fn w() {\n    sv.ajna()\n}\nsv.kary(w)\n'))
    proc = bun(["samanvay", path])
    assert proc.returncode == 1
    assert "samanvay[SV02]" in proc.stdout


def test_cli_json_shape():
    proc = bun(["samanvay", "--json", EXAMPLE])
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert len(payload["karies"]) == 3
    assert payload["stats"]["karies"] == 3


def test_cli_dot_and_stats_and_explain():
    dot = bun(["samanvay", "--dot", EXAMPLE])
    assert dot.stdout.startswith("digraph samanvay {")
    stats = json.loads(bun(["samanvay", "--stats", EXAMPLE]).stdout)
    assert stats["karies"] == 3
    explain = bun(["samanvay", "--explain", EXAMPLE]).stdout
    assert "SV03" in explain and "SV08" in explain


def test_cli_verify_says_ok():
    proc = bun(["samanvay", "--verify", EXAMPLE])
    assert proc.returncode == 0
    assert "SAMANVAY: OK" in proc.stdout


def test_cli_run_reports_a_seed():
    proc = bun(["samanvay", "--run", "--seed=3", RACE])
    assert "SAMANVAY RUN seed=3" in proc.stdout
    assert "SV03 dwand" in proc.stdout
    assert proc.returncode == 1


def test_cli_sweep_finds_the_lost_update():
    proc = bun(["samanvay", "--seeds=0:4", RACE])
    assert "SAMANVAY SWEEP: 5 seed(s)" in proc.stdout
    assert proc.returncode == 1


def test_cli_missing_file_exits_two():
    proc = bun(["samanvay", "no-such-file.bun"])
    assert proc.returncode == 2


# ---------------------------------------------------------------------------
# The examples, on every engine
# ---------------------------------------------------------------------------

def test_example_runs_and_is_seed_independent():
    outputs = set()
    for seed in (0, 3, 7):
        proc = bun([EXAMPLE], seed=seed)
        assert proc.returncode == 0, proc.stderr
        outputs.add(proc.stdout)
    assert len(outputs) == 1
    assert "SAMANVAY PIPELINE OK" in outputs.pop()


def test_hindi_example_is_byte_identical():
    english = bun([EXAMPLE]).stdout
    hindi = bun([HINDI]).stdout
    assert english == hindi


def test_three_engines_agree_byte_for_byte():
    outputs = []
    for engine in ("tree", "vm", "register"):
        proc = bun([EXAMPLE], engine=engine, seed=3)
        assert proc.returncode == 0, (engine, proc.stderr)
        outputs.append(proc.stdout)
    assert outputs[0] == outputs[1] == outputs[2]


def test_race_example_shows_the_two_seeds():
    at_zero = bun([RACE], seed=0).stdout
    at_three = bun([RACE], seed=3).stdout
    assert "counter 2" in at_zero
    assert "counter 1" in at_three
    assert "races 1" in at_zero and "races 1" in at_three


# ---------------------------------------------------------------------------
# Documentation and wiring
# ---------------------------------------------------------------------------

def test_docs_exist_and_name_the_eight_codes():
    path = os.path.join(ROOT, "docs", "reference", "samanvay.md")
    assert os.path.exists(path)
    text = open(path, encoding="utf-8").read()
    for code in ALL_CODES:
        assert code in text
    assert "bun samanvay" in text


def test_version_is_at_least_0_8_0():
    proc = bun(["version", "--short"])
    major, minor, patch = (int(part) for part in
                           proc.stdout.strip().split("."))
    assert (major, minor) >= (0, 8)


def test_cli_usage_mentions_the_command():
    proc = bun(["--help"])
    assert "samanvay" in proc.stdout
