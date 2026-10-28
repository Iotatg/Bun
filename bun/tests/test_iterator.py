import pytest

from bun.checker import Checker
from bun.errors import BunError, BunRuntimeError
from bun.parser import parse
from bun.cli import run_source


def check(source):
    Checker().check(parse(source))


COUNTER = (
    "struct Counter {\n"
    "    var count: int\n"
    "    var limit: int\n"
    "}\n"
    "impl Counter {\n"
    "    fn next(self) -> option {\n"
    "        if self.count >= self.limit {\n"
    "            return none()\n"
    "        }\n"
    "        self.count = self.count + 1\n"
    "        return some(self.count)\n"
    "    }\n"
    "}\n"
)

ENGINES = ["tree", "vm", "register"]


def test_a_struct_with_next_is_iterable():
    check(COUNTER + "for n in Counter(0, 3) {\n    print(n)\n}\n")


def test_the_next_method_answers_with_an_option():
    check(COUNTER)


@pytest.mark.parametrize("engine", ENGINES, ids=ENGINES)
def test_every_engine_walks_the_struct(engine, capsys):
    run_source(COUNTER + "for n in Counter(0, 3) {\n    print(n)\n}\n",
               filename="<iter>.bun", engine=engine)
    assert capsys.readouterr().out == "1\n2\n3\n"


@pytest.mark.parametrize("engine", ENGINES, ids=ENGINES)
def test_every_engine_may_stop_early(engine, capsys):
    run_source(
        COUNTER +
        "let c = Counter(0, 5)\n"
        "for n in c {\n"
        "    if n == 2 {\n"
        "        break\n"
        "    }\n"
        "    print(n)\n"
        "}\n",
        filename="<iter>.bun", engine=engine)
    assert capsys.readouterr().out == "1\n"


@pytest.mark.parametrize("engine", ENGINES, ids=ENGINES)
def test_every_engine_keeps_walking_after_the_loop(engine, capsys):
    run_source(
        COUNTER +
        "let c = Counter(0, 5)\n"
        "for n in c {\n"
        "    if n == 2 {\n"
        "        break\n"
        "    }\n"
        "}\n"
        "print(c.count)\n",
        filename="<iter>.bun", engine=engine)
    assert capsys.readouterr().out == "2\n"


@pytest.mark.parametrize("engine", ENGINES, ids=ENGINES)
def test_every_engine_still_walks_a_list(engine, capsys):
    run_source("for n in [1, 2] {\n    print(n)\n}\n",
               filename="<iter>.bun", engine=engine)
    assert capsys.readouterr().out == "1\n2\n"


def test_the_next_method_has_to_answer_with_an_option():
    with pytest.raises(BunRuntimeError) as info:
        run_source(
            "struct Wrong {\n"
            "    var at: int\n"
            "}\n"
            "impl Wrong {\n"
            "    fn next(self) -> int {\n"
            "        return 1\n"
            "    }\n"
            "}\n"
            "for n in Wrong(0) {\n"
            "    print(n)\n"
            "}\n",
            filename="<iter>.bun", engine="tree")
    assert "option" in info.value.msg


def test_a_struct_without_next_is_not_walked_by_a_for():
    with pytest.raises(BunRuntimeError):
        run_source(
            "struct Empty {\n"
            "    var at: int\n"
            "}\n"
            "for n in Empty(1) {\n"
            "    print(n)\n"
            "}\n",
            filename="<iter>.bun", engine="tree")
