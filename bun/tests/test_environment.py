import pytest

from bun.environment import Environment
from bun.errors import BunRuntimeError


def test_define_and_get():
    env = Environment()
    env.define("x", 1, True)
    assert env.get("x") == 1


def test_child_lookup():
    parent = Environment()
    parent.define("x", 1, True)
    child = Environment(parent)
    assert child.get("x") == 1


def test_assign_updates_outer():
    parent = Environment()
    parent.define("x", 1, True)
    child = Environment(parent)
    child.assign("x", 2)
    assert parent.get("x") == 2


def test_assign_immutable_errors():
    env = Environment()
    env.define("x", 1, False)
    with pytest.raises(BunRuntimeError):
        env.assign("x", 2)


def test_get_undefined_errors():
    with pytest.raises(BunRuntimeError):
        Environment().get("nope")
