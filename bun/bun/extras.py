"""The extra builtins of Bun: text, data and number helpers.

A second shelf of builtins beside the core: the regular expressions of
the machine, the CSV table format, a few pieces of arithmetic and the
bridge to the REA reverse engineer. Everything here is local — nothing
talks to the network.
"""

import csv
import io
import re
import time
import uuid as uuid_module
import zlib

from .dict import BunDict
from .errors import BunRuntimeError
from .values import Builtin
from . import sandbox


def _one(name, args):
    if len(args) != 1:
        raise BunRuntimeError("%s() expects exactly 1 argument" % name)


def _two(name, args):
    if len(args) != 2:
        raise BunRuntimeError("%s() expects exactly 2 arguments" % name)


def _string(name, args, index=0):
    if not isinstance(args[index], str):
        raise BunRuntimeError("%s() expects a string" % name)
    return args[index]


# --- regular expressions ---------------------------------------------------

def _regex_match(args):
    _two("regex_match", args)
    pattern = _string("regex_match", args, 0)
    text = _string("regex_match", args, 1)
    return re.fullmatch(pattern, text) is not None


def _regex_search(args):
    _two("regex_search", args)
    found = re.search(_string("regex_search", args, 0),
                      _string("regex_search", args, 1))
    return found.group(0) if found else None


def _regex_findall(args):
    _two("regex_findall", args)
    return re.findall(_string("regex_findall", args, 0),
                      _string("regex_findall", args, 1))


def _regex_replace(args):
    if len(args) != 3:
        raise BunRuntimeError("regex_replace() expects a pattern, a"
                              " replacement and a text")
    for index in range(3):
        _string("regex_replace", args, index)
    return re.sub(args[0], args[1], args[2])


def _regex_groups(args):
    _two("regex_groups", args)
    found = re.search(_string("regex_groups", args, 0),
                      _string("regex_groups", args, 1))
    return list(found.groups()) if found else None


# --- csv -------------------------------------------------------------------

def _csv_parse(args):
    _one("csv_parse", args)
    text = _string("csv_parse", args)
    rows = list(csv.reader(io.StringIO(text)))
    return [[cell for cell in row] for row in rows if row]


def _csv_build(args):
    _one("csv_build", args)
    if not isinstance(args[0], list):
        raise BunRuntimeError("csv_build() expects a list of rows")
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for row in args[0]:
        if not isinstance(row, list):
            raise BunRuntimeError("csv_build() expects a list of rows")
        cells = []
        for cell in row:
            if isinstance(cell, bool):
                cells.append("true" if cell else "false")
            elif isinstance(cell, (int, float)):
                cells.append(cell)
            elif isinstance(cell, str):
                cells.append(cell)
            else:
                cells.append(str(cell))
        writer.writerow(cells)
    return buffer.getvalue()


# --- text ------------------------------------------------------------------

def _html_escape(args):
    _one("html_escape", args)
    text = _string("html_escape", args)
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


def _html_unescape(args):
    _one("html_unescape", args)
    text = _string("html_unescape", args)
    for entity, char in (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'),
                         ("&#39;", "'"), ("&amp;", "&")):
        text = text.replace(entity, char)
    return text


def _split_lines(args):
    _one("split_lines", args)
    return _string("split_lines", args).splitlines()


def _slugify(args):
    _one("slugify", args)
    text = _string("slugify", args)
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_-]+", "-", text).strip("-")


# --- numbers ---------------------------------------------------------------

def _gcd(args):
    if len(args) != 2 or not all(isinstance(a, int) and not isinstance(a, bool)
                                 for a in args):
        raise BunRuntimeError("gcd() expects two integers")
    a, b = abs(args[0]), abs(args[1])
    while b:
        a, b = b, a % b
    return a


def _lcm(args):
    if len(args) != 2 or not all(isinstance(a, int) and not isinstance(a, bool)
                                 for a in args):
        raise BunRuntimeError("lcm() expects two integers")
    a, b = abs(args[0]), abs(args[1])
    if a == 0 or b == 0:
        return 0
    return a // _gcd(args) * b


def _factorial(args):
    _one("factorial", args)
    if not isinstance(args[0], int) or isinstance(args[0], bool) or args[0] < 0:
        raise BunRuntimeError("factorial() expects a non-negative integer")
    result = 1
    for value in range(2, args[0] + 1):
        result *= value
    return result


def _clamp(args):
    if len(args) != 3:
        raise BunRuntimeError("clamp() expects a value and two bounds")
    for value in args:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise BunRuntimeError("clamp() expects numbers")
    return max(args[1], min(args[2], args[0]))


def _sign(args):
    _one("sign", args)
    if not isinstance(args[0], (int, float)) or isinstance(args[0], bool):
        raise BunRuntimeError("sign() expects a number")
    return (args[0] > 0) - (args[0] < 0)


# --- time, data, ids ---------------------------------------------------------

def _now_ms(args):
    if args:
        raise BunRuntimeError("now_ms() expects no arguments")
    sandbox.check_clock()
    return int(time.time() * 1000)


def _uuid(args):
    if args:
        raise BunRuntimeError("uuid() expects no arguments")
    return str(uuid_module.uuid4())


def _crc32(args):
    _one("crc32", args)
    data = args[0]
    if isinstance(data, str):
        data = data.encode("utf-8")
    if not isinstance(data, list):
        raise BunRuntimeError("crc32() expects a string or a list of bytes")
    try:
        payload = bytes(data)
    except (TypeError, ValueError):
        raise BunRuntimeError("crc32() expects bytes in the range 0-255")
    return zlib.crc32(payload) & 0xFFFFFFFF


def _file_size(args):
    _one("file_size", args)
    import os
    try:
        return os.path.getsize(_string("file_size", args))
    except OSError:
        return None


# --- the reverse engineer ----------------------------------------------------

def _check_path(name, args, index=0):
    if not isinstance(args[index], str):
        raise BunRuntimeError("%s() expects a path" % name)
    return args[index]


def _rea_analyze(args):
    _one("rea_analyze", args)
    sandbox.check_exec()
    from . import reatool
    summary = reatool.analyze(_check_path("rea_analyze", args))
    answer = BunDict()
    for key, value in summary.items():
        answer.set(key, value)
    return answer


def _rea_exports(args):
    _one("rea_exports", args)
    sandbox.check_exec()
    from . import reatool
    return reatool.exports(_check_path("rea_exports", args))


def _rea_decompile(args):
    if len(args) != 2:
        raise BunRuntimeError("rea_decompile() expects a path and a procedure")
    sandbox.check_exec()
    from . import reatool
    return reatool.decompile(_check_path("rea_decompile", args),
                             _check_path("rea_decompile", args, 1))


EXTRA_SIGNATURES = {
    "regex_match": 2, "regex_search": 2, "regex_findall": 2,
    "regex_replace": 3, "regex_groups": 2,
    "csv_parse": 1, "csv_build": 1,
    "html_escape": 1, "html_unescape": 1, "split_lines": 1, "slugify": 1,
    "gcd": 2, "lcm": 2, "factorial": 1, "clamp": 3, "sign": 1,
    "now_ms": 0, "uuid": 0, "crc32": 1, "file_size": 1,
    "rea_analyze": 1, "rea_exports": 1, "rea_decompile": 2,
}

EXTRA_DOCS = {
    "regex_match": ("regex_match(pattern: string, text: string) -> bool",
                    "True when the whole text matches the pattern."),
    "regex_search": ("regex_search(pattern: string, text: string) -> string",
                     "The first piece of the text that matches, or null."),
    "regex_findall": ("regex_findall(pattern: string, text: string) -> list",
                      "Every piece of the text that matches."),
    "regex_replace": ("regex_replace(pattern: string, replacement: string, text: string) -> string",
                      "Replace every match of the pattern in the text."),
    "regex_groups": ("regex_groups(pattern: string, text: string) -> list",
                     "The capture groups of the first match, or null."),
    "csv_parse": ("csv_parse(text: string) -> list",
                  "The rows of a CSV table as lists of cells."),
    "csv_build": ("csv_build(rows: list) -> string",
                  "A CSV table built from rows of cells."),
    "html_escape": ("html_escape(text: string) -> string",
                    "Turn the markup characters of a text into entities."),
    "html_unescape": ("html_unescape(text: string) -> string",
                      "Turn the entities of a text back into characters."),
    "split_lines": ("split_lines(text: string) -> list",
                    "The lines of a text, without the line ends."),
    "slugify": ("slugify(text: string) -> string",
                "A text turned into a url-friendly slug."),
    "gcd": ("gcd(a: int, b: int) -> int", "The greatest common divisor."),
    "lcm": ("lcm(a: int, b: int) -> int", "The least common multiple."),
    "factorial": ("factorial(n: int) -> int", "The product of 1 to n."),
    "clamp": ("clamp(value: number, low: number, high: number) -> number",
              "The value kept inside the bounds."),
    "sign": ("sign(value: number) -> int", "-1, 0 or 1."),
    "now_ms": ("now_ms() -> int", "The time of the machine in milliseconds."),
    "uuid": ("uuid() -> string", "A fresh random UUID (version 4)."),
    "crc32": ("crc32(data: any) -> int", "The CRC-32 checksum of a text or bytes."),
    "file_size": ("file_size(path: string) -> int",
                  "The size of a file in bytes, or null when it is not there."),
    "rea_analyze": ("rea_analyze(path: string) -> dict",
                    "The overview REA builds of any binary."),
    "rea_exports": ("rea_exports(path: string) -> string",
                    "The exported functions REA finds in a binary."),
    "rea_decompile": ("rea_decompile(path: string, procedure: string) -> string",
                      "The decompiled code of one procedure of a binary."),
}


def register_extras(env):
    """Put the extra builtins into the environment of a program."""
    table = {
        "regex_match": _regex_match, "regex_search": _regex_search,
        "regex_findall": _regex_findall, "regex_replace": _regex_replace,
        "regex_groups": _regex_groups,
        "csv_parse": _csv_parse, "csv_build": _csv_build,
        "html_escape": _html_escape, "html_unescape": _html_unescape,
        "split_lines": _split_lines, "slugify": _slugify,
        "gcd": _gcd, "lcm": _lcm, "factorial": _factorial,
        "clamp": _clamp, "sign": _sign,
        "now_ms": _now_ms, "uuid": _uuid, "crc32": _crc32,
        "file_size": _file_size,
        "rea_analyze": _rea_analyze, "rea_exports": _rea_exports,
        "rea_decompile": _rea_decompile,
    }
    for name, function in table.items():
        env.define(name, Builtin(name, function), False)
