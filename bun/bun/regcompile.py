"""The registerizer: the stack bytecode of Bun becomes register code.

The compiler of Bun emits the bytecode of a stack machine.  The
registerizer walks that bytecode and lowers it into the register code of
`bun.regcode`: the values of an expression move from an operand stack into
the registers of a frame, and every instruction names its operands.

The walk is linear, and the depth of the expression is known at every
instruction because the code of the compiler is structured: the branches
of an `if` join at the same depth, the body of a loop starts at the depth
of the loop, and a handler restores the depth it had.  The verifier of
`bun.regverify` proves that the property holds, so the register code of a
program that the compiler accepts always has a well formed depth.
"""

from . import ops
from . import regcode
from .compiler import (
    OP_ASSERT,
    OP_DEL,
    OP_DEL_INDEX,
    OP_YIELD,
    OP_BINARY,
    OP_BUILD_DICT,
    OP_BUILD_LIST,
    OP_BUILD_STRING,
    OP_CALL,
    OP_CLEAR_ERROR,
    OP_DEFINE_NAME,
    OP_DICT_SET,
    OP_DUP,
    OP_END_TRY,
    OP_ENTER_SCOPE,
    OP_EXIT_SCOPE,
    OP_FINALLY_END,
    OP_FOR_NEXT,
    OP_FOR_POP,
    OP_FOR_SETUP,
    OP_FORMAT,
    OP_HALT,
    OP_HAS_ERROR,
    OP_IMPORT,
    OP_INDEX,
    OP_JUMP,
    OP_JUMP_IF_FALSE,
    OP_JUMP_IF_TRUE,
    OP_LIST_APPEND,
    OP_LOAD_CONST,
    OP_LOAD_NAME,
    OP_MAKE_FUNCTION,
    OP_MATCH_FAIL,
    OP_MATCH_TEST,
    OP_METHOD_CALL,
    OP_PENDING_ERROR,
    OP_POP,
    OP_PROTOCOL_GET,
    OP_RECORD_EXPORT,
    OP_RETURN,
    OP_SCOPE_ENTER,
    OP_SCOPE_EXIT,
    OP_SLICE,
    OP_STORE_INDEX,
    OP_STORE_NAME,
    OP_STORE_SLICE,
    OP_THROW,
    OP_TRY,
    OP_TRY_FINALLY,
    OP_UNARY,
    OP_UNPACK_PLAN,
    OP_WITH_DEPTH,
    OP_WITH_ENTER,
    OP_WITH_POP_TARGET,
)


class RegisterizeError(Exception):
    """Raised when the stack bytecode cannot be lowered."""


class Registerizer:
    """Lower one code object of the stack machine into register code."""

    def __init__(self, code):
        self.source_code = code
        self.pool = regcode.Pool()
        self.out = []
        self.lines = []
        self.depths = []
        self.line = 0
        self.col = 0
        self.depth = 0
        # The register index of every stack index, so a jump can be
        # rewritten.
        self.targets = {}
        # The stack index of every register index, so a jump can be
        # patched when the target is known.
        self.patches = []

    # -- the helpers -------------------------------------------------------

    def emit(self, op, a=0, b=0, c=0, line=None, col=None):
        self.out.append((op, a, b, c))
        if line is None:
            line, col = self.line, self.col
        self.lines.append((line, col))
        self.depths.append(self.depth)
        return len(self.out) - 1

    def constant(self, value):
        return self.pool.add(value)

    def patch(self, index, target, cell=0):
        op, a, b, c = self.out[index]
        if cell == 0:
            self.out[index] = (op, target, b, c)
        elif cell == 1:
            self.out[index] = (op, a, target, c)
        else:
            self.out[index] = (op, a, b, target)

    # -- the walk ----------------------------------------------------------

    def run(self):
        code = self.source_code["code"]
        catch_entries = self._catch_entries(code)
        for index, instruction in enumerate(code):
            if index in catch_entries:
                # The handler of a catch puts the message of the error on
                # the stack before the body of the catch runs.
                self.depth += 1
            self.targets[index] = len(self.out)
            op = instruction[0]
            arg = instruction[1]
            self.line = instruction[2]
            self.col = instruction[3]
            handler = _HANDLERS.get(op)
            if handler is None:
                raise RegisterizeError("no register form for '%s'" % op)
            handler(self, arg, instruction)
        for index, stack_target, cell in self.patches:
            self.patch(index, self.targets[stack_target], cell)
        result = {
            "name": self.source_code.get("name", "<module>"),
            "params": list(self.source_code.get("params", [])),
            "consts": self.pool.values,
            "code": self.out,
            "lines": self.lines,
            "depths": self.depths,
            "filename": self.source_code.get("filename"),
            "source": self.source_code.get("source"),
            "param_defs": self._param_defs(),
            "is_generator": bool(self.source_code.get("is_generator")),
        }
        return result

    def _param_defs(self):
        """The parameters of the function, with their defaults lowered."""
        defs = []
        for spec in self.source_code.get("param_defs", []):
            entry = dict(spec)
            default = entry.get("default")
            if default is not None:
                entry["default"] = registerize(default)
            defs.append(entry)
        return defs

    def _catch_entries(self, code):
        """The instructions where the body of a catch begins.

        The body of a catch starts with the message of the error on the
        stack, so the depth of the expression is one more there than it
        was at the `try`.
        """
        entries = set()
        for instruction in code:
            if instruction[0] == "TRY":
                entries.add(instruction[1])
        return entries


# -- the lowering of every instruction ---------------------------------------
#
# The names of the slots follow the stack: the value of the expression is
# in the slots 0, 1, 2 and so on, and the instruction that pops a value
# names the slot it pops.

def _load_const(self, arg, instruction):
    self.emit(regcode.CONST, self.depth, self.constant(arg))
    self.depth += 1


def _load_name(self, arg, instruction):
    self.emit(regcode.LOAD_NAME, self.depth, self.constant(arg))
    self.depth += 1


def _store_name(self, arg, instruction):
    self.emit(regcode.STORE_NAME, self.depth - 1, self.constant(arg))
    self.depth -= 1


def _define_name(self, arg, instruction):
    name, mutable = arg
    self.emit(regcode.DEFINE_NAME, self.depth - 1, self.constant(name),
              1 if mutable else 0)
    self.depth -= 1


def _del(self, arg, instruction):
    self.emit(regcode.DEL, self.constant(arg))


def _del_index(self, arg, instruction):
    # The container is the deeper of the two, the index is on the top.
    self.emit(regcode.DEL_INDEX, self.depth - 2, self.depth - 1)
    self.depth -= 2


def _yield(self, arg, instruction):
    # The value that is given to the program sits in the slot, and the
    # answer of the program takes its place.
    self.emit(regcode.YIELD, self.depth - 1)


def _record_export(self, arg, instruction):
    self.emit(regcode.RECORD_EXPORT, self.constant(arg))


def _pop(self, arg, instruction):
    self.emit(regcode.POP, self.depth - 1)
    self.depth -= 1


def _dup(self, arg, instruction):
    self.emit(regcode.DUP, self.depth - 1)
    self.depth += 1


def _binary(self, arg, instruction):
    opcode = regcode.BINARY_OPCODES.get(arg)
    if opcode is None:
        raise RegisterizeError("no register form for the operator '%s'" % arg)
    self.emit(opcode, self.depth - 2, self.depth - 2, self.depth - 1)
    self.depth -= 1


def _unary(self, arg, instruction):
    opcode = regcode.UNARY_OPCODES.get(arg)
    if opcode is None:
        raise RegisterizeError("no register form for the operator '%s'" % arg)
    # The operator takes one value and gives one value, so the depth of
    # the expression does not change.
    self.emit(opcode, self.depth - 1, self.depth - 1)


def _build_list(self, arg, instruction):
    count = arg or 0
    self.emit(regcode.BUILD_LIST, self.depth - count, count)
    self.depth = self.depth - count + 1


def _build_dict(self, arg, instruction):
    count = arg or 0
    self.emit(regcode.BUILD_DICT, self.depth - count * 2, count)
    self.depth = self.depth - count * 2 + 1


def _build_string(self, arg, instruction):
    count = arg or 0
    self.emit(regcode.BUILD_STRING, self.depth - count, count)
    self.depth = self.depth - count + 1


def _list_append(self, arg, instruction):
    self.emit(regcode.LIST_APPEND, self.depth - 2)
    self.depth -= 1


def _dict_set(self, arg, instruction):
    self.emit(regcode.DICT_SET, self.depth - 3, self.depth - 2, self.depth - 1)
    self.depth -= 2


def _format(self, arg, instruction):
    self.emit(regcode.FORMAT, self.depth - 1, self.constant(arg))


def _index(self, arg, instruction):
    self.emit(regcode.INDEX, self.depth - 2, self.depth - 2, self.depth - 1)
    self.depth -= 1


def _slice(self, arg, instruction):
    # The object, the start, the stop and the step.
    self.emit(regcode.SLICE, self.depth - 4, 4)
    self.depth -= 3


def _store_slice(self, arg, instruction):
    # The value, the object, the start, the stop and the step.
    self.emit(regcode.STORE_SLICE, self.depth - 5, 5)
    self.depth -= 5


def _store_index(self, arg, instruction):
    # The value is the deepest of the three, the index is on the top.
    self.emit(regcode.STORE_INDEX, self.depth - 2, self.depth - 1,
              self.depth - 3)
    self.depth -= 3


def _unpack_plan(self, arg, instruction):
    # The iterable is on the stack, and the values of the plan take its
    # place.
    count = ops.plan_value_count(arg)
    self.emit(regcode.UNPACK_PLAN, self.depth - 1, self.constant(arg))
    self.depth += count - 1


def _make_function(self, arg, instruction):
    # The body of the function is lowered as well, so the register code of
    # a program holds nothing but register code.
    body = registerize(arg)
    self.emit(regcode.MAKE_FUNCTION, self.depth, self.constant(body))
    self.depth += 1


def _call(self, arg, instruction):
    count, has_kwargs = arg if arg else (0, False)
    callee = self.depth - count - (1 if has_kwargs else 0) - 1
    self.emit(regcode.CALL, callee, count, 1 if has_kwargs else 0)
    self.depth = callee + 1


def _method_call(self, arg, instruction):
    method, count = arg
    receiver = self.depth - count - 1
    self.emit(regcode.METHOD_CALL, receiver, count, self.constant(method))
    self.depth = receiver + 1


def _return(self, arg, instruction):
    self.emit(regcode.RETURN, self.depth - 1)
    self.depth -= 1


def _halt(self, arg, instruction):
    self.emit(regcode.HALT)


def _jump(self, arg, instruction):
    index = self.emit(regcode.JUMP)
    self.patches.append((index, arg, 0))


def _jump_if_false(self, arg, instruction):
    index = self.emit(regcode.JUMP_IF_FALSE, self.depth - 1)
    self.patches.append((index, arg, 1))
    self.depth -= 1


def _jump_if_true(self, arg, instruction):
    index = self.emit(regcode.JUMP_IF_TRUE, self.depth - 1)
    self.patches.append((index, arg, 1))
    self.depth -= 1


def _enter_scope(self, arg, instruction):
    self.emit(regcode.ENTER_SCOPE)


def _exit_scope(self, arg, instruction):
    self.emit(regcode.EXIT_SCOPE)


def _for_setup(self, arg, instruction):
    self.emit(regcode.FOR_SETUP, self.depth - 1)
    self.depth -= 1


def _for_next(self, arg, instruction):
    index = self.emit(regcode.FOR_NEXT, self.depth)
    self.patches.append((index, arg, 1))
    self.depth += 1


def _for_pop(self, arg, instruction):
    self.emit(regcode.FOR_POP)


def _import(self, arg, instruction):
    self.emit(regcode.IMPORT, self.constant(arg))


def _try(self, arg, instruction):
    index = self.emit(regcode.TRY)
    self.patches.append((index, arg, 0))


def _try_finally(self, arg, instruction):
    index = self.emit(regcode.TRY_FINALLY)
    self.patches.append((index, arg, 0))


def _end_try(self, arg, instruction):
    self.emit(regcode.END_TRY)


def _finally_end(self, arg, instruction):
    self.emit(regcode.FINALLY_END)


def _throw(self, arg, instruction):
    # The value is under the cause, and the cause is only there when the
    # throw names one.
    if arg:
        self.emit(regcode.THROW, self.depth - 2, 1)
        self.depth -= 2
    else:
        self.emit(regcode.THROW, self.depth - 1, 0)
        self.depth -= 1


def _assert(self, arg, instruction):
    # The message is on the top of the stack; without a message there is
    # nothing to pop.
    if arg:
        self.emit(regcode.ASSERT, self.depth - 1, 1)
        self.depth -= 1
    else:
        self.emit(regcode.ASSERT, 0, 0)


def _with_enter(self, arg, instruction):
    self.emit(regcode.WITH_ENTER, self.depth - 2, self.constant(arg))
    self.depth -= 2


def _with_pop_target(self, arg, instruction):
    self.emit(regcode.WITH_POP_TARGET, self.depth)
    self.depth += 1


def _protocol_get(self, arg, instruction):
    self.emit(regcode.PROTOCOL_GET, self.depth - 2, self.constant(arg))
    self.depth -= 1


def _pending_error(self, arg, instruction):
    self.emit(regcode.PENDING_ERROR, self.depth)
    self.depth += 1


def _clear_error(self, arg, instruction):
    self.emit(regcode.CLEAR_ERROR)


def _with_depth(self, arg, instruction):
    self.emit(regcode.WITH_DEPTH, self.depth)
    self.depth += 1


def _has_error(self, arg, instruction):
    self.emit(regcode.HAS_ERROR, self.depth)
    self.depth += 1


def _scope_enter(self, arg, instruction):
    self.emit(regcode.SCOPE_ENTER)


def _scope_exit(self, arg, instruction):
    self.emit(regcode.SCOPE_EXIT)


def _match_test(self, arg, instruction):
    self.emit(regcode.MATCH_TEST, self.depth - 1, self.constant(arg))


def _match_fail(self, arg, instruction):
    self.emit(regcode.MATCH_FAIL, self.depth - 1)
    self.depth -= 1


_HANDLERS = {
    OP_LOAD_CONST: _load_const,
    OP_LOAD_NAME: _load_name,
    OP_STORE_NAME: _store_name,
    OP_DEFINE_NAME: _define_name,
    OP_RECORD_EXPORT: _record_export,
    OP_POP: _pop,
    OP_DUP: _dup,
    OP_BINARY: _binary,
    OP_UNARY: _unary,
    OP_BUILD_LIST: _build_list,
    OP_BUILD_DICT: _build_dict,
    OP_BUILD_STRING: _build_string,
    OP_LIST_APPEND: _list_append,
    OP_DICT_SET: _dict_set,
    OP_FORMAT: _format,
    OP_INDEX: _index,
    OP_SLICE: _slice,
    OP_STORE_SLICE: _store_slice,
    OP_STORE_INDEX: _store_index,
    OP_UNPACK_PLAN: _unpack_plan,
    OP_MAKE_FUNCTION: _make_function,
    OP_CALL: _call,
    OP_METHOD_CALL: _method_call,
    OP_RETURN: _return,
    OP_HALT: _halt,
    OP_JUMP: _jump,
    OP_JUMP_IF_FALSE: _jump_if_false,
    OP_JUMP_IF_TRUE: _jump_if_true,
    OP_ENTER_SCOPE: _enter_scope,
    OP_EXIT_SCOPE: _exit_scope,
    OP_FOR_SETUP: _for_setup,
    OP_FOR_NEXT: _for_next,
    OP_FOR_POP: _for_pop,
    OP_IMPORT: _import,
    OP_TRY: _try,
    OP_TRY_FINALLY: _try_finally,
    OP_END_TRY: _end_try,
    OP_FINALLY_END: _finally_end,
    OP_THROW: _throw,
    OP_ASSERT: _assert,
    OP_DEL: _del,
    OP_DEL_INDEX: _del_index,
    OP_YIELD: _yield,
    OP_WITH_ENTER: _with_enter,
    OP_WITH_POP_TARGET: _with_pop_target,
    OP_PROTOCOL_GET: _protocol_get,
    OP_PENDING_ERROR: _pending_error,
    OP_CLEAR_ERROR: _clear_error,
    OP_WITH_DEPTH: _with_depth,
    OP_HAS_ERROR: _has_error,
    OP_SCOPE_ENTER: _scope_enter,
    OP_SCOPE_EXIT: _scope_exit,
    OP_MATCH_TEST: _match_test,
    OP_MATCH_FAIL: _match_fail,
}


def registerize(code):
    """Lower one code object of the stack machine into register code."""
    return Registerizer(code).run()
