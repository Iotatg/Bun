from .dict import BunDict, DICT_METHODS
from .errors import BunRuntimeError
from .ints import check as check_int
from .methods import LIST_METHODS, SECRET_METHODS, STRING_METHODS
from .set import BunSet, SET_METHODS
from .values import (
    BunSecret, BunStruct, copy_value, is_number, is_truthy, stringify,
    values_equal,
)

STRUCT_METHODS = {}


def make_struct(type_name, field_names, field_values):
    """Build a struct value from the values of its fields.

    A struct is a value type, so the values of its fields are copied.
    The copy happens here and not at the call of the constructor, so
    that every engine builds the same value.
    """
    fields = {}
    for name, value in zip(field_names, field_values):
        fields[name] = copy_value(value)
    return BunStruct(type_name, fields, list(field_names))


def get_field(obj, name):
    """Read one field of a struct."""
    if not isinstance(obj, BunStruct):
        raise BunRuntimeError(
            "type '%s' has no field '%s'" % (type_name(obj), name))
    if name not in obj.fields:
        raise BunRuntimeError(
            "unknown field '%s' on %s" % (name, obj.type_name))
    return obj.fields[name]


def set_field(obj, name, value):
    """Write one field of a struct."""
    if not isinstance(obj, BunStruct):
        raise BunRuntimeError(
            "type '%s' has no field '%s'" % (type_name(obj), name))
    if name not in obj.fields:
        raise BunRuntimeError(
            "unknown field '%s' on %s" % (name, obj.type_name))
    obj.fields[name] = value


def register_impl(type_name, method, function):
    """Record the implementation of a method of a struct type."""
    table = STRUCT_METHODS.setdefault(type_name, {})
    table[method] = function
    _METHOD_DISPATCH.pop((type_name, method), None)


def struct_method(type_name, method):
    """Find the implementation of a method of a struct type."""
    table = STRUCT_METHODS.get(type_name, {})
    if method not in table:
        raise BunRuntimeError(
            "unknown method '%s' on %s" % (method, type_name))
    return table[method]


def binary_op(op, left, right):
    if op == "+":
        if isinstance(left, str) and isinstance(right, str):
            return left + right
        if isinstance(left, list) and isinstance(right, list):
            return left + right
        if is_number(left) and is_number(right):
            if type(left) is int and type(right) is int:
                return check_int(left + right)
            return left + right
        if isinstance(left, str) or isinstance(right, str):
            return stringify(left) + stringify(right)
        raise BunRuntimeError("unsupported operands for '+'")
    if op in ("-", "*", "%"):
        if isinstance(left, BunSet) and isinstance(right, BunSet):
            if op == "-":
                return left.difference(right)
        if not (is_number(left) and is_number(right)):
            raise BunRuntimeError("unsupported operands for '%s'" % op)
        if op == "%":
            if right == 0:
                raise BunRuntimeError("division by zero")
            return left % right
        if type(left) is int and type(right) is int:
            return check_int(left - right if op == "-" else left * right)
        return left - right if op == "-" else left * right
    if op == "/":
        if not (is_number(left) and is_number(right)):
            raise BunRuntimeError("unsupported operands for '/'")
        if right == 0:
            raise BunRuntimeError("division by zero")
        if isinstance(left, int) and isinstance(right, int):
            return check_int(left // right)
        return left / right
    if op == "**":
        return power(left, right)
    if op in ("&", "|", "^", "<<", ">>"):
        if isinstance(left, BunSet) and isinstance(right, BunSet):
            if op == "|":
                return left.union(right)
            if op == "&":
                return left.intersection(right)
            if op == "^":
                return left.difference(right).union(
                    right.difference(left))
        if type(left) is not int or type(right) is not int:
            raise BunRuntimeError("unsupported operands for '%s'" % op)
        if op == "&":
            return left & right
        if op == "|":
            return left | right
        if op == "^":
            return left ^ right
        if right < 0:
            raise BunRuntimeError("negative shift count")
        if op == "<<":
            return check_int(left << right)
        return left >> right
    if op in ("<", "<=", ">", ">="):
        if (is_number(left) and is_number(right)) or (
                isinstance(left, str) and isinstance(right, str)):
            if op == "<":
                return left < right
            if op == "<=":
                return left <= right
            if op == ">":
                return left > right
            return left >= right
        raise BunRuntimeError("unsupported operands for '%s'" % op)
    if op == "==":
        return values_equal(left, right)
    if op == "!=":
        return not values_equal(left, right)
    raise BunRuntimeError("unknown operator '%s'" % op)


def unary_op(op, operand):
    if op == "-":
        if not is_number(operand):
            raise BunRuntimeError("unary '-' expects a number")
        if type(operand) is int:
            return check_int(-operand)
        return -operand
    if op == "~":
        if type(operand) is not int:
            raise BunRuntimeError("unary '~' expects an integer")
        return check_int(~operand)
    if op == "!":
        return not is_truthy(operand)
    raise BunRuntimeError("unknown unary operator '%s'" % op)


def power(left, right):
    """Raise `left` to the power of `right`, the way Python does.

    Two integers give an integer, and an integer that leaves the 64 bit
    range is an error.  A negative exponent gives a float, and a negative
    base with a fractional exponent is an error, because Bun has no
    complex numbers.
    """
    if not (is_number(left) and is_number(right)):
        raise BunRuntimeError("unsupported operands for '**'")
    if isinstance(left, bool) or isinstance(right, bool):
        raise BunRuntimeError("unsupported operands for '**'")
    if type(left) is int and type(right) is int:
        if right >= 0:
            return check_int(left ** right)
        return float(left) ** right
    base = float(left)
    exponent = float(right)
    if base < 0 and exponent != int(exponent):
        raise BunRuntimeError(
            "cannot raise a negative number to a fractional power")
    return base ** exponent


def index_value(obj, index):
    if isinstance(obj, (list, str)):
        if not isinstance(index, int) or isinstance(index, bool):
            raise BunRuntimeError("index must be an integer")
        if index < 0 or index >= len(obj):
            raise BunRuntimeError("index %d out of range" % index)
        return obj[index]
    if isinstance(obj, BunDict):
        try:
            return obj.get(index)
        except KeyError:
            # JavaScript object semantics: reading a missing key yields
            # undefined (represented as null here), it does not throw.
            return None
    raise BunRuntimeError("value is not indexable")


def slice_indices(length, start, stop, step):
    """Resolve slice bounds the way Python's `slice.indices()` does.

    Missing bounds are reported as `None` by the caller and filled in
    here. Negative indices count from the end of the sequence and
    out-of-range values are clamped.
    """
    if step is None:
        step = 1
    if step > 0:
        lower, upper = 0, length
    else:
        lower, upper = -1, length - 1
    if start is None:
        start = upper if step < 0 else lower
    else:
        if start < 0:
            start += length
            if start < lower:
                start = lower
            if start > upper:
                start = upper
        elif start > upper:
            start = upper
    if stop is None:
        stop = lower if step < 0 else upper
    else:
        if stop < 0:
            stop += length
            if stop < lower:
                stop = lower
            if stop > upper:
                stop = upper
        elif stop > upper:
            stop = upper
    return start, stop, step


def slice_value(obj, start, stop, step):
    """Return `obj[start:stop:step]` with Python slicing semantics."""
    if not isinstance(obj, (list, str)):
        raise BunRuntimeError("value is not sliceable")
    for name, value in (("start", start), ("stop", stop), ("step", step)):
        if value is None:
            continue
        if not isinstance(value, int) or isinstance(value, bool):
            raise BunRuntimeError("slice %s must be an integer" % name)
    if step is not None and step == 0:
        raise BunRuntimeError("slice step cannot be zero")
    first, last, stride = slice_indices(len(obj), start, stop, step)
    positions = list(range(first, last, stride))
    if isinstance(obj, str):
        return "".join(obj[position] for position in positions)
    return [obj[position] for position in positions]


def assign_slice(obj, start, stop, step, value):
    """Replace `obj[start:stop:step]` with `value`."""
    if not isinstance(obj, list):
        raise BunRuntimeError("value is not sliceable")
    if not isinstance(value, list):
        raise BunRuntimeError("can only assign a list to a slice")
    for name, bound in (("start", start), ("stop", stop), ("step", step)):
        if bound is None:
            continue
        if not isinstance(bound, int) or isinstance(bound, bool):
            raise BunRuntimeError("slice %s must be an integer" % name)
    if step is not None and step == 0:
        raise BunRuntimeError("slice step cannot be zero")
    first, last, stride = slice_indices(len(obj), start, stop, step)
    if stride == 1:
        obj[first:last] = value
        return
    positions = list(range(first, last, stride))
    if len(positions) != len(value):
        raise BunRuntimeError(
            "attempt to assign sequence of size %d to extended slice of size %d"
            % (len(value), len(positions)))
    for position, item in zip(positions, value):
        obj[position] = item


def assign_index(obj, index, value):
    if isinstance(obj, BunDict):
        obj.set(index, value)
        return
    if not isinstance(obj, list):
        raise BunRuntimeError("can only assign into a list")
    if not isinstance(index, int) or isinstance(index, bool):
        raise BunRuntimeError("list index must be an integer")
    if index < 0 or index >= len(obj):
        raise BunRuntimeError("list index %d out of range" % index)
    obj[index] = value


def delete_index(obj, index):
    """Remove an item from a dict or a list, the way `del` does."""
    if isinstance(obj, BunDict):
        obj.remove(index)
        return
    if not isinstance(obj, list):
        raise BunRuntimeError("can only delete from a list or a dict")
    if not isinstance(index, int) or isinstance(index, bool):
        raise BunRuntimeError("list index must be an integer")
    if index < 0 or index >= len(obj):
        raise BunRuntimeError("list index %d out of range" % index)
    del obj[index]


def type_name(value):
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if value is None:
        return "null"
    if isinstance(value, list):
        return "list"
    if isinstance(value, BunDict):
        return "dict"
    if isinstance(value, BunSet):
        return "set"
    if isinstance(value, BunSecret):
        return "secret"
    if isinstance(value, BunStruct):
        return value.type_name
    return type(value).__name__


_METHOD_DISPATCH = {}


def _resolve_method(method, receiver):
    """Find the implementation of `method` for `receiver`."""
    if isinstance(receiver, str):
        table = STRING_METHODS
        name = "string"
    elif isinstance(receiver, list):
        table = LIST_METHODS
        name = "list"
    elif isinstance(receiver, BunDict):
        table = DICT_METHODS
        name = "dict"
    elif isinstance(receiver, BunSet):
        table = SET_METHODS
        name = "set"
    elif isinstance(receiver, BunSecret):
        table = SECRET_METHODS
        name = "secret"
    elif isinstance(receiver, BunStruct):
        table = STRUCT_METHODS.get(receiver.type_name, {})
        name = receiver.type_name
    else:
        raise BunRuntimeError(
            "'%s' is not a method on %s" % (method, type_name(receiver)))
    if method not in table:
        raise BunRuntimeError(
            "unknown method '%s' on %s" % (method, name))
    return table[method]


def method_call(method, receiver, args):
    # The method tables are static, so the lookup result only depends on the
    # concrete type of the receiver and the method name. Caching it removes
    # the isinstance chain and the table lookup from every method call.
    if isinstance(receiver, BunStruct):
        key = (receiver.type_name, method)
    else:
        key = (type(receiver), method)
    handler = _METHOD_DISPATCH.get(key)
    if handler is None:
        handler = _resolve_method(method, receiver)
        _METHOD_DISPATCH[key] = handler
    return handler(receiver, args)


def param_spec(param):
    """Normalise a parameter description into a plain dictionary."""
    if isinstance(param, dict):
        return param
    return {
        "name": param.name,
        "param_kind": param.param_kind,
        "type_name": param.type_name,
        "default": param.default,
    }


def bind_arguments(name, specs, args, kwargs):
    """Map call arguments onto the parameters of a function.

    `specs` is a list of parameter descriptions with "name", "param_kind"
    and "default" keys. The result is an ordered list of
    `(spec, source, payload)` steps where `source` is one of "value",
    "default", "vararg" or "kwarg".
    """
    positional = []
    vararg = None
    kwarg = None
    kwonly = []
    for spec in specs:
        kind = spec["param_kind"]
        if kind == "positional":
            positional.append(spec)
        elif kind == "vararg":
            vararg = spec
        elif kind == "kwarg":
            kwarg = spec
        else:
            kwonly.append(spec)

    known = {}
    for spec in positional + kwonly:
        known[spec["name"]] = spec
    values = {}
    leftover = {}
    for key, value in kwargs.items():
        if key in known:
            values[key] = value
        else:
            leftover[key] = value

    if len(args) > len(positional) and vararg is None:
        raise BunRuntimeError(
            "function '%s' expects %d argument(s), got %d"
            % (name, len(positional), len(args)))

    steps = []
    for index, spec in enumerate(positional):
        if index < len(args):
            if spec["name"] in values:
                raise BunRuntimeError(
                    "function '%s' got multiple values for argument '%s'"
                    % (name, spec["name"]))
            steps.append((spec, "value", args[index]))
        elif spec["name"] in values:
            steps.append((spec, "value", values.pop(spec["name"])))
        elif spec["default"] is not None:
            steps.append((spec, "default", spec["default"]))
        else:
            raise BunRuntimeError(
                "function '%s' missing required argument '%s'"
                % (name, spec["name"]))
    for spec in kwonly:
        if spec["name"] in values:
            steps.append((spec, "value", values.pop(spec["name"])))
        elif spec["default"] is not None:
            steps.append((spec, "default", spec["default"]))
        else:
            raise BunRuntimeError(
                "function '%s' missing required argument '%s'"
                % (name, spec["name"]))
    if vararg is not None:
        steps.append((vararg, "vararg", list(args[len(positional):])))
    if kwarg is not None:
        steps.append((kwarg, "kwarg", leftover))
    elif leftover:
        key = sorted(leftover)[0]
        raise BunRuntimeError(
            "function '%s' got an unexpected keyword argument '%s'"
            % (name, key))
    return steps


def unpack_items(value):
    """Return the individual items of a value that can be unpacked."""
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str):
        return list(value)
    raise BunRuntimeError("cannot unpack %s" % _type_label(value))


def _type_label(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "value"


def build_unpack_plan(targets):
    """Build an unpacking plan from a list of assignment targets.

    The plan is a plain nested list so that it can travel through the
    bytecode unchanged:

    - ``["leaf"]`` binds a single value
    - ``["star"]`` binds the remaining values as a list
    - ``["list", plan, ...]`` unpacks a nested sequence
    - ``["seq", plan, ...]`` is the root of the plan

    A single enclosing pattern at the root is transparent: its children
    are the ones that receive the values.
    """
    if len(targets) == 1:
        kind = getattr(targets[0], "target_kind", None)
        if kind in ("list", "tuple"):
            targets = targets[0].targets
    plan = ["seq"]
    for target in targets:
        plan.append(target_plan(target))
    return plan


def target_plan(target):
    kind = getattr(target, "target_kind", None)
    if kind == "star":
        return ["star"]
    if kind in ("list", "tuple"):
        plan = [kind]
        for item in target.targets:
            plan.append(target_plan(item))
        return plan
    return ["leaf"]


def plan_leaf_count(plan):
    kind = plan[0]
    if kind == "leaf":
        return 1
    if kind == "star":
        return 0
    total = 0
    for sub in plan[1:]:
        total += plan_leaf_count(sub)
    return total


def plan_value_count(plan):
    """The number of values an unpacking plan binds.

    A star binds the rest of the values as one list, so it counts as one
    value even though it has no name.
    """
    kind = plan[0]
    if kind in ("leaf", "star"):
        return 1
    total = 0
    for sub in plan[1:]:
        total += plan_value_count(sub)
    return total


def plan_leaves(targets):
    """Return the leaf targets of an unpacking pattern, in plan order."""
    leaves = []
    _collect_leaves(targets, leaves)
    return leaves


def _collect_leaves(targets, leaves):
    for target in targets:
        kind = getattr(target, "target_kind", None)
        if kind == "star":
            leaves.append(target)
        elif kind in ("list", "tuple"):
            _collect_leaves(target.targets, leaves)
        else:
            leaves.append(target)


def unpack_plan(plan, items):
    """Apply an unpacking plan to `items` and return the bound values."""
    values = []
    _unpack_seq(plan[1:], items, values)
    return values


def _unpack_seq(plans, items, values):
    """Unpack a sequence of plans against `items`."""
    required = 0
    for sub in plans:
        if sub[0] != "star":
            required += 1
    star_at = -1
    for position, sub in enumerate(plans):
        if sub[0] == "star":
            star_at = position
            break
    if star_at < 0:
        if len(items) < required:
            raise BunRuntimeError(
                "not enough values to unpack (expected %d, got %d)"
                % (required, len(items)))
        if len(items) > required:
            raise BunRuntimeError(
                "too many values to unpack (expected %d)" % required)
        trailing = 0
    else:
        trailing = 0
        for later in plans[star_at + 1:]:
            if later[0] != "star":
                trailing += 1
        if len(items) < required:
            raise BunRuntimeError(
                "not enough values to unpack (expected %d, got %d)"
                % (required, len(items)))
    count = 0
    for sub in plans:
        kind = sub[0]
        if kind == "star":
            end = len(items) - trailing
            values.append(items[count:end])
            count = end
        elif kind in ("list", "tuple"):
            if count >= len(items):
                raise BunRuntimeError(
                    "not enough values to unpack (expected %d, got %d)"
                    % (required, len(items)))
            sub_items = unpack_items(items[count])
            count += 1
            sub_values = []
            _unpack_seq(sub[1:], sub_items, sub_values)
            values.extend(sub_values)
        else:
            if count >= len(items):
                raise BunRuntimeError(
                    "not enough values to unpack (expected %d, got %d)"
                    % (required, len(items)))
            values.append(items[count])
            count += 1
    return count


def unwrap_result(value):
    """Take the `ok` value of a Result, or report that it is an `err`.

    A Result is a dict with an `ok` key or an `err` key.  The `ok` key
    wins when both are present.  A value that is not a Result is an
    error.  The return is `(ok, payload)`: `ok` is true when the
    payload is the unwrapped value, and false when the payload is the
    Result that the enclosing function has to return.
    """
    if not isinstance(value, BunDict):
        raise BunRuntimeError(
            "'?' expects a Result value, got %s" % type_name(value))
    if value.has("ok"):
        return True, value.get("ok")
    if value.has("err"):
        return False, value
    raise BunRuntimeError("'?' expects a Result value")

