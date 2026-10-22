"""The set of the language.

A set holds values that are not equal to each other.  The values of a set
are the values a dict can use as a key: numbers, strings and null.  A set
keeps the order the values came in, so printing a set prints the values
the way they were added.
"""

from .errors import BunRuntimeError
from .methods import _arity
from .dict import make_key


class BunSet:
    """A collection of values that are not equal to each other."""

    def __init__(self, items=None):
        self.items = {}
        for item in (items or []):
            self.add(item)

    def add(self, item):
        self.items[make_key(item)] = item
        return self

    def remove(self, item):
        key = make_key(item)
        if key not in self.items:
            raise BunRuntimeError("value not in set")
        del self.items[key]

    def contains(self, item):
        return make_key(item) in self.items

    def values(self):
        return list(self.items.values())

    def union(self, other):
        """The set of the values of this set and of the other one."""
        result = BunSet(self.values())
        for item in other.values():
            result.add(item)
        return result

    def intersection(self, other):
        """The set of the values that are in this set and in the other one."""
        result = BunSet()
        for item in self.values():
            if other.contains(item):
                result.add(item)
        return result

    def difference(self, other):
        """The set of the values of this set that are not in the other one."""
        result = BunSet()
        for item in self.values():
            if not other.contains(item):
                result.add(item)
        return result

    def __len__(self):
        return len(self.items)


def s_len(recv, args):
    _arity("len", args, 0)
    return len(recv)


def s_add(recv, args):
    _arity("add", args, 1)
    recv.add(args[0])
    return recv


def s_remove(recv, args):
    _arity("remove", args, 1)
    recv.remove(args[0])
    return None


def s_contains(recv, args):
    _arity("contains", args, 1)
    return recv.contains(args[0])


def s_values(recv, args):
    _arity("values", args, 0)
    return recv.values()


def s_union(recv, args):
    _arity("union", args, 1)
    other = args[0]
    if not isinstance(other, BunSet):
        raise BunRuntimeError("union() expects a set")
    return recv.union(other)


def s_intersection(recv, args):
    _arity("intersection", args, 1)
    other = args[0]
    if not isinstance(other, BunSet):
        raise BunRuntimeError("intersection() expects a set")
    return recv.intersection(other)


def s_difference(recv, args):
    _arity("difference", args, 1)
    other = args[0]
    if not isinstance(other, BunSet):
        raise BunRuntimeError("difference() expects a set")
    return recv.difference(other)


SET_METHODS = {
    "len": s_len,
    "add": s_add,
    "remove": s_remove,
    "contains": s_contains,
    "values": s_values,
    "union": s_union,
    "intersection": s_intersection,
    "difference": s_difference,
}
