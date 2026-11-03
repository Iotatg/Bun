"""The polyglot runtime of Bun — call any language from a Bun program.

`run_language(lang, code)` runs a piece of code in another language and
returns a dictionary with its status, its output and the time it took.
The registry knows the interpreters and compilers of the machine: every
language found on the PATH is ready, and the compiled ones (C, C++ and
friends) are built once and cached by their digest.
"""

import hashlib
import os
import shutil
import subprocess
import tempfile
import time

_CACHE = {}


class Languages:
    """The languages of the machine: how to detect them, how to run them."""

    # name -> (detect commands, how to run a file, compile-first?)
    REGISTRY = {
        "python":     (["python3"], ["python3"], False),
        "javascript": (["node"], ["node"], False),
        "bash":       (["bash"], ["bash"], False),
        "sh":         (["sh"], ["sh"], False),
        "ruby":       (["ruby"], ["ruby"], False),
        "perl":       (["perl"], ["perl"], False),
        "php":        (["php"], ["php"], False),
        "lua":        (["lua", "lua5.4", "lua5.3"], ["lua"], False),
        "tcl":        (["tclsh"], ["tclsh"], False),
        "r":          (["Rscript"], ["Rscript"], False),
        "elixir":     (["elixir"], ["elixir"], False),
        "dart":       (["dart"], ["dart", "run"], False),
        "julia":      (["julia"], ["julia"], False),
        "haskell":    (["runghc", "ghc"], ["runghc"], False),
        "awk":        (["awk"], ["awk", "-f"], False),
        "sed":        (["sed"], ["sed", "-f"], False),
        "c":          (["cc", "gcc"], ["cc"], True),
        "cpp":        (["c++", "g++"], ["c++"], True),
        "rust":       (["rustc"], ["rustc"], True),
        "go":         (["go"], ["go"], True),
        "java":       (["javac"], ["javac"], True),
        "fortran":    (["gfortran"], ["gfortran"], True),
        "zig":        (["zig"], ["zig"], True),
    }

    ALIASES = {
        "py": "python", "python3": "python",
        "js": "javascript", "node": "javascript",
        "shell": "bash", "golang": "go",
        "c++": "cpp", "cxx": "cpp", "cc": "c",
        "rb": "ruby", "gjs": "javascript",
    }

    def find(self, language):
        """(interpreter command, compile command or None) for a language,
        or None when the machine has none."""
        language = self.ALIASES.get(language, language)
        detect, run, compile_first = self.REGISTRY.get(language, (None, None, False))
        if detect is None:
            return None
        for command in detect:
            if shutil.which(command):
                if compile_first:
                    return (run, command, language)
                return (run, None, language)
        return None

    def installed(self):
        """Every language of the registry that this machine can run."""
        ready = []
        for language in self.REGISTRY:
            if self.find(language):
                ready.append(language)
        return ready


def _write(path, text):
    with open(path, "w") as handle:
        handle.write(text)


def _run_compiled(language, run, compiler, code, timeout, program_args):
    """Compile once per digest, run many times: the cache of the machine."""
    digest = hashlib.sha256(
        (language + compiler + code).encode("utf-8")).hexdigest()[:32]
    directory = os.path.join(tempfile.gettempdir(), "bun-polyglot", digest)
    binary = os.path.join(directory, "program")
    if not os.path.exists(binary):
        os.makedirs(directory, exist_ok=True)
        if language == "go":
            _write(os.path.join(directory, "main.go"), code)
            _write(os.path.join(directory, "go.mod"),
                   "module bunpolyglot\n\ngo 1.21\n")
            build = ["go", "build", "-o", binary, "main.go"]
        elif language == "java":
            _write(os.path.join(directory, "Main.java"), code)
            build = ["javac", "-d", directory, os.path.join(directory, "Main.java")]
            binary = None  # java runs by class name
        else:
            suffix = {"rust": ".rs", "zig": ".zig", "fortran": ".f90"}.get(
                language, ".c" if language == "c" else ".cpp")
            source = os.path.join(directory, "main" + suffix)
            _write(source, code)
            if language == "rust":
                build = ["rustc", "-O", "-o", binary, source]
            elif language == "zig":
                build = ["zig", "build-exe", "-femit-bin=" + binary, source]
            else:
                build = [compiler, "-O2", "-o", binary, source]
        try:
            subprocess.run(build, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, check=True, timeout=timeout,
                           cwd=directory)
        except subprocess.CalledProcessError as error:
            return {"ok": False, "status": error.returncode, "build_failed": True,
                    "stdout": "", "stderr": error.stderr.decode("utf-8", "replace")}
        if binary is None:
            binary = ["java", "-cp", directory, "Main"]
    if isinstance(binary, str):
        command = [binary] + list(program_args)
    else:
        command = binary + list(program_args)
    started = time.time()
    completed = subprocess.run(command, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, check=False,
                               timeout=timeout)
    return {"ok": completed.returncode == 0,
            "status": completed.returncode, "build_failed": False,
            "stdout": completed.stdout.decode("utf-8", "replace"),
            "stderr": completed.stderr.decode("utf-8", "replace"),
            "seconds": time.time() - started}


def run_language(language, code, program_args=None, timeout=30):
    """Run code in another language; the answer is a plain dictionary.

    An unknown language never raises: the answer carries ok=false and
    the reason in stderr, so Bun code can branch on it.
    """
    machine = Languages()
    found = machine.find(language)
    if found is None:
        return {"ok": False, "status": None, "build_failed": False,
                "stdout": "",
                "stderr": "no interpreter for '%s' on this machine;"
                          " installed: %s"
                          % (language, ", ".join(machine.installed())),
                "seconds": 0.0}
    run, compiler, name = found
    program_args = list(program_args or [])
    if compiler is not None:
        return _run_compiled(name, run, compiler, code, timeout, program_args)
    with tempfile.NamedTemporaryFile("w", suffix=".tmp", delete=False) as handle:
        handle.write(code)
        path = handle.name
    try:
        started = time.time()
        completed = subprocess.run(run + [path] + program_args,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, check=False,
                                   timeout=timeout)
        return {"ok": completed.returncode == 0,
                "status": completed.returncode, "build_failed": False,
                "stdout": completed.stdout.decode("utf-8", "replace"),
                "stderr": completed.stderr.decode("utf-8", "replace"),
                "seconds": time.time() - started}
    except subprocess.TimeoutExpired:
        raise RuntimeError("%s timed out after %s seconds" % (language, timeout))
    finally:
        os.unlink(path)


def installed_languages():
    """The languages this machine can run, by name."""
    return Languages().installed()
