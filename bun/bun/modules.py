import json
import os

from .errors import BunRuntimeError, LexError, ParseError
from .lexer import Lexer
from .parser import Parser

PACKAGE_DIR = "bun_modules"
MANIFEST = "bun.pkg"
NATIVE_PREFIX = "bun:"
NATIVE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "lib", "bun")


def resolve_native(path):
    """Resolve a `bun:` module path to a file of the language's own library.

    The prefix can only name a file inside the library directory, so it
    cannot be used to load a module from anywhere else.
    """
    name = path[len(NATIVE_PREFIX):]
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise BunRuntimeError("invalid native module name '%s'" % path)
    if not name.replace("_", "").replace("-", "").isalnum():
        raise BunRuntimeError("invalid native module name '%s'" % path)
    full = os.path.join(NATIVE_DIR, name + ".bun")
    if not os.path.exists(full):
        raise BunRuntimeError("cannot find native module '%s'" % path)
    return full


def _read_manifest(path):
    try:
        with open(path, "r") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as error:
        raise BunRuntimeError("cannot read package manifest '%s': %s" % (path, error))
    if not isinstance(data, dict):
        raise BunRuntimeError("cannot read package manifest '%s': not an object" % path)
    return data


def _package_entry(package_root, name):
    manifest_path = os.path.join(package_root, MANIFEST)
    if os.path.exists(manifest_path):
        data = _read_manifest(manifest_path)
        main = data.get("main", "main.bun")
        candidate = os.path.normpath(os.path.join(package_root, main))
        if os.path.exists(candidate):
            return candidate
        if os.path.exists(candidate + ".bun"):
            return candidate + ".bun"
        raise BunRuntimeError(
            "package '%s' manifest points at a missing entry '%s'" % (name, main))
    for candidate in ("main.bun", "index.bun", name + ".bun"):
        full = os.path.join(package_root, candidate)
        if os.path.exists(full):
            return full
    raise BunRuntimeError(
        "package '%s' has no %s, main.bun, or index.bun" % (name, MANIFEST))


def resolve_package(path, base_dir):
    directory = os.path.abspath(base_dir or os.getcwd())
    while True:
        root = os.path.join(directory, PACKAGE_DIR)
        if os.path.isdir(root):
            package_root = os.path.join(root, path)
            if os.path.isdir(package_root):
                return _package_entry(package_root, path)
            direct = os.path.join(root, path + ".bun")
            if os.path.exists(direct):
                return direct
        parent = os.path.dirname(directory)
        if parent == directory:
            break
        directory = parent
    raise BunRuntimeError(
        "cannot find package '%s' in any %s directory" % (path, PACKAGE_DIR))


def resolve_module_path(path, base_dir):
    if path.startswith(NATIVE_PREFIX):
        return resolve_native(path)
    if path.startswith("./") or path.startswith("../"):
        full = os.path.normpath(os.path.join(base_dir, path))
        if not os.path.exists(full):
            full = full + ".bun"
        if not os.path.exists(full):
            raise BunRuntimeError("cannot find module '%s'" % path)
        return full
    if path.startswith("/") or path.startswith("."):
        raise BunRuntimeError(
            "unsupported module path '%s' (use './', '../', or a package name)"
            % path)
    return resolve_package(path, base_dir)


def load_module_source(path, full_path):
    try:
        with open(full_path, "r") as handle:
            source = handle.read()
    except OSError as error:
        raise BunRuntimeError(
            "cannot read module '%s': %s" % (path, error.strerror))
    except UnicodeDecodeError:
        raise BunRuntimeError(
            "cannot read module '%s': not valid UTF-8" % path)
    try:
        return Parser(Lexer(source).tokenize()).parse()
    except (LexError, ParseError) as error:
        raise BunRuntimeError(
            "cannot load module '%s': %s" % (path, error.msg))


def module_dir(full_path):
    return os.path.dirname(full_path)


def read_source(full_path):
    try:
        with open(full_path, "r") as handle:
            return handle.read()
    except OSError:
        return ""


def attach_module_frame(error, full_path, path):
    if error.filename is None:
        error.filename = full_path
    if error.source:
        return
    try:
        with open(full_path, "r") as handle:
            error.source = handle.read()
    except OSError:
        error.source = None
