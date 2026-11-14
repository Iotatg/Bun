"""A real x86-64 JIT for Bun's integer core.

The engine emits machine code, not a closure and not a tree walk: a
function of the core becomes a sequence of x86-64 instructions in an
executable page, and calling it is a `call` of that address.  The calling
convention is the System V one, so a compiled function is an ordinary
native function of the process.

The subset is the one described in `bun/intcore.py`.  A program outside
it is refused by name, and the message says which engine runs it.
"""

import ctypes
import mmap

from . import ast
from .intcore import Unsupported, range_call, static_type

# Registers of the System V argument order.
ARG_REGISTERS = [
    (0x48, 0x8B, 0xBD),   # rdi
    (0x48, 0x8B, 0xB5),   # rsi
    (0x48, 0x8B, 0x95),   # rdx
    (0x48, 0x8B, 0x8D),   # rcx
    (0x4C, 0x8B, 0x85),   # r8
    (0x4C, 0x8B, 0x8D),   # r9
]

STORE_REGISTERS = [
    (0x48, 0x89, 0xBD),   # rdi
    (0x48, 0x89, 0xB5),   # rsi
    (0x48, 0x89, 0x95),   # rdx
    (0x48, 0x89, 0x8D),   # rcx
    (0x4C, 0x89, 0x85),   # r8
    (0x4C, 0x89, 0x8D),   # r9
]

MOV_RAX_FROM_REGISTER = [
    bytes([0x48, 0x89, 0xF8]),   # rdi
    bytes([0x48, 0x89, 0xF0]),   # rsi
    bytes([0x48, 0x89, 0xD0]),   # rdx
    bytes([0x48, 0x89, 0xC8]),   # rcx
    bytes([0x4C, 0x89, 0xC0]),   # r8
    bytes([0x4C, 0x89, 0xC8]),   # r9
]

SETCC = {
    "==": 0x94,
    "!=": 0x95,
    "<": 0x9C,
    ">": 0x9F,
    "<=": 0x9E,
    ">=": 0x9D,
}

JZ = bytes([0x0F, 0x84])
JNZ = bytes([0x0F, 0x85])
JMP = bytes([0xE9])
JLE = bytes([0x0F, 0x8E])
JNS = bytes([0x0F, 0x89])
CALL = bytes([0xE8])
CALL_RAX = bytes([0xFF, 0xD0])
RET = bytes([0xC3])
LEAVE = bytes([0xC9])
PUSH_RBP = bytes([0x55])
MOV_RBP_RSP = bytes([0x48, 0x89, 0xE5])
SUB_RSP = bytes([0x48, 0x81, 0xEC])
TEST_RAX = bytes([0x48, 0x85, 0xC0])
TEST_RDX = bytes([0x48, 0x85, 0xD2])
TEST_RCX = bytes([0x48, 0x85, 0xC9])
MOV_RBX_RAX = bytes([0x48, 0x89, 0xC3])
MOV_RCX_RBX = bytes([0x48, 0x89, 0xD9])
MOV_RCX_RDX = bytes([0x48, 0x89, 0xD1])
XOR_RCX_RBX = bytes([0x48, 0x31, 0xD9])
CMP_RAX_RBX = bytes([0x48, 0x39, 0xD8])
CQO = bytes([0x48, 0x99])
IDIV_RBX = bytes([0x48, 0xF7, 0xFB])
ADD_RAX_RBX = bytes([0x48, 0x01, 0xD8])
SUB_RAX_RBX = bytes([0x48, 0x29, 0xD8])
IMUL_RAX_RBX = bytes([0x48, 0x0F, 0xAF, 0xC3])
AND_RAX_RBX = bytes([0x48, 0x21, 0xD8])
OR_RAX_RBX = bytes([0x48, 0x09, 0xD8])
XOR_RAX_RBX = bytes([0x48, 0x31, 0xD8])
SHL_RAX_CL = bytes([0x48, 0xD3, 0xE0])
SAR_RAX_CL = bytes([0x48, 0xD3, 0xF8])
NEG_RAX = bytes([0x48, 0xF7, 0xD8])
DEC_RAX = bytes([0x48, 0x83, 0xE8, 0x01])
INC_RAX = bytes([0x48, 0x83, 0xC0, 0x01])
SETNE_AL = bytes([0x0F, 0x95, 0xC0])
MOVZX_RAX_AL = bytes([0x48, 0x0F, 0xB6, 0xC0])


class _Code:
    """The bytes of one function and the patches they still need."""

    def __init__(self):
        self.data = bytearray()
        self.labels = {}
        self.jumps = []
        self.calls = []
        self.strings = []
        self.slots = 0
        self.scope = [{}]
        self.loops = []

    # -- emission ------------------------------------------------------
    def emit(self, *parts):
        for part in parts:
            self.data += part

    def imm32(self, value):
        self.data += (value & 0xFFFFFFFF).to_bytes(4, "little")

    def mov_rax_imm(self, value):
        self.emit(bytes([0x48, 0xB8]))
        self.data += (value & 0xFFFFFFFFFFFFFFFF).to_bytes(8, "little")

    def mov_rax_slot(self, slot):
        self.emit(bytes([0x48, 0x8B, 0x85]))
        self.imm32(-8 * (slot + 1))

    def mov_rbx_slot(self, slot):
        self.emit(bytes([0x48, 0x8B, 0x9D]))
        self.imm32(-8 * (slot + 1))

    def mov_slot_rax(self, slot):
        self.emit(bytes([0x48, 0x89, 0x85]))
        self.imm32(-8 * (slot + 1))

    def cmp_rax_slot(self, slot):
        self.emit(bytes([0x48, 0x3B, 0x85]))
        self.imm32(-8 * (slot + 1))

    # -- labels --------------------------------------------------------
    def new_label(self, prefix="L"):
        name = "%s%d" % (prefix, len(self.labels) + 1)
        while name in self.labels:
            name += "_"
        return name

    def place(self, name):
        self.labels[name] = len(self.data)

    def jump(self, opcode, name):
        self.emit(opcode)
        position = len(self.data)
        self.imm32(0)
        self.jumps.append((position, name))

    def call_name(self, name):
        self.emit(CALL)
        position = len(self.data)
        self.imm32(0)
        self.calls.append((position, name))

    def resolve(self):
        for position, name in self.jumps:
            target = self.labels.get(name)
            if target is None:
                raise Unsupported("jit", "a jump to the missing label '%s'"
                                  % name)
            delta = target - (position + 4)
            self.data[position:position + 4] = (delta & 0xFFFFFFFF).to_bytes(
                4, "little")

    # -- slots ---------------------------------------------------------
    def slot(self):
        index = self.slots
        self.slots += 1
        return index

    def bind(self, name, slot):
        self.scope[-1][name] = slot

    def lookup(self, name):
        for scope in reversed(self.scope):
            if name in scope:
                return scope[name]
        return None

    def type_of(self, name):
        return self.jit.type_of_local(self, name)


class _Function:
    def __init__(self, decl):
        self.decl = decl
        self.name = decl.name
        self.code = None
        self.offset = 0


class Jit:
    """Compile a whole program of the core and run it."""

    def __init__(self, program, filename="<jit>"):
        self.program = program
        self.filename = filename
        self.functions = {}
        self.returns = {}
        self.local_types = {}
        self.callbacks = {}
        self.keepalive = []
        self.buffer = None
        self.entry = None

    # -- compilation ---------------------------------------------------
    def unsupported(self, what, node=None):
        raise Unsupported("jit", what, node)

    def type_of_local(self, code, name):
        return self.local_types.get((id(code), name))

    def compile(self):
        declarations = [node for node in self.program.statements
                        if isinstance(node, ast.FnDecl)]
        for node in declarations:
            self._check_signature(node)
            self.returns[node.name] = node.return_type
            self.functions[node.name] = _Function(node)

        top_level = [node for node in self.program.statements
                     if not isinstance(node, ast.FnDecl)]
        self.entry = _Function(ast.FnDecl("__main", [],
                                          ast.Block(top_level)))
        order = [node.name for node in declarations] + ["__main"]

        for name in order:
            function = (self.functions[name] if name != "__main"
                        else self.entry)
            code = _Code()
            code.jit = self
            function.code = code
            self._compile_function(function, code)

        self._layout(order)
        return self

    def _check_signature(self, node):
        if node.type_params:
            self.unsupported("a generic function", node)
        if node.return_type not in ("int", "bool"):
            self.unsupported(
                "a function without an int or bool return type"
                if node.return_type is None else
                "the return type '%s'" % node.return_type, node)
        if len(node.params) > 6:
            self.unsupported("a function with %d parameters"
                             % len(node.params), node)
        for param in node.params:
            if param.default is not None:
                self.unsupported("a default argument", node)
            if param.param_kind != "positional":
                self.unsupported("a %s parameter" % param.param_kind, node)
            if param.type_name not in ("int", "bool", None):
                self.unsupported("the parameter type '%s'" % param.type_name,
                                 node)

    def _compile_function(self, function, code):
        node = function.decl
        params = []
        for param in node.params:
            slot = code.slot()
            code.bind(param.name, slot)
            self.local_types[(id(code), param.name)] = (
                param.type_name or "int")
            params.append(slot)

        if node.name == "__main":
            self._statements(node.body.statements, code)
        else:
            self._statement(node.body, code)
        code.emit(bytes([0x48, 0x31, 0xC0]))        # xor eax, eax
        code.emit(LEAVE, RET)

        frame = code.slots * 8
        frame = (frame + 15) // 16 * 16
        prologue = bytearray()
        prologue += PUSH_RBP + MOV_RBP_RSP + SUB_RSP
        prologue += frame.to_bytes(4, "little")
        for index, slot in enumerate(params):
            prologue += bytes(STORE_REGISTERS[index])
            prologue += (-8 * (slot + 1)).to_bytes(4, "little", signed=True)
        code.resolve()
        function.prologue = bytes(prologue)
        function.body = bytes(code.data)

    # -- layout and run ------------------------------------------------
    def _layout(self, order):
        total = 0
        for name in order:
            function = (self.functions[name] if name != "__main"
                        else self.entry)
            function.offset = total
            total += len(function.prologue) + len(function.body)
        data_base = total
        strings = bytearray()
        offsets = {}
        self.string_fixups = []

        for name in order:
            function = (self.functions[name] if name != "__main"
                        else self.entry)
            for position, text in function.code.strings:
                if text not in offsets:
                    offsets[text] = len(strings)
                    strings += text.encode("utf-8")
                self.string_fixups.append((
                    function.offset + len(function.prologue) + position,
                    offsets[text]))
        self.data_base = data_base

        self.buffer = bytearray()
        for name in order:
            function = (self.functions[name] if name != "__main"
                        else self.entry)
            self.buffer += function.prologue
            self.buffer += function.body
        self.buffer += strings

        for name in order:
            function = (self.functions[name] if name != "__main"
                        else self.entry)
            for position, target in function.code.calls:
                if target not in self.functions:
                    self.unsupported("the builtin '%s'" % target)
                callee = self.functions[target]
                absolute = (function.offset + len(function.prologue)
                            + position)
                delta = callee.offset - (absolute + 4)
                self.buffer[absolute:absolute + 4] = (
                    delta & 0xFFFFFFFF).to_bytes(4, "little")

    def run(self):
        page = mmap.mmap(-1, max(len(self.buffer), 4096),
                         prot=mmap.PROT_READ | mmap.PROT_WRITE
                         | mmap.PROT_EXEC)
        address = ctypes.addressof(ctypes.c_char.from_buffer(page))
        for position, offset in self.string_fixups:
            absolute = address + self.data_base + offset
            self.buffer[position:position + 8] = absolute.to_bytes(
                8, "little")
        page.write(self.buffer)
        entry = ctypes.CFUNCTYPE(ctypes.c_int64)(
            address + self.entry.offset)
        try:
            return entry()
        finally:
            page.close()

    # -- statements ----------------------------------------------------
    def _statements(self, items, code):
        for item in items:
            self._statement(item, code)

    def _statement(self, node, code):
        if isinstance(node, ast.LetStmt):
            kind = node.type_ann or static_type(
                node.value, lambda name: self.type_of_local(code, name),
                self.returns.get) or "int"
            if kind not in ("int", "bool"):
                self.unsupported("the type '%s' of '%s'"
                                 % (kind, node.name), node)
            slot = code.slot()
            self.expr(node.value, code)
            code.mov_slot_rax(slot)
            code.bind(node.name, slot)
            self.local_types[(id(code), node.name)] = kind
        elif isinstance(node, ast.AssignStmt):
            if not isinstance(node.target, ast.Identifier):
                self.unsupported("assignment to %s"
                                 % type(node.target).__name__, node)
            slot = code.lookup(node.target.name)
            if slot is None:
                self.unsupported("assignment to the global '%s'"
                                 % node.target.name, node)
            self.expr(node.value, code)
            code.mov_slot_rax(slot)
        elif isinstance(node, ast.OpAssignStmt):
            self._op_assign(node, code)
        elif isinstance(node, ast.IncDecStmt):
            if not isinstance(node.target, ast.Identifier):
                self.unsupported("increment of %s"
                                 % type(node.target).__name__, node)
            slot = code.lookup(node.target.name)
            if slot is None:
                self.unsupported("increment of the global '%s'"
                                 % node.target.name, node)
            code.mov_rax_slot(slot)
            code.emit(INC_RAX if node.op in ("++", "+=") else DEC_RAX)
            code.mov_slot_rax(slot)
        elif isinstance(node, ast.ExprStmt):
            self.expr(node.expr, code)
        elif isinstance(node, ast.Block):
            code.scope.append({})
            self._statements(node.statements, code)
            code.scope.pop()
        elif isinstance(node, ast.IfStmt):
            self._if(node, code)
        elif isinstance(node, ast.WhileStmt):
            self._while(node, code)
        elif isinstance(node, ast.ForStmt):
            self._for(node, code)
        elif isinstance(node, ast.ReturnStmt):
            if node.value is None:
                code.emit(bytes([0x48, 0x31, 0xC0]))
            else:
                self.expr(node.value, code)
            code.emit(LEAVE, RET)
        elif isinstance(node, ast.BreakStmt):
            self._jump_loop(node, code, "break")
        elif isinstance(node, ast.ContinueStmt):
            self._jump_loop(node, code, "continue")
        elif isinstance(node, ast.AssertStmt):
            self.unsupported("an 'assert' statement", node)
        else:
            self.unsupported("the statement '%s'" % type(node).__name__, node)

    def _op_assign(self, node, code):
        if not isinstance(node.target, ast.Identifier):
            self.unsupported("compound assignment to %s"
                             % type(node.target).__name__, node)
        slot = code.lookup(node.target.name)
        if slot is None:
            self.unsupported("compound assignment to the global '%s'"
                             % node.target.name, node)
        code.mov_rax_slot(slot)
        temp = code.slot()
        code.mov_slot_rax(temp)
        self.expr(node.value, code)
        code.emit(MOV_RBX_RAX)
        code.mov_rax_slot(temp)
        self._binary_op(node.op, code, node)
        code.mov_slot_rax(slot)

    def _if(self, node, code):
        otherwise = code.new_label("else")
        done = code.new_label("endif")
        self.expr(node.condition, code)
        code.emit(TEST_RAX)
        code.jump(JZ, otherwise)
        self._statement(node.then_branch, code)
        code.jump(JMP, done)
        code.place(otherwise)
        if node.else_branch is not None:
            self._statement(node.else_branch, code)
        code.place(done)

    def _while(self, node, code):
        start = code.new_label("while")
        done = code.new_label("endwhile")
        code.place(start)
        self.expr(node.condition, code)
        code.emit(TEST_RAX)
        code.jump(JZ, done)
        code.loops.append({"break": done, "continue": start,
                           "label": node.label})
        code.scope.append({})
        self._statement(node.body, code)
        code.scope.pop()
        code.loops.pop()
        code.jump(JMP, start)
        code.place(done)
        if node.orelse is not None:
            self._statement(node.orelse, code)

    def _for(self, node, code):
        if len(node.targets) != 1:
            self.unsupported("a loop over %d names" % len(node.targets), node)
        args = range_call(node.iterable)
        if args is None:
            self.unsupported("a loop over a container", node)
        if not 1 <= len(args) <= 3:
            self.unsupported("range() with %d arguments" % len(args), node)

        if len(args) == 1:
            start_node = ast.Literal(0, node.line, node.col)
            stop_node, step_node = args[0], ast.Literal(1, node.line, node.col)
        elif len(args) == 2:
            start_node, stop_node = args[0], args[1]
            step_node = ast.Literal(1, node.line, node.col)
        else:
            start_node, stop_node, step_node = args

        code.scope.append({})
        index = code.slot()
        self.expr(start_node, code)
        code.mov_slot_rax(index)
        stop = code.slot()
        self.expr(stop_node, code)
        code.mov_slot_rax(stop)
        step = code.slot()
        self.expr(step_node, code)
        code.mov_slot_rax(step)
        code.bind(node.targets[0], index)
        self.local_types[(id(code), node.targets[0])] = "int"

        top = code.new_label("for")
        done = code.new_label("endfor")
        negative = code.new_label("stepneg")
        condition_done = code.new_label("conddone")
        code.place(top)
        code.mov_rax_slot(step)
        code.emit(TEST_RAX)
        code.jump(JLE, negative)
        code.mov_rax_slot(index)
        code.cmp_rax_slot(stop)
        code.emit(bytes([0x0F, 0x9C, 0xC0]))          # setl al
        code.emit(MOVZX_RAX_AL)
        code.jump(JMP, condition_done)
        code.place(negative)
        code.mov_rax_slot(index)
        code.cmp_rax_slot(stop)
        code.emit(bytes([0x0F, 0x9F, 0xC0]))          # setg al
        code.emit(MOVZX_RAX_AL)
        code.place(condition_done)
        code.emit(TEST_RAX)
        code.jump(JZ, done)
        code.loops.append({"break": done, "continue": top,
                           "label": node.label})
        code.scope.append({})
        self._statement(node.body, code)
        code.scope.pop()
        code.loops.pop()
        code.mov_rax_slot(index)
        code.mov_rbx_slot(step)
        code.emit(ADD_RAX_RBX)
        code.mov_slot_rax(index)
        code.jump(JMP, top)
        code.place(done)
        code.scope.pop()
        if node.orelse is not None:
            self._statement(node.orelse, code)

    def _jump_loop(self, node, code, kind):
        label = getattr(node, "label", None)
        for entry in reversed(code.loops):
            if label is None or entry["label"] == label:
                code.jump(JMP, entry[kind])
                return
        if label is None:
            self.unsupported("'%s' outside of a loop" % kind, node)
        self.unsupported("a '%s' of the loop '%s'" % (kind, label), node)

    # -- expressions ---------------------------------------------------
    def expr(self, node, code):
        if isinstance(node, ast.Literal):
            value = node.value
            if isinstance(value, bool):
                code.mov_rax_imm(1 if value else 0)
            elif isinstance(value, int):
                code.mov_rax_imm(value)
            elif isinstance(value, str):
                self.unsupported("a string outside print", node)
            elif value is None:
                self.unsupported("null", node)
            else:
                self.unsupported("the literal %r" % (value,), node)
        elif isinstance(node, ast.Identifier):
            slot = code.lookup(node.name)
            if slot is None:
                self.unsupported("the global '%s'" % node.name, node)
            code.mov_rax_slot(slot)
        elif isinstance(node, ast.Unary):
            self._unary(node, code)
        elif isinstance(node, ast.Binary):
            self._binary(node, code)
        elif isinstance(node, ast.Logical):
            self._logical(node, code)
        elif isinstance(node, ast.Call):
            self._call(node, code)
        else:
            self.unsupported("the expression '%s'" % type(node).__name__,
                             node)

    def _unary(self, node, code):
        if node.op == "-":
            self.expr(node.operand, code)
            code.emit(NEG_RAX)
        elif node.op in ("not", "!"):
            self.expr(node.operand, code)
            code.emit(TEST_RAX, SETNE_AL, MOVZX_RAX_AL)
            code.emit(bytes([0x48, 0x83, 0xF0, 0x01]))   # xor rax, 1
        elif node.op == "+":
            self.expr(node.operand, code)
        else:
            self.unsupported("the unary operator '%s'" % node.op, node)

    def _binary(self, node, code):
        self.expr(node.left, code)
        temp = code.slot()
        code.mov_slot_rax(temp)
        self.expr(node.right, code)
        code.emit(MOV_RBX_RAX)
        code.mov_rax_slot(temp)
        self._binary_op(node.op, code, node)

    def _binary_op(self, op, code, node):
        if op in SETCC:
            code.emit(CMP_RAX_RBX)
            code.emit(bytes([0x0F, SETCC[op], 0xC0]))
            code.emit(MOVZX_RAX_AL)
        elif op == "+":
            code.emit(ADD_RAX_RBX)
        elif op == "-":
            code.emit(SUB_RAX_RBX)
        elif op == "*":
            code.emit(IMUL_RAX_RBX)
        elif op in ("//", "%"):
            code.emit(CQO, IDIV_RBX)
            if op == "%":
                code.emit(bytes([0x48, 0x89, 0xD0]))      # mov rax, rdx
            done = code.new_label("div")
            code.emit(TEST_RDX)
            code.jump(JZ, done)
            code.emit(MOV_RCX_RDX, XOR_RCX_RBX, TEST_RCX)
            code.jump(JNS, done)
            code.emit(DEC_RAX if op == "//" else ADD_RAX_RBX)
            code.place(done)
        elif op == "&":
            code.emit(AND_RAX_RBX)
        elif op == "|":
            code.emit(OR_RAX_RBX)
        elif op == "^":
            code.emit(XOR_RAX_RBX)
        elif op in ("<<", ">>"):
            code.emit(MOV_RCX_RBX)
            code.emit(SHL_RAX_CL if op == "<<" else SAR_RAX_CL)
        else:
            self.unsupported("the operator '%s'" % op, node)

    def _logical(self, node, code):
        """`a and b` is a when a is false, and b otherwise.

        The operand, not a truth value, is the answer: `3 and 5` is 5 and
        `2 or 7` is 2.  The left operand is already in rax when the jump
        is taken, so the jump alone is the answer.
        """
        done = code.new_label("bool")
        self.expr(node.left, code)
        code.emit(TEST_RAX)
        code.jump(JZ if node.op in ("and", "&&") else JNZ, done)
        self.expr(node.right, code)
        code.place(done)

    def _call(self, node, code):
        if not isinstance(node.callee, ast.Identifier):
            self.unsupported("a call of %s" % type(node.callee).__name__, node)
        name = node.callee.name
        if node.kwargs:
            self.unsupported("keyword arguments", node)
        if name == "print":
            return self._print(node, code)
        if name not in self.functions:
            self.unsupported("the builtin '%s'" % name, node)
        if len(node.args) > 6:
            self.unsupported("a call with %d arguments" % len(node.args), node)
        slots = []
        for arg in node.args:
            self.expr(arg, code)
            slot = code.slot()
            code.mov_slot_rax(slot)
            slots.append(slot)
        for index, slot in enumerate(slots):
            code.emit(bytes(ARG_REGISTERS[index]))
            code.imm32(-8 * (slot + 1))
        code.call_name(name)

    def _print(self, node, code):
        if len(node.args) != 1:
            self.unsupported("print with %d arguments" % len(node.args), node)
        arg = node.args[0]
        if isinstance(arg, ast.Literal) and isinstance(arg.value, str):
            text = arg.value
            address = self._callback("print_str")
            self.expr(ast.Literal(len(text.encode("utf-8")),
                                  node.line, node.col), code)
            code.emit(bytes([0x48, 0x89, 0xC6]))          # mov rsi, rax
            code.mov_rax_imm(0)
            position = len(code.data) - 8
            code.strings.append((position, text))
            code.emit(bytes([0x48, 0x89, 0xC7]))          # mov rdi, rax
            code.mov_rax_imm(address)
            code.emit(CALL_RAX)
            code.emit(bytes([0x48, 0x31, 0xC0]))
            return
        kind = static_type(arg, lambda name: self.type_of_local(code, name),
                           self.returns.get)
        if kind not in ("int", "bool"):
            self.unsupported("print of a value that is not an integer, a"
                             " boolean or a string literal", node)
        self.expr(arg, code)
        code.emit(bytes([0x48, 0x89, 0xC7]))              # mov rdi, rax
        address = self._callback("print_bool" if kind == "bool"
                                 else "print_i64")
        code.mov_rax_imm(address)
        code.emit(CALL_RAX)
        code.emit(bytes([0x48, 0x31, 0xC0]))

    def _callback(self, name):
        if name in self.callbacks:
            return self.callbacks[name]
        if name == "print_i64":
            def show(value):
                print(value)
            callback = ctypes.CFUNCTYPE(None, ctypes.c_int64)(show)
        elif name == "print_bool":
            def show(value):
                print("true" if value else "false")
            callback = ctypes.CFUNCTYPE(None, ctypes.c_int64)(show)
        else:
            def show(pointer, length):
                raw = ctypes.string_at(pointer, length)
                print(raw.decode("utf-8"))
            callback = ctypes.CFUNCTYPE(None, ctypes.c_int64,
                                        ctypes.c_int64)(show)
        self.keepalive.append(callback)
        address = ctypes.cast(callback, ctypes.c_void_p).value
        self.callbacks[name] = address
        return address


def _patch_imm64(data, position, value):
    """Write an absolute address into the `movabs rax, imm64` at position."""
    return data[:position] + (value & 0xFFFFFFFFFFFFFFFF).to_bytes(
        8, "little") + data[position + 8:]


def run_program(program, filename="<jit>"):
    """Compile the program and run its top level on the machine code."""
    return Jit(program, filename).compile().run()
