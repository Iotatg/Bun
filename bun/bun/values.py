from __future__ import annotations
from .records import record

from .dict import BunDict
from .errors import BunRuntimeError
from .set import BunSet


SECRET_MASK = "***"


@record
class BunFunction:
    name: str
    params: list[str]
    body: object
    closure: object
    filename: object = None
    source: object = None
    param_specs: list[object] = None
    is_generator: bool = False


@record
class Builtin:
    name: str
    func: object


class BunSecret:
    """A value that is redacted in every rendering.

    The wrapped value is only reachable through the ``reveal`` method, which
    keeps the escape hatch greppable.
    """

    def __init__(self, value):
        self.value = value


class ReturnSignal(Exception):
    def __init__(self, value, line=0, col=0):
        super().__init__(value)
        self.value = value
        self.line = line
        self.col = col


class LoopSignal(Exception):
    def __init__(self, line=0, col=0):
        super().__init__()
        self.line = line
        self.col = col


class BreakSignal(LoopSignal):
    pass


class ContinueSignal(LoopSignal):
    pass


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
    return _stringify(value, frozenset())


def _stringify(value, seen):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, BunSecret):
        return SECRET_MASK
    if isinstance(value, list):
        if id(value) in seen:
            return "[...]"
        nested = seen | {id(value)}
        return "[" + ", ".join(_stringify(v, nested) for v in value) + "]"
    if isinstance(value, BunDict):
        if id(value) in seen:
            return "{...}"
        nested = seen | {id(value)}
        pairs = ", ".join(
            "%s: %s" % (_stringify(k, nested), _stringify(v, nested)) for k, v in
            zip(value.keys(), value.values()))
        return "{" + pairs + "}"
    if isinstance(value, BunSet):
        if id(value) in seen:
            return "{...}"
        nested = seen | {id(value)}
        items = ", ".join(_stringify(item, nested) for item in value.values())
        return "{" + items + "}"
    if isinstance(value, BunFunction):
        return "<fn %s>" % value.name
    if isinstance(value, Builtin):
        return "<builtin %s>" % value.name
    return str(value)


def values_equal(a, b):
    if isinstance(a, BunSecret) or isinstance(b, BunSecret):
        if not isinstance(a, BunSecret) or not isinstance(b, BunSecret):
            return False
        return values_equal(a.value, b.value)
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
    if isinstance(a, BunDict) and isinstance(b, BunDict):
        if len(a) != len(b):
            return False
        for key in a.keys():
            if not b.has(key):
                return False
            if not values_equal(a.get(key), b.get(key)):
                return False
        return True
    if isinstance(a, BunSet) and isinstance(b, BunSet):
        if len(a) != len(b):
            return False
        for item in a.values():
            if not b.contains(item):
                return False
        return True
    return False


def quote_string(text):
    escaped = text.replace("\\", "\\\\")
    escaped = escaped.replace('"', '\\"')
    escaped = escaped.replace("\n", "\\n")
    escaped = escaped.replace("\t", "\\t")
    escaped = escaped.replace("\r", "\\r")
    return '"' + escaped + '"'


def repr_value(value):
    """Render a value the way the `!r` f-string conversion should."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return quote_string(value)
    if isinstance(value, BunSecret):
        return SECRET_MASK
    if isinstance(value, list):
        return "[" + ", ".join(repr_value(item) for item in value) + "]"
    if isinstance(value, BunDict):
        pairs = ", ".join(
            "%s: %s" % (repr_value(key), repr_value(item))
            for key, item in zip(value.keys(), value.values()))
        return "{" + pairs + "}"
    if isinstance(value, BunSet):
        items = ", ".join(repr_value(item) for item in value.values())
        return "{" + items + "}"
    if isinstance(value, BunFunction):
        return "<fn %s>" % value.name
    if isinstance(value, Builtin):
        return "<builtin %s>" % value.name
    return str(value)


def format_fstring_part(spec, conv, source_text, value):
    """Render one interpolated part of an f-string."""
    if source_text is not None:
        # The self-documenting form: f"{expr=}" prints the source first.
        return source_text + format_value(value, spec)
    if conv == "r":
        return repr_value(value)
    if conv == "s":
        return stringify(value)
    if spec is not None:
        return format_value(value, spec)
    return stringify(value)


def _group_digits(text):
    """Insert thousands separators into the integer part of `text`."""
    negative = text.startswith("-")
    if negative:
        text = text[1:]
    parts = text.split(".")
    integer = parts[0]
    groups = []
    while len(integer) > 3:
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    groups.insert(0, integer)
    joined = ",".join(groups)
    if negative:
        joined = "-" + joined
    if len(parts) > 1:
        joined = joined + "." + ".".join(parts[1:])
    return joined


def _pad(text, fill, align, width):
    if len(text) >= width:
        return text
    padding = width - len(text)
    if align == "<":
        return text + fill * padding
    if align == "^":
        left = padding // 2
        return fill * left + text + fill * (padding - left)
    if align == "=":
        return text
    return fill * padding + text


def format_value(value, spec):
    """Apply a Python-style format specification to a value.

    Supports the common subset: fill/align, sign, zero padding, width,
    thousands grouping, precision, and the `d f e g s x X o b c %` types.
    """
    if isinstance(value, BunSecret):
        return SECRET_MASK
    if spec is None or spec == "":
        return stringify(value)
    fill = " "
    align = None
    index = 0
    if len(spec) >= 2 and spec[1] in "<>^=":
        fill = spec[0]
        align = spec[1]
        index = 2
    elif spec[0] in "<>^=":
        align = spec[0]
        index = 1
    sign = ""
    if index < len(spec) and spec[index] in "+- ":
        sign = spec[index]
        index += 1
    if index < len(spec) and spec[index] == "#":
        index += 1
    zero = False
    if index < len(spec) and spec[index] == "0":
        zero = True
        index += 1
    width = 0
    while index < len(spec) and spec[index].isdigit():
        width = width * 10 + int(spec[index])
        index += 1
    grouping = False
    if index < len(spec) and spec[index] == ",":
        grouping = True
        index += 1
    precision = None
    if index < len(spec) and spec[index] == ".":
        index += 1
        precision = 0
        while index < len(spec) and spec[index].isdigit():
            precision = precision * 10 + int(spec[index])
            index += 1
    kind = ""
    if index < len(spec):
        kind = spec[index]
        index += 1
    if index != len(spec):
        raise BunRuntimeError("invalid format spec '%s'" % spec)

    negative = False
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, int):
        if kind in ("", "d"):
            text = str(abs(value))
        elif kind == "b":
            text = format(abs(value), "b")
        elif kind == "o":
            text = format(abs(value), "o")
        elif kind == "x":
            text = format(abs(value), "x")
        elif kind == "X":
            text = format(abs(value), "X")
        elif kind == "c":
            text = chr(value)
        elif kind in ("f", "e", "g", "%"):
            text = format(abs(value), kind if kind != "%" else "%")
            if kind == "%":
                text = "%.0f" % value if precision is None else "%.*f" % (precision, value)
            negative = value < 0
        elif kind == "s":
            text = str(value)
        else:
            raise BunRuntimeError("invalid format spec '%s'" % spec)
        if kind not in ("f", "e", "g", "%") and value < 0:
            negative = True
    elif isinstance(value, float):
        if kind in ("", "f"):
            text = "%.*f" % (6 if precision is None else precision, value)
        elif kind == "e":
            text = "%.*e" % (6 if precision is None else precision, value)
        elif kind == "g":
            text = "%.*g" % (6 if precision is None else precision, value)
        elif kind == "%":
            text = "%.*f%%" % (2 if precision is None else precision, value * 100)
        elif kind == "s":
            text = str(value)
        else:
            raise BunRuntimeError("invalid format spec '%s'" % spec)
        negative = text.startswith("-")
        if negative:
            text = text[1:]
    elif isinstance(value, str):
        if kind not in ("", "s"):
            raise BunRuntimeError("invalid format spec '%s'" % spec)
        text = value if precision is None else value[:precision]
    elif value is None:
        text = "null"
    else:
        text = stringify(value)

    if negative:
        prefix = "-"
    elif sign == "+":
        prefix = "+"
    elif sign == " ":
        prefix = " "
    else:
        prefix = ""

    if grouping and kind in ("", "d", "f", "e", "g"):
        text = _group_digits(text)

    if align is None and zero and kind in ("", "d", "f", "e", "g"):
        align = "="
        fill = "0"

    if align == "=":
        body = text
        sign_part = ""
        if body[:1] in "+-":
            sign_part = body[0]
            body = body[1:]
        total = len(sign_part) + len(body)
        if total < width:
            body = fill * (width - total) + body
        return sign_part + body

    text = prefix + text
    if align is None:
        align = "<" if isinstance(value, str) else ">"
    return _pad(text, fill, align, width)


def canonical_dump(value):
    """Render a value as canonical JSON with sorted dictionary keys."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return quote_string(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(canonical_dump(item) for item in value) + "]"
    if isinstance(value, BunSecret):
        return quote_string(SECRET_MASK)
    if isinstance(value, BunSet):
        return "[" + ", ".join(canonical_dump(item) for item in value.values()) + "]"
    if isinstance(value, BunDict):
        items = sorted(
            ((canonical_dump(key), canonical_dump(item))
             for key, item in zip(value.keys(), value.values())),
            key=lambda pair: pair[0])
        rendered = [key + ": " + item for key, item in items]
        return "{" + ", ".join(rendered) + "}"
    if isinstance(value, tuple):
        return "[" + ", ".join(canonical_dump(item) for item in value) + "]"
    if isinstance(value, dict):
        items = sorted(
            ((canonical_dump(key), canonical_dump(item))
             for key, item in value.items()),
            key=lambda pair: pair[0])
        rendered = [key + ": " + item for key, item in items]
        return "{" + ", ".join(rendered) + "}"
    raise BunRuntimeError("cannot canonicalize %s" % type(value).__name__)
