#!/usr/bin/env python3.11
"""Mirror bun/maturity.py into every registry the language requires.

`bun/maturity.py` is the single source of truth.  A builtin is only real
when all of these agree:

    bun/types.py            checker signatures (Python front end)
    bun/builtins.py         runtime registration
    bun/docs.py             the docs / API registry
    selfhost/docs.bun       the Bun-written docs mirror
    selfhost/checker.bun    checker signatures (Bun front end)
    bun/cbackend.py         LANGUAGE_BUILTINS name list

The script is idempotent: each generated region is delimited by a marker
and replaced, never appended twice.  Run `--check` to verify without
writing (used by the test suite).

    python3.11 tools/sync_maturity.py
    python3.11 tools/sync_maturity.py --check
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bun import maturity  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BEGIN = "BEGIN GENERATED MATURITY WAVE 1"
END = "END GENERATED MATURITY WAVE 1"

TYPES = {
    "int": "INT", "float": "FLOAT", "string": "STRING", "bool": "BOOL",
    "null": "NULL", "any": "ANY", "list": "LIST", "dict": "DICT",
    "fn": "FN", "secret": "SECRET", "set": "SET", "struct": "STRUCT",
    "enum": "ENUM", "result": "RESULT", "option": "OPTION",
}


def path(*parts):
    return os.path.join(ROOT, *parts)


def read(rel):
    with open(path(rel), "r", encoding="utf-8") as handle:
        return handle.read()


def write(rel, text):
    with open(path(rel), "w", encoding="utf-8") as handle:
        handle.write(text)


def strip_region(text, comment):
    """Remove a previously generated region, if present."""
    pattern = re.compile(
        r"[ \t]*" + re.escape(comment) + r"\s*" + re.escape(BEGIN)
        + r".*?" + re.escape(comment) + r"\s*" + re.escape(END) + r"[ \t]*\n",
        re.S)
    return pattern.sub("", text)


def region(body, comment, indent="    "):
    return (indent + comment + " " + BEGIN + "\n" + body
            + indent + comment + " " + END + "\n")


def insert_before(text, needle, block):
    """Put `block` immediately before the last `needle` in `text`."""
    index = text.rfind(needle)
    if index < 0:
        raise RuntimeError("could not find insertion point: %r" % needle)
    return text[:index] + block + text[index:]


# ---------------------------------------------------------------------------
# Generated bodies
# ---------------------------------------------------------------------------

def builtins_body():
    out = []
    for name in maturity.SIGNATURES:
        out.append(
            '    env.define("%s", Builtin("%s", '
            '_maturity.IMPLEMENTATIONS["%s"]), False)\n'
            % (name, name, name))
    return "".join(out)


def types_body():
    out = []
    for name, entries in maturity.SIGNATURES.items():
        (params, ret), = entries
        args = ", ".join(TYPES[p] for p in params)
        out.append('    "%s": [((%s), %s)],\n'
                   % (name, args + ("," if len(params) == 1 else ""),
                      TYPES[ret]))
    return "".join(out)


def checker_body():
    out = []
    for name, entries in maturity.SIGNATURES.items():
        (params, ret), = entries
        args = ", ".join('"%s"' % p for p in params)
        out.append('    "%s": [[[%s], "%s"]],\n'
                   % (name, args, ret))
    return "".join(out)


def signature_line(name, params, ret):
    args = ", ".join("arg%d: %s" % (i, p) for i, p in enumerate(params))
    return "%s(%s) -> %s" % (name, args, ret)


def docs_body():
    entries = maturity.docs_entries()
    out = []
    for name in sorted(maturity.SIGNATURES):
        (params, ret), = maturity.SIGNATURES[name]
        entry = entries[name]
        out.append('    "%s": {\n' % name)
        out.append('        "signature": %s,\n'
                   % py_string(signature_line(name, params, ret)))
        out.append('        "summary": %s,\n'
                   % py_string(entry["summary"]))
        if "example" in entry:
            out.append('        "example": %s,\n'
                       % py_string(entry["example"]))
        out.append('    },\n')
    return "".join(out)


def selfhost_docs_body():
    """The same entries as Bun source, written with JSON-compatible strings."""
    import json
    entries = maturity.docs_entries()
    out = []
    for name in sorted(maturity.SIGNATURES):
        (params, ret), = maturity.SIGNATURES[name]
        entry = entries[name]
        obj = {"signature": signature_line(name, params, ret),
               "summary": entry["summary"]}
        if "example" in entry:
            obj["example"] = entry["example"]
        rendered = json.dumps(obj, ensure_ascii=False, indent=4)
        rendered = rendered.replace("\n", "\n    ")
        out.append('    "%s": %s,\n' % (name, rendered))
    return "".join(out)


def cbackend_body():
    names = sorted(maturity.SIGNATURES)
    lines = []
    for i in range(0, len(names), 6):
        lines.append("    " + ", ".join('"%s"' % n for n in names[i:i + 6])
                     + ",\n")
    return "".join(lines)


def py_string(value):
    """A Python string literal, split only where a docs entry needs it."""
    import json
    return json.dumps(value, ensure_ascii=False)


# ---------------------------------------------------------------------------
# The six targets
# ---------------------------------------------------------------------------

def sync_builtins(check):
    rel = "bun/builtins.py"
    text = read(rel)
    text = strip_region(text, "#")
    if "from . import maturity as _maturity" not in text:
        anchor = "from .ops import type_name\n"
        if anchor not in text:
            raise RuntimeError("builtins.py import anchor missing")
        text = text.replace(anchor,
                            anchor + "from . import maturity as _maturity\n", 1)
    block = region(builtins_body(), "#")
    text = text + ("" if text.endswith("\n") else "\n") + block
    return finish(rel, text, check)


def sync_types(check):
    rel = "bun/types.py"
    text = strip_region(read(rel), "#")
    block = region(types_body(), "#")
    text = insert_before(text, "\n}\n\n\ndef is_known_type", block)
    return finish(rel, text, check)


def sync_py_docs(check):
    rel = "bun/docs.py"
    text = strip_region(read(rel), "#")
    block = region(docs_body(), "#")
    text = insert_before(text, "\n}\n\n\ndef doc_names", block)
    return finish(rel, text, check)


def sync_bun_docs(check):
    rel = "selfhost/docs.bun"
    text = strip_region(read(rel), "//")
    block = region(selfhost_docs_body(), "//")
    text = insert_before(text, "\n}\n\nexport fn doc_names", block)
    return finish(rel, text, check)


def sync_bun_checker(check):
    rel = "selfhost/checker.bun"
    text = strip_region(read(rel), "//")
    block = region(checker_body(), "//")
    text = insert_before(text, "\n}\n\nfn is_known_type", block)
    return finish(rel, text, check)


def sync_cbackend(check):
    rel = "bun/cbackend.py"
    text = strip_region(read(rel), "#")
    block = region(cbackend_body(), "#")
    # The end of LANGUAGE_BUILTINS is the first "])" after its declaration.
    start = text.index("LANGUAGE_BUILTINS = frozenset([")
    end = text.index("\n])", start)
    text = text[:end + 1] + block + text[end + 1:]
    return finish(rel, text, check)


def finish(rel, text, check):
    current = read(rel)
    if current == text:
        return rel, "unchanged"
    if check:
        return rel, "OUT OF SYNC"
    write(rel, text)
    return rel, "updated"


TARGETS = [
    sync_builtins, sync_types, sync_py_docs, sync_bun_docs,
    sync_bun_checker, sync_cbackend,
]


def main():
    check = "--check" in sys.argv[1:]
    results = [target(check) for target in TARGETS]
    for rel, status in results:
        print("%-28s %s" % (rel, status))
    bad = [rel for rel, status in results if status == "OUT OF SYNC"]
    print("builtins: %d   check: %s" % (len(maturity.SIGNATURES),
                                        "FAIL" if bad else "OK"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
