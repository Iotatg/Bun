"""Regenerate `selfhost/docs.bun` from the Python documentation registry.

The self-hosted front end ships its own copy of the documentation so it can
answer `bun doc` without the Python runtime. This script keeps both copies in
sync.

Usage:
    python3 tools/gen_docs.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bun import docs  # noqa: E402

HEADER = """// Docstrings for the Bun standard library.
//
// This file mirrors `bun/docs.py`; the parity suite checks that both
// registries describe the same symbols with the same content.

export let DOCS = {
"""

FOOTER = """}

export fn doc_names() -> list {
    var names = []
    for name in DOCS.keys() {
        names.push(name)
    }
    return names
}
"""


def bun_string(value):
    """Render a Python string as a Bun string literal."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return '"%s"' % escaped


def render():
    lines = [HEADER]
    for name in sorted(docs.DOCS):
        entry = docs.DOCS[name]
        lines.append("    %s: {\n" % bun_string(name))
        for key in ("signature", "summary", "details", "example"):
            if key not in entry:
                continue
            lines.append("        %s: %s,\n" % (bun_string(key), bun_string(entry[key])))
        lines.append("    },\n")
    lines.append(FOOTER)
    return "".join(lines)


def main():
    target = os.path.join(ROOT, "selfhost", "docs.bun")
    content = render()
    with open(target, "w") as handle:
        handle.write(content)
    print("wrote %s (%d symbols)" % (target, len(docs.DOCS)))


if __name__ == "__main__":
    main()
