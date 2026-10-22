"""The superinstruction tier of Bun.

The register VM runs one instruction at a time, and every instruction costs
a dispatch.  Two instructions that always run one after the other can be
replaced by one instruction that does the work of both, and the program
gets a little faster without changing what it does.

The fusion happens at load time, on the code that the verifier has already
checked, so a fused instruction is as safe as the two it replaces.  The
fusion is careful about two things:

- the second instruction of a pair must not be the target of a jump, or a
  jump that wanted to run only the second instruction would run the first
  one as well;
- the two instructions must sit at the depth the fusion expects, so the
  depth of the expression stays the same on every path.

The pairs that are fused are the ones that carry no side effect: the
loads of a name and the loads of a constant.  Every pair of them that
sits next to each other becomes one instruction.

The plan of the work of a fused instruction lives in the constant pool of
the code object::

    ("name", "count", "const", 1, (line, col))

The last cell is the place of the second part, so an error that happens
there is reported at the right place.
"""

from . import regcode


class FuseError(Exception):
    """Raised when the register code cannot be fused."""


# The pairs that can be fused, and the instruction that replaces them.
PAIRS = {
    (regcode.LOAD_NAME, regcode.LOAD_NAME): regcode.LOAD_NAME2,
    (regcode.LOAD_NAME, regcode.CONST): regcode.LOAD_NAME_CONST,
    (regcode.CONST, regcode.LOAD_NAME): regcode.CONST_LOAD_NAME,
}


def fuse(code):
    """Fuse the pairs of a code object and return the new code object.

    The code that comes in has to be verified already; the code that goes
    out is verified again by the caller, because the fusion changes the
    shape of the program.
    """
    instructions = code.get("code", [])
    depths = code.get("depths", [])
    lines = code.get("lines", [])
    consts = list(code.get("consts", []))
    if not instructions:
        return code
    targets = _targets(instructions)
    out = []
    out_depths = []
    out_lines = []
    # The map from the old index of an instruction to the new one, so the
    # jumps can be rewritten.
    moved = {}
    index = 0
    while index < len(instructions):
        current = instructions[index]
        following = instructions[index + 1] if index + 1 < len(instructions) \
            else None
        pair = _pair(current, following, index, targets, depths, lines,
                     consts)
        if pair is None:
            moved[index] = len(out)
            out.append(current)
            out_depths.append(depths[index] if index < len(depths) else 0)
            out_lines.append(lines[index] if index < len(lines) else (0, 0))
            index += 1
            continue
        fused, plan = pair
        consts.append(plan)
        moved[index] = len(out)
        out.append(fused)
        out_depths.append(depths[index] if index < len(depths) else 0)
        out_lines.append(lines[index] if index < len(lines) else (0, 0))
        # The second instruction is gone, so every jump that pointed at it
        # points at the fused instruction instead.
        moved[index + 1] = len(out) - 1
        index += 2
    result = dict(code)
    result["code"] = [_rewrite(ins, moved) for ins in out]
    result["depths"] = out_depths
    result["lines"] = out_lines
    result["consts"] = consts
    _fuse_nested(result)
    return result


def _fuse_nested(code):
    """Fuse the functions that the code holds."""
    consts = code.get("consts", [])
    for index, value in enumerate(consts):
        if isinstance(value, dict) and "code" in value:
            consts[index] = fuse(value)


def _targets(instructions):
    """The instructions that a jump can land on."""
    targets = set()
    for instruction in instructions:
        op = instruction[0]
        if op == regcode.JUMP:
            targets.add(instruction[1])
        elif op in (regcode.JUMP_IF_FALSE, regcode.JUMP_IF_TRUE):
            targets.add(instruction[2])
        elif op == regcode.FOR_NEXT:
            targets.add(instruction[2])
        elif op in (regcode.TRY, regcode.TRY_FINALLY):
            targets.add(instruction[1])
    return targets


def _pair(current, following, index, targets, depths, lines, consts):
    """The fused instruction of a pair, or None when there is none."""
    if following is None:
        return None
    key = (current[0], following[0])
    opcode = PAIRS.get(key)
    if opcode is None:
        return None
    # A jump that lands on the second instruction must still land there.
    if index + 1 in targets:
        return None
    # The second instruction writes into the slot after the first one, and
    # the depth of the expression grows by one with each of them.
    if following[1] != current[1] + 1:
        return None
    if index + 1 < len(depths) and index < len(depths):
        if depths[index + 1] != depths[index] + 1:
            return None
    first = _part(current, consts)
    second = _part(following, consts)
    if first is None or second is None:
        return None
    place = lines[index + 1] if index + 1 < len(lines) else (0, 0)
    plan = (first[0], first[1], second[0], second[1], place)
    return (opcode, current[1], len(consts), 0), plan


def _part(instruction, consts):
    """The kind and the value of a load."""
    op = instruction[0]
    if op == regcode.LOAD_NAME:
        return ("name", consts[instruction[2]])
    if op == regcode.CONST:
        return ("const", consts[instruction[2]])
    return None


def _rewrite(instruction, moved):
    """Point the jump of an instruction at its new place."""
    op = instruction[0]
    if op == regcode.JUMP:
        return (op, moved.get(instruction[1], instruction[1]), instruction[2],
                instruction[3])
    if op in (regcode.JUMP_IF_FALSE, regcode.JUMP_IF_TRUE):
        return (op, instruction[1], moved.get(instruction[2], instruction[2]),
                instruction[3])
    if op == regcode.FOR_NEXT:
        return (op, instruction[1], moved.get(instruction[2], instruction[2]),
                instruction[3])
    if op in (regcode.TRY, regcode.TRY_FINALLY):
        return (op, moved.get(instruction[1], instruction[1]), instruction[2],
                instruction[3])
    return instruction


def count_pairs(code):
    """Count the pairs of the code that the fusion would make.

    The count is what `bun compile --profile` shows for the tier: the
    number of times a pair of instructions sits next to each other in the
    code of the program.  The functions that the program holds are part
    of the count.
    """
    instructions = code.get("code", [])
    counts = {}
    for index in range(len(instructions) - 1):
        key = (instructions[index][0], instructions[index + 1][0])
        if key in PAIRS:
            counts[key] = counts.get(key, 0) + 1
    for value in code.get("consts", []):
        if isinstance(value, dict) and "code" in value:
            for key, count in count_pairs(value).items():
                counts[key] = counts.get(key, 0) + count
    return counts


def count_fused(code):
    """Count the fused instructions of a code object and its functions."""
    total = 0
    for instruction in code.get("code", []):
        if instruction[0] in (regcode.LOAD_NAME2, regcode.LOAD_NAME_CONST,
                               regcode.CONST_LOAD_NAME):
            total += 1
    for value in code.get("consts", []):
        if isinstance(value, dict) and "code" in value:
            total += count_fused(value)
    return total
