from __future__ import annotations
from .records import field, record


@record
class Program:
    statements: list[object]


@record
class LetStmt:
    name: str
    value: object
    mutable: bool = False
    line: int = 0
    col: int = 0
    exported: bool = False
    type_ann: str | None = None


@record
class AssignStmt:
    target: object
    value: object
    line: int = 0
    col: int = 0


@record
class UnpackTarget:
    target_kind: str
    targets: list[object] = field(default_factory=list)
    name: str | None = None
    line: int = 0
    col: int = 0


@record
class UnpackStmt:
    targets: list[object]
    value: object
    mutable: bool = True
    line: int = 0
    col: int = 0
    exported: bool = False


@record
class ExprStmt:
    expr: object
    line: int = 0
    col: int = 0


@record
class Block:
    statements: list[object]
    line: int = 0
    col: int = 0


@record
class IfStmt:
    condition: object
    then_branch: object
    else_branch: object | None = None
    line: int = 0
    col: int = 0


@record
class WhileStmt:
    condition: object
    body: object
    orelse: object = None
    line: int = 0
    col: int = 0


@record
class ForStmt:
    targets: list[str]
    iterable: object
    body: object
    orelse: object = None
    line: int = 0
    col: int = 0


@record
class AssertStmt:
    condition: object
    message: object = None
    line: int = 0
    col: int = 0


@record
class MatchPattern:
    pattern_kind: str
    name: str = ""
    value: object = None
    high: object = None
    items: list[object] = field(default_factory=list)
    entries: list[object] = field(default_factory=list)
    tail: object = None
    guard: object = None
    line: int = 0
    col: int = 0


@record
class MatchStmt:
    subject: object
    cases: list[object] = field(default_factory=list)
    line: int = 0
    col: int = 0


@record
class StructField:
    name: str
    type_ann: str | None = None
    mutable: bool = True
    default: object = None
    line: int = 0
    col: int = 0


@record
class StructDecl:
    name: str
    fields: list[object]
    line: int = 0
    col: int = 0


@record
class ImplDecl:
    type_name: str
    methods: list[object]
    line: int = 0
    col: int = 0


@record
class ProtocolDecl:
    name: str
    methods: list[object]
    line: int = 0
    col: int = 0


@record
class Attribute:
    object: object
    name: str
    line: int = 0
    col: int = 0


@record
class FnDecl:
    name: str
    params: list[object]
    body: object
    line: int = 0
    col: int = 0
    exported: bool = False
    return_type: str | None = None
    decorators: list[object] = field(default_factory=list)
    type_params: list[object] = field(default_factory=list)


@record
class TypeParam:
    """A type parameter of a function.

    The bound is the name of a class of types the parameter may not
    leave: `Num`, `Ord`, `Eq`, `Hash` or `Show`. A parameter without a
    bound may be any type.
    """
    name: str
    bound: str | None = None
    line: int = 0
    col: int = 0


@record
class Param:
    name: str
    type_name: str | None = None
    default: object | None = None
    param_kind: str = "positional"
    line: int = 0
    col: int = 0


@record
class ReturnStmt:
    value: object | None = None
    line: int = 0
    col: int = 0


@record
class TryStmt:
    try_block: object
    catch_params: list[str]
    catch_block: object
    finally_body: object = None
    line: int = 0
    col: int = 0


@record
class ThrowStmt:
    value: object
    cause: object = None
    line: int = 0
    col: int = 0


@record
class WithItem:
    expr: object
    name: str
    line: int = 0
    col: int = 0


@record
class WithStmt:
    items: list[object]
    body: object
    line: int = 0
    col: int = 0


@record
class ScopeStmt:
    body: object
    line: int = 0
    col: int = 0


@record
class BreakStmt:
    line: int = 0
    col: int = 0


@record
class ContinueStmt:
    line: int = 0
    col: int = 0


@record
class DelStmt:
    target: object
    line: int = 0
    col: int = 0


@record
class YieldStmt:
    value: object = None
    line: int = 0
    col: int = 0


@record
class YieldExpr:
    value: object = None
    line: int = 0
    col: int = 0


@record
class Literal:
    value: object
    line: int = 0
    col: int = 0


@record
class FString:
    parts: list[object]
    line: int = 0
    col: int = 0


@record
class FStringPart:
    literal: str | None = None
    expr: object | None = None
    spec: str | None = None
    conv: str | None = None
    source_text: str | None = None


@record
class Identifier:
    name: str
    line: int = 0
    col: int = 0


@record
class ListLiteral:
    elements: list[object]
    line: int = 0
    col: int = 0


@record
class Comprehension:
    element: object
    key: object | None = None
    value: object | None = None
    clauses: list[object] = field(default_factory=list)
    is_dict: bool = False
    line: int = 0
    col: int = 0


@record
class ComprehensionClause:
    target: str
    iterable: object
    condition: object | None = None
    line: int = 0
    col: int = 0


@record
class Unary:
    op: str
    operand: object
    line: int = 0
    col: int = 0


@record
class Unwrap:
    expr: object
    line: int = 0
    col: int = 0


@record
class Binary:
    left: object
    op: str
    right: object
    line: int = 0
    col: int = 0


@record
class Logical:
    left: object
    op: str
    right: object
    line: int = 0
    col: int = 0


@record
class Call:
    callee: object
    args: list[object]
    line: int = 0
    col: int = 0
    kwargs: list[object] = field(default_factory=list)


@record
class Index:
    target: object
    index: object
    line: int = 0
    col: int = 0


@record
class Slice:
    start: object | None = None
    stop: object | None = None
    step: object | None = None
    line: int = 0
    col: int = 0


@record
class MethodCall:
    receiver: object
    method: str
    args: list[object]
    line: int = 0
    col: int = 0


@record
class DictLiteral:
    entries: list[object]
    line: int = 0
    col: int = 0


@record
class ImportStmt:
    names: list[str]
    path: str
    line: int = 0
    col: int = 0
