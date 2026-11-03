from . import types
from .errors import BunRuntimeError
from .methods import _arity


def make_key(key):
    if isinstance(key, bool):
        return ("b", key)
    if isinstance(key, (int, float)):
        return ("n", key)
    if isinstance(key, str):
        return ("s", key)
    if key is None:
        return ("z", None)
    raise BunRuntimeError("dict keys must be strings, numbers, or null")


class BunDict:
    def __init__(self):
        self.items = {}

    def get(self, key):
        return self.items.get(make_key(key))

    def set(self, key, value):
        self.items[make_key(key)] = value

    def has(self, key):
        return make_key(key) in self.items

    def remove(self, key):
        k = make_key(key)
        if k not in self.items:
            raise BunRuntimeError("key not found")
        del self.items[k]

    def keys(self):
        return [k[1] for k in self.items]

    def values(self):
        return list(self.items.values())

    def __len__(self):
        return len(self.items)


def d_len(recv, args):
    _arity("len", args, 0)
    return len(recv)


def d_has(recv, args):
    _arity("has", args, 1)
    return recv.has(args[0])


def d_get(recv, args):
    _arity("get", args, 1)
    try:
        return recv.get(args[0])
    except KeyError:
        # JavaScript Map.get semantics: a missing key yields undefined
        # (represented as null here), it does not throw.
        return None


def d_keys(recv, args):
    _arity("keys", args, 0)
    return recv.keys()


def d_values(recv, args):
    _arity("values", args, 0)
    return recv.values()


def d_items(recv, args):
    """The pairs of the dict, the key first."""
    _arity("items", args, 0)
    return [[key[1], value] for key, value in recv.items.items()]


def d_set(recv, args):
    _arity("set", args, 2)
    recv.set(args[0], args[1])
    return recv


def d_update(recv, args):
    _arity("update", args, 1)
    other = args[0]
    if not isinstance(other, BunDict):
        raise BunRuntimeError("update() expects a dict")
    for key in other.keys():
        recv.set(key, other.get(key))
    return recv


def d_remove(recv, args):
    _arity("remove", args, 1)
    recv.remove(args[0])
    return None


DICT_METHODS = {
    "len": d_len,
    "has": d_has,
    "get": d_get,
    "set": d_set,
    "update": d_update,
    "keys": d_keys,
    "values": d_values,
    "items": d_items,
    "remove": d_remove,
}


# The arity and the answer of the methods of a dict, so the checker
# knows a method call before the program runs.
DICT_METHOD_INFO = {
    "len": ((0,), types.INT),
    "has": ((1,), types.BOOL),
    "get": ((1,), types.ANY),
    "set": ((2,), types.DICT),
    "update": ((1,), types.DICT),
    "keys": ((0,), types.LIST),
    "values": ((0,), types.LIST),
    "items": ((0,), types.LIST),
    "remove": ((1,), types.NULL),
}
