"""The register VM of Bun.

The stack VM is the reference semantics of the language.  The register VM
runs the same programs with the same errors and the same messages, but the
values of an expression live in the registers of a frame instead of on an
operand stack.

A frame has a register file of `regcode.REGISTER_COUNT` slots, an
overflow stack for the values that do not fit, and the bookkeeping of the
runtime: the environments, the handlers of the errors, the iterators of
the loops, the managers of the "with" statements and the groups of the
"scope" statements.

The slots of an expression are numbered from zero, and the slot ``i`` is
the register ``i`` while ``i`` is below the size of the file.  The
overflow stack holds the slots above that size, in the order they were
pushed, so the slot ``i`` of the overflow is the value of the slot
``i + REGISTER_COUNT``.
"""

import os
import threading

from . import ops
from . import patterns
from . import regcode
from . import tasks
from .builtins import register_builtins
from .dict import BunDict
from .generators import Generator, is_generator
from .set import BunSet
from .environment import Environment
from .errors import BunRuntimeError
from .modules import (
    attach_module_frame,
    load_module_source,
    module_dir,
    read_source,
    resolve_module_path,
)
from .values import (
    BunFunction, BunStruct, Builtin, copy_value, format_fstring_part,
    is_truthy, repr_value, stringify,
)


class _TopLevelReturn(Exception):
    def __init__(self, error):
        super().__init__()
        self.error = error


_DONE = object()


class RegFrame:
    """One frame of the register VM."""

    def __init__(self, code, env, base_dir, caller=None):
        self.code = code["code"]
        self.consts = code.get("consts", [])
        self.lines = code.get("lines", [])
        self.filename = code.get("filename")
        self.source = code.get("source")
        self.ip = 0
        self.env = env
        self.base_dir = base_dir
        self.regs = [None] * regcode.REGISTER_COUNT
        self.over = []
        self.sp = 0
        self.handlers = []
        self.pending_error = None
        self.with_stack = []
        self.scopes = []
        self.caller = caller
        self.iterators = []
        self.return_slot = None
        # The generator that runs in this frame, if there is one.
        self.generator = None
        self.depth = 1 if caller is None else caller.depth + 1

    def root(self):
        """The frame that started the call."""
        frame = self
        while frame.caller is not None:
            frame = frame.caller
        return frame

    # -- the slots ---------------------------------------------------------

    def slot(self, index):
        """The value of a slot of the expression."""
        if index < regcode.REGISTER_COUNT:
            return self.regs[index]
        return self.over[index - regcode.REGISTER_COUNT]

    def set_slot(self, index, value):
        """Write a value into a slot of the expression."""
        if index < regcode.REGISTER_COUNT:
            self.regs[index] = value
        else:
            self.over[index - regcode.REGISTER_COUNT] = value

    def push(self, index, value):
        """Write a value into a slot and open it."""
        self.set_slot(index, value)
        self.sp = index + 1

    def truncate(self, depth):
        """Drop the slots above a depth, the way a handler does."""
        self.sp = depth
        if depth <= regcode.REGISTER_COUNT:
            del self.over[:]
        else:
            keep = depth - regcode.REGISTER_COUNT
            del self.over[keep:]


class RegisterVM:
    """The register machine of Bun."""

    MAX_FRAMES = 10000

    def __init__(self, program_args=None, profile=False):
        self.globals = Environment()
        register_builtins(self.globals, program_args)
        self.globals.module_dir = os.getcwd()
        self.modules = {}
        self.loading = set()
        self.export_stack = []
        self.profile = profile
        self.instruction_counts = {}
        self._spawn_pool = []
        self.globals.define("spawn", Builtin("spawn", self._spawn), False)

    # -- the tasks ----------------------------------------------------------

    def _spawn(self, args):
        """Start a task that runs a function on its own thread."""
        if len(args) != 1:
            raise BunRuntimeError("spawn() expects a function")
        function = args[0]
        if not isinstance(function, BunFunction):
            raise BunRuntimeError("spawn() expects a function")
        record = {"id": tasks.new_task_id(), "done": False, "result": None,
                  "error": None, "cancelled": False, "thread": None}
        group = tasks.current_group()
        thread = threading.Thread(
            target=self._run_task, args=(function, record, group), daemon=True)
        record["thread"] = thread
        tasks.register_task(record)
        thread.start()
        return tasks.task_handle(record)

    def _run_task(self, function, record, group):
        tasks.set_current_group(group)
        tasks.set_current_task(record)
        try:
            env = Environment(function.closure)
            for spec, source, payload in ops.bind_arguments(
                    function.name, function.param_specs, [], {}):
                if source == "default":
                    env.define(spec["name"], self._execute(
                        payload, env, self.globals.module_dir), True)
                else:
                    env.define(spec["name"], payload, True)
            record["result"] = self._execute(
                self._call_code(function, []), env, self.globals.module_dir)
        except BaseException as error:
            record["error"] = error
        finally:
            record["done"] = True

    # -- the entry points --------------------------------------------------

    def run(self, code, env=None, base_dir=None):
        env = env if env is not None else self.globals
        if base_dir is None:
            base_dir = os.getcwd()
        self.globals.module_dir = base_dir
        return self._execute(code, env, base_dir)

    def _next_answer(self, frame, value):
        """Run the `next` method of a value and give its answer.

        The method is called with its receiver borrowed, the way a
        method call borrows it, so a value that walks a loop keeps its
        state between the steps of the loop: a copy would walk the same
        step over and over.
        """
        code = {
            "name": "<next>",
            "params": [],
            "consts": [value, "next"],
            "code": [
                (regcode.CONST, 0, 0, 0),
                (regcode.METHOD_CALL, 0, 0, 1),
                (regcode.HALT, 0, 0, 0),
            ],
            "lines": [0, 0, 0],
            "filename": "<next>",
            "source": "",
        }
        return self._execute(code, Environment(self.globals), frame.base_dir)

    def call_function(self, function, args):
        if not isinstance(function, BunFunction):
            raise BunRuntimeError("%s is not callable" % stringify(function))
        frame_env = Environment(self.globals)
        return self._execute(
            self._call_code(function, args), frame_env, os.getcwd())

    def _call_code(self, function, args):
        """The code that calls a function and ends with its result."""
        pool = [function]
        instructions = [(regcode.CONST, 0, 0, 0)]
        for index, value in enumerate(args):
            pool.append(value)
            instructions.append((regcode.CONST, index + 1, len(pool) - 1, 0))
        instructions.append((regcode.CALL, 0, len(args), 0))
        instructions.append((regcode.HALT, 0, 0, 0))
        return {
            "name": "<spawn>",
            "params": [],
            "consts": pool,
            "code": instructions,
            "lines": [0] * len(instructions),
            "filename": "<spawn>",
            "source": "",
        }

    # -- the loop ----------------------------------------------------------

    def _execute(self, code, env, base_dir, generator=None):
        frame = RegFrame(code, env, base_dir)
        frame.generator = generator
        while True:
            try:
                ins = frame.code[frame.ip]
                op = ins[0]
                frame.ip += 1
                if self.profile:
                    counts = self.instruction_counts
                    counts[op] = counts.get(op, 0) + 1
                handler = _DISPATCH.get(op)
                if handler is None:
                    raise BunRuntimeError("unknown instruction '%s'" % op)
                result = handler(self, frame, ins[1], ins[2], ins[3])
            except _TopLevelReturn as signal:
                raise signal.error
            except BunRuntimeError as error:
                if error.filename is None:
                    error.filename = frame.filename
                    error.source = frame.source
                if error.line == 0:
                    line, col = self._line_of(frame)
                    error.line, error.col = line, col
                target = frame
                while target is not None and not target.handlers:
                    target = target.caller
                if target is None:
                    raise
                kind, catch_ip, catch_env, stack_depth, iterator_depth = \
                    target.handlers.pop()
                target.truncate(stack_depth)
                del target.iterators[iterator_depth:]
                target.env = catch_env
                target.ip = catch_ip
                if kind == "finally":
                    target.pending_error = error
                else:
                    target.push(stack_depth, error.msg)
                frame = target
                continue
            if result is _DONE:
                return frame.slot(frame.sp - 1) if frame.sp else None
            if result is not None:
                frame = result

    # -- the instructions --------------------------------------------------

    def _line_of(self, frame):
        """The line and the column of the instruction that runs."""
        index = frame.ip - 1
        lines = frame.lines
        if 0 <= index < len(lines):
            line, col = lines[index]
            return line, col
        return 0, 0

    def _op_const(self, frame, a, b, c):
        frame.push(a, frame.consts[b])

    def _op_load_name(self, frame, a, b, c):
        frame.push(a, frame.env.get(frame.consts[b]))

    def _op_fused(self, frame, a, b, c):
        """Do the work of a pair of loads in one dispatch."""
        kind1, arg1, kind2, arg2, place = frame.consts[b]
        frame.set_slot(a, self._fused_value(frame, kind1, arg1, None))
        frame.set_slot(a + 1,
                       self._fused_value(frame, kind2, arg2, place))
        frame.sp = a + 2

    def _fused_value(self, frame, kind, value, place):
        if kind == "const":
            return value
        try:
            return frame.env.get(value)
        except BunRuntimeError as error:
            if error.line == 0 and place is not None:
                error.line, error.col = place
            raise

    def _op_store_name(self, frame, a, b, c):
        frame.env.assign(frame.consts[b], copy_value(frame.slot(a)))
        frame.sp = a

    def _op_define_name(self, frame, a, b, c):
        frame.env.define(frame.consts[b], copy_value(frame.slot(a)),
                         bool(c))
        frame.sp = a

    def _op_record_export(self, frame, a, b, c):
        if not self.export_stack:
            raise BunRuntimeError("'export' is only allowed in modules")
        name = frame.consts[a]
        self.export_stack[-1][name] = frame.env.get(name)

    def _op_pop(self, frame, a, b, c):
        frame.sp = a

    def _op_dup(self, frame, a, b, c):
        frame.push(a + 1, frame.slot(a))

    def _op_add(self, frame, a, b, c):
        left = frame.slot(b)
        right = frame.slot(c)
        if type(left) is int and type(right) is int:
            frame.set_slot(a, ops.check_int(left + right))
        else:
            frame.set_slot(a, ops.binary_op("+", left, right))
        frame.sp = a + 1

    def _op_sub(self, frame, a, b, c):
        left = frame.slot(b)
        right = frame.slot(c)
        if type(left) is int and type(right) is int:
            frame.set_slot(a, ops.check_int(left - right))
        else:
            frame.set_slot(a, ops.binary_op("-", left, right))
        frame.sp = a + 1

    def _op_mul(self, frame, a, b, c):
        left = frame.slot(b)
        right = frame.slot(c)
        if type(left) is int and type(right) is int:
            frame.set_slot(a, ops.check_int(left * right))
        else:
            frame.set_slot(a, ops.binary_op("*", left, right))
        frame.sp = a + 1

    def _op_div(self, frame, a, b, c):
        left = frame.slot(b)
        right = frame.slot(c)
        if type(left) is int and type(right) is int:
            if right == 0:
                raise BunRuntimeError("division by zero")
            frame.set_slot(a, ops.check_int(left // right))
        else:
            frame.set_slot(a, ops.binary_op("/", left, right))
        frame.sp = a + 1

    def _op_pow(self, frame, a, b, c):
        left = frame.slot(b)
        right = frame.slot(c)
        frame.set_slot(a, ops.power(left, right))
        frame.sp = a + 1

    def _op_mod(self, frame, a, b, c):
        left = frame.slot(b)
        right = frame.slot(c)
        if type(left) is int and type(right) is int:
            if right == 0:
                raise BunRuntimeError("division by zero")
            frame.set_slot(a, left % right)
        else:
            frame.set_slot(a, ops.binary_op("%", left, right))
        frame.sp = a + 1

    def _op_compare(self, frame, a, b, c, symbol):
        left = frame.slot(b)
        right = frame.slot(c)
        if type(left) is int and type(right) is int:
            if symbol == "==":
                value = left == right
            elif symbol == "!=":
                value = left != right
            elif symbol == "<":
                value = left < right
            elif symbol == "<=":
                value = left <= right
            elif symbol == ">":
                value = left > right
            else:
                value = left >= right
        else:
            value = ops.binary_op(symbol, left, right)
        frame.set_slot(a, value)
        frame.sp = a + 1

    def _op_eq(self, frame, a, b, c):
        self._op_compare(frame, a, b, c, "==")

    def _op_ne(self, frame, a, b, c):
        self._op_compare(frame, a, b, c, "!=")

    def _op_lt(self, frame, a, b, c):
        self._op_compare(frame, a, b, c, "<")

    def _op_le(self, frame, a, b, c):
        self._op_compare(frame, a, b, c, "<=")

    def _op_gt(self, frame, a, b, c):
        self._op_compare(frame, a, b, c, ">")

    def _op_ge(self, frame, a, b, c):
        self._op_compare(frame, a, b, c, ">=")

    def _op_bits(self, frame, a, b, c, symbol):
        left = frame.slot(b)
        right = frame.slot(c)
        if type(left) is int and type(right) is int:
            if symbol == "&":
                value = left & right
            elif symbol == "|":
                value = left | right
            elif symbol == "^":
                value = left ^ right
            elif symbol == "<<":
                if right < 0:
                    raise BunRuntimeError("negative shift count")
                value = ops.check_int(left << right)
            else:
                if right < 0:
                    raise BunRuntimeError("negative shift count")
                value = left >> right
        else:
            value = ops.binary_op(symbol, left, right)
        frame.set_slot(a, value)
        frame.sp = a + 1

    def _op_band(self, frame, a, b, c):
        self._op_bits(frame, a, b, c, "&")

    def _op_bor(self, frame, a, b, c):
        self._op_bits(frame, a, b, c, "|")

    def _op_bxor(self, frame, a, b, c):
        self._op_bits(frame, a, b, c, "^")

    def _op_shl(self, frame, a, b, c):
        self._op_bits(frame, a, b, c, "<<")

    def _op_shr(self, frame, a, b, c):
        self._op_bits(frame, a, b, c, ">>")

    def _op_neg(self, frame, a, b, c):
        frame.set_slot(a, ops.unary_op("-", frame.slot(b)))
        frame.sp = a + 1

    def _op_invert(self, frame, a, b, c):
        frame.set_slot(a, ops.unary_op("~", frame.slot(b)))
        frame.sp = a + 1

    def _op_not(self, frame, a, b, c):
        frame.set_slot(a, ops.unary_op("!", frame.slot(b)))
        frame.sp = a + 1

    def _op_build_list(self, frame, a, b, c):
        count = b
        items = []
        for index in range(count):
            items.append(frame.slot(a + index))
        frame.set_slot(a, items)
        frame.sp = a + 1

    def _op_build_dict(self, frame, a, b, c):
        count = b
        result = BunDict()
        for index in range(count):
            key = frame.slot(a + index * 2)
            value = frame.slot(a + index * 2 + 1)
            result.set(key, value)
        frame.set_slot(a, result)
        frame.sp = a + 1

    def _op_build_string(self, frame, a, b, c):
        count = b
        parts = []
        for index in range(count):
            parts.append(frame.slot(a + index))
        frame.set_slot(a, "".join(parts))
        frame.sp = a + 1

    def _op_list_append(self, frame, a, b, c):
        target = frame.slot(a)
        value = frame.slot(a + 1)
        if not isinstance(target, list):
            raise BunRuntimeError("internal error: list append target")
        target.append(value)
        frame.sp = a + 1

    def _op_dict_set(self, frame, a, b, c):
        target = frame.slot(a)
        if not isinstance(target, BunDict):
            raise BunRuntimeError("internal error: dict set target")
        target.set(frame.slot(b), frame.slot(c))
        frame.sp = a + 1

    def _op_index(self, frame, a, b, c):
        value = ops.index_value(frame.slot(b), frame.slot(c))
        frame.set_slot(a, value)
        frame.sp = a + 1

    def _op_store_index(self, frame, a, b, c):
        ops.assign_index(frame.slot(a), frame.slot(b), frame.slot(c))
        frame.sp = a

    def _op_slice(self, frame, a, b, c):
        count = b
        obj = frame.slot(a)
        start = frame.slot(a + 1)
        stop = frame.slot(a + 2)
        step = frame.slot(a + 3)
        frame.set_slot(a, ops.slice_value(obj, start, stop, step))
        frame.sp = a + 1

    def _op_store_slice(self, frame, a, b, c):
        count = b
        value = frame.slot(a)
        obj = frame.slot(a + 1)
        start = frame.slot(a + 2)
        stop = frame.slot(a + 3)
        step = frame.slot(a + 4)
        ops.assign_slice(obj, start, stop, step, value)
        frame.sp = a

    def _op_unpack_plan(self, frame, a, b, c):
        plan = frame.consts[b]
        value = frame.slot(a)
        items = ops.unpack_items(value)
        values = ops.unpack_plan(plan, items)
        # The values go on the stack in the reverse order, so the first
        # one ends up on the top of the stack.
        for offset, item in enumerate(reversed(values)):
            frame.set_slot(a + offset, item)
        frame.sp = a + len(values)

    def _op_format(self, frame, a, b, c):
        spec, conv, source_text = frame.consts[b]
        value = frame.slot(a)
        frame.set_slot(a, format_fstring_part(spec, conv, source_text, value))

    def _op_make_function(self, frame, a, b, c):
        body = frame.consts[b]
        frame.push(a, BunFunction(body["name"], body["params"], body,
                                  frame.env, body.get("filename"),
                                  body.get("source"),
                                  param_specs=body.get("param_defs")))

    def _op_call(self, frame, a, b, c):
        count = b
        has_kwargs = bool(c)
        kwargs = {}
        base = a
        if has_kwargs:
            raw = frame.slot(base + count + 1)
            if isinstance(raw, BunDict):
                for key in raw.keys():
                    kwargs[key] = raw.get(key)
        args = []
        for index in range(count):
            args.append(frame.slot(base + 1 + index))
        callee = frame.slot(base)
        return self._call_function(frame, callee, args, kwargs, base)

    def _call_function(self, frame, callee, args, kwargs, slot, borrowed=0):
        """Run a call. The answer goes into the slot of the call.

        The arguments of a call are copied, because a struct is a value
        type. The first `borrowed` arguments are left alone: a method
        call borrows the receiver, so a mutation through `self` is seen
        by the caller.
        """
        args = list(args)
        for index in range(borrowed, len(args)):
            args[index] = copy_value(args[index])
        if isinstance(callee, BunFunction):
            call_env = Environment(callee.closure)
            for spec, source, payload in ops.bind_arguments(
                    callee.name, callee.param_specs, args, kwargs):
                if source == "default":
                    call_env.define(spec["name"],
                                    self._execute(payload, call_env,
                                                  frame.base_dir), True)
                elif source == "kwarg":
                    extra = BunDict()
                    for key, value in payload.items():
                        extra.set(key, value)
                    call_env.define(spec["name"], extra, True)
                else:
                    call_env.define(spec["name"], payload, True)
            if callee.body.get("is_generator"):
                # A generator does not run now. It runs in a thread of
                # its own, and it gives its values one at a time.
                generator = Generator(
                    lambda gen: self._execute(callee.body, call_env,
                                              frame.base_dir, gen),
                    callee.name or "anonymous")
                frame.push(slot, generator)
                return None
            if frame.depth >= self.MAX_FRAMES:
                raise BunRuntimeError("stack overflow")
            body = callee.body
            callee_frame = RegFrame(body, call_env, frame.base_dir,
                                    caller=frame)
            callee_frame.return_slot = slot
            return callee_frame
        if isinstance(callee, Builtin):
            if kwargs:
                raise BunRuntimeError(
                    "builtin '%s' does not accept keyword arguments"
                    % callee.name)
            frame.push(slot, callee.func(args))
            return None
        raise BunRuntimeError(
            "%s is not callable" % stringify(callee))

    def _op_method_call(self, frame, a, b, c):
        count = b
        method = frame.consts[c]
        args = []
        for index in range(count):
            args.append(frame.slot(a + 1 + index))
        receiver = frame.slot(a)
        if isinstance(receiver, BunStruct):
            function = ops.struct_method(receiver.type_name, method)
            if isinstance(function, BunFunction):
                return self._call_function(
                    frame, function, [receiver] + args, {}, a, borrowed=1)
        frame.push(a, ops.method_call(method, receiver, args))

    def _op_make_struct(self, frame, a, b, c):
        type_name, field_names = frame.consts[b]
        count = c
        values = []
        for index in range(count):
            values.append(frame.slot(a + index))
        frame.set_slot(a, ops.make_struct(type_name, field_names, values))
        frame.sp = a + 1

    def _op_get_field(self, frame, a, b, c):
        obj = frame.slot(b)
        frame.set_slot(a, ops.get_field(obj, frame.consts[c]))
        frame.sp = a + 1

    def _op_set_field(self, frame, a, b, c):
        obj = frame.slot(a)
        value = frame.slot(b)
        ops.set_field(obj, frame.consts[c], copy_value(value))
        frame.sp = a

    def _op_register_impl(self, frame, a, b, c):
        type_name = frame.consts[a]
        method = frame.consts[b]
        body = frame.consts[c]
        function = BunFunction(body["name"], body["params"], body,
                               frame.env, body.get("filename"),
                               body.get("source"),
                               param_specs=body.get("param_defs"))
        ops.register_impl(type_name, method, function)

    def _op_unwrap_or_return(self, frame, a, b, c):
        ok, payload = ops.unwrap_result(frame.slot(a))
        if ok:
            frame.set_slot(a, payload)
            return None
        return self._op_return(frame, a, b, c)

    def _op_return(self, frame, a, b, c):
        value = copy_value(frame.slot(a))
        generator = frame.root().generator
        if generator is not None:
            # The body of a generator is over, and it gives its last
            # value to the program.
            generator.finish(value)
            return _DONE
        if frame.caller is None:
            raise _TopLevelReturn(
                BunRuntimeError("'return' outside of a function"))
        target = frame.return_slot
        if target is None:
            target = frame.caller.sp
        frame.caller.push(target, value)
        return frame.caller

    def _op_halt(self, frame, a, b, c):
        return _DONE

    def _op_jump(self, frame, a, b, c):
        frame.ip = a

    def _op_jump_if_false(self, frame, a, b, c):
        if not is_truthy(frame.slot(a)):
            frame.ip = b
        frame.sp = a

    def _op_jump_if_true(self, frame, a, b, c):
        if is_truthy(frame.slot(a)):
            frame.ip = b
        frame.sp = a

    def _op_jump_if_null(self, frame, a, b, c):
        # The null coalescing asks this question of the left side: is
        # the value null?
        if frame.slot(a) is None:
            frame.ip = b
        frame.sp = a

    def _op_enter_scope(self, frame, a, b, c):
        frame.env = Environment(frame.env)

    def _op_exit_scope(self, frame, a, b, c):
        frame.env = frame.env.parent

    def _op_yield(self, frame, a, b, c):
        value = frame.slot(a)
        generator = frame.root().generator
        if generator is None:
            raise BunRuntimeError("'yield' outside of a generator")
        frame.set_slot(a, generator.yield_value(value))

    def _op_for_setup(self, frame, a, b, c):
        iterable = frame.slot(a)
        # A value that answers a `next` method is walked with the answers
        # of that method, and the method is called the way this engine
        # calls it, with the receiver borrowed from the loop.
        if ops.has_next(iterable):
            frame.iterators.append(ops.protocol_iterator(
                iterable, lambda: self._next_answer(frame, iterable)))
        else:
            frame.iterators.append(ops.iterate(iterable))
        frame.sp = a

    def _op_for_next(self, frame, a, b, c):
        try:
            value = next(frame.iterators[-1])
        except StopIteration:
            frame.iterators.pop()
            frame.ip = b
            frame.sp = a
            return
        frame.push(a, value)

    def _op_for_pop(self, frame, a, b, c):
        if frame.iterators:
            frame.iterators.pop()

    def _op_import(self, frame, a, b, c):
        path, names = frame.consts[a]
        try:
            full_path = resolve_module_path(
                path, self._env_base_dir(frame.env, frame.base_dir))
            if full_path in self.modules:
                exports = self.modules[full_path]
            elif full_path in self.loading:
                raise BunRuntimeError("circular import of '%s'" % path)
            else:
                exports = self._run_module(path, full_path)
        except BunRuntimeError as error:
            if error.line == 0:
                error.line, error.col = b, c
            raise
        for name in names:
            if name not in exports:
                raise BunRuntimeError(
                    "module '%s' does not export '%s'" % (path, name))
            frame.env.define(name, exports[name], False)

    def _op_try(self, frame, a, b, c):
        frame.handlers.append(
            ("catch", a, frame.env, frame.sp, len(frame.iterators)))

    def _op_try_finally(self, frame, a, b, c):
        frame.handlers.append(
            ("finally", a, frame.env, frame.sp, len(frame.iterators)))

    def _op_end_try(self, frame, a, b, c):
        frame.handlers.pop()

    def _op_finally_end(self, frame, a, b, c):
        error = frame.pending_error
        if error is not None:
            frame.pending_error = None
            raise error

    def _op_throw(self, frame, a, b, c):
        cause = None
        if b:
            cause = stringify(frame.slot(a + 1))
        value = frame.slot(a)
        raise BunRuntimeError(stringify(value), 0, 0, cause=cause)

    def _op_assert(self, frame, a, b, c):
        if b:
            message = stringify(frame.slot(a))
            raise BunRuntimeError("assertion failed: " + message, 0, 0)
        raise BunRuntimeError("assertion failed", 0, 0)

    def _op_del(self, frame, a, b, c):
        frame.env.delete(frame.consts[a])

    def _op_del_index(self, frame, a, b, c):
        ops.delete_index(frame.slot(a), frame.slot(b))
        frame.sp = a

    def _op_with_enter(self, frame, a, b, c):
        result = frame.slot(a + 1)
        target = frame.slot(a)
        frame.env.define(frame.consts[b], result, True)
        frame.with_stack.append(target)
        frame.sp = a

    def _op_with_pop_target(self, frame, a, b, c):
        if not frame.with_stack:
            raise BunRuntimeError("'with' has no active target")
        frame.push(a, frame.with_stack.pop())

    def _op_protocol_get(self, frame, a, b, c):
        target = frame.slot(a)
        name = frame.consts[b]
        method = None
        if isinstance(target, BunDict):
            method = target.get(name)
        if method is None:
            raise BunRuntimeError(
                "'with' target does not implement '%s'" % name)
        if not isinstance(method, (BunFunction, Builtin)):
            raise BunRuntimeError(
                "'with' target method '%s' is not callable" % name)
        frame.set_slot(a, method)
        frame.sp = a + 1

    def _op_pending_error(self, frame, a, b, c):
        error = frame.pending_error
        frame.push(a, error.msg if error is not None else None)

    def _op_clear_error(self, frame, a, b, c):
        frame.pending_error = None

    def _op_with_depth(self, frame, a, b, c):
        frame.push(a, len(frame.with_stack))

    def _op_has_error(self, frame, a, b, c):
        frame.push(a, frame.pending_error is not None)

    def _op_scope_enter(self, frame, a, b, c):
        frame.scopes.append(tasks.scope_enter())

    def _op_scope_exit(self, frame, a, b, c):
        if not frame.scopes:
            raise BunRuntimeError("'scope' without an open group")
        state = frame.scopes.pop()
        error = tasks.scope_exit(state)
        if error is not None and frame.pending_error is None:
            raise tasks.as_runtime_error(error)

    def _op_match_test(self, frame, a, b, c):
        value = frame.slot(a)
        bindings = []
        if not patterns.match_pattern(value, frame.consts[b], bindings):
            frame.set_slot(a, False)
            return
        for name, bound in bindings:
            frame.env.define(name, bound, True)
        frame.set_slot(a, True)

    def _op_match_fail(self, frame, a, b, c):
        value = frame.slot(a)
        raise BunRuntimeError("no matching case for %s" % repr_value(value),
                              0, 0)

    # -- the modules -------------------------------------------------------

    def _env_base_dir(self, env, default):
        while env is not None:
            module_dir_value = getattr(env, "module_dir", None)
            if module_dir_value is not None:
                return module_dir_value
            env = env.parent
        return default

    def _run_module(self, path, full_path):
        program = load_module_source(path, full_path)
        from .compiler import Compiler
        code = Compiler(full_path, read_source(full_path)).compile_program(program)
        from .regcompile import registerize
        code = registerize(code)
        module_env = Environment(self.globals)
        module_base = module_dir(full_path)
        module_env.module_dir = module_base
        self.loading.add(full_path)
        self.export_stack.append({})
        try:
            try:
                self._execute(code, module_env, module_base)
            except BunRuntimeError as error:
                attach_module_frame(error, full_path, path)
                raise
        finally:
            exports = self.export_stack.pop()
            self.loading.discard(full_path)
        self.modules[full_path] = exports
        return exports


_DISPATCH = {
    regcode.CONST: RegisterVM._op_const,
    regcode.LOAD_NAME: RegisterVM._op_load_name,
    regcode.STORE_NAME: RegisterVM._op_store_name,
    regcode.DEFINE_NAME: RegisterVM._op_define_name,
    regcode.RECORD_EXPORT: RegisterVM._op_record_export,
    regcode.POP: RegisterVM._op_pop,
    regcode.DUP: RegisterVM._op_dup,
    regcode.ADD: RegisterVM._op_add,
    regcode.SUB: RegisterVM._op_sub,
    regcode.MUL: RegisterVM._op_mul,
    regcode.DIV: RegisterVM._op_div,
    regcode.MOD: RegisterVM._op_mod,
    regcode.POW: RegisterVM._op_pow,
    regcode.EQ: RegisterVM._op_eq,
    regcode.NE: RegisterVM._op_ne,
    regcode.LT: RegisterVM._op_lt,
    regcode.LE: RegisterVM._op_le,
    regcode.GT: RegisterVM._op_gt,
    regcode.GE: RegisterVM._op_ge,
    regcode.BAND: RegisterVM._op_band,
    regcode.BOR: RegisterVM._op_bor,
    regcode.BXOR: RegisterVM._op_bxor,
    regcode.SHL: RegisterVM._op_shl,
    regcode.SHR: RegisterVM._op_shr,
    regcode.NEG: RegisterVM._op_neg,
    regcode.INVERT: RegisterVM._op_invert,
    regcode.NOT: RegisterVM._op_not,
    regcode.BUILD_LIST: RegisterVM._op_build_list,
    regcode.BUILD_DICT: RegisterVM._op_build_dict,
    regcode.BUILD_STRING: RegisterVM._op_build_string,
    regcode.LIST_APPEND: RegisterVM._op_list_append,
    regcode.DICT_SET: RegisterVM._op_dict_set,
    regcode.INDEX: RegisterVM._op_index,
    regcode.STORE_INDEX: RegisterVM._op_store_index,
    regcode.SLICE: RegisterVM._op_slice,
    regcode.STORE_SLICE: RegisterVM._op_store_slice,
    regcode.UNPACK_PLAN: RegisterVM._op_unpack_plan,
    regcode.FORMAT: RegisterVM._op_format,
    regcode.MAKE_FUNCTION: RegisterVM._op_make_function,
    regcode.CALL: RegisterVM._op_call,
    regcode.METHOD_CALL: RegisterVM._op_method_call,
    regcode.RETURN: RegisterVM._op_return,
    regcode.HALT: RegisterVM._op_halt,
    regcode.JUMP: RegisterVM._op_jump,
    regcode.JUMP_IF_FALSE: RegisterVM._op_jump_if_false,
    regcode.JUMP_IF_TRUE: RegisterVM._op_jump_if_true,
    regcode.JUMP_IF_NULL: RegisterVM._op_jump_if_null,
    regcode.ENTER_SCOPE: RegisterVM._op_enter_scope,
    regcode.EXIT_SCOPE: RegisterVM._op_exit_scope,
    regcode.FOR_SETUP: RegisterVM._op_for_setup,
    regcode.FOR_NEXT: RegisterVM._op_for_next,
    regcode.FOR_POP: RegisterVM._op_for_pop,
    regcode.IMPORT: RegisterVM._op_import,
    regcode.TRY: RegisterVM._op_try,
    regcode.TRY_FINALLY: RegisterVM._op_try_finally,
    regcode.END_TRY: RegisterVM._op_end_try,
    regcode.FINALLY_END: RegisterVM._op_finally_end,
    regcode.THROW: RegisterVM._op_throw,
    regcode.ASSERT: RegisterVM._op_assert,
    regcode.DEL: RegisterVM._op_del,
    regcode.DEL_INDEX: RegisterVM._op_del_index,
    regcode.YIELD: RegisterVM._op_yield,
    regcode.WITH_ENTER: RegisterVM._op_with_enter,
    regcode.WITH_POP_TARGET: RegisterVM._op_with_pop_target,
    regcode.PROTOCOL_GET: RegisterVM._op_protocol_get,
    regcode.PENDING_ERROR: RegisterVM._op_pending_error,
    regcode.CLEAR_ERROR: RegisterVM._op_clear_error,
    regcode.WITH_DEPTH: RegisterVM._op_with_depth,
    regcode.HAS_ERROR: RegisterVM._op_has_error,
    regcode.SCOPE_ENTER: RegisterVM._op_scope_enter,
    regcode.SCOPE_EXIT: RegisterVM._op_scope_exit,
    regcode.MATCH_TEST: RegisterVM._op_match_test,
    regcode.MATCH_FAIL: RegisterVM._op_match_fail,
    regcode.MAKE_STRUCT: RegisterVM._op_make_struct,
    regcode.GET_FIELD: RegisterVM._op_get_field,
    regcode.SET_FIELD: RegisterVM._op_set_field,
    regcode.REGISTER_IMPL: RegisterVM._op_register_impl,
    regcode.UNWRAP_OR_RETURN: RegisterVM._op_unwrap_or_return,
    regcode.LOAD_NAME2: RegisterVM._op_fused,
    regcode.LOAD_NAME_CONST: RegisterVM._op_fused,
    regcode.CONST_LOAD_NAME: RegisterVM._op_fused,
}
