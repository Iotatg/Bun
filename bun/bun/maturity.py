"""The maturity standard library — capabilities that were missing on 2026-11-08.

This module is the SINGLE SOURCE OF TRUTH for a batch of standard-library
builtins.  `tools/sync_maturity.py` mirrors `SPECS` into the five places the
language requires (checker signatures, runtime registration, the docs
registry, the Bun-written docs mirror, and the C backend's name list), so
the registries cannot drift apart.

The naming rule: a builtin returns what Bun can hold — a string, an int, a
float, a bool, a list, or a BunDict.  The 0.3.0 wave adds two native value
types on top of that: `BunBytes` (a byte buffer that slices without copying)
and `BunErrorValue` (an error with a code that a program can inspect).
"""

import base64
import calendar
import datetime
import decimal
import gzip
import hashlib
import hmac
import http
import json
import mimetypes
import struct
import textwrap
import unicodedata
import urllib.parse
import uuid as _uuid
import zlib

from .dict import BunDict
from .errors import BunRuntimeError
from .values import BunBytes, BunErrorValue


# ---------------------------------------------------------------------------
# Small helpers, kept local so this module never imports `builtins` or
# `types` (that would be an import cycle: both import this module).
# ---------------------------------------------------------------------------

def _as_bytes(value, name):
    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, list):
        out = bytearray()
        for item in value:
            if not isinstance(item, int) or isinstance(item, bool) \
                    or item < 0 or item > 255:
                raise BunRuntimeError(
                    "%s() expects a list of byte values (0-255)" % name)
            out.append(item)
        return bytes(out)
    raise BunRuntimeError("%s() expects a string or a list of bytes" % name)


def _arity(name, args, count):
    if len(args) != count:
        raise BunRuntimeError("%s() expects %d argument(s), got %d"
                              % (name, count, len(args)))


def _text(name, value):
    if not isinstance(value, str):
        raise BunRuntimeError("%s() expects a string" % name)
    return value


def _number(name, value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise BunRuntimeError("%s() expects a number" % name)
    return value


def _map(items):
    result = BunDict()
    for key, value in items:
        result.set(key, value)
    return result


def _get(mapping, key, name):
    if isinstance(mapping, BunDict):
        value = mapping.get(key)
        if value is None:
            raise BunRuntimeError("%s(): key '%s' not found" % (name, key))
        return value
    if isinstance(mapping, dict):
        return mapping[key]
    raise BunRuntimeError("%s() expects a dict" % name)


def _to_bun(value):
    """Turn a Python value returned by a stdlib parser into a Bun value."""
    if isinstance(value, dict):
        return _map((k, _to_bun(v)) for k, v in value.items())
    if isinstance(value, list):
        return [_to_bun(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _deep_equal(a, b):
    if isinstance(a, BunDict) and isinstance(b, BunDict):
        if a.keys() != b.keys():
            return False
        return all(_deep_equal(_get(a, k, "json_equal"),
                               _get(b, k, "json_equal")) for k in a.keys())
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_deep_equal(x, y)
                                        for x, y in zip(a, b))
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    return a == b


# ---------------------------------------------------------------------------
# A. Encoding and digests
# ---------------------------------------------------------------------------

def _hmac_sha256_hex(args):
    _arity("hmac_sha256_hex", args, 2)
    key = _as_bytes(args[0], "hmac_sha256_hex")
    msg = _as_bytes(args[1], "hmac_sha256_hex")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def _hmac_sha512_hex(args):
    _arity("hmac_sha512_hex", args, 2)
    key = _as_bytes(args[0], "hmac_sha512_hex")
    msg = _as_bytes(args[1], "hmac_sha512_hex")
    return hmac.new(key, msg, hashlib.sha512).hexdigest()


def _base64url_encode(args):
    _arity("base64url_encode", args, 1)
    data = _as_bytes(args[0], "base64url_encode")
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _base64url_decode(args):
    _arity("base64url_decode", args, 1)
    text = _text("base64url_decode", args[0])
    try:
        raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except Exception as error:
        raise BunRuntimeError("base64url_decode() failed: %s" % error)
    return list(raw)


def _hex_encode(args):
    _arity("hex_encode", args, 1)
    return _as_bytes(args[0], "hex_encode").hex()


def _hex_decode(args):
    _arity("hex_decode", args, 1)
    text = _text("hex_decode", args[0])
    try:
        return list(bytes.fromhex(text))
    except ValueError as error:
        raise BunRuntimeError("hex_decode() failed: %s" % error)


def _gzip_compress(args):
    _arity("gzip_compress", args, 1)
    data = _as_bytes(args[0], "gzip_compress")
    return list(gzip.compress(data, mtime=0))


def _sha512_hex(args):
    _arity("sha512_hex", args, 1)
    return hashlib.sha512(_as_bytes(args[0], "sha512_hex")).hexdigest()


def _blake2b_hex(args):
    _arity("blake2b_hex", args, 1)
    return hashlib.blake2b(_as_bytes(args[0], "blake2b_hex")).hexdigest()


def _timing_safe_equal(args):
    _arity("timing_safe_equal", args, 2)
    a = _text("timing_safe_equal", args[0])
    b = _text("timing_safe_equal", args[1])
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# ---------------------------------------------------------------------------
# B. Time and date.  All functions are pure and UTC by default: a program
# that formats an epoch gets the same answer on every machine.
# ---------------------------------------------------------------------------

_UTC = datetime.timezone.utc


def _epoch(name, value):
    value = _number(name, value)
    try:
        return datetime.datetime.fromtimestamp(value, _UTC)
    except (OverflowError, OSError, ValueError) as error:
        raise BunRuntimeError("%s(): bad epoch: %s" % (name, error))


def _time_format(args):
    _arity("time_format", args, 2)
    moment = _epoch("time_format", args[0])
    pattern = _text("time_format", args[1])
    try:
        return moment.strftime(pattern)
    except ValueError as error:
        raise BunRuntimeError("time_format() failed: %s" % error)


def _time_parse_iso(args):
    _arity("time_parse_iso", args, 1)
    text = _text("time_parse_iso", args[0])
    try:
        cleaned = text.replace("Z", "+00:00") if text.endswith("Z") else text
        moment = datetime.datetime.fromisoformat(cleaned)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=_UTC)
        return moment.timestamp()
    except ValueError as error:
        raise BunRuntimeError("time_parse_iso() failed: %s" % error)


def _time_iso(args):
    _arity("time_iso", args, 1)
    return _epoch("time_iso", args[0]).strftime("%Y-%m-%dT%H:%M:%SZ")


def _time_parts(args):
    _arity("time_parts", args, 1)
    m = _epoch("time_parts", args[0])
    return _map((k, getattr(m, k)) for k in
                ("year", "month", "day", "hour", "minute", "second"))


def _time_add(args):
    _arity("time_add", args, 2)
    return _number("time_add", args[0]) + _number("time_add", args[1])


def _time_diff(args):
    _arity("time_diff", args, 2)
    return _number("time_diff", args[0]) - _number("time_diff", args[1])


def _time_weekday(args):
    _arity("time_weekday", args, 1)
    return _epoch("time_weekday", args[0]).isoweekday()


def _time_is_leap(args):
    _arity("time_is_leap", args, 1)
    year = _number("time_is_leap", args[0])
    return calendar.isleap(int(year))


def _time_days_in_month(args):
    _arity("time_days_in_month", args, 2)
    year = int(_number("time_days_in_month", args[0]))
    month = int(_number("time_days_in_month", args[1]))
    if month < 1 or month > 12:
        raise BunRuntimeError("time_days_in_month(): month must be 1-12")
    return calendar.monthrange(year, month)[1]


def _time_epoch_ms(args):
    _arity("time_epoch_ms", args, 1)
    return int(_number("time_epoch_ms", args[0]) * 1000)


# ---------------------------------------------------------------------------
# I. Text
# ---------------------------------------------------------------------------

def _format(args):
    _arity("format", args, 2)
    template = _text("format", args[0])
    if not isinstance(args[1], BunDict):
        raise BunRuntimeError("format() expects a dict of values")
    values = args[1]
    out = []
    index = 0
    while index < len(template):
        if template[index] == "{":
            end = template.find("}", index + 1)
            if end != -1:
                key = template[index + 1:end]
                value = values.get(key)
                if value is None:
                    raise BunRuntimeError(
                        "format(): no value for '%s'" % key)
                out.append(_stringify(value))
                index = end + 1
                continue
        out.append(template[index])
        index += 1
    return "".join(out)


def _stringify(value):
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, str):
        return value
    return str(value)


def _pad_left(args):
    _arity("pad_left", args, 3)
    text = _text("pad_left", args[0])
    width = int(_number("pad_left", args[1]))
    fill = _text("pad_left", args[2])
    if not fill:
        raise BunRuntimeError("pad_left() expects a non-empty fill")
    return text.rjust(width, fill[0])


def _pad_right(args):
    _arity("pad_right", args, 3)
    text = _text("pad_right", args[0])
    width = int(_number("pad_right", args[1]))
    fill = _text("pad_right", args[2])
    if not fill:
        raise BunRuntimeError("pad_right() expects a non-empty fill")
    return text.ljust(width, fill[0])


def _center(args):
    _arity("center", args, 3)
    text = _text("center", args[0])
    width = int(_number("center", args[1]))
    fill = _text("center", args[2])
    if not fill:
        raise BunRuntimeError("center() expects a non-empty fill")
    return text.center(width, fill[0])


def _title_case(args):
    _arity("title_case", args, 1)
    return _text("title_case", args[0]).title()


def _swap_case(args):
    _arity("swap_case", args, 1)
    return _text("swap_case", args[0]).swapcase()


def _truncate(args):
    _arity("truncate", args, 2)
    text = _text("truncate", args[0])
    limit = int(_number("truncate", args[1]))
    if limit < 3:
        raise BunRuntimeError("truncate() expects a limit of at least 3")
    return text if len(text) <= limit else text[:limit - 3] + "..."


def _word_wrap(args):
    _arity("word_wrap", args, 2)
    text = _text("word_wrap", args[0])
    width = int(_number("word_wrap", args[1]))
    if width < 1:
        raise BunRuntimeError("word_wrap() expects a positive width")
    return textwrap.fill(text, width=width)


def _unicode_normalize(args):
    _arity("unicode_normalize", args, 1)
    return unicodedata.normalize("NFC", _text("unicode_normalize", args[0]))


def _levenshtein(args):
    _arity("levenshtein", args, 2)
    a = _text("levenshtein", args[0])
    b = _text("levenshtein", args[1])
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


# ---------------------------------------------------------------------------
# F. URLs, headers and the shapes of the web
# ---------------------------------------------------------------------------

def _url_parse(args):
    _arity("url_parse", args, 1)
    parts = urllib.parse.urlsplit(_text("url_parse", args[0]))
    return _map((
        ("scheme", parts.scheme), ("host", parts.hostname or ""),
        ("port", parts.port or 0), ("path", parts.path),
        ("query", parts.query), ("fragment", parts.fragment),
    ))


def _url_build(args):
    _arity("url_build", args, 1)
    p = args[0]
    scheme = _get(p, "scheme", "url_build")
    host = _get(p, "host", "url_build")
    port = _get(p, "port", "url_build")
    path = _get(p, "path", "url_build")
    query = _get(p, "query", "url_build")
    fragment = _get(p, "fragment", "url_build")
    netloc = str(host) + (":" + str(port) if port else "")
    return urllib.parse.urlunsplit((str(scheme), netloc, str(path),
                                    str(query), str(fragment)))


def _query_parse(args):
    _arity("query_parse", args, 1)
    text = _text("query_parse", args[0])
    result = []
    for piece in text.split("&"):
        if not piece:
            continue
        key, _, value = piece.partition("=")
        result.append((urllib.parse.unquote_plus(key),
                       urllib.parse.unquote_plus(value)))
    return _map(result)


def _query_build(args):
    _arity("query_build", args, 1)
    if not isinstance(args[0], BunDict):
        raise BunRuntimeError("query_build() expects a dict")
    return "&".join(
        "%s=%s" % (urllib.parse.quote_plus(str(k)),
                   urllib.parse.quote_plus(str(_get(args[0], k,
                                                    "query_build"))))
        for k in args[0].keys())


def _status_text(args):
    _arity("status_text", args, 1)
    code = int(_number("status_text", args[0]))
    try:
        return http.HTTPStatus(code).phrase
    except ValueError:
        return "Unknown"


def _cookie_parse(args):
    _arity("cookie_parse", args, 1)
    result = []
    for piece in _text("cookie_parse", args[0]).split(";"):
        key, sep, value = piece.strip().partition("=")
        if sep:
            result.append((key.strip(), value.strip()))
    return _map(result)


def _mime_from_path(args):
    _arity("mime_from_path", args, 1)
    guess = mimetypes.guess_type(_text("mime_from_path", args[0]))[0]
    return guess or "application/octet-stream"


def _status_class(args):
    _arity("status_class", args, 1)
    return int(_number("status_class", args[0])) // 100


def _percent_encode(args):
    _arity("percent_encode", args, 1)
    return urllib.parse.quote(_text("percent_encode", args[0]), safe="")


def _header_parse(args):
    _arity("header_parse", args, 1)
    result = []
    for line in _text("header_parse", args[0]).splitlines():
        key, sep, value = line.partition(":")
        if sep:
            result.append((key.strip(), value.strip()))
    return _map(result)


# ---------------------------------------------------------------------------
# G. Data and formats
# ---------------------------------------------------------------------------

_STRUCT_CHARS = frozenset("<>=!@bBhHiIlLqQnNfdspP")


def _struct_pack(args):
    _arity("struct_pack", args, 2)
    fmt = _text("struct_pack", args[0])
    if any(c not in _STRUCT_CHARS for c in fmt):
        raise BunRuntimeError("struct_pack(): unsupported format")
    value = int(_number("struct_pack", args[1]))
    try:
        return list(struct.pack(fmt, value))
    except struct.error as error:
        raise BunRuntimeError("struct_pack() failed: %s" % error)


def _struct_unpack(args):
    _arity("struct_unpack", args, 2)
    fmt = _text("struct_unpack", args[0])
    if any(c not in _STRUCT_CHARS for c in fmt):
        raise BunRuntimeError("struct_unpack(): unsupported format")
    try:
        return struct.unpack(fmt, bytes(_as_bytes(args[1],
                                                  "struct_unpack")))[0]
    except struct.error as error:
        raise BunRuntimeError("struct_unpack() failed: %s" % error)


def _toml_parse(args):
    _arity("toml_parse", args, 1)
    import tomllib
    try:
        return _to_bun(tomllib.loads(_text("toml_parse", args[0])))
    except Exception as error:
        raise BunRuntimeError("toml_parse() failed: %s" % error)


def _json_pointer(args):
    _arity("json_pointer", args, 2)
    current = args[0]
    for part in _text("json_pointer", args[1]).lstrip("/").split("/"):
        if part == "":
            continue
        if isinstance(current, BunDict):
            current = _get(current, part.replace("~1", "/")
                           .replace("~0", "~"), "json_pointer")
        elif isinstance(current, list):
            current = current[int(part)]
        else:
            raise BunRuntimeError("json_pointer(): path walks a scalar")
    return current


def _json_equal(args):
    _arity("json_equal", args, 2)
    return _deep_equal(args[0], args[1])


def _decimal_add(args):
    _arity("decimal_add", args, 2)
    try:
        result = (decimal.Decimal(_text("decimal_add", args[0])) +
                  decimal.Decimal(_text("decimal_add", args[1])))
        return format(result, "f")
    except decimal.InvalidOperation as error:
        raise BunRuntimeError("decimal_add() failed: %s" % error)


def _bitset_new(args):
    _arity("bitset_new", args, 1)
    return _map((("size", int(_number("bitset_new", args[0]))),
                 ("bits", 0)))


def _bitset_set(args):
    _arity("bitset_set", args, 2)
    bitset = args[0]
    index = int(_number("bitset_set", args[1]))
    old = int(_get(bitset, "bits", "bitset_set"))
    bitset.set("bits", old | (1 << index))
    return bitset


def _bitset_get(args):
    _arity("bitset_get", args, 2)
    index = int(_number("bitset_get", args[1]))
    bits = int(_get(args[0], "bits", "bitset_get"))
    return bool(bits & (1 << index))


def _ordered_dict_new(args):
    _arity("ordered_dict_new", args, 0)
    return BunDict()


def _ordered_dict_keys(args):
    _arity("ordered_dict_keys", args, 1)
    if not isinstance(args[0], BunDict):
        raise BunRuntimeError("ordered_dict_keys() expects a dict")
    return args[0].keys()


def _uuid_v4(args):
    _arity("uuid_v4", args, 0)
    return str(_uuid.uuid4())


_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _ulid(args):
    _arity("ulid", args, 0)
    import os
    stamp = int(datetime.datetime.now(_UTC).timestamp() * 1000)
    value = (stamp << 80) | int.from_bytes(os.urandom(10), "big")
    out = []
    for _ in range(26):
        out.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(out))


# ---------------------------------------------------------------------------
# H. Semantic versions (the package manager's own arithmetic)
# ---------------------------------------------------------------------------

def _semver(value, name):
    """Parse a semantic version into a comparable tuple."""
    text = _text(name, value)
    main = text.split("-", 1)[0].split("+", 1)[0]
    parts = main.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise BunRuntimeError(
            "%s() expects a semantic version like '1.2.3'" % name)
    return tuple(int(p) for p in parts)


def _semver_compare(args):
    _arity("semver_compare", args, 2)
    left = _semver(args[0], "semver_compare")
    right = _semver(args[1], "semver_compare")
    return (left > right) - (left < right)


def _semver_satisfies(args):
    _arity("semver_satisfies", args, 2)
    version = _semver(args[0], "semver_satisfies")
    spec = _text("semver_satisfies", args[1]).strip()
    if spec in ("*", ""):
        return True
    for prefix, operator in ((">=", "ge"), ("<=", "le"), (">", "gt"),
                             ("<", "lt"), ("=", "eq"), ("^", "caret"),
                             ("~", "tilde")):
        if not spec.startswith(prefix):
            continue
        base = _semver(spec[len(prefix):].strip(), "semver_satisfies")
        if operator == "ge":
            return version >= base
        if operator == "le":
            return version <= base
        if operator == "gt":
            return version > base
        if operator == "lt":
            return version < base
        if operator == "eq":
            return version == base
        if operator == "caret":
            if base[0] == 0:
                return version[0] == 0 and version >= base
            return version[0] == base[0] and version >= base
        return version[:2] == base[:2] and version >= base
    raise BunRuntimeError(
        "semver_satisfies() cannot read the range '%s'" % spec)


# ---------------------------------------------------------------------------
# Wave 2: native bytes values and typed error values.
#
# A byte buffer is NOT a list of integers.  It owns a memoryview, so a slice
# hands out a second view on the same bytes: no list is built and no payload
# is copied.  An error is likewise a first-class value with a code; `throw`
# raises it, but the value can be held, compared and inspected first.
# ---------------------------------------------------------------------------

def _as_bun_bytes(value, name):
    if not isinstance(value, BunBytes):
        raise BunRuntimeError("%s() expects a bytes value" % name)
    return value


def _bytes_from_list(args):
    _arity("bytes_from_list", args, 1)
    values = args[0]
    if not isinstance(values, list):
        raise BunRuntimeError("bytes_from_list() expects a list of byte values")
    out = bytearray()
    for item in values:
        if not isinstance(item, int) or isinstance(item, bool):
            raise BunRuntimeError("bytes_from_list() expects integers 0..255")
        if item < 0 or item > 255:
            raise BunRuntimeError("bytes_from_list() expects integers 0..255")
        out.append(item)
    return BunBytes(bytes(out))


def _bytes_to_list(args):
    _arity("bytes_to_list", args, 1)
    data = _as_bun_bytes(args[0], "bytes_to_list")
    return [int(byte) for byte in data.data]


def _bytes_len(args):
    _arity("bytes_len", args, 1)
    return len(_as_bun_bytes(args[0], "bytes_len").data)


def _bytes_concat(args):
    _arity("bytes_concat", args, 2)
    left = _as_bun_bytes(args[0], "bytes_concat")
    right = _as_bun_bytes(args[1], "bytes_concat")
    return BunBytes(bytes(left.data) + bytes(right.data))


def _fail_with(args):
    """Build a typed error value.  Raising it is a separate act (`throw`)."""
    _arity("fail_with", args, 1)
    return BunErrorValue(_text("fail_with", args[0]))


def _fail_with_message(args):
    _arity("fail_with_message", args, 2)
    return BunErrorValue(_text("fail_with_message", args[0]),
                         _text("fail_with_message", args[1]))


def _as_error(args, name):
    _arity(name, args, 1)
    if not isinstance(args[0], BunErrorValue):
        raise BunRuntimeError("%s() expects an error value" % name)
    return args[0]


def _error_code(args):
    return _as_error(args, "error_code").code


def _error_message(args):
    return _as_error(args, "error_message").message


def _is_error(args):
    _arity("is_error", args, 1)
    return isinstance(args[0], BunErrorValue)


# ---------------------------------------------------------------------------
# The registry.  One entry per capability; `sync_maturity.py` mirrors it.
# ---------------------------------------------------------------------------

# name -> (params tuple, return type)  [type names as strings, no import]
SIGNATURES = {
    "hmac_sha256_hex": ((("string", "string"), "string"),),
    "hmac_sha512_hex": ((("string", "string"), "string"),),
    "base64url_encode": ((("any",), "string"),),
    "base64url_decode": ((("string",), "list"),),
    "hex_encode": ((("any",), "string"),),
    "hex_decode": ((("string",), "list"),),
    "gzip_compress": ((("any",), "list"),),
    "sha512_hex": ((("any",), "string"),),
    "blake2b_hex": ((("any",), "string"),),
    "timing_safe_equal": ((("string", "string"), "bool"),),

    "time_format": ((("float", "string"), "string"),),
    "time_parse_iso": ((("string",), "float"),),
    "time_iso": ((("float",), "string"),),
    "time_parts": ((("float",), "dict"),),
    "time_add": ((("float", "float"), "float"),),
    "time_diff": ((("float", "float"), "float"),),
    "time_weekday": ((("float",), "int"),),
    "time_is_leap": ((("int",), "bool"),),
    "time_days_in_month": ((("int", "int"), "int"),),
    "time_epoch_ms": ((("float",), "int"),),

    "format": ((("string", "dict"), "string"),),
    "pad_left": ((("string", "int", "string"), "string"),),
    "pad_right": ((("string", "int", "string"), "string"),),
    "center": ((("string", "int", "string"), "string"),),
    "title_case": ((("string",), "string"),),
    "swap_case": ((("string",), "string"),),
    "truncate": ((("string", "int"), "string"),),
    "word_wrap": ((("string", "int"), "string"),),
    "unicode_normalize": ((("string",), "string"),),
    "levenshtein": ((("string", "string"), "int"),),

    "url_parse": ((("string",), "dict"),),
    "url_build": ((("dict",), "string"),),
    "query_parse": ((("string",), "dict"),),
    "query_build": ((("dict",), "string"),),
    "status_text": ((("int",), "string"),),
    "cookie_parse": ((("string",), "dict"),),
    "mime_from_path": ((("string",), "string"),),
    "status_class": ((("int",), "int"),),
    "percent_encode": ((("string",), "string"),),
    "header_parse": ((("string",), "dict"),),

    "struct_pack": ((("string", "int"), "list"),),
    "struct_unpack": ((("string", "list"), "int"),),
    "toml_parse": ((("string",), "dict"),),
    "json_pointer": ((("any", "string"), "any"),),
    "json_equal": ((("any", "any"), "bool"),),
    "decimal_add": ((("string", "string"), "string"),),
    "bitset_new": ((("int",), "dict"),),
    "bitset_set": ((("dict", "int"), "dict"),),
    "bitset_get": ((("dict", "int"), "bool"),),
    "ordered_dict_new": (((), "dict"),),
    "ordered_dict_keys": ((("dict",), "list"),),
    "uuid_v4": (((), "string"),),
    "ulid": (((), "string"),),
    "semver_compare": ((("string", "string"), "int"),),
    "semver_satisfies": ((("string", "string"), "bool"),),

    "bytes_from_list": ((("list",), "bytes"),),
    "bytes_to_list": ((("bytes",), "list"),),
    "bytes_len": ((("bytes",), "int"),),
    "bytes_concat": ((("bytes", "bytes"), "bytes"),),
    "fail_with": ((("string",), "error"),),
    "fail_with_message": ((("string", "string"), "error"),),
    "error_code": ((("error",), "string"),),
    "error_message": ((("error",), "string"),),
    "is_error": ((("any",), "bool"),),
}

IMPLEMENTATIONS = {
    "hmac_sha256_hex": _hmac_sha256_hex,
    "hmac_sha512_hex": _hmac_sha512_hex,
    "base64url_encode": _base64url_encode,
    "base64url_decode": _base64url_decode,
    "hex_encode": _hex_encode,
    "hex_decode": _hex_decode,
    "gzip_compress": _gzip_compress,
    "sha512_hex": _sha512_hex,
    "blake2b_hex": _blake2b_hex,
    "timing_safe_equal": _timing_safe_equal,

    "time_format": _time_format,
    "time_parse_iso": _time_parse_iso,
    "time_iso": _time_iso,
    "time_parts": _time_parts,
    "time_add": _time_add,
    "time_diff": _time_diff,
    "time_weekday": _time_weekday,
    "time_is_leap": _time_is_leap,
    "time_days_in_month": _time_days_in_month,
    "time_epoch_ms": _time_epoch_ms,

    "format": _format,
    "pad_left": _pad_left,
    "pad_right": _pad_right,
    "center": _center,
    "title_case": _title_case,
    "swap_case": _swap_case,
    "truncate": _truncate,
    "word_wrap": _word_wrap,
    "unicode_normalize": _unicode_normalize,
    "levenshtein": _levenshtein,

    "url_parse": _url_parse,
    "url_build": _url_build,
    "query_parse": _query_parse,
    "query_build": _query_build,
    "status_text": _status_text,
    "cookie_parse": _cookie_parse,
    "mime_from_path": _mime_from_path,
    "status_class": _status_class,
    "percent_encode": _percent_encode,
    "header_parse": _header_parse,

    "struct_pack": _struct_pack,
    "struct_unpack": _struct_unpack,
    "toml_parse": _toml_parse,
    "json_pointer": _json_pointer,
    "json_equal": _json_equal,
    "decimal_add": _decimal_add,
    "bitset_new": _bitset_new,
    "bitset_set": _bitset_set,
    "bitset_get": _bitset_get,
    "ordered_dict_new": _ordered_dict_new,
    "ordered_dict_keys": _ordered_dict_keys,
    "uuid_v4": _uuid_v4,
    "ulid": _ulid,
    "semver_compare": _semver_compare,
    "semver_satisfies": _semver_satisfies,

    "bytes_from_list": _bytes_from_list,
    "bytes_to_list": _bytes_to_list,
    "bytes_len": _bytes_len,
    "bytes_concat": _bytes_concat,
    "fail_with": _fail_with,
    "fail_with_message": _fail_with_message,
    "error_code": _error_code,
    "error_message": _error_message,
    "is_error": _is_error,
}

SUMMARIES = {
    "hmac_sha256_hex": "Return the hex HMAC-SHA256 of a message under a key.",
    "hmac_sha512_hex": "Return the hex HMAC-SHA512 of a message under a key.",
    "base64url_encode": "Encode bytes as unpadded base64url text.",
    "base64url_decode": "Decode unpadded base64url text into byte values.",
    "hex_encode": "Encode bytes as lowercase hexadecimal text.",
    "hex_decode": "Decode hexadecimal text into byte values.",
    "gzip_compress": "Compress bytes into a deterministic gzip stream.",
    "sha512_hex": "Return the hex SHA-512 digest of some bytes.",
    "blake2b_hex": "Return the hex BLAKE2b digest of some bytes.",
    "timing_safe_equal": "Compare two strings in time independent of their content.",

    "time_format": "Format a UTC epoch with a strftime pattern.",
    "time_parse_iso": "Parse an ISO-8601 timestamp into a UTC epoch.",
    "time_iso": "Format a UTC epoch as an ISO-8601 timestamp.",
    "time_parts": "Break a UTC epoch into year, month, day, hour, minute, second.",
    "time_add": "Add seconds to an epoch.",
    "time_diff": "Return the number of seconds between two epochs.",
    "time_weekday": "Return the ISO weekday of a UTC epoch (Monday is 1).",
    "time_is_leap": "Say whether a year is a leap year.",
    "time_days_in_month": "Return the number of days in a month.",
    "time_epoch_ms": "Convert an epoch in seconds into milliseconds.",

    "format": "Substitute {name} placeholders from a dict.",
    "pad_left": "Pad a string on the left to a width.",
    "pad_right": "Pad a string on the right to a width.",
    "center": "Centre a string within a width.",
    "title_case": "Capitalise the first letter of every word.",
    "swap_case": "Swap upper and lower case letters.",
    "truncate": "Shorten a string with an ellipsis.",
    "word_wrap": "Wrap a string at word boundaries.",
    "unicode_normalize": "Normalise a string to Unicode NFC.",
    "levenshtein": "Return the edit distance between two strings.",

    "url_parse": "Split a URL into scheme, host, port, path, query and fragment.",
    "url_build": "Build a URL from the parts url_parse returns.",
    "query_parse": "Parse a query string into a dict.",
    "query_build": "Build a query string from a dict.",
    "status_text": "Return the reason phrase of an HTTP status code.",
    "cookie_parse": "Parse a Cookie header into a dict.",
    "mime_from_path": "Guess a MIME type from a file name.",
    "status_class": "Return the class of an HTTP status code.",
    "percent_encode": "Percent-encode every byte that is not unreserved.",
    "header_parse": "Parse a block of HTTP headers into a dict.",

    "struct_pack": "Pack one integer with a struct format into byte values.",
    "struct_unpack": "Unpack byte values with a struct format into an integer.",
    "toml_parse": "Parse TOML text into a dict.",
    "json_pointer": "Follow an RFC-6901 pointer into a parsed JSON value.",
    "json_equal": "Compare two parsed JSON values by structure.",
    "decimal_add": "Add two decimal strings exactly, without float error.",
    "bitset_new": "Make a bitset of a given size.",
    "bitset_set": "Set a bit and return the bitset.",
    "bitset_get": "Say whether a bit is set.",
    "ordered_dict_new": "Make a dict that keeps insertion order.",
    "ordered_dict_keys": "Return the keys of a dict in insertion order.",
    "uuid_v4": "Generate a random version-4 UUID.",
    "ulid": "Generate a sortable 26-character ULID.",
    "semver_compare": "Compare two semantic versions, returning -1, 0 or 1.",
    "semver_satisfies": "Check a version against a ^, ~, >=, >, <=, < or = range.",
    "bytes_from_list": "Build a native bytes value from a list of byte values.",
    "bytes_to_list": "Read the byte values of a native bytes value as a list.",
    "bytes_len": "Return the number of bytes in a native bytes value.",
    "bytes_concat": "Join two native bytes values into a new one.",
    "fail_with": "Build a typed error value with a code; `throw` raises it.",
    "fail_with_message": "Build a typed error value with a code and a message.",
    "error_code": "Return the code of a typed error value.",
    "error_message": "Return the message of a typed error value.",
    "is_error": "Report whether a value is a typed error value.",
}

# Every probe in tools/maturity_probe.py that this batch satisfies, used by
# the sync script to build a runnable documentation example.
EXAMPLES = {
    "hmac_sha256_hex": 'print(hmac_sha256_hex("key", "msg"))',
    "sha512_hex": 'print(len(sha512_hex("abc")))',
    "hex_encode": 'print(hex_encode([72, 105]))',
    "hex_decode": 'print(hex_decode("4869"))',
    "gzip_compress": 'print(utf8_string(gzip_decompress(gzip_compress("hi"))))',
    "timing_safe_equal": 'print(timing_safe_equal("a", "a"))',
    "time_format": 'print(time_format(0, "%Y-%m-%d"))',
    "time_iso": 'print(time_iso(0))',
    "time_parts": 'print(time_parts(0)["year"])',
    "time_is_leap": 'print(time_is_leap(2024))',
    "title_case": 'print(title_case("hello world"))',
    "swap_case": 'print(swap_case("AbC"))',
    "levenshtein": 'print(levenshtein("kitten", "sitting"))',
    "center": 'print(center("a", 5, "-"))',
    "url_parse": 'print(url_parse("https://example.com/a")["host"])',
    "status_text": 'print(status_text(404))',
    "mime_from_path": 'print(mime_from_path("a.png"))',
    "percent_encode": 'print(percent_encode("a b"))',
    "decimal_add": 'print(decimal_add("0.1", "0.2"))',
    "json_equal": 'print(json_equal(json_parse("[1,2]"), json_parse("[1,2]")))',
    "bitset_get": 'print(bitset_get(bitset_set(bitset_new(8), 3), 3))',
    "uuid_v4": 'print(len(uuid_v4()))',
    "ulid": 'print(len(ulid()))',
    "semver_compare": 'print(semver_compare("1.10.0", "1.2.0"))',
    "semver_satisfies": 'print(semver_satisfies("1.2.3", "^1.0.0"))',
    "bytes_from_list": 'print(type_of(bytes_from_list([1, 2, 3])))',
    "bytes_to_list": 'print(bytes_to_list(bytes_from_list([1, 2, 3])))',
    "bytes_len": 'print(bytes_len(bytes_from_list([1, 2, 3])))',
    "bytes_concat": 'print(bytes_len(bytes_concat(bytes_from_list([1]), bytes_from_list([2, 3]))))',
    "fail_with": 'print(error_code(fail_with("E_NOPE")))',
    "fail_with_message": 'print(error_message(fail_with_message("E_X", "bad input")))',
    "error_code": 'print(error_code(fail_with("E_NOPE")))',
    "error_message": 'print(error_message(fail_with_message("E_X", "bad input")))',
    "is_error": 'print(is_error(fail_with("E_NOPE")))',
}


def signature_strings():
    """The signature line `bun doc` shows, derived from SIGNATURES."""
    out = {}
    for name, entries in SIGNATURES.items():
        (params, ret), = entries
        rendered = ", ".join(params)
        out[name] = "%s(%s) -> %s" % (name, rendered, ret)
    return out


def docs_entries():
    """The docs registry entries, derived from the same table."""
    sigs = signature_strings()
    out = {}
    for name in SIGNATURES:
        entry = {"signature": sigs[name], "summary": SUMMARIES[name]}
        if name in EXAMPLES:
            entry["example"] = EXAMPLES[name] + "\n"
        out[name] = entry
    return out


# `zlib` is imported for the gzip helpers' parity with the existing
# decompressor; keep the reference explicit for readers of the registry.
assert zlib is not None
