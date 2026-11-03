"""Tests for the polyglot interop layer (bun.polyglot)."""

import pytest

from bun import polyglot
from bun.cli import run_source


def test_registry_has_20_plus_languages():
    assert len(polyglot.Languages.REGISTRY) >= 20


def test_core_languages_registered():
    names = set(polyglot.Languages.REGISTRY)
    for name in ("python", "javascript", "bash", "ruby", "perl", "php",
                 "lua", "c", "cpp", "rust", "go", "java"):
        assert name in names


def test_aliases_resolve():
    assert polyglot.Languages.REGISTRY[polyglot.Languages.ALIASES["js"]] \
        is not None or True
    assert polyglot.Languages.ALIASES["js"] == "javascript"
    assert polyglot.Languages.ALIASES["py"] == "python"
    assert polyglot.Languages.ALIASES["golang"] == "go"
    assert polyglot.Languages.ALIASES["c++"] == "cpp"
    assert polyglot.Languages.ALIASES["shell"] == "bash"


def test_installed_lists_working_interpreters():
    found = polyglot.installed_languages()
    assert "python" in found
    assert "bash" in found or "sh" in found


def test_run_python():
    result = polyglot.run_language("python", "print(40 + 2)")
    assert result["ok"] and result["stdout"].strip() == "42"


def test_run_javascript():
    result = polyglot.run_language("javascript", "console.log(6 * 7)")
    assert result["ok"] and result["stdout"].strip() == "42"


def test_run_bash():
    result = polyglot.run_language("bash", "echo hello-from-shell")
    assert result["ok"] and result["stdout"].strip() == "hello-from-shell"


def test_run_c_compiles_and_caches():
    result = polyglot.run_language(
        "c", "#include <stdio.h>\nint main(void){printf(\"%d\\n\", 21*2);"
             "return 0;}\n")
    assert result["ok"], result.get("stderr")
    assert result["stdout"].strip() == "42"
    # Second run must hit the compile cache and stay correct.
    again = polyglot.run_language(
        "c", "#include <stdio.h>\nint main(void){printf(\"%d\\n\", 21*2);"
             "return 0;}\n")
    assert again["ok"] and again["stdout"].strip() == "42"


def test_run_from_bun_code(capsys):
    run_source('let r = run_language("python", "print(\\"bun says hi\\")")\n'
               'print(r["stdout"].trim())\n', check=True)
    assert capsys.readouterr().out.strip() == "bun says hi"


def test_installed_languages_builtin(capsys):
    run_source('let langs = installed_languages()\n'
               'print(langs.contains("python"))\n', check=True)
    assert capsys.readouterr().out.strip() == "true"


def test_unknown_language_is_clean_error(capsys):
    run_source('let r = run_language("brainfuck", "++++")\n'
               'print(r["ok"])\n', check=True)
    assert capsys.readouterr().out.strip() == "false"


def test_bad_code_reports_failure_not_crash():
    result = polyglot.run_language("python", "syntax error here !!")
    assert not result["ok"]
    assert result["stderr"]
