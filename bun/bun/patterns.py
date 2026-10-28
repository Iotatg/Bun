"""The patterns of a ``match`` statement.

A pattern is written in the source and becomes a *plan*: a list that says
what to test and what to bind.  The plan is the same in the two
pipelines, so the tree engine and the virtual machine test a value in
the same way and a program behaves the same on both engines.

The plan of a pattern is one of:

| Plan | Meaning |
|------|---------|
| ``["literal", value]`` | the value equals the literal |
| ``["wildcard"]`` | anything, and nothing is bound |
| ``["binding", name]`` | anything, and the name is bound to the value |
| ``["type", name]`` | the type of the value is the named type |
| ``["range", low, high]`` | the value is in the range |
| ``["list", [plan, ...], plan]`` | a list, with the items bound, and a tail |
| ``["dict", [[key, plan], ...]]`` | a dict with the keys, with the values bound |
| ``["struct", name, [[field, plan], ...]]`` | a struct of the type, with its fields bound |
| ``["or", [plan, ...]]`` | one of the patterns, the first one that matches |
| ``["enum", ...]`` | a variant, as a dict (see `plan_from_ast`) |
"""

from .dict import BunDict
from .errors import BunRuntimeError
from .values import (
    BunFunction, BunSecret, BunStruct, is_number, values_equal,
)


def plan_from_ast(pattern):
    """Turn a parsed pattern into its plan."""
    kind = pattern.pattern_kind
    if kind == "literal":
        return ["literal", pattern.value]
    if kind == "wildcard":
        return ["wildcard"]
    if kind == "binding":
        return ["binding", pattern.name]
    if kind == "type":
        return ["type", pattern.value]
    if kind == "range":
        return ["range", pattern.value, pattern.high]
    if kind == "list":
        return ["list", [plan_from_ast(item) for item in pattern.items],
                plan_from_ast(pattern.tail) if pattern.tail is not None
                else None]
    if kind == "dict":
        return ["dict", [[key, plan_from_ast(sub)]
                         for key, sub in pattern.entries]]
    if kind == "or":
        return ["or", [plan_from_ast(item) for item in pattern.items]]
    if kind == "struct":
        # A pattern of a struct is the name of its type and the pattern
        # of every field it names: `Point(x: 0, y)` tests the type and
        # the field `x`, and binds the field `y`.
        return ["struct", pattern.value,
                [[field, plan_from_ast(sub)]
                 for field, sub in pattern.entries]]
    if kind == "enum":
        # A variant of an enum is a value shaped like a dict with the
        # name of the enum, the name of the variant and the list of the
        # fields, so the plan of a variant is the plan of that dict: it
        # is the shape of the value the plan tests, and nothing else.
        #
        # `Color.Red` tests the two names, and `Shape.Circle(r)` tests
        # the third entry as well: a list with one item, bound by
        # position.
        entries = [
            ("type", ["literal", pattern.value]),
            ("kind", ["literal", pattern.name]),
        ]
        if pattern.items:
            fields = ["list",
                      [plan_from_ast(item) for item in pattern.items],
                      None]
            entries.append(("fields", fields))
        return ["dict", entries]
    raise BunRuntimeError("unknown pattern '%s'" % kind)


def plan_names(plan):
    """The names that a plan binds."""
    if not isinstance(plan, (list, tuple)) or not plan:
        return []
    kind = plan[0]
    if kind == "binding":
        return [plan[1]]
    names = []
    if kind == "list":
        for item in plan[1]:
            names.extend(plan_names(item))
        if len(plan) > 2 and plan[2] is not None:
            names.extend(plan_names(plan[2]))
    elif kind == "dict":
        for _, item in plan[1]:
            names.extend(plan_names(item))
    elif kind == "struct":
        for _, item in plan[2]:
            names.extend(plan_names(item))
    elif kind == "or":
        for item in plan[1]:
            names.extend(plan_names(item))
    return names


def pattern_names(pattern):
    """The names a pattern binds."""
    kind = pattern.pattern_kind
    if kind == "binding":
        return [pattern.name]
    if kind == "list":
        names = []
        for item in pattern.items:
            names.extend(pattern_names(item))
        if pattern.tail is not None:
            names.extend(pattern_names(pattern.tail))
        return names
    if kind == "dict":
        names = []
        for _, sub in pattern.entries:
            names.extend(pattern_names(sub))
        return names
    if kind == "struct":
        names = []
        for _, sub in pattern.entries:
            names.extend(pattern_names(sub))
        return names
    if kind == "or":
        names = []
        for item in pattern.items:
            names.extend(pattern_names(item))
        return names
    if kind == "enum":
        names = []
        for item in pattern.items:
            names.extend(pattern_names(item))
        return names
    return []


def type_name_of(value):
    """The name of the type of a value, as the type patterns use it.

    The names are the names of the type system: ``int``, ``float``,
    ``string``, ``bool``, ``list``, ``dict``, ``null`` and ``fn``.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, BunDict):
        return "dict"
    if isinstance(value, BunFunction):
        return "fn"
    if isinstance(value, BunSecret):
        return "secret"
    return "any"


def match_pattern(value, plan, bindings):
    """Test a value against a plan.

    The names of the pattern are collected in ``bindings`` and are only
    applied by the caller when the whole pattern matches, so a pattern
    that fails halfway does not leave half of its names behind.
    """
    kind = plan[0]
    if kind == "literal":
        return values_equal(value, plan[1])
    if kind == "wildcard":
        return True
    if kind == "binding":
        bindings.append((plan[1], value))
        return True
    if kind == "type":
        return type_name_of(value) == plan[1]
    if kind == "range":
        if not is_number(value):
            return False
        return plan[1] <= value <= plan[2]
    if kind == "list":
        if not isinstance(value, list):
            return False
        items = plan[1]
        tail = plan[2]
        if tail is None:
            if len(value) != len(items):
                return False
        elif len(value) < len(items):
            return False
        for item, sub in zip(value, items):
            if not match_pattern(item, sub, bindings):
                return False
        if tail is not None:
            # The tail takes the rest of the list.
            if not match_pattern(value[len(items):], tail, bindings):
                return False
        return True
    if kind == "dict":
        if not isinstance(value, BunDict):
            return False
        for key, sub in plan[1]:
            if not value.has(key):
                return False
            if not match_pattern(value.get(key), sub, bindings):
                return False
        return True
    if kind == "struct":
        # The value has to be a struct of the named type, and every
        # field the pattern names is matched the way a dict entry is:
        # the field has to be there and its value has to answer the
        # plan of the field.
        if not isinstance(value, BunStruct):
            return False
        if value.type_name != plan[1]:
            return False
        fields = value.fields
        for field, sub in plan[2]:
            if field not in fields:
                return False
            if not match_pattern(fields[field], sub, bindings):
                return False
        return True
    if kind == "or":
        # The alternatives are tried in order, and the names of the one
        # that matches are the names of the case.
        for sub in plan[1]:
            found = []
            if match_pattern(value, sub, found):
                bindings.extend(found)
                return True
        return False
    raise BunRuntimeError("unknown pattern '%s'" % kind)
