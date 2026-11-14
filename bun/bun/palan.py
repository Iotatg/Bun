"""Palan (पालन, "nurture") — the resilience wave.

0.7.0 asked *is this program safe?*  0.8.0 asked *which orders does it allow,
and can I see that order again?*  This wave asks the third question a
concurrent program always raises: **what happens when a task dies, and can I
make that death repeatable?**

The answer is built on two pieces that only exist because 0.8.0 shipped a
deterministic scheduler:

* **A virtual clock.**  One tick per scheduling point.  ``sona(n)`` parks a
  task until the clock has moved *n* ticks; when nothing else can run the
  scheduler jumps the clock to the earliest wake-up instead of calling it a
  deadlock.  A timeout is therefore measured in steps, not in nanoseconds,
  and a program that sleeps for an hour finishes in microseconds — the same
  microseconds, in the same order, on every machine.

* **A seeded die.**  ``sankat(p)`` says "this task may fail"; ``jokhim()``
  rolls.  The roll is derived from ``(seed, task, call index)``, so a chaos
  run is a function of the seed and nothing else.  A failure found at seed
  41 is found again at seed 41, tomorrow, on another machine.

On top of those, ``lib/bun/palan.bun`` writes the supervision policy in Bun
itself: supervisors with three restart strategies and a restart budget, a
retry with exponential backoff and deterministic jitter, and a circuit
breaker whose cooldown is measured on the virtual clock.

Eight codes, six static and two runtime:

    PL01  a supervisor with no children          (static)
    PL02  a retry that cannot retry              (static)
    PL03  a deadline nothing checks              (static)
    PL04  a supervisor that gives up at once     (static)
    PL05  sleeping while holding a lock          (static)
    PL06  a breaker that never closes            (static)
    PL07  a supervisor exhausted its budget      (runtime)
    PL08  a call was refused by an open breaker  (runtime)

No keyword was added.  Every name is a function of ``bun:palan``, so all 118
language packs can write the wave on the day it ships.
"""

from __future__ import annotations

import random
import threading
from dataclasses import dataclass, field

from . import ast
from .antar import Sthan, sthan_of
from .errors import BunRuntimeError
from .samanvay import Chinh, Nidan, _block_statements, _walk

# ---------------------------------------------------------------------------
# The ledger.  CODES is the single source of truth: the Bun library copies
# these rows verbatim, and the toolchain prints them.
# ---------------------------------------------------------------------------

CODES = {
    "PL01": {
        "name": "rikt rakshak",
        "message": "this supervisor has no children, so it can only wait",
        "hint": "add a child with palan.baccha(sup, fn, name)",
    },
    "PL02": {
        "name": "vyarth punar",
        "message": "this retry cannot retry: it allows one attempt",
        "hint": "attempts counts the first try, so use at least 2",
    },
    "PL03": {
        "name": "anaavashyak avadhi",
        "message": "this function sets a deadline that nothing checks",
        "hint": "call palan.jaanch() at the points where the work can stop",
    },
    "PL04": {
        "name": "shunya budget",
        "message": "this supervisor gives up on the first failure",
        "hint": "a restart budget of 0 is a crash with extra steps",
    },
    "PL05": {
        "name": "tal mein sona",
        "message": "this task sleeps while it holds a lock",
        "hint": "release the lock before sleeping; the holder blocks every "
                "other task",
    },
    "PL06": {
        "name": "kabhi band",
        "message": "this breaker never leaves the open state",
        "hint": "a cooldown of 0 means no trial call is ever allowed",
    },
    "PL07": {
        "name": "budget khatam",
        "message": "this supervisor exhausted its restart budget",
        "hint": "raise the budget, widen the window, or fix the child",
    },
    "PL08": {
        "name": "vyavdhan khula",
        "message": "this call was refused by an open circuit breaker",
        "hint": "the breaker opens after repeated failures; wait for the "
                "cooldown or handle the refusal",
    },
}

RULES = [
    {"id": code, "name": CODES[code]["name"], "text": CODES[code]["message"],
     "principle": principle, "bun_rule": rule}
    for code, principle, rule in [
        ("PL01", "Erlang/OTP: a supervisor exists to watch children", "P1"),
        ("PL02", "retry is a loop with a bound, not a wish", "P2"),
        ("PL03", "a deadline is a promise that something will check it", "P3"),
        ("PL04", "a restart budget is the difference between a hiccup and "
                 "an outage", "P1"),
        ("PL05", "a lock is held for as short a time as the work allows",
         "P4"),
        ("PL06", "a breaker that never closes is a permanent outage", "P2"),
        ("PL07", "escalation is a decision, and it must be reported", "P1"),
        ("PL08", "a refused call is a result, not an accident", "P2"),
    ]
]

# The exported names of bun:palan.  Names, never keywords.
PL_FNS = frozenset({
    "sona", "abhi", "avadhi", "jaanch", "sankat", "jokhim",
    "rakshak", "baccha", "chalau", "punar", "vyavdhi", "guzar",
    "report", "niyam", "codes", "audit", "ledger",
})

# Calls that change the state of a supervision structure.
SUPERVISION_FNS = frozenset({"rakshak", "baccha", "chalau"})
POLICY_FNS = frozenset({"punar", "vyavdhi", "guzar"})
CLOCK_FNS = frozenset({"sona", "abhi", "avadhi", "jaanch"})


# ---------------------------------------------------------------------------
# Static model
# ---------------------------------------------------------------------------

@dataclass
class Supervisor:
    """One `palan.rakshak(...)` binding and the children it is given."""

    name: str
    sthan: Sthan
    strategy: str = ""
    budget: int | None = None
    window: int | None = None
    children: list = field(default_factory=list)

    def to_dict(self):
        return {"name": self.name, "at": str(self.sthan),
                "strategy": self.strategy, "budget": self.budget,
                "window": self.window,
                "children": [c[0] for c in self.children]}


@dataclass
class Event:
    """One palan call, in source order, inside one scope."""

    kind: str
    sthan: Sthan
    args: tuple = ()


class Analysis:
    """The result of the static pass."""

    def __init__(self, filename="<program>", source=""):
        self.filename = filename
        self.source = source
        self.alias = None
        self.sv_alias = None
        self.supervisors: dict[str, Supervisor] = {}
        self.events: dict[str, list[Event]] = {}
        self.nidan: list[Nidan] = []
        self.unknown_baccha = False
        self.program = None

    # -- reporting ---------------------------------------------------------

    def add(self, code, sthan, labels=None, notes=None, hint=None):
        row = CODES.get(code, {})
        nidan = Nidan(code, message=row.get("message", ""), primary=sthan,
                      labels=labels, notes=notes,
                      hint=hint or row.get("hint", ""),
                      filename=self.filename, family="palan")
        nidan.name = row.get("name", "unknown")
        self.nidan.append(nidan)

    def stats(self):
        total_children = sum(len(s.children) for s in self.supervisors.values())
        return {
            "supervisors": len(self.supervisors),
            "children": total_children,
            "strategies": sorted({s.strategy
                                  for s in self.supervisors.values()
                                  if s.strategy}),
            "retries": sum(1 for events in self.events.values()
                           for e in events if e.kind == "punar"),
            "deadlines": sum(1 for events in self.events.values()
                             for e in events if e.kind == "avadhi"),
            "checkpoints": sum(1 for events in self.events.values()
                               for e in events if e.kind == "jaanch"),
            "sleeps": sum(1 for events in self.events.values()
                          for e in events if e.kind == "sona"),
            "breakers": sum(1 for events in self.events.values()
                            for e in events if e.kind == "vyavdhi"),
            "nidan": len(self.nidan),
        }


# ---------------------------------------------------------------------------
# Small AST helpers.  The parser builds `palan.x(y)` as a MethodCall and
# `(palan.x)(y)` as a Call; both spell the same function.
# ---------------------------------------------------------------------------

def _call_name(node, alias):
    if alias is None:
        return None
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


def _call_args(node):
    if isinstance(node, ast.MethodCall):
        return tuple(node.args or ())
    if isinstance(node, ast.Call):
        return tuple(node.args or ())
    return ()


def _int_of(node):
    if isinstance(node, ast.Literal) and isinstance(node.value, int) and \
            not isinstance(node.value, bool):
        return node.value
    return None


def _text_of(node):
    if isinstance(node, ast.Literal) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Identifier):
        return node.name
    return None


def _alias_of(program, module):
    """The name a program bound `import "bun:<module>" as X` to."""
    for statement in program.statements:
        if not isinstance(statement, ast.ImportStmt):
            continue
        path = statement.path or ""
        if path == "bun:" + module or path.endswith("/" + module + ".bun") \
                or path == module + ".bun":
            return statement.alias or module
    return None


# ---------------------------------------------------------------------------
# The static pass
# ---------------------------------------------------------------------------

def analyze_program(program, filename="<program>", source=""):
    result = Analysis(filename=filename, source=source)
    result.program = program
    result.alias = _alias_of(program, "palan")
    result.sv_alias = _alias_of(program, "samanvay")
    if result.alias is None:
        return result

    # 1. Walk every function body and the top level, recording the calls in
    #    source order per scope.  A scope is the function name, or "<top>".
    scopes = [("<top>", program)]
    for statement in program.statements:
        if isinstance(statement, ast.FnDecl):
            scopes.append((statement.name, statement.body))

    for name, body in scopes:
        events = []
        _collect(body, result.alias, events, top=(name == "<top>"))
        events.sort(key=lambda e: (e.sthan.line, e.sthan.col))
        result.events[name] = events

    # 2. Bind supervisors: `let s = palan.rakshak(...)`.
    for statement in program.statements:
        if isinstance(statement, ast.LetStmt):
            kind = _call_name(statement.value, result.alias)
            if kind == "rakshak":
                _bind_supervisor(result, statement.name, statement.value)
        if isinstance(statement, ast.FnDecl):
            for inner in _walk_nodes(statement.body):
                if isinstance(inner, ast.LetStmt):
                    if _call_name(inner.value, result.alias) == "rakshak":
                        _bind_supervisor(result, inner.name, inner.value)

    # 3. Attach children: `palan.baccha(sup, fn, name)`.
    for events in result.events.values():
        for event in events:
            if event.kind != "baccha":
                continue
            if not event.args:
                continue
            target = _text_of(event.args[0])
            if target is None:
                result.unknown_baccha = True
                continue
            supervisor = result.supervisors.get(target)
            if supervisor is None:
                # A supervisor created somewhere we cannot see (a parameter,
                # a call result).  Say nothing rather than guess.
                result.unknown_baccha = True
                continue
            label = _text_of(event.args[2]) if len(event.args) > 2 else None
            supervisor.children.append((label or "child", event.sthan))

    # 4. The six static checks.
    _check_pl01(result)
    _check_pl02(result)
    _check_pl03(result)
    _check_pl04(result)
    _check_pl05(result)
    _check_pl06(result)

    result.nidan.sort(key=lambda n: (n.primary.line, n.primary.col, n.code))
    return result


def _walk_nodes(node):
    out = []
    _walk(node, lambda item, parents: out.append(item))
    return out


def _collect(body, alias, events, top=False):
    """Record every palan call in source order.

    A top-level walk must not descend into a function body, or every call
    inside a function would be counted twice: once for the file and once
    for the function.
    """
    if top:
        for statement in _block_statements(body):
            if isinstance(statement, ast.FnDecl):
                continue
            for node in _walk_nodes(statement):
                kind = _call_name(node, alias)
                if kind is not None:
                    events.append(Event(kind, sthan_of(node),
                                        _call_args(node)))
        return
    for node in _walk_nodes(body):
        kind = _call_name(node, alias)
        if kind is None:
            continue
        events.append(Event(kind, sthan_of(node), _call_args(node)))


def _bind_supervisor(result, name, call):
    args = _call_args(call)
    supervisor = Supervisor(name=name, sthan=sthan_of(call))
    if args:
        strategy = _text_of(args[0])
        if strategy is not None:
            supervisor.strategy = strategy
    if len(args) > 1:
        supervisor.budget = _int_of(args[1])
    if len(args) > 2:
        supervisor.window = _int_of(args[2])
    result.supervisors[name] = supervisor


def _check_pl01(result):
    """A supervisor with no children."""
    if result.unknown_baccha:
        return
    for supervisor in result.supervisors.values():
        if supervisor.children:
            continue
        result.add("PL01", supervisor.sthan,
                   labels=[Chinh(supervisor.sthan,
                                 "supervisor '%s' has no children"
                                 % supervisor.name, True)],
                   notes=["a supervisor with no children returns immediately; "
                          "it watches nothing and restarts nothing"])


def _check_pl02(result):
    """A retry that cannot retry."""
    for events in result.events.values():
        for event in events:
            if event.kind != "punar" or len(event.args) < 2:
                continue
            attempts = _int_of(event.args[1])
            if attempts is None or attempts > 1:
                continue
            result.add("PL02", event.sthan,
                       labels=[Chinh(event.sthan, "attempts = %d" % attempts,
                                     True)],
                       notes=["attempts counts the first try, so 1 means "
                              "the body runs exactly once"])


def _check_pl03(result):
    """A deadline that nothing checks."""
    for scope, events in result.events.items():
        deadlines = [e for e in events if e.kind == "avadhi"]
        if not deadlines:
            continue
        checks = [e for e in events if e.kind == "jaanch"]
        if checks:
            continue
        first = deadlines[0]
        result.add("PL03", first.sthan,
                   labels=[Chinh(first.sthan, "deadline set here", True)],
                   notes=["the clock moves at every scheduling point, but a "
                          "task that never yields never notices",
                          "scope '%s' has no palan.jaanch()" % scope])


def _check_pl04(result):
    """A supervisor that gives up on the first failure."""
    for supervisor in result.supervisors.values():
        if supervisor.budget != 0:
            continue
        result.add("PL04", supervisor.sthan,
                   labels=[Chinh(supervisor.sthan,
                                 "restart budget = 0", True)],
                   notes=["the first failure escalates, which is the same "
                          "outcome as running the child once"])


def _check_pl05(result):
    """Sleeping while holding a lock.

    The lock words belong to bun:samanvay, so the check needs both aliases.
    It reads the calls in source order inside one function and keeps a
    depth counter: a `sona` while the depth is positive is a sleep under a
    lock.
    """
    if result.sv_alias is None:
        return
    for scope, events in result.events.items():
        if scope == "<top>":
            continue
        marks = []
        for event in events:
            if event.kind == "sona":
                marks.append(("sona", event.sthan, None))
        for name, body in _scope_bodies(result, scope):
            for node in _walk_nodes(body):
                kind = _call_name(node, result.sv_alias)
                if kind in ("pakad", "chhod"):
                    marks.append((kind, sthan_of(node), None))
        marks.sort(key=lambda m: (m[1].line, m[1].col))
        depth = 0
        held = None
        for kind, sthan, _ in marks:
            if kind == "pakad":
                depth += 1
                held = held or sthan
            elif kind == "chhod":
                depth = max(0, depth - 1)
                if depth == 0:
                    held = None
            elif kind == "sona" and depth > 0:
                result.add("PL05", sthan,
                           labels=[Chinh(sthan, "sleeps here", True),
                                   Chinh(held, "lock taken here")],
                           notes=["the virtual clock advances while the lock "
                                  "is held, so every waiter loses that time"])


def _scope_bodies(result, scope):
    """The AST bodies of the function called `scope`."""
    out = []
    if result.program is None:
        return out
    for node in _walk_nodes(result.program):
        if isinstance(node, ast.FnDecl) and node.name == scope:
            out.append((scope, node.body))
    return out


def _check_pl06(result):
    """A breaker that never leaves the open state."""
    for events in result.events.values():
        for event in events:
            if event.kind != "vyavdhi" or len(event.args) < 2:
                continue
            cooldown = _int_of(event.args[1])
            if cooldown is None or cooldown > 0:
                continue
            result.add("PL06", event.sthan,
                       labels=[Chinh(event.sthan, "cooldown = 0", True)],
                       notes=["a breaker opens after the failure threshold "
                              "and only a cooldown lets it try again"])


def analyze_source(source, filename="<program>"):
    from .lexer import Lexer
    from .parser import Parser
    program = Parser(Lexer(source).tokenize()).parse()
    return analyze_program(program, filename, source)


# ---------------------------------------------------------------------------
# Verification: the internal consistency a tool can rely on.
# ---------------------------------------------------------------------------

@dataclass
class Check:
    ok: bool
    problems: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def verify(analysis):
    problems = []
    seen = set()
    for nidan in analysis.nidan:
        if nidan.code not in CODES:
            problems.append("unknown code %s" % nidan.code)
        if nidan.primary.line < 0:
            problems.append("%s has no primary span" % nidan.code)
        key = (nidan.code, str(nidan.primary))
        if key in seen:
            problems.append("duplicate nidan %s at %s" % key)
        seen.add(key)
    for code in CODES:
        if not any(n.code == code for n in analysis.nidan):
            continue
        if not CODES[code]["name"]:
            problems.append("%s has no name" % code)
    stats = analysis.stats()
    stats["rules"] = len(RULES)
    stats["codes"] = len(CODES)
    return Check(not problems, problems, stats)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_text(analysis):
    stats = analysis.stats()
    out = ["PALAN — resilience report for %s" % analysis.filename,
           "  module      %s" % (analysis.alias or "(not imported)"),
           "  supervisors %d (%d children)"
           % (stats["supervisors"], stats["children"]),
           "  retries     %d" % stats["retries"],
           "  deadlines   %d (%d checkpoints)"
           % (stats["deadlines"], stats["checkpoints"]),
           "  sleeps      %d" % stats["sleeps"],
           "  breakers    %d" % stats["breakers"],
           "  nidan       %d" % stats["nidan"]]
    if analysis.supervisors:
        out.append("")
        out.append("supervisors")
        for supervisor in analysis.supervisors.values():
            out.append("  %-12s %-10s budget=%s window=%s children=%d  at %s"
                       % (supervisor.name, supervisor.strategy or "?",
                          supervisor.budget, supervisor.window,
                          len(supervisor.children), supervisor.sthan))
    if analysis.nidan:
        out.append("")
        for nidan in analysis.nidan:
            out.append(nidan.render(analysis.source))
    elif analysis.alias:
        out.append("")
        out.append("PALAN OK — no nidan")
    return "\n".join(out)


def render_json(analysis):
    import json
    return json.dumps({
        "file": analysis.filename,
        "alias": analysis.alias,
        "stats": analysis.stats(),
        "supervisors": [s.to_dict() for s in analysis.supervisors.values()],
        "nidan": [n.to_dict() for n in analysis.nidan],
    }, indent=2, sort_keys=True)


def render_dot(analysis):
    lines = ["digraph palan {", '  rankdir="LR";',
             '  node [shape=box, fontname="monospace"];']
    for name, supervisor in analysis.supervisors.items():
        lines.append('  "%s" [label="%s\\n%s"];'
                     % (name, name, supervisor.strategy or "?"))
        for child, _sthan in supervisor.children:
            safe = "%s/%s" % (name, child)
            lines.append('  "%s" [label="%s"];' % (safe, child))
            lines.append('  "%s" -> "%s";' % (name, safe))
    lines.append("}")
    return "\n".join(lines)


def render_stats(analysis):
    import json
    return json.dumps(analysis.stats(), indent=2, sort_keys=True)


def render_explain(analysis, source=""):
    out = ["PALAN — what the wave promises", ""]
    for rule in RULES:
        out.append("%s  %-18s %s" % (rule["id"], rule["name"], rule["text"]))
        out.append("     principle: %s   bun rule: %s"
                   % (rule["principle"], rule["bun_rule"]))
    out.append("")
    out.append("The clock: one tick per scheduling point.  sona(n) waits n")
    out.append("ticks.  When nothing can run, the scheduler jumps to the")
    out.append("earliest wake-up instead of reporting a deadlock.")
    out.append("")
    out.append("The die: sankat(p) says a task may fail, jokhim() rolls.")
    out.append("The roll is (seed, task, call index), so a chaos run is a")
    out.append("function of the seed alone.")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Runtime: the clock, the die, the counters.
# ---------------------------------------------------------------------------

_STATE = threading.local()
_DEADLINES = {}      # tid -> absolute tick
_RISK = [0.0]        # the program-wide failure probability
_DICE = {}           # tid -> rolls so far
_CHOICES = {}        # tid -> choices so far (a separate stream)
_EVENTS = []         # escalation and refusal, for --run
_REPORT = {"rolls": 0, "failures": 0, "escalations": 0, "refusals": 0,
           "sleeps": 0, "ticks": 0}


def reset():
    global _DEADLINES, _RISK, _DICE, _CHOICES, _EVENTS
    _DEADLINES = {}
    _RISK[0] = 0.0
    _DICE = {}
    _CHOICES = {}
    _EVENTS = []
    for key in _REPORT:
        _REPORT[key] = 0
    for attribute in ("deadline", "risk"):
        if hasattr(_STATE, attribute):
            delattr(_STATE, attribute)


def _runtime():
    """The Samanvay runtime, started on first use.

    Palan has no runtime of its own: it borrows the scheduler, because a
    second clock would be a second truth.  The first call starts it with
    the pending seed, exactly as the first `sv.*` call would.
    """
    from . import samanvay
    runtime = samanvay.runtime()
    if not runtime.used:
        runtime.start(samanvay.pending_seed())
    if getattr(samanvay._STATE, "tid", None) is None:
        samanvay._STATE.tid = 0
    return runtime


def _task_id():
    from . import samanvay
    return getattr(samanvay._STATE, "tid", None)


def _require_task(name):
    _runtime()
    tid = _task_id()
    if tid is None:
        raise BunRuntimeError(
            "palan: %s() needs a task; import bun:samanvay and call it "
            "inside the program" % name)
    return tid


def clock():
    return _runtime().scheduler.now


def sleep(millis):
    tid = _require_task("sona")
    _runtime().sleep(millis)
    _REPORT["sleeps"] += 1
    _REPORT["ticks"] = _runtime().scheduler.now
    return tid


def deadline(millis):
    tid = _require_task("avadhi")
    _DEADLINES[tid] = _runtime().scheduler.now + int(millis)
    return _DEADLINES[tid]


def check():
    tid = _require_task("jaanch")
    limit = _DEADLINES.get(tid)
    now = _runtime().scheduler.now
    if limit is not None and now >= limit:
        from . import samanvay
        raise BunRuntimeError(
            "palan: deadline exceeded at tick %d (limit %d)"
            % (now, limit), samanvay.site()[0], samanvay.site()[1])
    return now


def set_risk(probability):
    """Set the program-wide chance that a roll fails.

    The probability is global on purpose: `sankat` describes the world the
    program runs in, not one task in it.  The roll itself is per task, so
    two tasks that both roll get different answers from the same seed.
    """
    _RISK[0] = float(probability)
    return _RISK[0]


def roll():
    """One deterministic roll of the die for the current task."""
    tid = _require_task("jokhim")
    probability = _RISK[0]
    index = _DICE.get(tid, 0)
    _DICE[tid] = index + 1
    _REPORT["rolls"] += 1
    if probability <= 0.0:
        return False
    seed_value = _runtime().scheduler.seed_value
    value = random.Random("%d:%d:%d" % (seed_value, tid, index)).random()
    hit = value < probability
    if hit:
        _REPORT["failures"] += 1
    return hit


def note(code, **payload):
    """Record a runtime finding (PL07 escalation, PL08 refusal)."""
    entry = {"code": code, "tick": _runtime().scheduler.now}
    entry.update(payload)
    _EVENTS.append(entry)
    if code == "PL07":
        _REPORT["escalations"] += 1
    elif code == "PL08":
        _REPORT["refusals"] += 1
    return entry


def summary():
    data = dict(_REPORT)
    data["ticks"] = _runtime().scheduler.now
    data["events"] = list(_EVENTS)
    return data


def report_nidan(source=""):
    """Render the runtime findings as nidan, for `bun palan --run`."""
    out = []
    for entry in _EVENTS:
        code = entry.get("code")
        if code not in CODES:
            continue
        primary = Sthan()
        out.append(Nidan(code, primary=primary, family="palan",
                         notes=["tick %s" % entry.get("tick")],
                         filename="<runtime>"))
    return out
