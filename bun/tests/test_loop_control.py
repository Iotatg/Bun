"""Tests for break/continue, + coercion, and runtime error frames."""

import pytest

from bun.cli import run_source
from bun.errors import BunRuntimeError, BunTypeError


def run_both(source, capsys):
    """Run the same source on both engines and assert identical output."""
    run_source(source, filename="<test>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<test>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    return vm_out


def test_break_exits_while_loop(capsys):
    out = run_both(
        "var i = 0\n"
        "while i < 10 {\n"
        "  i = i + 1\n"
        "  if i == 4 { break }\n"
        "}\n"
        "print(i)\n", capsys)
    assert out == "4\n"


def test_continue_skips_rest_of_body(capsys):
    out = run_both(
        "var i = 0\n"
        "var sum = 0\n"
        "while i < 5 {\n"
        "  i = i + 1\n"
        "  if i % 2 == 0 { continue }\n"
        "  sum = sum + i\n"
        "}\n"
        "print(sum)\n", capsys)
    assert out == "9\n"


def test_break_exits_for_loop(capsys):
    out = run_both(
        "var kept = []\n"
        "for x in [1, 2, 3, 4, 5] {\n"
        "  if x == 4 { break }\n"
        "  kept.push(x)\n"
        "}\n"
        "print(kept.len())\n", capsys)
    assert out == "3\n"


def test_continue_in_for_loop(capsys):
    out = run_both(
        "var kept = []\n"
        "for x in [1, 2, 3, 4] {\n"
        "  if x % 2 == 0 { continue }\n"
        "  kept.push(x)\n"
        "}\n"
        "print(kept.len())\n", capsys)
    assert out == "2\n"


def test_nested_break_only_exits_inner_loop(capsys):
    out = run_both(
        "var n = 0\n"
        "for a in [1, 2, 3] {\n"
        "  for b in [1, 2, 3] {\n"
        "    if b == 2 { break }\n"
        "    n = n + 1\n"
        "  }\n"
        "}\n"
        "print(n)\n", capsys)
    assert out == "3\n"


def test_break_inside_if_block_unwinds_scope(capsys):
    out = run_both(
        "var i = 0\n"
        "var seen = 0\n"
        "while i < 5 {\n"
        "  i = i + 1\n"
        "  if i == 2 {\n"
        "    let hidden = 99\n"
        "    break\n"
        "  }\n"
        "  seen = seen + 1\n"
        "}\n"
        "print(i)\n"
        "print(seen)\n", capsys)
    assert out == "2\n1\n"


def test_break_inside_try_block(capsys):
    out = run_both(
        "var i = 0\n"
        "var hits = 0\n"
        "while i < 5 {\n"
        "  i = i + 1\n"
        "  try {\n"
        "    if i == 3 { break }\n"
        "    hits = hits + 1\n"
        "  } catch {\n"
        "    hits = hits - 1\n"
        "  }\n"
        "}\n"
        "print(i)\n"
        "print(hits)\n", capsys)
    assert out == "3\n2\n"


def test_continue_inside_try_block(capsys):
    out = run_both(
        "var c = 0\n"
        "for x in [1, 2, 3, 4] {\n"
        "  try {\n"
        "    if x == 2 { continue }\n"
        "    c = c + 1\n"
        "  } catch {\n"
        "    c = c - 1\n"
        "  }\n"
        "}\n"
        "print(c)\n", capsys)
    assert out == "3\n"


def test_break_outside_loop_is_a_static_error(capsys):
    with pytest.raises(BunTypeError) as info:
        run_source("break", filename="<test>.bun", engine="vm")
    assert "outside of a loop" in str(info.value)


def test_continue_outside_loop_is_a_static_error(capsys):
    with pytest.raises(BunTypeError) as info:
        run_source("continue", filename="<test>.bun", engine="vm")
    assert "outside of a loop" in str(info.value)


def test_plus_concatenates_string_and_number(capsys):
    out = run_both('print("id=" + 42)\n', capsys)
    assert out == "id=42\n"


def test_plus_concatenates_number_and_string(capsys):
    out = run_both('print(42 + "id")\n', capsys)
    assert out == "42id\n"


def test_plus_concatenates_string_and_bool(capsys):
    out = run_both('print("v=" + true)\n', capsys)
    assert out == "v=true\n"


def test_plus_still_adds_two_numbers(capsys):
    out = run_both("print(1 + 2)\n", capsys)
    assert out == "3\n"


def test_plus_still_rejects_null_operands(capsys):
    with pytest.raises(BunRuntimeError) as info:
        run_source("print(null + null)", filename="<test>.bun", engine="vm")
    assert "unsupported operands" in str(info.value)


def test_runtime_error_in_imported_module_reports_module_file(tmp_path):
    write = tmp_path / "broken.bun"
    write.write_text("export let value = 1\nprint(missing_name)\n")
    main = tmp_path / "main.bun"
    main.write_text('import { value } from "./broken"\nprint(value)\n')
    with pytest.raises(BunRuntimeError) as info:
        run_source(main.read_text(), filename=str(main), engine="vm")
    assert info.value.filename == str(write)
    assert info.value.line == 2


def test_runtime_error_in_imported_function_reports_module_file(tmp_path):
    write = tmp_path / "broken.bun"
    write.write_text(
        "export fn boom() {\n"
        "  let parts = null\n"
        "  print(parts + 1)\n"
        "}\n")
    main = tmp_path / "main.bun"
    main.write_text(
        'import { boom } from "./broken"\n'
        "boom()\n")
    with pytest.raises(BunRuntimeError) as info:
        run_source(main.read_text(), filename=str(main), engine="vm")
    assert info.value.filename == str(write)
    assert "unsupported operands" in str(info.value)
