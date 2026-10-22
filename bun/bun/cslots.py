"""The frames of the native backend.

The native backend of Bun keeps the names of a program in the environments
of the runtime, and every access of a name is a lookup in a table of
strings.  That is simple, and it is slow: a loop of ten million turns
makes an environment for its body every turn, and it looks its variable
up by its name every time.

The analysis of this module gives every name of a program a place in the
frame of the function that owns it:

* a name that no closure captures lives in a slot of the frame, so the
  access of a name is the access of an array,
* a name that a closure captures lives in an environment, because the
  closure has to find the name when it runs later.

The environments are only made when a scope holds a name that needs one,
so a loop that touches only its own variables never allocates anything.

The analysis follows the rules of the machine of the stack, which is the
reference of the language:

* a name is read in the scope that binds it, and the scope of a name is
  the scope that was open where the name was defined,
* a name that no open scope binds is looked up in the environments, and it
  is an error when no environment holds it.

The scopes are found with a walk of the code that follows the jumps,
because the scopes of a `break` and of a `continue` are closed before the
jump, and the block that holds the jump never closes them again.
"""

from . import regcode
from .patterns import plan_names

# The scope of the parameters of a function is the scope of the call, and
# it is open in every instruction of the function.
OUTER = -1


class Binding:
    """A name that a code object binds."""

    __slots__ = ("name", "mutable", "scope", "slot", "env", "forced_env")

    def __init__(self, name, mutable, scope):
        self.name = name
        self.mutable = mutable
        self.scope = scope
        self.slot = None
        self.env = False
        self.forced_env = False


class Scope:
    """A scope of a code object.

    The scope of the parameters of a function is the scope zero, and the
    scopes of the blocks of the body follow it.
    """

    __slots__ = ("depth", "bindings", "needs_env", "jumps")

    def __init__(self, depth):
        self.depth = depth
        self.bindings = []
        self.needs_env = False
        self.jumps = []

    def bind(self, position, binding):
        """Add a binding to the scope."""
        self.bindings.append((position, binding))

    def find(self, name, position):
        """The binding of a name that the scope holds before a place."""
        found = None
        for at, binding in self.bindings:
            if at >= position:
                break
            if binding.name == name:
                found = binding
        return found


class Site:
    """A place where a code object reads or writes a name."""

    __slots__ = ("position", "name", "kind", "binding", "dynamic", "slot")

    def __init__(self, position, name, kind, binding):
        self.position = position
        self.name = name
        self.kind = kind
        self.binding = binding
        self.dynamic = binding is None
        self.slot = None


class Frame:
    """What the backend knows about one code object."""

    __slots__ = ("code", "scopes", "bindings", "param_bindings", "sites",
                 "sites_by_position", "children", "free", "bound", "env_names",
                 "slot_count", "scope_depth", "scope_exit", "needs_env",
                 "max_depth", "states")

    def __init__(self, code):
        self.code = code
        self.scopes = {}           # the scopes, keyed by the place that opens
        self.bindings = []
        self.param_bindings = []
        self.sites = []
        self.sites_by_position = {}
        self.children = []
        self.free = set()
        self.bound = set()
        self.env_names = set()
        self.slot_count = 0
        self.scope_depth = {}      # the place that opens a scope -> its depth
        self.scope_exit = {}       # the place that closes a scope -> its depth
        self.needs_env = False
        self.max_depth = 0
        self.states = []           # the open scopes at every instruction

    def site_at(self, position):
        """The place where a name is read or written."""
        return self.sites_by_position[position]

    def site_of_name(self, name, position):
        """The last place where a name was bound, before a place."""
        found = None
        for site in self.sites:
            if site.position > position:
                break
            if site.name == name and site.kind == "define":
                found = site
        return found

    def enter_needs_env(self, position):
        """Whether the scope that an instruction opens needs an environment."""
        return self.scopes[position].needs_env

    def scope_of(self, position):
        """The scope that an instruction of a name belongs to."""
        state = self.states[position]
        return self.scopes[state[-1]]


def analyze(code):
    """Analyse a program and return the frames of its code objects.

    The result is keyed by the identity of the code object, because a
    code object is a dictionary and it cannot be a key of a dictionary.
    """
    frames = {}
    order = []
    _collect(code, frames, order)
    for frame in order:
        _build(frame)
    for frame in reversed(order):
        _free(frame)
    for frame in order:
        _capture(frame)
    for frame in order:
        _slots(frame)
    return frames


def _collect(code, frames, order):
    """Collect the code objects of a program, the module first."""
    if id(code) in frames:
        return frames[id(code)]
    frame = Frame(code)
    frames[id(code)] = frame
    order.append(frame)
    for value in code.get("consts", []):
        if isinstance(value, dict) and "code" in value:
            child = _collect(value, frames, order)
            frame.children.append(child)
    for spec in code.get("param_defs", []):
        default = spec.get("default")
        if isinstance(default, dict) and "code" in default:
            child = _collect(default, frames, order)
            frame.children.append(child)
    return frame


def _successors(frame, position):
    """The places where the flow of the code goes after an instruction."""
    instructions = frame.code["code"]
    op, a, b, c = instructions[position]
    if op == regcode.JUMP:
        return [a]
    if op in (regcode.JUMP_IF_FALSE, regcode.JUMP_IF_TRUE):
        return [position + 1, b]
    if op == regcode.FOR_NEXT:
        # The loop leaves when the iterator has no more items.
        return [position + 1, b]
    if op in (regcode.TRY, regcode.TRY_FINALLY):
        # The handler of the error runs with the scopes of the `try`
        # closed, so it takes the scope of the `try` itself.
        return [position + 1, a]
    if op in (regcode.RETURN, regcode.HALT):
        return []
    return [position + 1]


def _transfer(frame, position, state):
    """The scopes that are open after an instruction."""
    op = frame.code["code"][position][0]
    if op == regcode.ENTER_SCOPE:
        return state + (position,)
    if op == regcode.EXIT_SCOPE:
        if len(state) > 1:
            return state[:-1]
    return state


def _states(frame):
    """The scopes that are open at every instruction of a code object.

    The walk follows the jumps, because a `break` closes the scopes of
    the block that holds it before it jumps, and the block never closes
    them again.
    """
    instructions = frame.code["code"]
    count = len(instructions)
    states = [None] * count
    if count == 0:
        return states
    states[0] = (OUTER,)
    work = [0]
    while work:
        position = work.pop()
        state = states[position]
        if state is None:
            continue
        after = _transfer(frame, position, state)
        for target in _successors(frame, position):
            if target < 0 or target >= count:
                continue
            if states[target] is None:
                states[target] = after
                work.append(target)
    return states


def _linear_states(frame):
    """The scopes that are open at every instruction, read in a line.

    The line cannot know the scopes of a `break`, so it is only the
    answer for the instructions that no jump reaches.
    """
    instructions = frame.code["code"]
    states = []
    state = (OUTER,)
    for instruction in instructions:
        states.append(state)
        state = _transfer(frame, len(states) - 1, state)
    return states


def _resolve(frame, state, name, position):
    """The binding of a name that a place reads."""
    for scope_id in reversed(state):
        scope = frame.scopes.get(scope_id)
        if scope is None:
            continue
        binding = scope.find(name, position)
        if binding is not None:
            return binding
    return None


def _build(frame):
    """Build the scopes, the bindings and the sites of a code object."""
    code = frame.code
    consts = code.get("consts", [])
    instructions = code["code"]
    outer = Scope(0)
    frame.scopes[OUTER] = outer
    for spec in code.get("param_defs", []):
        name = spec["name"]
        binding = Binding(name, True, outer)
        outer.bind(-1, binding)
        frame.bindings.append(binding)
        frame.param_bindings.append(binding)
        frame.bound.add(name)
    for position, instruction in enumerate(instructions):
        if instruction[0] == regcode.ENTER_SCOPE:
            frame.scopes[position] = Scope(0)
    states = _states(frame)
    linear = _linear_states(frame)
    frame.states = states
    for position, instruction in enumerate(instructions):
        op, a, b, c = instruction
        state = states[position]
        if state is None:
            state = linear[position]
        if op == regcode.ENTER_SCOPE:
            scope = frame.scopes[position]
            scope.depth = len(state)
            frame.scope_depth[position] = scope.depth
            if scope.depth > frame.max_depth:
                frame.max_depth = scope.depth
        elif op == regcode.EXIT_SCOPE:
            frame.scope_exit[position] = len(state) - 1
        elif op == regcode.DEFINE_NAME:
            name = consts[b]
            scope = frame.scopes[state[-1]]
            binding = Binding(name, bool(c), scope)
            scope.bind(position, binding)
            frame.bindings.append(binding)
            frame.bound.add(name)
            frame.sites.append(Site(position, name, "define", binding))
            frame.sites_by_position[position] = frame.sites[-1]
        elif op == regcode.MATCH_TEST:
            # A pattern binds its names in the scope of the case, and the
            # scope has an environment of its own, so the names of the
            # pattern leave the scope when the case ends.
            scope = frame.scopes[state[-1]]
            for name in plan_names(consts[b]):
                binding = Binding(name, True, scope)
                binding.forced_env = True
                scope.bind(position, binding)
                frame.bindings.append(binding)
                frame.bound.add(name)
        elif op == regcode.WITH_ENTER:
            # The name of a `with` lives in the environment of the scope
            # that holds the statement, because the statement defines the
            # name there, and the name leaves the scope when the scope
            # ends.
            name = consts[b]
            scope = frame.scopes[state[-1]]
            binding = Binding(name, True, scope)
            binding.forced_env = True
            scope.bind(position, binding)
            frame.bindings.append(binding)
            frame.bound.add(name)
        elif op == regcode.LOAD_NAME:
            name = consts[b]
            frame.sites.append(Site(position, name, "read",
                                     _resolve(frame, state, name, position)))
            frame.sites_by_position[position] = frame.sites[-1]
        elif op == regcode.STORE_NAME:
            name = consts[b]
            frame.sites.append(Site(position, name, "write",
                                     _resolve(frame, state, name, position)))
            frame.sites_by_position[position] = frame.sites[-1]
        elif op == regcode.DEL:
            name = consts[a]
            frame.sites.append(Site(position, name, "delete",
                                     _resolve(frame, state, name, position)))
            frame.sites_by_position[position] = frame.sites[-1]
        elif op == regcode.JUMP:
            scope = frame.scopes.get(state[-1])
            if scope is not None:
                scope.jumps.append((position, a))
        elif op in (regcode.JUMP_IF_FALSE, regcode.JUMP_IF_TRUE):
            scope = frame.scopes.get(state[-1])
            if scope is not None:
                scope.jumps.append((position, b))


def _free(frame):
    """The names that leave the scopes of a code object.

    A name leaves the code object when a place reads it and no scope that
    is open binds it, and when a function of the code object reads a name
    that it does not bind itself.  A name that a function of the code
    object removes leaves it as well, because the removal has to reach
    the scope that holds the name.
    """
    names = set()
    for site in frame.sites:
        if site.binding is None:
            names.add(site.name)
    for child in frame.children:
        names |= child.free
    frame.free = names


def _capture(frame):
    """The names of a code object that a closure of it captures.

    A name that a function of the code object reads, and that the
    function does not bind itself, comes from the scope of the code
    object, so the name has to live in an environment.
    """
    captured = set()
    for child in frame.children:
        captured |= child.free
    frame.env_names = captured & frame.bound


def _slots(frame):
    """Give every name of a code object its place in the frame."""
    conditional = set()
    for scope in frame.scopes.values():
        for site in frame.sites:
            if site.kind != "define" or site.binding.scope is not scope:
                continue
            for source, target in scope.jumps:
                if source < site.position < target:
                    # The place that defines the name can be jumped over,
                    # so the name is not always there, and the name has to
                    # be looked up when it is read.
                    conditional.add(site.name)
                    break
    # A name that the program removes lives in an environment, because
    # the removal has to reach the scope that holds the name, and a slot
    # of a frame belongs to the frame that made it.
    removed = set()
    for site in frame.sites:
        if site.kind == "delete":
            removed.add(site.name)
    env_names = frame.env_names | conditional | removed
    slot = 0
    for binding in frame.bindings:
        if binding.forced_env:
            # The name is bound by a pattern, and the pattern binds it in
            # the environment of the scope of the case.
            binding.env = True
            binding.slot = None
        elif binding.name in env_names:
            binding.env = True
            binding.slot = None
        else:
            binding.env = False
            binding.slot = slot
            slot += 1
    frame.slot_count = slot
    for site in frame.sites:
        if site.binding is None or site.binding.env:
            site.dynamic = True
            site.slot = None
        else:
            site.dynamic = False
            site.slot = site.binding.slot
    for scope in frame.scopes.values():
        scope.needs_env = False
        for _, binding in scope.bindings:
            if binding.env:
                scope.needs_env = True
                break
    # The parameters of a function live in the environment of the call
    # when a closure of the function captures one of them.
    frame.needs_env = frame.scopes[OUTER].needs_env
