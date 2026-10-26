import os

from . import ops
from . import patterns
from . import tasks
from .builtins import register_builtins
from .compiler import (
    OP_ASSERT,
    OP_DEL,
    OP_DEL_INDEX,
    OP_YIELD,
    OP_BINARY,
    OP_BUILD_DICT,
    OP_BUILD_LIST,
    OP_BUILD_STRING,
    OP_DICT_SET,
    OP_CALL,
    OP_DEFINE_NAME,
    OP_DUP,
    OP_END_TRY,
    OP_ENTER_SCOPE,
    OP_FINALLY_END,
    OP_EXIT_SCOPE,
    OP_FOR_NEXT,
    OP_FOR_POP,
    OP_FOR_SETUP,
    OP_FORMAT,
    OP_HALT,
    OP_IMPORT,
    OP_INDEX,
    OP_JUMP,
    OP_JUMP_IF_FALSE,
    OP_JUMP_IF_TRUE,
    OP_LOAD_CONST,
    OP_LIST_APPEND,
    OP_LOAD_NAME,
    OP_MAKE_FUNCTION,
    OP_METHOD_CALL,
    OP_POP,
    OP_RECORD_EXPORT,
    OP_RETURN,
    OP_STORE_INDEX,
    OP_SLICE,
    OP_STORE_NAME,
    OP_STORE_SLICE,
    OP_UNPACK_PLAN,
    OP_THROW,
    OP_TRY,
    OP_TRY_FINALLY,
    OP_UNARY,
    OP_WITH_ENTER,
    OP_WITH_POP_TARGET,
    OP_PROTOCOL_GET,
    OP_PENDING_ERROR,
    OP_CLEAR_ERROR,
    OP_WITH_DEPTH,
    OP_HAS_ERROR,
    OP_SCOPE_ENTER,
    OP_SCOPE_EXIT,
    OP_MATCH_TEST,
    OP_MATCH_FAIL,
    OP_MAKE_STRUCT,
    OP_GET_FIELD,
    OP_SET_FIELD,
    OP_REGISTER_IMPL,
    OP_UNWRAP_OR_RETURN,
    Compiler,
)
from .dict import BunDict
from .generators import Generator, is_generator
from .set import BunSet
from .environment import Environment
from .errors import BunRuntimeError
from .ints import INT_MAX, INT_MIN
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


class Frame:
    def __init__(self, code, env, base_dir, caller=None):
        self.code = code["code"]
        self.filename = code.get("filename")
        self.source = code.get("source")
        self.ip = 0
        self.env = env
        self.base_dir = base_dir
        self.stack = []
        self.handlers = []
        self.pending_error = None
        self.with_stack = []
        self.scopes = []
        self.caller = caller
        self.iterators = []
        self.depth = 1 if caller is None else caller.depth + 1
        self.generator = None

    def root(self):
        """The frame that started the execution."""
        frame = self
        while frame.caller is not None:
            frame = frame.caller
        return frame


class VM:
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

    def run(self, code, env=None, base_dir=None):
        env = env if env is not None else self.globals
        if base_dir is None:
            base_dir = os.getcwd()
        self.globals.module_dir = base_dir
        return self._execute(code, env, base_dir)

    def eval_expression(self, node, env, base_dir=None):
        code = Compiler("<repl>", "").compile_expression(node)
        return self._execute(code, env, base_dir if base_dir is not None
                             else os.getcwd())

    def call_function(self, function, args):
        if not isinstance(function, BunFunction):
            raise BunRuntimeError("%s is not callable" % stringify(function))
        instructions = [("LOAD_CONST", function, 0, 0)]
        for value in args:
            instructions.append(("LOAD_CONST", value, 0, 0))
        instructions.append(("CALL", (len(args), False), 0, 0))
        instructions.append(("HALT", None, 0, 0))
        code = {
            "name": "<spawn>",
            "params": [],
            "code": instructions,
            "filename": "<spawn>",
            "source": "",
        }
        frame_env = Environment(self.globals)
        return self._execute(code, frame_env, os.getcwd())

    def _execute(self, code, env, base_dir, generator=None):
        frame = Frame(code, env, base_dir)
        frame.generator = generator
        dispatch = self.DISPATCH
        # The instruction pointer, the code array and the operand stack are
        # kept in local variables. Attribute access on the frame is one of
        # the most expensive parts of a naive dispatch loop, and the frame
        # is only consulted again when a handler needs it.
        code_list = frame.code
        stack = frame.stack
        ip = frame.ip
        counts = self.instruction_counts if self.profile else None
        # The integers of the language are 64 bits wide. The bounds are
        # kept in local variables, because the hot loop reads them for
        # every arithmetic operation.
        int_max = INT_MAX
        int_min = INT_MIN
        while True:
            ins = code_list[ip]
            op = ins[0]
            arg = ins[1]
            ip += 1
            frame.ip = ip
            if counts is not None:
                counts[op] = counts.get(op, 0) + 1

            # The hot instructions are handled inline. Every avoided call
            # matters because the interpreter runs user code millions of
            # times per second.
            try:
                if op == OP_LOAD_CONST:
                    stack.append(arg)
                    continue
                if op == OP_BINARY:
                    right = stack.pop()
                    left = stack.pop()
                    if type(left) is int and type(right) is int:
                        if arg == "+":
                            result = left + right
                            if result > int_max or result < int_min:
                                raise BunRuntimeError("integer overflow")
                            stack.append(result)
                            continue
                        if arg == "-":
                            result = left - right
                            if result > int_max or result < int_min:
                                raise BunRuntimeError("integer overflow")
                            stack.append(result)
                            continue
                        if arg == "*":
                            result = left * right
                            if result > int_max or result < int_min:
                                raise BunRuntimeError("integer overflow")
                            stack.append(result)
                            continue
                        if arg == "%":
                            if right == 0:
                                raise BunRuntimeError("division by zero")
                            stack.append(left % right)
                            continue
                        if arg == "/":
                            if right == 0:
                                raise BunRuntimeError("division by zero")
                            result = left // right
                            if result > int_max or result < int_min:
                                raise BunRuntimeError("integer overflow")
                            stack.append(result)
                            continue
                        if arg == "<":
                            stack.append(left < right)
                            continue
                        if arg == "<=":
                            stack.append(left <= right)
                            continue
                        if arg == ">":
                            stack.append(left > right)
                            continue
                        if arg == ">=":
                            stack.append(left >= right)
                            continue
                        if arg == "==":
                            stack.append(left == right)
                            continue
                        if arg == "!=":
                            stack.append(left != right)
                            continue
                        if arg == "&":
                            stack.append(left & right)
                            continue
                        if arg == "|":
                            stack.append(left | right)
                            continue
                        if arg == "^":
                            stack.append(left ^ right)
                            continue
                        if arg == "<<":
                            if right < 0:
                                raise BunRuntimeError("negative shift count")
                            result = left << right
                            if result > int_max or result < int_min:
                                raise BunRuntimeError("integer overflow")
                            stack.append(result)
                            continue
                        if arg == ">>":
                            if right < 0:
                                raise BunRuntimeError("negative shift count")
                            stack.append(left >> right)
                            continue
                    stack.append(ops.binary_op(arg, left, right))
                    continue
                if op == OP_LOAD_NAME:
                    scope = frame.env
                    while scope is not None:
                        values = scope.values
                        if arg in values:
                            stack.append(values[arg][0])
                            break
                        scope = scope.parent
                    else:
                        raise BunRuntimeError("undefined variable '%s'" % arg)
                    continue
                if op == OP_STORE_NAME:
                    scope = frame.env
                    while scope is not None:
                        values = scope.values
                        if arg in values:
                            if not values[arg][1]:
                                raise BunRuntimeError(
                                    "cannot assign to immutable variable '%s'" % arg)
                            values[arg][0] = copy_value(stack.pop())
                            break
                        scope = scope.parent
                    else:
                        raise BunRuntimeError("undefined variable '%s'" % arg)
                    continue
                if op == OP_JUMP:
                    ip = arg
                    frame.ip = ip
                    continue
                if op == OP_JUMP_IF_FALSE:
                    value = stack.pop()
                    if value is None or value is False:
                        ip = arg
                        frame.ip = ip
                    elif value is not True and not is_truthy(value):
                        ip = arg
                        frame.ip = ip
                    continue
                if op == OP_JUMP_IF_TRUE:
                    value = stack.pop()
                    if value is True:
                        ip = arg
                        frame.ip = ip
                    elif value is not None and value is not False and is_truthy(value):
                        ip = arg
                        frame.ip = ip
                    continue
                if op == OP_POP:
                    stack.pop()
                    continue
                if op == OP_DUP:
                    stack.append(stack[-1])
                    continue
                if op == OP_BUILD_LIST:
                    if arg:
                        items = stack[-arg:]
                        del stack[-arg:]
                    else:
                        items = []
                    stack.append(items)
                    continue
                if op == OP_DEFINE_NAME:
                    name, mutable = arg
                    frame.env.define(name, copy_value(stack.pop()), mutable)
                    continue
                if op == OP_ENTER_SCOPE:
                    frame.env = Environment(frame.env)
                    continue
                if op == OP_EXIT_SCOPE:
                    frame.env = frame.env.parent
                    continue

                handler = dispatch[op]
                next_frame = handler(self, frame, arg, ins[2], ins[3])
            except _TopLevelReturn as signal:
                raise signal.error
            except BunRuntimeError as error:
                if error.filename is None:
                    error.filename = frame.filename
                    error.source = frame.source
                if error.line == 0:
                    error.line, error.col = ins[2], ins[3]
                target = frame
                while target is not None and not target.handlers:
                    target = target.caller
                if target is None:
                    raise
                kind, catch_ip, catch_env, stack_depth, iterator_depth = \
                    target.handlers.pop()
                del target.stack[stack_depth:]
                del target.iterators[iterator_depth:]
                target.env = catch_env
                target.ip = catch_ip
                if kind == "finally":
                    target.pending_error = error
                else:
                    target.stack.append(error.msg)
                frame = target
                code_list = frame.code
                stack = frame.stack
                ip = frame.ip
                continue
            if next_frame is _DONE:
                return frame.stack.pop() if frame.stack else None
            if next_frame is not None:
                frame = next_frame
                code_list = frame.code
                stack = frame.stack
                ip = frame.ip
            else:
                # A handler may have redirected the instruction pointer.
                ip = frame.ip

    def _op_load_const(self, frame, arg, line, col):
        frame.stack.append(arg)

    def _op_build_list(self, frame, arg, line, col):
        if arg:
            items = frame.stack[-arg:]
            del frame.stack[-arg:]
        else:
            items = []
        frame.stack.append(items)

    def _op_build_dict(self, frame, arg, line, col):
        result = BunDict()
        if arg:
            flat = frame.stack[-arg * 2:]
            del frame.stack[-arg * 2:]
            for position in range(0, len(flat), 2):
                result.set(flat[position], flat[position + 1])
        frame.stack.append(result)

    def _op_build_string(self, frame, arg, line, col):
        if arg:
            items = frame.stack[-arg:]
            del frame.stack[-arg:]
        else:
            items = []
        frame.stack.append("".join(items))

    def _op_list_append(self, frame, arg, line, col):
        value = frame.stack.pop()
        target = frame.stack[-1]
        if not isinstance(target, list):
            raise BunRuntimeError("internal error: list append target")
        target.append(value)

    def _op_dict_set(self, frame, arg, line, col):
        value = frame.stack.pop()
        key = frame.stack.pop()
        target = frame.stack[-1]
        if not isinstance(target, BunDict):
            raise BunRuntimeError("internal error: dict set target")
        target.set(key, value)

    def _op_format(self, frame, arg, line, col):
        spec, conv, source_text = arg
        value = frame.stack.pop()
        frame.stack.append(format_fstring_part(spec, conv, source_text, value))

    def _op_load_name(self, frame, arg, line, col):
        frame.stack.append(frame.env.get(arg))

    def _op_define_name(self, frame, arg, line, col):
        name, mutable = arg
        frame.env.define(name, copy_value(frame.stack.pop()), mutable)

    def _op_store_name(self, frame, arg, line, col):
        frame.env.assign(arg, copy_value(frame.stack.pop()))

    def _op_del(self, frame, arg, line, col):
        frame.env.delete(arg)

    def _op_del_index(self, frame, arg, line, col):
        index = frame.stack.pop()
        container = frame.stack.pop()
        ops.delete_index(container, index)

    def _op_pop(self, frame, arg, line, col):
        frame.stack.pop()

    def _op_dup(self, frame, arg, line, col):
        frame.stack.append(frame.stack[-1])

    def _op_enter_scope(self, frame, arg, line, col):
        frame.env = Environment(frame.env)

    def _op_exit_scope(self, frame, arg, line, col):
        frame.env = frame.env.parent

    def _op_make_function(self, frame, arg, line, col):
        frame.stack.append(
            BunFunction(arg["name"], arg["params"], arg, frame.env,
                        arg.get("filename"), arg.get("source"),
                        param_specs=arg.get("param_defs")))

    def _op_call(self, frame, arg, line, col):
        count, has_kwargs = arg if arg else (0, False)
        kwargs = {}
        if has_kwargs:
            raw = frame.stack.pop()
            if isinstance(raw, BunDict):
                for key in raw.keys():
                    kwargs[key] = raw.get(key)
        if count:
            args = frame.stack[-count:]
            del frame.stack[-count:]
        else:
            args = []
        callee = frame.stack.pop()
        return self._call_function(frame, callee, args, kwargs)

    def _call_function(self, frame, callee, args, kwargs, borrowed=0):
        """Run a call. The answer stays on the stack of the frame.

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
                frame.stack.append(generator)
                return None
            if frame.depth >= self.MAX_FRAMES:
                raise BunRuntimeError("stack overflow")
            return Frame(callee.body, call_env, frame.base_dir, caller=frame)
        if isinstance(callee, Builtin):
            if kwargs:
                raise BunRuntimeError(
                    "builtin '%s' does not accept keyword arguments"
                    % callee.name)
            frame.stack.append(callee.func(args))
            return None
        raise BunRuntimeError(
            "%s is not callable" % stringify(callee))

    def _op_return(self, frame, arg, line, col):
        value = copy_value(frame.stack.pop())
        generator = frame.root().generator
        if generator is not None:
            # The body of a generator is over, and it gives its last
            # value to the program.
            generator.finish(value)
            return _DONE
        if frame.caller is None:
            raise _TopLevelReturn(
                BunRuntimeError("'return' outside of a function", line, col))
        frame.caller.stack.append(value)
        return frame.caller

    def _op_halt(self, frame, arg, line, col):
        return _DONE

    def _op_yield(self, frame, arg, line, col):
        value = frame.stack.pop()
        generator = frame.root().generator
        if generator is None:
            raise BunRuntimeError("'yield' outside of a generator", line, col)
        frame.stack.append(generator.yield_value(value))

    def _op_index(self, frame, arg, line, col):
        index = frame.stack.pop()
        obj = frame.stack.pop()
        frame.stack.append(ops.index_value(obj, index))

    def _op_slice(self, frame, arg, line, col):
        step = frame.stack.pop()
        stop = frame.stack.pop()
        start = frame.stack.pop()
        obj = frame.stack.pop()
        frame.stack.append(ops.slice_value(obj, start, stop, step))

    def _op_store_slice(self, frame, arg, line, col):
        step = frame.stack.pop()
        stop = frame.stack.pop()
        start = frame.stack.pop()
        obj = frame.stack.pop()
        value = frame.stack.pop()
        ops.assign_slice(obj, start, stop, step, value)

    def _op_unpack_plan(self, frame, arg, line, col):
        value = frame.stack.pop()
        items = ops.unpack_items(value)
        values = ops.unpack_plan(arg, items)
        for item in reversed(values):
            frame.stack.append(item)

    def _op_store_index(self, frame, arg, line, col):
        index = frame.stack.pop()
        obj = frame.stack.pop()
        value = frame.stack.pop()
        ops.assign_index(obj, index, value)

    def _op_method_call(self, frame, arg, line, col):
        method, count = arg
        if count:
            args = frame.stack[-count:]
            del frame.stack[-count:]
        else:
            args = []
        receiver = frame.stack.pop()
        if isinstance(receiver, BunStruct):
            function = ops.struct_method(receiver.type_name, method)
            if isinstance(function, BunFunction):
                return self._call_function(
                    frame, function, [receiver] + args, {}, borrowed=1)
        frame.stack.append(ops.method_call(method, receiver, args))

    def _op_make_struct(self, frame, arg, line, col):
        type_name, field_names = arg
        count = len(field_names)
        if count:
            values = frame.stack[-count:]
            del frame.stack[-count:]
        else:
            values = []
        frame.stack.append(ops.make_struct(type_name, field_names, values))

    def _op_get_field(self, frame, arg, line, col):
        obj = frame.stack.pop()
        frame.stack.append(ops.get_field(obj, arg))

    def _op_set_field(self, frame, arg, line, col):
        value = frame.stack.pop()
        obj = frame.stack.pop()
        ops.set_field(obj, arg, copy_value(value))

    def _op_register_impl(self, frame, arg, line, col):
        type_name, method, body = arg
        function = BunFunction(body["name"], body["params"], body,
                               frame.env, body.get("filename"),
                               body.get("source"),
                               param_specs=body.get("param_defs"))
        ops.register_impl(type_name, method, function)

    def _op_try(self, frame, arg, line, col):
        frame.handlers.append(
            ("catch", arg, frame.env, len(frame.stack), len(frame.iterators)))

    def _op_try_finally(self, frame, arg, line, col):
        frame.handlers.append(
            ("finally", arg, frame.env, len(frame.stack), len(frame.iterators)))

    def _op_end_try(self, frame, arg, line, col):
        frame.handlers.pop()

    def _op_finally_end(self, frame, arg, line, col):
        error = frame.pending_error
        if error is not None:
            frame.pending_error = None
            raise error

    def _op_protocol_get(self, frame, arg, line, col):
        name = frame.stack.pop()
        target = frame.stack.pop()
        method = None
        if isinstance(target, BunDict):
            method = target.get(name)
        if method is None:
            raise BunRuntimeError(
                "'with' target does not implement '%s'" % arg, line, col)
        if not isinstance(method, (BunFunction, Builtin)):
            raise BunRuntimeError(
                "'with' target method '%s' is not callable" % arg, line, col)
        frame.stack.append(method)

    def _op_with_enter(self, frame, arg, line, col):
        result = frame.stack.pop()
        target = frame.stack.pop()
        frame.env.define(arg, result, True)
        frame.with_stack.append(target)

    def _op_scope_enter(self, frame, arg, line, col):
        frame.scopes.append(tasks.scope_enter())

    def _op_scope_exit(self, frame, arg, line, col):
        if not frame.scopes:
            raise BunRuntimeError("'scope' without an open group", line, col)
        state = frame.scopes.pop()
        error = tasks.scope_exit(state)
        if error is not None and frame.pending_error is None:
            raise tasks.as_runtime_error(error)

    def _op_with_pop_target(self, frame, arg, line, col):
        if not frame.with_stack:
            raise BunRuntimeError("'with' has no active target", line, col)
        frame.stack.append(frame.with_stack.pop())

    def _op_with_depth(self, frame, arg, line, col):
        frame.stack.append(len(frame.with_stack))

    def _op_has_error(self, frame, arg, line, col):
        frame.stack.append(frame.pending_error is not None)

    def _op_pending_error(self, frame, arg, line, col):
        error = frame.pending_error
        frame.stack.append(error.msg if error is not None else None)

    def _op_clear_error(self, frame, arg, line, col):
        frame.pending_error = None

    def _op_throw(self, frame, arg, line, col):
        cause = None
        if arg:
            cause = stringify(frame.stack.pop())
        value = frame.stack.pop()
        raise BunRuntimeError(stringify(value), line, col, cause=cause)

    def _op_assert(self, frame, arg, line, col):
        if arg:
            message = stringify(frame.stack.pop())
            raise BunRuntimeError("assertion failed: " + message, line, col)
        raise BunRuntimeError("assertion failed", line, col)

    def _op_match_test(self, frame, arg, line, col):
        value = frame.stack.pop()
        bindings = []
        if not patterns.match_pattern(value, arg, bindings):
            frame.stack.append(False)
            return
        for name, bound in bindings:
            frame.env.define(name, bound, True)
        frame.stack.append(True)

    def _op_match_fail(self, frame, arg, line, col):
        value = frame.stack.pop()
        raise BunRuntimeError("no matching case for %s" % repr_value(value),
                              line, col)

    def _env_base_dir(self, env, default):
        while env is not None:
            module_dir = getattr(env, "module_dir", None)
            if module_dir is not None:
                return module_dir
            env = env.parent
        return default

    def _op_import(self, frame, arg, line, col):
        path, names = arg
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
                error.line, error.col = line, col
            raise
        for name in names:
            if name not in exports:
                raise BunRuntimeError(
                    "module '%s' does not export '%s'" % (path, name))
            frame.env.define(name, exports[name], False)

    def _op_record_export(self, frame, arg, line, col):
        if not self.export_stack:
            raise BunRuntimeError("'export' is only allowed in modules")
        self.export_stack[-1][arg] = frame.env.get(arg)

    def _run_module(self, path, full_path):
        program = load_module_source(path, full_path)
        code = Compiler(full_path, read_source(full_path)).compile_program(program)
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

    def _op_binary(self, frame, arg, line, col):
        right = frame.stack.pop()
        left = frame.stack.pop()
        frame.stack.append(ops.binary_op(arg, left, right))

    def _op_unary(self, frame, arg, line, col):
        frame.stack.append(ops.unary_op(arg, frame.stack.pop()))

    def _op_unwrap_or_return(self, frame, arg, line, col):
        ok, payload = ops.unwrap_result(frame.stack.pop())
        if ok:
            frame.stack.append(payload)
            return None
        frame.stack.append(payload)
        return self._op_return(frame, arg, line, col)

    def _op_jump(self, frame, arg, line, col):
        frame.ip = arg

    def _op_jump_if_false(self, frame, arg, line, col):
        if not is_truthy(frame.stack.pop()):
            frame.ip = arg

    def _op_jump_if_true(self, frame, arg, line, col):
        if is_truthy(frame.stack.pop()):
            frame.ip = arg

    def _op_for_setup(self, frame, arg, line, col):
        iterable = frame.stack.pop()
        if isinstance(iterable, BunDict):
            iterable = iterable.keys()
        if isinstance(iterable, BunSet):
            iterable = iterable.values()
        if is_generator(iterable):
            frame.iterators.append(iter(iterable))
            return
        if not isinstance(iterable, (list, str)):
            raise BunRuntimeError("value is not iterable")
        frame.iterators.append(iter(iterable))

    def _op_for_next(self, frame, arg, line, col):
        try:
            frame.stack.append(next(frame.iterators[-1]))
        except StopIteration:
            frame.iterators.pop()
            frame.ip = arg

    def _op_for_pop(self, frame, arg, line, col):
        if frame.iterators:
            frame.iterators.pop()

    DISPATCH = {
        OP_LOAD_CONST: _op_load_const,
        OP_BUILD_LIST: _op_build_list,
        OP_BUILD_DICT: _op_build_dict,
        OP_BUILD_STRING: _op_build_string,
        OP_LIST_APPEND: _op_list_append,
        OP_DICT_SET: _op_dict_set,
        OP_FORMAT: _op_format,
        OP_LOAD_NAME: _op_load_name,
        OP_DEFINE_NAME: _op_define_name,
        OP_STORE_NAME: _op_store_name,
        OP_POP: _op_pop,
        OP_DUP: _op_dup,
        OP_ENTER_SCOPE: _op_enter_scope,
        OP_EXIT_SCOPE: _op_exit_scope,
        OP_MAKE_FUNCTION: _op_make_function,
        OP_CALL: _op_call,
        OP_RETURN: _op_return,
        OP_HALT: _op_halt,
        OP_BINARY: _op_binary,
        OP_UNARY: _op_unary,
        OP_JUMP: _op_jump,
        OP_JUMP_IF_FALSE: _op_jump_if_false,
        OP_JUMP_IF_TRUE: _op_jump_if_true,
        OP_FOR_SETUP: _op_for_setup,
        OP_FOR_NEXT: _op_for_next,
        OP_FOR_POP: _op_for_pop,
        OP_INDEX: _op_index,
        OP_SLICE: _op_slice,
        OP_STORE_SLICE: _op_store_slice,
        OP_UNPACK_PLAN: _op_unpack_plan,
        OP_STORE_INDEX: _op_store_index,
        OP_METHOD_CALL: _op_method_call,
        OP_IMPORT: _op_import,
        OP_RECORD_EXPORT: _op_record_export,
        OP_TRY: _op_try,
        OP_TRY_FINALLY: _op_try_finally,
        OP_WITH_ENTER: _op_with_enter,
        OP_WITH_POP_TARGET: _op_with_pop_target,
        OP_PROTOCOL_GET: _op_protocol_get,
        OP_PENDING_ERROR: _op_pending_error,
        OP_CLEAR_ERROR: _op_clear_error,
        OP_WITH_DEPTH: _op_with_depth,
        OP_HAS_ERROR: _op_has_error,
        OP_END_TRY: _op_end_try,
        OP_FINALLY_END: _op_finally_end,
        OP_THROW: _op_throw,
        OP_ASSERT: _op_assert,
        OP_DEL: _op_del,
        OP_DEL_INDEX: _op_del_index,
        OP_YIELD: _op_yield,
        OP_MATCH_TEST: _op_match_test,
        OP_MATCH_FAIL: _op_match_fail,
        OP_SCOPE_ENTER: _op_scope_enter,
        OP_SCOPE_EXIT: _op_scope_exit,
        OP_MAKE_STRUCT: _op_make_struct,
        OP_GET_FIELD: _op_get_field,
        OP_SET_FIELD: _op_set_field,
        OP_REGISTER_IMPL: _op_register_impl,
        OP_UNWRAP_OR_RETURN: _op_unwrap_or_return,
    }
