"""Tests for the 23 extra builtins (bun.extras)."""

import pytest

from bun.cli import run_source
from bun.errors import BunRuntimeError, BunTypeError


def run(source, capsys):
    run_source(source, filename="<extras>.bun", check=True)
    return capsys.readouterr().out.strip()


# ---------------------------------------------------------------------------
# regex
# ---------------------------------------------------------------------------

def test_regex_match(capsys):
    assert run('print(regex_match("^ab+c$", "abbbc"))', capsys) == "true"
    assert run('print(regex_match("^ab+c$", "xyz"))', capsys) == "false"


def test_regex_search_and_findall(capsys):
    assert run('print(regex_search("\\\\d+", "ab12cd"))', capsys) == "true"
    assert run('print(str(regex_findall("\\\\d+", "a1b22c333")))', capsys) \
        == '["1", "22", "333"]'


def test_regex_replace(capsys):
    assert run('print(regex_replace("\\\\d+", "a1b22", "#"))', capsys) \
        == "a#b#"


def test_regex_groups(capsys):
    assert run('print(str(regex_groups("(\\\\w+)@(\\\\w+)", '
               '"me@here")))', capsys) == '["me", "here"]'


# ---------------------------------------------------------------------------
# csv + html + text
# ---------------------------------------------------------------------------

def test_csv_roundtrip(capsys):
    assert run('print(str(csv_parse("a,b\\n1,2\\n")))', capsys) \
        == '[["a", "b"], ["1", "2"]]'
    assert run('print(csv_build([["a", "b"], ["1", "2"]]))', capsys) \
        == "a,b\n1,2"


def test_html_escape_roundtrip(capsys):
    assert run('print(html_escape("<b & \'>"))', capsys) \
        == "&lt;b &amp; &#x27;&gt;"
    assert run('print(html_unescape("&lt;i&gt;"))', capsys) == "<i>"


def test_split_lines_and_slugify(capsys):
    assert run('print(str(split_lines("a\\r\\nb\\nc")))', capsys) \
        == '["a", "b", "c"]'
    assert run('print(slugify("Hello, Bun World! 42"))', capsys) \
        == "hello-bun-world-42"


# ---------------------------------------------------------------------------
# math
# ---------------------------------------------------------------------------

def test_gcd_lcm(capsys):
    assert run('print(gcd(48, 18))', capsys) == "6"
    assert run('print(lcm(4, 6))', capsys) == "12"


def test_factorial(capsys):
    assert run('print(factorial(0))', capsys) == "1"
    assert run('print(factorial(10))', capsys) == "3628800"


def test_clamp_sign(capsys):
    assert run('print(clamp(15, 1, 10))', capsys) == "10"
    assert run('print(sign(-3))', capsys) == "-1"
    assert run('print(sign(0))', capsys) == "0"


# ---------------------------------------------------------------------------
# time + ids + hashing
# ---------------------------------------------------------------------------

def test_now_ms_is_big(capsys):
    assert int(run('print(now_ms() > 1600000000000)', capsys)) == 1


def test_uuid_unique(capsys):
    out = run('print(uuid() != uuid())', capsys)
    assert out == "true"


def test_crc32(capsys):
    assert run('print(crc32("hello"))', capsys) == "907060870"


# ---------------------------------------------------------------------------
# filesystem + rea
# ---------------------------------------------------------------------------

def test_file_size(tmp_path, capsys):
    target = tmp_path / "blob.txt"
    target.write_text("12345")
    assert run('print(file_size(%s))' % _bs(str(target)), capsys) == "5"


def _bs(path):
    return '"' + str(path).replace("\\", "\\\\") + '"'


def test_rea_missing_file_is_clean(capsys):
    """rea builtins must not crash on a path that has no REA report."""
    out = run('let r = rea_analyze("/tmp/no-such-binary-here")\n'
              'print(r != null)', capsys)
    assert out in ("true", "false")
