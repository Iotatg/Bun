"""The executable identity contract: docs/reference/bun-identity.md.

`bun:identity` is written in Bun and holds the origin ledger. These tests
derive the *real* keyword set from bun/lexer.py and bun/langpacks.py, so a
new keyword with no attribution fails the suite. The guard is deliberately
simple and deliberately falsifiable — see test_guard_is_falsifiable.
"""

import contextlib
import io
import os

import pytest

from bun import langpacks
from bun.cli import run_source
from bun.errors import ParseError
from bun.lexer import KEYWORDS, Lexer
from bun.parser import Parser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE = os.path.join(ROOT, "tests", "_identity_probe.bun")
LAB = os.path.join(ROOT, "tools", "identity_lab.bun")
HINDI = os.path.join(ROOT, "examples", "identity_hi.bun")
CHARTER = os.path.join(ROOT, "docs", "reference", "bun-identity.md")

ENGINES = [("tree", False), ("vm", False),
           ("register", False), ("register", True)]

ORIGINS = {"bun", "borrowed", "shared", "rejected"}
STATUSES = {"canonical", "compatibility", "rejected", "planned"}


def plain(value):
    """BunDict is not a Python dict; normalise it for assertions."""
    if hasattr(value, "keys") and not isinstance(value, dict):
        return {key: plain(value.get(key)) for key in value.keys()}
    if isinstance(value, list):
        return [plain(item) for item in value]
    return value


def bun_value(expr, engine="vm", tier=False, lang=None):
    source = ('import "bun:identity" as id\n'
              'let RESULT = id.' + expr + '\n')
    env = run_source(source, filename=PROBE, engine=engine, tier=tier,
                     lang=lang)
    return plain(env.get("RESULT"))


def check_coverage(ledger):
    expected = set(KEYWORDS) | set(langpacks.SOFT_KEYWORDS)
    got = set(ledger)
    missing = expected - got
    extra = got - expected
    assert not missing, "keywords with no origin entry: %s" % sorted(missing)
    assert not extra, "ledger names keywords the lexer lacks: %s" % sorted(extra)


# ------------------------------------------------------------------ guard

def test_identity_ledger_covers_every_keyword():
    check_coverage(bun_value("keywords()"))


def test_guard_is_falsifiable():
    """Removing one entry must break the guard, or the guard is theatre."""
    ledger = dict(bun_value("keywords()"))
    ledger.pop("let")
    with pytest.raises(AssertionError, match="no origin entry"):
        check_coverage(ledger)


def test_every_keyword_maps_to_a_known_family():
    families = {f["name"] for f in bun_value("families()")}
    for keyword, family in bun_value("keywords()").items():
        assert family in families, (keyword, family)


# ------------------------------------------------------------------ ledger

def test_every_family_is_fully_attributed():
    families = bun_value("families()")
    assert len(families) == len({f["name"] for f in families})
    for f in families:
        assert f["origin"] in ORIGINS
        assert f["status"] in STATUSES
        assert f["reason"] and f["bun_rule"] and f["name"]
        if f["origin"] == "borrowed":
            assert f["from"], "borrowed family must name its source"
        if f["origin"] == "bun":
            assert f["from"] == "", "a Bun family must claim no source"


def test_every_form_is_fully_attributed():
    forms = bun_value("forms()")
    assert len(forms) == len({f["name"] for f in forms})
    for f in forms:
        assert f["origin"] in ORIGINS
        assert f["status"] in STATUSES
        assert f["reason"] and f["bun_rule"] and f["name"]
        if f["origin"] == "borrowed":
            assert f["from"], "borrowed form must name its source"
        if f["origin"] == "bun":
            assert f["status"] == "canonical"
    names = {f["name"] for f in forms}
    assert 'import "path" as ns' in names
    assert 'import * as ns from "path"' in names


def test_every_rule_reference_exists():
    rules = bun_value("rules()")
    ids = {r["id"] for r in rules}
    assert len(ids) == len(rules) >= 8
    for r in rules:
        assert r["name"] and r["text"] and r["source"]
    for entry in bun_value("families()") + bun_value("forms()"):
        assert entry["bun_rule"] in ids


def test_bun_module_form_is_canonical_and_the_copy_is_rejected():
    forms = {f["name"]: f for f in bun_value("forms()")}
    assert forms['import "path" as ns']["origin"] == "bun"
    assert forms['import "path" as ns']["status"] == "canonical"
    assert forms['import * as ns from "path"']["status"] == "rejected"
    assert "ECMAScript" in forms['import * as ns from "path"']["from"]


@pytest.mark.parametrize("engine,tier", ENGINES,
                         ids=["tree", "vm", "register", "register+tier"])
def test_audit_is_certified_on_every_engine(engine, tier):
    audit = bun_value("audit()", engine=engine, tier=tier)
    assert audit["ok"] is True
    assert audit["verdict"] == "IDENTITY_LEDGER_CERTIFIED"
    assert audit["passed"] == audit["total"] == 15
    assert all(c["ok"] for c in audit["checks"])


# ------------------------------------------------------------------ refusal

def test_ecmascript_module_spelling_is_refused_by_the_parser():
    source = 'import * as ns from "./m.bun"\nprint(ns.x)\n'
    with pytest.raises(ParseError, match="is not Bun syntax") as exc:
        Parser(Lexer(source).tokenize()).parse()
    assert 'import "path" as ns' in str(exc.value)


def test_readme_no_longer_defines_bun_by_other_languages():
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    assert "Rust/Go/Python-inspired syntax" not in readme
    assert "docs/reference/bun-identity.md" in readme


def test_charter_lists_every_rule():
    text = open(CHARTER, encoding="utf-8").read()
    for rule in bun_value("rules()"):
        assert rule["id"] in text
        assert rule["name"] in text
    assert "A ledger is not a proof of originality" in text


# ------------------------------------------------------------------ execution

def test_identity_lab_is_byte_identical_on_all_engines():
    source = open(LAB, encoding="utf-8").read()
    outputs = []
    for engine, tier in ENGINES:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            run_source(source, filename=LAB, engine=engine, tier=tier)
        outputs.append(buf.getvalue())
    assert all(out == outputs[0] for out in outputs)
    assert "IDENTITY_LEDGER_CERTIFIED" in outputs[0]
    assert 'import "path" as ns' in outputs[0]
    assert 'import * as ns from "path"' in outputs[0]


@pytest.mark.parametrize("engine,tier", ENGINES,
                         ids=["tree", "vm", "register", "register+tier"])
def test_hindi_keyword_program_runs_on_every_engine(engine, tier, capsys):
    # A form made only of words the language packs translate can be written
    # in the reader's own language on the day it is introduced (R7).
    source = open(HINDI, encoding="utf-8").read()
    run_source(source, filename=HINDI, engine=engine, tier=tier)
    assert "IDENTITY_LEDGER_CERTIFIED" in capsys.readouterr().out
