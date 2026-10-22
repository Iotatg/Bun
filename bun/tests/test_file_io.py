import pytest

from bun.interpreter import Interpreter
from bun.parser import parse
from bun.errors import BunRuntimeError


def run(source, interp=None):
    interp = interp or Interpreter()
    interp.run(parse(source))
    return interp


def test_roundtrip(tmp_path):
    path = tmp_path / "f.txt"
    run('write_file("%s", "line1\\nline2\\n")' % path)
    interp = run('let text = read_file("%s")' % path)
    assert interp.globals.get("text") == "line1\nline2\n"


def test_append(tmp_path):
    path = tmp_path / "f.txt"
    run('write_file("%s", "a")' % path)
    run('append_file("%s", "b")' % path)
    interp = run('let text = read_file("%s")' % path)
    assert interp.globals.get("text") == "ab"


def test_file_exists(tmp_path):
    from bun.parser import parse_expression
    path = tmp_path / "f.txt"
    run('write_file("%s", "x")' % path)
    interp = Interpreter()
    assert interp.evaluate(
        parse_expression('file_exists("%s")' % path), interp.globals) is True
    assert interp.evaluate(
        parse_expression('file_exists("%s")' % (tmp_path / "nope.txt")),
        interp.globals) is False


def test_read_missing_errors(tmp_path):
    with pytest.raises(BunRuntimeError):
        run('read_file("%s")' % (tmp_path / "nope.txt"))


def test_arity_errors():
    with pytest.raises(BunRuntimeError):
        run('read_file("a", "b")')


def test_read_file_type_error():
    with pytest.raises(BunRuntimeError):
        run("read_file(1.5)")


def test_write_file_type_error(tmp_path):
    path = tmp_path / "f.txt"
    with pytest.raises(BunRuntimeError):
        run('write_file("%s", 42)' % path)


def test_file_exists_type_error():
    with pytest.raises(BunRuntimeError):
        run("file_exists(1)")


def test_write_then_string_ops(tmp_path):
    path = tmp_path / "f.txt"
    run('write_file("%s", " a , b ")' % path)
    interp = run('let text = read_file("%s")\nlet parts = text.trim().split(",")' % path)
    assert interp.globals.get("parts") == ["a ", " b"]
