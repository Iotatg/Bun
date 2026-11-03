"""Tests for the multi-language keyword packs (bun.langpacks)."""

import unicodedata

import pytest

from bun import langpacks
from bun.cli import run_source


def _codes():
    return {row[0] for row in langpacks.list_packs()}


def test_pack_count_at_least_100():
    """The 100+ languages promise: at least 100 keyword packs ship."""
    packs = langpacks.list_packs()
    assert len(packs) >= 100
    # Each row is (code, name, keyword-count).
    for code, name, count in packs:
        assert code and name and count >= 10


def test_core_packs_present():
    codes = _codes()
    for code in ("hinglish", "hi", "ur", "bn", "ta", "te", "ml", "kn", "mr",
                 "es", "fr", "de", "pt", "ru", "ar", "zh", "zh_tw", "ja",
                 "ko", "id", "tr", "vi", "th", "pl", "nl", "fa", "he", "el"):
        assert code in codes


def _is_word_char(ch):
    return ch.isalnum() or ch == "_" or \
        unicodedata.category(ch) in ("Mn", "Mc", "Me")


def test_keywords_are_identifiers():
    """No keyword may contain junk (spaces, punctuation, emoji)."""
    for code, _name, _count in langpacks.list_packs():
        _name, table = langpacks.pack(code)
        for slot, word in table.items():
            assert word and all(_is_word_char(ch) for ch in word), \
                (code, slot, word)


def test_no_cross_slot_collision():
    """The same word must not mean two different things in one pack."""
    for code, _name, _count in langpacks.list_packs():
        _name, table = langpacks.pack(code)
        words = list(table.values())
        assert len(words) == len(set(words)), code


def test_soft_keywords_are_not_translated():
    """match/scope/spawn/to stay usable in every pack."""
    assert langpacks.SOFT_KEYWORDS == ("match", "scope", "spawn", "to")


def test_hinglish_pack():
    _name, hing = langpacks.pack("hinglish")
    assert hing["let"] == "manle"
    assert hing["if"] == "agar"
    assert hing["else"] == "warna"
    assert hing["fn"] == "kaam"
    assert hing["return"] == "wapas"


def test_hindi_pack():
    _name, hi = langpacks.pack("hi")
    assert hi["let"] == "मानी"
    assert hi["fn"] == "काम"
    assert hi["if"] == "अगर"


def test_chinese_pack():
    _name, zh = langpacks.pack("zh")
    assert zh["let"] == "让"
    assert zh["if"] == "如果"
    assert zh["return"] == "返回"


def test_run_in_hindi(capsys):
    run_source('मानी x = 40\nprint(x + 2)\n', lang="hi", check=True)
    assert capsys.readouterr().out.strip() == "42"


def test_run_in_hinglish(capsys):
    run_source('manle x = 5\nagar x > 3 { print("bada") } warna '
               '{ print("chota") }\n', lang="hinglish", check=True)
    assert capsys.readouterr().out.strip() == "bada"


def test_run_in_chinese(capsys):
    run_source('让 x = 7\n如果 x > 5 { print("大") } 否则 { print("小") }\n',
               lang="zh", check=True)
    assert capsys.readouterr().out.strip() == "大"


def test_run_in_spanish(capsys):
    _name, es = langpacks.pack("es")
    run_source('%s x = 21\nprint(x * 2)\n' % es["let"], lang="es", check=True)
    assert capsys.readouterr().out.strip() == "42"


def test_detect_directive():
    assert langpacks.detect_directive("#lang: hi\nमानी x = 1\n") == "hi"
    assert langpacks.detect_directive("let x = 1\n") is None
    assert langpacks.detect_directive("# lang: klingon\n") is None


def test_detect_auto():
    src = "मानी x = 9\nअगर x > 5 { print(x) } अन्यथा { print(0) }\n"
    assert langpacks.detect_auto(src) == "hi"
    assert langpacks.detect_auto("let x = 1\nprint(x)\n") is None


def test_unknown_pack_is_error():
    with pytest.raises(KeyError):
        langpacks.pack("klingon")
