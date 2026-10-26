from .records import record


class TokenType:
    """The type of a token.

    The types are plain strings: an enum costs a fifth of the startup
    time of the language, and the name of a type is all that is ever
    used."""

    INT = "INT"
    FLOAT = "FLOAT"
    STRING = "STRING"
    FSTRING = "FSTRING"
    IDENT = "IDENT"
    TRUE = "TRUE"
    FALSE = "FALSE"
    NULL = "NULL"
    LET = "LET"
    VAR = "VAR"
    FN = "FN"
    STRUCT = "STRUCT"
    IMPL = "IMPL"
    PROTOCOL = "PROTOCOL"
    IF = "IF"
    ELSE = "ELSE"
    WHILE = "WHILE"
    FOR = "FOR"
    IN = "IN"
    RETURN = "RETURN"
    AND = "AND"
    OR = "OR"
    NOT = "NOT"
    PLUS = "PLUS"
    MINUS = "MINUS"
    STAR = "STAR"
    DOUBLE_STAR = "DOUBLE_STAR"
    SLASH = "SLASH"
    PERCENT = "PERCENT"
    AMP = "AMP"
    PIPE = "PIPE"
    CARET = "CARET"
    TILDE = "TILDE"
    LSHIFT = "LSHIFT"
    RSHIFT = "RSHIFT"
    ASSIGN = "ASSIGN"
    EQ = "EQ"
    NEQ = "NEQ"
    LT = "LT"
    LTE = "LTE"
    GT = "GT"
    GTE = "GTE"
    BANG = "BANG"
    QUESTION = "QUESTION"
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"
    LBRACE = "LBRACE"
    RBRACE = "RBRACE"
    LBRACKET = "LBRACKET"
    RBRACKET = "RBRACKET"
    COMMA = "COMMA"
    COLON = "COLON"
    DOT = "DOT"
    IMPORT = "IMPORT"
    FROM = "FROM"
    EXPORT = "EXPORT"
    TRY = "TRY"
    CATCH = "CATCH"
    FINALLY = "FINALLY"
    WITH = "WITH"
    AS = "AS"
    THROW = "THROW"
    ASSERT = "ASSERT"
    BREAK = "BREAK"
    CONTINUE = "CONTINUE"
    DEL = "DEL"
    YIELD = "YIELD"
    ARROW = "ARROW"
    FAT_ARROW = "FAT_ARROW"
    AT = "AT"
    EOF = "EOF"


@record
class Token:
    type: TokenType
    value: object
    line: int
    col: int
