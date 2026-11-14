"""Tests of the 0.6.0 wave: Antar, Bun's unified control-flow graph.

The graph is checked as a graph, not as a string: every khand has exactly
one nirnaya, every edge names a khand that exists, a loop is found from a
back edge, and a program that leaves the supported subset is refused by
name.  The engine is checked against the engines that came before it on
the same programs, because a seventh engine that disagrees is a seventh
language.
"""

import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout

import pytest

from bun import antar
from bun.antar import (CHUNAV, JA, LAUT, SAMAAPT, AntarMachine, Check,
                       Kriya, Khand, Nirnaya, Pravah, Sthan, lower_program,
                       verify)
from bun.cli import run_source
from bun.intcore import Unsupported
from bun.lexer import Lexer
from bun.parser import Parser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "tools", "maturity", "antar_core.bun")


def parse(source):
    return Parser(Lexer(source).tokenize()).parse()


def graph_of(source):
    return lower_program(parse(source), "<test>.bun")


def run_engine(source, engine):
    captured = io.StringIO()
    with redirect_stdout(captured):
        run_source(source, filename="<test>.bun", check=True, engine=engine)
    return captured.getvalue()


def parity(source, engines=("tree", "vm", "register", "antar")):
    outputs = [run_engine(source, engine) for engine in engines]
    assert len(set(outputs)) == 1, outputs
    return outputs[0]


PROGRAM = (
    "fn gcd(a: int, b: int) -> int {\n"
    "    while b != 0 {\n"
    "        let t = b\n"
    "        b = a % b\n"
    "        a = t\n"
    "    }\n"
    "    return a\n"
    "}\n"
    "var total = 0\n"
    "for i in range(1, 11) {\n"
    "    total = total + i * i\n"
    "}\n"
    "print(gcd(48, 18))\n"
    "print(total)\n"
)


# ---------------------------------------------------------------------------
# The shape of the graph
# ---------------------------------------------------------------------------

def test_every_khand_has_exactly_one_terminator():
    graph = graph_of(PROGRAM)
    for flow in graph.all_flows():
        for block in flow.blocks:
            assert block.nirnaya is not None
            assert block.nirnaya.kind in (JA, CHUNAV, LAUT, SAMAAPT)


def test_every_edge_names_a_khand_that_exists():
    graph = graph_of(PROGRAM)
    for flow in graph.all_flows():
        for block in flow.blocks:
            for target in block.successors():
                assert 0 <= target < len(flow.blocks)


def test_verify_accepts_the_graph_and_reports_its_size():
    check = verify(graph_of(PROGRAM))
    assert check.ok, check.problems
    assert check.stats["blocks"] > 0
    assert check.stats["edges"] >= check.stats["blocks"] - 1
    assert check.stats["dead"] == []


def test_an_if_ends_in_a_chunav_with_two_targets():
    graph = graph_of('if 1 < 2 { print("a") } else { print("b") }')
    chunav = [block.nirnaya for block in graph.main.blocks
              if block.nirnaya.kind == CHUNAV]
    assert len(chunav) == 1
    assert chunav[0].then != chunav[0].otherwise


def test_a_logical_condition_becomes_two_tests_not_one():
    plain = graph_of("if 1 < 2 { print(1) }")
    both = graph_of("if (1 < 2) and (3 > 2) { print(1) }")
    count = lambda graph: sum(1 for block in graph.main.blocks
                              if block.nirnaya.kind == CHUNAV)
    assert count(both) == count(plain) + 1


def test_a_while_has_a_back_edge_and_one_loop():
    graph = graph_of("var i = 0\nwhile i < 3 { i++ }\n")
    found = antar.loops(graph.main)
    assert len(found) == 1
    head = found[0]["head"]
    assert head in found[0]["body"]
    # The body of the loop reaches the head again.
    assert any(head in block.successors()
               for block in graph.main.blocks
               if block.index in found[0]["body"])


def test_the_head_of_a_loop_dominates_its_body():
    graph = graph_of("var i = 0\nwhile i < 3 { i++ }\n")
    found = antar.loops(graph.main)
    dom = antar.dominators(graph.main)
    head = found[0]["head"]
    for index in found[0]["body"]:
        assert head in dom[index]


def test_break_and_continue_name_the_loop_they_leave():
    graph = graph_of(
        "for i in range(5) as outer {\n"
        "    if i == 1 { continue outer }\n"
        "    if i == 3 { break outer }\n"
        "}\n")
    targets = [block.nirnaya for block in graph.main.blocks
               if block.nirnaya.kind == JA]
    exits = [block.index for block in graph.main.blocks
             if block.tag == "for-exit"]
    advances = [block.index for block in graph.main.blocks
                if block.tag == "for-advance"]
    assert any(n.then in exits for n in targets)
    assert any(n.then in advances for n in targets)


def test_a_for_over_a_list_is_refused_by_name():
    with pytest.raises(Unsupported) as failure:
        graph_of("for x in [1, 2] { print(x) }")
    assert "antar" in str(failure.value)
    assert "range" in str(failure.value)


def test_a_for_with_a_dynamic_step_is_refused_by_name():
    with pytest.raises(Unsupported) as failure:
        graph_of("let s = 2\nfor i in range(0, 9, s) { print(i) }")
    assert "step" in str(failure.value)


def test_a_negative_step_is_lowered_to_a_greater_than_test():
    graph = graph_of("for i in range(3, 0, -1) { print(i) }")
    tests = [block.nirnaya.expr for block in graph.main.blocks
             if block.nirnaya.kind == CHUNAV]
    assert any(getattr(node, "op", None) == ">" for node in tests)


def test_the_verifier_catches_a_target_that_does_not_exist():
    graph = graph_of("print(1)")
    graph.main.blocks[0].nirnaya = Nirnaya(JA, Sthan(1, 1), then=99)
    check = verify(graph)
    assert not check.ok
    assert any("missing khand" in problem for problem in check.problems)


def test_the_verifier_catches_a_khand_without_a_terminator():
    graph = graph_of("print(1)")
    graph.main.blocks.append(Khand(1, [], None, Sthan(1, 1), "orphan"))
    check = verify(graph)
    assert not check.ok
    assert any("no nirnaya" in problem for problem in check.problems)


def test_a_dead_join_after_two_returns_is_reported_not_fatal():
    graph = graph_of(
        "fn f(n: int) -> int {\n"
        "    if n > 0 { return 1 } else { return 2 }\n"
        "}\n"
        "print(f(1))\n")
    check = verify(graph)
    assert check.ok, check.problems
    assert check.stats["dead"], "the join khand must be reported as dead"


def test_a_position_packs_into_one_integer():
    position = Sthan(12, 34)
    assert position.packed == (12 << 12) | 34
    assert str(position) == "12:34"


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------

def test_the_fixture_runs_on_the_graph_and_on_the_older_engines():
    assert os.path.exists(FIXTURE)
    outputs = []
    for engine in ("tree", "vm", "register", "antar"):
        captured = io.StringIO()
        with redirect_stdout(captured):
            run_source(open(FIXTURE, encoding="utf-8").read(),
                       filename=FIXTURE, check=True, engine=engine)
        outputs.append(captured.getvalue())
    assert len(set(outputs)) == 1, outputs


def test_arithmetic_loops_and_functions_agree_across_engines():
    parity(PROGRAM)


def test_nested_conditions_agree_across_engines():
    parity(
        "fn classify(n: int) -> string {\n"
        "    if n < 0 { return \"neg\" }\n"
        "    else if n == 0 { return \"zero\" }\n"
        "    return \"pos\"\n"
        "}\n"
        "print(classify(-1))\n"
        "print(classify(0))\n"
        "print(classify(1))\n")


def test_labelled_loops_and_short_circuit_agree_across_engines():
    parity(
        "var hits = 0\n"
        "for i in range(10) as outer {\n"
        "    if i % 2 == 0 { continue outer }\n"
        "    if i > 7 { break outer }\n"
        "    hits += i\n"
        "}\n"
        "print(hits)\n"
        "print((1 < 2) and (3 > 2))\n"
        "print(1 and 0)\n"
        "print(2 or 3)\n")


def test_recursion_runs_as_a_stack_of_graphs():
    output = parity(
        "fn fib(n: int) -> int {\n"
        "    if n < 2 { return n }\n"
        "    return fib(n - 1) + fib(n - 2)\n"
        "}\n"
        "print(fib(10))\n")
    assert output == "55\n"


def test_a_function_value_is_callable_from_an_expression():
    output = parity(
        "fn twice(n: int) -> int { return n * 2 }\n"
        "print([twice(1), twice(2), twice(3)])\n")
    assert output == "[2, 4, 6]\n"


def test_an_assert_with_a_message_fails_like_the_tree_engine():
    with pytest.raises(Exception) as graph_failure:
        run_engine('assert 1 > 2, "impossible"\n', "antar")
    with pytest.raises(Exception) as tree_failure:
        run_engine('assert 1 > 2, "impossible"\n', "tree")
    assert str(graph_failure.value) == str(tree_failure.value)


def test_the_machine_runs_a_graph_built_by_hand():
    flow = Pravah("hand", [], [], 0, "<hand>")
    flow.blocks.append(Khand(0, [Kriya("emit", Sthan(1, 1),
                                       expr=parse("print(7)").statements[0].expr)],
                             Nirnaya(SAMAAPT, Sthan(1, 1)), Sthan(1, 1), "entry"))
    graph = antar.Antar(flows={}, main=flow, filename="<hand>")
    captured = io.StringIO()
    with redirect_stdout(captured):
        AntarMachine().run(graph)
    assert captured.getvalue() == "7\n"


# ---------------------------------------------------------------------------
# The command line
# ---------------------------------------------------------------------------

def cli(*args):
    return subprocess.run([sys.executable, "-m", "bun"] + list(args),
                          cwd=ROOT, capture_output=True, text=True,
                          timeout=120)


def test_the_cli_verifies_the_fixture():
    result = cli("antar", FIXTURE, "--verify")
    assert result.returncode == 0, result.stderr
    assert "ANTAR: OK" in result.stdout
    assert "pravah" in result.stdout


def test_the_cli_dumps_json_with_blocks_and_edges():
    result = cli("antar", FIXTURE, "--json")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["stats"]["blocks"] > 0
    assert data["flows"]
    for flow in data["flows"]:
        assert flow["blocks"]
        assert all("nirnaya" in block for block in flow["blocks"])
        assert flow["reverse_postorder"]


def test_the_cli_dumps_dot():
    result = cli("antar", FIXTURE, "--dot")
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("digraph antar")
    assert "->" in result.stdout


def test_the_cli_reports_stats():
    result = cli("antar", FIXTURE, "--stats")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["flows"] >= 1
    assert "loops" in data


def test_the_cli_runs_the_fixture_on_the_antar_engine():
    result = cli("--engine", "antar", FIXTURE)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "6\n55\nneg\nzero\npos\n27\ntrue"


def test_engines_lists_antar():
    result = cli("engines", "--json")
    assert result.returncode == 0, result.stderr
    names = {item["name"] for item in json.loads(result.stdout)["engines"]}
    assert "antar" in names


def test_an_unknown_engine_is_rejected_with_the_new_name_in_the_message():
    result = cli("--engine", "nope", FIXTURE)
    assert result.returncode == 2
    assert "antar" in result.stderr
