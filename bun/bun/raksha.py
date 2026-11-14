"""Raksha — Bun's memory and safety analysis.

`raksha` (रक्षा) means "protection, the keeping of a thing safe".  This is
Bun's own static pass over a program's ownership: who owns a value, who
has borrowed it, for how long, and when it is released.  It never runs the
program.

Where the idea came from
------------------------
Reading Rust's MIR showed that a borrow checker is not a pile of special
cases.  It is three ordinary questions asked on one control-flow graph:
which points can reach a point, which points a point can reach, and which
points dominate which.  A loan is live on the points that lie on some path
from its issue to its last use — a *region*, not a lexical scope.  That is
the principle borrowed here.  Nothing else is: there is no `&`, no `'a`,
no `mut`, no `unsafe`, no `Box`, no `Drop` trait and no Rust syntax at all.
Bun says ownership with `swatva`, loans with `udhaar` / `adhikar`, release
with `visarjan`, and deterministic cleanup with the `with` statement it
already had.  The vocabulary and the design are Bun's own.

The vocabulary
--------------
    swatva    one owner of one value
    sanchay   transfer of ownership (a move)
    udhaar    a shared, read-only loan
    adhikar   an exclusive, writable loan
    visarjan  release (drop)
    kosh      a cell whose aliasing is checked at run time
    kaal      the region of a loan: a set of bindu
    bindu     a program point (flow, block, index)
    nidan     a diagnostic with a primary sthan and labelled chinh
    chinh     one labelled span of a nidan
    sthan     a source position packed into one integer (from antar)
    praman    the verification of the analysis itself

What Raksha owns
----------------
Ownership, moves, loans, conflict of loans, escape of loans, release,
drop order, cleanup edges, the two error channels (`Ok`/`Err` and
`some`/`none`) and the refusal of raw-pointer-shaped names.  It reads a
Bun AST, so every engine that already runs the program can be checked
before it runs (rule R3, `static_before_run`).

What Raksha refuses by name
---------------------------
A declaration that is not a function or a statement of straight-line
control flow inside an analysed flow is refused with
`Unsupported("raksha", "...")`.  A refusal names the construct.  It never
silently analyses a shape it does not understand (rule R2).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from . import ast
from .antar import Sthan, expr_text, sthan_of
from .intcore import Unsupported

# Re-exported so a caller needs only this module for positions.
__all__ = [
    "Sthan", "sthan_of", "Chinh", "Nidan", "Bindu", "Swatva", "Udhaar",
    "PravahR", "Raksha", "Check", "CODES", "RULES",
    "analyze_source", "analyze_program", "verify",
    "render_json", "render_dot", "render_text", "render_explain",
]


# ---------------------------------------------------------------------------
# The error codes.  Bun's own numbering; the shape of a diagnostic (a code,
# a primary span, labelled spans, a hint) is the principle, not the table.
# ---------------------------------------------------------------------------

CODES = {
    "RK01": {"name": "use_after_sanchay",
             "message": "the value was already moved",
             "hint": "sanchay transfers swatva; use the new owner"},
    "RK02": {"name": "double_sanchay",
             "message": "a moved owner was moved again",
             "hint": "a value has one owner; keep the new one"},
    "RK03": {"name": "loan_conflict",
             "message": "an exclusive loan overlaps another loan's kaal",
             "hint": "shorten a kaal, or finish the earlier loan first"},
    "RK04": {"name": "write_through_shared",
             "message": "likh needs an adhikar, not an udhaar",
             "hint": "take an adhikar when the value must be written"},
    "RK05": {"name": "move_while_loaned",
             "message": "the owner is loaned out",
             "hint": "let every kaal end before a move or a visarjan"},
    "RK06": {"name": "use_after_visarjan",
             "message": "the value was already released",
             "hint": "swatva ends at visarjan; do not use the name again"},
    "RK07": {"name": "double_visarjan",
             "message": "the owner was released twice",
             "hint": "with rk.swatva(v) as a { ... } releases it for you"},
    "RK08": {"name": "loan_escape",
             "message": "a loan cannot leave the flow that owns it",
             "hint": "return the value, or transfer swatva with sanchay"},
    "RK09": {"name": "owner_leak",
             "message": "the owner is still live at the end of the flow",
             "hint": "use with ... as ..., or call visarjan, or sanchay it"},
    "RK10": {"name": "unhandled_parinam",
             "message": "a parinam (Ok/Err) was discarded",
             "hint": "inspect it with parinam_* or pass it on with ?"},
    "RK11": {"name": "unchecked_vikalp",
             "message": "a vikalp (some/none) was taken without a check",
             "hint": "use is_some / is_none before taking the value"},
    "RK12": {"name": "unsafe_refused",
             "message": "a raw-pointer-shaped name is not part of Bun",
             "hint": "Bun has no unsafe; use swatva and a loan"},
    "RK13": {"name": "spawn_loan",
             "message": "a loan cannot cross into a spawned task",
             "hint": "transfer swatva into the task, or join before the loan"},
    "RK14": {"name": "drop_order",
             "message": "the releases are not in reverse declaration order",
             "hint": "Bun releases in the reverse order of declaration"},
}

RULES = [
    {"id": c, "name": CODES[c]["name"], "text": CODES[c]["message"],
     "rust_seed": "principle borrowed from Rust's ownership and borrow rules; "
                  "no Rust syntax is borrowed",
     "bun_rule": r}
    for c, r in zip(
        sorted(CODES),
        ["R1", "R1", "R3", "R2", "R3", "R1", "R1",
         "R3", "R3", "R6", "R6", "R2", "R4", "R1"])
]

# The universal names of the bun:raksha module.  They are names, not
# keywords, so every one of the 118 language packs can write them today.
RAKSHA_FNS = frozenset({
    "swatva", "sanchay", "udhaar", "adhikar", "padh", "likh",
    "visarjan", "kosh", "kosh_padh", "kosh_likh",
    "parinam_map", "parinam_chain", "parinam_or",
    "vikalp_map", "vikalp_or", "niyam", "codes", "audit", "summary",
})

UNSAFE_NAMES = frozenset({
    "unsafe", "raw_pointer", "deref_raw", "ffi_load", "ptr_read",
    "ptr_write", "transmute", "mem_forget",
})

BORROWED_KEYWORDS = frozenset({"mut", "ref", "box", "unsafe"})

# After a visarjan the value is gone, but the owner record stays as the
# ledger of what happened.  Reading these fields is reading the ledger,
# not using the value; RK06 must not fire on them.
OWNER_METADATA = frozenset({
    "id", "kind", "sthiti", "drop_log", "loans", "origin", "name",
    "declaration", "state",
})


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Chinh:
    """One labelled span of a nidan."""

    sthan: Sthan
    text: str
    primary: bool = False


class Nidan:
    """A diagnostic: one code, one primary sthan, labelled chinh, a hint."""

    def __init__(self, code, message=None, primary=None, labels=None,
                 hint=None, notes=None, filename="<program>"):
        self.code = code
        self.name = CODES.get(code, {}).get("name", "unknown")
        self.message = message or CODES.get(code, {}).get("message", "")
        self.primary = primary or Sthan()
        self.labels = list(labels or [])
        self.hint = hint or CODES.get(code, {}).get("hint", "")
        self.notes = list(notes or [])
        self.filename = filename

    def to_dict(self):
        return {
            "code": self.code,
            "name": self.name,
            "message": self.message,
            "file": self.filename,
            "primary": str(self.primary),
            "packed": self.primary.packed,
            "labels": [{"at": str(c.sthan), "text": c.text,
                        "primary": c.primary} for c in self.labels],
            "hint": self.hint,
            "notes": list(self.notes),
        }

    def render(self, source=""):
        lines = source.splitlines() if source else []
        out = ["raksha[%s]: %s" % (self.code, self.message),
               "  --> %s:%s" % (self.filename, self.primary)]
        shown = {self.primary.line} | {c.sthan.line for c in self.labels}
        shown = {n for n in shown if n > 0}
        if not shown:
            for note in self.notes:
                out.append("   = nidan: %s" % note)
            if self.hint:
                out.append("   = sulabh: %s" % self.hint)
            return "\n".join(out)
        lo = max(1, min(shown) - 1)
        hi = max(shown) + 1
        out.append("   |")
        for number in range(lo, hi + 1):
            text = lines[number - 1] if number - 1 < len(lines) else ""
            out.append("%3d | %s" % (number, text))
            marks = [c for c in self.labels if c.sthan.line == number]
            if self.primary.line == number and not any(c.primary for c in marks):
                marks.insert(0, Chinh(self.primary, self.message, True))
            for chinh in marks:
                col = max(1, chinh.sthan.col)
                width = max(1, min(max(1, len(text) - col + 1), 28))
                caret = "^" if chinh.primary else "-"
                out.append("   | %s%s %s" % (" " * (col - 1), caret * width,
                                             chinh.text))
        out.append("   |")
        for note in self.notes:
            out.append("   = nidan: %s" % note)
        if self.hint:
            out.append("   = sulabh: %s" % self.hint)
        return "\n".join(out)

    def __str__(self):
        return "raksha[%s]: %s at %s" % (self.code, self.message, self.primary)


# ---------------------------------------------------------------------------
# The memory flow
# ---------------------------------------------------------------------------

@dataclass
class Bindu:
    """One program point — the (flow, block, index) that MIR calls Location."""

    flow: str
    block: int
    index: int
    sthan: Sthan = field(default_factory=Sthan)
    text: str = ""
    kind: str = ""

    def key(self):
        return (self.flow, self.block, self.index)

    def label(self):
        return "%s:%d:%d" % self.key()

    def __str__(self):
        return "%-8s %s  %s" % (self.kind, self.label(), self.text)


@dataclass
class Swatva:
    """One owner of one value."""

    id: int
    name: str
    sthan: Sthan
    state: str = "live"          # live | moved | dropped | transferred
    loans: list = field(default_factory=list)
    drop_at: object = None
    declaration: int = 0
    scope: int = 0


@dataclass
class Udhaar:
    """One loan.  `region` is a set of Bindu.key(), i.e. a kaal."""

    id: int
    owner: int
    kind: str                    # udhaar | adhikar
    sthan: Sthan
    issued: object = None
    region: set = field(default_factory=set)
    last_use: object = None
    live: bool = True

    def kind_text(self):
        return "adhikar" if self.kind == "adhikar" else "udhaar"


@dataclass
class PravahR:
    """The memory flow of one function."""

    name: str
    points: list = field(default_factory=list)
    edges: list = field(default_factory=list)
    entry: object = None
    exits: list = field(default_factory=list)
    owners: list = field(default_factory=list)
    loans: list = field(default_factory=list)
    drops: list = field(default_factory=list)
    cleanup: list = field(default_factory=list)
    sthan: Sthan = field(default_factory=Sthan)

    def edges_from(self, key):
        return [b for a, b in self.edges if a == key]

    def edges_to(self, key):
        return [a for a, b in self.edges if b == key]

    def point_map(self):
        return {p.key(): p for p in self.points}

    def predecessors(self, key):
        return self.edges_to(key)

    def reverse_postorder(self):
        """Depth-first postorder, reversed — the order a forward pass wants."""
        successors = {}
        for a, b in self.edges:
            successors.setdefault(a, []).append(b)
        seen, post = set(), []

        def visit(node):
            if node in seen:
                return
            seen.add(node)
            for nxt in successors.get(node, []):
                visit(nxt)
            post.append(node)

        if self.entry is not None:
            visit(self.entry)
        for p in self.points:
            visit(p.key())
        return list(reversed(post))

    def dominators(self):
        """Iterative fixed point: dom(entry)={entry}, else all points."""
        keys = [p.key() for p in self.points]
        allset = set(keys)
        dom = {k: set(allset) for k in keys}
        if self.entry is not None:
            dom[self.entry] = {self.entry}
        preds = {k: [] for k in keys}
        for a, b in self.edges:
            if a in preds and b in preds:
                preds[b].append(a)
        changed = True
        while changed:
            changed = False
            for k in keys:
                if k == self.entry:
                    continue
                incoming = preds[k]
                if incoming:
                    new = set(allset)
                    for p in incoming:
                        new &= dom[p]
                else:
                    new = set()
                new.add(k)
                if new != dom[k]:
                    dom[k] = new
                    changed = True
        return dom

    def loops(self):
        """Natural loops: a back edge n -> h where h dominates n."""
        dom = self.dominators()
        found = []
        for a, b in self.edges:
            if b in dom.get(a, set()) and a != b:
                found.append((b, a))
        return sorted(set(found))


_ANUMATI = re.compile(
    r"^\s*//\s*raksha\s*:\s*allow\s+(RK\d{2})\s*:\s*(.+?)\s*$")


@dataclass
class Anumati:
    """One named, auditable exception.

    `anumati` (अनुमति) means permission.  It is a plain Bun comment, not an
    attribute and not a keyword: `// raksha:allow RK01: <reason>` written on
    the line above a deliberately unsafe line.  It permits exactly one code
    on exactly one line.  `verify()` refuses any anumati that suppressed
    nothing, so a stale or blanket exception cannot hide a real diagnostic.
    """

    code: str
    line: int
    pragma_line: int
    reason: str
    used: int = 0

    def to_dict(self):
        return {"code": self.code, "line": self.line,
                "pragma_line": self.pragma_line, "reason": self.reason,
                "used": self.used}


def _allowances(source):
    """Read `raksha:allow` pragmas.  A pragma targets the next source line."""
    lines = (source or "").splitlines()
    out = []
    for index, text in enumerate(lines, 1):
        match = _ANUMATI.match(text)
        if not match:
            continue
        target = index + 1
        while target <= len(lines) and (
                not lines[target - 1].strip()
                or _ANUMATI.match(lines[target - 1])):
            target += 1
        if target > len(lines):
            target = index          # invalid: verify() will refuse it
        out.append(Anumati(match.group(1), target, index, match.group(2)))
    return out


def _apply_allowances(raksha):
    """Move permitted nidan out of `diagnostics` into the visible ledger."""
    kept = []
    for nidan in raksha.diagnostics:
        permit = None
        for anumati in raksha.allowances:
            if anumati.code == nidan.code and \
                    anumati.line == nidan.primary.line:
                permit = anumati
                break
        if permit is None:
            kept.append(nidan)
        else:
            permit.used += 1
            nidan.allowed_by = permit.reason
            raksha.allowed.append(nidan)
    raksha.diagnostics = kept


@dataclass
class Raksha:
    """The whole-program analysis."""

    flows: dict = field(default_factory=dict)
    main: object = None
    diagnostics: list = field(default_factory=list)
    allowed: list = field(default_factory=list)
    allowances: list = field(default_factory=list)
    filename: str = "<program>"
    source: str = ""

    def all_flows(self):
        return list(self.flows.values()) + ([self.main] if self.main else [])

    def stats(self):
        flows = self.all_flows()
        return {
            "flows": len(flows),
            "points": sum(len(f.points) for f in flows),
            "edges": sum(len(f.edges) for f in flows),
            "owners": sum(len(f.owners) for f in flows),
            "loans": sum(len(f.loans) for f in flows),
            "drops": sum(len(f.drops) for f in flows),
            "cleanup": sum(len(f.cleanup) for f in flows),
            "loops": sum(len(f.loops()) for f in flows),
            "diagnostics": len(self.diagnostics),
            "allowed": len(self.allowed),
            "allowances": len(self.allowances),
        }

    def regions(self):
        out = {}
        for flow in self.all_flows():
            for loan in flow.loans:
                out["%s/loan%d" % (flow.name, loan.id)] = sorted(
                    "%s:%d:%d" % k for k in loan.region)
        return out


@dataclass
class Check:
    ok: bool
    problems: list
    stats: dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call_parts(node):
    """(namespace, name) of a call, or (None, None)."""
    if isinstance(node, ast.MethodCall):
        receiver = node.receiver
        if isinstance(receiver, ast.Identifier):
            return (receiver.name, node.method)
        return (None, node.method)
    if not isinstance(node, ast.Call):
        return (None, None)
    callee = node.callee
    if isinstance(callee, ast.Attribute):
        if isinstance(callee.object, ast.Identifier):
            return (callee.object.name, callee.name)
        return (None, callee.name)
    if isinstance(callee, ast.Identifier):
        return (None, callee.name)
    return (None, None)


def _children(node):
    """Child expressions of any AST node, for a conservative walk."""
    if node is None:
        return []
    if isinstance(node, (ast.Literal, ast.Identifier)):
        return []
    if isinstance(node, ast.Call):
        return [node.callee] + list(node.args) + [v for _, v in node.kwargs]
    if isinstance(node, ast.Attribute):
        return [node.object]
    if isinstance(node, (ast.Binary, ast.Logical)):
        return [node.left, node.right]
    if isinstance(node, ast.Unary):
        return [node.operand]
    if isinstance(node, ast.Unwrap):
        return [node.expr]
    if isinstance(node, ast.Index):
        return [node.target, node.index]
    if isinstance(node, ast.ListLiteral):
        return list(node.elements)
    if isinstance(node, ast.DictLiteral):
        result = []
        for entry in node.entries:
            if isinstance(entry, (tuple, list)):
                result.extend(entry)
            else:
                result.append(entry)
        return result
    if isinstance(node, ast.MethodCall):
        return [node.receiver] + list(node.args)
    if isinstance(node, ast.FString):
        return [p.expr for p in node.parts if getattr(p, "expr", None)]
    if isinstance(node, ast.Comprehension):
        return [node.element] + [c.iterable for c in node.clauses]
    return []


def _text(node):
    """Quote an expression in Raksha's own dump.

    antar's renderer predates `MethodCall` in this position and assumes a
    different name for list elements, so Raksha quotes expressions itself.
    A dump quotes the program; it never pretends to be the parser.
    """
    if node is None:
        return "-"
    if isinstance(node, ast.Literal):
        return '"%s"' % node.value if isinstance(node.value, str) \
            else repr(node.value)
    if isinstance(node, ast.Identifier):
        return node.name
    if isinstance(node, ast.MethodCall):
        return "%s.%s(%s)" % (
            _text(node.receiver), node.method,
            ", ".join(_text(a) for a in node.args))
    if isinstance(node, ast.Call):
        args = [_text(a) for a in node.args]
        args += ["%s: %s" % (k, _text(v)) for k, v in node.kwargs]
        return "%s(%s)" % (_text(node.callee), ", ".join(args))
    if isinstance(node, ast.Attribute):
        return "%s.%s" % (_text(node.object), node.name)
    if isinstance(node, ast.Index):
        return "%s[%s]" % (_text(node.target), _text(node.index))
    if isinstance(node, (ast.Binary, ast.Logical)):
        return "(%s %s %s)" % (_text(node.left), node.op, _text(node.right))
    if isinstance(node, ast.Unary):
        return "%s%s" % (node.op, _text(node.operand))
    if isinstance(node, ast.Unwrap):
        return "%s?" % _text(node.expr)
    if isinstance(node, ast.ListLiteral):
        return "[%s]" % ", ".join(_text(i) for i in node.elements)
    if isinstance(node, ast.DictLiteral):
        return "{%s}" % ", ".join(type(e).__name__ for e in node.entries)
    return type(node).__name__


def _stmt_exprs(statement):
    """Expressions of a statement, for walking a spawned function body.

    A `spawn { ... }` carries an anonymous function as an argument.  Its
    body is a different flow, so Raksha does not emit bindu for it; it
    only needs to know which names the body reads (RK13).
    """
    if statement is None:
        return []
    out = []
    if isinstance(statement, ast.Block):
        for item in statement.statements:
            out.extend(_stmt_exprs(item))
        return out
    for name in ("value", "expr", "condition", "iterable", "subject",
                 "target", "index", "operand"):
        value = getattr(statement, name, None)
        if value is not None and not isinstance(
                value, (list, ast.Block, str, int, float, bool)):
            out.append(value)
    for name in ("args", "elements"):
        value = getattr(statement, name, None)
        if isinstance(value, list):
            out.extend(x for x in value
                       if not isinstance(x, (str, int, float, bool)))
    for name in ("then_branch", "else_branch", "body", "try_block",
                 "catch_block", "finally_body", "orelse"):
        value = getattr(statement, name, None)
        if isinstance(value, (ast.Block, list)):
            out.extend(_stmt_exprs(value))
    if isinstance(statement, ast.WithStmt):
        out.extend(item.expr for item in statement.items)
    return out


def _statements_of(block):
    """A Block, a list of statements, or None -> a list."""
    if block is None:
        return []
    if isinstance(block, ast.Block):
        return list(block.statements)
    if isinstance(block, list):
        return list(block)
    return [block]


def _refuse(node):
    label = type(node).__name__
    friendly = {
        "StructDecl": "a struct declaration",
        "EnumDecl": "an enum declaration",
        "ImplDecl": "an impl declaration",
        "ProtocolDecl": "a protocol declaration",
        "YieldStmt": "a yield statement",
        "UnpackStmt": "an unpacking assignment",
    }.get(label, "a %s statement" % label)
    raise Unsupported("raksha", "%s (%s)" % (friendly, label), node)


# ---------------------------------------------------------------------------
# Lowering + analysis of one flow
# ---------------------------------------------------------------------------

class _Vishleshan:
    """The builder and analyser of one pravah.

    `vishleshan` (विश्लेषण) means analysis.  It lowers statements to bindu,
    walks expressions for ownership events, infers each loan's kaal on the
    graph, and reports nidan.
    """

    def __init__(self, name, alias, filename):
        self.name = name
        self.alias = alias
        self.filename = filename
        self.flow = PravahR(name=name)
        self._preds = [None]
        self._block = 0
        self._index = 0
        self._owner_seq = 0
        self._loan_seq = 0
        self._owner_of = {}         # variable name -> owner id
        self._loan_of = {}          # variable name -> loan id
        self._owners = {}           # owner id -> Swatva
        self._loans = {}            # loan id -> Udhaar
        self._current = None
        self._in_spawn = 0
        self._scope_stack = []      # list of list[owner id]
        self._drop_order_expected = []
        self._with_count = 0
        self._break_preds = []
        self._pending_releases = []
        self._scope = 0
        self._scope_seq = 0
        self.diagnostics = []

    # -- points and edges ---------------------------------------------------

    def _emit(self, kind, text, node, preds=None):
        if preds is None:
            preds = self._preds
        point = Bindu(self.name, self._block, self._index,
                      sthan_of(node) if node is not None else Sthan(),
                      text, kind)
        self.flow.points.append(point)
        self._index += 1
        for source in preds:
            if source is not None:
                self.flow.edges.append((source, point.key()))
        self._preds = [point.key()]
        if self.flow.entry is None:
            self.flow.entry = point.key()
        self._current = point.key()
        return point

    def _new_block(self):
        self._block += 1
        self._index = 0

    def _nidan(self, code, node, labels=None, notes=None, message=None):
        at = sthan_of(node) if node is not None else Sthan()
        item = Nidan(code, message=message, primary=at,
                     labels=labels or [Chinh(at, "yahan", True)],
                     notes=notes or [CODES[code]["name"]],
                     filename=self.filename)
        self.diagnostics.append(item)
        return item

    # -- owners and loans ---------------------------------------------------

    def _new_owner(self, name, node):
        self._owner_seq += 1
        owner = Swatva(self._owner_seq, name, sthan_of(node),
                       declaration=self._owner_seq, scope=self._scope)
        self._owners[owner.id] = owner
        self.flow.owners.append(owner)
        if name:
            self._owner_of[name] = owner.id
        for scope in self._scope_stack:
            scope.append(owner.id)
        return owner

    def _new_loan(self, owner, kind, node, name=None):
        self._loan_seq += 1
        loan = Udhaar(self._loan_seq, owner.id, kind, sthan_of(node),
                      issued=self._current)
        loan.last_use = self._current
        self._loans[loan.id] = loan
        self.flow.loans.append(loan)
        owner.loans.append(loan.id)
        if name:
            self._loan_of[name] = loan.id
        return loan

    def _owner_state_check(self, owner, node, what):
        if owner.state == "moved":
            self._nidan("RK02" if what == "sanchay" else "RK01", node,
                        notes=["swatva pehle hi sanchay ho chuka hai",
                               "use_after_sanchay"])
        elif owner.state == "dropped":
            self._nidan("RK06", node,
                        notes=["swatva visarjan ho chuka hai",
                               "use_after_visarjan"])
        return owner.state == "live"

    def _live_loans(self, owner):
        return [self._loans[i] for i in owner.loans
                if i in self._loans and self._loans[i].live]

    # -- expression walk ----------------------------------------------------

    def _eval(self, node):
        """Walk an expression; return a small descriptor of its value."""
        if node is None:
            return None
        if isinstance(node, ast.Identifier):
            if node.name in BORROWED_KEYWORDS:
                self._nidan("RK12", node,
                            notes=["a Rust keyword is not a Bun construct",
                                   "unsafe_refused"])
            if node.name in UNSAFE_NAMES:
                self._nidan("RK12", node,
                            notes=["Bun keeps no raw pointers",
                                   "unsafe_refused"])
            if node.name in self._owner_of:
                owner = self._owners[self._owner_of[node.name]]
                self._owner_state_check(owner, node, "use")
                return ("owner", owner.id)
            if node.name in self._loan_of:
                return ("loan", self._loan_of[node.name])
            return ("name", node.name)

        if isinstance(node, (ast.Call, ast.MethodCall)):
            namespace, name = _call_parts(node)
            if name == "spawn":
                self._in_spawn += 1
            values = []
            for child in _children(node):
                if isinstance(child, ast.FnDecl):
                    # A spawned body is a separate flow.  Walk it for
                    # names only; never emit its bindu into this flow.
                    for expr in _stmt_exprs(child.body):
                        self._eval(expr)
                    values.append(None)
                else:
                    values.append(self._eval(child))
            if name == "spawn":
                self._in_spawn -= 1
            for value in values:
                if value and value[0] == "loan" and self._in_spawn:
                    self._nidan("RK13", node,
                                notes=["a kaal cannot cross a task boundary",
                                       "spawn_loan"])
            if name in UNSAFE_NAMES:
                self._nidan("RK12", node,
                            notes=["Bun refuses raw pointers by name",
                                   "unsafe_refused"])
            if isinstance(node, ast.Call) and isinstance(node.callee,
                                                         ast.Attribute):
                self._eval(node.callee.object)
            if namespace == self.alias and name in RAKSHA_FNS:
                return self._raksha_call(name, node, values)
            if name in ("Ok", "Err"):
                return ("parinam", name)
            if name in ("some", "none"):
                return ("vikalp", name)
            if name == "is_some" or name == "is_none":
                return ("checked", name)
            if name in ("is_ok", "is_err"):
                return ("checked", name)
            return ("call", name)

        if isinstance(node, ast.Index):
            key = node.index
            field = key.value if isinstance(key, ast.Literal) else None
            target = node.target
            if (isinstance(field, str) and field in OWNER_METADATA
                    and isinstance(target, ast.Identifier)
                    and target.name in self._owner_of):
                # Reading the release ledger is not using the value.
                return ("metadata", field)
            values = [self._eval(child) for child in _children(node)]
            for value in values:
                if value and value[0] == "loan" and self._in_spawn:
                    self._nidan("RK13", node,
                                notes=["a kaal cannot cross a task boundary",
                                       "spawn_loan"])
            return values[0] if values else None

        if isinstance(node, ast.Attribute):
            if (node.name in OWNER_METADATA
                    and isinstance(node.object, ast.Identifier)
                    and node.object.name in self._owner_of):
                return ("metadata", node.name)
            values = [self._eval(child) for child in _children(node)]
            return values[0] if values else None

        if isinstance(node, (ast.ListLiteral, ast.DictLiteral)):
            values = [self._eval(child) for child in _children(node)]
            for value in values:
                if value and value[0] == "loan":
                    self._nidan("RK08", node,
                                notes=["a loan was stored in a container",
                                       "loan_escape"])
            return ("container", len(values))

        values = [self._eval(child) for child in _children(node)]
        for value in values:
            if value and value[0] == "loan" and self._in_spawn:
                self._nidan("RK13", node,
                            notes=["a kaal cannot cross a task boundary",
                                   "spawn_loan"])
        return values[0] if values else None

    def _raksha_call(self, name, node, values):
        args = node.args
        first = values[1] if len(values) > 1 else None   # values[0] is callee
        # values is _children(node) = [callee, arg0, arg1, ...]
        argvals = values[1:]

        if name == "swatva":
            owner = self._new_owner(None, node)
            return ("owner", owner.id)

        if name == "sanchay":
            if argvals and argvals[0] and argvals[0][0] == "owner":
                owner = self._owners[argvals[0][1]]
                if self._owner_state_check(owner, node, "sanchay"):
                    # A release is checked after kaal inference: a loan
                    # whose last use is already past is not live here.
                    self._pending_releases.append(
                        (self._current, owner.id, node, "sanchay"))
                    owner.state = "moved"
                    new = self._new_owner(None, node)
                    return ("owner", new.id)
            return ("owner", None)

        if name in ("udhaar", "adhikar"):
            if argvals and argvals[0] and argvals[0][0] == "owner" \
                    and argvals[0][1]:
                owner = self._owners[argvals[0][1]]
                if self._owner_state_check(owner, node, "loan"):
                    loan = self._new_loan(owner, name, node)
                    return ("loan", loan.id)
            return ("loan", None)

        if name == "padh":
            for value in argvals:
                if value and value[0] == "loan" and value[1]:
                    loan = self._loans.get(value[1])
                    if loan:
                        loan.last_use = self._current
            return ("value", "padh")

        if name == "likh":
            for value in argvals:
                if value and value[0] == "loan" and value[1]:
                    loan = self._loans.get(value[1])
                    if loan:
                        if loan.kind != "adhikar":
                            self._nidan("RK04", node,
                                        notes=["udhaar sirf padhne ke liye",
                                               "write_through_shared"])
                        loan.last_use = self._current
            return ("value", "likh")

        if name == "visarjan":
            for value in argvals:
                if value and value[0] == "owner" and value[1]:
                    self._drop(value[1], node)
            return ("value", "visarjan")

        if name in ("parinam_map", "parinam_chain", "parinam_or"):
            return ("parinam", name)
        if name in ("vikalp_map", "vikalp_or"):
            return ("vikalp", name)
        return ("call", name)

    def _drop(self, owner_id, node):
        owner = self._owners.get(owner_id)
        if owner is None:
            return
        if owner.state == "dropped":
            self._nidan("RK07", node,
                        notes=["visarjan do baar nahin",
                               "double_visarjan"])
            return
        if owner.state == "moved":
            # The use of the name already reported RK01 on the way in.
            return
        self._pending_releases.append(
            (self._current, owner.id, node, "visarjan"))
        for loan in self._live_loans(owner):
            loan.live = False
        owner.state = "dropped"
        owner.drop_at = self._current
        self.flow.drops.append((self._current, owner.id))

    # -- statements ---------------------------------------------------------

    def lower(self, statements):
        self._preds = [None]
        self._lower_seq(statements, [None])
        self._infer_regions()
        self._check_releases()
        self._detect_conflicts()
        self._check_scope_exits()
        self._finalize()
        return self.flow

    def _lower_seq(self, statements, preds):
        self._preds = list(preds)
        for statement in statements:
            self._lower_stmt(statement)
        return list(self._preds)

    def _lower_body(self, block, preds):
        return self._lower_seq(_statements_of(block), preds)

    def _lower_stmt(self, node):
        if isinstance(node, ast.ImportStmt):
            self._emit("call", "import %s" % node.path, node)
            return

        if isinstance(node, (ast.StructDecl, ast.EnumDecl, ast.ImplDecl,
                             ast.ProtocolDecl, ast.YieldStmt, ast.UnpackStmt)):
            _refuse(node)

        if isinstance(node, ast.FnDecl):
            # A nested function is its own flow; the outer flow only sees
            # the declaration.  Top-level functions are filtered out before
            # lowering.
            self._emit("call", "fn %s" % node.name, node)
            return

        if isinstance(node, ast.Block):
            self._lower_body(node, self._preds)
            return

        if isinstance(node, ast.LetStmt):
            point = self._emit("set", "set %s = %s" % (
                node.name, _text(node.value)), node)
            self._current = point.key()
            value = self._eval(node.value)
            self._bind(node.name, value, node)
            return

        if isinstance(node, ast.AssignStmt):
            point = self._emit("assign", "assign %s = %s" % (
                _text(node.target), _text(node.value)), node)
            self._current = point.key()
            self._eval(node.target)
            value = self._eval(node.value)
            if isinstance(node.target, ast.Identifier):
                self._bind(node.target.name, value, node)
            return

        if isinstance(node, (ast.OpAssignStmt, ast.IncDecStmt,
                             ast.AssertStmt, ast.DelStmt)):
            point = self._emit("call", type(node).__name__, node)
            self._current = point.key()
            for child in _children(node):
                self._eval(child)
            return

        if isinstance(node, ast.ExprStmt):
            point = self._emit("call", _text(node.expr), node)
            self._current = point.key()
            value = self._eval(node.expr)
            if value and value[0] == "parinam":
                self._nidan("RK10", node,
                            notes=["Ok/Err ka parinam kaheen nahin gaya",
                                   "unhandled_parinam"])
            elif value and value[0] == "vikalp":
                self._nidan("RK11", node,
                            notes=["vikalp ko bina jaanch ke chhod diya",
                                   "unchecked_vikalp"])
            return

        if isinstance(node, ast.ReturnStmt):
            point = self._emit("return", "laut %s" % _text(node.value), node)
            self._current = point.key()
            value = self._eval(node.value)
            if value and value[0] == "loan":
                self._nidan("RK08", node,
                            notes=["ek loan lautaya ja raha hai",
                                   "loan_escape"])
            elif value and value[0] == "owner" and value[1]:
                owner = self._owners.get(value[1])
                if owner and owner.state == "live":
                    owner.state = "transferred"
            self.flow.exits.append(point.key())
            self._preds = []
            return

        if isinstance(node, (ast.BreakStmt, ast.ContinueStmt)):
            point = self._emit("branch", type(node).__name__, node)
            self._break_preds.append(point.key())
            self._preds = []
            return

        if isinstance(node, ast.ThrowStmt):
            point = self._emit("return", "throw %s" % _text(node.value),
                               node)
            self._current = point.key()
            self._eval(node.value)
            self.flow.exits.append(point.key())
            self._preds = []
            return

        if isinstance(node, ast.IfStmt):
            branch = self._emit("branch", "chunav %s" %
                                _text(node.condition), node)
            self._current = branch.key()
            self._eval(node.condition)
            then_preds = self._lower_body(node.then_branch, [branch.key()])
            if node.else_branch is not None:
                else_preds = self._lower_body(node.else_branch,
                                              [branch.key()])
            else:
                else_preds = [branch.key()]
            join = self._emit("join", "join", node,
                              preds=then_preds + else_preds)
            self._preds = [join.key()]
            return

        if isinstance(node, (ast.WhileStmt, ast.ForStmt)):
            head = self._emit("branch", "chunav %s" % _text(
                node.condition if isinstance(node, ast.WhileStmt)
                else node.iterable), node)
            self._current = head.key()
            self._eval(node.condition if isinstance(node, ast.WhileStmt)
                       else node.iterable)
            saved = self._break_preds
            self._break_preds = []
            body_preds = self._lower_body(node.body, [head.key()])
            for key in body_preds:
                self.flow.edges.append((key, head.key()))
            breaks = self._break_preds
            self._break_preds = saved
            self._emit("join", "join", node,
                       preds=[head.key()] + breaks)
            return

        if isinstance(node, ast.WithStmt):
            self._with_count += 1
            saved_scope = self._scope
            self._scope_seq += 1
            self._scope = self._scope_seq
            bound = []
            last = None
            for item in node.items:
                point = self._emit("set", "set %s = %s" % (
                    item.name, _text(item.expr)), item)
                self._current = point.key()
                value = self._eval(item.expr)
                self._bind(item.name, value, item)
                if value and value[0] == "owner" and value[1]:
                    owner = self._owners[value[1]]
                    owner.name = item.name
                    bound.append(owner.id)
                last = point.key()
            if last is None:
                last = self._preds[-1] if self._preds else None
            body_preds = self._lower_body(node.body, [last])
            # Bun's `with` calls __exit__ on both the normal and the error
            # path.  The error path is an unwind edge: it reaches the same
            # release point without going through the body.
            entry = last
            drop = self._emit("drop", "visarjan (with)", node,
                              preds=body_preds)
            if entry is not None:
                self.flow.cleanup.append((entry, drop.key()))
                self.flow.edges.append((entry, drop.key()))
            for owner_id in reversed(bound):
                self._drop(owner_id, node)
            self._drop_order_expected.extend(reversed(bound))
            self._scope = saved_scope
            self._preds = [drop.key()]
            return

        if isinstance(node, ast.TryStmt):
            try_preds = self._lower_body(node.try_block, self._preds)
            catch_preds = []
            if node.catch_block is not None:
                catch_preds = self._lower_body(node.catch_block,
                                              [self.flow.entry])
            tail = try_preds + catch_preds
            if node.finally_body is not None:
                finally_preds = self._lower_body(node.finally_body, tail)
                first = self.flow.points[-1].key() if self.flow.points else None
                for key in try_preds:
                    self.flow.cleanup.append((key, first))
                    if first is not None:
                        self.flow.edges.append((key, first))
                tail = finally_preds
            self._preds = tail
            return

        if isinstance(node, ast.ScopeStmt):
            self._scope_stack.append([])
            body_preds = self._lower_body(node.body, self._preds)
            scope = self._scope_stack.pop()
            for owner_id in reversed(scope):
                owner = self._owners.get(owner_id)
                if owner and owner.state == "live":
                    owner.state = "transferred"
            self._preds = body_preds
            return

        if isinstance(node, ast.MatchStmt):
            point = self._emit("branch", "match %s" % _text(node.subject),
                               node)
            self._current = point.key()
            self._eval(node.subject)
            arms = []
            for case in node.cases:
                body = getattr(case, "body", None) or getattr(case, "result",
                                                              None)
                arms.extend(self._lower_body(body, [point.key()]))
            self._emit("join", "join", node, preds=arms or [point.key()])
            return

        # Anything else is a straight-line statement we can quote but not
        # interpret: refuse it by name rather than pretend we understood it.
        _refuse(node)

    def _bind(self, name, value, node):
        if not name or not value:
            return
        if value[0] == "owner" and value[1]:
            owner = self._owners[value[1]]
            owner.name = name
            self._owner_of[name] = owner.id
        elif value[0] == "loan" and value[1]:
            self._loan_of[name] = value[1]
        elif value[0] in ("parinam", "vikalp"):
            pass

    # -- region inference ---------------------------------------------------

    def _reach_from(self, start, reverse=False):
        adjacency = {}
        for a, b in self.flow.edges:
            if reverse:
                adjacency.setdefault(b, []).append(a)
            else:
                adjacency.setdefault(a, []).append(b)
        seen, stack = set(), [start]
        while stack:
            key = stack.pop()
            if key in seen:
                continue
            seen.add(key)
            for nxt in adjacency.get(key, []):
                if nxt not in seen:
                    stack.append(nxt)
        return seen

    def _infer_regions(self):
        """A kaal is the set of points on some path from issue to last use.

        This is the NLL principle: a loan lives on points, not on lexical
        braces.  Back edges are ordinary edges, so a loan used inside a
        loop has a region that covers the loop body.
        """
        for loan in self.flow.loans:
            end = loan.last_use or loan.issued
            if end is None:
                loan.region = set()
                continue
            forward = self._reach_from(loan.issued)
            backward = self._reach_from(end, reverse=True)
            loan.region = forward & backward
            if end not in loan.region:
                loan.region.add(end)
            if loan.issued not in loan.region:
                loan.region.add(loan.issued)
            loan.live = True

    def _check_releases(self):
        """A release is legal only when no kaal still covers its point.

        This is the NLL answer to the classic "borrow still active" error:
        the loan ends at its last use, not at the end of a brace.  A loan
        used two lines before the release does not conflict with it.
        """
        for key, owner_id, node, what in self._pending_releases:
            for loan in self.flow.loans:
                if loan.owner != owner_id or not loan.live:
                    continue
                if loan.issued == key:
                    continue
                if key in loan.region:
                    labels = [
                        Chinh(loan.sthan, "%s yahan jaari" %
                              loan.kind_text(), False),
                        Chinh(sthan_of(node), "%s yahan" % what, True),
                    ]
                    self._nidan("RK05", node, labels=labels,
                                notes=["ek kaal is bindu par abhi jeevit hai",
                                       "kaal last_use par samaapt hota hai",
                                       "move_while_loaned"])
                    break

    def _detect_conflicts(self):
        loans = self.flow.loans
        for i, left in enumerate(loans):
            for right in loans[i + 1:]:
                if left.owner != right.owner:
                    continue
                if left.kind != "adhikar" and right.kind != "adhikar":
                    continue
                overlap = left.region & right.region
                if not overlap:
                    continue
                at = Sthan(right.sthan.line, right.sthan.col)
                labels = [
                    Chinh(left.sthan, "%s yahan jaari (%s)" % (
                        left.kind_text(), left.id), False),
                    Chinh(right.sthan, "%s yahan jaari (%s)" % (
                        right.kind_text(), right.id), True),
                ]
                self._nidan("RK03", right.sthan, labels=labels,
                            notes=["dono kaal %d bindu par milte hain" %
                                   len(overlap),
                                   "ek samay mein ek adhikar ya anek udhaar",
                                   "loan_conflict"])
                left.live = False
                right.live = False

    def _check_scope_exits(self):
        """An owner still live at the end of a flow is a leak (RK09)."""
        for owner in self.flow.owners:
            if owner.state != "live":
                continue
            labels = [Chinh(owner.sthan, "swatva yahan bana", True)]
            self._nidan("RK09", owner.sthan, labels=labels,
                        notes=["is flow mein na sanchay, na visarjan, na "
                               "with ka __exit__ mila",
                               "owner_leak"])

    def _check_drop_order(self):
        """Bun releases owners in the reverse order of their declaration.

        Rust drops locals in reverse declaration order.  Bun takes the
        principle (deterministic, reverse release) and states it as a rule
        of the analysis itself, so a manual `visarjan(a); visarjan(b)`
        is refused before the program runs.
        """
        owners = {o.id: o for o in self.flow.owners}
        groups = {}
        for key, owner_id in self.flow.drops:
            if owner_id is None or owner_id not in owners:
                continue
            groups.setdefault(owners[owner_id].scope, []).append(owner_id)
        for scope, actual in groups.items():
            declared = [o.id for o in self.flow.owners
                        if o.scope == scope and o.state == "dropped"]
            expected = list(reversed(declared))
            if len(actual) >= 2 and actual != expected:
                at = self.flow.points[-1].sthan if self.flow.points else \
                    self.flow.sthan
                self._nidan("RK14", at,
                            labels=[Chinh(at, "visarjan ka kram", True)],
                            notes=["scope %d: declared %s, released %s" %
                                   (scope, declared, actual),
                                   "Bun declares in one order and releases "
                                   "in the reverse order, inside one scope",
                                   "drop_order"])

    def _finalize(self):
        if self.flow.sthan.line == 0 and self.flow.points:
            self.flow.sthan = self.flow.points[0].sthan
        self._check_drop_order()
        # Keep only diagnostics belonging to this flow; the caller merges.
        for nidan in self.diagnostics:
            if nidan.filename != self.filename:
                nidan.filename = self.filename


# ---------------------------------------------------------------------------
# Whole-program entry points
# ---------------------------------------------------------------------------

def _alias_of(program):
    for statement in program.statements:
        if not isinstance(statement, ast.ImportStmt):
            continue
        path = statement.path or ""
        if path == "bun:raksha" or path.endswith("/raksha.bun") \
                or path == "raksha.bun":
            return statement.alias or "raksha"
    return None


def analyze_program(program, filename="<program>", source=""):
    """Analyse an already-parsed program.  Never runs it."""
    if not source and filename and os.path.isfile(filename):
        try:
            with open(filename, "r", encoding="utf-8") as handle:
                source = handle.read()
        except OSError:
            source = ""
    alias = _alias_of(program)
    result = Raksha(filename=filename, source=source)
    result.allowances = _allowances(source)
    if alias is None:
        return result

    body = []
    functions = []
    for statement in program.statements:
        if isinstance(statement, ast.FnDecl):
            functions.append(statement)
        elif isinstance(statement, (ast.StructDecl, ast.EnumDecl,
                                   ast.ImplDecl, ast.ProtocolDecl)):
            # Type declarations are not flows; they are refused only when
            # they appear *inside* a flow that is being analysed.
            continue
        else:
            body.append(statement)

    analyses = []
    main = _Vishleshan("mool", alias, filename)
    main.lower(body)
    result.main = main.flow
    result.diagnostics.extend(main.diagnostics)
    analyses.append(main)

    for decl in functions:
        flow = _Vishleshan(decl.name, alias, filename)
        flow.lower(_statements_of(decl.body))
        result.flows[decl.name] = flow.flow
        result.diagnostics.extend(flow.diagnostics)
        analyses.append(flow)

    result.diagnostics.sort(key=lambda d: (d.primary.line, d.primary.col,
                                           d.code))
    _apply_allowances(result)
    return result


def analyze_source(source, filename="<program>"):
    from .lexer import Lexer
    from .parser import Parser

    program = Parser(Lexer(source).tokenize()).parse()
    return analyze_program(program, filename=filename, source=source)


# ---------------------------------------------------------------------------
# Verification of the analysis itself (praman)
# ---------------------------------------------------------------------------

def verify(raksha):
    problems = []
    stats = dict(raksha.stats())
    points = set()
    for flow in raksha.all_flows():
        for point in flow.points:
            points.add(point.key())

    for flow in raksha.all_flows():
        owners = {o.id: o for o in flow.owners}
        loans = {l.id: l for l in flow.loans}
        for loan in flow.loans:
            if loan.owner not in owners:
                problems.append("%s: loan %d names a missing owner" %
                                (flow.name, loan.id))
            if not loan.region:
                problems.append("%s: loan %d has an empty kaal" %
                                (flow.name, loan.id))
            for key in loan.region:
                if key not in points:
                    problems.append("%s: loan %d has a kaal point that "
                                    "does not exist" % (flow.name, loan.id))
                    break
        for key, owner_id in flow.drops:
            if owner_id is None:
                continue
            if owner_id not in owners:
                problems.append("%s: a release names a missing owner" %
                                flow.name)
        for point in flow.points:
            if point.kind not in ("set", "assign", "call", "branch", "join",
                                  "drop", "return"):
                problems.append("%s: unknown bindu kind '%s'" %
                                (flow.name, point.kind))
        if flow.entry is not None and flow.entry not in points:
            problems.append("%s: the entry is not a bindu" % flow.name)

    for nidan in raksha.diagnostics:
        if nidan.code not in CODES:
            problems.append("nidan '%s' is not in CODES" % nidan.code)
        if not nidan.labels or not nidan.hint or not nidan.notes:
            problems.append("nidan '%s' is missing a label, hint or note" %
                            nidan.code)

    # An anumati is a claim that a specific diagnostic exists at a specific
    # line.  Verify that claim: an unknown code, an empty reason, a pragma
    # that permitted nothing, or a permitted nidan without a reason are all
    # failures.  This is what makes the exception auditable rather than a
    # way to switch the analysis off.
    for anumati in raksha.allowances:
        if anumati.code not in CODES:
            problems.append("anumati '%s' is not in CODES" % anumati.code)
        if not anumati.reason.strip():
            problems.append("anumati at line %d has no reason" %
                            anumati.pragma_line)
        if anumati.used == 0:
            problems.append("anumati at line %d permits %s at line %d "
                            "but suppressed nothing" %
                            (anumati.pragma_line, anumati.code,
                             anumati.line))
    for nidan in raksha.allowed:
        if not getattr(nidan, "allowed_by", ""):
            problems.append("permitted nidan '%s' has no anumati reason" %
                            nidan.code)
        if nidan.code not in CODES:
            problems.append("permitted nidan '%s' is not in CODES" %
                            nidan.code)

    if raksha.main is not None and raksha.main.drops and \
            not raksha.main.cleanup and any(
                owner.state == "dropped" for owner in raksha.main.owners):
        # Cleanup edges are required only for `with`-driven releases; a
        # manual visarjan has no unwind edge and is not an error.  Record
        # it as a fact, not a problem.
        pass

    stats["diagnostics_by_code"] = {}
    for nidan in raksha.diagnostics:
        stats["diagnostics_by_code"][nidan.code] = \
            stats["diagnostics_by_code"].get(nidan.code, 0) + 1
    stats["allowed_by_code"] = {}
    for nidan in raksha.allowed:
        stats["allowed_by_code"][nidan.code] = \
            stats["allowed_by_code"].get(nidan.code, 0) + 1
    stats["ok"] = not problems
    return Check(ok=not problems, problems=problems, stats=stats)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_json(raksha):
    check = verify(raksha)
    payload = {
        "file": raksha.filename,
        "stats": raksha.stats(),
        "regions": raksha.regions(),
        "diagnostics": [d.to_dict() for d in raksha.diagnostics],
        "allowed": [d.to_dict() for d in raksha.allowed],
        "allowances": [a.to_dict() for a in raksha.allowances],
        "flows": {},
        "check": {"ok": check.ok, "problems": check.problems,
                  "stats": check.stats},
        "verdict": "RAKSHA_CLEAN" if check.ok and not raksha.diagnostics
                   else "RAKSHA_DIAGNOSTICS",
    }
    for flow in raksha.all_flows():
        payload["flows"][flow.name] = {
            "entry": "%s:%d:%d" % flow.entry if flow.entry else None,
            "points": [{"at": p.label(), "kind": p.kind, "text": p.text,
                        "sthan": str(p.sthan), "packed": p.sthan.packed}
                       for p in flow.points],
            "edges": [["%s:%d:%d" % a, "%s:%d:%d" % b]
                      for a, b in flow.edges],
            "cleanup": [["%s:%d:%d" % a, "%s:%d:%d" % b]
                        for a, b in flow.cleanup],
            "owners": [{"id": o.id, "name": o.name, "state": o.state,
                        "declared": o.declaration,
                        "at": str(o.sthan)} for o in flow.owners],
            "loans": [{"id": l.id, "owner": l.owner, "kind": l.kind,
                       "issued": "%s:%d:%d" % l.issued if l.issued else None,
                       "last_use": "%s:%d:%d" % l.last_use
                       if l.last_use else None,
                       "kaal": sorted("%s:%d:%d" % k for k in l.region)}
                      for l in flow.loans],
            "drops": [["%s:%d:%d" % k, o] for k, o in flow.drops],
            "loops": [["%s:%d:%d" % a, "%s:%d:%d" % b]
                      for a, b in flow.loops()],
        }
    return json.dumps(payload, indent=2, sort_keys=True)


def render_dot(raksha):
    out = ["digraph raksha {", "  rankdir=TB;",
           "  node [shape=box, fontname=monospace];"]
    for flow in raksha.all_flows():
        out.append("  subgraph cluster_%s {" % flow.name.replace("-", "_"))
        out.append('    label="%s";' % flow.name)
        for point in flow.points:
            label = "%s\\n%s" % (point.kind, point.text.replace('"', "'"))
            colour = {"drop": "lightcoral", "branch": "lightblue",
                      "return": "lightgrey", "set": "lightgreen"}.get(
                          point.kind, "white")
            out.append('    "%s" [label="%s", style=filled, fillcolor=%s];'
                       % (point.label(), label[:60], colour))
        for a, b in flow.edges:
            out.append('    "%s:%d:%d" -> "%s:%d:%d";' % (a + b))
        for a, b in flow.cleanup:
            out.append('    "%s:%d:%d" -> "%s:%d:%d" '
                       '[style=dashed, color=red, label=unwind];'
                       % (a + b))
        out.append("  }")
    out.append("}")
    return "\n".join(out)


def render_text(raksha):
    out = ["RAKSHA %s" % raksha.filename,
           "pravah %d  bindu %d  kinara %d  swatva %d  udhaar %d  "
           "visarjan %d  loops %d  nidan %d" % (
               raksha.stats()["flows"], raksha.stats()["points"],
               raksha.stats()["edges"], raksha.stats()["owners"],
               raksha.stats()["loans"], raksha.stats()["drops"],
               raksha.stats()["loops"], raksha.stats()["diagnostics"])]
    for flow in raksha.all_flows():
        out.append("")
        out.append("pravah %s  (entry %s)" % (
            flow.name, "%s:%d:%d" % flow.entry if flow.entry else "-"))
        for point in flow.points:
            out.append("  %s" % point)
        out.append("  kinara %d, cleanup %d, loops %d" % (
            len(flow.edges), len(flow.cleanup), len(flow.loops())))
        for owner in flow.owners:
            out.append("  swatva %d %-12s %s at %s" % (
                owner.id, owner.name, owner.state, owner.sthan))
        for loan in flow.loans:
            out.append("  %-8s %d -> swatva %d  kaal %d bindu" % (
                loan.kind_text(), loan.id, loan.owner, len(loan.region)))
        for key, owner_id in flow.drops:
            out.append("  visarjan swatva %s at %s:%d:%d" %
                       (owner_id, key[0], key[1], key[2]))
    if raksha.diagnostics:
        out.append("")
        out.append("nidan:")
        for nidan in raksha.diagnostics:
            out.append("  %s" % nidan)
    if raksha.allowed:
        out.append("")
        out.append("anumati (permitted nidan, explicitly recorded):")
        for nidan in raksha.allowed:
            out.append("  %s  <- %s" % (nidan, nidan.allowed_by))
    return "\n".join(out)


def render_explain(raksha, source=""):
    text = source or raksha.source
    out = ["RAKSHA / रक्षा — %s" % raksha.filename, "",
           "The three questions on one graph: reachability forward, "
           "reachability backward, and dominance.  A kaal is the set of "
           "bindu on some path from a loan's issue to its last use.",
           "", "niyam (rules, principle borrowed / syntax not borrowed):"]
    for rule in RULES:
        out.append("  %-5s %-22s %s  [%s]" % (
            rule["id"], rule["name"], rule["text"], rule["bun_rule"]))
    out.append("")
    out.append("stats: %s" % json.dumps(raksha.stats(), sort_keys=True))
    out.append("")
    if not raksha.diagnostics:
        out.append("No nidan.  Every owner has one terminal state; every "
                   "kaal is a set of points on the graph.")
    for nidan in raksha.diagnostics:
        out.append("")
        out.append(nidan.render(text))
    if raksha.allowances:
        out.append("")
        out.append("anumati (an explicit, one-line, one-code permission):")
        for anumati in raksha.allowances:
            out.append("  line %-4d %-5s used %d  %s" % (
                anumati.line, anumati.code, anumati.used, anumati.reason))
    check = verify(raksha)
    out.append("")
    out.append("praman: %s (%d problem(s))" %
               ("OK" if check.ok else "FAILED", len(check.problems)))
    for problem in check.problems:
        out.append("  - %s" % problem)
    return "\n".join(out)
