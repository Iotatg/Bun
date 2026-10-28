"""The C backend of Bun.

The backend reads the register code of the language and writes a C
program that uses the runtime of `lib/bun/c_runtime.h`.  The system
compiler turns that program into a binary.

The register code is the input because it is already flat and already
verified: the values of an expression live in the registers of a frame,
the jumps land on instructions of the same function, and the depth of
the expression is the same on every path.  The emitter translates one
instruction into one piece of C, and the golden corpus of the test
suite is the oracle: a program that prints something different under
the backend is a bug in the backend.

The backend never changes the language.  A construct it cannot translate
is refused at compile time, by name, instead of being mistranslated.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile

from .errors import BunError, HINTS
from . import cslots
from . import modules as bun_modules
from . import regcode
from .patterns import plan_names


class CBackendError(BunError):
    """A construct the backend cannot translate."""


# The number of the names of a frame above which the frame is an array
# and not a few variables.  A function with many names has many
# variables, and the compiler of the system keeps them in the memory
# anyway.
SCALAR_SLOTS = 16


# The instructions that can fail at run time.  The backend writes the
# position of the source before them, so a failure of the program carries
# the place of the source, like a failure of the machine carries it.
FAILING = frozenset([
    regcode.LOAD_NAME, regcode.STORE_NAME,
    regcode.LOAD_NAME2, regcode.LOAD_NAME_CONST, regcode.CONST_LOAD_NAME,
    regcode.ADD, regcode.SUB, regcode.MUL, regcode.DIV, regcode.MOD,
    regcode.LT, regcode.LE, regcode.GT, regcode.GE,
    regcode.BAND, regcode.BOR, regcode.BXOR, regcode.SHL, regcode.SHR,
    regcode.NEG, regcode.INVERT,
    regcode.BUILD_DICT, regcode.DICT_SET,
    regcode.INDEX, regcode.STORE_INDEX, regcode.SLICE, regcode.STORE_SLICE,
    regcode.UNPACK_PLAN, regcode.FORMAT,
    regcode.MAKE_STRUCT, regcode.GET_FIELD, regcode.SET_FIELD,
    regcode.UNWRAP_OR_RETURN,
    regcode.CALL, regcode.METHOD_CALL,
    regcode.FOR_SETUP,
    regcode.THROW, regcode.ASSERT,
    regcode.DEL, regcode.DEL_INDEX,
    regcode.IMPORT,
])

# The instructions that jump to another instruction.
JUMPS = frozenset([
    regcode.JUMP, regcode.JUMP_IF_FALSE, regcode.JUMP_IF_TRUE,
    regcode.FOR_NEXT, regcode.TRY, regcode.TRY_FINALLY,
])


# The builtins the backend has.  A program that uses another builtin is
# refused at compile time, by name, instead of failing at run time with
# a confusing message.
SUPPORTED_BUILTINS = frozenset([
    "print", "len", "range", "str", "int", "chr", "ord", "float",
    "type_of", "abs", "min", "max", "bool", "sum", "any", "all",
    "zip", "enumerate", "sorted", "reversed",
    "read_file", "write_file", "append_file", "file_exists", "getenv",
    "set", "secret", "dump",
    "Ok", "Err", "is_ok", "is_err",
    "some", "none", "is_some", "is_none",
    "spawn", "task_join", "task_done", "cancel", "task_cancelled",
    "sleep",
])

# The builtins of the language.  The list is checked against the runtime
# by the test suite, so the two do not drift apart.
LANGUAGE_BUILTINS = frozenset([
    "args", "print", "len", "range", "str", "input", "int", "chr", "ord",
    "float", "type_of", "bool", "abs", "sum", "any", "all", "min", "max",
    "zip", "enumerate", "sorted", "reversed", "set", "next", "send",
    "dump", "secret", "url_encode", "url_decode",
    "some", "none", "is_some", "is_none",
    "read_file", "write_file", "append_file", "file_exists", "getenv",
    "getenv_or", "json_parse", "json_stringify", "http_get", "http_post",
    "http_get_bytes", "http_post_multipart", "write_bytes", "read_bytes",
    "bytes_slice", "bytes_append",
    "exec", "eval", "now",
    "sleep", "spawn", "task_join", "task_done", "cancel", "task_cancelled",
    "sandbox_enter", "sandbox_exit", "mutex", "lock", "unlock", "ffi_load",
    "list_dir", "make_dir", "exit", "sha256", "sha1", "md5", "base64_encode",
    "pbkdf2_sha512",
    "base64_decode", "random_bytes", "random", "random_int",
    "aes_ige_encrypt", "aes_ige_decrypt", "aes_ctr_crypt", "rsa_encrypt",
    "double_from_bits", "double_to_bits",
    "pow_mod", "gzip_decompress", "tcp_set_timeout", "bigint_factorize",
    "bigint_mul_mod_bytes",
    "tcp_connect", "tcp_tls_connect", "tcp_listen", "tcp_accept",
    "tcp_close", "tcp_write", "tcp_read", "h2_connect", "h2_request",
    "h2_close", "bigint_from_bytes", "bigint_to_bytes", "bigint_from_int",
    "bigint_to_int", "bigint_mul", "bigint_add", "bigint_sub",
    "bigint_mod", "bigint_div", "bigint_gcd", "bigint_mul_mod",
    "bigint_cmp", "bigint_pow_mod", "utf8_bytes", "utf8_string",
    "starts_with", "ends_with", "substring", "index_of", "split", "join",
    "replace", "trim", "lower", "upper",
    "Ok", "Err", "is_ok", "is_err",
])


def _children(node):
    """The nodes inside a node of the tree."""
    if isinstance(node, (list, tuple)):
        return list(node)
    if hasattr(node, "__dict__"):
        return [value for value in vars(node).values()]
    return []


def _collect_names(node, reads, defines):
    """The names a program reads and the names it defines.

    The names a program reads carry the place of the source where the
    program reads them, so a refusal of the backend points at the line
    of the program.
    """
    from . import ast

    if isinstance(node, ast.Identifier):
        reads.setdefault(node.name, (getattr(node, "line", 0),
                                     getattr(node, "col", 0)))
        return
    if isinstance(node, ast.LetStmt):
        defines.add(node.name)
        _collect_names(node.value, reads, defines)
        return
    if isinstance(node, ast.AssignStmt):
        target = node.target
        if isinstance(target, ast.Identifier):
            defines.add(target.name)
        else:
            _collect_names(target, reads, defines)
        _collect_names(node.value, reads, defines)
        return
    if isinstance(node, ast.UnpackStmt):
        for target in node.targets:
            if isinstance(target, ast.Identifier):
                defines.add(target.name)
            else:
                _collect_names(target, reads, defines)
        _collect_names(node.value, reads, defines)
        return
    if isinstance(node, ast.UnpackTarget):
        if node.name:
            defines.add(node.name)
        for target in node.targets:
            _collect_names(target, reads, defines)
        return
    if isinstance(node, ast.FnDecl):
        defines.add(node.name)
        for param in node.params:
            defines.add(param.name)
        _collect_names(node.body, reads, defines)
        return
    if isinstance(node, ast.Param):
        defines.add(node.name)
        _collect_names(node.default, reads, defines)
        return
    if isinstance(node, ast.ImportStmt):
        for name in node.names:
            defines.add(name)
        return
    for child in _children(node):
        _collect_names(child, reads, defines)


def check_builtins(program):
    """Refuse a program that uses a builtin the backend does not have."""
    from . import ast

    reads = {}
    defines = set()
    for statement in program.statements:
        _collect_names(statement, reads, defines)
    for name in sorted(set(reads) & LANGUAGE_BUILTINS):
        if name in defines:
            continue
        if name in SUPPORTED_BUILTINS:
            continue
        line, col = reads[name]
        raise CBackendError(
            "the C backend does not support the builtin '%s'" % name,
            line, col)


# The opcodes the backend does not translate.  The value is the message
# of the refusal.
REFUSED = {
    regcode.YIELD: "the yield statement",
}

# The kinds of a plan of a pattern, as the runtime knows them.
PLAN_LITERAL = 1
PLAN_WILDCARD = 2
PLAN_BINDING = 3
PLAN_TYPE = 4
PLAN_RANGE = 5
PLAN_LIST = 6
PLAN_DICT = 7
PLAN_OR = 8
PLAN_STRUCT = 9

PLAN_KINDS = ("literal", "wildcard", "binding", "type", "range", "list",
              "dict", "or", "struct")


def _escape(text):
    """The text of a C string literal."""
    out = []
    for char in text:
        if char == "\\":
            out.append("\\\\")
        elif char == '"':
            out.append('\\"')
        elif char == "\n":
            out.append("\\n")
        elif char == "\t":
            out.append("\\t")
        elif char == "\r":
            out.append("\\r")
        elif char == "?":
            out.append("\\?")
        elif ord(char) < 32 or ord(char) == 127:
            out.append("\\%03o" % ord(char))
        else:
            out.append(char)
    return "".join(out)


def _c_string(text):
    return '"%s"' % _escape(text)


class CEmitter:
    """The emitter of the C backend."""

    def __init__(self, code, filename="<program>", source=None):
        self.code = code
        self.filename = filename
        self.source = source
        self.source_lines = source.splitlines() if source else []
        self.functions = []          # the code objects, in the order they are emitted
        self._index = {}
        self.out = []
        self.params = []            # the parameter tables of the functions
        self.frames = cslots.analyze(code)
        # The modules of the program: the program itself, then the modules
        # it imports, in the order they are first met.
        self.modules = [{
            "path": filename,
            "full": os.path.abspath(filename),
            "code": code,
            "source": source,
        }]
        self._module_index = {os.path.abspath(filename): 0}
        self._module_of = {}        # the module of every code object
        self._module_of[id(code)] = 0
        self.static_globals = {}    # (module, name) -> the static variable
        self.defined_names = set()  # the names the program defines
        self.builtin_globals = set()  # the names that always hold a builtin
        self.static_builtins = {}  # the name of a builtin -> the static
        self._match_names = {}  # the id of a code -> the names of its patterns
        self.static_definitions = {}  # (module, name) -> (code, place, register, body)
        self.static_environments = {}  # (module, name) -> the static environment
        # The code objects whose frame of names is a few variables and not
        # an array.  The emitter fills the table when it writes the frame.
        self.scalar_slots = {}
        # The code objects of the methods of the structs.  The first
        # argument of a method is the receiver, and it is borrowed.
        self.methods = set()

    # -- the code objects ---------------------------------------------------

    def collect(self, code, module_index=0):
        """Collect the code objects of the program, the module first."""
        if id(code) in self._index:
            return self._index[id(code)]
        index = len(self.functions)
        self._index[id(code)] = index
        self.functions.append(code)
        self._module_of[index] = module_index
        consts = code.get("consts", [])
        for value in consts:
            if isinstance(value, dict) and "code" in value:
                self.collect(value, module_index)
        for instruction in code.get("code", []):
            op, a, b, c = instruction
            if op == regcode.REGISTER_IMPL:
                body = consts[c]
                if isinstance(body, dict) and "code" in body:
                    self.methods.add(id(body))
        for spec in code.get("param_defs", []):
            default = spec.get("default")
            if isinstance(default, dict) and "code" in default:
                self.collect(default, module_index)
        return index

    def function_name(self, code):
        return "bun_fn_%d" % self._index[id(code)]

    # -- the globals --------------------------------------------------------

    def analyse_globals(self):
        """Find the names of the program that hold a function and never change.

        The lookup of a name in the environment is the most expensive part
        of a call, and a name that the program defines once and never
        changes can be read from a static variable instead.  The variable
        holds nothing until the definition runs, and a read of a name that
        was not defined yet falls back to the environment.
        """
        changed = set()
        for code in self.functions:
            consts = code.get("consts", [])
            for instruction in code["code"]:
                op, a, b, c = instruction
                if op == regcode.STORE_NAME:
                    changed.add(consts[b])
                elif op == regcode.DEL:
                    changed.add(consts[a])
        self.parents = {}
        for frame in self.frames.values():
            for child in frame.children:
                self.parents[id(child)] = frame
        self.module_codes = set(id(module["code"]) for module in self.modules)
        self.defined_names = set()
        for number, module in enumerate(self.modules):
            self.analyse_module(number, module["code"], changed)
        self.builtin_globals = self.find_builtin_globals(changed)
        self.find_static_builtins()

    def find_builtin_globals(self, changed):
        """The names that always hold the builtin of the language.

        A name that the program never defines and never changes always
        holds the builtin of the language, so a call of that name does
        not have to look the builtin up in the environment.
        """
        names = set()
        for name in SUPPORTED_BUILTINS:
            if name in self.defined_names:
                continue
            if name in changed:
                continue
            names.add(name)
        return names

    def analyse_module(self, number, code, changed):
        """Find the names of a module that hold a function and never change."""
        consts = code.get("consts", [])
        instructions = code["code"]
        definitions = {}
        for position, instruction in enumerate(instructions):
            op, a, b, c = instruction
            if op != regcode.DEFINE_NAME:
                continue
            name = consts[b]
            self.defined_names.add(name)
            if name in definitions:
                # The name is defined twice, so a read of it does not always
                # find the same value.
                definitions[name] = None
                continue
            if name in changed:
                definitions[name] = None
                continue
            if position == 0:
                continue
            previous = instructions[position - 1]
            if previous[0] != regcode.MAKE_FUNCTION or previous[1] != a:
                # The value is not a function: a decorated function and a
                # function that is built by an expression are not cached.
                continue
            site = self.frames[id(code)].sites_by_position.get(position)
            if site is None or not site.dynamic:
                # The name lives in the frame of the module, and a read of
                # it does not look it up in the environment.
                continue
            body = consts[previous[2]]
            definitions[name] = (code, position, a, body)
        for name, place in definitions.items():
            if place is None:
                continue
            key = (number, name)
            self.static_globals[key] = "bun_static_%d" % len(self.static_globals)
            self.static_definitions[key] = place
            self.static_environments[key] = "bun_static_env_%d" % len(
                self.static_environments)

    def match_names(self, code):
        """The names that the patterns of a code object bind.

        A pattern binds a name in the environment of the code object, so
        a name that a pattern binds is not the builtin of the language
        when the arm of the pattern reads it.
        """
        key = id(code)
        if key in self._match_names:
            return self._match_names[key]
        names = set()
        consts = code.get("consts", [])
        for instruction in code["code"]:
            if instruction[0] != regcode.MATCH_TEST:
                continue
            names |= set(plan_names(consts[instruction[2]]))
        self._match_names[key] = names
        return names

    def find_static_builtins(self):
        """Find the builtins that the program reads.

        A builtin of the language lives in the table of the globals, and
        the lookup of a name in that table is the most expensive part of a
        read.  A builtin that the program reads is kept in a static
        variable, and the program reads the variable.
        """
        read = set()
        for code in self.functions:
            consts = code.get("consts", [])
            for instruction in code["code"]:
                if instruction[0] == regcode.LOAD_NAME:
                    read.add(consts[instruction[2]])
        for name in sorted(read):
            if name not in self.builtin_globals:
                continue
            self.static_builtins[name] = "bun_builtin_static_%d" % len(
                self.static_builtins)

    def static_name_at(self, code, position, name):
        """The static variable of a name, when the name can be read from it."""
        number = self._module_of[self._index[id(code)]]
        key = (number, name)
        if key not in self.static_globals:
            return None
        site = self.frames[id(code)].site_at(position)
        if not site.dynamic:
            return None
        if not self.reads_the_definition(code, position, name):
            return None
        if name in self.match_names(code):
            return None
        if self.shadowed(code, name):
            return None
        return self.static_globals[key]

    def reads_the_definition(self, code, position, name):
        """Whether a place of the program reads the definition of a name.

        The static variable of a name holds the function that the module
        defines, so a place of the program may read the variable only
        when the place reads the name of the module and not another
        binding of the same name.
        """
        number = self._module_of[self._index[id(code)]]
        place = self.static_definitions.get((number, name))
        if place is None:
            return False
        definition = self.frames[id(place[0])].sites_by_position.get(place[1])
        if definition is None:
            return False
        site = self.frames[id(code)].site_at(position)
        if site.binding is None:
            # The name comes from the environment of the module.
            return True
        return site.binding is definition.binding

    def track_registers(self, code, instruction, position):
        """Remember the registers that hold a name of the module.

        The register of a call that the program makes to a name of the
        module is the register that the read of the name filled, and the
        read of the name is the only way a register holds that name.

        The registers that hold a builtin of the language are remembered
        as well, so a call of a builtin does not have to look the builtin
        up in the environment.
        """
        op, a, b, c = instruction
        if op == regcode.LOAD_NAME:
            name = code["consts"][b]
            if self.static_name_at(code, position, name) is not None:
                self._cached[a] = name
            else:
                self._cached.pop(a, None)
            if self.builtin_name_at(code, position, name) is not None:
                self._builtins[a] = name
            else:
                self._builtins.pop(a, None)
            return
        for slot in self.touched_slots(code, instruction):
            self._cached.pop(slot, None)
            self._builtins.pop(slot, None)
        if op in (regcode.LOAD_NAME2, regcode.LOAD_NAME_CONST,
                  regcode.CONST_LOAD_NAME):
            self._cached.pop(a + 1, None)
            self._builtins.pop(a + 1, None)

    def direct_call(self, code, position, register):
        """The function of a call that the program makes to a known name.

        The call is translated into a call of the C function of the name,
        so the compiler of the system sees which function is called.
        """
        name = self._cached.get(register)
        if name is None:
            return None
        number = self._module_of[self._index[id(code)]]
        key = (number, name)
        place = self.static_definitions.get(key)
        if place is None:
            return None
        body = place[3]
        return (self.function_name(body), self.static_environments[key],
                self.frames[id(body)].needs_env)

    def builtin_name_at(self, code, position, name):
        """The builtin of a name, when the name always holds it.

        The name is the builtin of the language when the program never
        defines it, when the program never changes it and when no
        function of the program binds it.
        """
        if name not in self.builtin_globals:
            return None
        site = self.frames[id(code)].site_at(position)
        if not site.dynamic:
            return None
        if site.binding is not None:
            # The function binds the name itself, so the name is the name
            # of the function and not the builtin of the language.
            return None
        if name in self.match_names(code):
            return None
        if self.shadowed(code, name):
            return None
        return name

    def static_builtin_at(self, code, position, name):
        """The static variable of a builtin, when the builtin can be read.

        The builtin is read from the static variable, and the static holds
        the builtin from the moment the program starts.
        """
        if self.builtin_name_at(code, position, name) is None:
            return None
        return self.static_builtins.get(name)

    def builtin_call(self, code, position, register):
        """The builtin of a call that the program makes to a known name.

        The call is translated into a call of the C function of the
        builtin, so the compiler of the system sees which builtin is
        called.
        """
        name = self._builtins.get(register)
        if name is None:
            return None
        return name

    def shadowed(self, code, name):
        """Whether a name of the program is bound by an enclosing function."""
        frame = self.frames[id(code)]
        while True:
            if name in self.match_names(frame.code):
                return True
            parent = self.parents.get(id(frame))
            if parent is None:
                return False
            if name in self.match_names(parent.code):
                return True
            if id(parent.code) in self.module_codes:
                # The module holds the name itself, and the name of the
                # module is not a shadow of it.
                return False
            if name in parent.bound:
                return True
            frame = parent

    # -- the modules --------------------------------------------------------

    def collect_modules(self):
        """Find the modules the program imports and compile them."""
        position = 0
        while position < len(self.functions):
            code = self.functions[position]
            position += 1
            for instruction in code["code"]:
                if instruction[0] != regcode.IMPORT:
                    continue
                path = code["consts"][instruction[1]][0]
                self.module_for(path, code)

    def module_for(self, path, code):
        """The module an import names, compiled and ready to be linked."""
        index = self._module_of[self._index[id(code)]]
        base = os.path.dirname(self.modules[index]["full"])
        try:
            full = bun_modules.resolve_module_path(path, base)
        except BunError as error:
            raise CBackendError(error.msg, error.line, error.col)
        if full in self._module_index:
            return self._module_index[full]
        source = bun_modules.read_source(full)
        try:
            program = bun_modules.load_module_source(path, full)
        except BunError as error:
            raise CBackendError(error.msg, error.line, error.col)
        from .compiler import Compiler
        from .regcompile import registerize
        from .regverify import verify_program
        # The body of a module is not checked by the checker of the
        # language, so the backend does not check it either: the two
        # engines accept the same modules.
        check_builtins(program)
        module_code = registerize(Compiler(full, source).compile_program(program))
        verify_program(module_code)
        number = len(self.modules)
        self.modules.append({"path": path, "full": full, "code": module_code,
                              "source": source})
        self._module_index[full] = number
        self.frames.update(cslots.analyze(module_code))
        self.collect(module_code, number)
        return number

    def module_number(self, path, code):
        """The number of the module an import names."""
        index = self._module_of[self._index[id(code)]]
        base = os.path.dirname(self.modules[index]["full"])
        try:
            full = bun_modules.resolve_module_path(path, base)
        except BunError as error:
            raise CBackendError(error.msg)
        if full not in self._module_index:
            raise CBackendError("the C backend lost the module '%s'" % path)
        return self._module_index[full]

    def emit_module_runner(self, number, module):
        """The function that runs a module once and keeps its exports."""
        name = "bun_module_%d" % number
        body = self.function_name(module["code"])
        lines = []
        lines.append("static BunModule *%s(void) {" % name)
        lines.append("    static BunModule *cache = NULL;")
        lines.append("    static int loading = 0;")
        lines.append("    if (cache) return cache;")
        lines.append("    if (loading) {")
        lines.append("        bun_throw(\"circular import of '%%s'\", %s);"
                     % _c_string(module["path"]))
        lines.append("    }")
        lines.append("    loading = 1;")
        lines.append("    cache = bun_module_new();")
        lines.append("    bun_current_module = cache;")
        lines.append("    %s(bun_env_new(bun_globals_env), NULL, 0, "
                     "bun_null_value());" % body)
        lines.append("    bun_current_module = NULL;")
        lines.append("    loading = 0;")
        lines.append("    return cache;")
        lines.append("}")
        return lines

    # -- the program --------------------------------------------------------

    def emit(self):
        self.collect(self.code, 0)
        self.collect_modules()
        self.prepare_params()
        self.collect_plans()
        self.analyse_globals()
        lines = []
        lines.append("/* The program, generated by the C backend of Bun. */")
        lines.append('#include "c_runtime.h"')
        lines.append("")
        lines.extend(self.emit_picture())
        lines.append("")
        lines.extend(self.emit_plan_declarations())
        lines.append("")
        lines.extend(self.emit_plan_arrays())
        lines.append("")
        for index in range(len(self.functions)):
            lines.append("static BunValue bun_fn_%d(BunEnv *env, BunValue *args, "
                         "int argc, BunValue kwargs);" % index)
        lines.append("")
        for name in sorted(self.static_globals.values()):
            lines.append("static BunValue %s;" % name)
        lines.append("")
        for name in sorted(self.static_environments.values()):
            lines.append("static BunEnv *%s;" % name)
        lines.append("")
        for name in sorted(self.static_builtins.values()):
            lines.append("static BunValue %s;" % name)
        lines.append("")
        for number in range(1, len(self.modules)):
            lines.append("static BunModule *bun_module_%d(void);" % number)
        lines.append("")
        lines.extend(self.emit_constants())
        lines.append("")
        lines.extend(self.emit_param_tables())
        lines.append("")
        for index, code in enumerate(self.functions):
            lines.extend(self.emit_function(index, code))
            lines.append("")
        for number in range(1, len(self.modules)):
            lines.extend(self.emit_module_runner(number, self.modules[number]))
            lines.append("")
        lines.extend(self.emit_plan_setup())
        lines.extend(self.emit_constant_setup())
        lines.append("static BunValue bun_module_code(BunEnv *globals) {")
        lines.append("    bun_init_plans();")
        lines.append("    bun_init_constants();")
        for name, variable in sorted(self.static_builtins.items()):
            # The builtin of the language lives in the table of the
            # globals, and the lookup of a name in that table is the most
            # expensive part of a read.  The static variable holds the
            # builtin, and a read of the name reads the variable.
            lines.append("    %s = bun_env_get(globals, %s);"
                         % (variable, _c_string(name)))
        lines.append("    return %s(globals, NULL, 0, bun_null_value());"
                     % self.function_name(self.code))
        lines.append("}")
        lines.append("")
        return "\n".join(lines)

    def emit_picture(self):
        """The lines of the program and the table of the hints.

        The table of the hints is the table of the machine, so a failure of
        the backend gives the same advice as a failure of the machine.
        """
        lines = []
        lines.append("/* The picture of a failure. */")
        lines.append("const char *const bun_source_file = %s;"
                     % _c_string(self.filename))
        lines.append("const char *const *bun_source_lines[] = {")
        for line in self.source_lines:
            lines.append("    %s," % _c_string(line))
        lines.append("    NULL")
        lines.append("};")
        lines.append("const int bun_source_line_count = %d;"
                     % len(self.source_lines))
        lines.append("const BunHint bun_hints[] = {")
        for pattern, hint in HINTS:
            lines.append("    {%s, %s}," % (_c_string(pattern), _c_string(hint)))
        lines.append("    {NULL, NULL}")
        lines.append("};")
        return lines

    # -- the plans of the patterns -------------------------------------------

    def is_plan(self, value):
        """Whether a constant of the pool is the plan of a pattern."""
        if not isinstance(value, (list, tuple)) or not value:
            return False
        kind = value[0]
        return isinstance(kind, str) and kind in PLAN_KINDS

    def collect_plans(self):
        """Find the plans of the patterns and give them a name."""
        self._plan_names = {}
        self._plan_objects = {}
        self._plan_arrays = {}
        self._plan_order = []
        self._plan_sequence = []
        self._plan_counter = {}
        for index, code in enumerate(self.functions):
            for position, value in enumerate(code.get("consts", [])):
                if not self.is_plan(value):
                    continue
                key = (index, id(value))
                self._plan_names[key] = "bun_plan_%d_%d" % (index, position)
                self._plan_objects[key] = value
                self._plan_sequence.append(key)
                self._plan_order.append((index, value))
                self._walk_plan(index, value)

    def _walk_plan(self, index, plan):
        """Give a name to the plans inside a plan."""
        kind = plan[0]
        children = []
        if kind == "list":
            children = list(plan[1])
            if plan[2] is not None:
                children.append(plan[2])
        elif kind == "dict":
            children = [sub for _, sub in plan[1]]
        elif kind == "struct":
            children = [sub for _, sub in plan[2]]
        elif kind == "or":
            children = list(plan[1])
        for child in children:
            key = (index, id(child))
            if key not in self._plan_names:
                self._plan_counter[index] = self._plan_counter.get(index, 0) + 1
                self._plan_names[key] = "bun_plan_%d_n%d" % (
                    index, self._plan_counter[index])
                self._plan_objects[key] = child
                self._plan_sequence.append(key)
            self._walk_plan(index, child)

    def emit_plan_declarations(self):
        """The declaration of every plan of the program."""
        lines = []
        for key in self._plan_sequence:
            lines.append("static BunPlan %s;" % self._plan_names[key])
        return lines

    def emit_plan_arrays(self):
        """The arrays of the items and of the keys of the plans."""
        lines = []
        seen = set()
        for index, plan in self._plan_order:
            self._plan_array(index, plan, lines, seen)
        return lines

    def _plan_array(self, index, plan, lines, seen):
        """The array of the items of a plan, and the arrays below it."""
        kind = plan[0]
        key = (index, id(plan))
        if key in seen:
            return
        seen.add(key)
        name = self._plan_names[key]
        if kind == "list":
            for item in plan[1]:
                self._plan_array(index, item, lines, seen)
            if plan[2] is not None:
                self._plan_array(index, plan[2], lines, seen)
            array = "%s_items" % name
            self._plan_arrays[key] = array
            lines.append("static const BunPlan *const %s[] = {" % array)
            for item in plan[1]:
                lines.append("    &%s," % self._plan_names[(index, id(item))])
            lines.append("};")
        elif kind == "dict":
            for _, sub in plan[1]:
                self._plan_array(index, sub, lines, seen)
            array = "%s_items" % name
            keys = "%s_keys" % name
            self._plan_arrays[key] = array
            lines.append("static const BunPlan *const %s[] = {" % array)
            for _, sub in plan[1]:
                lines.append("    &%s," % self._plan_names[(index, id(sub))])
            lines.append("};")
            lines.append("static const char *const %s[] = {" % keys)
            for name_of_key, _ in plan[1]:
                lines.append("    %s," % _c_string(name_of_key))
            lines.append("};")
            self._plan_arrays[(index, id(plan), "keys")] = keys
        elif kind == "struct":
            # The plan of a struct holds the pattern of every field it
            # names, the way a dict holds the pattern of its entries:
            # one array of the plans and one array of the field names.
            for _, sub in plan[2]:
                self._plan_array(index, sub, lines, seen)
            array = "%s_items" % name
            keys = "%s_fields" % name
            self._plan_arrays[key] = array
            lines.append("static const BunPlan *const %s[] = {" % array)
            for _, sub in plan[2]:
                lines.append("    &%s," % self._plan_names[(index, id(sub))])
            lines.append("};")
            lines.append("static const char *const %s[] = {" % keys)
            for field, _ in plan[2]:
                lines.append("    %s," % _c_string(field))
            lines.append("};")
            self._plan_arrays[(index, id(plan), "keys")] = keys
        elif kind == "or":
            for item in plan[1]:
                self._plan_array(index, item, lines, seen)
            array = "%s_items" % name
            self._plan_arrays[key] = array
            lines.append("static const BunPlan *const %s[] = {" % array)
            for item in plan[1]:
                lines.append("    &%s," % self._plan_names[(index, id(item))])
            lines.append("};")

    def emit_plan_setup(self):
        """The function that fills the plans of the patterns."""
        lines = []
        lines.append("/* The plans of the patterns. */")
        lines.append("static void bun_init_plans(void) {")
        for key in self._plan_sequence:
            lines.extend(self._plan_setup(key[0], self._plan_objects[key]))
        lines.append("}")
        lines.append("")
        return lines

    def _plan_setup(self, index, plan):
        """The statements that fill one plan."""
        kind = plan[0]
        name = self._plan_names[(index, id(plan))]
        lines = []
        if kind == "literal":
            lines.append("    %s.kind = %d;" % (name, PLAN_LITERAL))
            lines.append("    %s.literal = %s;" % (name, self.value_expr(plan[1])))
        elif kind == "wildcard":
            lines.append("    %s.kind = %d;" % (name, PLAN_WILDCARD))
        elif kind == "binding":
            lines.append("    %s.kind = %d;" % (name, PLAN_BINDING))
            lines.append("    %s.name = %s;" % (name, _c_string(plan[1])))
        elif kind == "type":
            lines.append("    %s.kind = %d;" % (name, PLAN_TYPE))
            lines.append("    %s.literal = %s;" % (name, self.value_expr(plan[1])))
        elif kind == "range":
            lines.append("    %s.kind = %d;" % (name, PLAN_RANGE))
            lines.append("    %s.low = %s;" % (name, self.value_expr(plan[1])))
            lines.append("    %s.high = %s;" % (name, self.value_expr(plan[2])))
        elif kind == "list":
            lines.append("    %s.kind = %d;" % (name, PLAN_LIST))
            lines.append("    %s.count = %d;" % (name, len(plan[1])))
            lines.append("    %s.items = %s;" % (name, self._plan_arrays[
                (index, id(plan))]))
            if plan[2] is not None:
                lines.append("    %s.tail = &%s;" % (
                    name, self._plan_names[(index, id(plan[2]))]))
        elif kind == "dict":
            lines.append("    %s.kind = %d;" % (name, PLAN_DICT))
            lines.append("    %s.count = %d;" % (name, len(plan[1])))
            lines.append("    %s.keys = %s;" % (name, self._plan_arrays[
                (index, id(plan), "keys")]))
            lines.append("    %s.values = %s;" % (name, self._plan_arrays[
                (index, id(plan))]))
        elif kind == "or":
            lines.append("    %s.kind = %d;" % (name, PLAN_OR))
            lines.append("    %s.count = %d;" % (name, len(plan[1])))
            lines.append("    %s.items = %s;" % (name, self._plan_arrays[
                (index, id(plan))]))
        elif kind == "struct":
            lines.append("    %s.kind = %d;" % (name, PLAN_STRUCT))
            lines.append("    %s.literal = %s;" % (
                name, self.value_expr(plan[1])))
            lines.append("    %s.count = %d;" % (name, len(plan[2])))
            lines.append("    %s.keys = %s;" % (name, self._plan_arrays[
                (index, id(plan), "keys")]))
            lines.append("    %s.values = %s;" % (name, self._plan_arrays[
                (index, id(plan))]))
        return lines

    def value_expr(self, value):
        """The C expression of a value of the program."""
        if value is None:
            return "bun_null_value()"
        if isinstance(value, bool):
            return "bun_bool_value(%d)" % (1 if value else 0)
        if isinstance(value, int):
            return "bun_int_value(%d)" % value
        if isinstance(value, float):
            return "bun_float_value(%.17g)" % value
        if isinstance(value, str):
            return "bun_str_from_c(%s)" % _c_string(value)
        raise CBackendError(
            "the C backend cannot translate the value %r" % (value,))

    # -- the constants ------------------------------------------------------

    def emit_constants(self):
        """The constants of the pool of every code object."""
        lines = []
        for index, code in enumerate(self.functions):
            for position, value in enumerate(code.get("consts", [])):
                name = "bun_const_%d_%d" % (index, position)
                if value is None:
                    lines.append("static const BunValue %s = { BUN_NULL, { 0 } };"
                                 % name)
                elif isinstance(value, bool):
                    lines.append(
                        "static const BunValue %s = { BUN_BOOL, { .b = %d } };"
                        % (name, 1 if value else 0))
                elif isinstance(value, int):
                    lines.append(
                        "static const BunValue %s = { BUN_INT, { .i = %d } };"
                        % (name, value))
                elif isinstance(value, float):
                    lines.append(
                        "static const BunValue %s = { BUN_FLOAT, { .f = %.17g } };"
                        % (name, value))
                elif isinstance(value, str):
                    # A string of the pool is a string of the program, and
                    # the program has one string and not one string for
                    # every use of it.  The value is built once, when the
                    # program starts, and every use reads it.
                    lines.append("static BunValue %s;" % name)
                    lines.append("static const char *const %s_text = %s;"
                                 % (name, _c_string(value)))
                elif isinstance(value, (list, tuple, dict)):
                    continue
                else:
                    raise CBackendError(
                        "the backend cannot translate the constant %r"
                        % (value,))
        return lines

    def emit_constant_setup(self):
        """The function that builds the strings of the pool."""
        lines = []
        lines.append("/* The strings of the pool of the program. */")
        lines.append("static void bun_init_constants(void) {")
        for index, code in enumerate(self.functions):
            for position, value in enumerate(code.get("consts", [])):
                if isinstance(value, str):
                    name = "bun_const_%d_%d" % (index, position)
                    lines.append("    %s = bun_str_from_c(%s_text);"
                                 % (name, name))
        lines.append("}")
        lines.append("")
        return lines

    def const_expr(self, code, index, position):
        """The C expression of a constant of the pool.

        A string of the pool is a variable of the program, and the
        program builds it once, when it starts.
        """
        return "bun_const_%d_%d" % (self._index[id(code)], position)

    # -- the functions ------------------------------------------------------

    def emit_function(self, index, code):
        name = self.function_name(code)
        instructions = code["code"]
        depths = code.get("depths", [])
        consts = code.get("consts", [])
        info = self.frames[id(code)]
        highest = 0
        for instruction in instructions:
            for slot in self.touched_slots(code, instruction):
                if slot > highest:
                    highest = slot
        slots = max(highest + 1, 1)
        frame_slots = max(info.slot_count, 1)
        scope_count = max(info.max_depth + 1, 1)
        has_handler = any(instruction[0] in (regcode.TRY, regcode.TRY_FINALLY)
                          for instruction in instructions)
        # Every loop of the function holds an iterator, and the iterators
        # of the loops that nest are live at the same time.  The number
        # of the loops is an upper bound of that number, and it is much
        # smaller than the number of the instructions.
        loops = sum(1 for instruction in instructions
                    if instruction[0] == regcode.FOR_SETUP)
        # The targets of the `with` statements of the function wait on a
        # stack of their own, and the number of the statements is an
        # upper bound of the depth of that stack.
        withs = sum(1 for instruction in instructions
                    if instruction[0] == regcode.WITH_ENTER)
        handler_numbers = {}
        number = 0
        for position, instruction in enumerate(instructions):
            if instruction[0] in (regcode.TRY, regcode.TRY_FINALLY):
                handler_numbers[position] = number
                number += 1
        lines = []
        lines.append("static BunValue %s(BunEnv *env, BunValue *args, "
                     "int argc, BunValue kwargs) {" % name)
        if has_handler:
            # The frame of the names and the registers of a function that
            # catches an error live on the heap: the error jumps into the
            # frame, and the values of an automatic object would be lost.
            lines.append("    BunValue *slots = (BunValue *)bun_alloc("
                         "sizeof(BunValue) * %d);" % frame_slots)
            lines.append("    memset(slots, 0, sizeof(BunValue) * %d);"
                         % frame_slots)
            lines.append("    BunEnv **scopes = (BunEnv **)bun_alloc("
                         "sizeof(BunEnv *) * %d);" % scope_count)
            lines.append("    memset(scopes, 0, sizeof(BunEnv *) * %d);"
                         % scope_count)
        else:
            if frame_slots <= SCALAR_SLOTS:
                # The frame of the names of a function that catches no
                # error is a few variables, not an array: the compiler of
                # the system keeps them in the registers of the machine,
                # and a loop does not write them to the memory on every
                # step.
                self.scalar_slots[id(code)] = True
                lines.append("    BunValue %s;"
                             % ", ".join("slot_%d" % index
                                         for index in range(frame_slots)))
                for number in range(frame_slots):
                    lines.append("    slot_%d.tag = BUN_NULL; slot_%d.as.i = 0;"
                                 % (number, number))
            else:
                lines.append("    BunValue slots[%d];" % frame_slots)
                lines.append("    memset(slots, 0, sizeof(slots));")
            lines.append("    BunEnv *scopes[%d];" % scope_count)
        if has_handler:
            lines.append("    BunValue *regs = (BunValue *)bun_alloc("
                         "sizeof(BunValue) * %d);" % slots)
            lines.append("    memset(regs, 0, sizeof(BunValue) * %d);" % slots)
            lines.append("    BunIter *iters = (BunIter *)bun_alloc("
                         "sizeof(BunIter) * %d);" % max(loops, 1))
            # The counters live in the memory and not in the registers of
            # the machine: an error jumps into the frame of the function,
            # and a counter that the compiler of the system keeps in a
            # register would have a value that nobody knows.
            lines.append("    volatile int iter_count = 0;")
            lines.append("    BunPending *pending = "
                         "(BunPending *)bun_alloc(sizeof(BunPending));")
            lines.append("    pending->has = 0;")
            if withs:
                # The stack of the targets of the `with` statements lives
                # on the heap, because an error jumps into the frame of
                # the function, and the values of an automatic object
                # would be lost.
                lines.append("    BunValue *with_stack = (BunValue *)"
                             "bun_alloc(sizeof(BunValue) * %d);" % withs)
                lines.append("    volatile int with_depth = 0;")
            for position in sorted(handler_numbers):
                lines.append("    BunHandler *h_%d = NULL;"
                             % handler_numbers[position])
        else:
            # The registers of the expression are plain variables, and
            # they are not zeroed: the verifier proves that every
            # register that an instruction touches is below the depth of
            # the expression, and the depth of the expression holds the
            # values that the stack machine pushed before it.  A register
            # is written before it is read, so its first value is never a
            # leftover.
            lines.append("    BunValue %s;"
                         % ", ".join("r%d" % index for index in range(slots)))
            if loops:
                # The iterators of the loops of the function live in the
                # frame, and the frame of a function that has no loop
                # holds none.
                lines.append("    BunIter iters[%d];" % loops)
                lines.append("    int iter_count = 0;")
            if withs:
                lines.append("    BunValue with_stack[%d];" % withs)
                lines.append("    volatile int with_depth = 0;")
        table = self.param_tables[index][0]
        count = self.param_tables[index][1]
        if count:
            lines.extend(self.bind_parameters(code, table, count))
        lines.append("")
        marks = code.get("lines", [])
        targets = self.jump_targets(instructions)
        written = None
        body = []
        self._cached = {}
        self._builtins = {}
        for position, instruction in enumerate(instructions):
            if position in targets:
                # A jump may land here with another value in a register.
                self._cached.clear()
                self._builtins.clear()
            body.append("L%d:" % position)
            marker = self.position_marker(code, instruction, marks,
                                          position, targets, written)
            if marker is not None:
                body.append(marker)
                written = (marks[position] if position < len(marks)
                           else written)
            elif instruction[0] in (regcode.CALL, regcode.METHOD_CALL):
                # The call may change the position of the source, so the
                # next failure of this function writes it again.
                written = None
            body.extend(self.emit_instruction(code, instruction, position,
                                              depths,
                                              handler_numbers.get(position)))
            self.track_registers(code, instruction, position)
        if not has_handler:
            # The registers of a function that catches no error are plain
            # variables, so the compiler keeps them in the registers of
            # the machine.
            body = [self.register_variable(line) for line in body]
        lines.extend(body)
        lines.append("    return bun_null_value();")
        lines.append("}")
        return lines

    def register_variable(self, line):
        """The line of C with the registers written as plain variables."""
        return re.sub(r"\bregs\[(\d+)\]", lambda m: "r" + m.group(1), line)

    def jump_targets(self, instructions):
        """The instructions a jump of the function can land on."""
        targets = set()
        for instruction in instructions:
            op, a, b, c = instruction
            if op == regcode.JUMP or op == regcode.TRY \
                    or op == regcode.TRY_FINALLY:
                targets.add(a)
            elif op == regcode.JUMP_IF_FALSE or op == regcode.JUMP_IF_TRUE \
                    or op == regcode.FOR_NEXT:
                targets.add(b)
        return targets

    def position_marker(self, code, instruction, marks, position, targets,
                        written):
        """The line that writes the position of the source.

        The position is written before an instruction that can fail, and the
        position is written again when a jump lands on an instruction,
        because the jump may come from another place of the source.
        """
        op = instruction[0]
        if op not in FAILING and position not in targets:
            return None
        if op in (regcode.LOAD_NAME, regcode.STORE_NAME):
            site = self.frames[id(code)].sites_by_position.get(position)
            if site is not None and not site.dynamic:
                # A name that lives in a slot cannot fail when it is read,
                # and a name that can be written cannot fail when it is
                # written.
                if op == regcode.LOAD_NAME:
                    return None
                if site.binding is not None and site.binding.mutable:
                    return None
        if position >= len(marks):
            return None
        line, col = marks[position]
        if not line:
            return None
        if written is not None and written == (line, col) \
                and position not in targets:
            return None
        return "    bun_at(%d, %d);" % (line, col)

    def position_of(self, code, position):
        """The line and the column of an instruction of the program."""
        marks = code.get("lines", [])
        if position < len(marks):
            line, col = marks[position]
            return line, col
        return 0, 0

    def emit_instruction(self, code, instruction, position, depths,
                         handler_number):
        op, a, b, c = instruction
        consts = code.get("consts", [])
        if op in REFUSED:
            raise CBackendError(
                "the C backend does not support %s" % REFUSED[op],
                *self.position_of(code, position))
        if op == regcode.CONST:
            return ["    regs[%d] = %s;" % (a, self.const_expr(code, a, b))]
        if op == regcode.LOAD_NAME:
            site = self.frames[id(code)].site_at(position)
            if site.dynamic:
                static = self.static_name_at(code, position, consts[b])
                if static is None:
                    static = self.static_builtin_at(code, position, consts[b])
                    if static is not None:
                        # The builtin is copied into the static when the
                        # program starts, and the program always runs
                        # after that, so the read needs no check.
                        return ["    regs[%d] = %s;" % (a, static)]
                if static is not None:
                    return ["    regs[%d] = %s;" % (a, static)]
                return ["    regs[%d] = bun_env_get(env, %s);"
                        % (a, _c_string(consts[b]))]
            return ["    regs[%d] = %s;" % (a, self.slot_ref(code, site.slot))]
        if op == regcode.STORE_NAME:
            site = self.frames[id(code)].site_at(position)
            if site.dynamic:
                return ["    bun_env_assign(env, %s, regs[%d]);"
                        % (_c_string(consts[b]), a)]
            if not site.binding.mutable:
                return ["    bun_throw(\"cannot assign to immutable variable "
                        "'%s'\", %s);" % (consts[b], _c_string(consts[b]))]
            return ["    %s = bun_copy_value(regs[%d]);"
                    % (self.slot_ref(code, site.slot), a)]
        if op == regcode.DEFINE_NAME:
            site = self.frames[id(code)].site_at(position)
            if site.dynamic:
                lines = ["    bun_env_define(env, %s, regs[%d], %d);"
                         % (_c_string(consts[b]), a, 1 if c else 0)]
                number = self._module_of[self._index[id(code)]]
                key = (number, consts[b])
                place = self.static_definitions.get(key)
                if place is not None and place[0] is code \
                        and place[1] == position:
                    # The static variable holds the function, so a later
                    # read of the name does not look it up, and the static
                    # environment holds the environment the function closes
                    # over, so a later call of it does not look it up
                    # either.
                    lines.append("    %s = bun_copy_value(regs[%d]);"
                                 % (self.static_globals[key], a))
                    lines.append("    %s = env;"
                                 % self.static_environments[key])
                return lines
            return ["    %s = bun_copy_value(regs[%d]);"
                    % (self.slot_ref(code, site.slot), a)]
        if op == regcode.POP:
            return []
        if op == regcode.DUP:
            return ["    regs[%d] = regs[%d];" % (a + 1, a)]
        if op == regcode.ADD:
            return ["    regs[%d] = bun_add(regs[%d], regs[%d]);" % (a, b, c)]
        if op == regcode.SUB:
            return ["    regs[%d] = bun_sub(regs[%d], regs[%d]);" % (a, b, c)]
        if op == regcode.MUL:
            return ["    regs[%d] = bun_mul(regs[%d], regs[%d]);" % (a, b, c)]
        if op == regcode.DIV:
            return ["    regs[%d] = bun_div(regs[%d], regs[%d]);" % (a, b, c)]
        if op == regcode.MOD:
            return ["    regs[%d] = bun_mod(regs[%d], regs[%d]);" % (a, b, c)]
        if op == regcode.POW:
            return ["    regs[%d] = bun_pow(regs[%d], regs[%d]);" % (a, b, c)]
        if op == regcode.EQ:
            return ["    regs[%d] = bun_bool_value(bun_values_equal(regs[%d], "
                    "regs[%d]));" % (a, b, c)]
        if op == regcode.NE:
            return ["    regs[%d] = bun_bool_value(!bun_values_equal(regs[%d], "
                    "regs[%d]));" % (a, b, c)]
        if op == regcode.LT:
            return ["    regs[%d] = bun_compare(regs[%d], regs[%d], 0);"
                    % (a, b, c)]
        if op == regcode.LE:
            return ["    regs[%d] = bun_compare(regs[%d], regs[%d], 1);"
                    % (a, b, c)]
        if op == regcode.GT:
            return ["    regs[%d] = bun_compare(regs[%d], regs[%d], 2);"
                    % (a, b, c)]
        if op == regcode.GE:
            return ["    regs[%d] = bun_compare(regs[%d], regs[%d], 3);"
                    % (a, b, c)]
        if op == regcode.BAND:
            return ["    regs[%d] = bun_bits(regs[%d], regs[%d], 0);"
                    % (a, b, c)]
        if op == regcode.BOR:
            return ["    regs[%d] = bun_bits(regs[%d], regs[%d], 1);"
                    % (a, b, c)]
        if op == regcode.BXOR:
            return ["    regs[%d] = bun_bits(regs[%d], regs[%d], 2);"
                    % (a, b, c)]
        if op == regcode.SHL:
            return ["    regs[%d] = bun_bits(regs[%d], regs[%d], 3);"
                    % (a, b, c)]
        if op == regcode.SHR:
            return ["    regs[%d] = bun_bits(regs[%d], regs[%d], 4);"
                    % (a, b, c)]
        if op == regcode.NEG:
            return ["    regs[%d] = bun_negate(regs[%d]);" % (a, a)]
        if op == regcode.INVERT:
            return ["    regs[%d] = bun_invert(regs[%d]);" % (a, a)]
        if op == regcode.NOT:
            return ["    regs[%d] = bun_bool_value(!bun_truthy(regs[%d]));" % (a, a)]
        if op == regcode.BUILD_LIST:
            lines = ["    {",
                     "        BunValue items[%d];" % max(b, 1)]
            for index in range(b):
                lines.append("        items[%d] = regs[%d];"
                             % (index, a + index))
            lines.extend([
                "        BunValue list = bun_list_new();",
                "        for (int i = 0; i < %d; i++) {" % b,
                "            bun_list_push(list.as.obj, items[i]);",
                "        }",
                "        regs[%d] = list;" % a,
                "    }",
            ])
            return lines
        if op == regcode.BUILD_DICT:
            lines = ["    {",
                     "        BunValue items[%d];" % max(b * 2, 1)]
            for index in range(b * 2):
                lines.append("        items[%d] = regs[%d];"
                             % (index, a + index))
            lines.extend([
                "        BunValue dict = bun_dict_new();",
                "        for (int i = 0; i < %d; i++) {" % b,
                "            bun_dict_set(dict.as.obj, items[i * 2],",
                "                              items[i * 2 + 1]);",
                "        }",
                "        regs[%d] = dict;" % a,
                "    }",
            ])
            return lines
        if op == regcode.BUILD_STRING:
            lines = ["    {",
                     "        BunValue items[%d];" % max(b, 1)]
            for index in range(b):
                lines.append("        items[%d] = regs[%d];"
                             % (index, a + index))
            lines.extend([
                "        BunValue text = bun_str_new(\"\", 0);",
                "        for (int i = 0; i < %d; i++) {" % b,
                "            text = bun_str_concat(text, items[i]);",
                "        }",
                "        regs[%d] = text;" % a,
                "    }",
            ])
            return lines
        if op == regcode.LIST_APPEND:
            return [
                "    if (regs[%d].tag != BUN_LIST) {" % a,
                "        bun_throw(\"internal error: list append target\");",
                "    }",
                "    bun_list_push(regs[%d].as.obj, regs[%d]);" % (a, a + 1),
            ]
        if op == regcode.MAKE_STRUCT:
            type_name, field_names = consts[b]
            lines = ["    {",
                     "        const char *names[%d];" % max(c, 1)]
            for index, name in enumerate(field_names):
                lines.append("        names[%d] = %s;"
                             % (index, _c_string(name)))
            lines.append("        BunValue values[%d];" % max(c, 1))
            for index in range(c):
                lines.append("        values[%d] = regs[%d];"
                             % (index, a + index))
            lines.extend([
                "        regs[%d] = bun_struct_new(%s, names, values, %d);"
                % (a, _c_string(type_name), c),
                "    }",
            ])
            return lines
        if op == regcode.GET_FIELD:
            return ["    regs[%d] = bun_get_field(regs[%d], %s);"
                    % (a, b, _c_string(consts[c]))]
        if op == regcode.SET_FIELD:
            return ["    bun_set_field(regs[%d], %s, regs[%d]);"
                    % (a, _c_string(consts[c]), b)]
        if op == regcode.REGISTER_IMPL:
            body = consts[c]
            return ["    bun_register_struct_method(%s, %s, %s, env);"
                    % (_c_string(consts[a]), _c_string(consts[b]),
                       self.function_name(body))]
        if op == regcode.DICT_SET:
            return [
                "    if (regs[%d].tag != BUN_DICT) {" % a,
                "        bun_throw(\"internal error: dict set target\");",
                "    }",
                "    bun_dict_set(regs[%d].as.obj, regs[%d], regs[%d]);"
                % (a, b, c),
            ]
        if op == regcode.INDEX:
            return ["    regs[%d] = bun_index(regs[%d], regs[%d]);" % (a, b, c)]
        if op == regcode.STORE_INDEX:
            return ["    bun_store_index(regs[%d], regs[%d], regs[%d]);"
                    % (a, b, c)]
        if op == regcode.SLICE:
            return ["    regs[%d] = bun_slice(regs[%d], regs[%d], regs[%d], "
                    "regs[%d]);" % (a, a, a + 1, a + 2, a + 3)]
        if op == regcode.STORE_SLICE:
            return ["    bun_store_slice(regs[%d], regs[%d], regs[%d], regs[%d], "
                    "regs[%d]);" % (a + 1, a + 2, a + 3, a + 4, a)]
        if op == regcode.UNPACK_PLAN:
            plan = consts[b]
            kinds = self.plan_kinds(plan)
            lines = ["    {",
                     "        BunValue value = regs[%d];" % a,
                     "        BunValue unpacked[%d];" % max(len(kinds), 1),
                     "        bun_unpack(value, \"%s\", unpacked);" % kinds]
            for index in range(len(kinds)):
                lines.append("        regs[%d] = unpacked[%d];"
                             % (a + index, index))
            lines.append("    }")
            return lines
        if op == regcode.FORMAT:
            spec, conv, source_text = consts[b]
            return ["    regs[%d] = bun_format(regs[%d], %s, %s, %s);"
                    % (a, a, self.text_expr(spec), self.text_expr(conv),
                       self.text_expr(source_text))]
        if op == regcode.IMPORT:
            path, names = consts[a]
            number = self.module_number(path, code)
            lines = ["    {",
                     "        BunModule *module = bun_module_%d();" % number]
            for name in names:
                lines.append("        bun_env_define(env, %s, "
                             "bun_module_lookup(module, %s, %s), 0);"
                             % (_c_string(name), _c_string(name),
                                _c_string(path)))
            lines.append("    }")
            return lines
        if op == regcode.RECORD_EXPORT:
            name = consts[a]
            site = self.frames[id(code)].site_of_name(name, position)
            if site is None or site.dynamic:
                value = "bun_env_get(env, %s)" % _c_string(name)
            else:
                value = self.slot_ref(code, site.slot)
            return ["    bun_module_export(%s, %s);" % (_c_string(name), value)]
        if op == regcode.DEL:
            # The name lives in an environment, because the removal has to
            # reach the scope that holds the name.
            name = consts[a]
            return ["    bun_env_delete(env, %s);" % _c_string(name)]
        if op == regcode.DEL_INDEX:
            return ["    bun_delete_index(regs[%d], regs[%d]);" % (a, b)]
        if op == regcode.MAKE_FUNCTION:
            body = consts[b]
            index = self._index[id(body)]
            table, count = self.param_tables[index][0], \
                self.param_tables[index][1]
            needs_env = self.frames[id(body)].needs_env
            return ["    regs[%d] = bun_make_function(%s, %s, env, %s, %d, %d);"
                    % (a, _c_string(body.get("name", "<fn>")),
                       self.function_name(body), table, count, needs_env)]
        if op == regcode.CALL:
            kwargs = ("regs[%d]" % (a + b + 1)) if c else "bun_null_value()"
            lines = ["    {"]
            if not c:
                builtin = self.builtin_call(code, position, a)
                if builtin is not None:
                    # The name of the callee always holds the builtin of
                    # the language, so the call does not look the builtin
                    # up, and the compiler of the system sees which
                    # builtin is called.
                    lines.append("        BunValue call_args[%d];"
                                 % max(b, 1))
                    for index in range(b):
                        lines.append("        call_args[%d] = regs[%d];"
                                     % (index, a + 1 + index))
                    lines.extend([
                        "        BunValue result = bun_builtin_%s(call_args, %d);"
                        % (builtin, b),
                        "        regs[%d] = result;" % a,
                        "    }",
                    ])
                    return lines
            direct = self.direct_call(code, position, a)
            if direct is not None:
                # The name of the callee is a name of the module that the
                # program never changes, so the call does not look the
                # function up, and the compiler of the system can see
                # which function is called.
                function, environment, needs_env = direct
                if needs_env:
                    lines.append("        BunEnv *callee_env = bun_env_new(%s);"
                                 % environment)
                else:
                    lines.append("        BunEnv *callee_env = %s;" % environment)
                lines.append("        BunValue call_args[%d];" % max(b, 1))
                for index in range(b):
                    lines.append("        call_args[%d] = regs[%d];"
                                 % (index, a + 1 + index))
                lines.extend([
                    "        BunValue result = %s(callee_env, call_args, %d, %s);"
                    % (function, b, kwargs),
                    "        regs[%d] = result;" % a,
                    "    }",
                ])
                return lines
            lines.extend([
                "        BunValue callee = regs[%d];" % a,
                "        BunValue call_args[%d];" % max(b, 1),
            ])
            for index in range(b):
                lines.append("        call_args[%d] = regs[%d];"
                             % (index, a + 1 + index))
            lines.extend([
                "        BunValue result = bun_call(callee, call_args, %d, %s);"
                % (b, kwargs),
                "        regs[%d] = result;" % a,
                "    }",
            ])
            return lines
        if op == regcode.METHOD_CALL:
            method = consts[c]
            lines = ["    {",
                     "        BunValue receiver = regs[%d];" % a,
                     "        BunValue call_args[%d];" % max(b, 1)]
            for index in range(b):
                lines.append("        call_args[%d] = regs[%d];"
                             % (index, a + 1 + index))
            lines.extend([
                "        regs[%d] = bun_method_call(receiver, %s, call_args, %d);"
                % (a, _c_string(method), b),
                "    }",
            ])
            return lines
        if op == regcode.UNWRAP_OR_RETURN:
            return [
                "    {",
                "        BunValue tmp = regs[%d];" % a,
                "        BunValue out;",
                "        if (!bun_unwrap_result(tmp, &out)) {",
                "            return bun_copy_value(tmp);",
                "        }",
                "        regs[%d] = out;" % a,
                "    }",
            ]
        if op == regcode.RETURN:
            return ["    return bun_copy_value(regs[%d]);" % a]
        if op == regcode.HALT:
            # The value of the expression of the program is on the top of
            # the stack, one slot below the depth of the instruction.
            depth = depths[position] if position < len(depths) else 0
            if depth > 0:
                return ["    return regs[%d];" % (depth - 1)]
            return ["    return bun_null_value();"]
        if op == regcode.JUMP:
            return ["    goto L%d;" % a]
        if op == regcode.JUMP_IF_FALSE:
            return ["    if (!bun_truthy(regs[%d])) goto L%d;" % (a, b)]
        if op == regcode.JUMP_IF_TRUE:
            return ["    if (bun_truthy(regs[%d])) goto L%d;" % (a, b)]
        if op == regcode.ENTER_SCOPE:
            depth = self.frames[id(code)].scope_depth[position]
            lines = ["    scopes[%d] = env;" % depth]
            if self.frames[id(code)].enter_needs_env(position):
                lines.append("    env = bun_env_new(env);")
            return lines
        if op == regcode.EXIT_SCOPE:
            depth = self.frames[id(code)].scope_exit.get(position, 0)
            if depth <= 0:
                return []
            return ["    env = scopes[%d];" % depth]
        if op == regcode.SCOPE_ENTER:
            # The group of the scope is opened before the body runs, and
            # the tasks that the body spawns belong to the group.
            return ["    bun_scope_enter();"]
        if op == regcode.SCOPE_EXIT:
            # The group is closed: every task of the group is joined, and
            # the first failure of a child is the failure of the scope
            # when the body has no failure of its own.
            return ["    bun_scope_exit(pending);"]
        if op == regcode.FOR_SETUP:
            return ["    iters[iter_count++] = bun_iter_new(regs[%d]);" % a]
        if op == regcode.FOR_NEXT:
            return [
                "    {",
                "        BunValue item;",
                "        if (!bun_iter_next(&iters[iter_count - 1], &item)) {",
                "            iter_count--;",
                "            goto L%d;" % b,
                "        }",
                "        regs[%d] = item;" % a,
                "    }",
            ]
        if op == regcode.FOR_POP:
            return ["    if (iter_count > 0) { iter_count--; }"]
        if op == regcode.MATCH_TEST:
            plan = consts[b]
            key = (self._index[id(code)], id(plan))
            name = self._plan_names.get(key)
            if name is None:
                raise CBackendError(
                    "the C backend does not support the pattern of this case",
                    *self.position_of(code, position))
            return [
                "    {",
                "        BunMatchList bindings = { NULL, 0, 0 };",
                "        int matched = bun_match_plan(regs[%d], &%s, &bindings);"
                % (a, name),
                "        int index;",
                "        for (index = 0; index < bindings.count; index++) {",
                "            bun_env_define(env, bindings.items[index].name,",
                "                             bindings.items[index].value, 1);",
                "        }",
                "        regs[%d] = bun_bool_value(matched);" % a,
                "    }",
            ]
        if op == regcode.MATCH_FAIL:
            return ["    bun_throw(\"no matching case for %%s\", "
                    "bun_repr(regs[%d]));" % a]
        if op == regcode.PROTOCOL_GET:
            # The method of a `with` target is a method of a dictionary,
            # and a target that does not hold the method is a failure.
            return ["    regs[%d] = bun_protocol_get(regs[%d], %s);"
                    % (a, a, _c_string(consts[b]))]
        if op == regcode.WITH_ENTER:
            # The name of the `with` lives in the environment of the scope
            # that holds the statement, and the target waits on the stack
            # of the targets until the statement ends.
            return [
                "    bun_env_define(env, %s, regs[%d], 1);"
                % (_c_string(consts[b]), a + 1),
                "    with_stack[with_depth++] = regs[%d];" % a,
            ]
        if op == regcode.WITH_POP_TARGET:
            return [
                "    if (with_depth <= 0) {",
                "        bun_throw(\"'with' has no active target\");",
                "    }",
                "    regs[%d] = with_stack[--with_depth];" % a,
            ]
        if op == regcode.WITH_DEPTH:
            return ["    regs[%d] = bun_int_value(with_depth);" % a]
        if op == regcode.PENDING_ERROR:
            return ["    regs[%d] = pending->has ? pending->value : "
                    "bun_null_value();" % a]
        if op == regcode.CLEAR_ERROR:
            return ["    pending->has = 0;"]
        if op == regcode.HAS_ERROR:
            return ["    regs[%d] = bun_bool_value(pending->has);" % a]
        if op == regcode.TRY:
            slot = self.catch_slot(code, position, depths)
            return [
                "    h_%d = bun_handler_push(0, env);" % handler_number,
                "    if (setjmp(h_%d->buf) != 0) {" % handler_number,
                "        bun_handler_pop();",
                "        env = h_%d->env;" % handler_number,
                "        regs[%d] = bun_str_from_c(bun_error_message);" % slot,
                "        goto L%d;" % a,
                "    }",
            ]
        if op == regcode.TRY_FINALLY:
            return [
                "    h_%d = bun_handler_push(1, env);" % handler_number,
                "    if (setjmp(h_%d->buf) != 0) {" % handler_number,
                "        bun_handler_pop();",
                "        env = h_%d->env;" % handler_number,
                "        pending->value = bun_str_from_c(bun_error_message);",
                "        pending->has = 1;",
                "        goto L%d;" % a,
                "    }",
            ]
        if op == regcode.END_TRY:
            return ["    bun_handler_pop();"]
        if op == regcode.FINALLY_END:
            return [
                "    if (pending->has) {",
                "        pending->has = 0;",
                "        bun_throw(\"%s\", pending->value.as.obj->data);",
                "    }",
            ]
        if op == regcode.THROW:
            # The message of the error is the value that was thrown; the
            # cause of the error is only shown in the picture of the
            # failure, and the backend has no picture.
            return ["    bun_throw(\"%%s\", bun_stringify(regs[%d]));" % a]
        if op == regcode.ASSERT:
            # The branch that skips the assertion is already in the code,
            # so reaching the assertion means the condition was false.
            if b:
                return [
                    "    bun_throw(\"assertion failed: %%s\", "
                    "bun_stringify(regs[%d]));" % a,
                ]
            return ["    bun_throw(\"assertion failed\");"]
        raise CBackendError(
            "the C backend does not support the instruction '%s'" % op,
            *self.position_of(code, position))

    # -- the helpers --------------------------------------------------------

    def touched_slots(self, code, instruction):
        """The registers that an instruction reads or writes."""
        return regcode.touched_slots(code, instruction)

    def text_expr(self, text):
        if text is None:
            return "NULL"
        return _c_string(text)

    def plan_kinds(self, plan):
        """The plan of an unpacking, as the letters of the runtime."""
        if not isinstance(plan, (list, tuple)) or not plan or plan[0] != "seq":
            raise CBackendError(
                "the C backend does not support this unpacking")
        kinds = []
        for entry in plan[1:]:
            if not isinstance(entry, (list, tuple)) or not entry:
                raise CBackendError(
                    "the C backend does not support this unpacking")
            kind = entry[0]
            if kind == "leaf":
                kinds.append("l")
            elif kind == "star":
                kinds.append("s")
            else:
                raise CBackendError(
                    "the C backend does not support this unpacking")
        return "".join(kinds)

    def catch_slot(self, code, position, depths):
        """The register that holds the message of a caught error."""
        if position < len(depths):
            return depths[position]
        return 0

    def prepare_params(self):
        """Build the parameter table of every function."""
        self.param_tables = {}
        for index, code in enumerate(self.functions):
            defs = code.get("param_defs", [])
            info = self.frames[id(code)]
            if not defs:
                self.param_tables[index] = ("NULL", 0, [])
                continue
            name = "bun_params_%d" % index
            lines = []
            method = id(code) in self.methods
            for position, spec in enumerate(defs):
                kind = spec.get("param_kind", "positional")
                if kind == "positional":
                    code_kind = 0
                elif kind == "vararg":
                    code_kind = 1
                elif kind == "kwarg":
                    code_kind = 2
                else:
                    code_kind = 3
                # The first argument of a method is the receiver, and it
                # is borrowed: the method changes the receiver itself.
                borrowed = 1 if method and position == 0 else 0
                default = spec.get("default")
                if default is None:
                    lines.append("    { %s, %d, 0, NULL, %d, %d }," % (
                        _c_string(spec["name"]), code_kind, self.param_slot(
                            info, position), borrowed))
                else:
                    default_index = self._index[id(default)]
                    lines.append("    { %s, %d, 1, %s, %d, %d }," % (
                        _c_string(spec["name"]), code_kind,
                        self.function_name(default),
                        self.param_slot(info, position), borrowed))
            self.param_tables[index] = (name, len(defs), lines)

    def param_slot(self, info, position):
        """The slot of the frame where a parameter of a function lives."""
        if position >= len(info.param_bindings):
            return -1
        slot = info.param_bindings[position].slot
        if slot is None:
            return -1
        return slot

    def slot_ref(self, code, index):
        """The name of a slot of the frame of the names of a function.

        The frame of a function that catches no error is a few variables
        and not an array, so the compiler of the system keeps the names
        in the registers of the machine.
        """
        if self.scalar_slots.get(id(code)):
            return "slot_%d" % index
        return "slots[%d]" % index

    def bind_parameters(self, code, table, count):
        """The lines that bind the arguments of a function.

        A function whose parameters are all plain and live in the frame
        takes its arguments with a few stores, and the slow path of the
        runtime is only there for the calls that are not plain.
        """
        name = _c_string(code.get("name", "<fn>"))
        defs = code.get("param_defs", [])
        info = self.frames[id(code)]
        frame = max(info.slot_count, 1)
        scalars = bool(self.scalar_slots.get(id(code)))

        def slow(indent):
            """The path of the calls that are not plain.

            The runtime wants the frame of the names as an array.  The
            frame of a function that catches no error is a few variables,
            so the slow path copies them into an array, and the copy
            keeps the frame in the registers of the machine.
            """
            if not scalars:
                return [indent + "bun_bind_parameters(env, %s, %s, %d, args, "
                        "argc, kwargs, slots);" % (name, table, count)]
            lines = [indent + "BunValue binding[%d];" % frame,
                     indent + "memset(binding, 0, sizeof(binding));"]
            for index in range(frame):
                lines.append(indent + "binding[%d] = %s;"
                             % (index, self.slot_ref(code, index)))
            lines.append(indent + "bun_bind_parameters(env, %s, %s, %d, args, "
                         "argc, kwargs, binding);" % (name, table, count))
            for index in range(frame):
                lines.append(indent + "%s = binding[%d];"
                             % (self.slot_ref(code, index), index))
            return lines

        slots = []
        for position, spec in enumerate(defs):
            if spec.get("param_kind", "positional") != "positional":
                return slow("    ")
            if spec.get("default") is not None:
                return slow("    ")
            slot = self.param_slot(info, position)
            if slot < 0:
                return slow("    ")
            slots.append(slot)
        # The first argument of a method is the receiver, and it is
        # borrowed: the other arguments are copied.
        method = id(code) in self.methods
        lines = ["    if (kwargs.tag != BUN_DICT && argc == %d) {" % count]
        for position, slot in enumerate(slots):
            if method and position == 0:
                lines.append("        %s = args[%d];"
                             % (self.slot_ref(code, slot), position))
            else:
                lines.append("        %s = bun_copy_value(args[%d]);"
                             % (self.slot_ref(code, slot), position))
        lines.append("    } else {")
        lines.extend(slow("        "))
        lines.append("    }")
        return lines

    def emit_param_tables(self):
        """The parameter tables of the functions."""
        lines = []
        for index in sorted(self.param_tables):
            name, count, body = self.param_tables[index]
            if not body:
                continue
            lines.append("static const BunParam %s[] = {" % name)
            lines.extend(body)
            lines.append("};")
        return lines


def emit_program(code, filename="<program>", source=None):
    """The C source of a program."""
    emitter = CEmitter(code, filename, source)
    text = emitter.emit()
    return text, emitter


RUNTIME_HEADER = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "lib", "bun", "c_runtime.h")

CACHE_DIR = os.environ.get(
    "BUN_CACHE_DIR",
    os.path.join(os.path.expanduser("~"), ".cache", "bun", "c"))


# The flags of the compiler of C. They are part of the key of the cache,
# so a change of them builds the programs again.
# The flags of the compiler of the system.
#
# The loops are aligned on a boundary of 32 bytes, because the loop of a
# program is the place where the speed matters most, and an aligned loop
# runs faster.
#
# The compiler does not guess the way a branch goes.  A guess makes the
# compiler of the system lay the blocks of the program out for the guess,
# and the guess is wrong for the loops of a program often enough that the
# value of a loop stays in the memory instead of the registers of the
# machine.  Without the guess, every loop of a program runs at the same
# speed.
CFLAGS = ("-std=c11", "-O3", "-falign-loops=32",
          "-fno-guess-branch-probability", "-w")


def cache_key(source, compiler):
    """The key of a program in the cache of the built binaries.

    The key covers the source, the runtime of C, the compiler and its
    flags, so a change of any of them builds the program again.
    """
    import hashlib
    digest = hashlib.sha256()
    digest.update(source.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(compiler.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(" ".join(CFLAGS).encode("utf-8"))
    digest.update(b"\x00")
    try:
        with open(RUNTIME_HEADER, "rb") as handle:
            digest.update(handle.read())
    except OSError:
        pass
    return digest.hexdigest()[:32]


def build_binary(code, filename="<program>", workdir=None, cc=None,
                 keep=False, cache=True, source=None):
    """Compile a program into a binary and return the path of the binary.

    The binary of a program is kept in the cache, so the second run of
    the same program does not pay for the compiler of the system.
    """
    text, _ = emit_program(code, filename, source)
    compiler = cc or os.environ.get("CC", "cc")
    directory = workdir
    cached = None
    if cache and directory is None:
        key = cache_key(text, compiler)
        cached = os.path.join(CACHE_DIR, key, "program")
        if os.path.exists(cached):
            return cached, os.path.dirname(cached)
    if directory is None:
        directory = tempfile.mkdtemp(prefix="bun-c-")
    os.makedirs(directory, exist_ok=True)
    c_path = os.path.join(directory, "program.c")
    with open(c_path, "w", encoding="utf-8") as handle:
        handle.write(text)
    binary = os.path.join(directory, "program")
    command = [compiler] + list(CFLAGS) + ["-I",
               os.path.dirname(RUNTIME_HEADER), "-o", binary, c_path, "-lm"]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise CBackendError("the C compiler failed:\n%s" % result.stderr)
    if cache and cached is not None:
        try:
            os.makedirs(os.path.dirname(cached), exist_ok=True)
            shutil.copy2(binary, cached)
            return cached, os.path.dirname(cached)
        except OSError:
            pass
    return binary, directory


def is_cached(directory):
    """Whether a build directory belongs to the cache."""
    try:
        return os.path.abspath(directory).startswith(
            os.path.abspath(CACHE_DIR) + os.sep)
    except (TypeError, ValueError):
        return False


def run_binary(binary, program_args=None, filename=None):
    """Run a compiled program."""
    command = [binary]
    if program_args:
        command.extend(program_args)
    environment = None
    if filename:
        environment = dict(os.environ)
        environment["BUN_SOURCE_FILE"] = filename
    return subprocess.run(command, env=environment)


def cleanup(directory):
    """Remove the directory of a build."""
    shutil.rmtree(directory, ignore_errors=True)
