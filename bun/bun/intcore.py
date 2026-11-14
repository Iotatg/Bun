"""The integer core that the native backends share.

The WASM engine and the x86-64 JIT do not run the whole language, and
they say so by name.  Both run one subset: 64-bit integers, booleans,
`if`, `while`, `for ... in range(...)`, calls between functions of the
same subset, and `print` of an integer, a boolean or a string literal.

Two backends that disagree about what a program means are two languages,
so the parts both must agree on live here: how a `range` loop is read,
and the static type of an expression.  Everything else belongs to the
backend that emits the code.
"""

from . import ast
from .errors import BunError


class Unsupported(BunError):
    """A construct outside the integer core of a native backend."""

    def __init__(self, engine, what, node=None):
        line = getattr(node, "line", 0) or 0
        col = getattr(node, "col", 0) or 0
        super().__init__(
            "the %s engine does not implement %s; run this program with"
            " --engine vm" % (engine, what), line, col)


def range_call(node):
    """The arguments of `range(...)`, or None when the node is not one."""
    if not isinstance(node, ast.Call):
        return None
    if not isinstance(node.callee, ast.Identifier):
        return None
    if node.callee.name != "range" or node.kwargs:
        return None
    return node.args


def static_type(node, lookup, returns):
    """The static type of an expression of the integer core.

    `lookup` answers the type of a local name and `returns` the result
    type of a function; both return None when they do not know.  The
    answer is used for one decision only: whether `print` writes `true`
    or `1`, and whether a value may go on the integer stack at all.
    """
    if isinstance(node, ast.Literal):
        value = node.value
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int):
            return "int"
        if isinstance(value, str):
            return "string"
        if value is None:
            return "null"
        return None
    if isinstance(node, ast.Identifier):
        return lookup(node.name)
    if isinstance(node, ast.Binary):
        if node.op in ("==", "!=", "<", ">", "<=", ">="):
            return "bool"
        return "int"
    if isinstance(node, ast.Logical):
        # `a and b` answers one of its operands, so its type is the type
        # of an operand and not always a boolean: `3 and 5` is an int.
        right = static_type(node.right, lookup, returns)
        if right is not None:
            return right
        return static_type(node.left, lookup, returns)
    if isinstance(node, ast.Unary):
        return "bool" if node.op in ("not", "!") else "int"
    if isinstance(node, ast.Call):
        if isinstance(node.callee, ast.Identifier):
            if node.callee.name == "print":
                return "null"
            return returns(node.callee.name)
    return None
