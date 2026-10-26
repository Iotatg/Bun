"""The register code of Bun.

The stack VM is the reference semantics of the language.  The register
code is a second shape of the same program: the values live in a register
file instead of on an operand stack, and every instruction names its
operands.

An instruction is a tuple of four cells::

    (opcode, a, b, c)

The meaning of the cells depends on the opcode, and every opcode says what
its cells mean.  A cell holds an integer, or the value ``0`` when the
opcode does not use it.  The values that are not integers live in the
constant pool of the code object, and an instruction names a pool entry by
its index.

The register file of a frame holds the values of the expression that is
being evaluated.  The slot ``i`` of the expression is the register ``i``
while ``i`` is below the size of the file; the slots above that size live
in the overflow stack of the frame.  The registerizer knows the depth of
the expression at every instruction, so the code is exact.

The register code is verified before it runs: the verifier proves that the
registers are inside the file, that the jumps land on an instruction of
the same function, and that the depth of the expression is the same on
every path that reaches an instruction.
"""

# The number of registers of a frame.  The overflow stack takes the
# values that do not fit.
REGISTER_COUNT = 64

# The values.
CONST = "CONST"
LOAD_NAME = "LOAD_NAME"
STORE_NAME = "STORE_NAME"
DEFINE_NAME = "DEFINE_NAME"
RECORD_EXPORT = "RECORD_EXPORT"

# The shape of the expression.
POP = "POP"
DUP = "DUP"

# The arithmetic.  Every operator has its own opcode, so the interpreter
# does not look up the operator in a table.
ADD = "ADD"
SUB = "SUB"
MUL = "MUL"
DIV = "DIV"
MOD = "MOD"
POW = "POW"
EQ = "EQ"
NE = "NE"
LT = "LT"
LE = "LE"
GT = "GT"
GE = "GE"
BAND = "BAND"
BOR = "BOR"
BXOR = "BXOR"
SHL = "SHL"
SHR = "SHR"
NEG = "NEG"
INVERT = "INVERT"
NOT = "NOT"

# The operators of the arithmetic, and the opcode of each one.
BINARY_OPCODES = {
    "+": ADD,
    "-": SUB,
    "*": MUL,
    "/": DIV,
    "%": MOD,
    "**": POW,
    "==": EQ,
    "!=": NE,
    "<": LT,
    "<=": LE,
    ">": GT,
    ">=": GE,
    "&": BAND,
    "|": BOR,
    "^": BXOR,
    "<<": SHL,
    ">>": SHR,
}

UNARY_OPCODES = {
    "-": NEG,
    "~": INVERT,
    "!": NOT,
}

# The containers.
BUILD_LIST = "BUILD_LIST"
BUILD_DICT = "BUILD_DICT"
BUILD_STRING = "BUILD_STRING"
LIST_APPEND = "LIST_APPEND"
DICT_SET = "DICT_SET"
INDEX = "INDEX"
STORE_INDEX = "STORE_INDEX"
SLICE = "SLICE"
STORE_SLICE = "STORE_SLICE"
UNPACK_PLAN = "UNPACK_PLAN"
FORMAT = "FORMAT"

# The calls.
MAKE_FUNCTION = "MAKE_FUNCTION"
CALL = "CALL"
METHOD_CALL = "METHOD_CALL"
RETURN = "RETURN"
HALT = "HALT"

# The control.
JUMP = "JUMP"
JUMP_IF_FALSE = "JUMP_IF_FALSE"
JUMP_IF_TRUE = "JUMP_IF_TRUE"

# The scopes.
ENTER_SCOPE = "ENTER_SCOPE"
EXIT_SCOPE = "EXIT_SCOPE"

# The loops.
FOR_SETUP = "FOR_SETUP"
FOR_NEXT = "FOR_NEXT"
FOR_POP = "FOR_POP"

# The modules.
IMPORT = "IMPORT"

# The errors.
TRY = "TRY"
TRY_FINALLY = "TRY_FINALLY"
END_TRY = "END_TRY"
FINALLY_END = "FINALLY_END"
THROW = "THROW"
ASSERT = "ASSERT"

# The "del" statement.
DEL = "DEL"
DEL_INDEX = "DEL_INDEX"

# The "yield" statement.
YIELD = "YIELD"

# The "with" statement.
WITH_ENTER = "WITH_ENTER"
WITH_POP_TARGET = "WITH_POP_TARGET"
PROTOCOL_GET = "PROTOCOL_GET"
PENDING_ERROR = "PENDING_ERROR"
CLEAR_ERROR = "CLEAR_ERROR"
WITH_DEPTH = "WITH_DEPTH"
HAS_ERROR = "HAS_ERROR"

# The "scope" statement.
SCOPE_ENTER = "SCOPE_ENTER"
SCOPE_EXIT = "SCOPE_EXIT"

# The "match" statement.
MATCH_TEST = "MATCH_TEST"
MATCH_FAIL = "MATCH_FAIL"

# The structs.
MAKE_STRUCT = "MAKE_STRUCT"
GET_FIELD = "GET_FIELD"
SET_FIELD = "SET_FIELD"
REGISTER_IMPL = "REGISTER_IMPL"

# The result and the `?` operator.
UNWRAP_OR_RETURN = "UNWRAP_OR_RETURN"

# The superinstructions.  They do the work of two instructions in one
# dispatch, and the plan of the work lives in the constant pool.
LOAD_NAME2 = "LOAD_NAME2"
LOAD_NAME_CONST = "LOAD_NAME_CONST"
CONST_LOAD_NAME = "CONST_LOAD_NAME"


class Pool:
    """The constant pool of one code object.

    The pool holds the values that an instruction names by an index: the
    constants of the program, the names of the variables, the plans of the
    patterns and the code of the functions.  A value is in the pool once,
    so two instructions that name the same name share the entry.

    The key of a value carries its type, because `True` and `1` are the
    same value in Python and different values in Bun.
    """

    def __init__(self):
        self.values = []
        self._index = {}

    def add(self, value):
        try:
            key = (type(value).__name__, value)
            found = self._index.get(key)
        except TypeError:
            # A value that cannot be a key, a list for instance.
            self.values.append(value)
            return len(self.values) - 1
        if found is not None:
            return found
        self.values.append(value)
        index = len(self.values) - 1
        try:
            self._index[key] = index
        except TypeError:
            pass
        return index

    def get(self, index):
        return self.values[index]


def instruction(op, a=0, b=0, c=0):
    """Build one instruction of the register code."""
    return (op, a, b, c)


# The meaning of the cells of every instruction.  The cells are named by
# their kind:
#
#   "slot"    a slot of the expression
#   "pool"    an index of the constant pool
#   "count"   a number of slots
#   "target"  the index of an instruction
#   "flag"    a yes or a no
OPERANDS = {
    CONST: ("slot", "pool", None),
    LOAD_NAME: ("slot", "pool", None),
    STORE_NAME: ("slot", "pool", None),
    DEFINE_NAME: ("slot", "pool", "flag"),
    RECORD_EXPORT: ("pool", None, None),
    POP: ("slot", None, None),
    DUP: ("slot", None, None),
    ADD: ("slot", "slot", "slot"),
    SUB: ("slot", "slot", "slot"),
    MUL: ("slot", "slot", "slot"),
    DIV: ("slot", "slot", "slot"),
    MOD: ("slot", "slot", "slot"),
    POW: ("slot", "slot", "slot"),
    EQ: ("slot", "slot", "slot"),
    NE: ("slot", "slot", "slot"),
    LT: ("slot", "slot", "slot"),
    LE: ("slot", "slot", "slot"),
    GT: ("slot", "slot", "slot"),
    GE: ("slot", "slot", "slot"),
    BAND: ("slot", "slot", "slot"),
    BOR: ("slot", "slot", "slot"),
    BXOR: ("slot", "slot", "slot"),
    SHL: ("slot", "slot", "slot"),
    SHR: ("slot", "slot", "slot"),
    NEG: ("slot", "slot", None),
    INVERT: ("slot", "slot", None),
    NOT: ("slot", "slot", None),
    BUILD_LIST: ("slot", "count", None),
    BUILD_DICT: ("slot", "count", None),
    BUILD_STRING: ("slot", "count", None),
    LIST_APPEND: ("slot", None, None),
    DICT_SET: ("slot", "slot", "slot"),
    INDEX: ("slot", "slot", "slot"),
    STORE_INDEX: ("slot", "slot", "slot"),
    SLICE: ("slot", "count", None),
    STORE_SLICE: ("slot", "count", None),
    UNPACK_PLAN: ("slot", "pool", None),
    FORMAT: ("slot", "pool", None),
    MAKE_FUNCTION: ("slot", "pool", None),
    CALL: ("slot", "count", "flag"),
    METHOD_CALL: ("slot", "count", "pool"),
    RETURN: ("slot", None, None),
    HALT: (None, None, None),
    JUMP: ("target", None, None),
    JUMP_IF_FALSE: ("slot", "target", None),
    JUMP_IF_TRUE: ("slot", "target", None),
    ENTER_SCOPE: (None, None, None),
    EXIT_SCOPE: (None, None, None),
    FOR_SETUP: ("slot", None, None),
    FOR_NEXT: ("slot", "target", None),
    FOR_POP: (None, None, None),
    IMPORT: ("pool", None, None),
    TRY: ("target", None, None),
    TRY_FINALLY: ("target", None, None),
    END_TRY: (None, None, None),
    FINALLY_END: (None, None, None),
    THROW: ("slot", "flag", None),
    ASSERT: ("slot", "flag", None),
    DEL: ("pool", None, None),
    DEL_INDEX: ("slot", "slot", None),
    YIELD: ("slot", None, None),
    WITH_ENTER: ("slot", "pool", None),
    WITH_POP_TARGET: ("slot", None, None),
    PROTOCOL_GET: ("slot", "pool", None),
    PENDING_ERROR: ("slot", None, None),
    CLEAR_ERROR: (None, None, None),
    WITH_DEPTH: ("slot", None, None),
    HAS_ERROR: ("slot", None, None),
    SCOPE_ENTER: (None, None, None),
    SCOPE_EXIT: (None, None, None),
    MATCH_TEST: ("slot", "pool", None),
    MATCH_FAIL: ("slot", None, None),
    MAKE_STRUCT: ("slot", "pool", "count"),
    GET_FIELD: ("slot", "slot", "pool"),
    SET_FIELD: ("slot", "slot", "pool"),
    REGISTER_IMPL: ("pool", "pool", "pool"),
    UNWRAP_OR_RETURN: ("slot", None, None),
    LOAD_NAME2: ("slot", "pool", None),
    LOAD_NAME_CONST: ("slot", "pool", None),
    CONST_LOAD_NAME: ("slot", "pool", None),
}

# The instructions that end a function.
TERMINATORS = (RETURN, HALT)


def is_instruction(value):
    """Report whether a value looks like an instruction."""
    return (isinstance(value, tuple) and len(value) == 4
            and isinstance(value[0], str))


def format_instruction(ins, pool=None):
    """Render one instruction as a line of text."""
    op, a, b, c = ins
    name = op
    if op in BINARY_OPCODES.values() or op in UNARY_OPCODES.values():
        for symbol, code in BINARY_OPCODES.items():
            if code == op:
                name = symbol
                break
        else:
            for symbol, code in UNARY_OPCODES.items():
                if code == op:
                    name = symbol
                    break
    if pool is None:
        return "%s %d %d %d" % (name, a, b, c)
    parts = []
    for value in (a, b, c):
        if isinstance(value, str):
            parts.append('"%s"' % value)
        else:
            parts.append(str(value))
    return "%s %s" % (name, " ".join(parts))


def read_slots(code, instruction):
    """The registers that an instruction reads.

    The registers that an instruction reads have to be live, so they are
    below the depth of the expression.  The registers that an instruction
    writes may be the one above the depth, because that is where the
    value of the expression goes.
    """
    op, a, b, c = instruction
    if op in (CONST, LOAD_NAME, MAKE_FUNCTION, WITH_POP_TARGET,
              PENDING_ERROR, WITH_DEPTH, HAS_ERROR,
              LOAD_NAME2, LOAD_NAME_CONST, CONST_LOAD_NAME):
        return []
    if op in (STORE_NAME, DEFINE_NAME, POP, DUP, RETURN, FOR_SETUP,
              FORMAT, UNPACK_PLAN, YIELD, MATCH_TEST, MATCH_FAIL,
              UNWRAP_OR_RETURN):
        return [a]
    if op in BINARY_OPCODES.values():
        return [b, c]
    if op in UNARY_OPCODES.values():
        return [a]
    if op == BUILD_LIST or op == BUILD_STRING:
        return list(range(a, a + b))
    if op == MAKE_STRUCT:
        return list(range(a, a + c))
    if op == GET_FIELD:
        return [b]
    if op == SET_FIELD:
        return [a, b]
    if op == BUILD_DICT:
        return list(range(a, a + b * 2))
    if op == LIST_APPEND:
        return [a, a + 1]
    if op == DICT_SET:
        return [a, b, c]
    if op == INDEX:
        return [a, c]
    if op == STORE_INDEX:
        return [a, b, c]
    if op == SLICE:
        return list(range(a, a + b))
    if op == STORE_SLICE:
        return list(range(a, a + b))
    if op == CALL:
        return list(range(a, a + b + (1 if c else 0)))
    if op == METHOD_CALL:
        return list(range(a, a + b))
    if op in (JUMP_IF_FALSE, JUMP_IF_TRUE):
        return [a]
    if op == THROW:
        return [a, a + 1] if c else [a]
    if op == ASSERT:
        return [a] if b else []
    if op == WITH_ENTER:
        return [a, a + 1]
    if op == PROTOCOL_GET:
        return [a]
    if op == DEL_INDEX:
        return [a, b]
    return []


def touched_slots(code, instruction):
    """The registers that an instruction reads or writes.

    The registers of an instruction are the registers of the expression
    that is live at that point, and the one that the instruction writes.
    Every one of them is below the depth of the expression, so the
    values of the registers are always written before they are read.
    """
    op, a, b, c = instruction
    slots = [a]
    if op in (ADD, SUB, MUL, DIV, MOD, EQ, NE, LT, LE, GT, GE, BAND, BOR,
              BXOR, SHL, SHR, POW):
        slots.extend([b, c])
    elif op == INDEX:
        slots.extend([b, c])
    elif op == STORE_INDEX:
        slots.extend([b, c])
    elif op == DICT_SET:
        slots.extend([b, c])
    elif op == LIST_APPEND:
        slots.append(a + 1)
    elif op == DUP:
        slots.append(a + 1)
    elif op == BUILD_LIST:
        slots.append(a + b - 1)
    elif op == BUILD_DICT:
        slots.append(a + b * 2 - 1)
    elif op == BUILD_STRING:
        slots.append(a + b - 1)
    elif op == MAKE_STRUCT:
        slots.append(a + c - 1)
    elif op == GET_FIELD:
        slots.append(b)
    elif op == SET_FIELD:
        slots.append(b)
    elif op == SLICE:
        slots.append(a + 3)
    elif op == STORE_SLICE:
        slots.append(a + 4)
    elif op == UNPACK_PLAN:
        plan = code.get("consts", [])[b]
        slots.append(a + len(plan) - 1)
    elif op == CALL:
        slots.append(a + b + (1 if c else 0))
    elif op == METHOD_CALL:
        slots.append(a + b)
    return slots


def format_code(code, pool=None):
    """Render a whole code object as a list of lines."""
    lines = []
    for index, ins in enumerate(code["code"]):
        lines.append("%4d  %s" % (index, format_instruction(ins, pool)))
    return lines
