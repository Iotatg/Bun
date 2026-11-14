"""Bun's own WebAssembly virtual machine.

This is the engine behind `bun --engine wasm`.  It reads the binary
format (not a text format and not a host library): it decodes the type,
import, function, memory, export, code and data sections, checks the
structure it needs, and runs the instructions.  A module that uses an
instruction the machine does not know is refused with the opcode, not
guessed at.

The machine runs the subset that `bun/wasm.py` emits, and a little more
(memory load and store, `select`, `br_table` is not included).  It is a
real interpreter for that subset, and its limits are written down in
`docs/reference/engines.md`.
"""

import struct

from .errors import BunRuntimeError

MAGIC = b"\x00asm\x01\x00\x00\x00"

# Value types.
I32 = 0x7F
I64 = 0x7E
F32 = 0x7D
F64 = 0x7C

# Control instructions.
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
SELECT = 0x1B
LOCAL_GET = 0x20
LOCAL_SET = 0x21
LOCAL_TEE = 0x22
GLOBAL_GET = 0x23
GLOBAL_SET = 0x24
I32_LOAD = 0x28
I64_LOAD = 0x29
I32_STORE = 0x36
I64_STORE = 0x37
MEMORY_SIZE = 0x3F
MEMORY_GROW = 0x40
I32_CONST = 0x41
I64_CONST = 0x42
I32_EQZ = 0x45
I32_EQ = 0x46
I32_NE = 0x47
I32_LT_S = 0x48
I32_GT_S = 0x4A
I32_LE_S = 0x4C
I32_GE_S = 0x4E
I32_ADD = 0x6A
I32_SUB = 0x6B
I32_MUL = 0x6C
I32_AND = 0x71
I32_OR = 0x72
I32_XOR = 0x73
I64_EQZ = 0x50
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
I64_SHR_U = 0x88
I32_WRAP_I64 = 0xA7
I64_EXTEND_I32_S = 0xAC
I64_EXTEND_I32_U = 0xAD

MASK64 = (1 << 64) - 1


class WasmError(BunRuntimeError):
    pass


class WasmTrap(WasmError):
    pass


def _uleb(data, index):
    result = 0
    shift = 0
    while True:
        if index >= len(data):
            raise WasmError("the module ends inside a number")
        byte = data[index]
        index += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, index
        shift += 7
        if shift > 63:
            raise WasmError("a number of the module is too long")


def _sleb(data, index):
    result = 0
    shift = 0
    while True:
        if index >= len(data):
            raise WasmError("the module ends inside a number")
        byte = data[index]
        index += 1
        result |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            if byte & 0x40:
                result -= 1 << shift
            return result, index


def _name(data, index):
    length, index = _uleb(data, index)
    end = index + length
    if end > len(data):
        raise WasmError("the module ends inside a name")
    try:
        return data[index:end].decode("utf-8"), end
    except UnicodeDecodeError:
        raise WasmError("a name of the module is not valid UTF-8")


def _vector(data, index, reader):
    count, index = _uleb(data, index)
    items = []
    for _ in range(count):
        item, index = reader(data, index)
        items.append(item)
    return items, index


def _valtype(data, index):
    if index >= len(data):
        raise WasmError("the module ends inside a type")
    return data[index], index + 1


def _limits(data, index):
    flag, index = _uleb(data, index)
    minimum, index = _uleb(data, index)
    maximum = None
    if flag & 1:
        maximum, index = _uleb(data, index)
    return (minimum, maximum), index


class Function:
    __slots__ = ("type_index", "locals", "body", "code", "ends", "elses")

    def __init__(self, type_index, locals_, body):
        self.type_index = type_index
        self.locals = locals_
        self.body = body
        self.code = []
        self.ends = {}
        self.elses = {}


class Module:
    def __init__(self):
        self.types = []
        self.imports = []
        self.functions = []
        self.exports = {}
        self.memory = bytearray()
        self.data = []


def decode(data):
    """Decode a binary module, or say exactly what is wrong with it."""
    if len(data) < 8 or not data.startswith(MAGIC):
        raise WasmError("not a WebAssembly 1.0 binary module"
                        " (the magic or the version is wrong)")
    module = Module()
    index = 8
    while index < len(data):
        section_id = data[index]
        index += 1
        size, index = _uleb(data, index)
        end = index + size
        if end > len(data):
            raise WasmError("section %d runs past the end of the module"
                            % section_id)
        payload = data[index:end]
        index = end
        if section_id == 1:
            _decode_types(module, payload)
        elif section_id == 2:
            _decode_imports(module, payload)
        elif section_id == 3:
            _decode_functions(module, payload)
        elif section_id == 5:
            _decode_memory(module, payload)
        elif section_id == 7:
            _decode_exports(module, payload)
        elif section_id == 10:
            _decode_code(module, payload)
        elif section_id == 11:
            _decode_data(module, payload)
        elif section_id == 0:
            pass
        else:
            raise WasmError("unsupported section %d" % section_id)
    _check_module(module)
    return module


def _decode_types(module, payload):
    def read_type(data, index):
        if index >= len(data) or data[index] != 0x60:
            raise WasmError("a type is not a function type")
        params, index = _vector(data, index + 1, _valtype)
        results, index = _vector(data, index, _valtype)
        return (params, results), index
    module.types, _ = _vector(payload, 0, read_type)


def _decode_imports(module, payload):
    def read_import(data, index):
        name, index = _name(data, index)
        field, index = _name(data, index)
        if index >= len(data):
            raise WasmError("the module ends inside an import")
        kind = data[index]
        index += 1
        if kind == 0x00:
            type_index, index = _uleb(data, index)
            return (name, field, kind, type_index), index
        if kind == 0x01:
            _, index = _valtype(data, index)
            _, index = _limits(data, index)
            return (name, field, kind, None), index
        if kind == 0x02:
            limits, index = _limits(data, index)
            return (name, field, kind, limits), index
        if kind == 0x03:
            _, index = _valtype(data, index)
            if index < len(data) and data[index] == 0x01:
                index += 1
            return (name, field, kind, None), index
        raise WasmError("import of kind %d" % kind)
    module.imports, _ = _vector(payload, 0, read_import)


def _decode_functions(module, payload):
    def read_index(data, index):
        return _uleb(data, index)
    module.function_types, _ = _vector(payload, 0, read_index)


def _decode_memory(module, payload):
    limits, _ = _vector(payload, 0, _limits)
    if not limits:
        return
    pages = limits[0][0]
    module.memory = bytearray(pages * 65536)


def _decode_exports(module, payload):
    def read_export(data, index):
        name, index = _name(data, index)
        if index >= len(data):
            raise WasmError("the module ends inside an export")
        kind = data[index]
        index += 1
        entry, index = _uleb(data, index)
        return (name, kind, entry), index
    exports, _ = _vector(payload, 0, read_export)
    for name, kind, entry in exports:
        module.exports[name] = (kind, entry)


def _decode_code(module, payload):
    def read_body(data, index):
        size, index = _uleb(data, index)
        end = index + size
        if end > len(data):
            raise WasmError("a function body runs past the end of its section")
        body = data[index:end]
        groups, position = _uleb(body, 0)
        locals_ = []
        for _ in range(groups):
            count, position = _uleb(body, position)
            if position >= len(body):
                raise WasmError("a body ends inside its locals")
            kind = body[position]
            position += 1
            if kind not in (I32, I64, F32, F64):
                raise WasmError("a local has the unknown type %d" % kind)
            locals_.extend([kind] * count)
        return Function(0, locals_, body[position:]), end
    bodies, _ = _vector(payload, 0, read_body)
    if len(bodies) != len(module.function_types):
        raise WasmError("the code section has %d bodies for %d functions"
                        % (len(bodies), len(module.function_types)))
    for type_index, function in zip(module.function_types, bodies):
        function.type_index = type_index
        _decode_body(function)
        module.functions.append(function)


def _decode_data(module, payload):
    def read_segment(data, index):
        flags, index = _uleb(data, index)
        if flags != 0:
            raise WasmError("data segment of kind %d" % flags)
        if index >= len(data) or data[index] not in (I32_CONST, I64_CONST):
            raise WasmError("a data segment has no constant offset")
        offset, index = _sleb(data, index + 1)
        if index >= len(data) or data[index] != END:
            raise WasmError("a data segment has no end of its offset")
        index += 1
        length, index = _uleb(data, index)
        end = index + length
        if end > len(data):
            raise WasmError("a data segment runs past the end of its section")
        return (offset, data[index:end]), end
    module.data, _ = _vector(payload, 0, read_segment)


_IMMEDIATES = {
    BLOCK: "block", LOOP: "block", IF: "block",
    BR: "label", BR_IF: "label", CALL: "func",
    LOCAL_GET: "local", LOCAL_SET: "local", LOCAL_TEE: "local",
    GLOBAL_GET: "global", GLOBAL_SET: "global",
    I32_CONST: "i32", I64_CONST: "i64",
    I32_LOAD: "mem", I64_LOAD: "mem", I32_STORE: "mem", I64_STORE: "mem",
    MEMORY_SIZE: "byte", MEMORY_GROW: "byte",
}


def _decode_body(function):
    data = function.body
    index = 0
    code = function.code
    while index < len(data):
        op = data[index]
        index += 1
        kind = _IMMEDIATES.get(op)
        if kind == "block":
            if index >= len(data):
                raise WasmError("the body ends inside a block")
            code.append((op, data[index]))
            index += 1
        elif kind in ("label", "func", "local", "global"):
            value, index = _uleb(data, index)
            code.append((op, value))
        elif kind == "i32":
            value, index = _sleb(data, index)
            code.append((op, value))
        elif kind == "i64":
            value, index = _sleb(data, index)
            code.append((op, value))
        elif kind == "mem":
            align, index = _uleb(data, index)
            offset, index = _uleb(data, index)
            code.append((op, (align, offset)))
        elif kind == "byte":
            code.append((op, data[index]))
            index += 1
        else:
            code.append((op, None))
    _link(function)


def _link(function):
    stack = []
    for index, (op, _) in enumerate(function.code):
        if op in (BLOCK, LOOP, IF):
            stack.append(index)
        elif op == ELSE:
            if not stack:
                raise WasmError("'else' without 'if'")
            function.elses[stack[-1]] = index
        elif op == END:
            if stack:
                function.ends[stack.pop()] = index


def _check_module(module):
    total = len(module.functions) + _import_count(module)
    for name, (kind, entry) in module.exports.items():
        if kind == 0x02:
            continue
        if kind != 0x00:
            raise WasmError("the export '%s' is neither a function nor a"
                            " memory" % name)
        if entry >= total:
            raise WasmError("the export '%s' names no function" % name)
    for function in module.functions:
        if function.type_index >= len(module.types):
            raise WasmError("a function has no type")


def _import_count(module):
    return sum(1 for item in module.imports if item[2] == 0x00)


class _Control:
    __slots__ = ("kind", "start", "end", "height", "results")

    def __init__(self, kind, start, end, height, results=0):
        self.kind = kind
        self.start = start
        self.end = end
        self.height = height
        self.results = results


class Machine:
    """A machine for one module."""

    MAX_DEPTH = 400

    def __init__(self, module, host=None):
        self.module = module
        self.host = host or Host()
        self.host.machine = self
        self.memory = module.memory or bytearray(65536)
        for offset, chunk in module.data:
            self.memory[offset:offset + len(chunk)] = chunk
        self.depth = 0
        self.imports = [item for item in module.imports if item[2] == 0x00]

    # -- entry points --------------------------------------------------
    def function_index(self, name):
        kind, index = self.module.exports.get(name, (None, None))
        if kind != 0x00:
            raise WasmError("the module exports no function '%s'" % name)
        return index

    def call_export(self, name, args=None):
        index = self.function_index(name)
        signature = self.module.types[
            self._function(index).type_index]
        params, _ = signature
        args = list(args or [])
        if len(args) != len(params):
            raise WasmError("'%s' takes %d arguments" % (name, len(params)))
        return self._invoke(index, args)

    def call(self, name, *args):
        return self.call_export(name, list(args))

    # -- the machine ---------------------------------------------------
    def _function(self, index):
        imports = _import_count(self.module)
        if index < imports:
            raise WasmError("the import %d is not a Bun function" % index)
        return self.module.functions[index - imports]

    def _invoke(self, index, args):
        imports = _import_count(self.module)
        if index < imports:
            return self._call_import(index, args)
        function = self.module.functions[index - imports]
        if self.depth >= self.MAX_DEPTH:
            raise WasmTrap("call stack exhausted at depth %d"
                           % self.MAX_DEPTH)
        self.depth += 1
        try:
            return self._run(function, args)
        finally:
            self.depth -= 1

    def _call_import(self, index, args):
        name = self.imports[index][1]
        handler = getattr(self.host, name, None)
        if handler is None:
            raise WasmError("the host has no import '%s'" % name)
        return handler(*args)

    def _run(self, function, args):
        stack = list(args)
        locals_ = [None] * (len(args) + len(function.locals))
        for position, value in enumerate(args):
            locals_[position] = value
        for position, kind in enumerate(function.locals):
            locals_[len(args) + position] = 0
        control = []
        code = function.code
        pc = 0
        limit = len(code)
        while pc < limit:
            op, arg = code[pc]
            if op == I64_CONST or op == I32_CONST:
                stack.append(arg)
            elif op == LOCAL_GET:
                stack.append(locals_[arg])
            elif op == LOCAL_SET:
                locals_[arg] = stack.pop()
            elif op == LOCAL_TEE:
                locals_[arg] = stack[-1]
            elif op == I64_ADD:
                right = stack.pop()
                stack[-1] = _wrap64(stack[-1] + right)
            elif op == I64_SUB:
                right = stack.pop()
                stack[-1] = _wrap64(stack[-1] - right)
            elif op == I64_MUL:
                right = stack.pop()
                stack[-1] = _wrap64(stack[-1] * right)
            elif op == I64_DIV_S:
                right = stack.pop()
                if right == 0:
                    raise WasmTrap("integer divide by zero")
                stack[-1] = _trunc_div(stack[-1], right)
            elif op == I64_REM_S:
                right = stack.pop()
                if right == 0:
                    raise WasmTrap("integer divide by zero")
                stack[-1] = _trunc_rem(stack[-1], right)
            elif op == I64_AND:
                stack[-1] &= stack.pop()
            elif op == I64_OR:
                stack[-1] |= stack.pop()
            elif op == I64_XOR:
                stack[-1] ^= stack.pop()
            elif op == I64_SHL:
                count = stack.pop() & 63
                stack[-1] = _wrap64(stack[-1] << count)
            elif op == I64_SHR_S:
                count = stack.pop() & 63
                stack[-1] = stack[-1] >> count
            elif op == I64_SHR_U:
                count = stack.pop() & 63
                stack[-1] = (stack[-1] & MASK64) >> count
            elif op in _COMPARE:
                right = stack.pop()
                left = stack[-1]
                stack[-1] = 1 if _COMPARE[op](left, right) else 0
            elif op == I64_EQZ:
                stack[-1] = 1 if stack[-1] == 0 else 0
            elif op == I32_EQZ:
                stack[-1] = 1 if stack[-1] == 0 else 0
            elif op in _COMPARE32:
                right = stack.pop() & 0xFFFFFFFF
                left = stack[-1] & 0xFFFFFFFF
                stack[-1] = 1 if _COMPARE32[op](left, right) else 0
            elif op == I32_ADD:
                stack[-1] = _wrap32(stack[-1] + stack.pop())
            elif op == I32_SUB:
                stack[-1] = _wrap32(stack[-1] - stack.pop())
            elif op == I32_MUL:
                stack[-1] = _wrap32(stack[-1] * stack.pop())
            elif op == I32_AND:
                stack[-1] &= stack.pop()
            elif op == I32_OR:
                stack[-1] |= stack.pop()
            elif op == I32_XOR:
                stack[-1] ^= stack.pop()
            elif op == I64_EXTEND_I32_U:
                stack[-1] = stack[-1] & 0xFFFFFFFF
            elif op == I64_EXTEND_I32_S:
                value = stack[-1] & 0xFFFFFFFF
                stack[-1] = value - (1 << 32) if value & 0x80000000 else value
            elif op == I32_WRAP_I64:
                stack[-1] = _wrap32(stack[-1])
            elif op == DROP:
                stack.pop()
            elif op == SELECT:
                condition = stack.pop()
                right = stack.pop()
                left = stack.pop()
                stack.append(left if condition else right)
            elif op == NOP:
                pass
            elif op == BLOCK or op == LOOP:
                control.append(_Control("block" if op == BLOCK else "loop",
                                        pc, function.ends[pc], len(stack),
                                        1 if arg != 0x40 else 0))
            elif op == IF:
                condition = stack.pop()
                results = 1 if arg != 0x40 else 0
                if condition:
                    control.append(_Control("if", pc, function.ends[pc],
                                            len(stack), results))
                elif pc in function.elses:
                    control.append(_Control("if", function.elses[pc],
                                            function.ends[pc], len(stack),
                                            results))
                    pc = function.elses[pc]
                else:
                    pc = function.ends[pc]
            elif op == ELSE:
                frame = control.pop()
                _unwind(stack, frame)
                pc = frame.end
            elif op == END:
                if control:
                    frame = control.pop()
                    _unwind(stack, frame)
            elif op == BR or op == BR_IF:
                if op == BR_IF:
                    condition = stack.pop()
                    if not condition:
                        pc += 1
                        continue
                target = control[-1 - arg]
                _unwind(stack, target)
                for _ in range(arg + 1):
                    control.pop()
                if target.kind == "loop":
                    control.append(target)
                    pc = target.start + 1
                    continue
                pc = target.end + 1
                continue
            elif op == RETURN:
                return stack[-1] if stack else 0
            elif op == CALL:
                imports = _import_count(self.module)
                if arg < imports:
                    signature = self.module.types[self.imports[arg][3]]
                    count = len(signature[0])
                    call_args = stack[-count:] if count else []
                    if count:
                        del stack[-count:]
                    stack.append(self._call_import(arg, call_args) or 0)
                else:
                    callee = self.module.functions[arg - imports]
                    signature = self.module.types[callee.type_index]
                    count = len(signature[0])
                    call_args = stack[-count:] if count else []
                    if count:
                        del stack[-count:]
                    stack.append(self._invoke(arg, call_args))
            elif op == I64_LOAD or op == I32_LOAD:
                _, offset = arg
                address = stack.pop() + offset
                size = 8 if op == I64_LOAD else 4
                stack.append(int.from_bytes(self.memory[address:address + size],
                                            "little"))
            elif op == I64_STORE or op == I32_STORE:
                _, offset = arg
                value = stack.pop()
                address = stack.pop() + offset
                size = 8 if op == I64_STORE else 4
                self.memory[address:address + size] = (
                    value & ((1 << (size * 8)) - 1)).to_bytes(size, "little")
            elif op == MEMORY_SIZE:
                stack.append(len(self.memory) // 65536)
            elif op == MEMORY_GROW:
                pages = stack.pop()
                stack.append(self._grow(pages))
            elif op == UNREACHABLE:
                raise WasmTrap("unreachable executed")
            else:
                raise WasmError("unknown instruction 0x%02X" % op)
            pc += 1
        return stack[-1] if stack else 0

    def _grow(self, pages):
        try:
            self.memory.extend(bytes(pages * 65536))
        except (MemoryError, OverflowError):
            return -1
        return len(self.memory) // 65536 - pages


def _unwind(stack, frame):
    """Drop the operands of a block, keeping the results it produced."""
    if frame.results:
        values = stack[len(stack) - frame.results:]
        del stack[frame.height:]
        stack.extend(values)
    else:
        del stack[frame.height:]


def _wrap64(value):
    value &= MASK64
    return value - (1 << 64) if value & (1 << 63) else value


def _wrap32(value):
    value &= 0xFFFFFFFF
    return value - (1 << 32) if value & 0x80000000 else value


def _trunc_div(left, right):
    quotient = abs(left) // abs(right)
    if (left < 0) != (right < 0):
        quotient = -quotient
    return _wrap64(quotient)


def _trunc_rem(left, right):
    return _wrap64(left - _trunc_div(left, right) * right)


_COMPARE32 = {
    I32_EQ: lambda a, b: a == b,
    I32_NE: lambda a, b: a != b,
    I32_LT_S: lambda a, b: _signed32(a) < _signed32(b),
    I32_GT_S: lambda a, b: _signed32(a) > _signed32(b),
    I32_LE_S: lambda a, b: _signed32(a) <= _signed32(b),
    I32_GE_S: lambda a, b: _signed32(a) >= _signed32(b),
}


def _signed32(value):
    return value - (1 << 32) if value & 0x80000000 else value


_COMPARE = {
    0x51: lambda a, b: a == b,          # i64.eq
    0x52: lambda a, b: a != b,          # i64.ne
    0x53: lambda a, b: a < b,           # i64.lt_s
    0x54: lambda a, b: (a & MASK64) < (b & MASK64),
    0x55: lambda a, b: a > b,           # i64.gt_s
    0x56: lambda a, b: (a & MASK64) > (b & MASK64),
    0x57: lambda a, b: a <= b,          # i64.le_s
    0x58: lambda a, b: (a & MASK64) <= (b & MASK64),
    0x59: lambda a, b: a >= b,          # i64.ge_s
    0x5A: lambda a, b: (a & MASK64) >= (b & MASK64),
}


class Host:
    """The host functions a module may import: `env.print_*`."""

    def print_i64(self, value):
        print(value)
        return None

    def print_bool(self, value):
        print("true" if value else "false")
        return None

    def print_str(self, offset, length):
        print(self._text(offset, length))
        return None

    def _text(self, offset, length):
        machine = getattr(self, "machine", None)
        memory = machine.memory if machine else b""
        return bytes(memory[offset:offset + length]).decode("utf-8")


def run_module(module, entry="main", args=None):
    """Run the exported function `entry` of a decoded module."""
    host = Host()
    machine = Machine(module, host)
    host.machine = machine
    return machine.call_export(entry, args)
