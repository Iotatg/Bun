"""Tests for the ``secret`` type and its redaction rules."""

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


def test_secret_is_redacted_when_printed(capsys):
    out = run_both('print(secret("hunter2"))\n', capsys)
    assert out == "***\n"


def test_str_of_a_secret_is_redacted(capsys):
    out = run_both('print(str(secret("hunter2")))\n', capsys)
    assert out == "***\n"


def test_dump_of_a_secret_is_redacted(capsys):
    out = run_both('print(dump(secret("hunter2")))\n', capsys)
    assert out == '"***"\n'


def test_type_of_a_secret(capsys):
    out = run_both('print(type_of(secret("x")))\n', capsys)
    assert out == "secret\n"


def test_reveal_returns_the_wrapped_value(capsys):
    out = run_both('print(secret("hunter2").reveal())\n', capsys)
    assert out == "hunter2\n"


def test_reveal_works_on_a_variable(capsys):
    out = run_both(
        'var token = secret(42)\nprint(token.reveal())\n', capsys)
    assert out == "42\n"


def test_secret_inside_a_dict_is_redacted(capsys):
    out = run_both(
        'print(dump({"key": secret("s3cr3t"), "name": "demo"}))\n', capsys)
    assert out == '{"key": "***", "name": "demo"}\n'


def test_secret_inside_a_list_is_redacted(capsys):
    out = run_both('print(dump([secret("s3cr3t"), 1]))\n', capsys)
    assert out == '["***", 1]\n'


def test_secret_in_an_f_string_is_redacted(capsys):
    out = run_both('var t = secret("s3cr3t")\nprint(f"value={t}")\n', capsys)
    assert out == "value=***\n"


def test_secret_in_an_error_message_is_redacted(capsys):
    out = run_both(
        'try {\n'
        '    throw secret("s3cr3t")\n'
        '} catch e {\n'
        '    print("caught " + e)\n'
        "}\n", capsys)
    assert out == "caught ***\n"


def test_secret_value_does_not_leak_into_a_runtime_error():
    with pytest.raises(BunRuntimeError) as info:
        run_source(
            'var t = secret("s3cr3t")\n'
            "print(t + 1)\n",
            filename="<test>.bun", check=True, engine="vm")
    assert "s3cr3t" not in info.value.msg


def test_reveal_is_the_only_way_out(capsys):
    out = run_both(
        'var t = secret("s3cr3t")\n'
        'print(t)\n'
        'print(t.reveal())\n', capsys)
    assert out == "***\ns3cr3t\n"


def test_secret_equality_compares_the_wrapped_value(capsys):
    out = run_both(
        'print(secret(1) == secret(1))\n'
        'print(secret(1) == secret(2))\n'
        'print(secret(1) == 1)\n', capsys)
    assert out == "true\nfalse\nfalse\n"


def test_reveal_on_a_plain_value_is_an_error():
    with pytest.raises(BunTypeError) as info:
        run_source('print("abc".reveal())\n', filename="<test>.bun",
                   check=True, engine="vm")
    assert "reveal" in info.value.msg


def test_secret_is_not_assignable_to_string():
    with pytest.raises(Exception) as info:
        run_source('var x: string = secret("a")\n', filename="<test>.bun",
                   check=True, engine="vm")
    assert "secret" in str(info.value)
