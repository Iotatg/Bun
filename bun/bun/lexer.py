import unicodedata

from . import langpacks
from .tokens import Token, TokenType
from .errors import LexError
from .ints import fits as fits_int

KEYWORDS = {
    "let": TokenType.LET,
    "var": TokenType.VAR,
    "fn": TokenType.FN,
    "struct": TokenType.STRUCT,
    "enum": TokenType.ENUM,
    "impl": TokenType.IMPL,
    "protocol": TokenType.PROTOCOL,
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
    "not": TokenType.NOT,
    "import": TokenType.IMPORT,
    "from": TokenType.FROM,
    "export": TokenType.EXPORT,
    "try": TokenType.TRY,
    "catch": TokenType.CATCH,
    "finally": TokenType.FINALLY,
    "with": TokenType.WITH,
    "as": TokenType.AS,
    "throw": TokenType.THROW,
    "assert": TokenType.ASSERT,
    "break": TokenType.BREAK,
    "continue": TokenType.CONTINUE,
    "del": TokenType.DEL,
    "yield": TokenType.YIELD,
}

_THREE_CHAR = {
    "<<=": TokenType.LSHIFT_ASSIGN,
    ">>=": TokenType.RSHIFT_ASSIGN,
}

_TWO_CHAR = {
    "==": TokenType.EQ,
    "!=": TokenType.NEQ,
    "<=": TokenType.LTE,
    ">=": TokenType.GTE,
    "->": TokenType.ARROW,
    "=>": TokenType.FAT_ARROW,
    "**": TokenType.DOUBLE_STAR,
    "<<": TokenType.LSHIFT,
    ">>": TokenType.RSHIFT,
    "++": TokenType.INCREMENT,
    "--": TokenType.DECREMENT,
    "??": TokenType.NULL_COALESCE,
    "+=": TokenType.PLUS_ASSIGN,
    "-=": TokenType.MINUS_ASSIGN,
    "*=": TokenType.STAR_ASSIGN,
    "/=": TokenType.SLASH_ASSIGN,
    "%=": TokenType.PERCENT_ASSIGN,
    "&=": TokenType.AMP_ASSIGN,
    "|=": TokenType.PIPE_ASSIGN,
    "^=": TokenType.CARET_ASSIGN,
}

_ONE_CHAR = {
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "*": TokenType.STAR,
    "/": TokenType.SLASH,
    "%": TokenType.PERCENT,
    "&": TokenType.AMP,
    "|": TokenType.PIPE,
    "^": TokenType.CARET,
    "@": TokenType.AT,
    "~": TokenType.TILDE,
    "=": TokenType.ASSIGN,
    "<": TokenType.LT,
    ">": TokenType.GT,
    "!": TokenType.BANG,
    "?": TokenType.QUESTION,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    "{": TokenType.LBRACE,
    "}": TokenType.RBRACE,
    "[": TokenType.LBRACKET,
    "]": TokenType.RBRACKET,
    ",": TokenType.COMMA,
    ":": TokenType.COLON,
    ".": TokenType.DOT,
}


class Lexer:
    def __init__(self, source, lang=None):
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens = []
        if lang is None:
            lang = langpacks.detect_directive(source)
        self.lang = lang
        self._hard = dict(KEYWORDS)
        self._soft = {}
        if lang:
            if not langpacks.has_pack(lang):
                raise LexError("unknown language pack '%s'" % lang, 1, 1)
            _, table = langpacks.pack(lang)
            for english, localized in table.items():
                if english in langpacks.SOFT_KEYWORDS:
                    self._soft.setdefault(localized, english)
                elif english in KEYWORDS:
                    self._hard.setdefault(localized, KEYWORDS[english])
        self._split_keys = sorted(set(self._hard) | set(self._soft),
                                  key=len, reverse=True)

    def lang_aliases(self):
        """The localized-keyword table, for the Bun-written front end.

        Both front ends must see one grammar. The host owns the language
        pack data (like module resolution), while the Bun lexer owns the
        word-splitting logic; this hands it the exact table this lexer
        built, so the two cannot drift apart.
        """
        hard = {word: kind for word, kind in self._hard.items()
                if word not in KEYWORDS}
        return {
            "code": self.lang,
            "hard": hard,
            "soft": dict(self._soft),
            "split": list(self._split_keys),
        }

    def tokenize(self):
        while self.pos < len(self.source):
            ch = self._peek()
            if ch in " \t\r\n":
                self._advance()
            elif ch == ";":
                # An optional statement terminator.  Bun's grammar already
                # ends a statement when its expression ends, so the mark is
                # decorative: skipping it lets one line hold several
                # statements without changing the grammar.
                self._advance()
            elif ch == "#" or (ch == "/" and self._peek(1) == "/"):
                while self.pos < len(self.source) and self._peek() != "\n":
                    self._advance()
            elif ch.isdigit():
                self._number()
            elif ch == '"' or ch == "'":
                if self.source[self.pos:self.pos + 3] == ch * 3:
                    self._triple_string(ch)
                else:
                    self._string(ch)
            elif ch == "f" and self._peek(1) in ('"', "'"):
                self._fstring()
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

    def _exponent_ahead(self):
        """True when the current position starts an exponent, like `e-8`."""
        if self._peek() != "e" and self._peek() != "E":
            return False
        offset = 1
        if self._peek(offset) == "+" or self._peek(offset) == "-":
            offset += 1
        digit = self._peek(offset)
        if digit == "" or not digit.isdigit():
            return False
        return True

    def _number(self):
        line, col = self.line, self.col
        start = self.pos
        if self._peek() == "0" and self._peek(1) != "" and self._peek(1) in "xXbBoO":
            prefix = self._peek(1).lower()
            self._advance()
            self._advance()
            digits_start = self.pos
            while self._peek().isalnum():
                self._advance()
            digits = self.source[digits_start:self.pos]
            if not digits:
                raise LexError("invalid numeric literal", line, col)
            try:
                if prefix == "x":
                    value = int(digits, 16)
                elif prefix == "b":
                    value = int(digits, 2)
                else:
                    value = int(digits, 8)
            except ValueError:
                raise LexError("invalid numeric literal", line, col)
            if not fits_int(value):
                raise LexError("integer literal out of range", line, col)
            self._add(TokenType.INT, value, line, col)
            return
        while self._peek().isdigit():
            self._advance()
        is_float = False
        if self._peek() == "." and self._peek(1).isdigit():
            is_float = True
            self._advance()
            while self._peek().isdigit():
                self._advance()
        if self._exponent_ahead():
            is_float = True
            self._advance()
            if self._peek() == "+" or self._peek() == "-":
                self._advance()
            while self._peek().isdigit():
                self._advance()
        elif self._peek() == "e" or self._peek() == "E":
            raise LexError("invalid numeric literal", line, col)
        text = self.source[start:self.pos]
        if is_float:
            self._add(TokenType.FLOAT, float(text), line, col)
        else:
            value = int(text)
            if not fits_int(value):
                raise LexError("integer literal out of range", line, col)
            self._add(TokenType.INT, value, line, col)

    def _skip(self, text):
        """Move the position over a piece of text."""
        newlines = text.count("\n")
        if newlines:
            self.line += newlines
            self.col = len(text) - text.rfind("\n")
        else:
            self.col += len(text)
        self.pos += len(text)

    def _string(self, quote='"'):
        line, col = self.line, self.col
        self._advance()
        start = self.pos
        end = self.source.find(quote, start)
        if end != -1:
            escape = self.source.find("\\", start, end)
            if escape == -1:
                # The string carries no escape, so the value comes in one
                # piece and the position moves over it at once.
                value = self.source[start:end]
                self._skip(value)
                self._advance()
                self._add(TokenType.STRING, value, line, col)
                return
        chars = list(self.source[start:self.pos])
        while True:
            if self.pos >= len(self.source):
                raise LexError("unterminated string", line, col)
            ch = self._advance()
            if ch == quote:
                break
            if ch == "\\":
                esc_line, esc_col = self.line, self.col
                chars.append(self._read_escape(esc_line, esc_col))
            else:
                chars.append(ch)
        self._add(TokenType.STRING, "".join(chars), line, col)

    def _read_escape(self, esc_line, esc_col):
        """Read the character after a backslash and answer its value."""
        nxt = self._advance()
        mapping = {"n": "\n", "t": "\t", "r": "\r", "b": "\b",
                   "f": "\f", "v": "\v", "0": "\0", '"': '"',
                   "'": "'", "\\": "\\"}
        if nxt in ("x", "u", "U"):
            # \xHH, \uHHHH and \UHHHHHHHH name a Unicode code point by
            # its hexadecimal value, the way a language that owns its own
            # strings should.
            count = {"x": 2, "u": 4, "U": 8}[nxt]
            digits = ""
            for _ in range(count):
                if self.pos >= len(self.source):
                    raise LexError("incomplete unicode escape",
                                   esc_line, esc_col)
                digits += self._advance()
            try:
                return chr(int(digits, 16))
            except (ValueError, OverflowError):
                raise LexError(
                    "invalid unicode escape '\\%s%s'" % (nxt, digits),
                    esc_line, esc_col)
        if nxt not in mapping:
            raise LexError("invalid escape '\\%s'" % nxt, esc_line, esc_col)
        return mapping[nxt]

    def _triple_string(self, quote):
        """Lex a multiline string delimited by three matching quotes.

        Newlines and single quotes inside the body are ordinary characters;
        only three quotes in a row end it.  Escapes use the very same table
        as a single-line string, so the two forms cannot drift apart.
        """
        line, col = self.line, self.col
        self._advance()
        self._advance()
        self._advance()
        chars = []
        while True:
            if self.pos >= len(self.source):
                raise LexError("unterminated multiline string", line, col)
            if (self._peek() == quote and self._peek(1) == quote
                    and self._peek(2) == quote):
                self._advance()
                self._advance()
                self._advance()
                break
            ch = self._advance()
            if ch == "\\":
                esc_line, esc_col = self.line, self.col
                chars.append(self._read_escape(esc_line, esc_col))
            else:
                chars.append(ch)
        self._add(TokenType.STRING, "".join(chars), line, col)

    def _fstring(self):
        """Lex an f-string.

        The token carries the *raw* body between the quotes. Escapes are
        resolved by the parser, which needs to see the literal text and the
        interpolated expressions separately. Inside an interpolated
        expression the same quote character may be reused, so the body
        scan tracks brace depth.
        """
        line, col = self.line, self.col
        self._advance()                 # the 'f' prefix
        quote = self._advance()         # the opening quote
        start = self.pos
        depth = 0
        while True:
            if self.pos >= len(self.source):
                raise LexError("unterminated string", line, col)
            ch = self.source[self.pos]
            if ch == "\\":
                self._advance()
                if self.pos >= len(self.source):
                    raise LexError("unterminated string", line, col)
                self._advance()
                continue
            if depth == 0 and ch == quote:
                break
            if ch == "{":
                depth += 1
            elif ch == "}":
                if depth > 0:
                    depth -= 1
            elif ch == quote:
                # A nested string inside an interpolated expression.
                self._advance()
                while True:
                    if self.pos >= len(self.source):
                        raise LexError("unterminated string", line, col)
                    inner = self.source[self.pos]
                    if inner == "\\":
                        self._advance()
                        if self.pos >= len(self.source):
                            raise LexError("unterminated string", line, col)
                        self._advance()
                        continue
                    self._advance()
                    if inner == quote:
                        break
                continue
            self._advance()
        body = self.source[start:self.pos]
        self._advance()                 # the closing quote
        self._add(TokenType.FSTRING, body, line, col)

    def _ident_char(self, ch):
        """A character that may continue an identifier in any script."""
        return bool(ch) and (ch.isalnum() or ch == "_" or
                             unicodedata.category(ch) in ("Mn", "Mc", "Me"))

    def _spaceless(self, text):
        """True when the text needs keyword splitting: the scripts of
        Chinese, Japanese, Thai and friends do not separate words with
        spaces, so a keyword may be glued to the name after it."""
        for ch in text:
            code = ord(ch)
            if (0x2E80 <= code <= 0x9FFF or 0xA960 <= code <= 0xA97F
                    or 0xAC00 <= code <= 0xD7FF or 0x0E00 <= code <= 0x0E7F
                    or 0x1780 <= code <= 0x17FF or 0x1000 <= code <= 0x109F):
                return True
        return False

    def _emit_word(self, text, line, col):
        """One identifier word: a localized or English keyword, a soft
        keyword under its English name, or a plain identifier."""
        if not text:
            return
        soft = self._soft.get(text)
        if soft is not None:
            self._add(TokenType.IDENT, soft, line, col)
            return
        keyword = self._hard.get(text)
        if keyword is not None:
            self._add(keyword, text, line, col)
            return
        if self.lang and self._spaceless(text):
            self._split_word(text, line, col)
            return
        self._add(TokenType.IDENT, text, line, col)

    def _split_word(self, text, line, col):
        """Peel localized keywords off the front of a glued word."""
        index = 0
        plain = ""
        while index < len(text):
            for key in self._split_keys:
                if text.startswith(key, index):
                    if plain:
                        self._add(TokenType.IDENT, plain, line,
                                  col + index - len(plain))
                        plain = ""
                    self._emit_word(key, line, col + index)
                    index += len(key)
                    break
            else:
                plain += text[index]
                index += 1
        if plain:
            self._add(TokenType.IDENT, plain, line,
                      col + index - len(plain))

    def _identifier(self):
        line, col = self.line, self.col
        start = self.pos
        while self._ident_char(self._peek()):
            self._advance()
        text = self.source[start:self.pos]
        self._emit_word(text, line, col)

    def _operator(self):
        line, col = self.line, self.col
        ch = self._advance()
        three = ch + self._peek() + self._peek(1)
        if three in _THREE_CHAR:
            self._advance()
            self._advance()
            self._add(_THREE_CHAR[three], three, line, col)
            return
        two = ch + self._peek()
        if two in _TWO_CHAR:
            self._advance()
            self._add(_TWO_CHAR[two], two, line, col)
            return
        if ch in _ONE_CHAR:
            self._add(_ONE_CHAR[ch], ch, line, col)
            return
        raise LexError("unexpected character '%s'" % ch, line, col)
