"""The Bun-written front end reads Bun's own language packs.

A `#lang:` program is still a Bun program, so the front end written in
Bun must see the same tokens, AST, bytecode and static errors as the
Python one. The host supplies only the keyword table; the word-splitting
logic lives in `selfhost/lexer.bun`.

These cases are deliberately small but cover every branch of `emit_word`:
localized hard keywords, soft keywords, spaceless scripts with a glued
name, a plain English program, and a program with no directive at all.
"""

import pytest

from bun.checker import Checker
from bun.cli import main
from bun.compiler import Compiler
from bun.errors import BunError
from bun.lexer import Lexer
from bun.parser import Parser
from bun.selfhost import (
    ast_to_data,
    canonical,
    code_to_data,
    run_front_end,
    token_to_data,
)


PROGRAMS = {
    "hi": '#lang: hi\nमानी x = 1\nमानी y = 2\nprint(x + y)\n',
    "hi-soft": '#lang: hi\nमानी मिलान = 7\nprint(मिलान)\n',
    "hi-match": '#lang: hi\nमानी n = 2\nprint(मिलान n { 1 => "one" 2 => "two" _ => "many" })\n',
    "zh-glued": '#lang: zh\n让x = 3\n让y = 4\nprint(x + y)\n',
    "zh-spaced": '#lang: zh\n让 x = 5\nprint(x)\n',
    "ja": '#lang: ja\nおく x = 6\nprint(x)\n',
    "th": '#lang: th\nกำหนด x = 8\nprint(x)\n',
    "hinglish": '#lang: hinglish\nmanle x = 11\nprint(x)\n',
    "fr": '#lang: fr\nsoit x = 12\nprint(x)\n',
    "english": 'let x = 10\nprint(x)\n',
    "no-directive": 'let 让x = 9\nprint(让x)\n',
    "unknown-pack": '#lang: zz-not-a-pack\nlet x = 13\nprint(x)\n',
}


@pytest.fixture(params=sorted(PROGRAMS), ids=lambda key: key)
def program(request, tmp_path):
    key = request.param
    path = tmp_path / (key.replace("-", "_") + ".bun")
    source = PROGRAMS[key]
    path.write_text(source, encoding="utf-8")
    return key, str(path), source


def _python_tokens(source):
    return [token_to_data(token) for token in Lexer(source).tokenize()]


def _python_ast(source):
    return ast_to_data(Parser(Lexer(source).tokenize()).parse())


def _python_code(path, source):
    program = Parser(Lexer(source).tokenize()).parse()
    return code_to_data(Compiler(path, source).compile_program(program))


def _python_check_error(source, base_dir):
    program = Parser(Lexer(source).tokenize()).parse()
    try:
        Checker().check(program, base_dir=base_dir)
    except BunError as error:
        return (error.msg, error.line, error.col)
    return None


def _bun_check_error(path):
    try:
        run_front_end(path, "check", check=False)
    except BunError as error:
        return (error.msg, error.line, error.col)
    return None


def test_token_parity(program, capsys):
    _, path, source = program
    expected = canonical(_python_tokens(source))
    run_front_end(path, "lex", check=False)
    assert capsys.readouterr().out == expected + "\n"


def test_ast_parity(program, capsys):
    _, path, source = program
    expected = canonical(_python_ast(source))
    run_front_end(path, "ast", check=False)
    assert capsys.readouterr().out == expected + "\n"


def test_code_parity(program, capsys):
    _, path, source = program
    expected = canonical(_python_code(path, source))
    run_front_end(path, "dump", check=False)
    assert capsys.readouterr().out == expected + "\n"


def test_checker_parity(program):
    import os

    _, path, source = program
    base_dir = os.path.dirname(os.path.abspath(path))
    assert _bun_check_error(path) == _python_check_error(source, base_dir)


def test_execution_parity(program, capsys):
    _, path, _ = program
    assert main([path]) == 0
    python_out = capsys.readouterr().out
    assert main(["--front-end", "bun", path]) == 0
    bun_out = capsys.readouterr().out
    assert bun_out == python_out
    assert bun_out.strip() != ""


def test_alias_table_is_the_single_source():
    """The Bun lexer is handed the very table the Python lexer built."""
    lexer = Lexer(PROGRAMS["hi"])
    data = lexer.lang_aliases()
    assert data["code"] == "hi"
    assert data["hard"]["मानी"] == "LET"
    assert data["hard"]["आयात"] == "IMPORT"
    assert data["soft"]["मिलान"] == "match"
    # Longest-first, so a glued keyword wins over a shorter prefix.
    assert data["split"] == sorted(data["split"], key=len, reverse=True)
    # English keywords are already compiled into the Bun lexer, so only
    # localized aliases travel across the host boundary.
    assert all(word not in ("let", "fn", "import")
               for word in data["hard"])


def test_hard_alias_keeps_its_own_spelling():
    toks = _python_tokens(PROGRAMS["hi"])
    assert toks[0] == {"type": "LET", "value": "मानी", "line": 2, "col": 1}


def test_soft_alias_becomes_an_english_ident():
    toks = _python_tokens(PROGRAMS["hi-soft"])
    assert toks[1] == {"type": "IDENT", "value": "match",
                       "line": 2, "col": 6}


def test_spaceless_script_splits_a_glued_keyword():
    toks = _python_tokens(PROGRAMS["zh-glued"])
    assert toks[0] == {"type": "LET", "value": "让", "line": 2, "col": 1}
    assert toks[1] == {"type": "IDENT", "value": "x", "line": 2, "col": 2}


def test_no_directive_never_splits_a_name():
    """Without a pack, a CJK identifier is one name, not a keyword."""
    toks = _python_tokens(PROGRAMS["no-directive"])
    assert toks[1] == {"type": "IDENT", "value": "让x",
                       "line": 1, "col": 5}
    assert Lexer(PROGRAMS["no-directive"]).lang_aliases()["code"] is None


def test_unknown_directive_is_just_a_comment():
    lexer = Lexer(PROGRAMS["unknown-pack"])
    assert lexer.lang_aliases()["code"] is None


def test_cli_lang_flag_both_front_ends(tmp_path, capsys):
    """`--lang hi` must reach the Bun front end too, not only Python."""
    path = tmp_path / "cli_lang.bun"
    path.write_text("मानी x = 21\nprint(x * 2)\n", encoding="utf-8")
    assert main(["--lang", "hi", str(path)]) == 0
    python_out = capsys.readouterr().out
    assert main(["--lang", "hi", "--front-end", "bun", str(path)]) == 0
    assert capsys.readouterr().out == python_out == "42\n"


def test_cli_lang_auto_both_front_ends(tmp_path, capsys):
    """`--lang auto` resolves on both sides to the same detected pack."""
    path = tmp_path / "cli_auto.bun"
    path.write_text(
        "मानी x = सही\nमानी y = झूठ\nअगर x { print(1) } अन्यथा { print(0) }\n",
        encoding="utf-8")
    assert main(["--lang", "auto", str(path)]) == 0
    python_out = capsys.readouterr().out
    assert main(["--lang", "auto", "--front-end", "bun", str(path)]) == 0
    assert capsys.readouterr().out == python_out == "1\n"
