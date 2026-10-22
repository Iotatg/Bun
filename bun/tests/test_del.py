"""The tests of the `del` statement.

`del name` removes a name from the scope that holds it, and
`del container[key]` removes an item from a dict or a list.
"""

import shutil

import pytest

from bun.cli import NativeExit, run_source
from bun.errors import BunError, format_error

ENGINES = ("tree", "vm", "register")


def _has_compiler():
    return shutil.which("cc") is not None


needs_compiler = pytest.mark.skipif(not _has_compiler(),
                                    reason="no C compiler")


def run_everywhere(source, capsys):
    """Run the same source on every engine and assert the same output."""
    outputs = []
    for engine in ENGINES:
        run_source(source, filename="<del>.bun", check=True, engine=engine)
        outputs.append(capsys.readouterr().out)
    assert len(set(outputs)) == 1, outputs
    return outputs[0]


def run_error(source, capsys, engine="vm"):
    with pytest.raises(BunError) as info:
        run_source(source, filename="<del>.bun", check=True, engine=engine)
    return info.value.msg


def _vm_failure(source, capfd, filename="<del>.bun"):
    """The failure of the machine, in the picture of the command line."""
    capfd.readouterr()
    try:
        run_source(source, filename=filename, check=False, engine="vm")
    except BunError as error:
        return format_error(error, source, filename) + "\n"
    return ""


def _c_failure(source, capfd, filename="<del>.bun"):
    """The failure of the backend, in the picture of the command line."""
    capfd.readouterr()
    try:
        run_source(source, filename=filename, check=False, engine="c")
    except NativeExit:
        pass
    return capfd.readouterr().err


def test_a_name_can_be_removed(capsys):
    out = run_everywhere(
        "var x = 1\n"
        "print(x)\n"
        "del x\n"
        "try {\n"
        "    print(x)\n"
        "} catch err {\n"
        "    print(\"gone: \" + err)\n"
        "}\n", capsys)
    assert out == "1\ngone: undefined variable 'x'\n"


def test_a_key_can_be_removed(capsys):
    out = run_everywhere(
        "let d = {\"a\": 1, \"b\": 2}\n"
        "del d[\"a\"]\n"
        "print(d.has(\"a\"))\n"
        "print(d.keys().join(\",\"))\n", capsys)
    assert out == "false\nb\n"


def test_an_item_can_be_removed(capsys):
    out = run_everywhere(
        "var lst = [1, 2, 3]\n"
        "del lst[1]\n"
        "print(lst.join(\",\"))\n", capsys)
    assert out == "1,3\n"


def test_a_removed_name_is_gone_from_the_scope_only(capsys):
    out = run_everywhere(
        "var x = 1\n"
        "fn f() {\n"
        "    var x = 2\n"
        "    del x\n"
        "    return 0\n"
        "}\n"
        "f()\n"
        "print(x)\n", capsys)
    assert out == "1\n"


def test_a_missing_key_is_an_error(capsys):
    message = run_error(
        "let d = {\"a\": 1}\n"
        "del d[\"missing\"]\n", capsys)
    assert message == "key not found"


def test_an_index_out_of_range_is_an_error(capsys):
    message = run_error(
        "var lst = [1, 2]\n"
        "del lst[9]\n", capsys)
    assert message == "list index 9 out of range"


def test_an_index_that_is_not_an_integer_is_an_error(capsys):
    message = run_error(
        "var lst = [1, 2]\n"
        "del lst[\"x\"]\n", capsys)
    assert message == "list index must be an integer"


def test_a_string_cannot_be_deleted_from(capsys):
    message = run_error(
        "var s = \"abc\"\n"
        "del s[0]\n", capsys)
    assert message == "can only delete from a list or a dict"


def test_a_name_that_does_not_exist_is_a_static_error(capsys):
    message = run_error("del nope\n", capsys)
    assert message == "undefined variable 'nope'"


def test_a_name_can_be_defined_again_after_it_was_removed(capsys):
    out = run_everywhere(
        "var x = 1\n"
        "del x\n"
        "var x = 2\n"
        "print(x)\n", capsys)
    assert out == "2\n"


@needs_compiler
def test_the_native_backend_runs_the_statement(capfd):
    source = (
        "var x = 1\n"
        "del x\n"
        "let d = {\"a\": 1}\n"
        "del d[\"a\"]\n"
        "var lst = [1, 2, 3]\n"
        "del lst[1]\n"
        "print(d.has(\"a\"))\n"
        "print(lst.join(\",\"))\n")
    capfd.readouterr()
    run_source(source, filename="<del>.bun", check=True, engine="vm")
    expected = capfd.readouterr().out
    run_source(source, filename="<del>.bun", check=True, engine="c")
    assert capfd.readouterr().out == expected
    assert expected == "false\n1,3\n"


@needs_compiler
def test_the_native_backend_fails_the_same_way(capfd):
    """The failure of the backend is the failure of the machine."""
    source = "let d = {\"a\": 1}\ndel d[\"missing\"]\n"
    expected = _vm_failure(source, capfd=capfd)
    got = _c_failure(source, capfd=capfd)
    assert expected != ""
    assert got == expected
