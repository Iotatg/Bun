"""Antar — the shape of a Bun program once control flow is made explicit.

`antar` (अंतर) means "the inside, the interval between".  It is Bun's own
intermediate representation: one graph per function, shared by every tool
that needs to reason about a program instead of running it.

Why it exists
-------------
Bun had six engines and each of them lowered control flow in its own way.
`if`, `while`, `for`, `break`, `continue`, short-circuit `and`/`or` and
`return` were written once per backend, so six implementations had to
agree on one meaning.  Reading Rust's MIR showed the principle that
removes that duplication: a function is a graph of *straight-line blocks*
that end in exactly one *terminator*, and every later stage consumes that
one graph.  The principle is borrowed; the design, the names and the
semantics here are Bun's own.

The vocabulary
--------------
    khand     a basic block: a list of kriya and one nirnaya
    kriya     a straight-line action (set, assign, opset, step, emit, check)
    nirnaya   the single terminator of a khand
              ja        go to one khand
              chunav    choose between two khand by a test
              laut      leave the flow with a value
              samaapt   leave the flow with no value
              viram     unreachable
    sthan     a source position, packed into one integer
    pravah    one flow graph: the khand of one function
    antar     the whole program: a map of flows plus the main flow

What Antar owns
---------------
Statement-level control flow.  Conditions are lowered into `chunav`
terminators, and a logical condition (`and`/`or`) becomes a chain of
khand, so short-circuit evaluation is visible in the graph instead of
being hidden in an expression evaluator.  Expressions themselves are
evaluated by the same evaluator the tree engine uses, so a value means
exactly the same thing on both engines.

What Antar does not own (and says so by name)
---------------------------------------------
`for` over a value that is not `range(...)`, `try`, `match`, `with`,
generators, structs, enums, protocols, imports and closures are outside
the graph and are refused with `Unsupported("antar", ...)`.  A refusal
names the construct; it never silently miscompiles.

One environment per flow
------------------------
A `pravah` has one environment, so a name declared inside a khand stays
visible after it.  Block scoping is a property of the tree engine, not of
the graph.  This is a documented difference, not an accident.
"""

from dataclasses import dataclass, field

from . import ast, ops
from .environment import Environment
from .errors import BunRuntimeError
from .intcore import Unsupported
from .values import Builtin, copy_value, is_truthy, stringify


# ---------------------------------------------------------------------------
# Terminator kinds.  Bun words, not English keywords.
# ---------------------------------------------------------------------------

JA = "ja"
CHUNAV = "chunav"
LAUT = "laut"
SAMAAPT = "samaapt"
VIRAM = "viram"

TERMINATORS = (JA, CHUNAV, LAUT, SAMAAPT, VIRAM)

# Kriya kinds.
SET = "set"
ASSIGN = "assign"
OPSET = "opset"
STEP = "step"
EMIT = "emit"
CHECK = "check"

ACTIONS = (SET, ASSIGN, OPSET, STEP, EMIT, CHECK)


# ---------------------------------------------------------------------------
# The nodes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Sthan:
    """A source position, packed the way a compiler wants to store it.

    Rust stores a span in eight bytes.  Bun stores a position in one
    integer: line in the high bits, column in the low twelve bits.  The
    packed form is what a graph dump and a diagnostic both quote.
    """

    line: int = 0
    col: int = 0

    @property
    def packed(self):
        return (self.line << 12) | (self.col & 0xFFF)

    def __str__(self):
        return "%d:%d" % (self.line, self.col)


def sthan_of(node):
    return Sthan(getattr(node, "line", 0) or 0, getattr(node, "col", 0) or 0)


@dataclass
class Kriya:
    """One straight-line action of a khand."""

    kind: str
    sthan: Sthan
    name: object = None       # target name for set/assign/opset/step
    op: object = None         # operator for opset/step
    expr: object = None       # the AST expression that produces the value
    mutable: bool = True      # for set
    message: object = None    # the expression of an assert message
    note: str = ""

    def text(self):
        if self.kind == SET:
            return "set %s = %s" % (self.name, expr_text(self.expr))
        if self.kind == ASSIGN:
            return "assign %s = %s" % (self.name, expr_text(self.expr))
        if self.kind == OPSET:
            return "%s %s= %s" % (self.name, self.op, expr_text(self.expr))
        if self.kind == STEP:
            return "%s%s" % (self.name, "++" if self.op == "+" else "--")
        if self.kind == EMIT:
            return "emit %s" % expr_text(self.expr)
        if self.kind == CHECK:
            return "check %s" % expr_text(self.expr)
        return self.kind


@dataclass
class Nirnaya:
    """The single terminator of a khand."""

    kind: str
    sthan: Sthan
    then: object = None        # target khand for ja / true target for chunav
    otherwise: object = None   # false target for chunav
    expr: object = None        # test for chunav, value for laut

    def targets(self):
        if self.kind == JA:
            return [self.then]
        if self.kind == CHUNAV:
            return [self.then, self.otherwise]
        return []

    def text(self):
        if self.kind == JA:
            return "ja -> %s" % self.then
        if self.kind == CHUNAV:
            return "chunav %s ? %s : %s" % (
                expr_text(self.expr), self.then, self.otherwise)
        if self.kind == LAUT:
            if self.expr is None:
                return "laut"
            return "laut %s" % expr_text(self.expr)
        if self.kind == SAMAAPT:
            return "samaapt"
        return "viram"


@dataclass
class Khand:
    """A basic block: actions, then exactly one terminator."""

    index: int
    kriya: list = field(default_factory=list)
    nirnaya: object = None
    sthan: Sthan = field(default_factory=Sthan)
    tag: str = ""

    def successors(self):
        if self.nirnaya is None:
            return []
        return [t for t in self.nirnaya.targets() if t is not None]


@dataclass
class Pravah:
    """One flow graph — the khand of one function."""

    name: str
    params: list = field(default_factory=list)
    blocks: list = field(default_factory=list)
    entry: int = 0
    filename: str = "<program>"
    sthan: Sthan = field(default_factory=Sthan)

    def __len__(self):
        return len(self.blocks)

    def edges(self):
        count = 0
        for block in self.blocks:
            count += len(block.successors())
        return count


@dataclass
class Antar:
    """The whole program: every flow, plus the flow of the module body."""

    flows: dict = field(default_factory=dict)
    main: object = None
    filename: str = "<program>"

    def all_flows(self):
        return list(self.flows.values()) + ([self.main] if self.main else [])

    def stats(self):
        blocks = sum(len(flow.blocks) for flow in self.all_flows())
        edges = sum(flow.edges() for flow in self.all_flows())
        return {
            "flows": len(self.all_flows()),
            "blocks": blocks,
            "edges": edges,
            "functions": len(self.flows),
        }


# ---------------------------------------------------------------------------
# Rendering an expression for a dump.  The graph quotes the program; it
# never pretends to be the parser.
# ---------------------------------------------------------------------------

def expr_text(node):
    if node is None:
        return "-"
    if isinstance(node, ast.Literal):
        if isinstance(node.value, str):
            return '"%s"' % node.value
        return repr(node.value)
    if isinstance(node, ast.Identifier):
        return node.name
    if isinstance(node, ast.Binary):
        return "(%s %s %s)" % (expr_text(node.left), node.op,
                               expr_text(node.right))
    if isinstance(node, ast.Logical):
        return "(%s %s %s)" % (expr_text(node.left), node.op,
                               expr_text(node.right))
    if isinstance(node, ast.Unary):
        return "%s%s" % (node.op, expr_text(node.operand))
    if isinstance(node, ast.Call):
        args = [expr_text(arg) for arg in node.args]
        args += ["%s: %s" % (name, expr_text(value))
                 for name, value in node.kwargs]
        return "%s(%s)" % (expr_text(node.callee), ", ".join(args))
    if isinstance(node, ast.ListLiteral):
        return "[%s]" % ", ".join(expr_text(item) for item in node.items)
    if isinstance(node, ast.Attribute):
        return "%s.%s" % (expr_text(node.object), node.name)
    if isinstance(node, ast.Index):
        return "%s[%s]" % (expr_text(node.target), expr_text(node.index))
    return type(node).__name__


# ---------------------------------------------------------------------------
# Lowering: AST -> Antar
# ---------------------------------------------------------------------------

class _Nirmana:
    """The builder of one pravah.

    `nirmana` means construction.  The builder owns the list of khand,
    the current khand and the stack of loops, so a `break` can be lowered
    to a `ja` to the exit khand of the loop it names.
    """

    def __init__(self, name, params, filename, sthan):
        self.filename = filename
        self.blocks = [Khand(0, [], None, sthan, "entry")]
        self.current = 0
        self.sealed = False
        self.loops = []
        self.temps = 0
        self.params = params
        self.name = name

    # -- block plumbing ----------------------------------------------------
    def emit(self, kriya):
        if self.sealed:
            raise BunRuntimeError("antar: action after terminator")
        self.blocks[self.current].kriya.append(kriya)

    def terminate(self, nirnaya):
        if self.sealed:
            raise BunRuntimeError("antar: two terminators in one khand")
        self.blocks[self.current].nirnaya = nirnaya
        self.sealed = True

    def new(self, tag, sthan):
        self.blocks.append(Khand(len(self.blocks), [], None, sthan, tag))
        return len(self.blocks) - 1

    def switch_to(self, index):
        self.current = index
        self.sealed = self.blocks[index].nirnaya is not None

    def goto(self, index, sthan):
        self.terminate(Nirnaya(JA, sthan, then=index))

    def temp(self, prefix):
        self.temps += 1
        return "__antar_%s_%d" % (prefix, self.temps)

    def flow(self):
        return Pravah(self.name, self.params, self.blocks, 0,
                      self.filename, self.blocks[0].sthan)

    # -- statements --------------------------------------------------------
    def lower(self, statements):
        for statement in statements:
            if self.sealed:
                # Everything after a terminator in the same khand is dead
                # code.  The tree engine never reaches it either, so the
                # graph drops it instead of inventing a block for it.
                return
            self.statement(statement)

    def statement(self, node):
        if isinstance(node, ast.LetStmt):
            self.emit(Kriya(SET, sthan_of(node), name=node.name,
                            expr=node.value, mutable=node.mutable))
        elif isinstance(node, ast.AssignStmt):
            self._assign(node)
        elif isinstance(node, ast.OpAssignStmt):
            if not isinstance(node.target, ast.Identifier):
                raise Unsupported("antar", "a compound assignment to a"
                                  " field or an index", node)
            self.emit(Kriya(OPSET, sthan_of(node), name=node.target.name,
                            op=node.op, expr=node.value))
        elif isinstance(node, ast.IncDecStmt):
            if not isinstance(node.target, ast.Identifier):
                raise Unsupported("antar", "an increment of a field or an"
                                  " index", node)
            op = node.op if node.op in ("+", "-") else (
                "+" if node.op == "++" else "-")
            self.emit(Kriya(STEP, sthan_of(node), name=node.target.name,
                            op=op))
        elif isinstance(node, ast.ExprStmt):
            if isinstance(node.expr, ast.Identifier) and \
                    node.expr.name == "pass":
                return
            self.emit(Kriya(EMIT, sthan_of(node), expr=node.expr))
        elif isinstance(node, ast.AssertStmt):
            self.emit(Kriya(CHECK, sthan_of(node), expr=node.condition,
                            message=node.message))
        elif isinstance(node, ast.Block):
            self.lower(node.statements)
        elif isinstance(node, ast.IfStmt):
            self._if(node)
        elif isinstance(node, ast.WhileStmt):
            self._while(node)
        elif isinstance(node, ast.ForStmt):
            self._for(node)
        elif isinstance(node, ast.ReturnStmt):
            self.terminate(Nirnaya(LAUT, sthan_of(node), expr=node.value))
        elif isinstance(node, ast.BreakStmt):
            target = self._loop_target(node, "break")
            self.goto(target, sthan_of(node))
        elif isinstance(node, ast.ContinueStmt):
            target = self._loop_target(node, "continue")
            self.goto(target, sthan_of(node))
        elif isinstance(node, (ast.FnDecl, ast.StructDecl, ast.EnumDecl,
                               ast.ProtocolDecl, ast.ImplDecl)):
            raise Unsupported("antar", "a declaration inside a block", node)
        else:
            raise Unsupported("antar", "the statement %s"
                              % type(node).__name__, node)

    def _assign(self, node):
        target = node.target
        if isinstance(target, ast.Identifier):
            self.emit(Kriya(ASSIGN, sthan_of(node), name=target.name,
                            expr=node.value))
            return
        if isinstance(target, ast.UnpackTarget):
            raise Unsupported("antar", "an unpacking assignment", node)
        raise Unsupported("antar", "an assignment to a field or an index",
                          node)

    def _loop_target(self, node, what):
        label = getattr(node, "label", None)
        if not self.loops:
            raise Unsupported("antar", "a %s outside a loop" % what, node)
        if label is None:
            entry = self.loops[-1]
        else:
            entry = None
            for candidate in reversed(self.loops):
                if candidate[0] == label:
                    entry = candidate
                    break
            if entry is None:
                raise Unsupported("antar", "a %s of the loop '%s'"
                                  % (what, label), node)
        return entry[1] if what == "break" else entry[2]

    def _branch(self, branch):
        """Lower a branch, which is a block or a single statement.

        `else if` is not an `else` that contains an `if`: the parser hands
        the nested `if` over directly.  Both shapes mean the same thing.
        """
        if isinstance(branch, ast.Block):
            self.lower(branch.statements)
        else:
            self.statement(branch)

    def _if(self, node):
        then_block = self.new("then", sthan_of(node))
        join_block = self.new("join", sthan_of(node))
        if node.else_branch is not None:
            else_block = self.new("else", sthan_of(node))
            self.condition(node.condition, then_block, else_block)
            self.switch_to(else_block)
            self._branch(node.else_branch)
            if not self.sealed:
                self.goto(join_block, sthan_of(node))
        else:
            self.condition(node.condition, then_block, join_block)
        self.switch_to(then_block)
        self._branch(node.then_branch)
        if not self.sealed:
            self.goto(join_block, sthan_of(node))
        self.switch_to(join_block)

    def _while(self, node):
        head = self.new("while-head", sthan_of(node))
        body = self.new("while-body", sthan_of(node))
        exit_block = self.new("while-exit", sthan_of(node))
        self.goto(head, sthan_of(node))
        self.switch_to(head)
        self.condition(node.condition, body, exit_block)
        self.loops.append((node.label, exit_block, head))
        self.switch_to(body)
        self._branch(node.body)
        if not self.sealed:
            self.goto(head, sthan_of(node))
        self.loops.pop()
        self.switch_to(exit_block)
        if node.orelse is not None:
            self._branch(node.orelse)

    def _for(self, node):
        args = _range_args(node.iterable)
        if args is None:
            raise Unsupported("antar", "a for loop over anything other than"
                              " range(...)", node)
        if len(node.targets) != 1:
            raise Unsupported("antar", "a for loop with %d targets"
                              % len(node.targets), node)
        if len(args) > 3:
            raise Unsupported("antar", "range(...) with %d arguments"
                              % len(args), node)
        if len(args) == 3 and _literal_number(args[2]) is None:
            raise Unsupported("antar", "a range step that is not a literal"
                              " number", node)

        name = node.targets[0]
        counter = self.temp("i")
        stop = self.temp("stop")
        step_name = self.temp("step")

        if len(args) == 1:
            start_node, stop_node, step_value = ast.Literal(0), args[0], 1
        elif len(args) == 2:
            start_node, stop_node, step_value = args[0], args[1], 1
        else:
            start_node, stop_node = args[0], args[1]
            step_value = _literal_number(args[2])

        self.emit(Kriya(SET, sthan_of(node), name=counter, expr=start_node))
        self.emit(Kriya(SET, sthan_of(node), name=stop, expr=stop_node))
        self.emit(Kriya(SET, sthan_of(node), name=step_name,
                        expr=ast.Literal(step_value)))
        # The loop name is bound once, before the head, so the body can
        # assign it without depending on block scoping.
        self.emit(Kriya(SET, sthan_of(node), name=name, expr=start_node))

        head = self.new("for-head", sthan_of(node))
        body = self.new("for-body", sthan_of(node))
        advance = self.new("for-advance", sthan_of(node))
        exit_block = self.new("for-exit", sthan_of(node))

        self.goto(head, sthan_of(node))
        self.switch_to(head)
        comparison = ast.Binary(
            ast.Identifier(counter, getattr(node, "line", 0),
                           getattr(node, "col", 0)),
            "<" if step_value >= 0 else ">",
            ast.Identifier(stop, getattr(node, "line", 0),
                           getattr(node, "col", 0)),
            getattr(node, "line", 0), getattr(node, "col", 0))
        self.condition(comparison, body, exit_block)

        self.loops.append((node.label, exit_block, advance))
        self.switch_to(body)
        self.emit(Kriya(ASSIGN, sthan_of(node), name=name,
                        expr=ast.Identifier(counter, getattr(node, "line", 0),
                                            getattr(node, "col", 0))))
        self.lower(node.body.statements)
        if not self.sealed:
            self.goto(advance, sthan_of(node))
        self.loops.pop()

        self.switch_to(advance)
        self.emit(Kriya(OPSET, sthan_of(node), name=counter, op="+",
                        expr=ast.Identifier(step_name,
                                            getattr(node, "line", 0),
                                            getattr(node, "col", 0))))
        self.goto(head, sthan_of(node))
        self.switch_to(exit_block)
        if node.orelse is not None:
            self._branch(node.orelse)

    # -- conditions --------------------------------------------------------
    def condition(self, node, yes, no):
        """Lower a test into chunav khand, keeping short-circuit visible.

        `a and b` becomes: test a, on false go to `no`, on true test b.
        `a or b` becomes: test a, on true go to `yes`, on false test b.
        A graph that hides this in an evaluator cannot be analysed.
        """
        if isinstance(node, ast.Logical) and node.op in ("and", "or"):
            middle = self.new("%s-rhs" % node.op, sthan_of(node))
            if node.op == "and":
                self.condition(node.left, middle, no)
                self.switch_to(middle)
                self.condition(node.right, yes, no)
            else:
                self.condition(node.left, yes, middle)
                self.switch_to(middle)
                self.condition(node.right, yes, no)
            return
        self.terminate(Nirnaya(CHUNAV, sthan_of(node), then=yes,
                               otherwise=no, expr=node))


def _range_args(node):
    if not isinstance(node, ast.Call):
        return None
    if not isinstance(node.callee, ast.Identifier):
        return None
    if node.callee.name != "range" or node.kwargs:
        return None
    return node.args


def _literal_int(node):
    return isinstance(node, ast.Literal) and type(node.value) is int


def _literal_number(node):
    """The value of a literal number, including a negated literal.

    `-1` is not a Literal: the parser hands over Unary('-', Literal(1)).
    A step of `-1` is still a literal for the purpose of lowering a loop,
    so the builder reads through the sign.
    """
    if isinstance(node, ast.Literal) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.Unary) and node.op in ("-", "+") and \
            _literal_int(node.operand):
        return -node.operand.value if node.op == "-" else node.operand.value
    return None


def lower_program(program, filename="<program>"):
    """Lower a parsed program into one Antar graph."""
    functions = {}
    for statement in program.statements:
        if isinstance(statement, ast.FnDecl):
            functions[statement.name] = statement

    flows = {}
    for name, declaration in functions.items():
        builder = _Nirmana(name, declaration.params, filename,
                           sthan_of(declaration))
        builder.lower(declaration.body.statements)
        if not builder.sealed:
            builder.terminate(Nirnaya(SAMAAPT, sthan_of(declaration)))
        flows[name] = builder.flow()

    main = _Nirmana("main", [], filename, Sthan(1, 1))
    for statement in program.statements:
        if isinstance(statement, ast.FnDecl):
            continue
        if isinstance(statement, (ast.StructDecl, ast.EnumDecl,
                                  ast.ProtocolDecl, ast.ImplDecl)):
            raise Unsupported("antar", "a top-level declaration of %s"
                              % type(statement).__name__, statement)
        if isinstance(statement, ast.ImportStmt):
            raise Unsupported("antar", "an import", statement)
        main.statement(statement)
    if not main.sealed:
        main.terminate(Nirnaya(SAMAAPT, Sthan(1, 1)))

    return Antar(flows=flows, main=main.flow(), filename=filename)


# ---------------------------------------------------------------------------
# The verifier — the graph must be a graph, not a hope
# ---------------------------------------------------------------------------

@dataclass
class Check:
    ok: bool = True
    problems: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def fail(self, message):
        self.ok = False
        self.problems.append(message)


def verify(antar):
    """Check the structural invariants of every flow.

    These are the rules a later stage is allowed to assume:

      * every khand has exactly one nirnaya
      * every target of a nirnaya names an existing khand
      * a chunav has both targets
      * the entry khand exists
      * every khand is reachable from the entry

A khand that is unreachable is reported in the stats as `dead`, not
silently dropped: a graph with dead code is a graph whose source had
dead code.  It is not a hard failure, because `if c { return 1 } else
{ return 2 }` legitimately leaves the join khand with no predecessor.
    """
    check = Check()
    dead = []
    for flow in antar.all_flows():
        if not flow.blocks:
            check.fail("%s: no khand" % flow.name)
            continue
        if flow.entry < 0 or flow.entry >= len(flow.blocks):
            check.fail("%s: entry khand %s does not exist"
                       % (flow.name, flow.entry))
            continue
        for block in flow.blocks:
            if block.nirnaya is None:
                check.fail("%s: khand %d has no nirnaya"
                           % (flow.name, block.index))
                continue
            if block.nirnaya.kind not in TERMINATORS:
                check.fail("%s: khand %d has the unknown nirnaya %r"
                           % (flow.name, block.index, block.nirnaya.kind))
            if block.nirnaya.kind == CHUNAV:
                if block.nirnaya.then is None or \
                        block.nirnaya.otherwise is None:
                    check.fail("%s: khand %d is a chunav with a missing"
                               " target" % (flow.name, block.index))
            for target in block.successors():
                if not isinstance(target, int) or target < 0 or \
                        target >= len(flow.blocks):
                    check.fail("%s: khand %d points at the missing khand %r"
                               % (flow.name, block.index, target))
        reachable = _reachable(flow)
        for block in flow.blocks:
            if block.index not in reachable:
                dead.append("%s:%d" % (flow.name, block.index))
        for kriya in (k for b in flow.blocks for k in b.kriya):
            if kriya.kind not in ACTIONS:
                check.fail("%s: unknown kriya %r" % (flow.name, kriya.kind))
    check.stats = antar.stats()
    check.stats["dead"] = dead
    return check


def _reachable(flow):
    seen = set()
    stack = [flow.entry]
    while stack:
        index = stack.pop()
        if index in seen or index < 0 or index >= len(flow.blocks):
            continue
        seen.add(index)
        stack.extend(flow.blocks[index].successors())
    return seen


# ---------------------------------------------------------------------------
# Analyses a later stage can build on.  These are the queries Rust's
# CfgCache answers; Bun answers them on its own graph.
# ---------------------------------------------------------------------------

def predecessors(flow):
    result = {block.index: [] for block in flow.blocks}
    for block in flow.blocks:
        for target in block.successors():
            if target in result:
                result[target].append(block.index)
    return result


def reverse_postorder(flow):
    """Depth-first postorder, reversed — the order data flow likes."""
    order = []
    seen = set()

    def walk(index):
        seen.add(index)
        for target in flow.blocks[index].successors():
            if target not in seen:
                walk(target)
        order.append(index)

    walk(flow.entry)
    return list(reversed(order))


def dominators(flow):
    """The dominator set of every reachable khand.

    A khand d dominates n when every path from the entry to n passes
    through d.  The entry dominates itself.  The answer is computed by
    the classic fixed point: start with "everything", then intersect the
    predecessors until nothing changes.
    """
    reachable = _reachable(flow)
    order = reverse_postorder(flow)
    preds = predecessors(flow)
    dom = {index: set(reachable) for index in reachable}
    dom[flow.entry] = {flow.entry}
    changed = True
    while changed:
        changed = False
        for index in order:
            if index == flow.entry:
                continue
            incoming = [p for p in preds[index] if p in reachable]
            if not incoming:
                continue
            common = set(dom[incoming[0]])
            for p in incoming[1:]:
                common &= dom[p]
            common.add(index)
            if common != dom[index]:
                dom[index] = common
                changed = True
    return dom


def loops(flow):
    """Natural loops, found from back edges.

    An edge n -> h is a back edge when h dominates n.  The loop is h plus
    every khand that reaches n without passing through h.
    """
    dom = dominators(flow)
    preds = predecessors(flow)
    found = []
    for block in flow.blocks:
        for target in block.successors():
            # A back edge n -> h exists when h dominates n, that is when
            # h is in the dominator set of n.
            if block.index in dom and target in dom.get(block.index, ()):
                body = {target, block.index}
                stack = [block.index]
                while stack:
                    index = stack.pop()
                    for p in preds.get(index, ()):
                        if p not in body:
                            body.add(p)
                            if p != target:
                                stack.append(p)
                found.append({"head": target, "tail": block.index,
                              "body": sorted(body)})
    return found


# ---------------------------------------------------------------------------
# The engine — walk the graph, do not walk the tree
# ---------------------------------------------------------------------------

class AntarMachine:
    """Run an Antar graph.

    The machine executes khand in order, and control leaves a khand only
    through its nirnaya.  Expressions are evaluated by the same evaluator
    the tree engine uses, so a value means the same thing on both.  A call
    to a function of the program runs that function's own pravah, so the
    call stack is a stack of graphs, not a stack of syntax nodes.
    """

    def __init__(self, program_args=None):
        from .interpreter import Interpreter

        self.interp = Interpreter(program_args)
        self.antar = None
        self.flows = {}
        self.depth = 0

    def run(self, antar, base_dir=None):
        import os

        self.antar = antar
        self.flows = dict(antar.flows)
        env = self.interp.globals
        env.module_dir = base_dir or os.getcwd()
        self._install_functions(env)
        return self.run_flow(antar.main, [], {}, env)

    def _install_functions(self, env):
        for name, flow in self.flows.items():
            env.define(name, Builtin(name, self._wrapper(name)), True)

    def _wrapper(self, name):
        def call(args):
            flow = self.flows[name]
            return self.run_flow(flow, list(args), {}, self.interp.globals)
        return call

    # -- the loop over khand ----------------------------------------------
    def run_flow(self, flow, args, kwargs, parent_env):
        env = Environment(parent_env)
        for spec, source, payload in ops.bind_arguments(
                flow.name, [ops.param_spec(p) for p in flow.params],
                list(args), kwargs):
            if source == "default":
                env.define(spec["name"], self.evaluate(payload, env), True)
            elif source == "kwarg":
                env.define(spec["name"], payload, True)
            else:
                env.define(spec["name"], copy_value(payload), True)

        self.depth += 1
        if self.depth > 250:
            self.depth -= 1
            raise BunRuntimeError("stack overflow")
        try:
            index = flow.entry
            steps = 0
            while True:
                steps += 1
                if steps > 10_000_000:
                    raise BunRuntimeError("antar: the graph did not settle")
                block = flow.blocks[index]
                for kriya in block.kriya:
                    self.action(kriya, env)
                nirnaya = block.nirnaya
                if nirnaya.kind == JA:
                    index = nirnaya.then
                elif nirnaya.kind == CHUNAV:
                    index = nirnaya.then if is_truthy(
                        self.evaluate(nirnaya.expr, env)) \
                        else nirnaya.otherwise
                elif nirnaya.kind == LAUT:
                    if nirnaya.expr is None:
                        return None
                    return copy_value(self.evaluate(nirnaya.expr, env))
                elif nirnaya.kind == SAMAAPT:
                    return None
                else:
                    raise BunRuntimeError("antar: the unreachable khand %d"
                                          " was reached" % index)
        finally:
            self.depth -= 1

    # -- actions -----------------------------------------------------------
    def action(self, kriya, env):
        if kriya.kind == SET:
            env.define(kriya.name, copy_value(self.evaluate(kriya.expr, env)),
                       kriya.mutable)
        elif kriya.kind == ASSIGN:
            self.interp._assign(_ident(kriya.name, kriya.sthan),
                                self.evaluate(kriya.expr, env), env)
        elif kriya.kind == OPSET:
            self.interp._op_assign(
                _ident(kriya.name, kriya.sthan), kriya.op,
                lambda: self.evaluate(kriya.expr, env), env)
        elif kriya.kind == STEP:
            self.interp._op_assign(
                _ident(kriya.name, kriya.sthan), kriya.op, lambda: 1, env)
        elif kriya.kind == EMIT:
            self.interp.last_value = self.evaluate(kriya.expr, env)
        elif kriya.kind == CHECK:
            if not is_truthy(self.evaluate(kriya.expr, env)):
                message = "assertion failed"
                if kriya.message is not None:
                    message += ": " + stringify(
                        self.evaluate(kriya.message, env))
                raise BunRuntimeError(message, kriya.sthan.line,
                                      kriya.sthan.col)
        else:
            raise BunRuntimeError("antar: unknown kriya %r" % kriya.kind)

    def evaluate(self, node, env):
        if isinstance(node, ast.Call) and isinstance(node.callee,
                                                    ast.Identifier):
            name = node.callee.name
            if name in self.flows:
                args = [self.evaluate(arg, env) for arg in node.args]
                kwargs = {key: self.evaluate(value, env)
                          for key, value in node.kwargs}
                return self.run_flow(self.flows[name], args, kwargs, env)
        return self.interp.evaluate(node, env)


def _ident(name, sthan):
    return ast.Identifier(name, sthan.line, sthan.col)


def run_program(program, filename="<program>", program_args=None,
                base_dir=None):
    """Lower, verify and run.  A broken graph never runs."""
    antar = lower_program(program, filename)
    check = verify(antar)
    if not check.ok:
        raise BunRuntimeError("antar: " + "; ".join(check.problems))
    AntarMachine(program_args).run(antar, base_dir=base_dir)
    return antar


# ---------------------------------------------------------------------------
# Dumps
# ---------------------------------------------------------------------------

def render_text(antar):
    lines = ["antar %s" % antar.filename]
    for flow in antar.all_flows():
        lines.append("")
        lines.append("pravah %s  (%d khand, %d kinara)"
                     % (flow.name, len(flow.blocks), flow.edges()))
        for block in flow.blocks:
            head = "  khand %d" % block.index
            if block.tag:
                head += "  [%s]" % block.tag
            lines.append(head)
            for kriya in block.kriya:
                lines.append("    kriya   %-34s @%s"
                             % (kriya.text(), kriya.sthan))
            if block.nirnaya is not None:
                lines.append("    nirnaya %-34s @%s"
                             % (block.nirnaya.text(), block.nirnaya.sthan))
    return "\n".join(lines)


def render_json(antar):
    import json

    payload = {"file": antar.filename, "stats": antar.stats(), "flows": []}
    for flow in antar.all_flows():
        blocks = []
        for block in flow.blocks:
            blocks.append({
                "index": block.index,
                "tag": block.tag,
                "sthan": str(block.sthan),
                "packed": block.sthan.packed,
                "kriya": [{"kind": k.kind, "text": k.text(),
                           "sthan": str(k.sthan)} for k in block.kriya],
                "nirnaya": None if block.nirnaya is None else {
                    "kind": block.nirnaya.kind,
                    "text": block.nirnaya.text(),
                    "then": block.nirnaya.then,
                    "otherwise": block.nirnaya.otherwise,
                    "sthan": str(block.nirnaya.sthan),
                },
                "successors": block.successors(),
            })
        payload["flows"].append({
            "name": flow.name,
            "entry": flow.entry,
            "blocks": blocks,
            "edges": flow.edges(),
            "reverse_postorder": reverse_postorder(flow),
            "loops": loops(flow),
        })
    return json.dumps(payload, indent=2, sort_keys=True)


def render_dot(antar):
    lines = ["digraph antar {", "  rankdir=TB;"]
    for flow in antar.all_flows():
        lines.append("  subgraph cluster_%s {" % flow.name.replace("-", "_"))
        lines.append('    label="pravah %s";' % flow.name)
        for block in flow.blocks:
            label = "khand %d\\n" % block.index
            label += "\\n".join(k.text().replace('"', "'")
                                for k in block.kriya)
            if block.kriya:
                label += "\\n"
            label += block.nirnaya.text().replace('"', "'") \
                if block.nirnaya is not None else ""
            lines.append('    b%d_%d [shape=box, label="%s"];'
                         % (id(flow) % 10000, block.index, label))
        for block in flow.blocks:
            for target in block.successors():
                lines.append("    b%d_%d -> b%d_%d;"
                             % (id(flow) % 10000, block.index,
                                id(flow) % 10000, target))
        lines.append("  }")
    lines.append("}")
    return "\n".join(lines)
