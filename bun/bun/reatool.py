"""The bridge between Bun and the REA reverse-engineering toolkit.

REA (morluto/rea) turns the tools of the reverse engineer into one
command line. This module drives it from Bun, so a binary built by any
language — C, C++, Rust, Go, Bun's own native backend — can be opened,
listed and decompiled without leaving `bun reverse`.

The heavy lifting stays in REA and its analysis providers (Ghidra and
friends); this module only composes their commands and reads the
evidence they return.
"""

import json
import os
import shutil
import subprocess
import sys


def _node():
    """A node new enough for REA (its runtime wants a recent zlib)."""
    for candidate in ("/tmp/node-v22.23.4-linux-x64/bin/node",):
        if os.path.exists(candidate):
            return candidate
    return shutil.which("node") or "node"


def _find_cli():
    """Where the rea command line lives, or None."""
    home = os.environ.get("REA_HOME",
                          os.path.join(os.path.expanduser("~"), "work",
                                       "rea-src"))
    script = os.path.join(home, "scripts", "rea.mjs")
    if os.path.exists(script):
        return [_node(), script]
    installed = shutil.which("rea")
    if installed:
        return [installed]
    return None


def _environment():
    environment = dict(os.environ)
    if not environment.get("GHIDRA_INSTALL_DIR"):
        candidate = "/tmp/ghidra_12.1.4_PUBLIC"
        if os.path.isdir(candidate):
            environment["GHIDRA_INSTALL_DIR"] = candidate
    java = None
    for base in ("/tmp",):
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            if name.startswith("jdk-21"):
                java = os.path.join(base, name)
    if java:
        environment["JAVA_HOME"] = java
        environment["JAVA_HOME"] = java
        environment["PATH"] = os.path.join(java, "bin") + os.pathsep + \
            environment.get("PATH", "")
    return environment


def _run_cli(arguments, timeout=570):
    command = _find_cli()
    if command is None:
        raise RuntimeError("REA is not installed; clone morluto/rea and"
                           " run `npm ci && npm run build:cached`")
    try:
        completed = subprocess.run(
            command + arguments, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False, timeout=timeout,
            env=_environment())
    except subprocess.TimeoutExpired:
        raise RuntimeError("REA timed out on %s" % " ".join(arguments))
    except OSError as error:
        raise RuntimeError("REA failed to start: %s" % error)
    return completed.stdout.decode("utf-8", "replace")


def _markdown_values(markdown, headers):
    """Pull the `## header` sections out of a REA markdown answer."""
    sections = {}
    current = None
    for line in markdown.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {name: "\n".join(body).strip()
            for name, body in sections.items()}


def analyze(path):
    """The overview of a binary: format, architecture, procedure count."""
    text = _run_cli(["analyze", path, "--format", "md"])
    values = _markdown_values(text, ())
    summary = {}
    for key in ("subject.name", "subject.local_path", "provider",
                "normalized_result.procedure_count",
                "normalized_result.string_count",
                "normalized_result.segment_count", "confidence"):
        if key in values:
            summary[key] = values[key]
    return summary


def layout(path):
    """The memory layout of a binary: sections, segments, entry point."""
    text = _run_cli(["inspect-binary-layout", path, "--format", "md"])
    return _markdown_values(text, ()).get("normalized_result", text)


def exports(path):
    """The exported functions of a binary (its public face)."""
    text = _run_cli(["inspect-native-exports", path, "--format", "md"])
    return _markdown_values(text, ()).get("normalized_result", text)


def functions(path):
    """The functions REA knows in a binary, with their sizes."""
    text = _run_cli(["function", path, "--format", "md"])
    return _markdown_values(text, ()).get("normalized_result", text)


def decompile(path, procedure):
    """The pseudo-C of one procedure of a binary."""
    text = _run_cli(["decompile", path, "--procedure", procedure,
                     "--format", "md"])
    return _markdown_values(text, ()).get("normalized_result", text)


def cmd_reverse(args):
    """The command line entry: `bun reverse <binary> [procedure]`."""
    if not args or args[0] in ("-h", "--help"):
        print("usage: bun reverse <binary> [procedure]")
        print("  without a procedure: the overview and the functions")
        print("  with one: the decompiled code of that procedure")
        return 2 if not args else 0
    path = args[0]
    if not os.path.exists(path):
        print("error: no such file: %s" % path, file=sys.stderr)
        return 1
    try:
        if len(args) >= 2:
            print(decompile(path, args[1]))
        else:
            for key, value in analyze(path).items():
                print("%s: %s" % (key, value))
            print("\nexported functions:")
            print(exports(path))
    except RuntimeError as error:
        print("error: %s" % error, file=sys.stderr)
        return 1
    return 0
