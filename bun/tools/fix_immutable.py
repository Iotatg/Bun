#!/usr/bin/env python3
"""Turn the `let` of a name that changes into `var`.

The checker of the language says "cannot assign to immutable variable" and
gives the place of the change.  The name itself lives in the declaration
that comes before it, in the same function, so the script finds that
declaration and turns it into `var`.

    python3 tools/fix_immutable.py <folder> [<folder> ...]
"""

import os
import re
import subprocess
import sys

ERROR = re.compile(
    r"error: cannot assign to immutable variable '([^']+)'")
PLACE = re.compile(r"-->\s+(\S+):(\d+):(\d+)")


def check(path):
    result = subprocess.run(
        [sys.executable, "-m", "bun", "check", path],
        capture_output=True, text=True, timeout=120)
    return result.stdout + result.stderr


def fix_one(path, name, line):
    """Change the declaration of the name into `var`."""
    with open(path) as handle:
        lines = handle.read().split("\n")
    start = 0
    for index in range(min(line, len(lines)) - 1, -1, -1):
        if re.match(r"^(export )?fn ", lines[index]):
            start = index
            break
    pattern = re.compile(r"^(\s*)let\s+%s\b" % re.escape(name))
    for index in range(start, min(line, len(lines))):
        if pattern.match(lines[index]):
            lines[index] = pattern.sub(r"\1var %s" % name, lines[index], count=1)
            with open(path, "w") as handle:
                handle.write("\n".join(lines))
            return True
    return False


def walk(folder):
    for root, dirs, files in os.walk(folder):
        dirs[:] = [name for name in dirs if not name.startswith("_")]
        for name in sorted(files):
            if name.endswith(".bun"):
                yield os.path.join(root, name)


def main(argv):
    if len(argv) < 2:
        print("the tool needs a folder")
        return 1
    files = []
    for folder in argv[1:]:
        files.extend(walk(folder))
    total = 0
    for path in files:
        for _ in range(40):
            text = check(path)
            found = ERROR.search(text)
            if found is None:
                break
            place = PLACE.search(text)
            if place is None:
                print("no place for the error in", path)
                print(text[:400])
                break
            name = found.group(1)
            line = int(place.group(2))
            if fix_one(path, name, line) is False:
                print("cannot fix", name, "in", path, "line", line)
                break
            total += 1
    print("the names that changed:", total)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
