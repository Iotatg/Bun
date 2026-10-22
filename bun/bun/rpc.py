"""The machine surface of the language.

The language is queryable, not just readable: an assistant drives a
session of Bun over JSON-RPC 2.0, one object per line, on the standard
input and the standard output.

The protocol never changes the language. It is a surface over the same
front end, the same checker and the same machine, and the session it
keeps is the session of the REPL.
"""

import json
import os
import sys

from .checker import Checker
from .compiler import Compiler
from .dict import BunDict
from .errors import BunError, hint_for
from .lexer import Lexer
from .ops import type_name
from .parser import Parser
from .values import SECRET_MASK, BunSecret, stringify
from .vm import VM

# The codes of the protocol.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
LANGUAGE_ERROR = -32000

# The kinds of the errors of the language.
KINDS = {
    "LexError": "lex",
    "ParseError": "parse",
    "BunTypeError": "type",
    "BunRuntimeError": "runtime",
    "BunError": "runtime",
}


def error_kind(error):
    """The kind of an error of the language."""
    return KINDS.get(type(error).__name__, "runtime")


def value_to_json(value):
    """The JSON of a value of the language.

    The structure is the answer; the text of the value is there too,
    because a human reads the text.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, BunSecret):
        return SECRET_MASK
    if isinstance(value, (list, tuple)):
        return [value_to_json(item) for item in value]
    if isinstance(value, BunDict):
        return {str(key): value_to_json(item)
                for key, item in zip(value.keys(), value.values())}
    if isinstance(value, dict):
        return {str(key): value_to_json(item)
                for key, item in value.items()}
    return {"kind": "fn", "name": getattr(value, "name", "")}


def value_type(value):
    """The name of the type of a value, the way the language names it."""
    name = type_name(value)
    if name in ("BunFunction", "Builtin"):
        return "fn"
    return name


class Session:
    """A session of the language.

    The session holds a machine and the scope of the names, so a value
    defined by one call is there for the next one.
    """

    def __init__(self, engine="vm", base_dir=None):
        self.engine = engine
        self.base_dir = base_dir or os.getcwd()
        self.vm = VM()
        self.checker = Checker()
        self.scope = {}

    def eval(self, source, check=True):
        """Run the source in the session and return the value."""
        program = Parser(Lexer(source).tokenize()).parse()
        if check:
            self.scope = self.checker.check(program, base_dir=self.base_dir,
                                           scope=self.scope)
        statements = program.statements
        if len(statements) == 1 and _is_expression(statements[0]):
            value = self.vm.eval_expression(statements[0].expr,
                                            self.vm.globals, self.base_dir)
            return value
        code = Compiler("<repl>", source).compile_program(program)
        self.vm.run(code, env=self.vm.globals, base_dir=self.base_dir)
        return None

    def check(self, source):
        """Check the source and return the diagnostics."""
        program = Parser(Lexer(source).tokenize()).parse()
        self.scope = self.checker.check(program, base_dir=self.base_dir,
                                       scope=self.scope)
        return {"ok": True}

    def compile(self, source):
        """Return the bytecode of the source."""
        program = Parser(Lexer(source).tokenize()).parse()
        code = Compiler("<repl>", source).compile_program(program)
        return {"instructions": [_instruction(entry) for entry in code["code"]],
                "constants": [stringify(item) for item in code["params"]]}

    def symbols(self):
        """The names the session holds.

        The names of the program are the ones of the scope of the
        checker; the builtins are not names of the session, they are
        names of the language.
        """
        return {"names": sorted(self.scope)}

    def reset(self):
        """Empty the session."""
        self.vm = VM()
        self.checker = Checker()
        self.scope = {}
        return {"ok": True}


def _is_expression(statement):
    from . import ast
    return isinstance(statement, ast.ExprStmt)


def _instruction(entry):
    """The JSON of one instruction of the bytecode."""
    op, arg, line, col = entry
    if isinstance(arg, (list, tuple)):
        described = [str(item) for item in arg]
    else:
        described = str(arg)
    return {"op": op, "arg": described, "line": line, "col": col}


class Server:
    """The server of the protocol.

    The server reads the requests on the input and writes the answers on
    the output, one JSON object per line.
    """

    def __init__(self, session=None, input_stream=None, output_stream=None):
        self.session = session or Session()
        self.input = input_stream if input_stream is not None else sys.stdin
        self.output = output_stream if output_stream is not None else sys.stdout

    def handle(self, request):
        """The answer of one request, or None when the session ends."""
        if not isinstance(request, dict):
            return _error(None, INVALID_REQUEST,
                          "the request must be an object")
        identifier = request.get("id")
        method = request.get("method")
        if not isinstance(method, str):
            return _error(identifier, INVALID_REQUEST,
                          "the request must have a method")
        params = request.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return _error(identifier, INVALID_PARAMS,
                          "the params must be an object")
        handler = getattr(self, "_method_" + method.replace(".", "_"), None)
        if handler is None:
            return _error(identifier, METHOD_NOT_FOUND,
                          "unknown method '%s'" % method)
        try:
            result = handler(params)
        except BunError as error:
            data = {"kind": error_kind(error), "line": error.line,
                    "col": error.col}
            hint = hint_for(error.msg)
            if hint is not None:
                data["hint"] = hint
            return _error(identifier, LANGUAGE_ERROR, error.msg, data)
        except (ValueError, TypeError, KeyError) as error:
            return _error(identifier, INVALID_PARAMS, str(error))
        if method == "shutdown":
            return _result(identifier, result)
        return _result(identifier, result)

    # The methods.

    def _method_eval(self, params):
        source = _source(params)
        value = self.session.eval(source)
        return {"value": value_to_json(value), "type": value_type(value),
                "printed": stringify(value) if value is not None else ""}

    def _method_check(self, params):
        return self.session.check(_source(params))

    def _method_compile(self, params):
        return self.session.compile(_source(params))

    def _method_symbols(self, params):
        return self.session.symbols()

    def _method_reset(self, params):
        return self.session.reset()

    def _method_api(self, params):
        from .cli import api_data
        return api_data()

    def _method_docs(self, params):
        from . import docs
        symbol = params.get("symbol")
        if symbol is None:
            return {"symbols": docs.doc_names()}
        entry = docs.DOCS.get(symbol)
        if entry is None:
            raise ValueError("unknown symbol '%s'" % symbol)
        return dict(entry)

    def _method_shutdown(self, params):
        return {"ok": True}

    # The loop.

    def serve(self):
        """Read the requests until the end of the input."""
        for line in self.input:
            line = line.strip()
            if line == "":
                continue
            try:
                request = json.loads(line)
            except ValueError as error:
                self._write(_error(None, PARSE_ERROR, str(error)))
                continue
            answer = self.handle(request)
            if answer is not None:
                self._write(answer)
            if isinstance(request, dict) and request.get("method") == \
                    "shutdown":
                break
        return 0

    def _write(self, answer):
        self.output.write(json.dumps(answer) + "\n")
        self.output.flush()


def _source(params):
    source = params.get("source")
    if source is None:
        source = params.get("code")
    if not isinstance(source, str):
        raise ValueError("the params need a 'source'")
    return source


def _result(identifier, result):
    return {"jsonrpc": "2.0", "id": identifier, "result": result}


def _error(identifier, code, message, data=None):
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": identifier, "error": error}
