import pytest

from bun.lexer import Lexer
from bun.tokens import TokenType
from bun.errors import LexError


def test_numbers_and_operators():
    toks = Lexer("1 + 2 * 3").tokenize()
    assert [t.type for t in toks] == [
        TokenType.INT, TokenType.PLUS, TokenType.INT,
        TokenType.STAR, TokenType.INT, TokenType.EOF,
    ]
    assert [t.value for t in toks[:-1]] == [1, "+", 2, "*", 3]


def test_float_and_string():
    toks = Lexer('3.14 "hi\\n"').tokenize()
    assert toks[0].type == TokenType.FLOAT and toks[0].value == 3.14
    assert toks[1].type == TokenType.STRING and toks[1].value == "hi\n"


def test_exponent_notation():
    toks = Lexer("1e-8 2.5E+3 1e8").tokenize()
    assert [t.type for t in toks[:-1]] == [
        TokenType.FLOAT, TokenType.FLOAT, TokenType.FLOAT]
    assert toks[0].value == 1e-8
    assert toks[1].value == 2500.0
    assert toks[2].value == 100000000.0


def test_an_incomplete_exponent_is_an_error():
    with pytest.raises(LexError) as info:
        Lexer("1e").tokenize()
    assert info.value.msg == "invalid numeric literal"


def test_a_name_that_starts_with_e_is_not_an_exponent():
    toks = Lexer("1 e").tokenize()
    assert toks[0].type == TokenType.INT
    assert toks[1].type == TokenType.IDENT


def test_keywords():
    source = "let var fn if else while for in return true false null and or"
    toks = Lexer(source).tokenize()
    assert [t.type for t in toks[:-1]] == [
        TokenType.LET, TokenType.VAR, TokenType.FN, TokenType.IF, TokenType.ELSE,
        TokenType.WHILE, TokenType.FOR, TokenType.IN, TokenType.RETURN,
        TokenType.TRUE, TokenType.FALSE, TokenType.NULL, TokenType.AND, TokenType.OR,
    ]


def test_comments():
    toks = Lexer("1 // comment\n# another\n2").tokenize()
    assert [t.value for t in toks[:-1]] == [1, 2]


def test_line_and_column():
    toks = Lexer("a\n  b").tokenize()
    assert toks[0].line == 1 and toks[0].col == 1
    assert toks[1].line == 2 and toks[1].col == 3


def test_unterminated_string():
    with pytest.raises(LexError):
        Lexer('"abc').tokenize()


def test_unexpected_character():
    with pytest.raises(LexError):
        Lexer("$").tokenize()
