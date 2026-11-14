"""Samanvay (समन्वय, "coordination") — Bun's deterministic concurrency wave.

The wave answers one question that a language with ``spawn`` must answer
before it can be called production-ready:

    when two tasks touch the same thing, which of the two orders did the
    program actually allow, and can I see that order again tomorrow?

Bun's answer has three parts, and none of them is a new keyword:

1. **A deterministic scheduler.**  Every task runs under a baton: exactly
   one task executes at a time, and the scheduler chooses the next one from
   a seeded generator.  A seed is therefore a replay token — the same
   program and the same seed produce the same interleaving, byte for byte.
   This is the FoundationDB idea (determinism makes a failure repeatable)
   applied to a language runtime instead of a database.

2. **Happens-before, not timers.**  Every task carries a vector clock.  A
   channel send, a lock release, a task join and a close are release
   operations; the matching receive, acquire, join and read are acquire
   operations.  Two accesses to one shared cell that are not ordered by
   those edges are a data race (SV03), reported with both source spans.
   This is the ThreadSanitizer principle, computed on Bun's own trace.

3. **A wait-for graph.**  When no task can run, the scheduler does not hang
   and does not guess: it records what every blocked task waits for, looks
   for a cycle, and reports SV04 with the cycle (or, when there is no cycle,
   with the exact set of waits that cannot progress).

Shared state is explicit.  A cell is created with ``sv.sajha(v)`` and read
or written with ``sv.padh`` / ``sv.likh``; a plain variable is not traced.
That is a deliberate boundary, and it is the same boundary Rust draws with
``Mutex<T>``: you can only share what you wrapped.  The static pass (SV01)
refuses a task that writes a captured variable directly, so the boundary is
enforced rather than assumed.

Nothing in this module runs unless the program imports ``bun:samanvay``.
The runtime half of the wave is ``lib/bun/samanvay.bun``, written in Bun.
"""

from __future__ import annotations

import json
import random
import threading
from dataclasses import dataclass

from .antar import Sthan, sthan_of, expr_text
from . import ast

__all__ = [
    "CODES", "RULES", "SV_FNS", "SYNC_FNS", "MUTATORS",
    "Chinh", "Nidan", "Kary", "Samanvay", "Check",
    "analyze_program", "analyze_source", "verify",
    "render_json", "render_dot", "render_text", "render_stats",
    "render_explain", "reset", "summary", "seed", "site",
    "set_site", "clear_site",
]


# ---------------------------------------------------------------------------
# The error codes.  Eight names, one per failure a concurrent program has.
# ---------------------------------------------------------------------------

CODES = {
    "SV01": {"name": "asurakshit_lekh",
             "message": "a task writes a captured variable with no "
                        "coordination",
             "hint": "wrap the value with sv.sajha and write it with "
                     "sv.likh, or take a lock first"},
    "SV02": {"name": "kary_leak",
             "message": "a spawned task is never joined",
             "hint": "keep the handle and call sv.mel(h), or spawn inside "
                     "scope { ... }"},
    "SV03": {"name": "dwand",
             "message": "two tasks touch one cell and neither happens "
                        "before the other",
             "hint": "put both accesses under one sv.tal, or order them "
                     "with a channel"},
    "SV04": {"name": "bandh",
             "message": "no task can make progress",
             "hint": "break the cycle: one task must take the locks in the "
                     "same order as the other"},
    "SV05": {"name": "kanal_dosh",
             "message": "the channel is used after it was closed",
             "hint": "close a channel once, after the last send"},
    "SV06": {"name": "stale",
             "message": "a task reads a value that the parent writes after "
                        "the spawn",
             "hint": "write before the spawn, or join before the write"},
    "SV07": {"name": "tal_kram",
             "message": "two flows take the same two locks in opposite "
                        "order",
             "hint": "give every flow one global lock order"},
    "SV08": {"name": "kary_visfot",
             "message": "a task is spawned inside a loop with no scope",
             "hint": "spawn inside scope { ... } so the group joins them"},
}

RULES = [
    {"id": code, "name": CODES[code]["name"], "text": CODES[code]["message"],
     "principle": principle, "bun_rule": rule}
    for code, principle, rule in [
        ("SV01", "Rust's Send/Sync: sharing needs a type that says how",
         "S1"),
        ("SV02", "structured concurrency: no task outlives its parent",
         "S2"),
        ("SV03", "ThreadSanitizer: a race is a missing happens-before edge",
         "S3"),
        ("SV04", "wait-for graph: a deadlock is a cycle in 'waits for'",
         "S4"),
        ("SV05", "a closed channel is a one-way door",
         "S5"),
        ("SV06", "a spawn is not a join: the parent keeps running",
         "S2"),
        ("SV07", "lock ordering: the cheapest deadlock prevention there is",
         "S4"),
        ("SV08", "unbounded fan-out is a leak with extra steps",
         "S2"),
    ]
]

# The exported names of bun:samanvay.  Names, never keywords, so the
# language packs can write the wave on the day it ships.
SV_FNS = frozenset({
    "sajha", "padh", "likh", "tal", "pakad", "chhod",
    "kanal", "bhej", "le", "band", "kary", "mel", "chhodo",
    "ajna", "beej", "trace", "niyam", "codes", "audit", "summary",
})

# A call to one of these is evidence that the task coordinates its access.
SYNC_FNS = frozenset({
    "pakad", "chhod", "padh", "likh", "bhej", "le", "band", "mel", "ajna",
})

MUTATORS = frozenset({
    "push", "append", "pop", "set", "remove", "insert", "sort", "clear",
    "update", "extend", "reverse", "add", "discard",
})


# ---------------------------------------------------------------------------
# Diagnostics.  Same shape as Raksha's: code, primary span, labelled spans,
# a hint and notes -- a diagnostic a tool can consume and a human can read.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Chinh:
    """One labelled span of a nidan."""

    sthan: Sthan
    text: str
    primary: bool = False


class Nidan:
    """A Samanvay diagnostic."""

    def __init__(self, code, message=None, primary=None, labels=None,
                 hint=None, notes=None, filename="<program>",
                 family="samanvay"):
        self.family = family
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
            "code": self.code, "name": self.name, "message": self.message,
            "file": self.filename, "primary": str(self.primary),
            "labels": [{"at": str(c.sthan), "text": c.text,
                        "primary": c.primary} for c in self.labels],
            "hint": self.hint, "notes": list(self.notes),
        }

    def render(self, source=""):
        lines = source.splitlines() if source else []
        out = ["%s[%s]: %s" % (self.family, self.code, self.message),
               "  --> %s:%s" % (self.filename, self.primary)]
        shown = {self.primary.line} | {c.sthan.line for c in self.labels}
        shown = {n for n in shown if n > 0}
        if shown:
            out.append("   |")
            for number in range(max(1, min(shown) - 1), max(shown) + 2):
                text = lines[number - 1] if number - 1 < len(lines) else ""
                out.append("%3d | %s" % (number, text))
                marks = [c for c in self.labels if c.sthan.line == number]
                if self.primary.line == number and not any(
                        c.primary for c in marks):
                    marks.insert(0, Chinh(self.primary, self.message, True))
                for chinh in marks:
                    col = max(1, chinh.sthan.col)
                    width = max(1, min(max(1, len(text) - col + 1), 28))
                    out.append("   | %s%s %s" % (
                        " " * (col - 1),
                        "^" if chinh.primary else "-", chinh.text))
            out.append("   |")
        for note in self.notes:
            out.append("   = nidan: %s" % note)
        if self.hint:
            out.append("   = sulabh: %s" % self.hint)
        return "\n".join(out)

    def __str__(self):
        return "%s[%s]: %s at %s" % (self.family, self.code, self.message,
                                     self.primary)


# ---------------------------------------------------------------------------
# Static model: one Kary per spawn site.
# ---------------------------------------------------------------------------

@dataclass
class Kary:
    """A spawn site and what the spawned body does with shared names."""

    tid: int
    name: str                 # the function the task runs
    sthan: Sthan              # the spawn call
    body: object = None
    reads: list = None        # [(name, sthan)]
    writes: list = None       # [(name, sthan)]
    syncs: list = None        # [(fn, sthan)]
    locks: list = None        # [(lock name, sthan)] in first-use order
    closes: list = None       # [(channel name, sthan)]
    sends: list = None        # [(channel name, sthan)]
    joined: bool = False
    in_loop: bool = False
    in_scope: bool = False
    handle: object = None

    def __post_init__(self):
        self.reads = list(self.reads or [])
        self.writes = list(self.writes or [])
        self.syncs = list(self.syncs or [])
        self.locks = list(self.locks or [])
        self.closes = list(self.closes or [])
        self.sends = list(self.sends or [])

    def to_dict(self):
        return {
            "tid": self.tid, "name": self.name, "at": str(self.sthan),
            "reads": [{"name": n, "at": str(s)} for n, s in self.reads],
            "writes": [{"name": n, "at": str(s)} for n, s in self.writes],
            "syncs": [{"fn": f, "at": str(s)} for f, s in self.syncs],
            "locks": [{"name": n, "at": str(s)} for n, s in self.locks],
            "closes": [{"name": n, "at": str(s)} for n, s in self.closes],
            "sends": [{"name": n, "at": str(s)} for n, s in self.sends],
            "joined": self.joined, "in_loop": self.in_loop,
            "in_scope": self.in_scope,
        }


class Check:
    """The result of verifying an analysis or a run."""

    def __init__(self, ok, problems=None, stats=None):
        self.ok = ok
        self.problems = list(problems or [])
        self.stats = dict(stats or {})

    def to_dict(self):
        return {"ok": self.ok, "problems": list(self.problems),
                "stats": dict(self.stats)}


class Samanvay:
    """The static half: spawn sites, shared names, lock orders."""

    def __init__(self, filename="<program>", source=""):
        self.filename = filename
        self.source = source
        self.karies = []
        self.diagnostics = []
        self.lock_orders = {}     # flow name -> [lock names]
        self.lock_sites = {}      # flow name -> {lock name: Sthan}
        self.module_writes = []   # [(name, sthan)] at module level

    def stats(self):
        return {
            "karies": len(self.karies),
            "diagnostics": len(self.diagnostics),
            "codes": sorted({d.code for d in self.diagnostics}),
            "flows": len(self.lock_orders),
            "joined": sum(1 for k in self.karies if k.joined),
            "unjoined": sum(1 for k in self.karies if not k.joined),
            "shared_writes": sum(len(k.writes) for k in self.karies),
            "sync_calls": sum(len(k.syncs) for k in self.karies),
        }


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _children(node):
    """Every AST child of a node, in field order."""
    out = []
    values = getattr(node, "__dict__", {})
    for name, value in values.items():
        if name in ("line", "col"):
            continue
        if isinstance(value, (list, tuple)):
            for item in value:
                if hasattr(item, "__dict__") and item.__class__.__module__ == "bun.ast":
                    out.append(item)
                elif isinstance(item, tuple):
                    for part in item:
                        if hasattr(part, "__dict__") and \
                                part.__class__.__module__ == "bun.ast":
                            out.append(part)
        elif hasattr(value, "__dict__") and value.__class__.__module__ == "bun.ast":
            out.append(value)
    return out


def _walk(node, visit, parents=()):
    if node is None or not hasattr(node, "__dict__"):
        return
    visit(node, parents)
    for child in _children(node):
        _walk(child, visit, parents + (node,))


def _block_statements(node):
    return getattr(node, "statements", []) or []


def _alias_of(program):
    for statement in program.statements:
        if not isinstance(statement, ast.ImportStmt):
            continue
        path = statement.path or ""
        if path == "bun:samanvay" or path.endswith("/samanvay.bun") \
                or path == "samanvay.bun":
            return statement.alias or "samanvay"
    return None


def _is_sv_call(node, alias):
    """`sv.name(...)` for the imported alias.

    The parser builds `sv.name(x)` as a MethodCall and `(sv.name)(x)` as a
    Call; both spellings name the same function, so both are recognised.
    """
    return _sv_name(node, alias) is not None


def _sv_name(node, alias):
    if isinstance(node, ast.MethodCall):
        if isinstance(node.receiver, ast.Identifier) and \
                node.receiver.name == alias:
            return node.method
        return None
    if isinstance(node, ast.Call) and isinstance(node.callee, ast.Attribute):
        target = node.callee
        if isinstance(target.object, ast.Identifier) and \
                target.object.name == alias:
            return target.name
    return None


def _bound_names(block):
    """Names a block binds itself (let/for targets/params of nested fns)."""
    names = set()
    for statement in _block_statements(block):
        if isinstance(statement, ast.LetStmt):
            names.add(statement.name)
        elif isinstance(statement, ast.ForStmt):
            names.update(statement.targets)
        elif isinstance(statement, ast.UnpackStmt):
            for target in statement.targets:
                names.update(getattr(target, "targets", []) or [])
        elif isinstance(statement, ast.FnDecl):
            names.add(statement.name)
        elif isinstance(statement, (ast.StructDecl, ast.EnumDecl)):
            names.add(getattr(statement, "name", ""))
    return names


def _params(function):
    out = []
    for param in getattr(function, "params", []) or []:
        out.append(getattr(param, "name", param))
    return out


def _expr_name(node):
    """A stable name for a lock or channel expression."""
    if isinstance(node, ast.Identifier):
        return node.name
    if isinstance(node, ast.Attribute):
        return "%s.%s" % (_expr_name(node.object), node.name)
    if isinstance(node, ast.Call):
        return "%s()" % _expr_name(node.callee)
    if isinstance(node, ast.Literal):
        return repr(node.value)
    return expr_text(node)


# ---------------------------------------------------------------------------
# The static pass
# ---------------------------------------------------------------------------

class _Vishleshan:
    """Walk one spawn site and record what its body does."""

    def __init__(self, alias, filename):
        self.alias = alias
        self.filename = filename

    def analyze(self, kary, function, module_names):
        body = getattr(function, "body", None)
        params = set(_params(function))
        local = _bound_names(body) | params
        reads = {}
        writes = {}

        def visit(node, parents):
            if isinstance(node, ast.Identifier):
                name = node.name
                if name not in local and name in module_names:
                    reads.setdefault(name, sthan_of(node))
                return
            if isinstance(node, ast.AssignStmt) and \
                    isinstance(node.target, ast.Identifier):
                name = node.target.name
                if name not in local:
                    writes.setdefault(name, sthan_of(node))
                return
            if isinstance(node, (ast.OpAssignStmt, ast.IncDecStmt)) and \
                    isinstance(node.target, ast.Identifier):
                name = node.target.name
                if name not in local:
                    writes.setdefault(name, sthan_of(node))
                return
            if isinstance(node, ast.MethodCall) and \
                    isinstance(node.receiver, ast.Identifier) and \
                    node.method in MUTATORS:
                name = node.receiver.name
                if name not in local:
                    writes.setdefault(name, sthan_of(node))
                return
            name = _sv_name(node, self.alias)
            if name is None:
                return
            if name in SYNC_FNS:
                kary.syncs.append((name, sthan_of(node)))
            if name in ("pakad", "chhod") and node.args:
                lock = _expr_name(node.args[0])
                if name == "pakad" and lock not in [l for l, _ in kary.locks]:
                    kary.locks.append((lock, sthan_of(node)))
            if name == "band" and node.args:
                kary.closes.append((_expr_name(node.args[0]), sthan_of(node)))
            if name == "bhej" and node.args:
                kary.sends.append((_expr_name(node.args[0]), sthan_of(node)))

        _walk(body, visit)
        kary.reads = [(n, s) for n, s in reads.items()]
        kary.writes = [(n, s) for n, s in writes.items()]
        return kary


def analyze_program(program, filename="<program>", source=""):
    """Analyse a parsed program.  Never runs it."""
    import os
    if not source and filename and os.path.isfile(filename):
        try:
            with open(filename, "r", encoding="utf-8") as handle:
                source = handle.read()
        except OSError:
            source = ""
    alias = _alias_of(program)
    result = Samanvay(filename=filename, source=source)
    if alias is None:
        return result

    functions = {}
    module_names = set()
    for statement in program.statements:
        if isinstance(statement, ast.FnDecl):
            functions[statement.name] = statement
        elif isinstance(statement, ast.LetStmt):
            module_names.add(statement.name)
        elif isinstance(statement, ast.UnpackStmt):
            for target in statement.targets:
                module_names.update(getattr(target, "targets", []) or [])
        if isinstance(statement, (ast.AssignStmt, ast.OpAssignStmt,
                                  ast.IncDecStmt)) and \
                isinstance(getattr(statement, "target", None),
                           ast.Identifier):
            result.module_writes.append(
                (statement.target.name, sthan_of(statement)))

    analyzer = _Vishleshan(alias, filename)
    counter = [0]

    def new_kary(node, parents, name, body, handle=None):
        counter[0] += 1
        kary = Kary(tid=counter[0], name=name, sthan=sthan_of(node),
                    body=body, handle=handle)
        kary.in_loop = any(isinstance(p, (ast.ForStmt, ast.WhileStmt))
                           for p in parents)
        kary.in_scope = any(isinstance(p, ast.ScopeStmt) for p in parents)
        analyzer.analyze(kary, body, module_names)
        result.karies.append(kary)
        return kary

    # Spawn sites: sv.kary(fn) anywhere in the program.
    sites = []

    def visit(node, parents):
        if _sv_name(node, alias) != "kary" or not node.args:
            return
        target = node.args[0]
        if isinstance(target, ast.Identifier) and target.name in functions:
            function = functions[target.name]
            name = target.name
        elif isinstance(target, ast.FnDecl):
            function = target
            name = target.name or "anon"
        else:
            function = None
            name = _expr_name(target)
        handle = None
        for parent in reversed(parents):
            if isinstance(parent, ast.LetStmt) and parent.value is node:
                handle = parent.name
                break
        kary = new_kary(node, parents, name, function, handle)
        sites.append((kary, node, parents))

    _walk(program, visit)

    # A handle is joined when `sv.mel(handle)` appears anywhere.
    joined = set()
    def find_join(node, parents):
        if _sv_name(node, alias) == "mel" and node.args:
            joined.add(_expr_name(node.args[0]))
    _walk(program, find_join)

    for kary, node, parents in sites:
        if kary.handle is not None and kary.handle in joined:
            kary.joined = True

        # SV02 -- a task nobody joins.
        if not kary.joined and not kary.in_scope:
            result.diagnostics.append(Nidan(
                "SV02", primary=kary.sthan,
                labels=[Chinh(kary.sthan, "task '%s' starts here" % kary.name,
                              True)],
                notes=["the handle is %s" % (
                    "never joined" if kary.handle else "not even kept"),
                    "scope { ... } would join it at the end of the block"],
                filename=filename))

        # SV01 -- a write to a captured variable with no coordination.
        if kary.writes and not kary.syncs:
            name, sthan = kary.writes[0]
            result.diagnostics.append(Nidan(
                "SV01", primary=sthan,
                labels=[Chinh(sthan, "writes '%s'" % name, True),
                        Chinh(kary.sthan, "from this task")],
                notes=["the task calls no sv.pakad / sv.likh / sv.bhej / "
                       "sv.le, so nothing orders this write",
                       "a plain variable is not traced; wrap it with "
                       "sv.sajha to make the access visible"],
                filename=filename))

        # SV05 -- a channel closed twice, or a send after the close.  The
        # two lists are merged by position: a send *before* the close is
        # legal, and only the textual order can tell them apart.
        events = [(s.line, s.col, "close", n, s) for n, s in kary.closes]
        events += [(s.line, s.col, "send", n, s) for n, s in kary.sends]
        seen_close = {}
        for _, _, kind, name, sthan in sorted(events, key=lambda e: e[:2]):
            if kind == "close":
                if name in seen_close:
                    result.diagnostics.append(Nidan(
                        "SV05", primary=sthan,
                        labels=[Chinh(sthan, "second close", True),
                                Chinh(seen_close[name], "first close")],
                        notes=["a close is the last event a channel allows"],
                        filename=filename))
                else:
                    seen_close[name] = sthan
            elif name in seen_close:
                result.diagnostics.append(Nidan(
                    "SV05", primary=sthan,
                    labels=[Chinh(sthan, "send after close", True),
                            Chinh(seen_close[name], "closed here")],
                    notes=["the receiver has already seen the close"],
                    filename=filename))

        # SV08 -- fan-out in a loop without a scope.
        if kary.in_loop and not kary.in_scope and not kary.joined:
            result.diagnostics.append(Nidan(
                "SV08", primary=kary.sthan,
                labels=[Chinh(kary.sthan, "spawn inside a loop", True)],
                notes=["the loop can start more tasks than the program can "
                       "join"],
                filename=filename))

        # SV06 -- a module value written after the spawn and read by the task.
        for name, sthan in kary.reads:
            for wname, wsthan in result.module_writes:
                if wname == name and wsthan.line > kary.sthan.line:
                    result.diagnostics.append(Nidan(
                        "SV06", primary=sthan,
                        labels=[Chinh(sthan, "reads '%s'" % name, True),
                                Chinh(wsthan, "written here, after the spawn"),
                                Chinh(kary.sthan, "spawn")],
                        notes=["the parent keeps running after sv.kary; "
                               "the task may see either value"],
                        filename=filename))
                    break

    # SV07 -- two flows take the same two locks in opposite order.
    for statement in program.statements:
        if isinstance(statement, ast.FnDecl):
            order = []
            sites = {}
            def collect(node, parents):
                if _sv_name(node, alias) == "pakad" and node.args:
                    name = _expr_name(node.args[0])
                    if name not in order:
                        order.append(name)
                        sites[name] = sthan_of(node)
            _walk(statement.body, collect)
            if len(order) >= 2:
                result.lock_orders[statement.name] = order
                result.lock_sites[statement.name] = sites

    names = sorted(result.lock_orders)
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            a, b = result.lock_orders[left], result.lock_orders[right]
            for x in range(len(a)):
                for y in range(x + 1, len(a)):
                    if a[y] in b and a[x] in b and \
                            b.index(a[y]) < b.index(a[x]):
                        here = result.lock_sites.get(right, {}).get(a[y])
                        there = result.lock_sites.get(left, {}).get(a[x])
                        primary = here or there or Sthan(1, 1)
                        result.diagnostics.append(Nidan(
                            "SV07", primary=primary,
                            labels=[Chinh(primary, "flows '%s' and '%s'"
                                          % (left, right), True)],
                            notes=["'%s' takes %s then %s" % (left, a[x], a[y]),
                                   "'%s' takes %s then %s" % (right, a[y], a[x]),
                                   "one of the two orders must change"],
                            filename=filename))
                        break

    result.diagnostics.sort(key=lambda d: (d.primary.line, d.primary.col,
                                           d.code))
    return result


def analyze_source(source, filename="<program>"):
    from .lexer import Lexer
    from .parser import Parser

    program = Parser(Lexer(source).tokenize()).parse()
    return analyze_program(program, filename=filename, source=source)


# ---------------------------------------------------------------------------
# Verification of the analysis (praman)
# ---------------------------------------------------------------------------

def verify(analysis):
    """Check the analysis is internally consistent and falsifiable."""
    problems = []
    for nidan in analysis.diagnostics:
        if nidan.code not in CODES:
            problems.append("nidan '%s' is not in CODES" % nidan.code)
        if not nidan.labels:
            problems.append("%s has no labelled span" % nidan.code)
        if not nidan.hint:
            problems.append("%s has no hint" % nidan.code)
        if not nidan.notes:
            problems.append("%s has no note" % nidan.code)
    seen = set()
    for kary in analysis.karies:
        key = (kary.name, str(kary.sthan))
        if key in seen:
            problems.append("two tasks at %s" % kary.sthan)
        seen.add(key)
        for name, sthan in kary.writes:
            if sthan.line == 0:
                problems.append("task %s has a write with no position"
                                % kary.name)
    for left in analysis.lock_orders:
        for right in analysis.lock_orders:
            if left >= right:
                continue
            a, b = analysis.lock_orders[left], analysis.lock_orders[right]
            if a == b:
                problems.append("flows %s and %s report the same order twice"
                                % (left, right))
    stats = analysis.stats()
    stats["ok"] = not problems
    return Check(ok=not problems, problems=problems, stats=stats)


# ---------------------------------------------------------------------------
# Rendering (static)
# ---------------------------------------------------------------------------

def render_json(analysis):
    check = verify(analysis)
    payload = {
        "file": analysis.filename,
        "ok": check.ok and not analysis.diagnostics,
        "karies": [k.to_dict() for k in analysis.karies],
        "lock_orders": analysis.lock_orders,
        "nidan": [d.to_dict() for d in analysis.diagnostics],
        "stats": check.stats,
        "problems": check.problems,
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def render_dot(analysis):
    lines = ["digraph samanvay {", '  rankdir=LR;',
             '  node [shape=box, fontname="monospace"];',
             '  "mool" [shape=ellipse];']
    for kary in analysis.karies:
        node = "t%d" % kary.tid
        lines.append('  %s [label="%s\\n%s"];' % (node, kary.name,
                                                  kary.sthan))
        lines.append('  "mool" -> %s [label="kary"];' % node)
        if kary.joined:
            lines.append('  %s -> "mool" [label="mel", style=dashed];' % node)
        for lock, sthan in kary.locks:
            lines.append('  %s -> "lock:%s" [label="pakad"];' % (node, lock))
    lines.append("}")
    return "\n".join(lines)


def render_stats(analysis):
    return json.dumps(verify(analysis).stats, indent=2, sort_keys=True)


def render_text(analysis):
    out = []
    out.append("samanvay: %s" % analysis.filename)
    if not analysis.karies:
        out.append("  no sv.kary site (import bun:samanvay to use the wave)")
        return "\n".join(out)
    out.append("  %d task(s)" % len(analysis.karies))
    for kary in analysis.karies:
        mark = "joined" if kary.joined else "unjoined"
        where = "scope" if kary.in_scope else "-"
        out.append("  t%d %-12s at %-8s %-8s %-5s locks=%s"
                   % (kary.tid, kary.name, kary.sthan, mark, where,
                      ",".join(name for name, _ in kary.locks) or "-"))
    if analysis.lock_orders:
        out.append("  lock orders:")
        for name in sorted(analysis.lock_orders):
            out.append("    %-12s %s" % (name,
                                         " -> ".join(analysis.lock_orders[name])))
    for nidan in analysis.diagnostics:
        out.append("")
        out.append(nidan.render(analysis.source))
    out.append("")
    if analysis.diagnostics:
        out.append("SAMANVAY: %d nidan" % len(analysis.diagnostics))
    else:
        out.append("SAMANVAY: OK (%d task, 0 nidan)" % len(analysis.karies))
    return "\n".join(out)


def render_explain(analysis, source=""):
    out = ["samanvay: the eight rules", ""]
    for rule in RULES:
        out.append("%s %-18s %s" % (rule["id"], rule["name"], rule["text"]))
        out.append("     principle: %s" % rule["principle"])
        out.append("     bun rule : %s" % rule["bun_rule"])
        out.append("")
    out.append("this file:")
    for nidan in analysis.diagnostics:
        out.append("  %s at %s -- %s" % (nidan.code, nidan.primary,
                                         nidan.message))
    if not analysis.diagnostics:
        out.append("  none")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Runtime: vector clocks, the baton, cells, channels, locks
# ---------------------------------------------------------------------------

def _hb(left, right):
    """True when clock `left` happens before clock `right`."""
    for tid, value in left.items():
        if right.get(tid, 0) < value:
            return False
    return True


def _merge(into, other):
    for tid, value in other.items():
        if value > into.get(tid, 0):
            into[tid] = value
    return into


class Bandh(Exception):
    """Raised inside a task when the scheduler proved a deadlock."""

    def __init__(self, report):
        super().__init__("samanvay: deadlock")
        self.report = report


class Epoch:
    __slots__ = ("tid", "clock", "site")

    def __init__(self, tid, clock, site):
        self.tid = tid
        self.clock = dict(clock)
        self.site = site

    def to_dict(self):
        return {"tid": self.tid, "clock": self.clock, "at": str(self.site)}


class Cell:
    __slots__ = ("id", "name", "value", "last_write", "reads", "accesses")

    def __init__(self, cid, name, value):
        self.id = cid
        self.name = name
        self.value = value
        self.last_write = None
        self.reads = {}
        self.accesses = 0


class Channel:
    __slots__ = ("id", "cap", "buf", "closed", "senders", "receivers",
                 "send_clock", "close_clock", "sent", "received")

    def __init__(self, cid, cap):
        self.id = cid
        self.cap = max(0, int(cap))
        self.buf = []
        self.closed = False
        self.senders = []
        self.receivers = []
        self.send_clock = None
        self.close_clock = None
        self.sent = 0
        self.received = 0


class Tal:
    """A lock."""

    __slots__ = ("id", "owner", "waiters", "release_clock", "taken")

    def __init__(self, lid):
        self.id = lid
        self.owner = None
        self.waiters = []
        self.release_clock = None
        self.taken = 0


class Task:
    __slots__ = ("tid", "name", "state", "thread", "error", "result",
                 "clock", "cancel", "site", "wait_for", "pending_clock")

    def __init__(self, tid, name="task"):
        self.tid = tid
        self.name = name
        self.state = "ready"
        self.thread = None
        self.error = None
        self.result = None
        self.clock = {tid: 0}
        self.cancel = False
        self.site = Sthan()
        self.wait_for = None
        self.pending_clock = None

    def to_dict(self):
        return {"tid": self.tid, "name": self.name, "state": self.state,
                "clock": dict(self.clock), "cancel": self.cancel,
                "at": str(self.site)}


class Scheduler:
    """One baton, one running task, one seeded choice per scheduling point."""

    def __init__(self, seed_value=0, max_steps=200000):
        self.cond = threading.Condition()
        self.seed_value = seed_value
        self.rng = random.Random(seed_value)
        self.tasks = {}
        self.ready = []
        self.current = None
        self.steps = 0
        self.schedule = []
        self.aborted = None
        self.started = False
        self.max_steps = max_steps
        # The virtual clock.  One tick per scheduling point, so time moves
        # only when the program yields or sleeps, never when the machine is
        # busy.  `sona(n)` parks a task until the clock passes now+n; when
        # nothing else can run the scheduler jumps the clock to the earliest
        # wake-up instead of calling it a deadlock.  This is why a timeout is
        # reproducible: it is measured in steps, not in nanoseconds.
        self.now = 0
        self.timers = []          # [(wake_at, tid)] -- kept sorted by use
        self.wakes = 0            # how many times the clock had to jump

    # -- admission ---------------------------------------------------------

    def ensure_main(self):
        if self.started:
            return self.tasks[0]
        self.started = True
        main = Task(0, "mool")
        self.tasks[0] = main
        self.current = 0
        return main

    def register(self, task):
        with self.cond:
            self.tasks[task.tid] = task
            self.ready.append(task.tid)
            self.cond.notify_all()

    def enter(self, tid):
        with self.cond:
            while self.current != tid and not self.aborted:
                self.cond.wait()
            if self.aborted:
                raise Bandh(self.aborted)

    # -- picking -----------------------------------------------------------

    def _ready_candidates(self):
        return sorted(tid for tid in self.ready
                      if self.tasks[tid].state == "ready")

    def _advance_clock(self):
        """Jump to the earliest timer and wake everything due."""
        if not self.timers:
            return False
        wake = min(item[0] for item in self.timers)
        if wake > self.now:
            self.now = wake
        due = [item for item in self.timers if item[0] <= self.now]
        self.timers = [item for item in self.timers if item[0] > self.now]
        self.wakes += 1
        for _, tid in due:
            task = self.tasks.get(tid)
            if task is None or task.state != "blocked":
                continue
            wait = task.wait_for
            if wait and wait[0] == "sona":
                task.state = "ready"
                task.wait_for = None
                if tid not in self.ready:
                    self.ready.append(tid)
        return True

    def _pick(self):
        candidates = self._ready_candidates()
        # A sleeper is not a deadlock: if the only runnable thing is the
        # clock, move the clock.
        while not candidates and self.timers:
            self._advance_clock()
            candidates = self._ready_candidates()
        if not candidates:
            return None
        tid = candidates[self.rng.randrange(len(candidates))]
        self.ready.remove(tid)
        self.current = tid
        return tid

    def _deadlock(self):
        blocked = [t for t in self.tasks.values() if t.state == "blocked"]
        edges = {}
        for task in blocked:
            wait = task.wait_for
            target = None
            if wait and wait[0] == "join":
                target = wait[1]
            elif wait and wait[0] == "tal":
                owner = wait[1].owner
                target = owner
            if target is not None and target != task.tid:
                edges.setdefault(task.tid, []).append(target)
        cycle = self._find_cycle(edges)
        return {
            "kind": "bandh",
            "cycle": cycle,
            "blocked": [{"tid": t.tid, "name": t.name,
                         "at": str(t.site),
                         "wait": self._wait_text(t.wait_for)}
                        for t in sorted(blocked, key=lambda x: x.tid)],
            "reason": ("a cycle in the wait-for graph"
                       if cycle else "every task is blocked and no wait can "
                                     "be satisfied"),
        }

    @staticmethod
    def _find_cycle(edges):
        state = {}
        stack = []

        def visit(node):
            state[node] = 1
            stack.append(node)
            for nxt in edges.get(node, []):
                if state.get(nxt) == 1:
                    return stack[stack.index(nxt):] + [nxt]
                if state.get(nxt, 0) == 0:
                    found = visit(nxt)
                    if found:
                        return found
            stack.pop()
            state[node] = 2
            return None

        for node in sorted(edges):
            if state.get(node, 0) == 0:
                found = visit(node)
                if found:
                    return found
        return None

    @staticmethod
    def _wait_text(wait):
        if not wait:
            return "nothing"
        if wait[0] == "join":
            return "join t%d" % wait[1]
        if wait[0] == "tal":
            return "lock #%d" % wait[1].id
        if wait[0] == "le":
            return "receive on channel #%d" % wait[1].id
        if wait[0] == "bhej":
            return "send on channel #%d" % wait[1].id
        if wait[0] == "sona":
            return "the clock (tick %d)" % wait[1]
        return str(wait[0])

    # -- scheduling points -------------------------------------------------

    def yield_point(self, tid):
        with self.cond:
            if self.aborted:
                raise Bandh(self.aborted)
            task = self.tasks[tid]
            task.clock[tid] = task.clock.get(tid, 0) + 1
            self.schedule.append(tid)
            self.steps += 1
            self.now += 1
            if self.steps > self.max_steps:
                self.aborted = {"kind": "step_limit", "steps": self.steps,
                                "reason": "the step limit was reached"}
                self.cond.notify_all()
                raise Bandh(self.aborted)
            if task.state != "blocked":
                task.state = "ready"
                if tid not in self.ready:
                    self.ready.append(tid)
            self._pick()
            self.cond.notify_all()
            while self.current != tid:
                if self.aborted:
                    raise Bandh(self.aborted)
                self.cond.wait()
            task.state = "running"

    def block(self, tid, wait_for):
        with self.cond:
            if self.aborted:
                raise Bandh(self.aborted)
            task = self.tasks[tid]
            task.state = "blocked"
            task.wait_for = wait_for
            self.schedule.append(tid)
            self.steps += 1
            nxt = self._pick()
            if nxt is None:
                self.aborted = self._deadlock()
                self.current = None
                self.cond.notify_all()
                raise Bandh(self.aborted)
            self.cond.notify_all()
            while self.current != tid:
                if self.aborted:
                    raise Bandh(self.aborted)
                self.cond.wait()
            task.state = "running"
            task.wait_for = None
            if task.pending_clock is not None:
                _merge(task.clock, task.pending_clock)
                task.pending_clock = None

    def unblock(self, tid, clock=None):
        with self.cond:
            task = self.tasks.get(tid)
            if task is None or task.state == "done":
                return
            if clock is not None:
                task.pending_clock = dict(clock)
            if task.state == "blocked":
                task.state = "ready"
                if tid not in self.ready:
                    self.ready.append(tid)
                self.cond.notify_all()

    def finish(self, tid):
        with self.cond:
            task = self.tasks.get(tid)
            if task is not None:
                task.state = "done"
            if tid in self.ready:
                self.ready.remove(tid)
            # A task that was waiting to join this one can run now.  The
            # wake-up must happen before the next pick, otherwise the
            # scheduler would see "nobody ready" and call a finished join
            # a deadlock.
            for other in list(self.tasks.values()):
                if other.state == "blocked" and other.wait_for and \
                        other.wait_for[0] == "join" and \
                        other.wait_for[1] == tid:
                    other.state = "ready"
                    other.wait_for = None
                    if other.tid not in self.ready:
                        self.ready.append(other.tid)
            if self.aborted:
                self.cond.notify_all()
                return
            if self.current == tid:
                nxt = self._pick()
                if nxt is None:
                    # Every remaining task is blocked: this is the same
                    # deadlock, seen from the finishing side.
                    self.aborted = self._deadlock()
                    self.current = None
                self.cond.notify_all()

    def all_done(self):
        return all(t.state == "done" for t in self.tasks.values())


class Runtime:
    """The whole runtime half: cells, channels, locks, tasks, the trace."""

    def __init__(self):
        self.scheduler = Scheduler()
        self.cells = {}
        self.channels = {}
        self.locks = {}
        self.next_id = [1]
        self.races = []
        self.deadlocks = []
        self.events = 0
        self.trace = []
        self.used = False
        self.reported_races = set()

    # -- helpers -----------------------------------------------------------

    def _id(self):
        value = self.next_id[0]
        self.next_id[0] += 1
        return value

    def _task(self):
        tid = getattr(_STATE, "tid", None)
        if tid is None:
            raise RuntimeError("samanvay: a coordination call outside a task")
        task = self.scheduler.tasks.get(tid)
        if task is None:
            raise RuntimeError("samanvay: unknown task %r" % (tid,))
        return task

    def _record(self, kind, tid, **payload):
        self.events += 1
        if len(self.trace) < 50000:
            entry = {"step": self.scheduler.steps, "kind": kind, "tid": tid}
            entry.update(payload)
            self.trace.append(entry)

    def _tick(self, task):
        task.clock[task.tid] = task.clock.get(task.tid, 0) + 1

    def _site(self):
        return Sthan(*getattr(_STATE, "site", (0, 0)))

    # -- lifecycle ---------------------------------------------------------

    def start(self, seed_value):
        if self.used:
            raise RuntimeError("samanvay: the runtime is already running")
        self.scheduler = Scheduler(seed_value)
        self.used = True
        main = self.scheduler.ensure_main()
        _STATE.tid = 0
        _STATE.site = (0, 0)
        return main

    def reset(self):
        self.scheduler = Scheduler()
        self.cells = {}
        self.channels = {}
        self.locks = {}
        self.next_id = [1]
        self.races = []
        self.deadlocks = []
        self.events = 0
        self.trace = []
        self.used = False
        self.reported_races = set()
        _PENDING_SEED[0] = None
        for attribute in ("tid", "site"):
            if hasattr(_STATE, attribute):
                delattr(_STATE, attribute)

    # -- cells -------------------------------------------------------------

    def cell(self, value, name=None):
        cid = self._id()
        cell = Cell(cid, name or ("cell%d" % cid), value)
        self.cells[cid] = cell
        return {"kind": "sajha", "id": cid, "name": cell.name}

    def _cell_of(self, handle):
        if not isinstance(handle, dict) or handle.get("kind") != "sajha":
            raise TypeError("samanvay: expected a cell from sv.sajha")
        return self.cells[handle["id"]]

    def read(self, handle):
        task = self._task()
        self._tick(task)
        cell = self._cell_of(handle)
        cell.accesses += 1
        epoch = cell.last_write
        if epoch is not None and not _hb(epoch.clock, task.clock):
            self._race(cell, epoch, Epoch(task.tid, task.clock, self._site()),
                       "read")
        cell.reads[task.tid] = Epoch(task.tid, task.clock, self._site())
        self._record("padh", task.tid, cell=cell.name, at=str(self._site()))
        self.scheduler.yield_point(task.tid)
        return cell.value

    def write(self, handle, value):
        task = self._task()
        self._tick(task)
        cell = self._cell_of(handle)
        cell.accesses += 1
        site = self._site()
        if cell.last_write is not None and \
                not _hb(cell.last_write.clock, task.clock):
            self._race(cell, cell.last_write,
                       Epoch(task.tid, task.clock, site), "write")
        for epoch in cell.reads.values():
            if not _hb(epoch.clock, task.clock):
                self._race(cell, epoch, Epoch(task.tid, task.clock, site),
                           "write")
        cell.value = value
        cell.last_write = Epoch(task.tid, task.clock, site)
        cell.reads = {tid: e for tid, e in cell.reads.items()
                      if not _hb(e.clock, task.clock)}
        self._record("likh", task.tid, cell=cell.name, at=str(site))
        self.scheduler.yield_point(task.tid)
        return value

    def _race(self, cell, left, right, kind):
        key = (cell.id, min(left.tid, right.tid), max(left.tid, right.tid),
               kind)
        if key in self.reported_races:
            return
        self.reported_races.add(key)
        self.races.append({
            "cell": cell.name, "cell_id": cell.id, "kind": kind,
            "first": left.to_dict(), "second": right.to_dict(),
            "reason": "neither access happens before the other",
        })

    # -- locks -------------------------------------------------------------

    def lock(self):
        lid = self._id()
        self.locks[lid] = Tal(lid)
        return {"kind": "tal", "id": lid}

    def _lock_of(self, handle):
        if not isinstance(handle, dict) or handle.get("kind") != "tal":
            raise TypeError("samanvay: expected a lock from sv.tal")
        return self.locks[handle["id"]]

    def acquire(self, handle):
        task = self._task()
        lock = self._lock_of(handle)
        while lock.owner is not None and lock.owner != task.tid:
            self._record("tal_wait", task.tid, lock=lock.id)
            lock.waiters.append(task.tid)
            try:
                self.scheduler.block(task.tid, ("tal", lock))
            finally:
                if task.tid in lock.waiters:
                    lock.waiters.remove(task.tid)
        if lock.owner == task.tid:
            raise RuntimeError("samanvay: lock #%d is not re-entrant" % lock.id)
        lock.owner = task.tid
        lock.taken += 1
        self._tick(task)
        if lock.release_clock is not None:
            _merge(task.clock, lock.release_clock)
        self._record("pakad", task.tid, lock=lock.id, at=str(self._site()))
        self.scheduler.yield_point(task.tid)

    def release(self, handle):
        task = self._task()
        lock = self._lock_of(handle)
        if lock.owner != task.tid:
            raise RuntimeError("samanvay: lock #%d is not held by this task"
                               % lock.id)
        self._tick(task)
        lock.owner = None
        lock.release_clock = dict(task.clock)
        self._record("chhod", task.tid, lock=lock.id, at=str(self._site()))
        for tid in list(lock.waiters):
            self.scheduler.unblock(tid, task.clock)
        self.scheduler.yield_point(task.tid)

    # -- channels ----------------------------------------------------------

    def channel(self, capacity=0):
        cid = self._id()
        self.channels[cid] = Channel(cid, capacity)
        return {"kind": "kanal", "id": cid}

    def _channel_of(self, handle):
        if not isinstance(handle, dict) or handle.get("kind") != "kanal":
            raise TypeError("samanvay: expected a channel from sv.kanal")
        return self.channels[handle["id"]]

    def send(self, handle, value):
        task = self._task()
        channel = self._channel_of(handle)
        if channel.closed:
            raise RuntimeError("samanvay: send on a closed channel #%d"
                               % channel.id)
        self._tick(task)
        clock = dict(task.clock)
        if channel.receivers:
            receiver = channel.receivers.pop(0)
            channel.buf.append(value)
            channel.sent += 1
            self._record("bhej", task.tid, channel=channel.id,
                         at=str(self._site()), direct=True)
            self.scheduler.unblock(receiver, clock)
            self.scheduler.yield_point(task.tid)
            return
        if len(channel.buf) < channel.cap:
            channel.buf.append(value)
            channel.send_clock = clock
            channel.sent += 1
            self._record("bhej", task.tid, channel=channel.id,
                         at=str(self._site()))
            self.scheduler.yield_point(task.tid)
            return
        channel.senders.append((task.tid, value))
        self._record("bhej_wait", task.tid, channel=channel.id)
        try:
            self.scheduler.block(task.tid, ("bhej", channel))
        finally:
            if (task.tid, value) in channel.senders:
                channel.senders.remove((task.tid, value))
        # The receiver moved the value into the buffer and handed its
        # clock back.
        channel.sent += 1
        self._record("bhej", task.tid, channel=channel.id,
                     at=str(self._site()))

    def recv(self, handle):
        task = self._task()
        channel = self._channel_of(handle)
        while not channel.buf:
            if channel.closed:
                self._tick(task)
                if channel.close_clock is not None:
                    _merge(task.clock, channel.close_clock)
                self._record("le", task.tid, channel=channel.id, closed=True)
                self.scheduler.yield_point(task.tid)
                return None
            channel.receivers.append(task.tid)
            self._record("le_wait", task.tid, channel=channel.id)
            self.scheduler.block(task.tid, ("le", channel))
        value = channel.buf.pop(0)
        channel.received += 1
        self._tick(task)
        if channel.send_clock is not None:
            _merge(task.clock, channel.send_clock)
        if channel.senders:
            sender, pending = channel.senders.pop(0)
            channel.buf.append(pending)
            self.scheduler.unblock(sender, task.clock)
        self._record("le", task.tid, channel=channel.id,
                     at=str(self._site()))
        self.scheduler.yield_point(task.tid)
        return value

    def close(self, handle):
        task = self._task()
        channel = self._channel_of(handle)
        if channel.closed:
            raise RuntimeError("samanvay: channel #%d is already closed"
                               % channel.id)
        channel.closed = True
        self._tick(task)
        channel.close_clock = dict(task.clock)
        for tid in list(channel.receivers):
            self.scheduler.unblock(tid, task.clock)
        channel.receivers = []
        self._record("band", task.tid, channel=channel.id, at=str(self._site()))
        self.scheduler.yield_point(task.tid)

    # -- tasks -------------------------------------------------------------

    def spawn(self, function, name="task", args=None):
        from .values import BunFunction
        if not isinstance(function, BunFunction):
            raise TypeError("samanvay: sv.kary expects a function")
        arguments = list(args or [])
        parent = self._task()
        self._tick(parent)
        tid = self._id()
        task = Task(tid, name or function.name or "task")
        task.clock = dict(parent.clock)
        task.clock[tid] = 0
        task.site = self._site()
        self.scheduler.register(task)
        self._record("kary", parent.tid, child=tid, at=str(self._site()))
        thread = threading.Thread(target=self._run_task,
                                  args=(task, function, arguments),
                                  daemon=True)
        task.thread = thread
        thread.start()
        return {"kind": "kary", "id": tid}

    def _run_task(self, task, function, arguments):
        from .interpreter import Interpreter
        _STATE.tid = task.tid
        try:
            self.scheduler.enter(task.tid)
            body = function.body
            if isinstance(body, dict) and "consts" in body:
                # The program was compiled by the register engine, so the
                # task body is register bytecode.  A VM cannot run it: its
                # dispatcher has no CONST op.  Pick the machine that
                # compiled the body, not the one that is convenient.
                from .regvm import RegisterVM
                engine = RegisterVM()
            elif isinstance(body, dict):
                # Stack bytecode from the VM engine.
                from .vm import VM
                engine = VM()
            else:
                engine = Interpreter()
            task.result = engine.call_function(function, list(arguments))
        except BaseException as error:                  # noqa: BLE001
            task.error = error
        finally:
            self.scheduler.finish(task.tid)
            if hasattr(_STATE, "tid"):
                delattr(_STATE, "tid")

    def _task_of(self, handle):
        if not isinstance(handle, dict) or handle.get("kind") != "kary":
            raise TypeError("samanvay: expected a task handle from sv.kary")
        return self.scheduler.tasks[handle["id"]]

    def join(self, handle):
        task = self._task()
        child = self._task_of(handle)
        while child.state != "done":
            self._record("mel_wait", task.tid, child=child.tid)
            self.scheduler.block(task.tid, ("join", child.tid))
        self._tick(task)
        _merge(task.clock, child.clock)
        self._record("mel", task.tid, child=child.tid, at=str(self._site()))
        if child.error is not None:
            raise child.error
        return child.result

    def cancel(self, handle):
        task = self._task()
        child = self._task_of(handle)
        child.cancel = True
        self._record("chhodo", task.tid, child=child.tid)

    def checkpoint(self):
        task = self._task()
        if task.cancel:
            raise RuntimeError("samanvay: task t%d was cancelled" % task.tid)
        self._record("ajna", task.tid, at=str(self._site()))
        self.scheduler.yield_point(task.tid)

    def sleep(self, millis):
        """Park the task until the virtual clock has moved `millis` ticks."""
        task = self._task()
        ticks = int(millis)
        if ticks <= 0:
            self._record("sona", task.tid, until=self.scheduler.now)
            self.scheduler.yield_point(task.tid)
            return self.scheduler.now
        wake = self.scheduler.now + ticks
        self._record("sona", task.tid, until=wake)
        self.scheduler.timers.append((wake, task.tid))
        try:
            self.scheduler.block(task.tid, ("sona", wake))
        finally:
            self.scheduler.timers = [item for item in self.scheduler.timers
                                     if item != (wake, task.tid)]
        return self.scheduler.now

    def clock(self):
        return self.scheduler.now

    # -- summary -----------------------------------------------------------

    def summary(self):
        sched = self.scheduler
        done = sum(1 for t in sched.tasks.values() if t.state == "done")
        return {
            "seed": sched.seed_value,
            "steps": sched.steps,
            "ticks": sched.now,
            "wakes": sched.wakes,
            "tasks": len(sched.tasks),
            "done": done,
            "schedule": list(sched.schedule),
            "schedule_hash": _hash(sched.schedule),
            "cells": len(self.cells),
            "channels": len(self.channels),
            "locks": len(self.locks),
            "events": self.events,
            "races": list(self.races),
            "deadlocks": list(self.deadlocks),
            "aborted": sched.aborted,
            "trace": list(self.trace[-200:]),
        }


def _hash(sequence):
    import hashlib
    digest = hashlib.sha256(
        ",".join(str(item) for item in sequence).encode("ascii")).hexdigest()
    return digest[:16]


_STATE = threading.local()
_RUNTIME = Runtime()


def runtime():
    return _RUNTIME


def reset():
    _RUNTIME.reset()


def set_site(line, col):
    _STATE.site = (line, col)


def clear_site():
    _STATE.site = (0, 0)


def site():
    return _STATE.site


# The seed is a promise about the future, so it may be given before the
# runtime exists.  `sv.beej(n)` stores it; the first coordination call
# starts the scheduler with it.  After that the seed is fixed: changing it
# mid-run would make the replay token a lie.
_PENDING_SEED = [None]


def seed(value):
    if _RUNTIME.used:
        raise RuntimeError(
            "samanvay: sv.beej must be called before the first "
            "coordination call (the seed is the replay token)")
    _PENDING_SEED[0] = int(value)
    return int(value)


def pending_seed():
    import os as _os
    if _PENDING_SEED[0] is not None:
        return _PENDING_SEED[0]
    try:
        return int(_os.environ.get("BUN_SAMANVAY_SEED", "0"))
    except ValueError:
        return 0


def summary():
    return _RUNTIME.summary()
