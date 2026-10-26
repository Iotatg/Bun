import os
import threading

from . import ast
from . import modules
from . import ops
from . import patterns
from . import tasks
from .values import (
    BreakSignal, BunFunction, BunStruct, Builtin, ContinueSignal, ReturnSignal,
    copy_value, format_fstring_part, is_truthy, repr_value, stringify,
)
from .environment import Environment
from .builtins import register_builtins
from .dict import BunDict
from .generators import Generator, is_generator
from .set import BunSet
from .errors import BunRuntimeError
from .compiler import has_yield


class Interpreter:
    def __init__(self, program_args=None):
        self.globals = Environment()
        register_builtins(self.globals, program_args)
        self.modules = {}
        self.loading = set()
        self.export_stack = []
        self.last_value = None
        self.structs = {}
        # The generator that runs in this thread, if there is one.
        self._current = threading.local()

    def run(self, program, env=None, base_dir=None):
        env = env if env is not None else self.globals
        if base_dir is None:
            base_dir = os.getcwd()
        self.globals.module_dir = base_dir
        self._collect_structs(program.statements)
        try:
            self.execute(program, env)
        except ReturnSignal as signal:
            raise BunRuntimeError(
                "'return' outside of a function",
                signal.line, signal.col)
        except BreakSignal as signal:
            raise BunRuntimeError(
                "'break' outside of a loop",
                signal.line, signal.col)
        except ContinueSignal as signal:
            raise BunRuntimeError(
                "'continue' outside of a loop",
                signal.line, signal.col)

    def _collect_structs(self, statements):
        """Collect the struct declarations of the program.

        The declarations are collected before the program runs, so a
        constructor may be called before the declaration that names it.
        """
        for statement in statements:
            if isinstance(statement, ast.StructDecl):
                self.structs[statement.name] = statement

    def call_function(self, function, args, borrowed=0):
        args = list(args)
        for index in range(borrowed, len(args)):
            args[index] = copy_value(args[index])
        call_env = Environment(function.closure)
        for spec, source, payload in ops.bind_arguments(
                function.name, function.param_specs, args, {}):
            if source == "default":
                call_env.define(spec["name"], self.evaluate(payload, call_env), True)
            elif source == "kwarg":
                call_env.define(spec["name"], self._to_dict(payload), True)
            else:
                call_env.define(spec["name"], payload, True)
        if function.is_generator:
            return Generator(
                lambda gen: self._run_generator(function.body, call_env, gen),
                function.name or "anonymous")
        try:
            self._execute_block(function.body, call_env)
        except ReturnSignal as signal:
            return signal.value
        except BunRuntimeError as error:
            self._attach_function_frame(error, function)
            raise
        return None

    def _to_dict(self, mapping):
        result = BunDict()
        for key, value in mapping.items():
            result.set(key, value)
        return result

    def _attach_function_frame(self, error, function):
        if error.filename is not None or function.filename is None:
            return
        error.filename = function.filename
        try:
            with open(function.filename, "r") as handle:
                error.source = handle.read()
        except OSError:
            error.source = None

    def _env_base_dir(self, env):
        while env is not None:
            module_dir = getattr(env, "module_dir", None)
            if module_dir is not None:
                return module_dir
            env = env.parent
        return os.getcwd()

    def _env_module_file(self, env):
        while env is not None:
            module_file = getattr(env, "module_file", None)
            if module_file is not None:
                return module_file
            env = env.parent
        return None

    def _register_impl(self, node, env):
        """Record the methods of an impl block."""
        for method in node.methods:
            function = self._make_function(method, env)
            ops.register_impl(node.type_name, method.name, function)

    def _construct(self, declaration, args, env):
        """Build the value of a struct from the arguments of a call."""
        fields = declaration.fields
        if len(args) > len(fields):
            raise BunRuntimeError(
                "struct '%s' expects %d argument(s), got %d"
                % (declaration.name, len(fields), len(args)))
        values = []
        for index, field in enumerate(fields):
            if index < len(args):
                values.append(args[index])
            elif field.default is not None:
                values.append(self.evaluate(field.default, env))
            else:
                raise BunRuntimeError(
                    "struct '%s' is missing a value for field '%s'"
                    % (declaration.name, field.name))
        return ops.make_struct(
            declaration.name, [field.name for field in fields], values)

    def _make_function(self, node, env):
        return BunFunction(
            node.name or "anonymous",
            [param.name for param in node.params],
            node.body,
            env,
            self._env_module_file(env),
            param_specs=[ops.param_spec(param) for param in node.params],
            is_generator=has_yield(node.body))

    def _apply_decorators(self, node, value, env):
        """Apply the decorators of a function to it.

        The decorators are applied from the closest one to the function
        outwards, so the decorator that is written last is the one that
        is called first. Each of them receives the function and returns
        the value that the name of the function holds afterwards.
        """
        for decorator in reversed(node.decorators):
            callee = self.evaluate(decorator, env)
            value = self.call_value(callee, [value])
        return value

    def execute(self, node, env):
        try:
            self._execute(node, env)
        except BunRuntimeError as error:
            if error.line == 0 and getattr(node, "line", 0):
                error.line, error.col = node.line, node.col
            raise
        except RecursionError:
            raise BunRuntimeError("stack overflow")

    def evaluate(self, node, env):
        try:
            return self._evaluate(node, env)
        except BunRuntimeError as error:
            if error.line == 0 and getattr(node, "line", 0):
                error.line, error.col = node.line, node.col
            raise
        except RecursionError:
            raise BunRuntimeError("stack overflow")

    def _execute(self, node, env):
        if isinstance(node, ast.Program):
            for statement in node.statements:
                self.execute(statement, env)
        elif isinstance(node, ast.LetStmt):
            value = self.evaluate(node.value, env)
            env.define(node.name, copy_value(value), node.mutable)
            if node.exported:
                self._record_export(node.name, value)
        elif isinstance(node, ast.AssignStmt):
            self._assign(node.target, self.evaluate(node.value, env), env)
        elif isinstance(node, ast.UnpackStmt):
            self._unpack_declare(node, env)
        elif isinstance(node, ast.ExprStmt):
            self.last_value = self.evaluate(node.expr, env)
        elif isinstance(node, ast.Block):
            self._execute_block(node, env)
        elif isinstance(node, ast.IfStmt):
            if is_truthy(self.evaluate(node.condition, env)):
                self.execute(node.then_branch, env)
            elif node.else_branch is not None:
                self.execute(node.else_branch, env)
        elif isinstance(node, ast.WhileStmt):
            broke = False
            while is_truthy(self.evaluate(node.condition, env)):
                try:
                    self.execute(node.body, env)
                except BreakSignal:
                    broke = True
                    break
                except ContinueSignal:
                    continue
            if not broke and node.orelse is not None:
                # The else of a loop runs when the loop ends without a
                # break.
                self.execute(node.orelse, env)
        elif isinstance(node, ast.ForStmt):
            iterable = self.evaluate(node.iterable, env)
            if isinstance(iterable, BunDict):
                iterable = iterable.keys()
            if isinstance(iterable, BunSet):
                iterable = iterable.values()
            if not isinstance(iterable, (list, str)) \
                    and not is_generator(iterable):
                raise BunRuntimeError("value is not iterable")
            broke = False
            for item in iterable:
                loop_env = Environment(env)
                self._bind_loop_targets(loop_env, node.targets, item)
                try:
                    self.execute(node.body, loop_env)
                except BreakSignal:
                    broke = True
                    break
                except ContinueSignal:
                    continue
            if not broke and node.orelse is not None:
                # The else of a loop runs when the loop ends without a
                # break.
                self.execute(node.orelse, env)
        elif isinstance(node, ast.FnDecl):
            value = self._make_function(node, env)
            value = self._apply_decorators(node, value, env)
            env.define(node.name, value, False)
            if node.exported:
                self._record_export(node.name, value)
        elif isinstance(node, ast.StructDecl):
            self.structs[node.name] = node
        elif isinstance(node, ast.ProtocolDecl):
            # A protocol is a type, and a type is not a value: the program
            # that declares it runs the same with it and without it.
            pass
        elif isinstance(node, ast.ImplDecl):
            self._register_impl(node, env)
        elif isinstance(node, ast.ImportStmt):
            exports = self._load_module(node.path, node.line, node.col, env)
            for name in node.names:
                if name not in exports:
                    raise BunRuntimeError(
                        "module '%s' does not export '%s'" % (node.path, name))
                env.define(name, exports[name], False)
        elif isinstance(node, ast.ReturnStmt):
            value = self.evaluate(node.value, env) if node.value is not None else None
            raise ReturnSignal(copy_value(value), node.line, node.col)
        elif isinstance(node, ast.TryStmt):
            self._execute_try(node, env)
        elif isinstance(node, ast.WithStmt):
            self._execute_with(node, env)
        elif isinstance(node, ast.ScopeStmt):
            self._execute_scope(node, env)
        elif isinstance(node, ast.ThrowStmt):
            cause = None
            if node.cause is not None:
                cause = stringify(self.evaluate(node.cause, env))
            raise BunRuntimeError(stringify(self.evaluate(node.value, env)),
                                  node.line, node.col, cause=cause)
        elif isinstance(node, ast.BreakStmt):
            raise BreakSignal(node.line, node.col)
        elif isinstance(node, ast.ContinueStmt):
            raise ContinueSignal(node.line, node.col)
        elif isinstance(node, ast.AssertStmt):
            if not is_truthy(self.evaluate(node.condition, env)):
                if node.message is not None:
                    text = stringify(self.evaluate(node.message, env))
                    raise BunRuntimeError("assertion failed: " + text,
                                          node.line, node.col)
                raise BunRuntimeError("assertion failed", node.line, node.col)
        elif isinstance(node, ast.MatchStmt):
            self._execute_match(node, env)
        elif isinstance(node, ast.DelStmt):
            self._execute_del(node, env)
        elif isinstance(node, ast.YieldStmt):
            self._yield_value(node, env)
        else:
            raise BunRuntimeError("unknown statement: %s" % type(node).__name__)

    def _bind_loop_targets(self, loop_env, targets, item):
        """Bind the value of a loop to the names of the loop."""
        if len(targets) == 1:
            loop_env.define(targets[0], item, True)
            return
        plan = ["seq"] + [["leaf"]] * len(targets)
        values = ops.unpack_plan(plan, ops.unpack_items(item))
        for name, value in zip(targets, values):
            loop_env.define(name, value, True)

    def _yield_value(self, node, env):
        """Give a value to the program and wait for the next one.

        The value of the expression is the value that the program sends
        back into the generator.
        """
        value = None
        if node.value is not None:
            value = self.evaluate(node.value, env)
        generator = getattr(self._current, "generator", None)
        if generator is None:
            raise BunRuntimeError("'yield' outside of a generator",
                                  node.line, node.col)
        return generator.yield_value(value)

    def _run_generator(self, body, env, generator):
        """Run the body of a generator in the thread of the generator."""
        self._current.generator = generator
        try:
            self._execute_block(body, env)
        except ReturnSignal as signal:
            generator.finish(signal.value)

    def _execute_del(self, node, env):
        """Run a `del` statement."""
        target = node.target
        if isinstance(target, ast.Identifier):
            env.delete(target.name)
            return
        container = self.evaluate(target.target, env)
        index = self.evaluate(target.index, env)
        ops.delete_index(container, index)

    def _execute_match(self, node, env):
        """Run a ``match`` statement.

        The first case whose pattern matches wins.  The names a pattern
        binds live in the scope of that case alone.
        """
        value = self.evaluate(node.subject, env)
        for pattern, body in node.cases:
            bindings = []
            if not patterns.match_pattern(value,
                                         patterns.plan_from_ast(pattern),
                                         bindings):
                continue
            case_env = Environment(env)
            for name, bound in bindings:
                case_env.define(name, bound, True)
            guard = getattr(pattern, "guard", None)
            if guard is not None and not is_truthy(self.evaluate(guard,
                                                                 case_env)):
                # A guard that does not hold sends the case on to the
                # next one, the same way a pattern that does not match.
                continue
            self.execute(body, case_env)
            return
        raise BunRuntimeError("no matching case for %s" % repr_value(value),
                              node.line, node.col)

    def _execute_block(self, block, env):
        block_env = Environment(env)
        for statement in block.statements:
            self.execute(statement, block_env)

    def _execute_try(self, node, env):
        try:
            try:
                self._execute_block(node.try_block, env)
            except BunRuntimeError as error:
                if node.catch_block is None:
                    raise
                catch_env = Environment(env)
                for name in node.catch_params:
                    catch_env.define(name, error.msg, True)
                self._execute_block(node.catch_block, catch_env)
        finally:
            if node.finally_body is not None:
                self._execute_block(node.finally_body, env)

    def _execute_with(self, node, env):
        entered = []
        error = None
        try:
            try:
                for item in node.items:
                    target = self.evaluate(item.expr, env)
                    enter = self._protocol_method(target, "__enter__")
                    value = self.call_value(enter, [])
                    entered.append(target)
                    env.define(item.name, value, True)
                self._execute_block(node.body, env)
            except BunRuntimeError as exc:
                error = exc
        finally:
            message = None if error is None else error.msg
            suppressed = self._run_exits(entered, message)
            if error is not None and not suppressed:
                raise error

    def _execute_scope(self, node, env):
        """Run a scope body inside a task group.

        The group joins every task that the body spawned.  An error of the
        body wins over an error of a child, because the body is the code
        that asked for the work.
        """
        state = tasks.scope_enter()
        try:
            self._execute_block(node.body, env)
        except BaseException:
            tasks.scope_exit(state)
            raise
        error = tasks.scope_exit(state)
        if error is not None:
            raise tasks.as_runtime_error(error)

    def _run_exits(self, entered, message):
        suppressed = False
        for target in reversed(entered):
            exit_fn = self._protocol_method(target, "__exit__")
            if self.call_value(exit_fn, [message]):
                suppressed = True
        return suppressed

    def _protocol_method(self, target, name):
        method = None
        if isinstance(target, BunDict):
            method = target.get(name)
        if method is None:
            raise BunRuntimeError(
                "'with' target does not implement '%s'" % name)
        if not isinstance(method, (BunFunction, Builtin)):
            raise BunRuntimeError(
                "'with' target method '%s' is not callable" % name)
        return method

    def call_value(self, callee, args):
        if isinstance(callee, BunFunction):
            call_env = Environment(callee.closure)
            for spec, source, payload in ops.bind_arguments(
                    callee.name, callee.param_specs, args, {}):
                if source == "default":
                    call_env.define(spec["name"],
                                    self.evaluate(payload, call_env), True)
                elif source == "kwarg":
                    call_env.define(spec["name"], self._to_dict(payload), True)
                else:
                    call_env.define(spec["name"], copy_value(payload), True)
            if callee.is_generator:
                # A generator gives its values one at a time, and it runs
                # in a thread of its own.
                return Generator(
                    lambda gen: self._run_generator(callee.body, call_env,
                                                    gen),
                    callee.name or "anonymous")
            try:
                self._execute_block(callee.body, call_env)
            except ReturnSignal as signal:
                return signal.value
            return None
        if isinstance(callee, Builtin):
            return callee.func(args)
        raise BunRuntimeError("%s is not callable" % stringify(callee))

    def _assign(self, target, value, env):
        if isinstance(target, ast.Identifier):
            env.assign(target.name, copy_value(value))
        elif isinstance(target, ast.UnpackTarget):
            self._unpack_assign(target, value, env)
        elif isinstance(target, ast.Attribute):
            obj = self.evaluate(target.object, env)
            ops.set_field(obj, target.name, copy_value(value))
        elif isinstance(target, ast.Index):
            if isinstance(target.index, ast.Slice):
                obj = self.evaluate(target.target, env)
                parts = []
                for part in (target.index.start, target.index.stop,
                             target.index.step):
                    parts.append(None if part is None
                                 else self.evaluate(part, env))
                ops.assign_slice(obj, parts[0], parts[1], parts[2], value)
            else:
                ops.assign_index(
                    self.evaluate(target.target, env),
                    self.evaluate(target.index, env),
                    value)
        else:
            raise BunRuntimeError("invalid assignment target")

    def _unpack_declare(self, node, env):
        value = self.evaluate(node.value, env)
        items = ops.unpack_items(value)
        plan = ops.build_unpack_plan(node.targets)
        values = ops.unpack_plan(plan, items)
        for target, item in zip(ops.plan_leaves(node.targets), values):
            if isinstance(target, ast.UnpackTarget):
                env.define(target.name, item, node.mutable)
            else:
                env.define(target.name, item, node.mutable)

    def _unpack_assign(self, target, value, env):
        items = ops.unpack_items(value)
        plan = ops.build_unpack_plan(target.targets)
        values = ops.unpack_plan(plan, items)
        for leaf, item in zip(ops.plan_leaves(target.targets), values):
            self._assign(leaf, item, env)

    def _evaluate(self, node, env):
        if isinstance(node, ast.Literal):
            return node.value
        if isinstance(node, ast.YieldExpr):
            return self._yield_value(node, env)
        if isinstance(node, ast.FnDecl):
            return self._make_function(node, env)
        if isinstance(node, ast.Identifier):
            return env.get(node.name)
        if isinstance(node, ast.ListLiteral):
            return [self.evaluate(element, env) for element in node.elements]
        if isinstance(node, ast.Comprehension):
            return self._comprehension(node, env)
        if isinstance(node, ast.DictLiteral):
            return self._dict_literal(node, env)
        if isinstance(node, ast.FString):
            return self._fstring(node, env)
        if isinstance(node, ast.Unary):
            return ops.unary_op(node.op, self.evaluate(node.operand, env))
        if isinstance(node, ast.Binary):
            return self._binary(node, env)
        if isinstance(node, ast.Logical):
            left = self.evaluate(node.left, env)
            if node.op == "and":
                return self.evaluate(node.right, env) if is_truthy(left) else left
            return left if is_truthy(left) else self.evaluate(node.right, env)
        if isinstance(node, ast.Call):
            return self._call(node, env)
        if isinstance(node, ast.Index):
            if isinstance(node.index, ast.Slice):
                return self._slice(node, env)
            return self._index(self.evaluate(node.target, env), self.evaluate(node.index, env))
        if isinstance(node, ast.MethodCall):
            return self._method_call(node, env)
        if isinstance(node, ast.Attribute):
            return ops.get_field(self.evaluate(node.object, env), node.name)
        if isinstance(node, ast.Unwrap):
            ok, payload = ops.unwrap_result(self.evaluate(node.expr, env))
            if ok:
                return payload
            raise ReturnSignal(payload, node.line, node.col)
        raise BunRuntimeError("unknown expression: %s" % type(node).__name__)

    def _dict_literal(self, node, env):
        result = BunDict()
        for key_node, value_node in node.entries:
            key = self.evaluate(key_node, env)
            result.set(key, self.evaluate(value_node, env))
        return result

    def _comprehension(self, node, env):
        """Evaluate a list or dict comprehension in its own scope."""
        scope = Environment(env)
        result = BunDict() if node.is_dict else []
        self._comprehension_clauses(node, node.clauses, 0, scope, result)
        return result

    def _comprehension_clauses(self, node, clauses, index, scope, result):
        if index >= len(clauses):
            if node.is_dict:
                key = self.evaluate(node.key, scope)
                result.set(key, self.evaluate(node.value, scope))
            else:
                result.append(self.evaluate(node.element, scope))
            return
        clause = clauses[index]
        iterable = self.evaluate(clause.iterable, scope)
        for item in iterable:
            scope.define(clause.target, item, True)
            if clause.condition is not None:
                if not is_truthy(self.evaluate(clause.condition, scope)):
                    continue
            self._comprehension_clauses(node, clauses, index + 1, scope, result)

    def _fstring(self, node, env):
        pieces = []
        for part in node.parts:
            if part.literal is not None:
                pieces.append(part.literal)
                continue
            value = self.evaluate(part.expr, env)
            pieces.append(self._fstring_part(part, value))
        return "".join(pieces)

    def _fstring_part(self, part, value):
        return format_fstring_part(part.spec, part.conv, part.source_text, value)

    def _binary(self, node, env):
        return ops.binary_op(
            node.op,
            self.evaluate(node.left, env),
            self.evaluate(node.right, env))

    def _call(self, node, env):
        if isinstance(node.callee, ast.Identifier):
            declaration = self.structs.get(node.callee.name)
            if declaration is not None:
                args = [self.evaluate(arg, env) for arg in node.args]
                return self._construct(declaration, args, env)
        callee = self.evaluate(node.callee, env)
        args = [self.evaluate(arg, env) for arg in node.args]
        kwargs = {}
        for name, value_node in node.kwargs:
            kwargs[name] = self.evaluate(value_node, env)
        if isinstance(callee, BunFunction):
            call_env = Environment(callee.closure)
            for spec, source, payload in ops.bind_arguments(
                    callee.name, callee.param_specs, args, kwargs):
                if source == "default":
                    call_env.define(spec["name"], self.evaluate(payload, call_env), True)
                elif source == "kwarg":
                    call_env.define(spec["name"], self._to_dict(payload), True)
                else:
                    call_env.define(spec["name"], copy_value(payload), True)
            if callee.is_generator:
                # A generator gives its values one at a time, and it runs
                # in a thread of its own.
                return Generator(
                    lambda gen: self._run_generator(callee.body, call_env,
                                                    gen),
                    callee.name or "anonymous")
            try:
                self._execute_block(callee.body, call_env)
            except ReturnSignal as signal:
                return signal.value
            return None
        if isinstance(callee, Builtin):
            if kwargs:
                raise BunRuntimeError(
                    "builtin '%s' does not accept keyword arguments" % callee.name)
            return callee.func(args)
        raise BunRuntimeError("%s is not callable" % stringify(callee))

    def _method_call(self, inner, env):
        receiver = self.evaluate(inner.receiver, env)
        args = [self.evaluate(arg, env) for arg in inner.args]
        if isinstance(receiver, BunStruct):
            function = ops.struct_method(receiver.type_name, inner.method)
            if isinstance(function, BunFunction):
                return self.call_function(function, [receiver] + args, borrowed=1)
            return ops.method_call(inner.method, receiver, args)
        return ops.method_call(inner.method, receiver, args)

    def _index(self, obj, index):
        return ops.index_value(obj, index)

    def _slice(self, node, env):
        """Evaluate `target[start:stop:step]`."""
        target = self.evaluate(node.target, env)
        parts = []
        for part in (node.index.start, node.index.stop, node.index.step):
            parts.append(None if part is None else self.evaluate(part, env))
        return ops.slice_value(target, parts[0], parts[1], parts[2])

    def _record_export(self, name, value):
        if not self.export_stack:
            raise BunRuntimeError("'export' is only allowed in modules")
        self.export_stack[-1][name] = value

    def _load_module(self, path, line, col, env):
        base_dir = self._env_base_dir(env)
        try:
            full_path = modules.resolve_module_path(path, base_dir)
            if full_path in self.modules:
                return self.modules[full_path]
            if full_path in self.loading:
                raise BunRuntimeError("circular import of '%s'" % path)
            program = modules.load_module_source(path, full_path)
        except BunRuntimeError as error:
            if error.line == 0:
                error.line, error.col = line, col
            raise
        module_env = Environment(self.globals)
        module_env.module_dir = modules.module_dir(full_path)
        module_env.module_file = full_path
        self.loading.add(full_path)
        self.export_stack.append({})
        try:
            try:
                self.execute(program, module_env)
            except BunRuntimeError as error:
                self._attach_module_frame(error, full_path, path)
                raise
            except ReturnSignal as signal:
                error = BunRuntimeError(
                    "'return' outside of a function",
                    signal.line, signal.col)
                self._attach_module_frame(error, full_path, path)
                raise error
        finally:
            exports = self.export_stack.pop()
            self.loading.discard(full_path)
        self.modules[full_path] = exports
        return exports

    def _attach_module_frame(self, error, full_path, path):
        modules.attach_module_frame(error, full_path, path)
