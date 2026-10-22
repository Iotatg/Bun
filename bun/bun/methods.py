from .errors import BunRuntimeError


def _arity(name, args, n):
    if len(args) != n:
        raise BunRuntimeError(
            "'%s' expects %d argument(s), got %d" % (name, n, len(args)))


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


def l_sort(recv, args):
    _arity("sort", args, 0)
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
    "splice": l_splice,
    "insert": l_insert,
}


def secret_reveal(recv, args):
    _arity("reveal", args, 0)
    return recv.value


SECRET_METHODS = {
    "reveal": secret_reveal,
}
