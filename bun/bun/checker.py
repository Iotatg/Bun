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
    type_params: list | None = None


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
        self.structs = {}
        self.impls = {}
        self.protocols = {}
        self.type_vars = []
        self._checking_method = None

    def check(self, program, base_dir=None, scope=None):
        self.base_dir = base_dir
        if scope is None:
            scope = {}
        self._collect_functions(program.statements, scope)
        self._collect_structs(program.statements, scope)
        self._collect_protocols(program.statements)
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
            elif isinstance(statement, ast.StructDecl):
                self.module_names.add(statement.name)
            elif isinstance(statement, ast.ProtocolDecl):
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
        elif isinstance(node, ast.StructDecl):
            names.add(node.name)
        elif isinstance(node, ast.ProtocolDecl):
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
                    False, statement.type_params)

    def _push_type_vars(self, fn):
        """Make the type parameters of a function the types in scope.

        A type parameter is a name of a type that is not known yet, so
        the body of the function is checked with it in place of a type.
        """
        frame = {}
        seen = set()
        for param in fn.type_params:
            if param.name in seen:
                raise BunTypeError(
                    "duplicate type parameter '%s'" % param.name,
                    param.line, param.col)
            if param.bound is not None and param.bound not in types.BOUND_NAMES:
                raise BunTypeError(
                    "unknown bound '%s'" % param.bound, param.line, param.col)
            seen.add(param.name)
            frame[param.name] = param.bound
        self.type_vars.append(frame)

    def _pop_type_vars(self):
        self.type_vars.pop()

    def _is_type_var(self, name):
        """Report whether a name is a type parameter in scope."""
        for frame in reversed(self.type_vars):
            if name in frame:
                return True
        return False

    def _type_var_bound(self, name):
        """The bound of a type parameter in scope."""
        for frame in reversed(self.type_vars):
            if name in frame:
                return frame[name]
        return None

    def _collect_structs(self, statements, scope):
        for statement in statements:
            if isinstance(statement, ast.StructDecl):
                self.structs[statement.name] = statement
                scope[statement.name] = Binding(types.STRUCT, mutable=False)
            elif isinstance(statement, ast.ImplDecl):
                methods = self.impls.setdefault(statement.type_name, {})
                for method in statement.methods:
                    methods[method.name] = method

    def _collect_protocols(self, statements):
        """Collect the protocols of the program.

        The protocols are collected before the statements are checked, so
        a protocol may be used before the declaration that names it.
        """
        for statement in statements:
            if isinstance(statement, ast.ProtocolDecl):
                methods = {}
                for method in statement.methods:
                    methods[method.name] = method
                self.protocols[statement.name] = methods

    def _missing_method(self, source, protocol_name):
        """The first method of a protocol that a type does not have.

        A protocol is satisfied by a type that has every method of the
        protocol, so the check of a protocol is a check of the methods.
        """
        if source == types.ANY:
            return None
        if source in self.protocols:
            methods = self.protocols[source]
        else:
            methods = self.impls.get(source)
        if methods is None:
            methods = {}
        for name in self.protocols[protocol_name]:
            if name not in methods:
                return name
        return None

    def _check_assignable(self, source, target, node, template, *extra):
        """Check that a value of the source type fits the target type.

        The message is written only when the check fails.  A protocol
        says which method is missing, because that is the part the
        program has to add.  A target that is a type parameter takes any
        type that satisfies its bound: the type of the parameter is not
        known yet.
        """
        if target in self.protocols:
            missing = self._missing_method(source, target)
            if missing is not None:
                raise BunTypeError(
                    "type '%s' does not satisfy protocol '%s': missing method '%s'"
                    % (source, target, missing), node.line, node.col)
            return
        if self._is_type_var(target):
            bound = self._type_var_bound(target)
            # A type parameter satisfies the bound of another type
            # parameter: the type is not known yet.
            if (not self._is_type_var(source)
                    and not types.satisfies_bound(source, bound)):
                raise BunTypeError(template % ((source, target) + extra),
                                   node.line, node.col)
            return
        if not types.is_assignable(source, target):
            raise BunTypeError(template % ((source, target) + extra),
                               node.line, node.col)

    def _assign_template(self, name):
        """The message of a value that does not fit the type of a name."""
        return ("cannot assign value of type '%s' to variable '" + name
                + "' of type '%s'")

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
            if node.type_ann is not None:
                self._check_assignable(
                    value_type, node.type_ann, node,
                    self._assign_template(node.name))
            if (isinstance(node.value, ast.FnDecl)
                    and node.type_ann in (None, types.FN)):
                scope[node.name] = Binding(
                    types.FN, self._param_specs(node.value),
                    node.value.return_type, node.mutable,
                    node.value.type_params)
            else:
                bound_type = node.type_ann or types.ANY
                if node.type_ann is None and value_type in self.structs:
                    bound_type = value_type
                scope[node.name] = Binding(bound_type, mutable=node.mutable)
        elif isinstance(node, ast.FnDecl):
            self._push_type_vars(node)
            try:
                self._check_annotation(node.return_type, node)
                self._check_decorators(node, scope)
                self._function(node, scope)
            finally:
                self._pop_type_vars()
            # The name of the function belongs to the block that holds it,
            # so a function that is defined inside a block may be called
            # there.
            scope[node.name] = Binding(
                types.FN, self._param_specs(node), node.return_type, False,
                node.type_params)
        elif isinstance(node, ast.AssignStmt):
            value_type = self._expr(node.value, scope)
            if isinstance(node.target, ast.Identifier):
                binding = scope.get(node.target.name)
                if binding is not None and binding.type != types.ANY:
                    self._check_assignable(
                        value_type, binding.type, node,
                        self._assign_template(node.target.name))
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
                    if binding.type != types.ANY:
                        self._check_assignable(
                            value_type, binding.type, node,
                            self._assign_template(leaf.name))
                    if not binding.mutable:
                        raise BunTypeError(
                            "cannot assign to immutable variable '%s'"
                            % leaf.name, node.line, node.col)
            elif isinstance(node.target, ast.Attribute):
                obj_type = self._expr(node.target.object, scope)
                self._check_field_assign(node.target, obj_type, node, scope)
            else:
                self._expr(node.target, scope)
        elif isinstance(node, ast.StructDecl):
            self._check_struct(node, scope)
        elif isinstance(node, ast.ImplDecl):
            self._check_impl(node, scope)
        elif isinstance(node, ast.ProtocolDecl):
            self._check_protocol(node, scope)
        elif isinstance(node, ast.ReturnStmt):
            if node.value is not None:
                value_type = self._expr(node.value, scope)
            else:
                value_type = types.NULL
            if self.return_stack:
                declared = self.return_stack[-1]
                if declared is not None:
                    self._check_assignable(
                        value_type, declared, node,
                        "cannot return value of type '%s' from function with "
                        "return type '%s'")
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
            item_type = self._expr(node.iterable, scope)
            element = self._element_type(item_type)
            loop_scope = dict(scope)
            for name in node.targets:
                loop_scope[name] = Binding(element or types.ANY)
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
        if name is None:
            return
        if self._is_type_var(name):
            return
        base = types.base_type(name)
        if types.is_known_type(base) or base in self.structs:
            for arg in types.type_args(name):
                self._check_annotation(arg, node)
            return
        if name in self.protocols:
            return
        raise BunTypeError("unknown type '%s'" % name, node.line, node.col)

    def _check_protocol(self, node, scope):
        """Check a protocol: the signatures of its methods."""
        seen = set()
        for method in node.methods:
            if method.name in seen:
                raise BunTypeError(
                    "duplicate method '%s' on protocol '%s'"
                    % (method.name, node.name), method.line, method.col)
            seen.add(method.name)
            self._check_annotation(method.return_type, method)
            for param in method.params:
                self._check_annotation(param.type_name, method)

    def _check_struct(self, node, scope):
        seen = set()
        for field in node.fields:
            if field.name in seen:
                raise BunTypeError(
                    "duplicate field '%s' on struct '%s'"
                    % (field.name, node.name), field.line, field.col)
            seen.add(field.name)
            self._check_annotation(field.type_ann, field)
            if field.default is not None:
                self._expr(field.default, scope)
        scope[node.name] = Binding(types.STRUCT, mutable=False)

    def _check_impl(self, node, scope):
        if node.type_name not in self.structs:
            raise BunTypeError(
                "impl of unknown type '%s'" % node.type_name,
                node.line, node.col)
        struct = self.structs[node.type_name]
        for method in node.methods:
            self._check_annotation(method.return_type, method)
            method.mutating = self._method_mutates(method)
            local = dict(scope)
            for spec in self._param_specs(method):
                self._check_annotation(spec["type"], method)
                if spec["name"] == "self":
                    local["self"] = Binding(node.type_name, mutable=True)
                else:
                    local[spec["name"]] = Binding(spec["type"] or types.ANY)
            names = set(spec["name"] for spec in self._param_specs(method))
            names |= self._bound_names(method.body.statements)
            self.name_stack.append(names)
            self.return_stack.append(method.return_type)
            saved = self._checking_method
            self._checking_method = (node.type_name, struct)
            self.function_depth += 1
            try:
                self._statements(method.body.statements, local)
            finally:
                self.function_depth -= 1
                self.return_stack.pop()
                self.name_stack.pop()
                self._checking_method = saved

    def _method_mutates(self, method):
        return self._assigns_self_field(method.body)

    def _assigns_self_field(self, node):
        if isinstance(node, ast.AssignStmt):
            target = node.target
            if (isinstance(target, ast.Attribute)
                    and isinstance(target.object, ast.Identifier)
                    and target.object.name == "self"):
                return True
        if isinstance(node, ast.Block):
            return any(self._assigns_self_field(s) for s in node.statements)
        if isinstance(node, ast.IfStmt):
            if self._assigns_self_field(node.then_branch):
                return True
            if node.else_branch is not None:
                return self._assigns_self_field(node.else_branch)
            return False
        if isinstance(node, (ast.WhileStmt, ast.ForStmt)):
            if self._assigns_self_field(node.body):
                return True
            if node.orelse is not None:
                return self._assigns_self_field(node.orelse)
            return False
        if isinstance(node, list):
            return any(self._assigns_self_field(item) for item in node)
        return False

    def _check_field_assign(self, attr, obj_type, node, scope):
        if obj_type == types.ANY:
            return
        struct = self.structs.get(obj_type)
        if struct is None:
            raise BunTypeError(
                "type '%s' has no fields" % obj_type, attr.line, attr.col)
        field = self._field(struct, attr.name)
        if field is None:
            raise BunTypeError(
                "unknown field '%s' on %s" % (attr.name, obj_type),
                attr.line, attr.col)
        if not field.mutable:
            raise BunTypeError(
                "cannot assign to immutable field '%s'" % attr.name,
                attr.line, attr.col)
        if (isinstance(attr.object, ast.Identifier)
                and attr.object.name != "self"):
            binding = scope.get(attr.object.name)
            if binding is not None and not binding.mutable:
                raise BunTypeError(
                    "cannot assign to field of immutable variable '%s'"
                    % attr.object.name, attr.line, attr.col)

    def _field(self, struct, name):
        for field in struct.fields:
            if field.name == name:
                return field
        return None

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
                if node.name in self.protocols:
                    raise BunTypeError(
                        "protocol '%s' is not a value" % node.name,
                        node.line, node.col)
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
            target_type = self._expr(node.target, scope)
            if isinstance(node.index, ast.Slice):
                for part in (node.index.start, node.index.stop,
                             node.index.step):
                    if part is not None:
                        self._expr(part, scope)
                return target_type
            self._expr(node.index, scope)
            return self._element_type(target_type) or types.ANY
        if isinstance(node, ast.MethodCall):
            return self._method_call(node, scope)
        if isinstance(node, ast.Attribute):
            obj_type = self._expr(node.object, scope)
            if obj_type == types.ANY:
                return types.ANY
            if obj_type == types.STRUCT:
                return types.ANY
            struct = self.structs.get(obj_type)
            if struct is None:
                raise BunTypeError(
                    "type '%s' has no fields" % obj_type, node.line, node.col)
            field = self._field(struct, node.name)
            if field is None:
                raise BunTypeError(
                    "unknown field '%s' on %s" % (node.name, obj_type),
                    node.line, node.col)
            return field.type_ann or types.ANY
        if isinstance(node, ast.Comprehension):
            return self._comprehension(node, scope)
        if isinstance(node, ast.Unwrap):
            return self._unwrap(node, scope)
        raise BunTypeError(
            "cannot check expression: %s" % type(node).__name__,
            getattr(node, "line", 0), getattr(node, "col", 0))

    def _unwrap(self, node, scope):
        """Check a postfix `?`.

        The operator is only legal inside a function, and the function
        has to return a `result` (or leave the type unknown).  A value
        whose type is known and is not a `result` is an error; a value
        of type `any` is left to the runtime.
        """
        if self.function_depth == 0:
            raise BunTypeError(
                "the '?' operator is only allowed inside a function",
                node.line, node.col)
        if self.return_stack:
            declared = self.return_stack[-1]
            if declared is not None and declared != types.RESULT \
                    and declared != types.ANY:
                raise BunTypeError(
                    "the '?' operator needs a function that returns 'result'",
                    node.line, node.col)
        source = self._expr(node.expr, scope)
        if source not in (types.RESULT, types.ANY, types.DICT):
            raise BunTypeError(
                "cannot use '?' on a value of type '%s'" % source,
                node.line, node.col)
        return types.ANY

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
        if binding.type == types.STRUCT:
            return self._constructor_call(name, arg_types, node)
        if binding.type != types.FN:
            raise BunTypeError(
                "'%s' of type '%s' is not callable" % (name, binding.type),
                node.line, node.col)
        if binding.params is None:
            return types.ANY
        if binding.type_params:
            return self._generic_call(
                name, binding, node, arg_types, kwarg_types, scope)
        self._check_call_args(name, binding.params, arg_types, kwarg_types, node)
        return binding.return_type or types.ANY

    def _generic_call(self, name, binding, node, arg_types, kwarg_types, scope):
        """Check the call of a generic function and give its type.

        The type arguments are found by matching the declared types of
        the parameters with the types of the arguments.  A type
        argument that cannot be found is `any`, a bound that the type
        does not satisfy is an error, and the type of the call is the
        declared return type with the type arguments put in place of
        the type parameters.
        """
        type_params = binding.type_params or []
        type_vars = set(param.name for param in type_params)
        bindings = {}
        specs = binding.params or []
        positional = [spec for spec in specs
                      if spec["param_kind"] == "positional"]
        for index, arg in enumerate(node.args):
            if index >= len(positional):
                break
            declared = positional[index]["type"]
            if declared is None:
                continue
            self._unify(declared, self._infer_type(arg, scope),
                        type_vars, bindings)
        known = {}
        for spec in positional:
            known[spec["name"]] = spec
        for key, value_node in node.kwargs:
            spec = known.get(key)
            if spec is None or spec["type"] is None:
                continue
            self._unify(spec["type"], self._infer_type(value_node, scope),
                        type_vars, bindings)
        for param in type_params:
            found = bindings.get(param.name, types.ANY)
            if not types.satisfies_bound(found, param.bound):
                raise BunTypeError(
                    "type '%s' does not satisfy the bound '%s' of type "
                    "parameter '%s'" % (found, param.bound, param.name),
                    node.line, node.col)
        effective = []
        for spec in specs:
            filled = dict(spec)
            filled["type"] = self._substitute(spec["type"], bindings, type_vars)
            effective.append(filled)
        self._check_call_args(name, effective, arg_types, kwarg_types, node)
        return self._substitute(binding.return_type, bindings, type_vars) \
            or types.ANY

    def _unify(self, declared, actual, type_vars, bindings):
        """Match a declared type with the type of an argument.

        A type parameter that is not known yet takes the type of the
        argument.  A type with type arguments is matched argument by
        argument, so the type of a list gives the type of its elements.
        """
        if declared is None:
            return
        if declared in type_vars:
            if declared not in bindings:
                bindings[declared] = actual
            return
        args = types.type_args(declared)
        if not args:
            return
        actual_args = types.type_args(actual)
        for index, arg in enumerate(args):
            if index >= len(actual_args):
                break
            self._unify(arg, actual_args[index], type_vars, bindings)

    def _substitute(self, name, bindings, type_vars):
        """Put the type arguments in place of the type parameters."""
        if name is None:
            return None
        if name in type_vars:
            return bindings.get(name, types.ANY)
        args = types.type_args(name)
        if not args:
            return name
        filled = [self._substitute(arg, bindings, type_vars) for arg in args]
        return types.base_type(name) + "<" + ", ".join(filled) + ">"

    def _element_type(self, name):
        """The type of the elements of a container.

        The type of a `list<int>` gives `int`, and the type of a
        `list` gives nothing: the type of the elements is not known.
        """
        if not name:
            return None
        base = types.base_type(name)
        args = types.type_args(name)
        if base in (types.LIST, types.SET) and args:
            return args[0]
        if base == types.DICT and len(args) > 1:
            return args[1]
        return None

    def _infer_type(self, node, scope):
        """The type of an expression, with the type of a literal worked out.

        A list of integers is a `list<int>` and not a `list`: the type
        arguments of a generic function are found with it.
        """
        if isinstance(node, ast.ListLiteral):
            if not node.elements:
                return types.LIST
            element = None
            for item in node.elements:
                item_type = self._infer_type(item, scope)
                if element is None:
                    element = item_type
                elif element != item_type:
                    element = types.ANY
            return types.LIST + "<" + element + ">"
        return self._expr(node, scope)

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
        self._check_assignable(
            arg_type, ptype, node,
            "argument of type '%s' is not assignable to parameter of type '%s' "
            "in call to '%s'", name)

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

    def _constructor_call(self, name, arg_types, node):
        struct = self.structs.get(name)
        if struct is None:
            return name
        required = [field for field in struct.fields if field.default is None]
        if len(arg_types) < len(required) or len(arg_types) > len(struct.fields):
            raise BunTypeError(
                "struct '%s' expects %d argument(s), got %d"
                % (name, len(required), len(arg_types)), node.line, node.col)
        for arg_type, field in zip(arg_types, struct.fields):
            if field.type_ann is None:
                continue
            if not types.is_assignable(arg_type, field.type_ann):
                raise BunTypeError(
                    "argument of type '%s' is not assignable to field '%s' of type '%s'"
                    % (arg_type, field.name, field.type_ann),
                    node.line, node.col)
        return name

    def _method_call(self, node, scope):
        recv_type = self._expr(node.receiver, scope)
        arg_types = [self._expr(arg, scope) for arg in node.args]
        if recv_type in (types.ANY, types.STRUCT):
            return types.ANY
        if recv_type in self.protocols:
            return self._protocol_method_call(node, recv_type, arg_types)
        methods = self.impls.get(recv_type)
        if methods is None:
            if recv_type in self.structs:
                raise BunTypeError(
                    "unknown method '%s' on %s" % (node.method, recv_type),
                    node.line, node.col)
            return types.ANY
        if node.method not in methods:
            if recv_type in self.structs:
                raise BunTypeError(
                    "unknown method '%s' on %s" % (node.method, recv_type),
                    node.line, node.col)
            return types.ANY
        method = methods[node.method]
        if getattr(method, "mutating", False):
            if (isinstance(node.receiver, ast.Identifier)
                    and node.receiver.name != "self"):
                binding = scope.get(node.receiver.name)
                if binding is not None and not binding.mutable:
                    raise BunTypeError(
                        "cannot call mutating method '%s' on immutable variable '%s'"
                        % (node.method, node.receiver.name),
                        node.line, node.col)
        params = [p for p in method.params if p.name != "self"]
        if len(arg_types) != len(params):
            raise BunTypeError(
                "method '%s' expects %d argument(s), got %d"
                % (node.method, len(params), len(arg_types)),
                node.line, node.col)
        for arg_type, param in zip(arg_types, params):
            if param.type_name is None:
                continue
            self._check_assignable(
                arg_type, param.type_name, node,
                "argument of type '%s' is not assignable to parameter of type "
                "'%s' in call to '%s'", node.method)
        return method.return_type or types.ANY

    def _protocol_method_call(self, node, protocol_name, arg_types):
        """Check the call of a method of a protocol.

        The signature of the protocol is the contract of the call: the
        arity and the types of the arguments are the ones it gives.
        """
        protocol = self.protocols[protocol_name]
        signature = protocol.get(node.method)
        if signature is None:
            raise BunTypeError(
                "unknown method '%s' on %s" % (node.method, protocol_name),
                node.line, node.col)
        params = [p for p in signature.params if p.name != "self"]
        if len(arg_types) != len(params):
            raise BunTypeError(
                "method '%s' expects %d argument(s), got %d"
                % (node.method, len(params), len(arg_types)),
                node.line, node.col)
        for arg_type, param in zip(arg_types, params):
            if param.type_name is None:
                continue
            self._check_assignable(
                arg_type, param.type_name, node,
                "argument of type '%s' is not assignable to parameter of type "
                "'%s' in call to '%s'", node.method)
        return signature.return_type or types.ANY
