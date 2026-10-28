from . import ast
from . import ops
from . import patterns
from . import records
from .errors import BunError, BunTypeError


OP_LOAD_CONST = "LOAD_CONST"
OP_BUILD_LIST = "BUILD_LIST"
OP_BUILD_DICT = "BUILD_DICT"
OP_LOAD_NAME = "LOAD_NAME"
OP_DEFINE_NAME = "DEFINE_NAME"
OP_STORE_NAME = "STORE_NAME"
OP_POP = "POP"
OP_DUP = "DUP"
OP_MAKE_FUNCTION = "MAKE_FUNCTION"
OP_CALL = "CALL"
OP_RETURN = "RETURN"
OP_HALT = "HALT"
OP_ENTER_SCOPE = "ENTER_SCOPE"
OP_EXIT_SCOPE = "EXIT_SCOPE"
OP_BINARY = "BINARY"
OP_UNARY = "UNARY"
OP_JUMP = "JUMP"
OP_JUMP_IF_FALSE = "JUMP_IF_FALSE"
OP_JUMP_IF_TRUE = "JUMP_IF_TRUE"
OP_FOR_SETUP = "FOR_SETUP"
OP_FOR_NEXT = "FOR_NEXT"
OP_FOR_POP = "FOR_POP"
OP_INDEX = "INDEX"
OP_STORE_INDEX = "STORE_INDEX"
OP_METHOD_CALL = "METHOD_CALL"
OP_IMPORT = "IMPORT"
OP_RECORD_EXPORT = "RECORD_EXPORT"
OP_TRY = "TRY"
OP_TRY_FINALLY = "TRY_FINALLY"
OP_END_TRY = "END_TRY"
OP_FINALLY_END = "FINALLY_END"
OP_THROW = "THROW"
OP_ASSERT = "ASSERT"
OP_DEL = "DEL"
OP_YIELD = "YIELD"
OP_DEL_INDEX = "DEL_INDEX"
OP_FORMAT = "FORMAT"
OP_BUILD_STRING = "BUILD_STRING"
OP_SLICE = "SLICE"
OP_STORE_SLICE = "STORE_SLICE"
OP_UNPACK_PLAN = "UNPACK_PLAN"
OP_LIST_APPEND = "LIST_APPEND"
OP_DICT_SET = "DICT_SET"
OP_WITH_ENTER = "WITH_ENTER"
OP_WITH_POP_TARGET = "WITH_POP_TARGET"
OP_PROTOCOL_GET = "PROTOCOL_GET"
OP_PENDING_ERROR = "PENDING_ERROR"
OP_CLEAR_ERROR = "CLEAR_ERROR"
OP_WITH_DEPTH = "WITH_DEPTH"
OP_HAS_ERROR = "HAS_ERROR"
OP_SCOPE_ENTER = "SCOPE_ENTER"
OP_SCOPE_EXIT = "SCOPE_EXIT"
OP_MATCH_TEST = "MATCH_TEST"
OP_MATCH_FAIL = "MATCH_FAIL"
OP_MAKE_STRUCT = "MAKE_STRUCT"
OP_GET_FIELD = "GET_FIELD"
OP_SET_FIELD = "SET_FIELD"
OP_REGISTER_IMPL = "REGISTER_IMPL"
OP_UNWRAP_OR_RETURN = "UNWRAP_OR_RETURN"

MATCH_SUBJECT = "__match_subject"


class CompileError(BunTypeError):
    pass


def make_code(name, params, code, filename, source):
    return {
        "name": name,
        "params": list(params),
        "code": code,
        "filename": filename,
        "source": source,
        "param_defs": [],
        "type_params": [],
    }


def has_yield(node):
    """Does the body of a function give values?

    A `yield` of a function that is written inside it belongs to that
    function, and not to the one that holds it.
    """
    if isinstance(node, (ast.YieldStmt, ast.YieldExpr)):
        return True
    if isinstance(node, ast.FnDecl):
        # A function that is written inside the function is its own.
        return False
    if isinstance(node, (list, tuple)):
        return any(has_yield(item) for item in node)
    if records.is_record(node):
        for name in records.fields(type(node)):
            if has_yield(getattr(node, name)):
                return True
    return False


def emit(code, op, arg, node):
    code.append((op, arg, getattr(node, "line", 0), getattr(node, "col", 0)))
    return len(code) - 1


def patch(code, index):
    op, arg, line, col = code[index]
    code[index] = (op, len(code), line, col)


def patch_to(code, index, target):
    op, arg, line, col = code[index]
    code[index] = (op, target, line, col)


class Compiler:
    def __init__(self, filename="<stdin>", source=""):
        self.filename = filename
        self.source = source
        self._scope_depth = 0
        self._try_contexts = []
        self._for_depth = 0
        self._loops = []
        self.structs = {}
        self.enums = {}

    def compile_program(self, program):
        code = []
        self._collect_structs(program.statements)
        for statement in program.statements:
            self.compile_statement(statement, code)
        code.append((OP_HALT, None, 0, 0))
        return make_code("<module>", [], code, self.filename, self.source)

    def _collect_structs(self, statements):
        """Collect the struct declarations of the program.

        The declarations are collected before the code is written, so a
        constructor may be called before the declaration that names it.
        """
        for statement in statements:
            if isinstance(statement, ast.StructDecl):
                self.structs[statement.name] = statement
            elif isinstance(statement, ast.EnumDecl):
                self.enums[statement.name] = statement

    def compile_function(self, node):
        code = []
        saved = (self._scope_depth, self._try_contexts, self._loops)
        self._scope_depth = 0
        self._try_contexts = []
        self._for_depth = 0
        self._loops = []
        emit(code, OP_ENTER_SCOPE, None, node)
        self._scope_depth += 1
        body = node.body
        if isinstance(body, ast.Block):
            for statement in body.statements:
                self.compile_statement(statement, code)
        else:
            self.compile_statement(body, code)
        emit(code, OP_EXIT_SCOPE, None, node)
        self._scope_depth -= 1
        emit(code, OP_LOAD_CONST, None, node)
        emit(code, OP_RETURN, None, node)
        self._scope_depth, self._try_contexts, self._loops = saved
        result = make_code(node.name or "anonymous",
                           [param.name for param in node.params], code,
                           self.filename, self.source)
        result["param_defs"] = [self._param_def(param) for param in node.params]
        result["type_params"] = [{"name": param.name, "bound": param.bound}
                                 for param in node.type_params]
        if has_yield(node.body):
            # A function that gives values is a generator, and the
            # runtime knows it before the program runs.
            result["is_generator"] = True
        return result

    def _param_def(self, param):
        return {
            "name": param.name,
            "param_kind": param.param_kind,
            "type_name": param.type_name,
            "default": (None if param.default is None
                        else self.compile_expression(param.default)),
        }

    def compile_statement(self, node, code):
        if isinstance(node, ast.LetStmt):
            self.compile_expr(node.value, code)
            emit(code, OP_DEFINE_NAME, (node.name, node.mutable), node)
            if node.exported:
                emit(code, OP_RECORD_EXPORT, node.name, node)
        elif isinstance(node, ast.AssignStmt):
            if isinstance(node.target, ast.Identifier):
                self.compile_expr(node.value, code)
                emit(code, OP_STORE_NAME, node.target.name, node)
            elif isinstance(node.target, ast.UnpackTarget):
                self.compile_expr(node.value, code)
                emit(code, OP_UNPACK_PLAN,
                     ops.build_unpack_plan(node.target.targets), node)
                for leaf in ops.plan_leaves(node.target.targets):
                    self._compile_unpack_store(leaf, code, node)
            elif isinstance(node.target, ast.Index):
                self.compile_expr(node.value, code)
                self.compile_expr(node.target.target, code)
                if isinstance(node.target.index, ast.Slice):
                    for part in (node.target.index.start,
                                 node.target.index.stop,
                                 node.target.index.step):
                        if part is None:
                            emit(code, OP_LOAD_CONST, None, node)
                        else:
                            self.compile_expr(part, code)
                    emit(code, OP_STORE_SLICE, None, node)
                else:
                    self.compile_expr(node.target.index, code)
                    emit(code, OP_STORE_INDEX, None, node)
            elif isinstance(node.target, ast.Attribute):
                self.compile_expr(node.target.object, code)
                self.compile_expr(node.value, code)
                emit(code, OP_SET_FIELD, node.target.name, node)
            else:
                raise CompileError("invalid assignment target")
        elif isinstance(node, ast.ExprStmt):
            self.compile_expr(node.expr, code)
            emit(code, OP_POP, None, node)
        elif isinstance(node, ast.UnpackStmt):
            self.compile_expr(node.value, code)
            emit(code, OP_UNPACK_PLAN, ops.build_unpack_plan(node.targets),
                 node)
            for leaf in ops.plan_leaves(node.targets):
                self._compile_unpack_store(leaf, code, node, node.mutable)
        elif isinstance(node, ast.Block):
            emit(code, OP_ENTER_SCOPE, None, node)
            for statement in node.statements:
                self.compile_statement(statement, code)
            emit(code, OP_EXIT_SCOPE, None, node)
        elif isinstance(node, ast.IfStmt):
            self.compile_expr(node.condition, code)
            else_jump = emit(code, OP_JUMP_IF_FALSE, None, node)
            self.compile_branch(node.then_branch, code)
            end_jump = emit(code, OP_JUMP, None, node)
            patch(code, else_jump)
            if node.else_branch is not None:
                self.compile_branch(node.else_branch, code)
            patch(code, end_jump)
        elif isinstance(node, ast.WhileStmt):
            head = len(code)
            self.compile_expr(node.condition, code)
            exit_jump = emit(code, OP_JUMP_IF_FALSE, None, node)
            context = self._enter_loop(node, code)
            self.compile_branch(node.body, code)
            self._leave_loop(context)
            cont_target = emit(code, OP_JUMP, head, node)
            patch(code, exit_jump)
            if node.orelse is not None:
                # The else of a loop runs when the loop ends without a
                # break, so a break has to jump over it.
                self.compile_branch(node.orelse, code)
            self._close_loop(context, cont_target, len(code))
        elif isinstance(node, ast.ForStmt):
            self.compile_expr(node.iterable, code)
            emit(code, OP_FOR_SETUP, None, node)
            head = len(code)
            exit_jump = emit(code, OP_FOR_NEXT, None, node)
            context = self._enter_loop(node, code)
            self._for_depth += 1
            emit(code, OP_ENTER_SCOPE, None, node)
            self._scope_depth += 1
            if len(node.targets) == 1:
                emit(code, OP_DEFINE_NAME, (node.targets[0], True), node)
            else:
                plan = ["seq"] + [["leaf"]] * len(node.targets)
                emit(code, OP_UNPACK_PLAN, plan, node)
                for name in node.targets:
                    emit(code, OP_DEFINE_NAME, (name, True), node)
            self.compile_branch(node.body, code)
            emit(code, OP_EXIT_SCOPE, None, node)
            self._scope_depth -= 1
            self._leave_loop(context)
            self._for_depth -= 1
            emit(code, OP_JUMP, head, node)
            patch(code, exit_jump)
            if node.orelse is not None:
                # The else of a loop runs when the loop ends without a
                # break, so a break has to jump over it.
                self.compile_branch(node.orelse, code)
            self._close_loop(context, head, len(code))
        elif isinstance(node, ast.TryStmt):
            self._compile_try(node, code)
        elif isinstance(node, ast.WithStmt):
            self._compile_with(node, code)
        elif isinstance(node, ast.ScopeStmt):
            self._compile_scope(node, code)
        elif isinstance(node, ast.ThrowStmt):
            if node.cause is not None:
                self.compile_expr(node.value, code)
                self.compile_expr(node.cause, code)
                emit(code, OP_THROW, True, node)
            else:
                self.compile_expr(node.value, code)
                emit(code, OP_THROW, False, node)
        elif isinstance(node, ast.AssertStmt):
            self.compile_expr(node.condition, code)
            ok_jump = emit(code, OP_JUMP_IF_TRUE, None, node)
            if node.message is not None:
                self.compile_expr(node.message, code)
                emit(code, OP_ASSERT, True, node)
            else:
                emit(code, OP_ASSERT, False, node)
            patch(code, ok_jump)
        elif isinstance(node, ast.DelStmt):
            self._compile_del(node, code)
        elif isinstance(node, ast.YieldStmt):
            if node.value is not None:
                self.compile_expr(node.value, code)
            else:
                emit(code, OP_LOAD_CONST, None, node)
            emit(code, OP_YIELD, None, node)
            # The answer of the program is of no use here.
            emit(code, OP_POP, None, node)
        elif isinstance(node, ast.BreakStmt):
            self._compile_loop_jump(node, code, "break")
        elif isinstance(node, ast.ContinueStmt):
            self._compile_loop_jump(node, code, "continue")
        elif isinstance(node, ast.MatchStmt):
            self._compile_match(node, code)
        elif isinstance(node, ast.FnDecl):
            emit(code, OP_MAKE_FUNCTION, self.compile_function(node), node)
            if node.decorators:
                self._compile_decorators(node, code)
            else:
                emit(code, OP_DEFINE_NAME, (node.name, False), node)
            if node.exported:
                emit(code, OP_RECORD_EXPORT, node.name, node)
        elif isinstance(node, ast.StructDecl):
            self.structs[node.name] = node
        elif isinstance(node, ast.EnumDecl):
            # An enum is a type, and a type is not a value: the program
            # that declares it writes nothing, the way a protocol does.
            self.enums[node.name] = node
        elif isinstance(node, ast.ProtocolDecl):
            # A protocol is a type, and a type is not a value: the program
            # that declares it runs the same with it and without it.
            pass
        elif isinstance(node, ast.ImplDecl):
            for method in node.methods:
                emit(code, OP_REGISTER_IMPL,
                     (node.type_name, method.name,
                      self.compile_function(method)), node)
        elif isinstance(node, ast.ImportStmt):
            emit(code, OP_IMPORT, (node.path, list(node.names)), node)
        elif isinstance(node, ast.ReturnStmt):
            if node.value is not None:
                self.compile_expr(node.value, code)
            else:
                emit(code, OP_LOAD_CONST, None, node)
            self._unwind_try_handlers(code, node, self._try_contexts)
            emit(code, OP_RETURN, None, node)
        else:
            raise CompileError(
                "unknown statement: %s" % type(node).__name__)

    def _compile_del(self, node, code):
        """Compile `del name` and `del container[key]`."""
        target = node.target
        if isinstance(target, ast.Identifier):
            emit(code, OP_DEL, target.name, node)
            return
        if isinstance(target, ast.Index) and not isinstance(target.index,
                                                              ast.Slice):
            self.compile_expr(target.target, code)
            self.compile_expr(target.index, code)
            emit(code, OP_DEL_INDEX, None, node)
            return
        raise CompileError("cannot delete this expression")

    def _compile_decorators(self, node, code):
        """Compile the decorators of a function.

        The decorators are applied from the closest one to the function
        outwards, so the decorator that is written last is the one that
        is called first. Each of them receives the function and returns
        the value that the name of the function holds afterwards.

        The name is bound before the decorators run, so that a decorator
        can call the function it decorates, and it is frozen again when
        the decorators are done.
        """
        emit(code, OP_DEFINE_NAME, (node.name, True), node)
        for decorator in reversed(node.decorators):
            self.compile_expr(decorator, code)
            emit(code, OP_LOAD_NAME, node.name, node)
            emit(code, OP_CALL, (1, False), node)
            emit(code, OP_STORE_NAME, node.name, node)
        emit(code, OP_LOAD_NAME, node.name, node)
        emit(code, OP_DEFINE_NAME, (node.name, False), node)

    def _compile_match(self, node, code):
        """Compile a ``match`` statement.

        The subject is evaluated once and kept in a hidden name, because
        a case may be tried more than once and the subject may be an
        expression with a cost.  Every case has its own scope, so the
        names a pattern binds do not leak into the next case.
        """
        emit(code, OP_ENTER_SCOPE, None, node)
        self._scope_depth += 1
        self.compile_expr(node.subject, code)
        emit(code, OP_DEFINE_NAME, (MATCH_SUBJECT, False), node)
        end_jumps = []
        for pattern, body in node.cases:
            emit(code, OP_ENTER_SCOPE, None, node)
            self._scope_depth += 1
            emit(code, OP_LOAD_NAME, MATCH_SUBJECT, node)
            emit(code, OP_MATCH_TEST, patterns.plan_from_ast(pattern), node)
            body_jump = emit(code, OP_JUMP_IF_TRUE, None, node)
            emit(code, OP_EXIT_SCOPE, None, node)
            self._scope_depth -= 1
            next_jump = emit(code, OP_JUMP, None, node)
            patch(code, body_jump)
            guard = getattr(pattern, "guard", None)
            guard_jump = None
            if guard is not None:
                # A guard that does not hold sends the case on to the
                # next one, the same way a pattern that does not match.
                self.compile_expr(guard, code)
                guard_jump = emit(code, OP_JUMP_IF_TRUE, None, node)
                emit(code, OP_EXIT_SCOPE, None, node)
                self._scope_depth -= 1
                guard_next_jump = emit(code, OP_JUMP, None, node)
                patch(code, guard_jump)
            self.compile_branch(body, code)
            emit(code, OP_EXIT_SCOPE, None, node)
            self._scope_depth -= 1
            end_jumps.append(emit(code, OP_JUMP, None, node))
            patch(code, next_jump)
            if guard is not None:
                patch(code, guard_next_jump)
        emit(code, OP_LOAD_NAME, MATCH_SUBJECT, node)
        emit(code, OP_MATCH_FAIL, None, node)
        end = len(code)
        for index in end_jumps:
            patch_to(code, index, end)
        emit(code, OP_EXIT_SCOPE, None, node)
        self._scope_depth -= 1

    def compile_branch(self, node, code):
        if isinstance(node, ast.Block):
            emit(code, OP_ENTER_SCOPE, None, node)
            self._scope_depth += 1
            for statement in node.statements:
                self.compile_statement(statement, code)
            emit(code, OP_EXIT_SCOPE, None, node)
            self._scope_depth -= 1
        else:
            self.compile_statement(node, code)

    def _enter_loop(self, node, code):
        context = {
            "code": code,
            "scope_depth": self._scope_depth,
            "try_depth": len(self._try_contexts),
            "for_depth": self._for_depth,
            "break_patches": [],
            "continue_patches": [],
        }
        self._loops.append(context)
        return context

    def _leave_loop(self, context):
        self._loops.pop()

    def _close_loop(self, context, continue_target, break_target):
        for index in context["continue_patches"]:
            patch_to(context["code"], index, continue_target)
        for index in context["break_patches"]:
            patch_to(context["code"], index, break_target)

    def _compile_try(self, node, code):
        has_catch = node.catch_block is not None
        has_finally = node.finally_body is not None
        finally_jump = None
        if has_finally:
            finally_jump = emit(code, OP_TRY_FINALLY, None, node)
        catch_jump = None
        if has_catch:
            catch_jump = emit(code, OP_TRY, None, node)
        context = {
            "kind": "try",
            "depth": len(self._try_contexts),
            "scope_depth": self._scope_depth,
            "has_catch": has_catch,
            "has_finally": has_finally,
            "finally_body": node.finally_body,
        }
        self._try_contexts.append(context)
        emit(code, OP_ENTER_SCOPE, None, node)
        self._scope_depth += 1
        for statement in node.try_block.statements:
            self.compile_statement(statement, code)
        emit(code, OP_EXIT_SCOPE, None, node)
        self._scope_depth -= 1
        if has_catch:
            emit(code, OP_END_TRY, None, node)
        if has_finally:
            emit(code, OP_END_TRY, None, node)
        end_jump = emit(code, OP_JUMP, None, node)
        # The catch block runs after the handler of the catch is gone, so a
        # return inside it must not take that handler away a second time.
        catch_context = dict(context)
        catch_context["has_catch"] = False
        self._try_contexts[-1] = catch_context
        if has_catch:
            patch(code, catch_jump)
            emit(code, OP_ENTER_SCOPE, None, node)
            self._scope_depth += 1
            for name in node.catch_params:
                emit(code, OP_DUP, None, node)
                emit(code, OP_DEFINE_NAME, (name, True), node)
            emit(code, OP_POP, None, node)
            for statement in node.catch_block.statements:
                self.compile_statement(statement, code)
            emit(code, OP_EXIT_SCOPE, None, node)
            self._scope_depth -= 1
            if has_finally:
                emit(code, OP_END_TRY, None, node)
        self._try_contexts[-1] = context
        if has_finally:
            patch(code, finally_jump)
            finally_start = len(code)
            self._compile_finally_body(context, code, node)
            emit(code, OP_FINALLY_END, None, node)
            patch_to(code, end_jump, finally_start)
        else:
            patch(code, end_jump)
        self._try_contexts.pop()

    def _compile_with(self, node, code):
        context = {
            "kind": "with",
            "depth": len(self._try_contexts),
            "scope_depth": self._scope_depth,
        }
        handler = emit(code, OP_TRY_FINALLY, None, node)
        self._try_contexts.append(context)
        for item in node.items:
            self.compile_expr(item.expr, code)
            emit(code, OP_DUP, None, node)
            emit(code, OP_LOAD_CONST, "__enter__", node)
            emit(code, OP_PROTOCOL_GET, "__enter__", node)
            emit(code, OP_CALL, (0, False), node)
            emit(code, OP_WITH_ENTER, item.name, node)
        emit(code, OP_ENTER_SCOPE, None, node)
        self._scope_depth += 1
        for statement in node.body.statements:
            self.compile_statement(statement, code)
        emit(code, OP_EXIT_SCOPE, None, node)
        self._scope_depth -= 1
        emit(code, OP_END_TRY, None, node)
        exit_start = len(code)
        self._compile_with_exit(code, node)
        end_jump = emit(code, OP_JUMP, None, node)
        patch_to(code, handler, len(code))
        handler_jump = emit(code, OP_JUMP, None, node)
        patch_to(code, handler_jump, exit_start)
        patch(code, end_jump)
        self._try_contexts.pop()

    def _compile_scope(self, node, code):
        """Compile a ``scope`` statement.

        The body runs inside a task group.  When the body leaves the scope
        the group joins every child it spawned; the first error of a child
        is raised in the parent.  The group is closed on the error path as
        well, so a failing body never leaves tasks running behind it.
        """
        context = {
            "kind": "scope",
            "depth": len(self._try_contexts),
            "scope_depth": self._scope_depth,
        }
        emit(code, OP_SCOPE_ENTER, None, node)
        handler = emit(code, OP_TRY_FINALLY, None, node)
        self._try_contexts.append(context)
        emit(code, OP_ENTER_SCOPE, None, node)
        self._scope_depth += 1
        for statement in node.body.statements:
            self.compile_statement(statement, code)
        emit(code, OP_EXIT_SCOPE, None, node)
        self._scope_depth -= 1
        emit(code, OP_END_TRY, None, node)
        emit(code, OP_SCOPE_EXIT, None, node)
        end_jump = emit(code, OP_JUMP, None, node)
        patch_to(code, handler, len(code))
        emit(code, OP_SCOPE_EXIT, None, node)
        emit(code, OP_FINALLY_END, None, node)
        patch(code, end_jump)
        self._try_contexts.pop()

    def _compile_with_exit(self, code, node):
        """Emit the ``__exit__`` calls for every manager that was entered.

        The managers are exited in reverse order of entry.  The sequence is
        shared by the normal path and the error path: ``PENDING_ERROR``
        yields ``null`` when no error is in flight, so the same code works
        for both.  An error raised by a manager is re-raised unless a
        manager suppressed it.
        """
        loop = len(code)
        emit(code, OP_WITH_DEPTH, None, node)
        emit(code, OP_LOAD_CONST, 0, node)
        emit(code, OP_BINARY, ">", node)
        done = emit(code, OP_JUMP_IF_FALSE, None, node)
        emit(code, OP_WITH_POP_TARGET, None, node)
        emit(code, OP_DUP, None, node)
        emit(code, OP_LOAD_CONST, "__exit__", node)
        emit(code, OP_PROTOCOL_GET, "__exit__", node)
        emit(code, OP_PENDING_ERROR, None, node)
        emit(code, OP_CALL, (1, False), node)
        suppress = emit(code, OP_JUMP_IF_TRUE, None, node)
        next_item = emit(code, OP_JUMP, None, node)
        patch(code, suppress)
        emit(code, OP_CLEAR_ERROR, None, node)
        patch_to(code, next_item, len(code))
        emit(code, OP_POP, None, node)
        back = emit(code, OP_JUMP, None, node)
        patch_to(code, back, loop)
        patch_to(code, done, len(code))
        emit(code, OP_HAS_ERROR, None, node)
        rethrow = emit(code, OP_JUMP_IF_TRUE, None, node)
        end = emit(code, OP_JUMP, None, node)
        patch(code, rethrow)
        emit(code, OP_FINALLY_END, None, node)
        patch_to(code, end, len(code))

    def _compile_finally_body(self, context, code, node):
        """Emit a finally block.

        The block is compiled as if it ran outside of its own ``try`` so a
        ``break``/``continue``/``return`` inside it targets the enclosing
        loop or function, not the try statement it belongs to.
        """
        emit(code, OP_ENTER_SCOPE, None, node)
        self._scope_depth += 1
        saved = self._try_contexts
        self._try_contexts = saved[:context["depth"]]
        try:
            for statement in context["finally_body"].statements:
                self.compile_statement(statement, code)
        finally:
            self._try_contexts = saved
        emit(code, OP_EXIT_SCOPE, None, node)
        self._scope_depth -= 1

    def _unwind_try_handlers(self, code, node, contexts):
        """Leave the given try statements, running their finally blocks.

        The scopes of the try body are left before the finally block runs so
        the block sees the same variables it would see on the normal path.
        Returns the scope depth that is left after the unwinding.
        """
        depth = self._scope_depth
        for context in reversed(contexts):
            target = context["scope_depth"] + 1
            while depth > target:
                emit(code, OP_EXIT_SCOPE, None, node)
                depth -= 1
            if context["kind"] == "with":
                emit(code, OP_END_TRY, None, node)
                self._compile_with_exit(code, node)
                continue
            if context["kind"] == "scope":
                # Leaving the scope early still closes the task group, so
                # the children of the scope are joined before the function
                # returns.
                emit(code, OP_END_TRY, None, node)
                emit(code, OP_SCOPE_EXIT, None, node)
                continue
            if context["has_catch"]:
                emit(code, OP_END_TRY, None, node)
            if context["has_finally"]:
                emit(code, OP_END_TRY, None, node)
                self._compile_finally_body(context, code, node)
        return depth

    def _compile_loop_jump(self, node, code, kind):
        if not self._loops:
            raise CompileError(
                "'%s' outside of a loop" % kind, node.line, node.col)
        context = self._loops[-1]
        depth = self._unwind_try_handlers(
            code, node, self._try_contexts[context["try_depth"]:])
        for _ in range(depth - context["scope_depth"]):
            emit(code, OP_EXIT_SCOPE, None, node)
        if kind == "break":
            for _ in range(self._for_depth - context["for_depth"]):
                emit(code, OP_FOR_POP, None, node)
        index = emit(code, OP_JUMP, None, node)
        context["%s_patches" % kind].append(index)


    def compile_expr(self, node, code):
        if isinstance(node, ast.Literal):
            emit(code, OP_LOAD_CONST, node.value, node)
        elif isinstance(node, ast.Identifier):
            emit(code, OP_LOAD_NAME, node.name, node)
        elif isinstance(node, ast.ListLiteral):
            for element in node.elements:
                self.compile_expr(element, code)
            emit(code, OP_BUILD_LIST, len(node.elements), node)
        elif isinstance(node, ast.Comprehension):
            self._compile_comprehension(node, code)
        elif isinstance(node, ast.Unary):
            self.compile_expr(node.operand, code)
            emit(code, OP_UNARY, node.op, node)
        elif isinstance(node, ast.Binary):
            self.compile_expr(node.left, code)
            self.compile_expr(node.right, code)
            emit(code, OP_BINARY, node.op, node)
        elif isinstance(node, ast.Logical):
            self.compile_expr(node.left, code)
            emit(code, OP_DUP, None, node)
            if node.op == "and":
                jump = emit(code, OP_JUMP_IF_FALSE, None, node)
            else:
                jump = emit(code, OP_JUMP_IF_TRUE, None, node)
            emit(code, OP_POP, None, node)
            self.compile_expr(node.right, code)
            patch(code, jump)
        elif isinstance(node, ast.YieldExpr):
            # The value of a `yield` expression is the value that the
            # program sends back into the generator.
            if node.value is not None:
                self.compile_expr(node.value, code)
            else:
                emit(code, OP_LOAD_CONST, None, node)
            emit(code, OP_YIELD, None, node)
        elif isinstance(node, ast.Index):
            self.compile_expr(node.target, code)
            if isinstance(node.index, ast.Slice):
                for part in (node.index.start, node.index.stop,
                             node.index.step):
                    if part is None:
                        emit(code, OP_LOAD_CONST, None, node)
                    else:
                        self.compile_expr(part, code)
                emit(code, OP_SLICE, None, node)
            else:
                self.compile_expr(node.index, code)
                emit(code, OP_INDEX, None, node)
        elif isinstance(node, ast.MethodCall):
            variant = self._enum_method_variant(node)
            if variant is not None:
                self._compile_enum_value(variant[0], variant[1], node.args,
                                        code, node)
                return
            self.compile_expr(node.receiver, code)
            for arg_node in node.args:
                self.compile_expr(arg_node, code)
            emit(code, OP_METHOD_CALL, (node.method, len(node.args)), node)
        elif isinstance(node, ast.DictLiteral):
            for key_node, value_node in node.entries:
                self.compile_expr(key_node, code)
                self.compile_expr(value_node, code)
            emit(code, OP_BUILD_DICT, len(node.entries), node)
        elif isinstance(node, ast.FString):
            for part in node.parts:
                if part.literal is not None:
                    emit(code, OP_LOAD_CONST, part.literal, node)
                else:
                    self.compile_expr(part.expr, code)
                    emit(code, OP_FORMAT,
                         (part.spec, part.conv, part.source_text), node)
            emit(code, OP_BUILD_STRING, len(node.parts), node)
        elif isinstance(node, ast.Call):
            if isinstance(node.callee, ast.Attribute):
                variant = self._enum_variant(node.callee)
                if variant is not None:
                    self._compile_enum_value(variant[0], variant[1],
                                           node.args, code, node)
                    return
            declaration = None
            if isinstance(node.callee, ast.Identifier):
                declaration = self.structs.get(node.callee.name)
            if declaration is not None:
                self._compile_constructor(declaration, node, code)
                return
            self.compile_expr(node.callee, code)
            for arg_node in node.args:
                self.compile_expr(arg_node, code)
            if node.kwargs:
                emit(code, OP_BUILD_DICT, 0, node)
                for name, value_node in node.kwargs:
                    emit(code, OP_LOAD_CONST, name, node)
                    self.compile_expr(value_node, code)
                    emit(code, OP_DICT_SET, None, node)
            emit(code, OP_CALL, (len(node.args), bool(node.kwargs)), node)
        elif isinstance(node, ast.Attribute):
            variant = self._enum_variant(node)
            if variant is not None:
                self._compile_enum_value(variant[0], variant[1], [], code,
                                        node)
                return
            self.compile_expr(node.object, code)
            emit(code, OP_GET_FIELD, node.name, node)
        elif isinstance(node, ast.Unwrap):
            self.compile_expr(node.expr, code)
            emit(code, OP_UNWRAP_OR_RETURN, None, node)
        elif isinstance(node, ast.FnDecl):
            emit(code, OP_MAKE_FUNCTION, self.compile_function(node), node)
        else:
            raise CompileError(
                "unknown expression: %s" % type(node).__name__)

    def _compile_constructor(self, declaration, node, code):
        """Compile a call of a struct name."""
        fields = declaration.fields
        if len(node.args) > len(fields):
            raise CompileError(
                "struct '%s' expects %d argument(s), got %d"
                % (declaration.name, len(fields), len(node.args)))
        for arg_node in node.args:
            self.compile_expr(arg_node, code)
        for field in fields[len(node.args):]:
            if field.default is None:
                raise CompileError(
                    "struct '%s' is missing a value for field '%s'"
                    % (declaration.name, field.name))
            self.compile_expr(field.default, code)
        emit(code, OP_MAKE_STRUCT,
             (declaration.name, [field.name for field in fields]), node)

    def _enum_variant(self, node):
        """The variant an attribute expression names, if it names one."""
        if not isinstance(node, ast.Attribute):
            return None
        if not isinstance(node.object, ast.Identifier):
            return None
        declaration = self.enums.get(node.object.name)
        if declaration is None:
            return None
        return (node.object.name, node.name, declaration)

    def _enum_method_variant(self, node):
        """The variant a method call names, if it names one.

        The fields of a variant are written like the arguments of a
        method, so the call of a variant is a method call on the name
        of its enum.
        """
        if not isinstance(node, ast.MethodCall):
            return None
        if not isinstance(node.receiver, ast.Identifier):
            return None
        if node.receiver.name not in self.enums:
            return None
        return (node.receiver.name, node.method, self.enums[node.receiver.name])

    def _compile_enum_value(self, enum_name, variant_name, arg_nodes, code,
                            node):
        """Compile the construction of the value of a variant.

        The value of a variant is a dict with three entries - the name
        of the enum, the name of the variant, and the list of the fields
        - so the construction is written with the two opcodes a dict
        literal is written with, and no opcode of its own.
        """
        variant = None
        for item in self.enums[enum_name].variants:
            if item.name == variant_name:
                variant = item
                break
        if variant is None:
            raise CompileError(
                "enum '%s' has no variant '%s'" % (enum_name, variant_name))
        if len(arg_nodes) != len(variant.field_types):
            raise CompileError(
                "variant '%s.%s' expects %d argument(s), got %d"
                % (enum_name, variant_name, len(variant.field_types),
                   len(arg_nodes)))
        emit(code, OP_LOAD_CONST, "type", node)
        emit(code, OP_LOAD_CONST, enum_name, node)
        emit(code, OP_LOAD_CONST, "kind", node)
        emit(code, OP_LOAD_CONST, variant_name, node)
        emit(code, OP_LOAD_CONST, "fields", node)
        for arg_node in arg_nodes:
            self.compile_expr(arg_node, code)
        emit(code, OP_BUILD_LIST, len(arg_nodes), node)
        emit(code, OP_BUILD_DICT, 3, node)

    def _compile_unpack_store(self, leaf, code, node, mutable=None):
        """Store one unpacked value into its target."""
        if isinstance(leaf, ast.UnpackTarget):
            emit(code, OP_DEFINE_NAME, (leaf.name, True), node)
            return
        if isinstance(leaf, ast.Identifier):
            if mutable is None:
                emit(code, OP_STORE_NAME, leaf.name, node)
            else:
                emit(code, OP_DEFINE_NAME, (leaf.name, mutable), node)
            return
        if isinstance(leaf, ast.Index):
            self.compile_expr(leaf.target, code)
            if isinstance(leaf.index, ast.Slice):
                for part in (leaf.index.start, leaf.index.stop,
                             leaf.index.step):
                    if part is None:
                        emit(code, OP_LOAD_CONST, None, node)
                    else:
                        self.compile_expr(part, code)
                emit(code, OP_STORE_SLICE, None, node)
            else:
                self.compile_expr(leaf.index, code)
                emit(code, OP_STORE_INDEX, None, node)
            return
        raise CompileError("invalid unpacking target")

    def _compile_comprehension(self, node, code):
        """Compile a list or dict comprehension.

        The accumulator lives on the value stack while the clause loops
        run, so `LIST_APPEND`/`DICT_SET` only have to look at the top of
        the stack.
        """
        if node.is_dict:
            emit(code, OP_BUILD_DICT, 0, node)
        else:
            emit(code, OP_BUILD_LIST, 0, node)
        emit(code, OP_ENTER_SCOPE, None, node)
        self._scope_depth += 1
        self._compile_clauses(node, node.clauses, 0, code)
        emit(code, OP_EXIT_SCOPE, None, node)
        self._scope_depth -= 1

    def _compile_clauses(self, node, clauses, index, code):
        if index >= len(clauses):
            if node.is_dict:
                self.compile_expr(node.key, code)
                self.compile_expr(node.value, code)
                emit(code, OP_DICT_SET, None, node)
            else:
                self.compile_expr(node.element, code)
                emit(code, OP_LIST_APPEND, None, node)
            return
        clause = clauses[index]
        self.compile_expr(clause.iterable, code)
        emit(code, OP_FOR_SETUP, None, node)
        head = len(code)
        exit_jump = emit(code, OP_FOR_NEXT, None, node)
        emit(code, OP_DEFINE_NAME, (clause.target, True), node)
        skip_jump = None
        if clause.condition is not None:
            self.compile_expr(clause.condition, code)
            skip_jump = emit(code, OP_JUMP_IF_FALSE, None, node)
        self._compile_clauses(node, clauses, index + 1, code)
        if skip_jump is not None:
            patch(code, skip_jump)
        emit(code, OP_JUMP, head, node)
        patch(code, exit_jump)

    def compile_expression(self, node):
        code = []
        self.compile_expr(node, code)
        code.append((OP_HALT, None, getattr(node, "line", 0),
                     getattr(node, "col", 0)))
        return make_code("<expr>", [], code, self.filename, self.source)
