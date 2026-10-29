"""The verifier of the register code of Bun.

The register code runs before it is trusted.  The verifier walks the code
of every function and proves the shape of the program:

- every name of a constant is inside the pool of the function;
- every slot is a slot of the expression, never a negative one;
- every jump lands on an instruction of the same function;
- the depth of the expression is the same on every path that reaches an
  instruction, so a loop cannot grow the expression without end;
- every function ends with a return or a halt.

The verifier is a safety net, not a proof of correctness.  The register
code of a program that the compiler accepts always passes it, and the
golden corpus of the test suite is what proves that the two machines run
the same programs in the same way.
"""

from . import regcode
from .errors import BunRuntimeError


class VerifyError(BunRuntimeError):
    """Raised when the register code is not well formed."""


def verify(code, name=None):
    """Verify one code object of the register machine."""
    instructions = code.get("code", [])
    pool = code.get("consts", [])
    depths = code.get("depths", [])
    where = name or code.get("name") or "<module>"
    if not instructions:
        raise VerifyError("the function '%s' has no code" % where)
    last = len(instructions) - 1
    for index, instruction in enumerate(instructions):
        op = instruction[0]
        kinds = regcode.OPERANDS.get(op)
        if kinds is None:
            raise VerifyError(
                "unknown instruction '%s' in '%s'" % (op, where))
        cells = instruction[1:]
        for position, kind in enumerate(kinds):
            if kind is None:
                continue
            value = cells[position]
            if kind == "pool":
                if not 0 <= value < len(pool):
                    raise VerifyError(
                        "the constant %d of '%s' is outside the pool"
                        % (value, where))
            elif kind == "slot":
                if value < 0:
                    raise VerifyError(
                        "the slot %d of '%s' is negative" % (value, where))
            elif kind == "target":
                if not 0 <= value <= last:
                    raise VerifyError(
                        "the jump of '%s' leaves the function" % where)
            elif kind == "count":
                if value < 0:
                    raise VerifyError(
                        "the count %d of '%s' is negative" % (value, where))
        if op == regcode.JUMP or op in (regcode.JUMP_IF_FALSE,
                                       regcode.JUMP_IF_TRUE,
                                       regcode.JUMP_IF_NULL):
            target = instruction[1] if op == regcode.JUMP else instruction[2]
            if not 0 <= target <= last:
                raise VerifyError(
                    "the jump of '%s' leaves the function" % where)
        if op == regcode.FOR_NEXT:
            target = instruction[2]
            if not 0 <= target <= last:
                raise VerifyError(
                    "the jump of '%s' leaves the function" % where)
        if op in (regcode.TRY, regcode.TRY_FINALLY):
            target = instruction[1]
            if not 0 <= target <= last:
                raise VerifyError(
                    "the handler of '%s' leaves the function" % where)
    # Every register that an instruction reads has to be live at that
    # point: a register that is read is below the depth of the
    # expression, and the depth holds the values that the stack machine
    # pushed before it.  A register is written before it is read, so its
    # first value is never a leftover.
    for index, instruction in enumerate(instructions):
        if index >= len(depths):
            break
        depth = depths[index]
        for slot in regcode.read_slots(code, instruction):
            if slot >= depth:
                raise VerifyError(
                    "the instruction %d of '%s' reads the register %d, "
                    "which is not live at the depth of the expression (%d)"
                    % (index, where, slot, depth))
    # The depth of the expression has to be the same on every path.
    for index, instruction in enumerate(instructions):
        op = instruction[0]
        if op in (regcode.JUMP, regcode.JUMP_IF_FALSE, regcode.JUMP_IF_TRUE,
                  regcode.JUMP_IF_NULL):
            target = instruction[1] if op == regcode.JUMP else instruction[2]
            expected = _depth_after(depths, index, op)
            if expected is None or target >= len(depths):
                continue
            if depths[target] != expected:
                raise VerifyError(
                    "the jump of '%s' changes the depth of the expression "
                    "(%d becomes %d at the instruction %d)"
                    % (where, expected, depths[target], target))
        elif op == regcode.FOR_NEXT:
            target = instruction[2]
            if target >= len(depths) or index >= len(depths):
                continue
            if depths[target] != depths[index]:
                raise VerifyError(
                    "the loop of '%s' changes the depth of the expression"
                    % where)
    # The function has to end with a return or a halt.
    final = instructions[-1][0]
    if final not in regcode.TERMINATORS:
        raise VerifyError(
            "the function '%s' does not end with a return" % where)
    return True


def _depth_after(depths, index, op):
    """The depth of the expression after a jump.

    The depth that is recorded for an instruction is the depth *before*
    it runs.  A jump does not change the depth, and a jump on a condition
    pops the condition.
    """
    if index >= len(depths):
        return None
    if op == regcode.JUMP:
        return depths[index]
    return depths[index] - 1


def verify_program(code):
    """Verify a code object and every function it holds."""
    verify(code)
    seen = set()
    _verify_consts(code.get("consts", []), seen)
    return True


def _verify_consts(consts, seen):
    for value in consts:
        if id(value) in seen:
            continue
        if isinstance(value, dict) and "code" in value:
            seen.add(id(value))
            verify(value)
            _verify_consts(value.get("consts", []), seen)
