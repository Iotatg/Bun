import os

from . import modules
from .compiler import Compiler
from .dict import BunDict
from .errors import BunRuntimeError, BunTypeError
from .lexer import Lexer
from .records import fields as record_fields, is_record
from .parser import Parser
from .values import Builtin, BunFunction, canonical_dump
from .vm import VM

SELFHOST_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "selfhost")

_DRIVER_CODE = None


def driver_code():
    global _DRIVER_CODE
    if _DRIVER_CODE is None:
        path = os.path.join(SELFHOST_DIR, "main.bun")
        with open(path, "r") as handle:
            source = handle.read()
        program = Parser(Lexer(source).tokenize()).parse()
        _DRIVER_CODE = Compiler(path, source).compile_program(program)
    return _DRIVER_CODE


def normalize(value):
    if isinstance(value, BunDict):
        return {
            normalize(key[1]): normalize(item)
            for key, item in value.items.items()
        }
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value]
    return value


def canonical(value):
    return canonical_dump(value)


def token_to_data(token):
    return {
        "type": token.type,
        "value": token.value,
        "line": token.line,
        "col": token.col,
    }


def ast_to_data(node):
    data = {"kind": type(node).__name__}
    for name in record_fields(type(node)):
        data[name] = _ast_value(getattr(node, name))
    return data


def _ast_value(value):
    if is_record(value):
        return ast_to_data(value)
    if isinstance(value, (list, tuple)):
        return [_ast_value(item) for item in value]
    return value


def code_to_data(code):
    data = {
        "name": code["name"],
        "params": list(code["params"]),
        "code": [
            [instruction[0], _arg_to_data(instruction[1]),
             instruction[2], instruction[3]]
            for instruction in code["code"]
        ],
        "filename": code["filename"],
        "source": code["source"],
        "param_defs": _param_defs_to_data(code.get("param_defs")),
        "type_params": list(code.get("type_params") or []),
    }
    if code.get("is_generator"):
        # A function that gives its values one at a time.
        data["is_generator"] = True
    return data


def _param_defs_to_data(defs):
    result = []
    for spec in defs or []:
        default = spec.get("default")
        result.append({
            "name": spec["name"],
            "param_kind": spec["param_kind"],
            "type_name": spec["type_name"],
            "default": (None if default is None else code_to_data(default)),
        })
    return result


def _arg_to_data(arg):
    if isinstance(arg, (list, tuple)):
        return [_arg_to_data(item) for item in arg]
    if isinstance(arg, dict):
        return code_to_data(arg)
    return arg


def _make_run_code(path):
    base_dir = os.path.dirname(os.path.abspath(path))

    def run_code(args):
        if len(args) != 1:
            raise BunRuntimeError("run_code() expects 1 argument")
        vm = VM()
        vm.run(normalize(args[0]), base_dir=base_dir)
        return None

    return Builtin("run_code", run_code)

def _type_error(args):
    if len(args) != 3:
        raise BunRuntimeError("type_error() expects 3 arguments")
    message, line, col = args
    raise BunTypeError(message, line, col)


def _type_of(args):
    if len(args) != 1:
        raise BunRuntimeError("type_of() expects 1 argument")
    value = args[0]
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, BunFunction):
        return "fn"
    return "any"


def _module_path(args):
    if len(args) != 2:
        raise BunRuntimeError("module_path() expects 2 arguments")
    return modules.resolve_module_path(args[0], args[1])


def _read_module(args):
    if len(args) != 2:
        raise BunRuntimeError("read_module() expects 2 arguments")
    path, full_path = args
    try:
        with open(full_path, "r") as handle:
            return handle.read()
    except OSError as error:
        raise BunRuntimeError(
            "cannot read module '%s': %s" % (path, error.strerror))
    except UnicodeDecodeError:
        raise BunRuntimeError(
            "cannot read module '%s': not valid UTF-8" % path)


def run_front_end(path, mode="run", check=True):
    with open(path, "r") as handle:
        source = handle.read()
    base_dir = os.path.dirname(os.path.abspath(path))
    if check or mode in ("run", "check"):
        Parser(Lexer(source).tokenize()).parse()
    vm = VM()
    vm.globals.define(
        "args",
        Builtin("args", lambda args: [path, mode, "1" if check else "0",
                                      base_dir]),
        False)
    vm.globals.define("run_code", _make_run_code(path), False)
    vm.globals.define("type_error", Builtin("type_error", _type_error), False)
    vm.globals.define("type_of", Builtin("type_of", _type_of), False)
    vm.globals.define("module_path", Builtin("module_path", _module_path), False)
    vm.globals.define("read_module", Builtin("read_module", _read_module), False)
    vm.run(driver_code(), base_dir=SELFHOST_DIR)
