class BunError(Exception):
    def __init__(self, msg, line=0, col=0, filename=None, source=None,
                 cause=None):
        super().__init__(msg)
        self.msg = msg
        self.line = line
        self.col = col
        self.filename = filename
        self.source = source
        self.cause = cause


class LexError(BunError):
    pass


class ParseError(BunError):
    pass


class BunRuntimeError(BunError):
    pass


class BunTypeError(BunError):
    pass


# The hints of the errors.
#
# The rule of the feel model: an error says what to do next.  The hint
# is a second line under the error, and it never changes the message:
# the message is the contract of the language, and the hint is the advice
# of the runtime.
#
# The table is matched in order, and the first hint whose pattern is in
# the message wins.  A pattern that is a plain text is a prefix of the
# message; a pattern between two slashes is a regular expression.
HINTS = [
    ("undefined variable",
     "declare the name before you use it, or check the spelling"),
    ("cannot assign to immutable variable",
     "use 'var' for a name that changes"),
    ("cannot assign value of type",
     "the value has another type than the variable; change the "
     "declaration or the value"),
    ("cannot convert",
     "the value has another type; turn it into a number with int() or "
     "float(), and into text with str()"),
    ("integer literal out of range",
     "the integers of Bun are 64 bits wide; the bigint helpers work on "
     "lists of bytes and hold more"),
    ("integer overflow",
     "the integers of Bun are 64 bits wide, and the operation left the "
     "range"),
    ("integer out of range",
     "the integers of Bun are 64 bits wide; the value does not fit"),
    ("out of range",
     "the index is past the end of the container; the first index is 0 "
     "and the last one is len(container) - 1"),
    ("index must be an integer",
     "an index is a whole number"),
    ("unknown method",
     "the method is not on this type; the methods of a list are push, "
     "pop, shift, len, join, contains, reverse, slice, sort, splice and "
     "insert"),
    ("value is not iterable",
     "a for loop walks a list or a dictionary"),
    ("not enough values to unpack",
     "the number of names and the number of values have to be the same"),
    ("cannot unpack",
     "only a list or a dictionary can be unpacked into names"),
    ("can only assign into a list",
     "the item of a list is set with its index"),
    ("can only assign a list to a slice",
     "a slice of a list takes a list of the same length"),
    ("division by zero",
     "check the divisor before the division"),
    ("negative shift count",
     "a shift counts to the left, so it cannot be negative"),
    ("no matching case",
     "add a case that matches the value, or a case that catches "
     "everything"),
    ("assertion failed",
     "the assertion is a promise of the program; check the values it "
     "holds"),
    ("unsupported operands",
     "the two values have types that do not go together"),
    ("unary '~' expects an integer",
     "the bit operators work on whole numbers"),
    ("the '?' operator is only allowed inside a function",
     "move the '?' into a function that returns a result"),
    ("the '?' operator needs a function that returns 'result'",
     "change the return type of the function to 'result'"),
    ("cannot use '?' on a value of type",
     "the value has to be a Result: wrap it with Ok() or Err()"),
    ("'?' expects a Result value",
     "the value has to be a Result: wrap it with Ok() or Err()"),
    ("expects",
     "the arguments do not match the signature of the call"),
    ("cannot open file",
     "check the path of the file"),
]


def hint_for(message):
    """The hint of an error message, or None when there is none."""
    for pattern, hint in HINTS:
        if pattern in message:
            return hint
    return None


def format_error(err, source, filename):
    if err.filename is not None:
        filename = err.filename
    if err.source is not None:
        source = err.source
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
    out += _format_causes(getattr(err, "cause", None))
    hint = hint_for(err.msg)
    if hint is not None:
        out += "\n  hint: %s" % hint
    return out


def _format_causes(cause):
    out = ""
    while cause is not None:
        if isinstance(cause, BunError):
            out += f"\n  caused by: {cause.msg}"
            cause = cause.cause
        else:
            out += f"\n  caused by: {cause}"
            cause = None
    return out
