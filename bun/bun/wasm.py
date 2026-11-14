"""A real WebAssembly backend for Bun's integer core.

The output is a binary module, not text: the magic `\\0asm`, the version,
and the type, import, function, memory, export, code and data sections of
the WebAssembly 1.0 binary format.  `bun --engine wasm` builds the module
in memory and runs it on Bun's own WebAssembly virtual machine
(`bun/wasmvm.py`), and `bun compile --target wasm` writes the same bytes
to a `.wasm` file that another runtime can load.

The backend covers the integer core described in `bun/intcore.py`.  A
program outside it is refused by name, never silently miscompiled.
"""

from . import ast
from .intcore import Unsupported, range_call, static_type

MAGIC = b"\x00asm\x01\x00\x00\x00"

I32 = 0x7F
I64 = 0x7E
BLOCK_EMPTY = 0x40

# Control.
UNREACHABLE = 0x00
NOP = 0x01
BLOCK = 0x02
LOOP = 0x03
IF = 0x04
ELSE = 0x05
END = 0x0B
BR = 0x0C
BR_IF = 0x0D
RETURN = 0x0F
CALL = 0x10
DROP = 0x1A

# Variables.
LOCAL_GET = 0x20
LOCAL_SET = 0x21
LOCAL_TEE = 0x22

# Constants.
I32_CONST = 0x41
I64_CONST = 0x42

# Integer comparison, all of them answer i32.
I64_EQZ = 0x50
I32_NE = 0x47
I32_AND = 0x71
I64_EQ = 0x51
I64_NE = 0x52
I64_LT_S = 0x53
I64_GT_S = 0x55
I64_LE_S = 0x57
I64_GE_S = 0x59

# Integer arithmetic.
I64_ADD = 0x7C
I64_SUB = 0x7D
I64_MUL = 0x7E
I64_DIV_S = 0x7F
I64_REM_S = 0x81
I64_AND = 0x83
I64_OR = 0x84
I64_XOR = 0x85
I64_SHL = 0x86
I64_SHR_S = 0x87
I32_WRAP_I64 = 0xA7
I64_EXTEND_I32_U = 0xAD

# Section ids.
SECTION_TYPE = 1
SECTION_IMPORT = 2
SECTION_FUNCTION = 3
SECTION_MEMORY = 5
SECTION_EXPORT = 7
SECTION_CODE = 10
SECTION_DATA = 11

FUNC_KIND = 0x00
MEMORY_PAGES = 1
DATA_BASE = 1024


def uleb(value):
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def sleb(value):
    out = bytearray()
    more = True
    while more:
        byte = value & 0x7F
        value >>= 7
        if (value == 0 and not byte & 0x40) or (value == -1 and byte & 0x40):
            more = False
        else:
            byte |= 0x80
        out.append(byte)
    return bytes(out)


def vector(items):
    return uleb(len(items)) + b"".join(items)

def section(section_id, payload):
    return bytes([section_id]) + uleb(len(payload)) + payload


def name_bytes(text):
    raw = text.encode("utf-8")
    return uleb(len(raw)) + raw


class _Signature:
    __slots__ = ("params", "results")

    def __init__(self, params, results):
        self.params = params
        self.results = results

    def key(self):
        return (tuple(self.params), tuple(self.results))


class _Function:
    __slots__ = ("name", "params", "results", "locals", "body", "index",
                 "hidden")

    def __init__(self, name, params, results, hidden=False):
        self.name = name
        self.params = params
        self.results = results
        self.locals = []
        self.body = bytearray()
        self.index = 0
        self.hidden = hidden


class Module:
    """A built module: the bytes, the exports and the host imports."""

    def __init__(self, data, functions, entry):
        self.data = data
        self.functions = functions
        self.entry = entry

    def write(self, path):
        with open(path, "wb") as handle:
            handle.write(self.data)
        return path


class _Builder:
    def __init__(self):
        self.types = []
        self.imports = []
        self.functions = []
        self.strings = {}
        self.data = bytearray()
        self.returns = {}
        self.floordiv = 0
        self.floormod = 0
        self.print_i64 = 0
        self.print_bool = 0
        self.print_str = 0

    # -- types ---------------------------------------------------------
    def type_index(self, params, results):
        wanted = (tuple(params), tuple(results))
        for index, signature in enumerate(self.types):
            if signature.key() == wanted:
                return index
        self.types.append(_Signature(list(params), list(results)))
        return len(self.types) - 1

    def add_import(self, module, field, params, results):
        index = self.type_index(params, results)
        self.imports.append((module, field, index))
        return len(self.imports) - 1

    def add_string(self, text):
        raw = text.encode("utf-8")
        if text in self.strings:
            return self.strings[text]
        offset = DATA_BASE + len(self.data)
        self.data.extend(raw)
        self.strings[text] = (offset, len(raw))
        return self.strings[text]

    # -- module --------------------------------------------------------
    def assign_indices(self):
        """Number the functions, imports first.

        The index must exist before a body is compiled, because a call
        writes it into the code.
        """
        import_count = len(self.imports)
        for index, function in enumerate(self.functions):
            function.index = import_count + index

    def build(self):
        self.assign_indices()
        function_types = [self.type_index(function.params, function.results)
                          for function in self.functions]
        payload = bytearray(MAGIC)

        types = []
        for signature in self.types:
            item = bytearray([0x60])
            item += vector([bytes([kind]) for kind in signature.params])
            item += vector([bytes([kind]) for kind in signature.results])
            types.append(bytes(item))
        payload += section(SECTION_TYPE, vector(types))

        imports = []
        for module, field, index in self.imports:
            item = bytearray(name_bytes(module) + name_bytes(field))
            item += bytes([FUNC_KIND]) + uleb(index)
            imports.append(bytes(item))
        if imports:
            payload += section(SECTION_IMPORT, vector(imports))

        functions = [uleb(type_index) for type_index in function_types]
        payload += section(SECTION_FUNCTION, vector(functions))

        memory = bytes([0x00]) + uleb(MEMORY_PAGES)
        payload += section(SECTION_MEMORY, vector([memory]))

        exports = []
        for function in self.functions:
            if function.hidden:
                continue
            item = bytearray(name_bytes(function.name))
            item += bytes([FUNC_KIND]) + uleb(function.index)
            exports.append(bytes(item))
        exports.append(bytes(name_bytes("memory")) + bytes([0x02, 0x00]))
        payload += section(SECTION_EXPORT, vector(exports))

        bodies = []
        for function in self.functions:
            body = bytearray()
            groups = []
            for kind in function.locals:
                if groups and groups[-1][1] == kind:
                    groups[-1][0] += 1
                else:
                    groups.append([1, kind])
            body += vector([uleb(count) + bytes([kind])
                            for count, kind in groups])
            body += function.body
            body += bytes([END])
            bodies.append(uleb(len(body)) + bytes(body))
        payload += section(SECTION_CODE, vector(bodies))

        if self.data:
            segment = bytes([0x00]) + bytes([I32_CONST]) + sleb(DATA_BASE)
            segment += bytes([END]) + uleb(len(self.data)) + bytes(self.data)
            payload += section(SECTION_DATA, vector([segment]))

        return bytes(payload)


class _Body:
    """The code of one function."""

    def __init__(self, builder, function, engine="wasm"):
        self.builder = builder
        self.function = function
        self.engine = engine
        self.labels = []
        self.scopes = [{}]
        self.slot = 0

    # -- helpers -------------------------------------------------------
    def unsupported(self, what, node=None):
        raise Unsupported(self.engine, what, node)

    def emit(self, *values):
        for value in values:
            if isinstance(value, bytes):
                self.function.body += value
            else:
                self.function.body.append(value)

    def u(self, value):
        self.function.body += uleb(value)

    def const(self, value):
        self.emit(I64_CONST)
        self.function.body += sleb(int(value))

    def declare(self, name, type_name, node=None):
        if type_name not in ("int", "bool"):
            self.unsupported("the type '%s' of '%s'"
                             % (type_name, name), node)
        index = len(self.function.params) + len(self.function.locals)
        self.function.locals.append(I64)
        self.scopes[-1][name] = (index, type_name)
        return index

    def bind_params(self, params):
        """A parameter is a local of the function, not a new local."""
        for index, param in enumerate(params):
            self.scopes[0][param.name] = (index, param.type_name or "int")

    def lookup(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name][0]
        return None

    def type_of_name(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name][1]
        return None

    def push_scope(self):
        self.scopes.append({})

    def pop_scope(self):
        self.scopes.pop()

    # -- labels --------------------------------------------------------
    def push_label(self, kind, label):
        self.labels.append({"kind": kind, "label": label})
        return len(self.labels) - 1

    def pop_label(self):
        self.labels.pop()

    def depth(self, kind, label, node):
        for index in range(len(self.labels) - 1, -1, -1):
            entry = self.labels[index]
            if entry["kind"] != kind:
                continue
            if label is not None and entry["label"] != label:
                continue
            return len(self.labels) - 1 - index
        if label is None:
            self.unsupported("'%s' outside of a loop" % kind, node)
        self.unsupported("a '%s' of the loop '%s'" % (kind, label), node)

    # -- statements ----------------------------------------------------
    def statements(self, items):
        for item in items:
            self.statement(item)

    def statement(self, node):
        if isinstance(node, ast.LetStmt):
            self.let_stmt(node)
        elif isinstance(node, ast.AssignStmt):
            self.assign_stmt(node)
        elif isinstance(node, ast.OpAssignStmt):
            self.op_assign_stmt(node)
        elif isinstance(node, ast.IncDecStmt):
            self.incdec_stmt(node)
        elif isinstance(node, ast.ExprStmt):
            self.expr(node.expr)
            self.emit(DROP)
        elif isinstance(node, ast.Block):
            self.push_scope()
            self.statements(node.statements)
            self.pop_scope()
        elif isinstance(node, ast.IfStmt):
            self.if_stmt(node)
        elif isinstance(node, ast.WhileStmt):
            self.while_stmt(node)
        elif isinstance(node, ast.ForStmt):
            self.for_stmt(node)
        elif isinstance(node, ast.ReturnStmt):
            if node.value is None:
                self.const(0)
            else:
                self.expr(node.value)
            self.emit(RETURN)
        elif isinstance(node, ast.BreakStmt):
            self.emit(BR)
            self.u(self.depth("exit", node.label, node))
        elif isinstance(node, ast.ContinueStmt):
            self.emit(BR)
            self.u(self.depth("loop", node.label, node))
        elif isinstance(node, ast.AssertStmt):
            self.assert_stmt(node)
        else:
            self.unsupported("the statement '%s'" % type(node).__name__, node)

    def let_stmt(self, node):
        kind = node.type_ann
        if kind is None:
            kind = static_type(node.value, self.type_of_name,
                               self.builder.returns.get) or "int"
        index = self.declare(node.name, kind, node)
        self.expr(node.value)
        self.emit(LOCAL_SET)
        self.u(index)

    def assign_stmt(self, node):
        if not isinstance(node.target, ast.Identifier):
            self.unsupported("assignment to %s"
                             % type(node.target).__name__, node)
        index = self.lookup(node.target.name)
        if index is None:
            self.unsupported("assignment to the global '%s'"
                             % node.target.name, node)
        self.expr(node.value)
        self.emit(LOCAL_SET)
        self.u(index)

    def op_assign_stmt(self, node):
        if not isinstance(node.target, ast.Identifier):
            self.unsupported("compound assignment to %s"
                             % type(node.target).__name__, node)
        index = self.lookup(node.target.name)
        if index is None:
            self.unsupported("compound assignment to the global '%s'"
                             % node.target.name, node)
        self.emit(LOCAL_GET)
        self.u(index)
        self.expr(node.value)
        self.emit(*_BINARY.get(node.op, ()))
        if node.op not in _BINARY:
            self.unsupported("the operator '%s'" % node.op, node)
        self.emit(LOCAL_SET)
        self.u(index)

    def incdec_stmt(self, node):
        if not isinstance(node.target, ast.Identifier):
            self.unsupported("increment of %s"
                             % type(node.target).__name__, node)
        index = self.lookup(node.target.name)
        if index is None:
            self.unsupported("increment of the global '%s'"
                             % node.target.name, node)
        self.emit(LOCAL_GET)
        self.u(index)
        self.const(1)
        self.emit(I64_ADD if node.op in ("++", "+=") else I64_SUB)
        self.emit(LOCAL_SET)
        self.u(index)

    def if_stmt(self, node):
        self.expr(node.condition)
        self.const(0)
        self.emit(I64_NE, IF, BLOCK_EMPTY)
        self.push_label("if", None)
        self.push_scope()
        self.statement(node.then_branch)
        self.pop_scope()
        if node.else_branch is not None:
            self.emit(ELSE)
            self.push_scope()
            self.statement(node.else_branch)
            self.pop_scope()
        self.pop_label()
        self.emit(END)

    def while_stmt(self, node):
        self.emit(BLOCK, BLOCK_EMPTY)
        self.push_label("exit", node.label)
        self.emit(LOOP, BLOCK_EMPTY)
        self.push_label("loop", node.label)
        self.expr(node.condition)
        self.emit(I64_EQZ, BR_IF)
        self.u(self.depth("exit", node.label, node))
        self.push_scope()
        self.statement(node.body)
        self.pop_scope()
        self.emit(BR)
        self.u(self.depth("loop", node.label, node))
        self.pop_label()
        self.emit(END)
        self.pop_label()
        self.emit(END)
        if node.orelse is not None:
            self.statement(node.orelse)

    def for_stmt(self, node):
        if len(node.targets) != 1:
            self.unsupported("a loop over %d names" % len(node.targets), node)
        args = range_call(node.iterable)
        if args is None:
            self.unsupported("a loop over a container", node)
        if not 1 <= len(args) <= 3:
            self.unsupported("range() with %d arguments" % len(args), node)
        self.push_scope()
        name = node.targets[0]
        start, stop, step = self._range_bounds(args, node)
        index = self.declare(name, "int", node)
        self.expr(start)
        self.emit(LOCAL_SET)
        self.u(index)
        stop_index = self.declare("#stop", "int", node)
        self.expr(stop)
        self.emit(LOCAL_SET)
        self.u(stop_index)
        step_index = self.declare("#step", "int", node)
        self.expr(step)
        self.emit(LOCAL_SET)
        self.u(step_index)

        self.emit(BLOCK, BLOCK_EMPTY)
        self.push_label("exit", node.label)
        self.emit(LOOP, BLOCK_EMPTY)
        self.push_label("loop", node.label)
        # (step > 0 ? i < stop : i > stop)
        self.emit(LOCAL_GET)
        self.u(step_index)
        self.const(0)
        self.emit(I64_GT_S, I64_EXTEND_I32_U)
        self.const(0)
        self.emit(I64_NE, IF, I64)
        self.emit(LOCAL_GET)
        self.u(index)
        self.emit(LOCAL_GET)
        self.u(stop_index)
        self.emit(I64_LT_S, I64_EXTEND_I32_U)
        self.emit(ELSE)
        self.emit(LOCAL_GET)
        self.u(index)
        self.emit(LOCAL_GET)
        self.u(stop_index)
        self.emit(I64_GT_S, I64_EXTEND_I32_U)
        self.emit(END)
        self.emit(I64_EQZ, BR_IF)
        self.u(self.depth("exit", node.label, node))
        self.push_scope()
        self.statement(node.body)
        self.pop_scope()
        self.emit(LOCAL_GET)
        self.u(index)
        self.emit(LOCAL_GET)
        self.u(step_index)
        self.emit(I64_ADD, LOCAL_SET)
        self.u(index)
        self.emit(BR)
        self.u(self.depth("loop", node.label, node))
        self.pop_label()
        self.emit(END)
        self.pop_label()
        self.emit(END)
        self.pop_scope()
        if node.orelse is not None:
            self.statement(node.orelse)

    def _range_bounds(self, args, node):
        if len(args) == 1:
            return ast.Literal(0, node.line, node.col), args[0], ast.Literal(1, node.line, node.col)
        if len(args) == 2:
            return args[0], args[1], ast.Literal(1, node.line, node.col)
        return args[0], args[1], args[2]

    def assert_stmt(self, node):
        self.expr(node.condition)
        self.emit(I64_EQZ, IF, BLOCK_EMPTY)
        self.emit(UNREACHABLE)
        self.emit(END)

    # -- expressions ---------------------------------------------------
    def expr(self, node):
        if isinstance(node, ast.Literal):
            value = node.value
            if isinstance(value, bool):
                self.const(1 if value else 0)
            elif isinstance(value, int):
                self.const(value)
            elif isinstance(value, str):
                self.unsupported("a string outside print", node)
            elif value is None:
                self.unsupported("null", node)
            else:
                self.unsupported("the literal %r" % (value,), node)
        elif isinstance(node, ast.Identifier):
            index = self.lookup(node.name)
            if index is None:
                self.unsupported("the global '%s'" % node.name, node)
            self.emit(LOCAL_GET)
            self.u(index)
        elif isinstance(node, ast.Unary):
            self.unary(node)
        elif isinstance(node, ast.Binary):
            self.binary(node)
        elif isinstance(node, ast.Logical):
            self.logical(node)
        elif isinstance(node, ast.Call):
            self.call(node)
        else:
            self.unsupported("the expression '%s'" % type(node).__name__,
                             node)

    def unary(self, node):
        if node.op == "-":
            self.const(0)
            self.expr(node.operand)
            self.emit(I64_SUB)
        elif node.op in ("not", "!"):
            self.expr(node.operand)
            self.emit(I64_EQZ, I64_EXTEND_I32_U)
        elif node.op == "+":
            self.expr(node.operand)
        else:
            self.unsupported("the unary operator '%s'" % node.op, node)

    def binary(self, node):
        if node.op in ("//", "%"):
            helper = (self.builder.floordiv if node.op == "//"
                      else self.builder.floormod)
            self.expr(node.left)
            self.expr(node.right)
            self.emit(CALL)
            self.u(helper)
            return
        self.expr(node.left)
        self.expr(node.right)
        opcodes = _BINARY.get(node.op)
        if opcodes is None:
            self.unsupported("the operator '%s'" % node.op, node)
        self.emit(*opcodes)

    def logical(self, node):
        """`a and b` answers a when a is false, and b otherwise.

        The answer is the operand, not a truth value: `3 and 5` is 5.  A
        local keeps the left operand while the condition is read from it.
        """
        keep = self.declare("#logic", "int", node)
        self.expr(node.left)
        self.emit(LOCAL_TEE)
        self.u(keep)
        self.const(0)
        self.emit(I64_NE, IF, I64)
        if node.op in ("and", "&&"):
            self.expr(node.right)
            self.emit(ELSE, LOCAL_GET)
            self.u(keep)
            self.emit(END)
        else:
            self.emit(LOCAL_GET)
            self.u(keep)
            self.emit(ELSE)
            self.expr(node.right)
            self.emit(END)

    def call(self, node):
        if not isinstance(node.callee, ast.Identifier):
            self.unsupported("a call of %s" % type(node.callee).__name__, node)
        name = node.callee.name
        if node.kwargs:
            self.unsupported("keyword arguments", node)
        if name == "print":
            return self.print_call(node)
        function = self.builder.function_by_name(name)
        if function is None:
            self.unsupported("the builtin '%s'" % name, node)
        if len(node.args) != len(function.params):
            self.unsupported("a call of '%s' with %d arguments"
                             % (name, len(node.args)), node)
        if len(node.args) > 6:
            self.unsupported("a call with %d arguments" % len(node.args), node)
        for arg in node.args:
            self.expr(arg)
        self.emit(CALL)
        self.u(function.index)

    def print_call(self, node):
        if len(node.args) != 1:
            self.unsupported("print with %d arguments" % len(node.args), node)
        arg = node.args[0]
        if isinstance(arg, ast.Literal) and isinstance(arg.value, str):
            offset, length = self.builder.add_string(arg.value)
            self.const(offset)
            self.const(length)
            self.emit(CALL)
            self.u(self.builder.print_str)
            self.const(0)
            return
        kind = static_type(arg, self.type_of_name, self.builder.returns.get)
        if kind == "bool":
            self.expr(arg)
            self.emit(CALL)
            self.u(self.builder.print_bool)
        elif kind == "int":
            self.expr(arg)
            self.emit(CALL)
            self.u(self.builder.print_i64)
        else:
            self.unsupported("print of a value that is not an integer, a"
                             " boolean or a string literal", node)
        self.const(0)


_BINARY = {
    "+": (I64_ADD,),
    "-": (I64_SUB,),
    "*": (I64_MUL,),
    "&": (I64_AND,),
    "|": (I64_OR,),
    "^": (I64_XOR,),
    "<<": (I64_SHL,),
    ">>": (I64_SHR_S,),
    "==": (I64_EQ, I64_EXTEND_I32_U),
    "!=": (I64_NE, I64_EXTEND_I32_U),
    "<": (I64_LT_S, I64_EXTEND_I32_U),
    ">": (I64_GT_S, I64_EXTEND_I32_U),
    "<=": (I64_LE_S, I64_EXTEND_I32_U),
    ">=": (I64_GE_S, I64_EXTEND_I32_U),
}


class _ModuleBuilder(_Builder):
    def function_by_name(self, name):
        for function in self.functions:
            if function.name == name:
                return function
        return None


def _get(index):
    return bytes([LOCAL_GET]) + uleb(index)


def _set(index):
    return bytes([LOCAL_SET]) + uleb(index)


def _const(value):
    return bytes([I64_CONST]) + sleb(value)


def _floor_helpers(builder):
    """Add the two helpers that make division Bun's division.

    WebAssembly divides toward zero and takes the remainder of the
    dividend; Bun divides toward negative infinity and takes the
    remainder of the divisor.  The difference is one subtraction, and it
    is written once, here, instead of at every `/` and `%` of a program.
    """
    divide = _Function("#floordiv", [I64, I64], [I64], hidden=True)
    divide.locals = [I64, I64]
    divide.body = bytearray(
        _get(0) + _get(1) + bytes([I64_DIV_S]) + _set(2)
        + _get(0) + _get(1) + bytes([I64_REM_S]) + _set(3)
        + _get(3) + _const(0) + bytes([I64_NE])
        + _get(3) + _const(0) + bytes([I64_LT_S])
        + _get(1) + _const(0) + bytes([I64_LT_S])
        + bytes([I32_NE, I32_AND, IF, BLOCK_EMPTY])
        + _get(2) + _const(1) + bytes([I64_SUB]) + _set(2)
        + bytes([END]) + _get(2))

    modulo = _Function("#floormod", [I64, I64], [I64], hidden=True)
    modulo.locals = [I64]
    modulo.body = bytearray(
        _get(0) + _get(1) + bytes([I64_REM_S]) + _set(2)
        + _get(2) + _const(0) + bytes([I64_NE])
        + _get(2) + _const(0) + bytes([I64_LT_S])
        + _get(1) + _const(0) + bytes([I64_LT_S])
        + bytes([I32_NE, I32_AND, IF, BLOCK_EMPTY])
        + _get(2) + _get(1) + bytes([I64_ADD]) + _set(2)
        + bytes([END]) + _get(2))

    builder.functions.extend([divide, modulo])
    return divide, modulo


def build(program, filename="<wasm>"):
    """Build a WebAssembly module from a Bun program of the integer core."""
    builder = _ModuleBuilder()
    builder.print_i64 = builder.add_import("env", "print_i64", [I64], [])
    builder.print_bool = builder.add_import("env", "print_bool", [I64], [])
    builder.print_str = builder.add_import("env", "print_str", [I64, I64],
                                           [])
    divide, modulo = _floor_helpers(builder)

    declarations = [node for node in program.statements
                    if isinstance(node, ast.FnDecl)]
    for node in declarations:
        if node.type_params:
            raise Unsupported("wasm", "a generic function", node)
        for param in node.params:
            if param.default is not None:
                raise Unsupported("wasm", "a default argument", node)
            if param.param_kind != "positional":
                raise Unsupported("wasm", "a %s parameter" % param.param_kind,
                                  node)
        if node.return_type not in ("int", "bool"):
            raise Unsupported(
                "wasm", "a function without an int or bool return type"
                if node.return_type is None else
                "the return type '%s'" % node.return_type, node)
        if len(node.params) > 6:
            raise Unsupported("wasm", "a function with %d parameters"
                              % len(node.params), node)
        function = _Function(node.name, [I64] * len(node.params), [I64])
        builder.functions.append(function)
        builder.returns[node.name] = node.return_type

    entry = _Function("main", [], [I64])
    builder.functions.append(entry)
    builder.returns["main"] = "int"
    builder.assign_indices()
    builder.floordiv = divide.index
    builder.floormod = modulo.index

    for node in declarations:
        function = builder.function_by_name(node.name)
        body = _Body(builder, function)
        body.bind_params(node.params)
        body.statement(node.body)
        body.const(0)

    body = _Body(builder, entry)
    for node in program.statements:
        if isinstance(node, ast.FnDecl):
            continue
        body.statement(node)
    body.const(0)

    data = builder.build()
    return Module(data, builder.functions, entry)


def compile_program(program, filename="<wasm>"):
    """Build the module and answer its bytes."""
    return build(program, filename).data
