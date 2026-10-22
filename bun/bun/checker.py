from __future__ import annotations
from .records import record

from . import ast, modules, ops, patterns, types
from .errors import BunError, BunTypeError


@record
class Binding:
    type: str
    params: list[dict | None] = None
    return_type: str | None = None
    mutable: bool = True


class Checker:
    def __init__(self):
        self.base_dir = None
        self.return_stack = []
        self.module_cache = {}
        self.module_loading = set()
        self.loop_depth = 0
        self.module_names = set()
        self.name_stack = []
        self.function_depth = 0

    def check(self, program, base_dir=None, scope=None):
        self.base_dir = base_dir
        if scope is None:
            scope = {}
        self._collect_functions(program.statements, scope)
        self._collect_module_names(program.statements)
        self._statements(program.statements, scope)
        return scope

    def _collect_module_names(self, statements):
        """Collect the names the module binds.

        The names are collected before the statements are checked, so a
        function may use a variable of the module that is defined further
        down. The name of a function is collected the same way.
        """
        for statement in statements:
            if isinstance(statement, ast.LetStmt):
                self.module_names.add(statement.name)
            elif isinstance(statement, ast.FnDecl):
                self.module_names.add(statement.name)
            elif isinstance(statement, ast.UnpackStmt):
                for name in self._unpack_names(statement.targets):
                    self.module_names.add(name)
            elif isinstance(statement, ast.ImportStmt):
                for name in statement.names:
                    self.module_names.add(name)

    def _bound_names(self, statements):
        """Collect the names a block binds.

        The names are collected for the whole block, so a name may be used
        before the statement that binds it. The check stays free of false
        positives, the order of the statements is not part of the type.
        """
        names = set()
        for statement in statements:
            self._collect_bound_names(statement, names)
        return names

    def _collect_bound_names(self, node, names):
        if isinstance(node, ast.LetStmt):
            names.add(node.name)
        elif isinstance(node, ast.FnDecl):
            names.add(node.name)
        elif isinstance(node, ast.AssignStmt):
            if isinstance(node.target, ast.Identifier):
                names.add(node.target.name)
            elif isinstance(node.target, ast.UnpackTarget):
                for name in self._unpack_names([node.target]):
                    names.add(name)
        elif isinstance(node, ast.UnpackStmt):
            for name in self._unpack_names(node.targets):
                names.add(name)
        elif isinstance(node, ast.ForStmt):
            for name in node.targets:
                names.add(name)
            self._collect_block_names(node.body, names)
        elif isinstance(node, ast.MatchStmt):
            for pattern, body in node.cases:
                for name in patterns.pattern_names(pattern):
                    names.add(name)
                self._collect_block_names(body, names)
        elif isinstance(node, ast.TryStmt):
            for name in node.catch_params:
                names.add(name)
            self._collect_block_names(node.try_block, names)
            if node.catch_block is not None:
                self._collect_block_names(node.catch_block, names)
            if node.finally_body is not None:
                self._collect_block_names(node.finally_body, names)
        elif isinstance(node, ast.WithStmt):
            for item in node.items:
                names.add(item.name)
            self._collect_block_names(node.body, names)
        elif isinstance(node, ast.ScopeStmt):
            self._collect_block_names(node.body, names)
        elif isinstance(node, ast.Block):
            self._collect_block_names(node, names)
        elif isinstance(node, ast.IfStmt):
            self._collect_block_names(node.then_branch, names)
            if node.else_branch is not None:
                self._collect_block_names(node.else_branch, names)
        elif isinstance(node, ast.WhileStmt):
            self._collect_block_names(node.body, names)

    def _collect_block_names(self, node, names):
        if isinstance(node, ast.Block):
            for statement in node.statements:
                self._collect_bound_names(statement, names)
        else:
            self._collect_bound_names(node, names)

    def _known_name(self, name):
        """Report whether a name is bound somewhere.

        The scope holds the names of the statements that were already
        checked, the name stack holds the names of the enclosing functions
        and the module holds the names of the module itself.
        """
        if name in self.module_names:
            return True
        for names in reversed(self.name_stack):
            if name in names:
                return True
        return False

    def _collect_functions(self, statements, scope):
        for statement in statements:
            if isinstance(statement, ast.FnDecl):
                scope[statement.name] = Binding(
                    types.FN, self._param_specs(statement), statement.return_type,
                    False)

    def _param_specs(self, fn):
        specs = []
        for param in fn.params:
            specs.append({
                "name": param.name,
                "type": param.type_name,
                "param_kind": param.param_kind,
                "has_default": param.default is not None,
            })
        return specs

    def _statements(self, statements, scope):
        for statement in statements:
            self._statement(statement, scope)

    def _statement(self, node, scope):
        if isinstance(node, ast.LetStmt):
            self._check_annotation(node.type_ann, node)
            value_type = self._expr(node.value, scope)
            if (node.type_ann is not None
                    and not types.is_assignable(value_type, node.type_ann)):
                raise BunTypeError(
                    "cannot assign value of type '%s' to variable '%s' of type '%s'"
                    % (value_type, node.name, node.type_ann), node.line, node.col)
            if (isinstance(node.value, ast.FnDecl)
                    and node.type_ann in (None, types.FN)):
                scope[node.name] = Binding(
                    types.FN, self._param_specs(node.value),
                    node.value.return_type, node.mutable)
            else:
                scope[node.name] = Binding(
                    node.type_ann or types.ANY, mutable=node.mutable)
        elif isinstance(node, ast.FnDecl):
            self._check_annotation(node.return_type, node)
            self._check_decorators(node, scope)
            self._function(node, scope)
            # The name of the function belongs to the block that holds it,
            # so a function that is defined inside a block may be called
            # there.
            scope[node.name] = Binding(
                types.FN, self._param_specs(node), node.return_type, False)
        elif isinstance(node, ast.AssignStmt):
            value_type = self._expr(node.value, scope)
            if isinstance(node.target, ast.Identifier):
                binding = scope.get(node.target.name)
                if (binding is not None and binding.type != types.ANY
                        and not types.is_assignable(value_type, binding.type)):
                    raise BunTypeError(
                        "cannot assign value of type '%s' to variable '%s' of type '%s'"
                        % (value_type, node.target.name, binding.type),
                        node.line, node.col)
                if binding is not None and not binding.mutable:
                    raise BunTypeError(
                        "cannot assign to immutable variable '%s'"
                        % node.target.name, node.line, node.col)
            elif isinstance(node.target, ast.UnpackTarget):
                for leaf in ops.plan_leaves(node.target.targets):
                    if not isinstance(leaf, ast.Identifier):
                        continue
                    binding = scope.get(leaf.name)
                    if binding is None:
                        continue
                    if (binding.type != types.ANY
                            and not types.is_assignable(value_type,
                                                       binding.type)):
                        raise BunTypeError(
                            "cannot assign value of type '%s' to variable '%s' of type '%s'"
                            % (value_type, leaf.name, binding.type),
                            node.line, node.col)
                    if not binding.mutable:
                        raise BunTypeError(
                            "cannot assign to immutable variable '%s'"
                            % leaf.name, node.line, node.col)
            else:
                self._expr(node.target, scope)
        elif isinstance(node, ast.ReturnStmt):
            if node.value is not None:
                value_type = self._expr(node.value, scope)
            else:
                value_type = types.NULL
            if self.return_stack:
                declared = self.return_stack[-1]
                if (declared is not None
                        and not types.is_assignable(value_type, declared)):
                    raise BunTypeError(
                        "cannot return value of type '%s' from function with return type '%s'"
                        % (value_type, declared), node.line, node.col)
        elif isinstance(node, ast.Block):
            self._statements(node.statements, dict(scope))
        elif isinstance(node, ast.IfStmt):
            self._expr(node.condition, scope)
            self._statement(node.then_branch, dict(scope))
            if node.else_branch is not None:
                self._statement(node.else_branch, dict(scope))
        elif isinstance(node, ast.WhileStmt):
            self._expr(node.condition, scope)
            self.loop_depth += 1
            try:
                self._statements(node.body.statements, dict(scope))
                if node.orelse is not None:
                    self._statement(node.orelse, dict(scope))
            finally:
                self.loop_depth -= 1
        elif isinstance(node, ast.ForStmt):
            self._expr(node.iterable, scope)
            loop_scope = dict(scope)
            for name in node.targets:
                loop_scope[name] = Binding(types.ANY)
            self.loop_depth += 1
            try:
                self._statements(node.body.statements, loop_scope)
                if node.orelse is not None:
                    # The else runs after the loop, so the name of the
                    # loop is gone by then.
                    self._statement(node.orelse, dict(scope))
            finally:
                self.loop_depth -= 1
        elif isinstance(node, ast.AssertStmt):
            self._expr(node.condition, scope)
            if node.message is not None:
                self._expr(node.message, scope)
        elif isinstance(node, ast.MatchStmt):
            self._expr(node.subject, scope)
            for pattern, body in node.cases:
                case_scope = dict(scope)
                for name in patterns.pattern_names(pattern):
                    case_scope[name] = Binding(types.ANY)
                guard = getattr(pattern, "guard", None)
                if guard is not None:
                    self._expr(guard, case_scope)
                self._statement(body, case_scope)
        elif isinstance(node, ast.ExprStmt):
            self._expr(node.expr, scope)
        elif isinstance(node, ast.DelStmt):
            self._expr(node.target, scope)
        elif isinstance(node, ast.YieldStmt):
            if self.function_depth == 0:
                raise BunTypeError(
                    "'yield' outside of a function", node.line, node.col)
            if node.value is not None:
                self._expr(node.value, scope)
        elif isinstance(node, ast.YieldExpr):
            if self.function_depth == 0:
                raise BunTypeError(
                    "'yield' outside of a function", node.line, node.col)
            if node.value is not None:
                self._expr(node.value, scope)
        elif isinstance(node, ast.UnpackStmt):
            self._expr(node.value, scope)
            for name in self._unpack_names(node.targets):
                scope[name] = Binding(types.ANY, mutable=node.mutable)
        elif isinstance(node, ast.Program):
            self._statements(node.statements, dict(scope))
        elif isinstance(node, ast.ImportStmt):
            self._import(node, scope)
        elif isinstance(node, ast.TryStmt):
            catch_scope = dict(scope)
            for name in node.catch_params:
                catch_scope[name] = Binding(types.ANY)
            self._statement(node.try_block, dict(scope))
            if node.catch_block is not None:
                self._statement(node.catch_block, catch_scope)
            if node.finally_body is not None:
                self._statement(node.finally_body, dict(scope))
        elif isinstance(node, ast.WithStmt):
            with_scope = dict(scope)
            for item in node.items:
                self._expr(item.expr, with_scope)
                with_scope[item.name] = Binding(types.ANY)
            self._statement(node.body, with_scope)
        elif isinstance(node, ast.ScopeStmt):
            self._statement(node.body, dict(scope))
        elif isinstance(node, ast.ThrowStmt):
            self._expr(node.value, scope)
            if node.cause is not None:
                self._expr(node.cause, scope)
        elif isinstance(node, ast.BreakStmt):
            if self.loop_depth == 0:
                raise BunTypeError(
                    "'break' outside of a loop", node.line, node.col)
        elif isinstance(node, ast.ContinueStmt):
            if self.loop_depth == 0:
                raise BunTypeError(
                    "'continue' outside of a loop", node.line, node.col)
        else:
            raise BunTypeError(
                "cannot check statement: %s" % type(node).__name__,
                getattr(node, "line", 0), getattr(node, "col", 0))

    def _function(self, fn, scope):
        local = dict(scope)
        specs = self._param_specs(fn)
        for spec in specs:
            self._check_annotation(spec["type"], fn)
            local[spec["name"]] = Binding(spec["type"] or types.ANY)
        names = set(spec["name"] for spec in specs)
        names |= self._bound_names(fn.body.statements)
        self.name_stack.append(names)
        self.return_stack.append(fn.return_type)
        saved_loop_depth = self.loop_depth
        self.loop_depth = 0
        self.function_depth += 1
        try:
            self._statements(fn.body.statements, local)
        finally:
            self.loop_depth = saved_loop_depth
            self.function_depth -= 1
            self.return_stack.pop()
            self.name_stack.pop()

    def _check_decorators(self, node, scope):
        """Check that every decorator of a function is a known function.

        A decorator is written as a name, so the name must be bound in
        the scope that holds the function, and it must be a function.
        The name of an import that is not checked yet is accepted, so
        that the order of the statements does not decide the meaning.
        """
        for decorator in node.decorators:
            name = decorator.name
            binding = scope.get(name)
            if binding is None:
                if self._known_name(name) or name in types.BUILTIN_SIGNATURES:
                    continue
                raise BunTypeError(
                    "undefined decorator '%s'" % name,
                    decorator.line, decorator.col)
            if binding.type not in (types.FN, types.ANY):
                raise BunTypeError(
                    "decorator '%s' is not a function" % name,
                    decorator.line, decorator.col)

    def _unpack_names(self, targets):
        """Collect the names bound by an unpacking pattern."""
        names = []
        for target in targets:
            if isinstance(target, ast.UnpackTarget):
                if target.target_kind == "star":
                    names.append(target.name)
                else:
                    names.extend(self._unpack_names(target.targets))
            else:
                names.append(target.name)
        return names

    def _check_annotation(self, name, node):
        if name is not None and not types.is_known_type(name):
            raise BunTypeError("unknown type '%s'" % name, node.line, node.col)

    def _import(self, node, scope):
        exports = self._module_exports(node.path, node)
        for name in node.names:
            if name not in exports:
                raise BunTypeError(
                    "module '%s' does not export '%s'" % (node.path, name),
                    node.line, node.col)
            binding = exports[name]
            scope[name] = Binding(
                binding.type, binding.params, binding.return_type, False)

    def _module_exports(self, path, node):
        try:
            full_path = modules.resolve_module_path(path, self.base_dir)
            program = modules.load_module_source(path, full_path)
        except BunError as error:
            message = error.msg
            prefix = "cannot load module '%s'" % path
            if not message.startswith(prefix):
                message = "%s: %s" % (prefix, message)
            raise BunTypeError(message, node.line, node.col)
        if full_path in self.module_cache:
            return self.module_cache[full_path]
        if full_path in self.module_loading:
            raise BunTypeError("circular import of '%s'" % path, node.line, node.col)
        self.module_loading.add(full_path)
        exports = {}
        try:
            previous_dir = self.base_dir
            self.base_dir = modules.module_dir(full_path)
            for statement in program.statements:
                if isinstance(statement, ast.ImportStmt):
                    self._import(statement, {})
                try:
                    binding = self._exported_binding(statement)
                except BunError as error:
                    raise BunTypeError(
                        "cannot load module '%s': %s" % (path, error.msg),
                        node.line, node.col)
                if binding is not None:
                    exports[binding[0]] = binding[1]
        finally:
            self.base_dir = previous_dir
            self.module_loading.discard(full_path)
        self.module_cache[full_path] = exports
        return exports

    def _exported_binding(self, statement):
        if isinstance(statement, ast.FnDecl) and statement.exported:
            self._check_annotation(statement.return_type, statement)
            for spec in self._param_specs(statement):
                self._check_annotation(spec["type"], statement)
            return statement.name, Binding(
                types.FN, self._param_specs(statement), statement.return_type,
                False)
        if isinstance(statement, ast.LetStmt) and statement.exported:
            self._check_annotation(statement.type_ann, statement)
            return statement.name, Binding(
                statement.type_ann or types.ANY, mutable=statement.mutable)
        return None

    def _expr(self, node, scope):
        if isinstance(node, ast.Literal):
            return self._literal_type(node.value)
        if isinstance(node, ast.Identifier):
            binding = scope.get(node.name)
            if binding is None:
                self._check_known_name(node)
                return types.ANY
            return binding.type
        if isinstance(node, ast.ListLiteral):
            for element in node.elements:
                self._expr(element, scope)
            return types.LIST
        if isinstance(node, ast.DictLiteral):
            for key, value in node.entries:
                self._expr(key, scope)
                self._expr(value, scope)
            return types.DICT
        if isinstance(node, ast.FString):
            for part in node.parts:
                if part.expr is not None:
                    self._expr(part.expr, scope)
            return types.STRING
        if isinstance(node, ast.YieldExpr):
            if self.function_depth == 0:
                raise BunTypeError(
                    "'yield' outside of a function", node.line, node.col)
            if node.value is not None:
                self._expr(node.value, scope)
            return types.ANY
        if isinstance(node, ast.FnDecl):
            for spec in self._param_specs(node):
                self._check_annotation(spec["type"], node)
            self._check_annotation(node.return_type, node)
            self._function(node, scope)
            return types.FN
        if isinstance(node, ast.Call):
            return self._call(node, scope)
        if isinstance(node, ast.Unary):
            self._expr(node.operand, scope)
            return types.ANY
        if isinstance(node, ast.Binary):
            self._expr(node.left, scope)
            self._expr(node.right, scope)
            return types.ANY
        if isinstance(node, ast.Logical):
            self._expr(node.left, scope)
            self._expr(node.right, scope)
            return types.ANY
        if isinstance(node, ast.Index):
            self._expr(node.target, scope)
            if isinstance(node.index, ast.Slice):
                for part in (node.index.start, node.index.stop,
                             node.index.step):
                    if part is not None:
                        self._expr(part, scope)
            else:
                self._expr(node.index, scope)
            return types.ANY
        if isinstance(node, ast.MethodCall):
            self._expr(node.receiver, scope)
            for arg in node.args:
                self._expr(arg, scope)
            return types.ANY
        if isinstance(node, ast.Comprehension):
            return self._comprehension(node, scope)
        raise BunTypeError(
            "cannot check expression: %s" % type(node).__name__,
            getattr(node, "line", 0), getattr(node, "col", 0))

    def _comprehension(self, node, scope):
        """Check a comprehension in its own scope.

        The loop targets are fresh mutable bindings, so they never leak
        into the enclosing scope and never shadow an immutable binding.
        """
        local = dict(scope)
        for clause in node.clauses:
            self._expr(clause.iterable, local)
            local[clause.target] = Binding(types.ANY, mutable=True)
        for clause in node.clauses:
            if clause.condition is not None:
                self._expr(clause.condition, local)
        if node.is_dict:
            self._expr(node.key, local)
            self._expr(node.value, local)
            return types.DICT
        self._expr(node.element, local)
        return types.LIST

    def _check_known_name(self, node):
        """Report a name that is not bound anywhere.

        The name of a builtin is always known, the name of an import is
        known as well, the name of a function is known even when the
        function is defined further down.
        """
        if node.name in types.BUILTIN_SIGNATURES:
            return
        if self._known_name(node.name):
            return
        raise BunTypeError(
            "undefined variable '%s'" % node.name, node.line, node.col)

    def _literal_type(self, value):
        if value is None:
            return types.NULL
        if isinstance(value, bool):
            return types.BOOL
        if isinstance(value, int):
            return types.INT
        if isinstance(value, float):
            return types.FLOAT
        if isinstance(value, str):
            return types.STRING
        return types.ANY

    def _call(self, node, scope):
        arg_types = [self._expr(arg, scope) for arg in node.args]
        kwarg_types = {}
        for name, value_node in node.kwargs:
            kwarg_types[name] = self._expr(value_node, scope)
        if not isinstance(node.callee, ast.Identifier):
            self._expr(node.callee, scope)
            return types.ANY
        name = node.callee.name
        binding = scope.get(name)
        if binding is None:
            if name in types.BUILTIN_SIGNATURES:
                return self._builtin_call(name, node, arg_types)
            self._check_known_name(node.callee)
            return types.ANY
        if binding.type == types.ANY:
            return types.ANY
        if binding.type != types.FN:
            raise BunTypeError(
                "'%s' of type '%s' is not callable" % (name, binding.type),
                node.line, node.col)
        if binding.params is None:
            return types.ANY
        self._check_call_args(name, binding.params, arg_types, kwarg_types, node)
        return binding.return_type or types.ANY

    def _check_call_args(self, name, specs, arg_types, kwarg_types, node):
        positional = [spec for spec in specs
                      if spec["param_kind"] == "positional"]
        kwonly = [spec for spec in specs if spec["param_kind"] == "kwonly"]
        has_vararg = any(spec["param_kind"] == "vararg" for spec in specs)
        has_kwarg = any(spec["param_kind"] == "kwarg" for spec in specs)
        plain = (not kwonly and not has_vararg and not has_kwarg
                 and all(not spec["has_default"] for spec in specs))
        if plain and not kwarg_types:
            if len(arg_types) != len(specs):
                raise BunTypeError(
                    "function '%s' expects %d argument(s), got %d"
                    % (name, len(specs), len(arg_types)), node.line, node.col)
            for arg_type, spec in zip(arg_types, specs):
                self._check_arg_type(arg_type, spec["type"], name, node)
            return
        known = {}
        for spec in positional + kwonly:
            known[spec["name"]] = spec
        if len(arg_types) > len(positional) and not has_vararg:
            raise BunTypeError(
                "function '%s' expects %d argument(s), got %d"
                % (name, len(positional), len(arg_types)), node.line, node.col)
        for index, arg_type in enumerate(arg_types):
            if index >= len(positional):
                break
            self._check_arg_type(arg_type, positional[index]["type"], name, node)
        for key, arg_type in kwarg_types.items():
            spec = known.get(key)
            if spec is None:
                if not has_kwarg:
                    raise BunTypeError(
                        "function '%s' got an unexpected keyword argument '%s'"
                        % (name, key), node.line, node.col)
                continue
            self._check_arg_type(arg_type, spec["type"], name, node)
        for index, spec in enumerate(positional):
            if index < len(arg_types) and spec["name"] in kwarg_types:
                raise BunTypeError(
                    "function '%s' got multiple values for argument '%s'"
                    % (name, spec["name"]), node.line, node.col)
        for index, spec in enumerate(positional):
            if index < len(arg_types):
                continue
            if spec["name"] in kwarg_types:
                continue
            if spec["has_default"]:
                continue
            raise BunTypeError(
                "function '%s' missing required argument '%s'"
                % (name, spec["name"]), node.line, node.col)
        for spec in kwonly:
            if spec["name"] in kwarg_types:
                continue
            if spec["has_default"]:
                continue
            raise BunTypeError(
                "function '%s' missing required argument '%s'"
                % (name, spec["name"]), node.line, node.col)

    def _check_arg_type(self, arg_type, ptype, name, node):
        if ptype is None:
            return
        if not types.is_assignable(arg_type, ptype):
            raise BunTypeError(
                "argument of type '%s' is not assignable to parameter of type '%s' in call to '%s'"
                % (arg_type, ptype, name), node.line, node.col)

    def _builtin_call(self, name, node, arg_types):
        for params, return_type in types.BUILTIN_SIGNATURES[name]:
            if len(params) != len(arg_types):
                continue
            for arg_type, ptype in zip(arg_types, params):
                if not types.is_assignable(arg_type, ptype):
                    break
            else:
                return return_type
        expected = " or ".join(
            str(len(params)) for params, _ in types.BUILTIN_SIGNATURES[name])
        raise BunTypeError(
            "%s() received arguments that do not match its signature (expected %s argument(s))"
            % (name, expected), node.line, node.col)
