#!/usr/bin/env python3
"""Report the type checker diagnostics of a Bun file and its imports.

Usage: python3 tools/check.py path/to/file.bun [...]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bun.checker import Checker
from bun.errors import BunError
from bun.lexer import Lexer
from bun.parser import Parser


def check(path):
    with open(path, "r") as handle:
        source = handle.read()
    program = Parser(Lexer(source).tokenize()).parse()
    try:
        Checker().check(program, base_dir=os.path.dirname(os.path.abspath(path)))
    except BunError as error:
        return str(error)
    return None


def main():
    paths = sys.argv[1:]
    if not paths:
        paths = ["ankita-music/bot"]
    failures = 0
    for path in paths:
        if os.path.isdir(path):
            for root, dirs, names in os.walk(path):
                dirs[:] = [d for d in dirs if d not in ("scratch", "__pycache__")]
                for name in sorted(names):
                    if name.endswith(".bun"):
                        failures += report(os.path.join(root, name))
        else:
            failures += report(path)
    if failures:
        print("%d file(s) with diagnostics" % failures)
        return 1
    return 0


def report(path):
    message = check(path)
    if message is None:
        return 0
    print("%s: %s" % (path, message))
    return 1


if __name__ == "__main__":
    sys.exit(main())
