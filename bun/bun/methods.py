from functools import cmp_to_key

from . import types
from .errors import BunRuntimeError


def _arity(name, args, n):
    if len(args) != n:
        raise BunRuntimeError(
            "'%s' expects %d argument(s), got %d" % (name, n, len(args)))


def _with_call(func):
    """Mark a method that runs the function it was given.

    A method that runs a function needs the engine of the program, so
    the engine hands a callback to the method.
    """
    func.needs_call = True
    return func


def _callable(name, value):
    """The function of an argument, or a refusal."""
    from .values import Builtin, BunFunction, stringify
    if not isinstance(value, (BunFunction, Builtin)):
        raise BunRuntimeError("%s is not callable" % stringify(value))
    return value


def _truthy(value):
    from .values import is_truthy
    return is_truthy(value)


def _order(name, value):
    """The answer of a comparator, or a refusal."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BunRuntimeError(
            "'%s' expects a number from the comparator" % name)
    return value


def _check_str(name, args, i):
    if not isinstance(args[i], str):
        raise BunRuntimeError("'%s' expects a string argument" % name)


def _check_int(name, args, i):
    if not isinstance(args[i], int) or isinstance(args[i], bool):
        raise BunRuntimeError("'%s' expects an integer argument" % name)


def s_trim(recv, args):
    _arity("trim", args, 0)
    return recv.strip()


def s_lower(recv, args):
    _arity("lower", args, 0)
    return recv.lower()


def s_upper(recv, args):
    _arity("upper", args, 0)
    return recv.upper()


def s_split(recv, args):
    _arity("split", args, 1)
    _check_str("split", args, 0)
    if args[0] == "":
        raise BunRuntimeError("'split' expects a non-empty separator")
    return recv.split(args[0])


def s_contains(recv, args):
    _arity("contains", args, 1)
    _check_str("contains", args, 0)
    return args[0] in recv


def s_starts_with(recv, args):
    _arity("starts_with", args, 1)
    _check_str("starts_with", args, 0)
    return recv.startswith(args[0])


def s_ends_with(recv, args):
    _arity("ends_with", args, 1)
    _check_str("ends_with", args, 0)
    return recv.endswith(args[0])


def s_replace(recv, args):
    _arity("replace", args, 2)
    _check_str("replace", args, 0)
    _check_str("replace", args, 1)
    return recv.replace(args[0], args[1])


def s_repeat(recv, args):
    _arity("repeat", args, 1)
    _check_int("repeat", args, 0)
    if args[0] < 0:
        raise BunRuntimeError("'repeat' expects a non-negative count")
    if args[0] >= 100000:
        raise BunRuntimeError("'repeat' count is too large")
    return recv * args[0]


def s_slice(recv, args):
    _arity("slice", args, 2)
    _check_int("slice", args, 0)
    _check_int("slice", args, 1)
    return recv[args[0]:args[1]]


def s_index_of(recv, args):
    _arity("index_of", args, 1)
    _check_str("index_of", args, 0)
    return recv.find(args[0])


def s_len(recv, args):
    _arity("len", args, 0)
    return len(recv)


def l_push(recv, args):
    _arity("push", args, 1)
    recv.append(args[0])
    return None


def l_pop(recv, args):
    _arity("pop", args, 0)
    if len(recv) == 0:
        raise BunRuntimeError("'pop' on an empty list")
    return recv.pop()


def l_shift(recv, args):
    _arity("shift", args, 0)
    if len(recv) == 0:
        raise BunRuntimeError("'shift' on an empty list")
    return recv.pop(0)


def l_len(recv, args):
    _arity("len", args, 0)
    return len(recv)


def l_join(recv, args):
    from .values import stringify
    _arity("join", args, 1)
    _check_str("join", args, 0)
    return args[0].join([stringify(item) for item in recv])


def l_contains(recv, args):
    _arity("contains", args, 1)
    return args[0] in recv


def l_reverse(recv, args):
    _arity("reverse", args, 0)
    return list(reversed(recv))


def l_slice(recv, args):
    _arity("slice", args, 2)
    _check_int("slice", args, 0)
    _check_int("slice", args, 1)
    return recv[args[0]:args[1]]


def _sort_values(recv):
    """Sort a list of numbers or of strings, in place."""
    numbers = 0
    strings = 0
    for item in recv:
        if isinstance(item, bool) or not isinstance(item, (int, float, str)):
            raise BunRuntimeError("cannot sort list with mixed types")
        if isinstance(item, str):
            strings += 1
        else:
            numbers += 1
    if numbers and strings:
        raise BunRuntimeError("cannot sort list with mixed types")
    recv.sort()


@_with_call
def l_sort(recv, args, call):
    """Sort a list, in place.

    Without an argument the list of numbers or of strings is sorted the
    old way.  With a comparator the list is sorted the way the
    comparator says: a negative answer puts the first value first, a
    positive answer puts the second value first, and zero keeps the two
    values in the order they had.
    """
    if len(args) > 1:
        raise BunRuntimeError(
            "'sort' expects 0 or 1 argument(s), got %d" % len(args))
    if not args:
        _sort_values(recv)
        return None
    comparator = _callable("sort", args[0])
    recv.sort(key=cmp_to_key(
        lambda left, right: _order("sort", call(comparator, [left, right]))))
    return None


@_with_call
def l_sort_by(recv, args, call):
    """Sort a list by the key of every value, in place."""
    _arity("sort_by", args, 1)
    key = _callable("sort_by", args[0])
    pairs = []
    numbers = 0
    strings = 0
    for item in recv:
        value = call(key, [item])
        if isinstance(value, str):
            strings += 1
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            numbers += 1
        else:
            raise BunRuntimeError("cannot sort list with mixed types")
        pairs.append((value, item))
    if numbers and strings:
        raise BunRuntimeError("cannot sort list with mixed types")
    pairs.sort(key=lambda pair: pair[0])
    recv[:] = [item for _, item in pairs]
    return None


@_with_call
def l_map(recv, args, call):
    """A new list of the results of the function."""
    _arity("map", args, 1)
    fn = _callable("map", args[0])
    return [call(fn, [item]) for item in recv]


@_with_call
def l_filter(recv, args, call):
    """A new list of the values the predicate keeps."""
    _arity("filter", args, 1)
    fn = _callable("filter", args[0])
    return [item for item in recv if _truthy(call(fn, [item]))]


@_with_call
def l_reduce(recv, args, call):
    """The fold of the list, the accumulator first."""
    _arity("reduce", args, 2)
    fn = _callable("reduce", args[1])
    acc = args[0]
    for item in recv:
        acc = call(fn, [acc, item])
    return acc


@_with_call
def l_find(recv, args, call):
    """The first value the predicate keeps, else null."""
    _arity("find", args, 1)
    fn = _callable("find", args[0])
    for item in recv:
        if _truthy(call(fn, [item])):
            return item
    return None


@_with_call
def l_any(recv, args, call):
    """Does the predicate keep any value of the list?"""
    _arity("any", args, 1)
    fn = _callable("any", args[0])
    for item in recv:
        if _truthy(call(fn, [item])):
            return True
    return False


@_with_call
def l_all(recv, args, call):
    """Does the predicate keep every value of the list?"""
    _arity("all", args, 1)
    fn = _callable("all", args[0])
    for item in recv:
        if not _truthy(call(fn, [item])):
            return False
    return True


@_with_call
def l_each(recv, args, call):
    """Run the function for every value of the list, in place."""
    _arity("each", args, 1)
    fn = _callable("each", args[0])
    for item in recv:
        call(fn, [item])
    return None


def l_splice(recv, args):
    _arity("splice", args, 2)
    _check_int("splice", args, 0)
    _check_int("splice", args, 1)
    start = args[0]
    count = args[1]
    if start < 0:
        start = max(0, len(recv) + start)
    if start > len(recv):
        start = len(recv)
    if count < 0:
        count = 0
    removed = recv[start:start + count]
    del recv[start:start + count]
    return removed


def l_insert(recv, args):
    _arity("insert", args, 2)
    _check_int("insert", args, 0)
    index = args[0]
    if index < 0:
        index = max(0, len(recv) + index)
    if index > len(recv):
        index = len(recv)
    recv.insert(index, args[1])
    return None


STRING_METHODS = {
    "trim": s_trim,
    "lower": s_lower,
    "upper": s_upper,
    "split": s_split,
    "contains": s_contains,
    "starts_with": s_starts_with,
    "ends_with": s_ends_with,
    "replace": s_replace,
    "repeat": s_repeat,
    "slice": s_slice,
    "index_of": s_index_of,
    "len": s_len,
}

LIST_METHODS = {
    "push": l_push,
    "pop": l_pop,
    "shift": l_shift,
    "len": l_len,
    "join": l_join,
    "contains": l_contains,
    "reverse": l_reverse,
    "slice": l_slice,
    "sort": l_sort,
    "sort_by": l_sort_by,
    "splice": l_splice,
    "insert": l_insert,
    "map": l_map,
    "filter": l_filter,
    "reduce": l_reduce,
    "find": l_find,
    "any": l_any,
    "all": l_all,
    "each": l_each,
}


def secret_reveal(recv, args):
    _arity("reveal", args, 0)
    return recv.value


SECRET_METHODS = {
    "reveal": secret_reveal,
}


# The arity and the answer of the methods of the containers, so the
# checker knows a method call before the program runs.  The arity is
# the list of the numbers of the arguments the method takes, so `sort`
# takes none or one.
STRING_METHOD_INFO = {
    "trim": ((0,), types.STRING),
    "lower": ((0,), types.STRING),
    "upper": ((0,), types.STRING),
    "split": ((1,), types.LIST),
    "contains": ((1,), types.BOOL),
    "starts_with": ((1,), types.BOOL),
    "ends_with": ((1,), types.BOOL),
    "replace": ((2,), types.STRING),
    "repeat": ((1,), types.STRING),
    "slice": ((2,), types.STRING),
    "index_of": ((1,), types.INT),
    "len": ((0,), types.INT),
}

LIST_METHOD_INFO = {
    "push": ((1,), types.NULL),
    "pop": ((0,), types.ANY),
    "shift": ((0,), types.ANY),
    "len": ((0,), types.INT),
    "join": ((1,), types.STRING),
    "contains": ((1,), types.BOOL),
    "reverse": ((0,), types.LIST),
    "slice": ((2,), types.LIST),
    "sort": ((0, 1), types.NULL),
    "sort_by": ((1,), types.NULL),
    "splice": ((2,), types.LIST),
    "insert": ((2,), types.NULL),
    "map": ((1,), types.LIST),
    "filter": ((1,), types.LIST),
    "reduce": ((2,), types.ANY),
    "find": ((1,), types.ANY),
    "any": ((1,), types.BOOL),
    "all": ((1,), types.BOOL),
    "each": ((1,), types.NULL),
}
