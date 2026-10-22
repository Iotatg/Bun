# Bun Language (v0.1 Interpreter) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `bun`, an original interpreted programming language (Rust/Go/Python-inspired syntax) with a tree-walking interpreter written in Python.

**Architecture:** Classic pipeline — `Lexer` turns source into tokens, a recursive-descent `Parser` builds an AST of dataclasses, and a tree-walking `Interpreter` evaluates the AST against a lexical `Environment`. Runtime values are Python natives (`int`, `float`, `str`, `bool`, `None`, `list`) plus `BunFunction`/`Builtin` wrappers.

**Tech Stack:** Python 3.11 (no third-party runtime deps), pytest for tests, bash launcher script.

## Global Constraints

- Python version floor: `>=3.8` (developed on 3.11).
- Zero third-party runtime dependencies — standard library only.
- Test framework: `pytest` (install globally with `pip install --break-system-packages pytest`).
- Package name: `bun`. CLI: `python -m bun <file.bun>`.
- No line-break statement terminators; statements are separated by grammar, not `;` or newlines.
- Comments support both `//` and `#`.
- All AST nodes live in `bun/ast.py`; all runtime value helpers in `bun/values.py`.
- Every error reports `line:col` and is a subclass of `BunError` in `bun/errors.py`.

---

### Task 1: Project scaffolding, errors, and tokens

**Files:**
- Create: `bun/__init__.py`
- Create: `bun/errors.py`
- Create: `bun/tokens.py`
- Create: `pyproject.toml`
- Test: `tests/test_errors.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `BunError(msg, line=0, col=0)` with attributes `.msg`, `.line`, `.col`; subclasses `LexError`, `ParseError`, `BunRuntimeError`.
  - `format_error(err, source, filename) -> str`
  - `TokenType` (Enum), `Token(type, value, line, col)`

- [ ] **Step 1: Install pytest**

```bash
pip install --break-system-packages pytest
```

Expected: pytest installed successfully (`Successfully installed pytest-...`).

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "bun-lang"
version = "0.1.0"
requires-python = ">=3.8"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 3: Write `bun/__init__.py`**

```python
"""Bun programming language (v0.1)."""

__version__ = "0.1.0"
```

- [ ] **Step 4: Write `bun/errors.py`**

```python
class BunError(Exception):
    def __init__(self, msg, line=0, col=0):
        super().__init__(msg)
        self.msg = msg
        self.line = line
        self.col = col


class LexError(BunError):
    pass


class ParseError(BunError):
    pass


class BunRuntimeError(BunError):
    pass


def format_error(err, source, filename):
    lines = source.splitlines()
    out = f"error: {err.msg}"
    if err.line:
        out += f"\n  --> {filename}:{err.line}:{err.col}"
        if 0 < err.line <= len(lines):
            text = lines[err.line - 1]
            gutter = str(err.line)
            pad = " " * len(gutter)
            caret = " " * max(err.col - 1, 0) + "^"
            out += f"\n {pad} |\n {gutter} | {text}\n {pad} | {caret}"
    return out
```

- [ ] **Step 5: Write `bun/tokens.py`**

```python
from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    INT = auto()
    FLOAT = auto()
    STRING = auto()
    IDENT = auto()
    TRUE = auto()
    FALSE = auto()
    NULL = auto()
    LET = auto()
    VAR = auto()
    FN = auto()
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    FOR = auto()
    IN = auto()
    RETURN = auto()
    AND = auto()
    OR = auto()
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    ASSIGN = auto()
    EQ = auto()
    NEQ = auto()
    LT = auto()
    LTE = auto()
    GT = auto()
    GTE = auto()
    BANG = auto()
    LPAREN = auto()
    RPAREN = auto()
    LBRACE = auto()
    RBRACE = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    COMMA = auto()
    EOF = auto()


@dataclass
class Token:
    type: TokenType
    value: object
    line: int
    col: int
```

- [ ] **Step 6: Write failing test `tests/test_errors.py`**

```python
from bun.errors import BunRuntimeError, format_error


def test_format_error_with_location():
    err = BunRuntimeError("boom", line=2, col=3)
    out = format_error(err, "a\nbbb\nc", "f.bun")
    assert "error: boom" in out
    assert "f.bun:2:3" in out
    assert "bbb" in out
    assert "^" in out


def test_format_error_without_location():
    err = BunRuntimeError("boom")
    assert format_error(err, "", "f.bun") == "error: boom"
```

- [ ] **Step 7: Run test to verify it passes**

Run: `python -m pytest tests/test_errors.py -v`
Expected: 2 passed.

- [ ] **Step 8: Commit**

```bash
git add bun/__init__.py bun/errors.py bun/tokens.py pyproject.toml tests/test_errors.py
git commit -m "feat: add package scaffolding, error types, and token definitions"
```

---

### Task 2: Lexer

**Files:**
- Create: `bun/lexer.py`
- Test: `tests/test_lexer.py`

**Interfaces:**
- Consumes: `TokenType`, `Token` from `bun.tokens`; `LexError` from `bun.errors`.
- Produces: `Lexer(source).tokenize() -> list[Token]` (always ends with an `EOF` token). Exported constant `KEYWORDS`.

- [ ] **Step 1: Write `bun/lexer.py`**

```python
from .tokens import Token, TokenType
from .errors import LexError

KEYWORDS = {
    "let": TokenType.LET,
    "var": TokenType.VAR,
    "fn": TokenType.FN,
    "if": TokenType.IF,
    "else": TokenType.ELSE,
    "while": TokenType.WHILE,
    "for": TokenType.FOR,
    "in": TokenType.IN,
    "return": TokenType.RETURN,
    "true": TokenType.TRUE,
    "false": TokenType.FALSE,
    "null": TokenType.NULL,
    "and": TokenType.AND,
    "or": TokenType.OR,
}

_TWO_CHAR = {
    "==": TokenType.EQ,
    "!=": TokenType.NEQ,
    "<=": TokenType.LTE,
    ">=": TokenType.GTE,
}

_ONE_CHAR = {
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "*": TokenType.STAR,
    "/": TokenType.SLASH,
    "%": TokenType.PERCENT,
    "=": TokenType.ASSIGN,
    "<": TokenType.LT,
    ">": TokenType.GT,
    "!": TokenType.BANG,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    "{": TokenType.LBRACE,
    "}": TokenType.RBRACE,
    "[": TokenType.LBRACKET,
    "]": TokenType.RBRACKET,
    ",": TokenType.COMMA,
}


class Lexer:
    def __init__(self, source):
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens = []

    def tokenize(self):
        while self.pos < len(self.source):
            ch = self._peek()
            if ch in " \t\r\n":
                self._advance()
            elif ch == "#" or (ch == "/" and self._peek(1) == "/"):
                while self.pos < len(self.source) and self._peek() != "\n":
                    self._advance()
            elif ch.isdigit():
                self._number()
            elif ch == '"':
                self._string()
            elif ch.isalpha() or ch == "_":
                self._identifier()
            else:
                self._operator()
        self._add(TokenType.EOF, None, self.line, self.col)
        return self.tokens

    def _add(self, ttype, value, line, col):
        self.tokens.append(Token(ttype, value, line, col))

    def _peek(self, offset=0):
        i = self.pos + offset
        return self.source[i] if i < len(self.source) else ""

    def _advance(self):
        ch = self.source[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _number(self):
        line, col = self.line, self.col
        start = self.pos
        while self._peek().isdigit():
            self._advance()
        is_float = False
        if self._peek() == "." and self._peek(1).isdigit():
            is_float = True
            self._advance()
            while self._peek().isdigit():
                self._advance()
        text = self.source[start:self.pos]
        if is_float:
            self._add(TokenType.FLOAT, float(text), line, col)
        else:
            self._add(TokenType.INT, int(text), line, col)

    def _string(self):
        line, col = self.line, self.col
        self._advance()
        chars = []
        while True:
            if self.pos >= len(self.source):
                raise LexError("unterminated string", line, col)
            ch = self._advance()
            if ch == '"':
                break
            if ch == "\\":
                esc_line, esc_col = self.line, self.col
                nxt = self._advance()
                mapping = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}
                if nxt not in mapping:
                    raise LexError("invalid escape '\\%s'" % nxt, esc_line, esc_col)
                chars.append(mapping[nxt])
            else:
                chars.append(ch)
        self._add(TokenType.STRING, "".join(chars), line, col)

    def _identifier(self):
        line, col = self.line, self.col
        start = self.pos
        while self._peek().isalnum() or self._peek() == "_":
            self._advance()
        text = self.source[start:self.pos]
        self._add(KEYWORDS.get(text, TokenType.IDENT), text, line, col)

    def _operator(self):
        line, col = self.line, self.col
        ch = self._advance()
        two = ch + self._peek()
        if two in _TWO_CHAR:
            self._advance()
            self._add(_TWO_CHAR[two], two, line, col)
            return
        if ch in _ONE_CHAR:
            self._add(_ONE_CHAR[ch], ch, line, col)
            return
        raise LexError("unexpected character '%s'" % ch, line, col)
```

- [ ] **Step 2: Write failing test `tests/test_lexer.py`**

```python
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
```

- [ ] **Step 3: Run test to verify it passes**

Run: `python -m pytest tests/test_lexer.py -v`
Expected: 7 passed.

- [ ] **Step 4: Commit**

```bash
git add bun/lexer.py tests/test_lexer.py
git commit -m "feat: add lexer with numbers, strings, keywords, and comments"
```

---

### Task 3: AST nodes

**Files:**
- Create: `bun/ast.py`

**Interfaces:**
- Consumes: nothing.
- Produces: dataclasses used by the parser and interpreter, each carrying `line`/`col`:
  - Statements: `Program(statements)`, `LetStmt(name, value, mutable, line, col)`, `AssignStmt(target, value, line, col)`, `ExprStmt(expr, line, col)`, `Block(statements, line, col)`, `IfStmt(condition, then_branch, else_branch, line, col)`, `WhileStmt(condition, body, line, col)`, `ForStmt(var_name, iterable, body, line, col)`, `FnDecl(name, params, body, line, col)`, `ReturnStmt(value, line, col)`
  - Expressions: `Literal(value, line, col)`, `Identifier(name, line, col)`, `ListLiteral(elements, line, col)`, `Unary(op, operand, line, col)`, `Binary(left, op, right, line, col)`, `Logical(left, op, right, line, col)`, `Call(callee, args, line, col)`, `Index(target, index, line, col)`

- [ ] **Step 1: Write `bun/ast.py`**

```python
from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass
class Program:
    statements: List[Any]


@dataclass
class LetStmt:
    name: str
    value: Any
    mutable: bool = False
    line: int = 0
    col: int = 0


@dataclass
class AssignStmt:
    target: Any
    value: Any
    line: int = 0
    col: int = 0


@dataclass
class ExprStmt:
    expr: Any
    line: int = 0
    col: int = 0


@dataclass
class Block:
    statements: List[Any]
    line: int = 0
    col: int = 0


@dataclass
class IfStmt:
    condition: Any
    then_branch: Any
    else_branch: Optional[Any] = None
    line: int = 0
    col: int = 0


@dataclass
class WhileStmt:
    condition: Any
    body: Any
    line: int = 0
    col: int = 0


@dataclass
class ForStmt:
    var_name: str
    iterable: Any
    body: Any
    line: int = 0
    col: int = 0


@dataclass
class FnDecl:
    name: str
    params: List[str]
    body: Any
    line: int = 0
    col: int = 0


@dataclass
class ReturnStmt:
    value: Optional[Any] = None
    line: int = 0
    col: int = 0


@dataclass
class Literal:
    value: Any
    line: int = 0
    col: int = 0


@dataclass
class Identifier:
    name: str
    line: int = 0
    col: int = 0


@dataclass
class ListLiteral:
    elements: List[Any]
    line: int = 0
    col: int = 0


@dataclass
class Unary:
    op: str
    operand: Any
    line: int = 0
    col: int = 0


@dataclass
class Binary:
    left: Any
    op: str
    right: Any
    line: int = 0
    col: int = 0


@dataclass
class Logical:
    left: Any
    op: str
    right: Any
    line: int = 0
    col: int = 0


@dataclass
class Call:
    callee: Any
    args: List[Any]
    line: int = 0
    col: int = 0


@dataclass
class Index:
    target: Any
    index: Any
    line: int = 0
    col: int = 0
```

- [ ] **Step 2: Verify it imports**

Run: `python -c "from bun import ast; print(ast.LetStmt('x', ast.Literal(1), False, 1, 1))"`
Expected: prints `LetStmt(name='x', value=Literal(value=1, line=1, col=1), mutable=False, line=1, col=1)`.

- [ ] **Step 3: Commit**

```bash
git add bun/ast.py
git commit -m "feat: define AST node dataclasses"
```

---

### Task 4: Parser

**Files:**
- Create: `bun/parser.py`
- Test: `tests/test_parser.py`

**Interfaces:**
- Consumes: `Lexer` from `bun.lexer`; `TokenType` from `bun.tokens`; node classes from `bun.ast`; `ParseError` from `bun.errors`.
- Produces:
  - `Parser(tokens)` with `.parse() -> ast.Program`
  - `parse(source) -> ast.Program`
  - `parse_expression(source) -> ast node`
  - Precedence (low to high): `or` < `and` < `== !=` < `< <= > >=` < `+ -` < `* / %` < unary `- !` < call `()` / index `[]`.

- [ ] **Step 1: Write `bun/parser.py`**

```python
from .tokens import TokenType
from .lexer import Lexer
from . import ast
from .errors import ParseError


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def _peek(self):
        return self.tokens[self.pos]

    def _check(self, ttype):
        return self._peek().type == ttype

    def _advance(self):
        tok = self.tokens[self.pos]
        if tok.type != TokenType.EOF:
            self.pos += 1
        return tok

    def _match(self, *types):
        if self._peek().type in types:
            return self._advance()
        return None

    def _expect(self, ttype, message):
        if self._check(ttype):
            return self._advance()
        tok = self._peek()
        raise ParseError("%s, found %s" % (message, tok.type.name), tok.line, tok.col)

    def parse(self):
        statements = []
        while not self._check(TokenType.EOF):
            statements.append(self._statement())
        return ast.Program(statements)

    def _statement(self):
        t = self._peek().type
        if t == TokenType.LET:
            return self._var_decl(False)
        if t == TokenType.VAR:
            return self._var_decl(True)
        if t == TokenType.FN:
            return self._fn_decl()
        if t == TokenType.IF:
            return self._if_stmt()
        if t == TokenType.WHILE:
            return self._while_stmt()
        if t == TokenType.FOR:
            return self._for_stmt()
        if t == TokenType.RETURN:
            return self._return_stmt()
        return self._expr_stmt()

    def _var_decl(self, mutable):
        kw = self._advance()
        name = self._expect(TokenType.IDENT, "expected variable name")
        self._expect(TokenType.ASSIGN, "expected '=' after variable name")
        value = self._expression()
        return ast.LetStmt(name.value, value, mutable, kw.line, kw.col)

    def _fn_decl(self):
        kw = self._advance()
        name = self._expect(TokenType.IDENT, "expected function name")
        self._expect(TokenType.LPAREN, "expected '(' after function name")
        params = []
        if not self._check(TokenType.RPAREN):
            params.append(self._expect(TokenType.IDENT, "expected parameter name").value)
            while self._match(TokenType.COMMA):
                params.append(self._expect(TokenType.IDENT, "expected parameter name").value)
        self._expect(TokenType.RPAREN, "expected ')' after parameters")
        body = self._block()
        return ast.FnDecl(name.value, params, body, kw.line, kw.col)

    def _if_stmt(self):
        kw = self._advance()
        condition = self._expression()
        then_branch = self._block()
        else_branch = None
        if self._match(TokenType.ELSE):
            if self._check(TokenType.IF):
                else_branch = self._if_stmt()
            else:
                else_branch = self._block()
        return ast.IfStmt(condition, then_branch, else_branch, kw.line, kw.col)

    def _while_stmt(self):
        kw = self._advance()
        condition = self._expression()
        body = self._block()
        return ast.WhileStmt(condition, body, kw.line, kw.col)

    def _for_stmt(self):
        kw = self._advance()
        name = self._expect(TokenType.IDENT, "expected loop variable name")
        self._expect(TokenType.IN, "expected 'in' after loop variable")
        iterable = self._expression()
        body = self._block()
        return ast.ForStmt(name.value, iterable, body, kw.line, kw.col)

    def _return_stmt(self):
        kw = self._advance()
        value = None
        if (not self._check(TokenType.RBRACE) and not self._check(TokenType.EOF)
                and self._peek().line == kw.line):
            value = self._expression()
        return ast.ReturnStmt(value, kw.line, kw.col)

    def _expr_stmt(self):
        start = self._peek()
        expr = self._expression()
        if self._match(TokenType.ASSIGN):
            value = self._expression()
            if not isinstance(expr, (ast.Identifier, ast.Index)):
                raise ParseError("invalid assignment target", start.line, start.col)
            return ast.AssignStmt(expr, value, start.line, start.col)
        return ast.ExprStmt(expr, start.line, start.col)

    def _block(self):
        lbrace = self._expect(TokenType.LBRACE, "expected '{'")
        statements = []
        while not self._check(TokenType.RBRACE) and not self._check(TokenType.EOF):
            statements.append(self._statement())
        self._expect(TokenType.RBRACE, "expected '}'")
        return ast.Block(statements, lbrace.line, lbrace.col)

    def _expression(self):
        return self._or()

    def _or(self):
        expr = self._and()
        while self._check(TokenType.OR):
            op = self._advance()
            expr = ast.Logical(expr, "or", self._and(), op.line, op.col)
        return expr

    def _and(self):
        expr = self._equality()
        while self._check(TokenType.AND):
            op = self._advance()
            expr = ast.Logical(expr, "and", self._equality(), op.line, op.col)
        return expr

    def _equality(self):
        expr = self._comparison()
        while self._peek().type in (TokenType.EQ, TokenType.NEQ):
            op = self._advance()
            expr = ast.Binary(expr, op.value, self._comparison(), op.line, op.col)
        return expr

    def _comparison(self):
        expr = self._term()
        while self._peek().type in (TokenType.LT, TokenType.LTE, TokenType.GT, TokenType.GTE):
            op = self._advance()
            expr = ast.Binary(expr, op.value, self._term(), op.line, op.col)
        return expr

    def _term(self):
        expr = self._factor()
        while self._peek().type in (TokenType.PLUS, TokenType.MINUS):
            op = self._advance()
            expr = ast.Binary(expr, op.value, self._factor(), op.line, op.col)
        return expr

    def _factor(self):
        expr = self._unary()
        while self._peek().type in (TokenType.STAR, TokenType.SLASH, TokenType.PERCENT):
            op = self._advance()
            expr = ast.Binary(expr, op.value, self._unary(), op.line, op.col)
        return expr

    def _unary(self):
        if self._peek().type in (TokenType.MINUS, TokenType.BANG):
            op = self._advance()
            return ast.Unary(op.value, self._unary(), op.line, op.col)
        return self._postfix()

    def _postfix(self):
        expr = self._primary()
        while True:
            if self._check(TokenType.LPAREN):
                self._advance()
                args = []
                if not self._check(TokenType.RPAREN):
                    args.append(self._expression())
                    while self._match(TokenType.COMMA):
                        args.append(self._expression())
                self._expect(TokenType.RPAREN, "expected ')' after arguments")
                expr = ast.Call(expr, args, expr.line, expr.col)
            elif self._check(TokenType.LBRACKET):
                self._advance()
                index = self._expression()
                self._expect(TokenType.RBRACKET, "expected ']' after index")
                expr = ast.Index(expr, index, expr.line, expr.col)
            else:
                break
        return expr

    def _primary(self):
        tok = self._peek()
        if tok.type in (TokenType.INT, TokenType.FLOAT, TokenType.STRING):
            self._advance()
            return ast.Literal(tok.value, tok.line, tok.col)
        if tok.type == TokenType.TRUE:
            self._advance()
            return ast.Literal(True, tok.line, tok.col)
        if tok.type == TokenType.FALSE:
            self._advance()
            return ast.Literal(False, tok.line, tok.col)
        if tok.type == TokenType.NULL:
            self._advance()
            return ast.Literal(None, tok.line, tok.col)
        if tok.type == TokenType.IDENT:
            self._advance()
            return ast.Identifier(tok.value, tok.line, tok.col)
        if tok.type == TokenType.LPAREN:
            self._advance()
            expr = self._expression()
            self._expect(TokenType.RPAREN, "expected ')' after expression")
            return expr
        if tok.type == TokenType.LBRACKET:
            self._advance()
            elements = []
            if not self._check(TokenType.RBRACKET):
                elements.append(self._expression())
                while self._match(TokenType.COMMA):
                    elements.append(self._expression())
            self._expect(TokenType.RBRACKET, "expected ']' after list elements")
            return ast.ListLiteral(elements, tok.line, tok.col)
        raise ParseError("unexpected token %s" % tok.type.name, tok.line, tok.col)


def parse(source):
    return Parser(Lexer(source).tokenize()).parse()


def parse_expression(source):
    return Parser(Lexer(source).tokenize())._expression()
```

- [ ] **Step 2: Write failing test `tests/test_parser.py`**

```python
import pytest

from bun import ast
from bun.parser import parse, parse_expression
from bun.errors import ParseError


def test_let_statement():
    stmt = parse("let x = 1").statements[0]
    assert isinstance(stmt, ast.LetStmt)
    assert stmt.name == "x" and stmt.mutable is False
    assert isinstance(stmt.value, ast.Literal) and stmt.value.value == 1


def test_var_is_mutable():
    stmt = parse("var y = 2").statements[0]
    assert isinstance(stmt, ast.LetStmt) and stmt.mutable is True


def test_binary_precedence():
    expr = parse_expression("1 + 2 * 3")
    assert isinstance(expr, ast.Binary) and expr.op == "+"
    assert isinstance(expr.right, ast.Binary) and expr.right.op == "*"


def test_logical_precedence():
    expr = parse_expression("a or b and c")
    assert isinstance(expr, ast.Logical) and expr.op == "or"
    assert isinstance(expr.right, ast.Logical) and expr.right.op == "and"


def test_function_declaration():
    fn = parse("fn add(a, b) { return a + b }").statements[0]
    assert isinstance(fn, ast.FnDecl) and fn.params == ["a", "b"]


def test_if_else():
    stmt = parse("if x { } else { }").statements[0]
    assert isinstance(stmt, ast.IfStmt)
    assert stmt.then_branch is not None and stmt.else_branch is not None


def test_assignment_statement():
    stmt = parse("x = 5").statements[0]
    assert isinstance(stmt, ast.AssignStmt)
    assert isinstance(stmt.target, ast.Identifier)


def test_index_assignment():
    stmt = parse("nums[0] = 5").statements[0]
    assert isinstance(stmt, ast.AssignStmt)
    assert isinstance(stmt.target, ast.Index)


def test_invalid_assignment_target():
    with pytest.raises(ParseError):
        parse("1 = 2")


def test_list_literal():
    expr = parse_expression("[1, 2, 3]")
    assert isinstance(expr, ast.ListLiteral) and len(expr.elements) == 3
```

- [ ] **Step 3: Run test to verify it passes**

Run: `python -m pytest tests/test_parser.py -v`
Expected: 10 passed.

- [ ] **Step 4: Commit**

```bash
git add bun/parser.py tests/test_parser.py
git commit -m "feat: add recursive-descent parser for Bun"
```

---

### Task 5: Runtime values and environment

**Files:**
- Create: `bun/values.py`
- Create: `bun/environment.py`
- Test: `tests/test_values.py`
- Test: `tests/test_environment.py`

**Interfaces:**
- Consumes: `BunRuntimeError` from `bun.errors`.
- Produces:
  - `BunFunction(name, params, body, closure)` — dataclass.
  - `Builtin(name, func)` — dataclass where `func(list) -> value`.
  - `ReturnSignal(value)` — exception used for `return` control flow.
  - `is_number(v) -> bool` (excludes `bool`).
  - `is_truthy(v) -> bool`.
  - `stringify(v) -> str`.
  - `values_equal(a, b) -> bool`.
  - `Environment(parent=None)` with `.define(name, value, mutable)`, `.get(name)`, `.assign(name, value)`.

- [ ] **Step 1: Write `bun/values.py`**

```python
from dataclasses import dataclass
from typing import Any, List


@dataclass
class BunFunction:
    name: str
    params: List[str]
    body: Any
    closure: Any


@dataclass
class Builtin:
    name: str
    func: Any


class ReturnSignal(Exception):
    def __init__(self, value):
        super().__init__()
        self.value = value


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_truthy(value):
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return len(value) > 0
    if isinstance(value, list):
        return len(value) > 0
    return True


def stringify(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "[" + ", ".join(stringify(v) for v in value) + "]"
    if isinstance(value, BunFunction):
        return "<fn %s>" % value.name
    if isinstance(value, Builtin):
        return "<builtin %s>" % value.name
    return str(value)


def values_equal(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if a is None or b is None:
        return a is None and b is None
    if is_number(a) and is_number(b):
        return a == b
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(values_equal(x, y) for x, y in zip(a, b))
    return False
```

- [ ] **Step 2: Write `bun/environment.py`**

```python
from .errors import BunRuntimeError


class Environment:
    def __init__(self, parent=None):
        self.parent = parent
        self.values = {}

    def define(self, name, value, mutable):
        self.values[name] = [value, mutable]

    def get(self, name):
        env = self
        while env is not None:
            if name in env.values:
                return env.values[name][0]
            env = env.parent
        raise BunRuntimeError("undefined variable '%s'" % name)

    def assign(self, name, value):
        env = self
        while env is not None:
            if name in env.values:
                if not env.values[name][1]:
                    raise BunRuntimeError("cannot assign to immutable variable '%s'" % name)
                env.values[name][0] = value
                return
            env = env.parent
        raise BunRuntimeError("undefined variable '%s'" % name)
```

- [ ] **Step 3: Write failing test `tests/test_values.py`**

```python
from bun.values import is_number, is_truthy, stringify, values_equal


def test_truthiness():
    assert is_truthy(1) is True
    assert is_truthy(0) is False
    assert is_truthy("") is False
    assert is_truthy("x") is True
    assert is_truthy(None) is False
    assert is_truthy([]) is False
    assert is_truthy([1]) is True


def test_stringify():
    assert stringify(True) == "true"
    assert stringify(None) == "null"
    assert stringify([1, "a", False]) == "[1, a, false]"


def test_values_equal_types():
    assert values_equal(True, 1) is False
    assert values_equal(True, True) is True
    assert values_equal(1, 1.0) is True
    assert values_equal([1, 2], [1, 2]) is True


def test_is_number_excludes_bool():
    assert is_number(1) is True
    assert is_number(True) is False
```

- [ ] **Step 4: Write failing test `tests/test_environment.py`**

```python
import pytest

from bun.environment import Environment
from bun.errors import BunRuntimeError


def test_define_and_get():
    env = Environment()
    env.define("x", 1, True)
    assert env.get("x") == 1


def test_child_lookup():
    parent = Environment()
    parent.define("x", 1, True)
    child = Environment(parent)
    assert child.get("x") == 1


def test_assign_updates_outer():
    parent = Environment()
    parent.define("x", 1, True)
    child = Environment(parent)
    child.assign("x", 2)
    assert parent.get("x") == 2


def test_assign_immutable_errors():
    env = Environment()
    env.define("x", 1, False)
    with pytest.raises(BunRuntimeError):
        env.assign("x", 2)


def test_get_undefined_errors():
    with pytest.raises(BunRuntimeError):
        Environment().get("nope")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_values.py tests/test_environment.py -v`
Expected: 9 passed.

- [ ] **Step 6: Commit**

```bash
git add bun/values.py bun/environment.py tests/test_values.py tests/test_environment.py
git commit -m "feat: add runtime value helpers and lexical environment"
```

---

### Task 6: Built-in functions

**Files:**
- Create: `bun/builtins.py`
- Test: `tests/test_builtins.py`

**Interfaces:**
- Consumes: `Builtin`, `stringify` from `bun.values`; `BunRuntimeError` from `bun.errors`.
- Produces: `register_builtins(env)` which defines `print`, `len`, `range`, `str`, `int`, `float` as immutable bindings. Each underlying callable takes a single list argument and returns a value.

- [ ] **Step 1: Write `bun/builtins.py`**

```python
from .values import Builtin, stringify
from .errors import BunRuntimeError


def _print(args):
    print(" ".join(stringify(a) for a in args))
    return None


def _len(args):
    if len(args) != 1:
        raise BunRuntimeError("len() expects 1 argument")
    value = args[0]
    if isinstance(value, (str, list)):
        return len(value)
    raise BunRuntimeError("len() expects a string or list")


def _range(args):
    if len(args) == 1:
        start, stop = 0, args[0]
    elif len(args) == 2:
        start, stop = args[0], args[1]
    else:
        raise BunRuntimeError("range() expects 1 or 2 arguments")
    for value in (start, stop):
        if not isinstance(value, int) or isinstance(value, bool):
            raise BunRuntimeError("range() expects integer arguments")
    return list(range(start, stop))


def _str(args):
    if len(args) != 1:
        raise BunRuntimeError("str() expects 1 argument")
    return stringify(args[0])


def _int(args):
    if len(args) != 1:
        raise BunRuntimeError("int() expects 1 argument")
    value = args[0]
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            raise BunRuntimeError("cannot convert '%s' to int" % value)
    raise BunRuntimeError("cannot convert value to int")


def _float(args):
    if len(args) != 1:
        raise BunRuntimeError("float() expects 1 argument")
    value = args[0]
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            raise BunRuntimeError("cannot convert '%s' to float" % value)
    raise BunRuntimeError("cannot convert value to float")


def register_builtins(env):
    env.define("print", Builtin("print", _print), False)
    env.define("len", Builtin("len", _len), False)
    env.define("range", Builtin("range", _range), False)
    env.define("str", Builtin("str", _str), False)
    env.define("int", Builtin("int", _int), False)
    env.define("float", Builtin("float", _float), False)
```

- [ ] **Step 2: Write failing test `tests/test_builtins.py`**

```python
import pytest

from bun.environment import Environment
from bun.builtins import register_builtins
from bun.errors import BunRuntimeError


def call(name, args):
    env = Environment()
    register_builtins(env)
    return env.get(name).func(args)


def test_str_int_float():
    assert call("str", [42]) == "42"
    assert call("int", ["7"]) == 7
    assert call("int", [3.9]) == 3
    assert call("float", ["1.5"]) == 1.5


def test_len_and_range():
    assert call("len", [[1, 2, 3]]) == 3
    assert call("len", ["abcd"]) == 4
    assert call("range", [3]) == [0, 1, 2]
    assert call("range", [1, 4]) == [1, 2, 3]


def test_len_type_error():
    with pytest.raises(BunRuntimeError):
        call("len", [5])


def test_range_wrong_type():
    with pytest.raises(BunRuntimeError):
        call("range", ["a"])


def test_print(capsys):
    call("print", [1, "and", True])
    assert capsys.readouterr().out == "1 and true\n"
```

- [ ] **Step 3: Run test to verify it passes**

Run: `python -m pytest tests/test_builtins.py -v`
Expected: 5 passed.

- [ ] **Step 4: Commit**

```bash
git add bun/builtins.py tests/test_builtins.py
git commit -m "feat: add built-in functions print, len, range, str, int, float"
```

---

### Task 7: Interpreter

**Files:**
- Create: `bun/interpreter.py`
- Test: `tests/test_interpreter.py`

**Interfaces:**
- Consumes: `bun.ast`; `BunFunction`, `Builtin`, `ReturnSignal`, `is_truthy`, `is_number`, `values_equal`, `stringify` from `bun.values`; `Environment` from `bun.environment`; `register_builtins` from `bun.builtins`; `BunRuntimeError` from `bun.errors`.
- Produces:
  - `Interpreter()` with `.globals` (an `Environment` seeded with builtins).
  - `.run(program, env=None)`
  - `.execute(node, env)`
  - `.evaluate(node, env)`
  - Both `execute`/`evaluate` attach `line`/`col` from the node to any `BunRuntimeError` that lacks a location.
  - Semantics: `let` immutable, `var` mutable; `/` is integer division for two ints, float otherwise; `%` and `/` by zero raise; `+` concatenates two strings or two lists.

- [ ] **Step 1: Write `bun/interpreter.py`**

```python
from . import ast
from .values import (
    BunFunction, Builtin, ReturnSignal, is_truthy, is_number,
    values_equal, stringify,
)
from .environment import Environment
from .builtins import register_builtins
from .errors import BunRuntimeError


class Interpreter:
    def __init__(self):
        self.globals = Environment()
        register_builtins(self.globals)

    def run(self, program, env=None):
        env = env if env is not None else self.globals
        self.execute(program, env)

    def execute(self, node, env):
        try:
            self._execute(node, env)
        except BunRuntimeError as error:
            if error.line == 0 and getattr(node, "line", 0):
                error.line, error.col = node.line, node.col
            raise

    def evaluate(self, node, env):
        try:
            return self._evaluate(node, env)
        except BunRuntimeError as error:
            if error.line == 0 and getattr(node, "line", 0):
                error.line, error.col = node.line, node.col
            raise

    def _execute(self, node, env):
        if isinstance(node, ast.Program):
            for statement in node.statements:
                self.execute(statement, env)
        elif isinstance(node, ast.LetStmt):
            env.define(node.name, self.evaluate(node.value, env), node.mutable)
        elif isinstance(node, ast.AssignStmt):
            self._assign(node.target, self.evaluate(node.value, env), env)
        elif isinstance(node, ast.ExprStmt):
            self.evaluate(node.expr, env)
        elif isinstance(node, ast.Block):
            self._execute_block(node, env)
        elif isinstance(node, ast.IfStmt):
            if is_truthy(self.evaluate(node.condition, env)):
                self.execute(node.then_branch, env)
            elif node.else_branch is not None:
                self.execute(node.else_branch, env)
        elif isinstance(node, ast.WhileStmt):
            while is_truthy(self.evaluate(node.condition, env)):
                self.execute(node.body, env)
        elif isinstance(node, ast.ForStmt):
            iterable = self.evaluate(node.iterable, env)
            if not isinstance(iterable, (list, str)):
                raise BunRuntimeError("value is not iterable")
            for item in iterable:
                loop_env = Environment(env)
                loop_env.define(node.var_name, item, True)
                self.execute(node.body, loop_env)
        elif isinstance(node, ast.FnDecl):
            env.define(node.name, BunFunction(node.name, node.params, node.body, env), False)
        elif isinstance(node, ast.ReturnStmt):
            value = self.evaluate(node.value, env) if node.value is not None else None
            raise ReturnSignal(value)
        else:
            raise BunRuntimeError("unknown statement: %s" % type(node).__name__)

    def _execute_block(self, block, env):
        block_env = Environment(env)
        for statement in block.statements:
            self.execute(statement, block_env)

    def _assign(self, target, value, env):
        if isinstance(target, ast.Identifier):
            env.assign(target.name, value)
        elif isinstance(target, ast.Index):
            obj = self.evaluate(target.target, env)
            index = self.evaluate(target.index, env)
            if not isinstance(obj, list):
                raise BunRuntimeError("can only assign into a list")
            if not isinstance(index, int) or isinstance(index, bool):
                raise BunRuntimeError("list index must be an integer")
            if index < 0 or index >= len(obj):
                raise BunRuntimeError("list index %d out of range" % index)
            obj[index] = value
        else:
            raise BunRuntimeError("invalid assignment target")

    def _evaluate(self, node, env):
        if isinstance(node, ast.Literal):
            return node.value
        if isinstance(node, ast.Identifier):
            return env.get(node.name)
        if isinstance(node, ast.ListLiteral):
            return [self.evaluate(element, env) for element in node.elements]
        if isinstance(node, ast.Unary):
            operand = self.evaluate(node.operand, env)
            if node.op == "-":
                if not is_number(operand):
                    raise BunRuntimeError("unary '-' expects a number")
                return -operand
            if node.op == "!":
                return not is_truthy(operand)
            raise BunRuntimeError("unknown unary operator '%s'" % node.op)
        if isinstance(node, ast.Binary):
            return self._binary(node, env)
        if isinstance(node, ast.Logical):
            left = self.evaluate(node.left, env)
            if node.op == "and":
                return self.evaluate(node.right, env) if is_truthy(left) else left
            return left if is_truthy(left) else self.evaluate(node.right, env)
        if isinstance(node, ast.Call):
            return self._call(node, env)
        if isinstance(node, ast.Index):
            return self._index(self.evaluate(node.target, env), self.evaluate(node.index, env))
        raise BunRuntimeError("unknown expression: %s" % type(node).__name__)

    def _binary(self, node, env):
        op = node.op
        left = self.evaluate(node.left, env)
        right = self.evaluate(node.right, env)
        if op == "+":
            if isinstance(left, str) and isinstance(right, str):
                return left + right
            if isinstance(left, list) and isinstance(right, list):
                return left + right
            if is_number(left) and is_number(right):
                return left + right
            raise BunRuntimeError("unsupported operands for '+'")
        if op in ("-", "*", "%"):
            if not (is_number(left) and is_number(right)):
                raise BunRuntimeError("unsupported operands for '%s'" % op)
            if op == "%":
                if right == 0:
                    raise BunRuntimeError("division by zero")
                return left % right
            return left - right if op == "-" else left * right
        if op == "/":
            if not (is_number(left) and is_number(right)):
                raise BunRuntimeError("unsupported operands for '/'")
            if right == 0:
                raise BunRuntimeError("division by zero")
            if isinstance(left, int) and isinstance(right, int):
                return left // right
            return left / right
        if op in ("<", "<=", ">", ">="):
            if (is_number(left) and is_number(right)) or (
                    isinstance(left, str) and isinstance(right, str)):
                if op == "<":
                    return left < right
                if op == "<=":
                    return left <= right
                if op == ">":
                    return left > right
                return left >= right
            raise BunRuntimeError("unsupported operands for '%s'" % op)
        if op == "==":
            return values_equal(left, right)
        if op == "!=":
            return not values_equal(left, right)
        raise BunRuntimeError("unknown operator '%s'" % op)

    def _call(self, node, env):
        callee = self.evaluate(node.callee, env)
        args = [self.evaluate(arg, env) for arg in node.args]
        if isinstance(callee, BunFunction):
            if len(args) != len(callee.params):
                raise BunRuntimeError(
                    "function '%s' expects %d argument(s), got %d"
                    % (callee.name, len(callee.params), len(args)))
            call_env = Environment(callee.closure)
            for name, value in zip(callee.params, args):
                call_env.define(name, value, True)
            try:
                self._execute_block(callee.body, call_env)
            except ReturnSignal as signal:
                return signal.value
            return None
        if isinstance(callee, Builtin):
            return callee.func(args)
        raise BunRuntimeError("%s is not callable" % stringify(callee))

    def _index(self, obj, index):
        if isinstance(obj, (list, str)):
            if not isinstance(index, int) or isinstance(index, bool):
                raise BunRuntimeError("index must be an integer")
            if index < 0 or index >= len(obj):
                raise BunRuntimeError("index %d out of range" % index)
            return obj[index]
        raise BunRuntimeError("value is not indexable")
```

- [ ] **Step 2: Write failing test `tests/test_interpreter.py`**

```python
import pytest

from bun.interpreter import Interpreter
from bun.parser import parse, parse_expression
from bun.errors import BunRuntimeError


def run(source):
    interp = Interpreter()
    interp.run(parse(source))
    return interp


def eval_expr(source):
    interp = Interpreter()
    return interp.evaluate(parse_expression(source), interp.globals)


def test_arithmetic():
    assert eval_expr("1 + 2 * 3") == 7
    assert eval_expr("10 / 3") == 3
    assert eval_expr("10 % 3") == 1
    assert eval_expr("2.5 + 0.5") == 3.0


def test_string_concat():
    assert eval_expr('"a" + "b"') == "ab"


def test_comparison_and_logical():
    assert eval_expr("1 < 2") is True
    assert eval_expr("true and false") is False
    assert eval_expr("null or 5") == 5


def test_let_and_var():
    interp = run("let x = 1\nvar y = 2\ny = y + 1")
    assert interp.globals.get("y") == 3


def test_immutable_assignment_errors():
    with pytest.raises(BunRuntimeError):
        run("let x = 1\nx = 2")


def test_undefined_variable_errors():
    with pytest.raises(BunRuntimeError):
        run("print(unknown)")


def test_if_else():
    interp = run("var r = 0\nif 1 < 2 { r = 1 } else { r = 2 }")
    assert interp.globals.get("r") == 1


def test_while_loop():
    interp = run("var i = 0\nwhile i < 5 { i = i + 1 }")
    assert interp.globals.get("i") == 5


def test_for_range():
    interp = run("var total = 0\nfor i in range(1, 4) { total = total + i }")
    assert interp.globals.get("total") == 6


def test_function_and_return():
    interp = run("fn add(a, b) { return a + b }\nlet r = add(2, 3)")
    assert interp.globals.get("r") == 5


def test_recursion():
    source = "fn fact(n) { if n < 2 { return 1 } return n * fact(n - 1) }\nlet r = fact(5)"
    interp = run(source)
    assert interp.globals.get("r") == 120


def test_closure_counter():
    source = (
        "fn make() {\n"
        "  var c = 0\n"
        "  fn inc() { c = c + 1\n    return c }\n"
        "  return inc\n"
        "}\n"
        "let f = make()\n"
        "let a = f()\n"
        "let b = f()"
    )
    interp = run(source)
    assert interp.globals.get("a") == 1
    assert interp.globals.get("b") == 2


def test_list_index_assignment():
    interp = run("let xs = [1, 2, 3]\nxs[0] = 9\nlet first = xs[0]\nlet n = len(xs)")
    assert interp.globals.get("first") == 9
    assert interp.globals.get("n") == 3


def test_index_out_of_range():
    with pytest.raises(BunRuntimeError):
        run("let xs = [1]\nlet x = xs[5]")


def test_division_by_zero():
    with pytest.raises(BunRuntimeError):
        run("let x = 1 / 0")
```

- [ ] **Step 3: Run test to verify it passes**

Run: `python -m pytest tests/test_interpreter.py -v`
Expected: 16 passed.

- [ ] **Step 4: Commit**

```bash
git add bun/interpreter.py tests/test_interpreter.py
git commit -m "feat: add tree-walking interpreter for statements and expressions"
```

---

### Task 8: CLI, REPL, and launcher

**Files:**
- Create: `bun/cli.py`
- Create: `bun/__main__.py`
- Create: `bin/bun`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `Lexer`, `Parser`, `Interpreter`, `stringify`, `BunError`, `format_error`, `bun.ast`.
- Produces:
  - `run_source(source, filename="<stdin>") -> Environment`
  - `run_file(path) -> int` (exit code)
  - `repl() -> int`
  - `main(argv=None) -> int`

- [ ] **Step 1: Write `bun/cli.py`**

```python
import sys

from .lexer import Lexer
from .parser import Parser
from .interpreter import Interpreter
from .values import stringify
from .errors import BunError, format_error
from . import ast

USAGE = """Bun programming language

Usage:
  bun <file.bun>     run a Bun program
  bun                start the interactive REPL
  bun -h | --help    show this help
"""


def run_source(source, filename="<stdin>"):
    tokens = Lexer(source).tokenize()
    program = Parser(tokens).parse()
    interpreter = Interpreter()
    interpreter.run(program)
    return interpreter.globals


def run_file(path):
    try:
        with open(path, "r") as handle:
            source = handle.read()
    except OSError as error:
        print("error: cannot open file '%s': %s" % (path, error), file=sys.stderr)
        return 1
    try:
        run_source(source, filename=path)
        return 0
    except BunError as error:
        print(format_error(error, source, path), file=sys.stderr)
        return 1


def repl():
    interpreter = Interpreter()
    while True:
        try:
            line = input("bun> ")
        except EOFError:
            print()
            break
        if line.strip() == "":
            continue
        try:
            program = Parser(Lexer(line).tokenize()).parse()
            for statement in program.statements:
                if isinstance(statement, ast.ExprStmt):
                    value = interpreter.evaluate(statement.expr, interpreter.globals)
                    if value is not None:
                        print(stringify(value))
                else:
                    interpreter.execute(statement, interpreter.globals)
        except BunError as error:
            print(format_error(error, line, "<repl>"))
    return 0


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return repl()
    if args[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    return run_file(args[0])
```

- [ ] **Step 2: Write `bun/__main__.py`**

```python
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Write `bin/bun`**

```bash
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$DIR${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m bun "$@"
```

- [ ] **Step 4: Make launcher executable**

```bash
chmod +x bin/bun
```

- [ ] **Step 5: Write failing test `tests/test_cli.py`**

```python
import pytest

from bun.cli import run_source, run_file
from bun.errors import BunRuntimeError


def test_run_source_returns_globals():
    env = run_source("let x = 21\nlet y = x * 2")
    assert env.get("y") == 42


def test_run_source_prints(capsys):
    run_source('print("hi")')
    assert capsys.readouterr().out == "hi\n"


def test_run_file_missing(tmp_path):
    assert run_file(str(tmp_path / "nope.bun")) == 1


def test_run_file_ok(tmp_path):
    program = tmp_path / "ok.bun"
    program.write_text("print(1 + 1)\n")
    assert run_file(str(program)) == 0


def test_run_file_error_exit_code(capsys, tmp_path):
    program = tmp_path / "bad.bun"
    program.write_text("let x = unknown\n")
    assert run_file(str(program)) == 1
    assert "error:" in capsys.readouterr().err
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_cli.py -v`
Expected: 5 passed.

- [ ] **Step 7: Smoke-test the CLI**

```bash
printf 'print("hello from Bun")\n' > /tmp/opencode/hello.bun
python -m bun /tmp/opencode/hello.bun
```

Expected output: `hello from Bun`

- [ ] **Step 8: Commit**

```bash
git add bun/cli.py bun/__main__.py bin/bun tests/test_cli.py
git commit -m "feat: add CLI, REPL, and bun launcher script"
```

---

### Task 9: Golden end-to-end tests, examples, and README

**Files:**
- Create: `tests/test_golden.py`
- Create: `tests/golden/hello.bun` + `tests/golden/hello.out`
- Create: `tests/golden/arithmetic.bun` + `tests/golden/arithmetic.out`
- Create: `tests/golden/fizzbuzz.bun` + `tests/golden/fizzbuzz.out`
- Create: `tests/golden/fib.bun` + `tests/golden/fib.out`
- Create: `tests/golden/lists.bun` + `tests/golden/lists.out`
- Create: `examples/hello.bun`
- Create: `README.md`

**Interfaces:**
- Consumes: `run_source` from `bun.cli`.
- Produces: golden harness that runs every `tests/golden/*.bun` and compares stdout to the sibling `.out` file.

- [ ] **Step 1: Write `tests/test_golden.py`**

```python
import glob
import os

import pytest

from bun.cli import run_source

GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "golden")


def golden_cases():
    return sorted(glob.glob(os.path.join(GOLDEN_DIR, "*.bun")))


@pytest.mark.parametrize("path", golden_cases(), ids=os.path.basename)
def test_golden(path, capsys):
    with open(path, "r") as handle:
        source = handle.read()
    with open(path[:-4] + ".out", "r") as handle:
        expected = handle.read()
    run_source(source, filename=path)
    assert capsys.readouterr().out == expected
```

- [ ] **Step 2: Write golden program and output files**

`tests/golden/hello.bun`:
```bun
print("Hello, Bun!")
```
`tests/golden/hello.out`:
```
Hello, Bun!
```

`tests/golden/arithmetic.bun`:
```bun
let a = 10
let b = 3
print(a + b)
print(a - b)
print(a * b)
print(a / b)
print(a % b)
```
`tests/golden/arithmetic.out`:
```
13
7
30
3
1
```

`tests/golden/fizzbuzz.bun`:
```bun
for i in range(1, 16) {
    if i % 15 == 0 { print("FizzBuzz") }
    else if i % 3 == 0 { print("Fizz") }
    else if i % 5 == 0 { print("Buzz") }
    else { print(i) }
}
```
`tests/golden/fizzbuzz.out`:
```
1
2
Fizz
4
Buzz
Fizz
7
8
Fizz
Buzz
11
Fizz
13
14
FizzBuzz
```

`tests/golden/fib.bun`:
```bun
fn fib(n) {
    if n < 2 { return n }
    return fib(n - 1) + fib(n - 2)
}
for i in range(0, 10) {
    print(fib(i))
}
```
`tests/golden/fib.out`:
```
0
1
1
2
3
5
8
13
21
34
```

`tests/golden/lists.bun`:
```bun
let nums = [1, 2, 3]
nums[0] = 99
print(nums)
print(len(nums))
```
`tests/golden/lists.out`:
```
[99, 2, 3]
3
```

- [ ] **Step 3: Create `examples/hello.bun`**

```bun
// A friendly first Bun program.
fn greet(name) {
    return "Hello, " + name + "!"
}

let names = ["World", "Bun", "Coder"]
for name in names {
    print(greet(name))
}
```

- [ ] **Step 4: Write `README.md`**

````markdown
# Bun

Bun is an original, dynamically-typed programming language with Rust/Go/Python-inspired
syntax. This repository contains the v0.1 tree-walking interpreter, written in Python.

## Requirements

- Python 3.8 or newer

## Run a program

```bash
python -m bun examples/hello.bun
```

## Start the REPL

```bash
python -m bun
```

Or use the launcher:

```bash
./bin/bun examples/hello.bun
```

## Language tour

```bun
// line comment
# also a comment

let x = 10          // immutable
var count = 0       // mutable
let name = "Bun"

fn add(a, b) {
    return a + b
}

if x > 5 { print("big") } else { print("small") }

while count < 3 { count = count + 1 }

for i in range(0, 5) { print(i) }

let nums = [1, 2, 3]
nums[0] = 99
print(len(nums))
```

Built-in functions: `print`, `len`, `range`, `str`, `int`, `float`.

## Tests

```bash
pip install --break-system-packages pytest
python -m pytest -v
```

## Roadmap

- Phase 1: tree-walking interpreter (this release)
- Phase 2: static type checker
- Phase 3: bytecode compiler + VM
- Phase 4: self-hosting (Bun written in Bun)
````

- [ ] **Step 5: Run the full test suite**

Run: `python -m pytest -v`
Expected: all tests pass (errors, lexer, parser, values, environment, builtins, interpreter, cli, golden).

- [ ] **Step 6: Run the example end-to-end**

```bash
python -m bun examples/hello.bun
```

Expected output:
```
Hello, World!
Hello, Bun!
Hello, Coder!
```

- [ ] **Step 7: Commit**

```bash
git add tests/test_golden.py tests/golden examples/hello.bun README.md
git commit -m "feat: add golden end-to-end tests, example program, and README"
```

---

## Self-Review

**Spec coverage:**
- Pipeline Lexer → Parser → AST → Interpreter → output: Tasks 2, 4, 3, 7.
- Components table (`lexer.py`, `tokens.py`, `ast.py`, `parser.py`, `values.py`, `environment.py`, `interpreter.py`, `builtins.py`, `errors.py`, `cli.py`, `__main__.py`, `tests/`): Tasks 1–9 cover every file.
- Syntax (`let`/`var`, `fn`, `if`/`else`, `while`, `for in`, lists, comments): Tasks 2–4, verified by golden programs.
- Semantics (dynamic typing, `let` immutable / `var` mutable, block scoping + closures, both comment styles, truthiness): Tasks 5 and 7, tested in Tasks 5, 6, 7.
- Operators & precedence: Task 4 parser methods ordered `or → and → equality → comparison → term → factor → unary → postfix`.
- Error handling (`line:col` + caret): Tasks 1 and 8, tested in Task 8.
- Testing strategy (unit + golden): Tasks 1–8 unit tests, Task 9 golden harness.

**Placeholder scan:** No TBD/TODO/"handle edge cases" left; every code step contains complete code.

**Type consistency:** `LetStmt.mutable`, `FnDecl.params`, `Binary.op` (string), `Logical.op` ("and"/"or"), `Builtin(name, func)`, `BunFunction(name, params, body, closure)`, `Environment.define/get/assign`, and `Interpreter.run/execute/evaluate` are used identically across parser, interpreter, CLI, and tests.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-10-14-bun-language.md`.
