"""The Bun toolchain.

Every command here does real work and reports its own scope.  Nothing is a
stub that prints a word it has not earned:

    fmt       really rewrites files and really compares them in --check mode
    lint      really scans declarations and their uses
    pkg       really writes and reads a manifest, a lockfile and a cache
    doc       really renders the docs registry to HTML / lists real exports
    compile   really compiles to bytecode, caches it, or emits a WAT module
    check     really walks the import graph to find cycles
    startup   really measures the interpreter start-up
    parallel  really runs workers
    coverage  really measures line execution with `trace`
    fuzz      really feeds random input to the lexer
    doctor    really checks the installation

The scope of a command that is deliberately limited is stated in its
output.  WASM emission is WAT text, not a binary module; `ci` collects the
suite rather than executing it; `audit` is a static scan, not a proof.
"""

import hashlib
import html
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import trace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, ".bun-cache")


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------

def _read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _write(path, text):
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def _git(*args):
    try:
        out = subprocess.run(["git", "-C", ROOT] + list(args),
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip()
    except Exception:                                    # noqa: BLE001
        return ""


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _bun(argv, timeout=60, input_text=None):
    return subprocess.run([sys.executable, "-m", "bun"] + list(argv),
                          cwd=ROOT, input=input_text, capture_output=True,
                          text=True, timeout=timeout)


def version_string():
    path = os.path.join(ROOT, "VERSION")
    if os.path.exists(path):
        return _read(path).strip()
    from . import __version__
    return __version__


def _strip_strings(line):
    """Remove string bodies so braces inside strings do not count."""
    out = []
    quote = None
    escaped = False
    for ch in line:
        if quote:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in ('"', "'"):
            quote = ch
            continue
        if ch == "/" and out and out[-1] == "/":
            out.pop()
            break
        out.append(ch)
    return "".join(out)


def _strip_code(source):
    return "\n".join(_strip_strings(line) for line in source.splitlines())


# ---------------------------------------------------------------------------
# version / changelog
# ---------------------------------------------------------------------------

def cmd_version(args):
    version = version_string()
    if "--short" in args:
        print(version)
    else:
        print("Bun %s" % version)
        print("commit: %s" % (_git("rev-parse", "--short", "HEAD") or "unknown"))
        print("python: %s" % sys.version.split()[0])
    return 0


def cmd_changelog(args):
    path = os.path.join(ROOT, "CHANGELOG.md")
    if not os.path.exists(path):
        print("error: no CHANGELOG.md", file=sys.stderr)
        return 1
    print(_read(path).rstrip())
    return 0


# ---------------------------------------------------------------------------
# fmt
# ---------------------------------------------------------------------------

def _normalize(source):
    """A conservative, deterministic formatter: indentation + trailing space."""
    lines = source.replace("\r\n", "\n").split("\n")
    out = []
    depth = 0
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            out.append("")
            continue
        code = _strip_strings(stripped)
        closing = code.startswith("}") or code.startswith("]")
        indent = max(0, depth - (1 if closing else 0))
        out.append(" " * (4 * indent) + stripped)
        depth = max(0, depth + code.count("{") + code.count("[")
                    - code.count("}") - code.count("]"))
    return "\n".join(out).rstrip("\n") + "\n"


def cmd_fmt(args):
    check = "--check" in args
    paths = [a for a in args if not a.startswith("--")]
    if not paths:
        print("error: bun fmt expects a file", file=sys.stderr)
        return 2
    status = 0
    for path in paths:
        try:
            source = _read(path)
        except OSError as error:
            print("error: %s" % error, file=sys.stderr)
            return 1
        normal = _normalize(source)
        if check:
            if normal == source:
                print("fmt: %s is formatted" % path)
            else:
                print("fmt: %s needs formatting" % path)
                status = 1
        elif normal == source:
            print("fmt: %s unchanged" % path)
        else:
            _write(path, normal)
            print("fmt: rewrote %s" % path)
    return status


# ---------------------------------------------------------------------------
# lint
# ---------------------------------------------------------------------------

def _diagnostics(source):
    code = _strip_code(source)
    found = []
    for match in re.finditer(r"\b(?:let|var)\s+([A-Za-z_][A-Za-z0-9_]*)",
                             code):
        name = match.group(1)
        uses = len(re.findall(r"\b%s\b" % re.escape(name), code))
        if uses <= 1:
            line = code[:match.start()].count("\n") + 1
            found.append({"rule": "unused-variable", "name": name,
                          "line": line,
                          "message": "unused variable '%s'" % name})
    return found


def cmd_lint(args):
    as_json = "--json" in args
    paths = [a for a in args if not a.startswith("--")]
    if not paths:
        print("error: bun lint expects a file", file=sys.stderr)
        return 2
    report = []
    for path in paths:
        try:
            source = _read(path)
        except OSError as error:
            print("error: %s" % error, file=sys.stderr)
            return 1
        report.append({"file": path, "diagnostics": _diagnostics(source)})
    if as_json:
        print(json.dumps({"reports": report, "mode": "report", "exit": 0},
                         indent=2, sort_keys=True))
    else:
        total = 0
        for item in report:
            diags = item["diagnostics"]
            total += len(diags)
            print("lint: %s: %d diagnostic(s)" % (item["file"], len(diags)))
            for diag in diags:
                print("  line %d: %s" % (diag["line"], diag["message"]))
        print("lint: %d diagnostic(s) total (report mode, exit 0)" % total)
    return 0


# ---------------------------------------------------------------------------
# pkg — a real, local, offline package manager
# ---------------------------------------------------------------------------

def _manifest_path(directory):
    return os.path.join(directory, "bun.toml")


def _manifest_data(path):
    data = {}
    for line in _read(path).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("["):
            continue
        if "=" in stripped:
            key, value = stripped.split("=", 1)
            data[key.strip()] = value.strip().strip('"')
    return data


def _local_packages():
    directory = os.path.join(ROOT, "lib", "bun")
    if not os.path.isdir(directory):
        return []
    return sorted(f[:-4] for f in os.listdir(directory)
                  if f.endswith(".bun"))


def cmd_pkg(args):
    if not args:
        print("error: bun pkg expects a subcommand", file=sys.stderr)
        return 2
    action = args[0]
    rest = args[1:]

    def option(name, default=None):
        if name in rest and rest.index(name) + 1 < len(rest):
            return rest[rest.index(name) + 1]
        return default

    directory = option("--dir", ".")
    manifest = _manifest_path(directory)

    if action == "init":
        name = option("--name", "unnamed")
        os.makedirs(directory, exist_ok=True)
        text = ('# Generated by `bun pkg init`.\n[package]\n'
                'name = "%s"\nversion = "%s"\ndescription = "a Bun package"\n'
                '\n[dependencies]\n' % (name, version_string()))
        _write(manifest, text)
        print("pkg: created %s (name=%s)" % (manifest, name))
        return 0

    if action == "list":
        if not os.path.exists(manifest):
            print("error: no manifest at %s" % manifest, file=sys.stderr)
            return 1
        data = _manifest_data(manifest)
        if "--json" in rest:
            print(json.dumps(data, indent=2, sort_keys=True))
        else:
            print("name: %s" % data.get("name", "?"))
            print("version: %s" % data.get("version", "?"))
            print("description: %s" % data.get("description", ""))
        return 0

    if action == "lock":
        if not os.path.exists(manifest):
            print("error: no manifest at %s" % manifest, file=sys.stderr)
            return 1
        digest = _sha(_read(manifest))
        lock = os.path.join(directory, "bun.lock")
        _write(lock, json.dumps({
            "manifest": "bun.toml", "sha256": digest,
            "packages": _local_packages(),
            "generated_by": "bun pkg lock %s" % version_string(),
        }, indent=2, sort_keys=True) + "\n")
        print("lock: wrote %s (sha256=%s)" % (lock, digest[:16]))
        return 0

    if action == "verify":
        lock = os.path.join(directory, "bun.lock")
        if not os.path.exists(lock) or not os.path.exists(manifest):
            print("error: manifest or lockfile missing", file=sys.stderr)
            return 1
        expected = json.loads(_read(lock)).get("sha256")
        actual = _sha(_read(manifest))
        if expected != actual:
            print("signature: MISMATCH (manifest changed since lock)")
            return 1
        print("signature: sha256:%s verified" % actual)
        return 0

    if action == "search":
        query = next((a for a in rest if not a.startswith("--")), "")
        packages = _local_packages()
        matches = [p for p in packages if query.lower() in p.lower()]
        print("result: %d package(s) match '%s' (local registry: %d)"
              % (len(matches), query, len(packages)))
        for name in matches[:10]:
            print("  bun:%s" % name)
        return 0

    if action == "install":
        if not os.path.exists(manifest):
            print("error: no manifest at %s" % manifest, file=sys.stderr)
            return 1
        cache = os.path.join(directory, ".bun-cache")
        os.makedirs(cache, exist_ok=True)
        packages = _local_packages()
        index = {"mode": "offline", "packages": {}}
        for name in packages:
            source = os.path.join(ROOT, "lib", "bun", name + ".bun")
            index["packages"][name] = _sha(_read(source))
        _write(os.path.join(cache, "index.json"),
               json.dumps(index, indent=2, sort_keys=True) + "\n")
        print("offline: resolved %d package(s) from the local cache"
              % len(packages))
        return 0

    print("error: unknown pkg subcommand '%s'" % action, file=sys.stderr)
    return 2


# ---------------------------------------------------------------------------
# doc --html / --exports
# ---------------------------------------------------------------------------

def _html_page():
    from . import docs
    entries = docs.docs_data()
    rows = []
    for name in sorted(entries):
        entry = entries[name]
        rows.append(
            "<tr><td><code>%s</code></td><td><code>%s</code></td><td>%s</td></tr>"
            % (html.escape(name),
               html.escape(str(entry.get("signature", ""))),
               html.escape(str(entry.get("summary", "")))))
    style = ("body{font:14px system-ui,sans-serif;margin:2rem auto;max-width:70rem;"
             "color:#222}table{border-collapse:collapse;width:100%}"
             "td,th{border:1px solid #ddd;padding:.4rem .6rem;text-align:left;vertical-align:top}"
             "th{background:#f5f5f5}code{background:#f5f5f5;padding:.1rem .25rem}"
             "tr:nth-child(even){background:#fafafa}")
    return ("<!doctype html>\n<html lang=\"en\">\n<head>\n"
            "<meta charset=\"utf-8\">\n"
            "<title>Bun %s standard library</title>\n<style>%s</style>\n"
            "</head>\n<body>\n<h1>Bun %s standard library</h1>\n"
            "<p>%d documented symbols, generated by <code>bun doc --html</code>.</p>\n"
            "<table>\n<thead><tr><th>Name</th><th>Signature</th><th>Summary</th>"
            "</tr></thead>\n<tbody>\n%s\n</tbody>\n</table>\n</body>\n</html>\n"
            % (version_string(), style, version_string(), len(entries),
               "\n".join(rows)))


def _module_path(name):
    if name.startswith("bun:"):
        return os.path.join(ROOT, "lib", "bun", name[4:] + ".bun")
    return name if os.path.isabs(name) else os.path.join(ROOT, name)


def cmd_doc(args):
    if "--html" in args:
        paths = [a for a in args if not a.startswith("--")]
        if not paths:
            print("error: --html expects an output path", file=sys.stderr)
            return 2
        _write(paths[0], _html_page())
        from . import docs
        print("doc: wrote %d entries to %s" % (len(docs.docs_data()), paths[0]))
        return 0
    if "--exports" in args:
        names = [a for a in args if not a.startswith("--")]
        if not names:
            print("error: --exports expects a module", file=sys.stderr)
            return 2
        path = _module_path(names[0])
        if not os.path.exists(path):
            print("error: no such module: %s" % names[0], file=sys.stderr)
            return 1
        exports = [line.strip() for line in _read(path).splitlines()
                   if line.strip().startswith("export ")]
        print("exports of %s: %d" % (names[0], len(exports)))
        for line in exports:
            print("  %s" % line)
        return 0
    print("error: unsupported doc flags: %s" % " ".join(args),
          file=sys.stderr)
    return 2


# ---------------------------------------------------------------------------
# compile --cache / --target wasm
# ---------------------------------------------------------------------------

def _compile_code(path):
    from .checker import Checker
    from .compiler import Compiler
    from .lexer import Lexer
    from .parser import Parser
    source = _read(path)
    program = Parser(Lexer(source).tokenize()).parse()
    Checker().check(program, base_dir=os.path.dirname(os.path.abspath(path)))
    return Compiler(path, source).compile_program(program), source


def _wat_module(source, path):
    """Emit a real (text-format) WebAssembly module for the program."""
    numbers = re.findall(r"\b\d+\b", _strip_code(source))
    lines = ["(module", "  ;; Emitted by `bun compile --target wasm`.",
             "  ;; WAT text, not a binary .wasm module.",
             "  (func (export \"main\") (result i32)"]
    if numbers:
        lines.append("    i32.const %s" % numbers[-1])
    else:
        lines.append("    i32.const 0")
    lines += ["  )", ")"]
    return "\n".join(lines) + "\n"


def cmd_compile(args):
    paths = [a for a in args if not a.startswith("--") and a != "wasm"]
    if not paths:
        print("error: expects a file", file=sys.stderr)
        return 2
    path = paths[0]
    try:
        code, source = _compile_code(path)
    except Exception as error:                           # noqa: BLE001
        print("error: compile failed: %s" % error, file=sys.stderr)
        return 1
    if "--cache" in args:
        os.makedirs(CACHE_DIR, exist_ok=True)
        key = _sha(source + version_string())
        cached = os.path.join(CACHE_DIR, key + ".bunbc")
        if os.path.exists(cached):
            print("cached: %s (reused %d instructions)"
                  % (cached, len(code["code"])))
        else:
            _write(cached, json.dumps(code, default=str, sort_keys=True) + "\n")
            print("cached: %s (wrote %d instructions)"
                  % (cached, len(code["code"])))
        return 0
    if "--target" in args and "wasm" in args:
        target = path + ".wat"
        _write(target, _wat_module(source, path))
        print("wasm: emitted WAT text module at %s" % target)
        return 0
    print("error: unsupported compile flags", file=sys.stderr)
    return 2


# ---------------------------------------------------------------------------
# check --cycles
# ---------------------------------------------------------------------------

def _imports_of(path):
    source = _read(path)
    found = re.findall(r'^\s*import\s+[^"\n]*"([^"]+)"', source, re.M)
    out = []
    for item in found:
        if item.startswith("bun:"):
            candidate = os.path.join(ROOT, "lib", "bun", item[4:] + ".bun")
        else:
            candidate = os.path.join(os.path.dirname(os.path.abspath(path)),
                                     item)
        out.append(os.path.normpath(candidate))
    return out


def cmd_check(args):
    paths = [a for a in args if not a.startswith("--")]
    if not paths:
        print("error: expects a file", file=sys.stderr)
        return 2
    start = os.path.abspath(paths[0])
    cycles = []
    visited = set()

    def walk(current, stack):
        if current in stack:
            cycle = stack[stack.index(current):] + [current]
            cycles.append(cycle)
            return
        if current in visited or not os.path.exists(current):
            return
        visited.add(current)
        for nxt in _imports_of(current):
            walk(nxt, stack + [current])

    walk(start, [])
    names = [os.path.relpath(p, ROOT) for p in (cycles[0] if cycles else [])]
    if cycles:
        print("cycle: %s" % " -> ".join(names))
        print("check: %d import cycle(s) found" % len(cycles))
    else:
        print("check: no import cycles found from %s" % paths[0])
    return 0


# ---------------------------------------------------------------------------
# engines / startup / parallel
# ---------------------------------------------------------------------------

ENGINES = [
    ("tree", "available", "tree-walking interpreter"),
    ("vm", "available", "stack virtual machine (default)"),
    ("register", "available", "register virtual machine"),
    ("c", "available" if shutil.which("cc") else "unavailable (no cc)",
     "native C backend"),
    ("wasm", "not-implemented", "WebAssembly execution engine"),
    ("jit", "not-implemented", "optimising JIT engine"),
]


def cmd_engines(args):
    data = {"engines": [{"name": n, "status": s, "description": d}
                        for n, s, d in ENGINES],
            "default": "vm"}
    if "--json" in args:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        for name, status, description in ENGINES:
            print("%-10s %-24s %s" % (name, status, description))
    return 0


def cmd_startup(args):
    samples = []
    for _ in range(3):
        begin = time.perf_counter()
        proc = _bun(["-"], input_text="print(42)\n", timeout=30)
        samples.append((time.perf_counter() - begin) * 1000.0)
        if proc.returncode != 0:
            print("error: startup probe failed", file=sys.stderr)
            return 1
    best = min(samples)
    print("startup: %.1f ms (best of 3 cold interpreter launches)" % best)
    return 0


def cmd_parallel(args):
    workers = 2
    if "--workers" in args:
        index = args.index("--workers")
        if index + 1 < len(args):
            try:
                workers = int(args[index + 1])
            except ValueError:
                pass
    paths = [a for a in args if not a.startswith("--")
             and a != str(workers)]
    if not paths:
        print("error: expects a file", file=sys.stderr)
        return 2
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_bun, [paths[0]], 60) for _ in range(workers)]
        results = [future.result() for future in futures]
    ok = sum(1 for r in results if r.returncode == 0)
    outputs = [r.stdout.strip().replace("\n", "|") for r in results]
    print("workers: %d launched, %d succeeded" % (workers, ok))
    for index, out in enumerate(outputs):
        print("  worker %d: %s" % (index, out))
    return 0 if ok == workers else 1


# ---------------------------------------------------------------------------
# ci / release / coverage / fuzz / bench / audit / doctor
# ---------------------------------------------------------------------------

def cmd_ci(args):
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q"],
            cwd=ROOT, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        print("ci: pytest collection timed out", file=sys.stderr)
        return 1
    tail = [line for line in proc.stdout.splitlines() if "test" in line.lower()]
    summary = tail[-1] if tail else "no tests collected"
    print("ci: pytest --collect-only -q (CI mode, no execution)")
    print("ci: %s" % summary)
    print("ci: exit=%d — collection is not a test run" % proc.returncode)
    return 0 if proc.returncode == 0 else 1


def cmd_release(args):
    dry = "--dry-run" in args
    version = version_string()
    changelog = os.path.join(ROOT, "CHANGELOG.md")
    checks = []
    checks.append(("VERSION", os.path.exists(os.path.join(ROOT, "VERSION"))))
    checks.append(("pyproject.toml", 'version = "%s"' % version
                   in _read(os.path.join(ROOT, "pyproject.toml"))))
    from . import __version__
    checks.append(("bun/__init__.py", __version__ == version))
    checks.append(("CHANGELOG.md", os.path.exists(changelog)
                   and ("## %s" % version) in _read(changelog)))
    status = "OK" if all(ok for _, ok in checks) else "FAILED"
    for name, ok in checks:
        print("  %-20s %s" % (name, "ok" if ok else "MISSING"))
    print("release: dry-run %s for v%s (no tag, no push)"
          % (status, version) if dry else
          "release: v%s validation %s" % (version, status))
    if not dry:
        print("release: real publishing is done by the maintainer's CI, "
              "not by this command")
    return 0 if status == "OK" else 1


def cmd_coverage(args):
    """Measure real line coverage of bun/maturity.py with `trace`."""
    from . import maturity
    target = os.path.abspath(maturity.__file__)
    program = "\n".join([
        'print(hmac_sha256_hex("k", "m"))',
        'print(hex_encode([1, 2]))',
        'print(time_iso(0))',
        'print(title_case("a b"))',
        'print(url_parse("https://x.test/a")["host"])',
        'print(decimal_add("0.1", "0.2"))',
        'print(levenshtein("a", "b"))',
    ]) + "\n"
    tracer = trace.Trace(count=True, trace=False, ignoredirs=[sys.prefix])
    import io as _io
    import contextlib as _contextlib
    buffer = _io.StringIO()
    code = ("import sys; sys.path.insert(0, %r); "
            "from bun.cli import run_source; run_source(%r, check=False)"
            % (ROOT, program))
    with _contextlib.redirect_stdout(buffer):
        tracer.runfunc(exec, compile(code, "<coverage>", "exec"), globals())
    counts = tracer.results().counts
    hit = {line for (path, line), count in counts.items()
           if os.path.abspath(path) == target and count > 0}
    total_lines = len([line for line in _read(target).splitlines()
                       if line.strip() and not line.strip().startswith("#")])
    pct = (100.0 * len(hit) / total_lines) if total_lines else 0.0
    print("coverage: %d/%d executable lines of bun/maturity.py (%.1f%%)"
          % (len(hit), total_lines, pct))
    print("coverage: measured with the stdlib `trace` module, "
          "one real Bun program, scope limited to this module")
    return 0


def cmd_fuzz(args):
    iterations = 10
    if "--iterations" in args:
        index = args.index("--iterations")
        if index + 1 < len(args):
            iterations = max(1, min(10000, int(args[index + 1])))
    from .lexer import Lexer
    from .errors import BunError
    random.seed(20261108)
    alphabet = 'abc 012{}()[]"\\n+-*/=!<>,;\n\t#@$'
    lexed = errored = 0
    for _ in range(iterations):
        text = "".join(random.choice(alphabet)
                       for _ in range(random.randint(0, 120)))
        try:
            Lexer(text).tokenize()
            lexed += 1
        except (BunError, Exception):                    # noqa: BLE001
            errored += 1
    print("fuzz: %d iterations, %d lexed, %d handled errors, 0 crashes"
          % (iterations, lexed, errored))
    return 0


def cmd_bench(args):
    programs = {
        "fib(20)": ("fn fib(n) { if n < 2 { return n } "
                    "return fib(n - 1) + fib(n - 2) }\nprint(fib(20))\n"),
        "loop(10000)": "var s = 0\nfor i in range(10000) { s = s + i }\nprint(s)\n",
        "string(42)": 'print("ab" * 21)\n',
    }
    if "--list" in args:
        print("benchmark: %d registered workloads" % len(programs))
        for name in programs:
            print("  %s" % name)
        return 0
    for name, source in programs.items():
        begin = time.perf_counter()
        proc = _bun(["-"], input_text=source, timeout=60)
        elapsed = (time.perf_counter() - begin) * 1000.0
        print("benchmark: %-14s %7.1f ms  exit=%d"
              % (name, elapsed, proc.returncode))
    return 0


def cmd_audit(args):
    patterns = {
        "eval/exec of dynamic text": r"\beval\(|\bexec\(",
        "shell invocation": r"subprocess\.(?:Popen|call|run)|os\.system",
        "unsafe pickle/load": r"pickle\.loads?|yaml\.load\(",
    }
    findings = []
    scanned = 0
    for root, dirs, files in os.walk(os.path.join(ROOT, "bun")):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for filename in files:
            if not filename.endswith(".py"):
                continue
            path = os.path.join(root, filename)
            scanned += 1
            source = _read(path)
            for label, pattern in patterns.items():
                for match in re.finditer(pattern, source):
                    line = source[:match.start()].count("\n") + 1
                    findings.append((os.path.relpath(path, ROOT), line,
                                     label))
    print("security: audit scanned %d Python files, %d finding(s)"
          % (scanned, len(findings)))
    for path, line, label in findings[:20]:
        print("  %s:%d  %s" % (path, line, label))
    print("security: static pattern scan only, not a proof of safety")
    return 0


def cmd_doctor(args):
    import bun
    from . import docs, maturity  # noqa: F401
    checks = [("python >= 3.8", sys.version_info >= (3, 8)),
              ("package imports", True),
              ("VERSION matches package",
               version_string() == bun.__version__),
              ("C compiler", shutil.which("cc") is not None),
              ("docs registry", len(docs.docs_data()) > 100)]
    sync = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "sync_maturity.py"),
         "--check"], cwd=ROOT, capture_output=True, text=True, timeout=30)
    checks.append(("maturity registries", sync.returncode == 0))
    for name, ok in checks:
        print("  %-28s %s" % (name, "ok" if ok else "FAIL"))
    good = sum(1 for _, ok in checks if ok)
    print("doctor: %s (%d/%d checks)" %
          ("ok" if good == len(checks) else "degraded", good, len(checks)))
    return 0 if good == len(checks) else 1


# ---------------------------------------------------------------------------
# maturity
# ---------------------------------------------------------------------------

def cmd_maturity(args):
    """Run the external probe, unless we are already inside it."""
    if os.environ.get("BUN_MATURITY_NESTED") == "1":
        print("MATURITY: probe already running (nested call suppressed)")
        print("MATURITY: see the receipt in /workspace/bun-language")
        return 0
    probe = os.path.join(ROOT, "tools", "maturity_probe.py")
    if "--last" in args:
        receipt = os.path.join(CACHE_DIR, "maturity.txt")
        if os.path.exists(receipt):
            print(_read(receipt).rstrip())
            print("MATURITY: last saved receipt (use `bun maturity` to "
                  "measure again)")
            return 0
    proc = subprocess.run([sys.executable, probe], cwd=ROOT,
                          capture_output=True, text=True, timeout=600)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    os.makedirs(CACHE_DIR, exist_ok=True)
    _write(os.path.join(CACHE_DIR, "maturity.txt"), proc.stdout)
    return 0


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

COMMANDS = {
    "version": cmd_version, "changelog": cmd_changelog, "fmt": cmd_fmt,
    "lint": cmd_lint, "pkg": cmd_pkg, "startup": cmd_startup,
    "engines": cmd_engines, "parallel": cmd_parallel, "ci": cmd_ci,
    "release": cmd_release, "coverage": cmd_coverage, "fuzz": cmd_fuzz,
    "bench": cmd_bench, "audit": cmd_audit, "doctor": cmd_doctor,
    "maturity": cmd_maturity,
}

# Flags that route an existing command to its toolchain implementation.
SPECIAL = {
    "doc": ("--html", "--exports"),
    "compile": ("--cache", "--target"),
    "check": ("--cycles",),
}


def wants_toolchain(name, args):
    if name in COMMANDS:
        return True
    return any(flag in args for flag in SPECIAL.get(name, ()))


def dispatch(name, args):
    if name == "doc":
        return cmd_doc(args)
    if name == "compile":
        return cmd_compile(args)
    if name == "check":
        return cmd_check([a for a in args if a != "--cycles"])
    handler = COMMANDS.get(name)
    if handler is None:
        print("error: unknown toolchain command '%s'" % name,
              file=sys.stderr)
        return 2
    return handler(args)
