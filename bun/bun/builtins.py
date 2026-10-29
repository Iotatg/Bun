import importlib
import json
import os
import struct
import subprocess
import sys
import threading
import time

from .dict import BunDict
from .set import BunSet
from .values import (
    Builtin, BunFunction, BunSecret, canonical_dump, is_truthy, stringify,
)
from .errors import BunRuntimeError
from .generators import is_generator
from .ints import check as _check_int
from . import tasks
from . import sandbox
from .ops import type_name


_FFI_ALLOWED = frozenset({
    "math", "time", "random", "json", "hashlib", "base64",
    "urllib.parse", "re", "uuid", "secrets", "string",
    "socket", "ssl", "cryptography", "binascii", "sqlite3",
})


def _make_args(program_args):
    values = list(program_args or [])

    def args_builtin(args):
        if len(args) != 0:
            raise BunRuntimeError("args() expects no arguments")
        return list(values)

    return args_builtin


def _print(args):
    print(" ".join(stringify(a) for a in args))
    return None


def _len(args):
    if len(args) != 1:
        raise BunRuntimeError("len() expects 1 argument")
    value = args[0]
    if isinstance(value, (str, list)):
        return len(value)
    raise BunRuntimeError("len() expects a string or list")


def _range(args):
    if len(args) == 1:
        start, stop, step = 0, args[0], 1
    elif len(args) == 2:
        start, stop, step = args[0], args[1], 1
    elif len(args) == 3:
        start, stop, step = args[0], args[1], args[2]
    else:
        raise BunRuntimeError("range() expects 1, 2 or 3 arguments")
    for value in (start, stop, step):
        if not isinstance(value, int) or isinstance(value, bool):
            raise BunRuntimeError("range() expects integer arguments")
    if step == 0:
        raise BunRuntimeError("range() step argument must not be zero")
    return list(range(start, stop, step))


def _str(args):
    if len(args) != 1:
        raise BunRuntimeError("str() expects 1 argument")
    return stringify(args[0])


def _input(args):
    if len(args) > 1:
        raise BunRuntimeError("input() expects an optional prompt")
    if args:
        if not isinstance(args[0], str):
            raise BunRuntimeError("input() expects a string prompt")
        sys.stdout.write(args[0])
        sys.stdout.flush()
    line = sys.stdin.readline()
    if line == "":
        raise BunRuntimeError("input() reached the end of the input")
    if line.endswith("\n"):
        line = line[:-1]
    if line.endswith("\r"):
        line = line[:-1]
    return line


def _int(args):
    if len(args) not in (1, 2):
        raise BunRuntimeError("int() expects 1 or 2 arguments")
    value = args[0]
    base = args[1] if len(args) == 2 else 10
    if not isinstance(base, int) or isinstance(base, bool):
        raise BunRuntimeError("int() expects base as int")
    if base < 2 or base > 36:
        raise BunRuntimeError("int() base must be between 2 and 36")
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        try:
            return _check_int(int(value), "integer out of range")
        except (ValueError, OverflowError):
            raise BunRuntimeError("cannot convert %s to int" % stringify(value))
    if isinstance(value, str):
        try:
            if base == 10:
                return _check_int(int(value), "integer out of range")
            return _check_int(int(value.strip(), base), "integer out of range")
        except ValueError:
            raise BunRuntimeError("cannot convert '%s' to int" % value)
    raise BunRuntimeError("cannot convert value to int")


def _chr(args):
    _one("chr", args)
    value = args[0]
    if not isinstance(value, int) or isinstance(value, bool):
        raise BunRuntimeError("chr() expects an int")
    if value < 0 or value > 0x10FFFF:
        raise BunRuntimeError("chr() argument out of range")
    try:
        return chr(value)
    except ValueError:
        raise BunRuntimeError("chr() argument out of range")


def _ord(args):
    _one("ord", args)
    value = args[0]
    if not isinstance(value, str):
        raise BunRuntimeError("ord() expects a string")
    if len(value) != 1:
        raise BunRuntimeError("ord() expects a single character string")
    return ord(value)


def _float(args):
    if len(args) != 1:
        raise BunRuntimeError("float() expects 1 argument")
    value = args[0]
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (ValueError, OverflowError):
            raise BunRuntimeError("cannot convert %s to float" % stringify(value))
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            raise BunRuntimeError("cannot convert '%s' to float" % value)
    raise BunRuntimeError("cannot convert value to float")


def _read_file(args):
    _one("read_file", args)
    if not isinstance(args[0], str):
        raise BunRuntimeError("read_file() expects a string path")
    sandbox.check_fs(args[0])
    try:
        with open(args[0], "r") as handle:
            return handle.read()
    except OSError as error:
        raise BunRuntimeError("cannot read '%s': %s" % (args[0], error.strerror))


def _write_file(args):
    _two("write_file", args)
    if not isinstance(args[0], str):
        raise BunRuntimeError("write_file() expects a string path")
    if not isinstance(args[1], str):
        raise BunRuntimeError("write_file() expects a string")
    sandbox.check_fs(args[0])
    try:
        with open(args[0], "w") as handle:
            handle.write(args[1])
    except OSError as error:
        raise BunRuntimeError("cannot write '%s': %s" % (args[0], error.strerror))
    return None


def _append_file(args):
    _two("append_file", args)
    if not isinstance(args[0], str):
        raise BunRuntimeError("append_file() expects a string path")
    if not isinstance(args[1], str):
        raise BunRuntimeError("append_file() expects a string")
    sandbox.check_fs(args[0])
    try:
        with open(args[0], "a") as handle:
            handle.write(args[1])
    except OSError as error:
        raise BunRuntimeError("cannot append to '%s': %s" % (args[0], error.strerror))
    return None


def _file_exists(args):
    _one("file_exists", args)
    if not isinstance(args[0], str):
        raise BunRuntimeError("file_exists() expects a string path")
    return os.path.exists(args[0])


def _getenv(args):
    _one("getenv", args)
    if not isinstance(args[0], str):
        raise BunRuntimeError("getenv() expects a string name")
    return os.environ.get(args[0])


def _getenv_or(args):
    _two("getenv_or", args)
    if not isinstance(args[0], str) or not isinstance(args[1], str):
        raise BunRuntimeError("getenv_or() expects two string arguments")
    return os.environ.get(args[0], args[1])


def _json_parse(args):
    _one("json_parse", args)
    if not isinstance(args[0], str):
        raise BunRuntimeError("json_parse() expects a string")
    try:
        return _from_json(json.loads(args[0]))
    except ValueError as error:
        raise BunRuntimeError("json_parse() failed: %s" % error)


def _from_json(value):
    if isinstance(value, dict):
        result = BunDict()
        for key, item in value.items():
            result.set(str(key), _from_json(item))
        return result
    if isinstance(value, list):
        return [_from_json(item) for item in value]
    return value


def _to_json(value):
    if isinstance(value, BunDict):
        return {str(key[1]): _to_json(item) for key, item in value.items.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json(item) for item in value]
    return value


def _to_python(value):
    if isinstance(value, BunDict):
        return {str(key[1]): _to_python(item) for key, item in value.items.items()}
    if isinstance(value, (list, tuple)):
        return [_to_python(item) for item in value]
    return value


def _to_bun(value):
    if isinstance(value, dict):
        result = BunDict()
        for key, item in value.items():
            result.set(str(key), _to_bun(item))
        return result
    if isinstance(value, (list, tuple)):
        return [_to_bun(item) for item in value]
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", "replace")
    return value


def _json_stringify(args):
    _one("json_stringify", args)
    try:
        return json.dumps(_to_json(args[0]), ensure_ascii=False)
    except (TypeError, ValueError) as error:
        raise BunRuntimeError("json_stringify() failed: %s" % error)


def _http_request(method, args, arity, body_index=None):
    if len(args) != arity:
        raise BunRuntimeError(
            "%s() expects %d arguments, got %d" % (method.lower(), arity, len(args)))
    url = args[0]
    headers = args[1]
    if not isinstance(url, str):
        raise BunRuntimeError("%s() expects a string url" % method.lower())
    if not isinstance(headers, BunDict):
        raise BunRuntimeError("%s() expects a dict of headers" % method.lower())
    body = None
    timeout = 30.0
    if body_index is not None:
        raw = args[body_index]
        if raw is not None:
            if not isinstance(raw, str):
                raise BunRuntimeError("%s() expects a string body" % method.lower())
            body = raw.encode("utf-8")
        timeout = args[body_index + 1]
    else:
        timeout = args[2]
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
        raise BunRuntimeError("%s() expects a numeric timeout" % method.lower())
    sandbox.check_net_url(url)
    header_map = {}
    for key in headers.keys():
        header_map[str(key)] = stringify(headers.get(key))
    import urllib.error
    import urllib.request
    request = urllib.request.Request(
        url, data=body, headers=header_map, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8", "replace")
            result = BunDict()
            result.set("status", response.status)
            result.set("body", payload)
            return result
    except urllib.error.HTTPError as error:
        payload = error.read().decode("utf-8", "replace")
        result = BunDict()
        result.set("status", error.code)
        result.set("body", payload)
        return result


def _http_get(args):
    return _http_request("GET", args, 3)


def _http_get_bytes(args):
    """Fetch a URL and return the body as a list of byte values."""
    if len(args) != 3:
        raise BunRuntimeError(
            "http_get_bytes() expects 3 arguments, got %d" % len(args))
    url = args[0]
    headers = args[1]
    if not isinstance(url, str):
        raise BunRuntimeError("http_get_bytes() expects a string url")
    if not isinstance(headers, BunDict):
        raise BunRuntimeError("http_get_bytes() expects a dict of headers")
    timeout = args[2]
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
        raise BunRuntimeError("http_get_bytes() expects a numeric timeout")
    sandbox.check_net_url(url)
    header_map = {}
    for key in headers.keys():
        header_map[str(key)] = stringify(headers.get(key))
    import urllib.error
    import urllib.request
    request = urllib.request.Request(url, headers=header_map, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return _bytes_response(response.status, response.read(),
                                   response.headers)
    except urllib.error.HTTPError as error:
        return _bytes_response(error.code, error.read(), error.headers)
    except urllib.error.URLError as error:
        raise BunRuntimeError("http_get_bytes() failed: %s" % error.reason)
    except OSError as error:
        raise BunRuntimeError("http_get_bytes() failed: %s" % error)


def _bytes_response(status, payload, headers):
    result = BunDict()
    result.set("status", status)
    result.set("body", list(payload))
    collected = BunDict()
    if headers is not None:
        for key in headers.keys():
            collected.set(str(key), headers.get(key))
    result.set("headers", collected)
    return result


def _write_bytes(args):
    """Write a list of byte values to a file."""
    _two("write_bytes", args)
    if not isinstance(args[0], str):
        raise BunRuntimeError("write_bytes() expects a string path")
    if not isinstance(args[1], list):
        raise BunRuntimeError("write_bytes() expects a list of bytes")
    sandbox.check_fs(args[0])
    payload = bytearray()
    for value in args[1]:
        if not isinstance(value, int) or isinstance(value, bool):
            raise BunRuntimeError("write_bytes() expects a list of bytes")
        if value < 0 or value > 255:
            raise BunRuntimeError("write_bytes() expects bytes between 0 and 255")
        payload.append(value)
    try:
        with open(args[0], "wb") as handle:
            handle.write(bytes(payload))
    except OSError as error:
        raise BunRuntimeError("cannot write '%s': %s" % (args[0], error.strerror))
    return len(payload)


def _read_bytes(args):
    """Read a file and return its content as a list of byte values."""
    _one("read_bytes", args)
    if not isinstance(args[0], str):
        raise BunRuntimeError("read_bytes() expects a string path")
    sandbox.check_fs(args[0])
    try:
        with open(args[0], "rb") as handle:
            return list(handle.read())
    except OSError as error:
        raise BunRuntimeError("cannot read '%s': %s" % (args[0], error.strerror))


def _bytes_append(args):
    """Append a list of byte values to another list of byte values."""
    _two("bytes_append", args)
    if not isinstance(args[0], list):
        raise BunRuntimeError("bytes_append() expects a list of bytes")
    if not isinstance(args[1], list):
        raise BunRuntimeError("bytes_append() expects a list of bytes")
    target = args[0]
    payload = args[1]
    for value in payload:
        if not isinstance(value, int) or isinstance(value, bool):
            raise BunRuntimeError("bytes_append() expects a list of bytes")
        if value < 0 or value > 255:
            raise BunRuntimeError("bytes_append() expects bytes between 0 and 255")
        target.append(value)
    return len(payload)


def _bytes_slice(args):
    """Take a part of a list of byte values."""
    _three("bytes_slice", args)
    if not isinstance(args[0], list):
        raise BunRuntimeError("bytes_slice() expects a list of bytes")
    if not isinstance(args[1], int) or isinstance(args[1], bool):
        raise BunRuntimeError("bytes_slice() expects an integer start")
    if not isinstance(args[2], int) or isinstance(args[2], bool):
        raise BunRuntimeError("bytes_slice() expects an integer end")
    data = args[0]
    start = args[1]
    end = args[2]
    if start < 0 or end < start:
        raise BunRuntimeError("bytes_slice() expects a start before the end")
    if end > len(data):
        end = len(data)
    return data[start:end]


def _http_post(args):
    return _http_request("POST", args, 4, body_index=2)


def _http_post_multipart(args):
    """Post a multipart body, with fields and files.

    The parts are a list of dictionaries.  A part with a `value` is a
    field, and a part with a `path` is a file: its bytes are read from
    the disk and put in the body under its name.
    """
    if len(args) != 4:
        raise BunRuntimeError(
            "http_post_multipart() expects 4 arguments, got %d" % len(args))
    url = args[0]
    headers = args[1]
    parts = args[2]
    timeout = args[3]
    if not isinstance(url, str):
        raise BunRuntimeError("http_post_multipart() expects a string url")
    if not isinstance(headers, BunDict):
        raise BunRuntimeError(
            "http_post_multipart() expects a dict of headers")
    if not isinstance(parts, list):
        raise BunRuntimeError(
            "http_post_multipart() expects a list of parts")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
        raise BunRuntimeError(
            "http_post_multipart() expects a numeric timeout")

    import random as _random_module
    boundary = "----bunform" + "".join(
        str(_random_module.randint(0, 9)) for _ in range(16))
    body = bytearray()
    for part in parts:
        if not isinstance(part, (dict, BunDict)):
            raise BunRuntimeError(
                "every part of http_post_multipart() must be a dict")
        name = part.get("name")
        if not isinstance(name, str) or name == "":
            raise BunRuntimeError(
                "every part of http_post_multipart() needs a name")
        if part.get("path") is not None:
            path = part.get("path")
            if not isinstance(path, str):
                raise BunRuntimeError(
                    "the path of a part of http_post_multipart() "
                    "must be a string")
            sandbox.check_fs(path)
            try:
                with open(path, "rb") as handle:
                    payload = handle.read()
            except OSError as error:
                raise BunRuntimeError(
                    "cannot read '%s': %s" % (path, error.strerror))
            filename = part.get("filename")
            if not isinstance(filename, str) or filename == "":
                filename = os.path.basename(path)
            content_type = part.get("content_type")
            if not isinstance(content_type, str) or content_type == "":
                content_type = "application/octet-stream"
            body.extend(("--%s\r\n" % boundary).encode("utf-8"))
            body.extend((
                'Content-Disposition: form-data; name="%s"; filename="%s"\r\n'
                % (name, filename)).encode("utf-8"))
            body.extend(("Content-Type: %s\r\n\r\n" % content_type)
                        .encode("utf-8"))
            body.extend(payload)
            body.extend(b"\r\n")
        else:
            value = part.get("value")
            if value is None:
                value = ""
            body.extend(("--%s\r\n" % boundary).encode("utf-8"))
            body.extend((
                'Content-Disposition: form-data; name="%s"\r\n\r\n'
                % name).encode("utf-8"))
            body.extend(str(value).encode("utf-8"))
            body.extend(b"\r\n")
    body.extend(("--%s--\r\n" % boundary).encode("utf-8"))

    header_map = {}
    for key in headers.keys():
        header_map[str(key)] = stringify(headers.get(key))
    header_map["Content-Type"] = "multipart/form-data; boundary=%s" % boundary
    header_map["Content-Length"] = str(len(body))

    import urllib.error
    import urllib.request
    sandbox.check_net_url(url)
    request = urllib.request.Request(
        url, data=bytes(body), headers=header_map, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8", "replace")
            result = BunDict()
            result.set("status", response.status)
            result.set("body", payload)
            return result
    except urllib.error.HTTPError as error:
        payload = error.read().decode("utf-8", "replace")
        result = BunDict()
        result.set("status", error.code)
        result.set("body", payload)
        return result
    except urllib.error.URLError as error:
        raise BunRuntimeError("http_post_multipart() failed: %s" % error.reason)
    except OSError as error:
        raise BunRuntimeError("http_post_multipart() failed: %s" % error)


def _eval(args):
    if len(args) != 1:
        raise BunRuntimeError("eval() expects 1 argument")
    source = args[0]
    if not isinstance(source, str):
        raise BunRuntimeError("eval() expects a string")
    from .checker import Checker
    from .errors import BunError
    from .interpreter import Interpreter
    from .lexer import Lexer
    from .parser import Parser
    base_dir = os.getcwd()
    try:
        tokens = Lexer(source).tokenize()
        program = Parser(tokens).parse()
        Checker().check(program, base_dir=base_dir)
    except BunError as error:
        raise BunRuntimeError("eval() failed: %s" % error.msg)
    interpreter = Interpreter()
    interpreter.run(program, base_dir=base_dir)
    return interpreter.last_value


def _exec(args):
    if not args or len(args) > 2:
        raise BunRuntimeError("exec() expects a list of arguments and an optional timeout")
    if not isinstance(args[0], list):
        raise BunRuntimeError("exec() expects a list of arguments")
    argv = []
    for item in args[0]:
        if not isinstance(item, str):
            raise BunRuntimeError("exec() expects string arguments")
        argv.append(item)
    if not argv:
        raise BunRuntimeError("exec() expects at least one argument")
    sandbox.check_exec()
    timeout = None
    if len(args) == 2:
        seconds = args[1]
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
            raise BunRuntimeError("exec() expects a number of seconds")
        if seconds < 0:
            raise BunRuntimeError("exec() expects a non-negative timeout")
        if seconds > 0:
            timeout = seconds
    try:
        completed = subprocess.run(
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            timeout=timeout)
    except subprocess.TimeoutExpired:
        raise BunRuntimeError("exec() timed out: %s" % argv[0])
    except OSError as error:
        raise BunRuntimeError("exec() failed: %s" % error)
    result = BunDict()
    result.set("status", completed.returncode)
    result.set("stdout", completed.stdout.decode("utf-8", "replace"))
    result.set("stderr", completed.stderr.decode("utf-8", "replace"))
    return result


def _now(args):
    if len(args) != 0:
        raise BunRuntimeError("now() expects no arguments")
    sandbox.check_clock()
    return time.time()


def _sleep(args):
    _one("sleep", args)
    if not isinstance(args[0], (int, float)) or isinstance(args[0], bool):
        raise BunRuntimeError("sleep() expects a number of seconds")
    if args[0] < 0:
        raise BunRuntimeError("sleep() expects a non-negative number")
    time.sleep(args[0])
    return None


def _run_task(function, args, record, group=None):
    tasks.set_current_group(group)
    tasks.set_current_task(record)
    try:
        if isinstance(function.body, dict):
            from .vm import VM
            vm = VM()
            record["result"] = vm.call_function(function, args)
        else:
            from .interpreter import Interpreter
            engine = Interpreter()
            record["result"] = engine.call_function(function, args)
    except BaseException as error:
        record["error"] = error
    finally:
        record["done"] = True


def _spawn(args):
    _one("spawn", args)
    function = args[0]
    if not isinstance(function, BunFunction):
        raise BunRuntimeError("spawn() expects a function")
    record = {"id": tasks.new_task_id(), "done": False, "result": None,
              "error": None, "cancelled": False, "thread": None}
    group = tasks.current_group()
    thread = threading.Thread(
        target=_run_task, args=(function, [], record, group), daemon=True)
    record["thread"] = thread
    tasks.register_task(record)
    thread.start()
    return tasks.task_handle(record)


def _task_record(args, name):
    _one(name, args)
    handle = args[0]
    if not isinstance(handle, BunDict):
        raise BunRuntimeError("%s() expects a task handle" % name)
    if not handle.has("id"):
        raise BunRuntimeError("%s() expects a task handle" % name)
    record = tasks.lookup_task(handle.get("id"))
    if record is None:
        raise BunRuntimeError("%s() received an unknown task" % name)
    return record


def _task_join(args):
    record = _task_record(args, "task_join")
    record["thread"].join()
    if record["error"] is not None:
        raise tasks.as_runtime_error(record["error"])
    return record["result"]


def _task_done(args):
    record = _task_record(args, "task_done")
    return record["done"]


def _cancel(args):
    record = _task_record(args, "cancel")
    record["cancelled"] = True
    return None


def _task_cancelled(args):
    if len(args) == 0:
        record = tasks.current_task()
        return bool(record is not None and record["cancelled"])
    record = _task_record(args, "task_cancelled")
    return bool(record["cancelled"])


def _sandbox_enter(args):
    """Install a capability manifest for the code that follows."""
    _one("sandbox_enter", args)
    manifest = args[0]
    if not isinstance(manifest, BunDict):
        raise BunRuntimeError("sandbox_enter() expects a dict manifest")
    sandbox.enter(manifest)
    return None


def _sandbox_exit(args):
    """Remove the capability manifest that is in force."""
    if len(args) != 0:
        raise BunRuntimeError("sandbox_exit() expects no arguments")
    sandbox.leave()
    return None


_MUTEXES = {}
_MUTEX_LOCK = threading.Lock()
_NEXT_MUTEX = [0]


def _mutex(args):
    if len(args) != 0:
        raise BunRuntimeError("mutex() expects no arguments")
    handle = BunDict()
    with _MUTEX_LOCK:
        mutex_id = _NEXT_MUTEX[0]
        _NEXT_MUTEX[0] += 1
        _MUTEXES[mutex_id] = threading.Lock()
    handle.set("id", mutex_id)
    return handle


def _mutex_lock(args, name):
    _one(name, args)
    handle = args[0]
    if not isinstance(handle, BunDict):
        raise BunRuntimeError("%s() expects a mutex" % name)
    if not handle.has("id"):
        raise BunRuntimeError("%s() expects a mutex" % name)
    mutex_id = handle.get("id")
    if mutex_id not in _MUTEXES:
        raise BunRuntimeError("%s() received an unknown mutex" % name)
    return _MUTEXES[mutex_id]


def _lock(args):
    _mutex_lock(args, "lock").acquire()
    return None


def _unlock(args):
    _mutex_lock(args, "unlock").release()
    return None


def _ffi_load(args):
    _one("ffi_load", args)
    name = args[0]
    if not isinstance(name, str):
        raise BunRuntimeError("ffi_load() expects a module name")
    if name not in _FFI_ALLOWED:
        raise BunRuntimeError(
            "ffi_load() refuses module '%s' (allowed: %s)"
            % (name, ", ".join(sorted(_FFI_ALLOWED))))
    try:
        module = importlib.import_module(name)
    except ImportError as error:
        raise BunRuntimeError("ffi_load() failed: %s" % error)
    result = BunDict()
    for attr in dir(module):
        if attr.startswith("_"):
            continue
        value = getattr(module, attr)
        if callable(value):
            result.set(attr, _ffi_wrap(name, attr, value))
        elif isinstance(value, (int, str, float, bool)):
            result.set(attr, value)
    return result


def _ffi_wrap(module_name, attr, function):
    def call(args):
        try:
            converted = [_to_python(item) for item in args]
            return _to_bun(function(*converted))
        except BunRuntimeError:
            raise
        except Exception as error:
            raise BunRuntimeError(
                "%s.%s failed: %s" % (module_name, attr, error))
    return Builtin("%s.%s" % (module_name, attr), call)


def _list_dir(args):
    _one("list_dir", args)
    if not isinstance(args[0], str):
        raise BunRuntimeError("list_dir() expects a string path")
    sandbox.check_fs(args[0])
    try:
        return os.listdir(args[0])
    except OSError as error:
        raise BunRuntimeError("list_dir() failed: %s" % error)


def _make_dir(args):
    _one("make_dir", args)
    if not isinstance(args[0], str):
        raise BunRuntimeError("make_dir() expects a string path")
    try:
        os.makedirs(args[0], exist_ok=True)
    except OSError as error:
        raise BunRuntimeError(
            "cannot create '%s': %s" % (args[0], error.strerror))
    return None


def _exit(args):
    _one("exit", args)
    code = args[0]
    if not isinstance(code, int) or isinstance(code, bool):
        raise BunRuntimeError("exit() expects an integer code")
    raise SystemExit(code)


# Crypto builtins for MTProto
def _as_bytes(value, name):
    """Normalize a Bun value into raw bytes.

    Byte lists are the canonical byte representation in Bun, so every crypto
    builtin accepts and returns lists of integers in the range 0-255.
    """
    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, list):
        out = bytearray()
        for item in value:
            if not isinstance(item, int) or isinstance(item, bool):
                raise BunRuntimeError("%s expects a list of byte values" % name)
            if item < 0 or item > 255:
                raise BunRuntimeError("%s expects byte values between 0 and 255" % name)
            out.append(item)
        return bytes(out)
    raise BunRuntimeError("%s expects a string or a list of bytes" % name)


def _sha256(args):
    _one("sha256", args)
    data = _as_bytes(args[0], "sha256()")
    import hashlib
    return list(hashlib.sha256(data).digest())


def _sha1(args):
    _one("sha1", args)
    data = _as_bytes(args[0], "sha1()")
    import hashlib
    return list(hashlib.sha1(data).digest())


def _md5(args):
    """Return the MD5 digest of bytes as a string of sixteen hex digits."""
    _one("md5", args)
    data = _as_bytes(args[0], "md5()")
    import hashlib
    return hashlib.md5(data).hexdigest()


def _pbkdf2_sha512(args):
    """Derive a key from a password with PBKDF2 over HMAC-SHA512."""
    if len(args) not in (3, 4):
        raise BunRuntimeError(
            "pbkdf2_sha512() expects three or four arguments, got %d" % len(args))
    password = _as_bytes(args[0], "pbkdf2_sha512()")
    salt = _as_bytes(args[1], "pbkdf2_sha512()")
    rounds = args[2]
    if not isinstance(rounds, int) or isinstance(rounds, bool):
        raise BunRuntimeError("pbkdf2_sha512() expects a number of rounds")
    if rounds < 1:
        raise BunRuntimeError("pbkdf2_sha512() expects at least one round")
    size = 64
    if len(args) == 4:
        size = args[3]
        if not isinstance(size, int) or isinstance(size, bool):
            raise BunRuntimeError("pbkdf2_sha512() expects a size of the key")
        if size < 1 or size > 1024:
            raise BunRuntimeError("pbkdf2_sha512() expects a size between 1 and 1024")
    import hashlib
    return list(hashlib.pbkdf2_hmac("sha512", password, salt, rounds, size))


def _gzip_decompress(args):
    _one("gzip_decompress", args)
    data = _as_bytes(args[0], "gzip_decompress()")
    import zlib
    try:
        return list(zlib.decompress(bytes(data), 47))
    except zlib.error as error:
        raise BunRuntimeError("gzip_decompress() failed: %s" % error)


def _base64_encode(args):
    _one("base64_encode", args)
    data = _as_bytes(args[0], "base64_encode()")
    import base64
    return base64.b64encode(data).decode("ascii")


def _base64_decode(args):
    _one("base64_decode", args)
    if not isinstance(args[0], str):
        raise BunRuntimeError("base64_decode() expects a string")
    import base64
    try:
        return list(base64.b64decode(args[0] + "=" * (-len(args[0]) % 4)))
    except Exception as e:
        raise BunRuntimeError("base64_decode() failed: %s" % e)


def _random_bytes(args):
    _one("random_bytes", args)
    length = args[0]
    if not isinstance(length, int) or isinstance(length, bool) or length < 0:
        raise BunRuntimeError("random_bytes() expects a non-negative integer")
    import secrets
    return list(secrets.token_bytes(length))


def _random(args):
    if len(args) != 0:
        raise BunRuntimeError("random() expects no arguments")
    import random as _random_module
    return _random_module.random()


def _random_int(args):
    _two("random_int", args)
    low = args[0]
    high = args[1]
    for value in (low, high):
        if not isinstance(value, int) or isinstance(value, bool):
            raise BunRuntimeError("random_int() expects integer arguments")
    if low > high:
        raise BunRuntimeError("random_int() expects the low bound to be smaller")
    import random as _random_module
    return _random_module.randint(low, high)


def _aes_ige_encrypt(args):
    _three("aes_ige_encrypt", args)
    data = _as_bytes(args[0], "aes_ige_encrypt()")
    key = _as_bytes(args[1], "aes_ige_encrypt()")
    iv = _as_bytes(args[2], "aes_ige_encrypt()")
    if len(key) != 32:
        raise BunRuntimeError("aes_ige_encrypt() expects a 32 byte key")
    if len(iv) != 32:
        raise BunRuntimeError("aes_ige_encrypt() expects a 32 byte iv")
    if len(data) % 16:
        raise BunRuntimeError("aes_ige_encrypt() expects data with a multiple of 16 bytes")
    from .aes import ige_encrypt
    try:
        return list(ige_encrypt(bytes(data), bytes(key), bytes(iv)))
    except ValueError as error:
        raise BunRuntimeError(str(error))


def _aes_ige_decrypt(args):
    _three("aes_ige_decrypt", args)
    data = _as_bytes(args[0], "aes_ige_decrypt()")
    key = _as_bytes(args[1], "aes_ige_decrypt()")
    iv = _as_bytes(args[2], "aes_ige_decrypt()")
    if len(key) != 32:
        raise BunRuntimeError("aes_ige_decrypt() expects a 32 byte key")
    if len(iv) != 32:
        raise BunRuntimeError("aes_ige_decrypt() expects a 32 byte iv")
    if len(data) % 16:
        raise BunRuntimeError("aes_ige_decrypt() expects data with a multiple of 16 bytes")
    from .aes import ige_decrypt
    try:
        return list(ige_decrypt(bytes(data), bytes(key), bytes(iv)))
    except ValueError as error:
        raise BunRuntimeError(str(error))


def _aes_ctr_crypt(args):
    _three("aes_ctr_crypt", args)
    data = _as_bytes(args[0], "aes_ctr_crypt()")
    key = _as_bytes(args[1], "aes_ctr_crypt()")
    iv = _as_bytes(args[2], "aes_ctr_crypt()")
    if len(key) != 32:
        raise BunRuntimeError("aes_ctr_crypt() expects a 32 byte key")
    if len(iv) != 16:
        raise BunRuntimeError("aes_ctr_crypt() expects a 16 byte iv")
    from .aes import ctr_crypt
    try:
        return list(ctr_crypt(bytes(data), bytes(key), bytes(iv)))
    except ValueError as error:
        raise BunRuntimeError(str(error))


def _rsa_encrypt(args):
    _three("rsa_encrypt", args)
    data = _as_bytes(args[0], "rsa_encrypt()")
    modulus, exponent = args[1], args[2]
    if not isinstance(modulus, str) or not isinstance(exponent, int):
        # modulus is already string
        raise BunRuntimeError("rsa_encrypt() expects modulus as string, exponent as int")
    try:
        n = int(modulus, 16) if modulus.startswith("0x") else int(modulus)
    except ValueError:
        raise BunRuntimeError("rsa_encrypt() expects a hexadecimal modulus")
    if n <= 0 or exponent <= 0:
        raise BunRuntimeError("rsa_encrypt() expects a positive modulus and exponent")
    size = (n.bit_length() + 7) // 8
    if len(data) + 11 > size:
        raise BunRuntimeError("rsa_encrypt() data does not fit into the modulus")
    # PKCS#1 v1.5 padding: a type byte, random filler and a zero separator.
    padding = size - len(data) - 3
    filler = bytearray()
    while len(filler) < padding:
        for byte in os.urandom(padding - len(filler)):
            if byte:
                filler.append(byte)
    block = b"\x00\x02" + bytes(filler) + b"\x00" + bytes(data)
    value = pow(int.from_bytes(block, "big"), exponent, n)
    return list(value.to_bytes(size, "big"))


def _pow_mod(args):
    _three("pow_mod", args)
    base, exp, mod = args[0], args[1], args[2]
    for name, val in [("base", base), ("exp", exp), ("mod", mod)]:
        if not isinstance(val, (int, list, bytes, bytearray)):
            raise BunRuntimeError("pow_mod() expects %s as int or bytes" % name)
    if isinstance(base, list):
        base = int.from_bytes(_as_bytes(base, "pow_mod()"), "big")
    if isinstance(exp, list):
        exp = int.from_bytes(_as_bytes(exp, "pow_mod()"), "big")
    if isinstance(mod, list):
        mod = int.from_bytes(_as_bytes(mod, "pow_mod()"), "big")
    if isinstance(base, (bytes, bytearray)):
        base = int.from_bytes(base, "big")
    if isinstance(exp, (bytes, bytearray)):
        exp = int.from_bytes(exp, "big")
    if isinstance(mod, (bytes, bytearray)):
        mod = int.from_bytes(mod, "big")
    return pow(base, exp, mod)


# Socket builtins for MTProto
def _tcp_connect(args):
    _two("tcp_connect", args)
    host, port = args[0], args[1]
    if not isinstance(host, str) or not isinstance(port, int):
        raise BunRuntimeError("tcp_connect() expects host (str) and port (int)")
    sandbox.check_net(host)
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(30)
    # The small words of a program go out without waiting for the answer of
    # the net, so the other side never waits for them.
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass
    try:
        sock.connect((host, port))
    except Exception as e:
        raise BunRuntimeError(f"tcp_connect() failed: {e}")
    handle = BunDict()
    handle.set("fd", sock.fileno())
    import threading
    if not hasattr(_tcp_connect, "_sockets"):
        _tcp_connect._sockets = {}
        _tcp_connect._lock = threading.Lock()
    with _tcp_connect._lock:
        _tcp_connect._sockets[sock.fileno()] = sock
    return handle


def _tcp_tls_connect(args):
    if len(args) not in (2, 3, 4):
        raise BunRuntimeError("tcp_tls_connect() expects 2 to 4 arguments, got %d" % len(args))
    host, port = args[0], args[1]
    if not isinstance(host, str) or not isinstance(port, int):
        raise BunRuntimeError("tcp_tls_connect() expects host (str) and port (int)")
    sandbox.check_net(host)
    alpn = []
    if len(args) >= 3 and args[2] is not None:
        if not isinstance(args[2], list):
            raise BunRuntimeError("tcp_tls_connect() expects alpn as a list of strings")
        for entry in args[2]:
            if not isinstance(entry, str):
                raise BunRuntimeError("tcp_tls_connect() expects alpn as a list of strings")
            alpn.append(entry)
    sni = None
    if len(args) >= 4 and args[3] is not None:
        if not isinstance(args[3], str):
            raise BunRuntimeError("tcp_tls_connect() expects sni as a string")
        sni = args[3]
    import socket
    import ssl
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(30)
    # The small words of a program go out without waiting for the answer of
    # the net, so the other side never waits for them.
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass
    try:
        sock.connect((host, port))
    except Exception as e:
        raise BunRuntimeError(f"tcp_tls_connect() connect failed: {e}")
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    if alpn:
        try:
            context.set_alpn_protocols(alpn)
        except NotImplementedError:
            pass
    try:
        tls_sock = context.wrap_socket(sock, server_hostname=sni or host)
    except Exception as e:
        raise BunRuntimeError(f"tcp_tls_connect() TLS handshake failed: {e}")
    handle = BunDict()
    handle.set("fd", tls_sock.fileno())
    handle.set("alpn", tls_sock.selected_alpn_protocol())
    import threading
    if not hasattr(_tcp_connect, "_sockets"):
        _tcp_connect._sockets = {}
        _tcp_connect._lock = threading.Lock()
    with _tcp_connect._lock:
        _tcp_connect._sockets[tls_sock.fileno()] = tls_sock
    return handle


def _tcp_listen(args):
    if len(args) not in (1, 2, 3):
        raise BunRuntimeError("tcp_listen() expects 1 to 3 arguments, got %d" % len(args))
    host = args[0] if args[0] is not None else "127.0.0.1"
    port = args[1] if len(args) >= 2 and args[1] is not None else 0
    if not isinstance(host, str) or not isinstance(port, int):
        raise BunRuntimeError("tcp_listen() expects host (str) and port (int)")
    sandbox.check_net(host)
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
        sock.listen(64)
    except Exception as e:
        raise BunRuntimeError(f"tcp_listen() failed: {e}")
    bound_host, bound_port = sock.getsockname()[:2]
    handle = BunDict()
    handle.set("fd", sock.fileno())
    handle.set("host", bound_host)
    handle.set("port", bound_port)
    handle.set("listener", True)
    import threading
    if not hasattr(_tcp_connect, "_sockets"):
        _tcp_connect._sockets = {}
        _tcp_connect._lock = threading.Lock()
    with _tcp_connect._lock:
        _tcp_connect._sockets[sock.fileno()] = sock
    return handle


def _tcp_accept(args):
    if len(args) not in (1, 2):
        raise BunRuntimeError("tcp_accept() expects 1 to 2 arguments, got %d" % len(args))
    handle = args[0]
    timeout = args[1] if len(args) >= 2 and args[1] is not None else 30.0
    if not isinstance(handle, BunDict) or not handle.has("fd"):
        raise BunRuntimeError("tcp_accept() expects a listener handle")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise BunRuntimeError("tcp_accept() expects timeout as a number")
    fd = handle.get("fd")
    if not hasattr(_tcp_connect, "_sockets") or fd not in _tcp_connect._sockets:
        raise BunRuntimeError("tcp_accept() invalid socket")
    listener = _tcp_connect._sockets[fd]
    listener.settimeout(float(timeout))
    try:
        conn, peer = listener.accept()
    except Exception as e:
        raise BunRuntimeError(f"tcp_accept() failed: {e}")
    conn.settimeout(30)
    accepted = BunDict()
    accepted.set("fd", conn.fileno())
    accepted.set("peer", "%s:%d" % peer[:2])
    import threading
    with _tcp_connect._lock:
        _tcp_connect._sockets[conn.fileno()] = conn
    return accepted


def _tcp_close(args):
    _one("tcp_close", args)
    handle = args[0]
    if not isinstance(handle, BunDict) or not handle.has("fd"):
        raise BunRuntimeError("tcp_close() expects a socket handle")
    fd = handle.get("fd")
    if not hasattr(_tcp_connect, "_sockets") or fd not in _tcp_connect._sockets:
        return False
    import threading
    with _tcp_connect._lock:
        sock = _tcp_connect._sockets.pop(fd, None)
    if sock is None:
        return False
    try:
        sock.close()
    except Exception:
        pass
    return True


def _tcp_write(args):
    _two("tcp_write", args)
    handle, data = args[0], args[1]
    if not isinstance(handle, BunDict) or not handle.has("fd"):
        raise BunRuntimeError("tcp_write() expects a socket handle")
    if isinstance(data, list):
        data = bytes(data)
    if not isinstance(data, (bytes, bytearray)):
        raise BunRuntimeError("tcp_write() expects data as bytes")
    fd = handle.get("fd")
    if not hasattr(_tcp_connect, "_sockets") or fd not in _tcp_connect._sockets:
        raise BunRuntimeError("tcp_write() invalid socket")
    sock = _tcp_connect._sockets[fd]
    try:
        sock.sendall(bytes(data))
        return True
    except Exception as e:
        raise BunRuntimeError(f"tcp_write() failed: {e}")


def _tcp_read(args):
    _two("tcp_read", args)
    handle, max_len = args[0], args[1]
    if not isinstance(handle, BunDict) or not handle.has("fd"):
        raise BunRuntimeError("tcp_read() expects a socket handle")
    if not isinstance(max_len, int) or max_len <= 0:
        raise BunRuntimeError("tcp_read() expects max_len as positive int")
    fd = handle.get("fd")
    if not hasattr(_tcp_connect, "_sockets") or fd not in _tcp_connect._sockets:
        raise BunRuntimeError("tcp_read() invalid socket")
    sock = _tcp_connect._sockets[fd]
    try:
        data = sock.recv(max_len)
        return list(data)
    except Exception as e:
        raise BunRuntimeError(f"tcp_read() failed: {e}")


def _tcp_set_timeout(args):
    _two("tcp_set_timeout", args)
    handle, timeout_ms = args[0], args[1]
    if not isinstance(handle, BunDict) or not handle.has("fd"):
        raise BunRuntimeError("tcp_set_timeout() expects a socket handle")
    if not isinstance(timeout_ms, (int, float)) or isinstance(timeout_ms, bool):
        raise BunRuntimeError("tcp_set_timeout() expects a number of milliseconds")
    fd = handle.get("fd")
    if not hasattr(_tcp_connect, "_sockets") or fd not in _tcp_connect._sockets:
        raise BunRuntimeError("tcp_set_timeout() invalid socket")
    sock = _tcp_connect._sockets[fd]
    try:
        sock.settimeout(timeout_ms / 1000.0)
    except Exception as e:
        raise BunRuntimeError(f"tcp_set_timeout() failed: {e}")
    return True


# Big integer builtins
def _bigint_value(value, name):
    from . import bigint
    try:
        return bigint._to_int(value, name)
    except ValueError as error:
        raise BunRuntimeError(str(error))


def _bigint_from_bytes(args):
    _one("bigint_from_bytes", args)
    from . import bigint
    try:
        return bigint.from_bytes(args[0])
    except ValueError as error:
        raise BunRuntimeError(str(error))


def _bigint_to_bytes(args):
    if len(args) not in (1, 2):
        raise BunRuntimeError("bigint_to_bytes() expects 1 or 2 arguments, got %d" % len(args))
    from . import bigint
    size = 0
    if len(args) == 2:
        if not isinstance(args[1], int) or isinstance(args[1], bool) or args[1] < 0:
            raise BunRuntimeError("bigint_to_bytes() expects a non-negative size")
        size = args[1]
    try:
        return bigint.to_bytes(args[0], size)
    except ValueError as error:
        raise BunRuntimeError(str(error))


def _bigint_from_int(args):
    _one("bigint_from_int", args)
    from . import bigint
    try:
        return bigint.from_int(args[0])
    except ValueError as error:
        raise BunRuntimeError(str(error))


def _bigint_to_int(args):
    _one("bigint_to_int", args)
    from . import bigint
    value = _bigint_value(args[0], "bigint_to_int()")
    if value > 0x7FFFFFFFFFFFFFFF:
        raise BunRuntimeError("bigint_to_int() value does not fit into an integer")
    return value


def _bigint_mul(args):
    _two("bigint_mul", args)
    from . import bigint
    try:
        return bigint.multiply(args[0], args[1])
    except ValueError as error:
        raise BunRuntimeError(str(error))


def _bigint_add(args):
    _two("bigint_add", args)
    from . import bigint
    try:
        return bigint.add(args[0], args[1])
    except ValueError as error:
        raise BunRuntimeError(str(error))


def _bigint_sub(args):
    _two("bigint_sub", args)
    from . import bigint
    try:
        return bigint.subtract(args[0], args[1])
    except ValueError as error:
        raise BunRuntimeError(str(error))


def _bigint_mod(args):
    _two("bigint_mod", args)
    from . import bigint
    try:
        return bigint.remainder(args[0], args[1])
    except ValueError as error:
        raise BunRuntimeError(str(error))


def _bigint_div(args):
    _two("bigint_div", args)
    from . import bigint
    try:
        return bigint.divide(args[0], args[1])
    except ValueError as error:
        raise BunRuntimeError(str(error))


def _bigint_gcd(args):
    _two("bigint_gcd", args)
    from . import bigint
    try:
        return bigint.gcd(args[0], args[1])
    except ValueError as error:
        raise BunRuntimeError(str(error))


def _bigint_mul_mod(args):
    _three("bigint_mul_mod", args)
    from . import bigint
    try:
        return bigint.multiply_mod(args[0], args[1], args[2])
    except (ValueError, TypeError) as error:
        raise BunRuntimeError(str(error))


def _bigint_mul_mod_bytes(args):
    _three("bigint_mul_mod_bytes", args)
    from . import bigint
    try:
        return bigint.multiply_mod_bytes(args[0], args[1], args[2])
    except ValueError as error:
        raise BunRuntimeError(str(error))


def _bigint_cmp(args):
    _two("bigint_cmp", args)
    from . import bigint
    try:
        return bigint.compare(args[0], args[1])
    except ValueError as error:
        raise BunRuntimeError(str(error))


def _bigint_pow_mod(args):
    _three("bigint_pow_mod", args)
    from . import bigint
    try:
        return bigint.pow_mod(args[0], args[1], args[2])
    except ValueError as error:
        raise BunRuntimeError(str(error))


def _bigint_factorize(args):
    _one("bigint_factorize", args)
    from . import bigint
    try:
        return bigint.factorize(args[0])
    except ValueError as error:
        raise BunRuntimeError(str(error))


def _utf8_bytes(args):
    _one("utf8_bytes", args)
    if not isinstance(args[0], str):
        raise BunRuntimeError("utf8_bytes() expects a string")
    return list(args[0].encode("utf-8"))


def _double_from_bits(args):
    _one("double_from_bits", args)
    bits = args[0]
    if isinstance(bits, bool) or not isinstance(bits, int):
        raise BunRuntimeError("double_from_bits() expects an int")
    return struct.unpack("<d", struct.pack("<q", bits))[0]


def _double_to_bits(args):
    _one("double_to_bits", args)
    value = args[0]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BunRuntimeError("double_to_bits() expects a number")
    return struct.unpack("<q", struct.pack("<d", float(value)))[0]


def _utf8_string(args):
    _one("utf8_string", args)
    data = _as_bytes(args[0], "utf8_string()")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _three(name, args):
    if len(args) != 3:
        raise BunRuntimeError("%s() expects 3 arguments, got %d" % (name, len(args)))


# HTTP/2 builtins used by the MTProto transport
def _h2_registry():
    if not hasattr(_h2_connect, "_connections"):
        _h2_connect._connections = {}
        _h2_connect._lock = threading.Lock()
        _h2_connect._counter = 0
    return _h2_connect._connections, _h2_connect._lock


def _h2_connect(args):
    if len(args) not in (2, 3, 4):
        raise BunRuntimeError("h2_connect() expects 2 to 4 arguments, got %d" % len(args))
    host, port = args[0], args[1]
    if not isinstance(host, str) or not isinstance(port, int):
        raise BunRuntimeError("h2_connect() expects host (str) and port (int)")
    sandbox.check_net(host)
    sni = None
    if len(args) >= 3 and args[2] is not None:
        if not isinstance(args[2], str):
            raise BunRuntimeError("h2_connect() expects sni as a string")
        sni = args[2]
    alpn = ["h2"]
    if len(args) >= 4 and args[3] is not None:
        if not isinstance(args[3], list):
            raise BunRuntimeError("h2_connect() expects alpn as a list of strings")
        alpn = []
        for entry in args[3]:
            if not isinstance(entry, str):
                raise BunRuntimeError("h2_connect() expects alpn as a list of strings")
            alpn.append(entry)
    from .h2 import H2Connection, connect
    try:
        sock = connect(host, port, sni or host, alpn)
        connection = H2Connection(sock, authority=sni or host)
        connection.handshake()
    except BunRuntimeError:
        raise
    except Exception as e:
        raise BunRuntimeError("h2_connect() failed: %s" % e)
    connections, lock = _h2_registry()
    with lock:
        _h2_connect._counter += 1
        handle_id = _h2_connect._counter
        connections[handle_id] = connection
    handle = BunDict()
    handle.set("id", handle_id)
    handle.set("host", host)
    handle.set("port", port)
    handle.set("sni", sni or host)
    return handle


def _h2_connection(handle):
    if not isinstance(handle, BunDict) or not handle.has("id"):
        raise BunRuntimeError("h2_request() expects a connection handle")
    connections, lock = _h2_registry()
    handle_id = handle.get("id")
    with lock:
        connection = connections.get(handle_id)
    if connection is None:
        raise BunRuntimeError("h2_request() received an unknown connection handle")
    return connection


def _h2_request(args):
    if len(args) not in (2, 3, 4):
        raise BunRuntimeError("h2_request() expects 2 to 4 arguments, got %d" % len(args))
    connection = _h2_connection(args[0])
    method = args[1]
    if not isinstance(method, str):
        raise BunRuntimeError("h2_request() expects method as a string")
    path = "/"
    if len(args) >= 3 and args[2] is not None:
        if not isinstance(args[2], str):
            raise BunRuntimeError("h2_request() expects path as a string")
        path = args[2]
    headers = []
    body = b""
    if len(args) >= 4 and args[3] is not None:
        payload = args[3]
        if isinstance(payload, BunDict):
            if payload.has("headers") or payload.has("body"):
                extra = payload.get("headers")
                if extra is not None:
                    if not isinstance(extra, BunDict):
                        raise BunRuntimeError("h2_request() expects the headers as a dict")
                    for name in extra.keys():
                        headers.append((name, extra.get(name)))
                raw = payload.get("body")
                if raw is not None:
                    body = bytes(_as_bytes(raw, "h2_request()"))
            else:
                for name in payload.keys():
                    headers.append((name, payload.get(name)))
        elif isinstance(payload, list):
            body = bytes(_as_bytes(payload, "h2_request()"))
        else:
            raise BunRuntimeError("h2_request() expects the payload as a dict of headers or a list of bytes")
    try:
        status, response_headers, response_body = connection.request(method, path, headers, body)
    except BunRuntimeError:
        raise
    except Exception as e:
        raise BunRuntimeError("h2_request() failed: %s" % e)
    result = BunDict()
    result.set("status", status)
    header_map = BunDict()
    for name, value in response_headers:
        header_map.set(name, value)
    result.set("headers", header_map)
    result.set("body", list(response_body))
    return result


def _h2_close(args):
    _one("h2_close", args)
    connection = _h2_connection(args[0])
    connections, lock = _h2_registry()
    with lock:
        handle_id = args[0].get("id")
        connections.pop(handle_id, None)
    connection.close()
    return True


def _url_encode(args):
    _one("url_encode", args)
    value = args[0]
    if not isinstance(value, str):
        raise BunRuntimeError("url_encode() expects a string")
    import urllib.parse
    return urllib.parse.quote(value, safe="")


def _url_decode(args):
    _one("url_decode", args)
    value = args[0]
    if not isinstance(value, str):
        raise BunRuntimeError("url_decode() expects a string")
    import urllib.parse
    return urllib.parse.unquote(value)


def _dump(args):
    _one("dump", args)
    return canonical_dump(args[0])


def _secret(args):
    _one("secret", args)
    return BunSecret(args[0])


def _type_of(args):
    _one("type_of", args)
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
    if isinstance(value, list):
        return "array"
    if isinstance(value, BunDict):
        return "dict"
    if isinstance(value, BunSet):
        return "set"
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, BunSecret):
        return "secret"
    if isinstance(value, BunFunction):
        return "fn"
    return "any"


def _starts_with(args):
    _two("starts_with", args)
    text, prefix = args[0], args[1]
    if not isinstance(text, str) or not isinstance(prefix, str):
        raise BunRuntimeError("starts_with() expects two strings")
    return text.startswith(prefix)


def _ends_with(args):
    _two("ends_with", args)
    text, suffix = args[0], args[1]
    if not isinstance(text, str) or not isinstance(suffix, str):
        raise BunRuntimeError("ends_with() expects two strings")
    return text.endswith(suffix)


def _substring(args):
    if len(args) not in (2, 3):
        raise BunRuntimeError("substring() expects 2 or 3 arguments")
    text = args[0]
    if not isinstance(text, str):
        raise BunRuntimeError("substring() expects a string")
    start = args[1]
    if not isinstance(start, int) or isinstance(start, bool):
        raise BunRuntimeError("substring() expects start as int")
    if len(args) == 2:
        return text[start:] if start >= 0 else text[start:]
    end = args[2]
    if not isinstance(end, int) or isinstance(end, bool):
        raise BunRuntimeError("substring() expects end as int")
    return text[start:end]


def _index_of(args):
    _two("index_of", args)
    text, needle = args[0], args[1]
    if not isinstance(text, str) or not isinstance(needle, str):
        raise BunRuntimeError("index_of() expects two strings")
    return text.find(needle)


def _split(args):
    if len(args) not in (2, 3):
        raise BunRuntimeError("split() expects 2 or 3 arguments")
    text, separator = args[0], args[1]
    if not isinstance(text, str) or not isinstance(separator, str):
        raise BunRuntimeError("split() expects two strings")
    if len(args) == 3:
        limit = args[2]
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise BunRuntimeError("split() expects limit as int")
        return text.split(separator, limit - 1) if limit > 0 else []
    return text.split(separator)


def _join(args):
    _two("join", args)
    items, separator = args[0], args[1]
    if not isinstance(items, list):
        raise BunRuntimeError("join() expects a list")
    if not isinstance(separator, str):
        raise BunRuntimeError("join() expects a string separator")
    return separator.join(stringify(item) for item in items)


def _replace(args):
    _three("replace", args)
    text, old, new = args[0], args[1], args[2]
    if not isinstance(text, str) or not isinstance(old, str) or not isinstance(new, str):
        raise BunRuntimeError("replace() expects three strings")
    return text.replace(old, new)


def _trim(args):
    _one("trim", args)
    text = args[0]
    if not isinstance(text, str):
        raise BunRuntimeError("trim() expects a string")
    return text.strip()


def _lower(args):
    _one("lower", args)
    text = args[0]
    if not isinstance(text, str):
        raise BunRuntimeError("lower() expects a string")
    return text.lower()


def _upper(args):
    _one("upper", args)
    text = args[0]
    if not isinstance(text, str):
        raise BunRuntimeError("upper() expects a string")
    return text.upper()


def _one(name, args):
    if len(args) != 1:
        raise BunRuntimeError("%s() expects 1 argument, got %d" % (name, len(args)))


# ---------------------------------------------------------------------------
# The everyday builtins
# ---------------------------------------------------------------------------
#
# The builtins that Python has and a program reaches for on the first
# line: the truth of a value, the size of a collection, the total of a
# collection, the pairs of two collections, the numbers of a collection
# with their index.  They are builtins and not a module, because a
# program that has to import them to count a list is a program with one
# more thing to get wrong.


def _bool(args):
    if len(args) != 1:
        raise BunRuntimeError("bool() expects 1 argument")
    return is_truthy(args[0])


def _abs(args):
    if len(args) != 1:
        raise BunRuntimeError("abs() expects 1 argument")
    value = args[0]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BunRuntimeError("abs() expects a number")
    return abs(value)


def _sum(args):
    if len(args) != 1:
        raise BunRuntimeError("sum() expects 1 argument")
    values = args[0]
    if not isinstance(values, list):
        raise BunRuntimeError("sum() expects a list")
    total = 0
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise BunRuntimeError("sum() expects a list of numbers")
        total = total + value
    return total


def _any(args):
    if len(args) != 1:
        raise BunRuntimeError("any() expects 1 argument")
    values = args[0]
    if not isinstance(values, list):
        raise BunRuntimeError("any() expects a list")
    for value in values:
        if is_truthy(value):
            return True
    return False


def _all(args):
    if len(args) != 1:
        raise BunRuntimeError("all() expects 1 argument")
    values = args[0]
    if not isinstance(values, list):
        raise BunRuntimeError("all() expects a list")
    for value in values:
        if not is_truthy(value):
            return False
    return True


def _min(args):
    if len(args) != 1:
        raise BunRuntimeError("min() expects 1 argument")
    values = args[0]
    if not isinstance(values, list):
        raise BunRuntimeError("min() expects a list")
    if not values:
        raise BunRuntimeError("min() expects a list with at least one value")
    best = values[0]
    for value in values[1:]:
        if _less(value, best):
            best = value
    return best


def _max(args):
    if len(args) != 1:
        raise BunRuntimeError("max() expects 1 argument")
    values = args[0]
    if not isinstance(values, list):
        raise BunRuntimeError("max() expects a list")
    if not values:
        raise BunRuntimeError("max() expects a list with at least one value")
    best = values[0]
    for value in values[1:]:
        if _less(best, value):
            best = value
    return best


def _less(left, right):
    """Whether a value is smaller than another one."""
    if isinstance(left, bool) or isinstance(right, bool):
        raise BunRuntimeError("cannot compare a bool with a number")
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left < right
    if isinstance(left, str) and isinstance(right, str):
        return left < right
    raise BunRuntimeError("cannot compare a %s with a %s"
                          % (type_name(left), type_name(right)))


def _zip(args):
    if len(args) != 2:
        raise BunRuntimeError("zip() expects 2 arguments")
    left, right = args
    if not isinstance(left, list) or not isinstance(right, list):
        raise BunRuntimeError("zip() expects two lists")
    count = len(left)
    if len(right) < count:
        count = len(right)
    pairs = []
    for index in range(count):
        pairs.append([left[index], right[index]])
    return pairs


def _enumerate(args):
    if len(args) != 1:
        raise BunRuntimeError("enumerate() expects 1 argument")
    values = args[0]
    if not isinstance(values, list):
        raise BunRuntimeError("enumerate() expects a list")
    pairs = []
    for index in range(len(values)):
        pairs.append([index, values[index]])
    return pairs


def _sorted(args):
    if len(args) != 1:
        raise BunRuntimeError("sorted() expects 1 argument")
    values = args[0]
    if not isinstance(values, list):
        raise BunRuntimeError("sorted() expects a list")
    # The sort is a merge, so the order of two values that compare equal
    # is the order they had: the sort of a list is stable.
    return _merge_sort(list(values))


def _merge_sort(values):
    count = len(values)
    if count < 2:
        return values
    middle = count // 2
    left = _merge_sort(values[:middle])
    right = _merge_sort(values[middle:])
    merged = []
    i = 0
    j = 0
    while i < len(left) and j < len(right):
        if _less(right[j], left[i]):
            merged.append(right[j])
            j = j + 1
        else:
            merged.append(left[i])
            i = i + 1
    while i < len(left):
        merged.append(left[i])
        i = i + 1
    while j < len(right):
        merged.append(right[j])
        j = j + 1
    return merged


def _reversed(args):
    if len(args) != 1:
        raise BunRuntimeError("reversed() expects 1 argument")
    values = args[0]
    if not isinstance(values, list):
        raise BunRuntimeError("reversed() expects a list")
    out = []
    for index in range(len(values) - 1, -1, -1):
        out.append(values[index])
    return out


def _next(args):
    if len(args) not in (1, 2):
        raise BunRuntimeError("next() expects 1 or 2 arguments")
    value = args[0]
    if not is_generator(value):
        raise BunRuntimeError("next() expects a generator")
    try:
        return value.next_value()
    except BunRuntimeError as error:
        if len(args) == 2 and error.msg == "the generator is over":
            return args[1]
        raise


def _send(args):
    """Send a value into a generator and wait for the next one."""
    if len(args) != 2:
        raise BunRuntimeError("send() expects 2 arguments")
    value = args[0]
    if not is_generator(value):
        raise BunRuntimeError("send() expects a generator")
    return value.send(args[1])


def _two(name, args):
    if len(args) != 2:
        raise BunRuntimeError("%s() expects 2 arguments, got %d" % (name, len(args)))


def _set(args):
    if len(args) > 1:
        raise BunRuntimeError("set() expects 0 or 1 arguments, got %d" % len(args))
    if not args:
        return BunSet()
    values = args[0]
    if not isinstance(values, list):
        raise BunRuntimeError("set() expects a list")
    return BunSet(values)


def _Ok(args):
    if len(args) != 1:
        raise BunRuntimeError("Ok() expects 1 argument")
    result = BunDict()
    result.set("ok", args[0])
    return result


def _Err(args):
    if len(args) != 1:
        raise BunRuntimeError("Err() expects 1 argument")
    result = BunDict()
    result.set("err", args[0])
    return result


def _is_ok(args):
    if len(args) != 1:
        raise BunRuntimeError("is_ok() expects 1 argument")
    value = args[0]
    return isinstance(value, BunDict) and value.has("ok")


def _some(args):
    if len(args) != 1:
        raise BunRuntimeError("some() expects 1 argument")
    option = BunDict()
    option.set("some", args[0])
    return option


def _none(args):
    if args:
        raise BunRuntimeError("none() expects no argument")
    option = BunDict()
    option.set("none", None)
    return option


def _is_some(args):
    if len(args) != 1:
        raise BunRuntimeError("is_some() expects 1 argument")
    value = args[0]
    return isinstance(value, BunDict) and value.has("some")


def _is_none(args):
    if len(args) != 1:
        raise BunRuntimeError("is_none() expects 1 argument")
    value = args[0]
    return (isinstance(value, BunDict)
            and not value.has("some") and value.has("none"))


def _is_err(args):
    if len(args) != 1:
        raise BunRuntimeError("is_err() expects 1 argument")
    value = args[0]
    return isinstance(value, BunDict) and value.has("err") and not value.has("ok")


def register_builtins(env, program_args=None):
    env.define("args", Builtin("args", _make_args(program_args)), False)
    env.define("print", Builtin("print", _print), False)
    env.define("len", Builtin("len", _len), False)
    env.define("range", Builtin("range", _range), False)
    env.define("str", Builtin("str", _str), False)
    env.define("input", Builtin("input", _input), False)
    env.define("int", Builtin("int", _int), False)
    env.define("chr", Builtin("chr", _chr), False)
    env.define("ord", Builtin("ord", _ord), False)
    env.define("float", Builtin("float", _float), False)
    env.define("type_of", Builtin("type_of", _type_of), False)
    env.define("bool", Builtin("bool", _bool), False)
    env.define("abs", Builtin("abs", _abs), False)
    env.define("sum", Builtin("sum", _sum), False)
    env.define("any", Builtin("any", _any), False)
    env.define("all", Builtin("all", _all), False)
    env.define("min", Builtin("min", _min), False)
    env.define("max", Builtin("max", _max), False)
    env.define("zip", Builtin("zip", _zip), False)
    env.define("enumerate", Builtin("enumerate", _enumerate), False)
    env.define("sorted", Builtin("sorted", _sorted), False)
    env.define("reversed", Builtin("reversed", _reversed), False)
    env.define("next", Builtin("next", _next), False)
    env.define("send", Builtin("send", _send), False)
    env.define("set", Builtin("set", _set), False)
    env.define("dump", Builtin("dump", _dump), False)
    env.define("secret", Builtin("secret", _secret), False)
    env.define("url_encode", Builtin("url_encode", _url_encode), False)
    env.define("url_decode", Builtin("url_decode", _url_decode), False)
    env.define("read_file", Builtin("read_file", _read_file), False)
    env.define("write_file", Builtin("write_file", _write_file), False)
    env.define("append_file", Builtin("append_file", _append_file), False)
    env.define("file_exists", Builtin("file_exists", _file_exists), False)
    env.define("getenv", Builtin("getenv", _getenv), False)
    env.define("getenv_or", Builtin("getenv_or", _getenv_or), False)
    env.define("json_parse", Builtin("json_parse", _json_parse), False)
    env.define("json_stringify", Builtin("json_stringify", _json_stringify), False)
    env.define("http_get", Builtin("http_get", _http_get), False)
    env.define("http_post", Builtin("http_post", _http_post), False)
    env.define("http_post_multipart",
               Builtin("http_post_multipart", _http_post_multipart), False)
    env.define("http_get_bytes", Builtin("http_get_bytes", _http_get_bytes), False)
    env.define("write_bytes", Builtin("write_bytes", _write_bytes), False)
    env.define("read_bytes", Builtin("read_bytes", _read_bytes), False)
    env.define("bytes_slice", Builtin("bytes_slice", _bytes_slice), False)
    env.define("bytes_append", Builtin("bytes_append", _bytes_append), False)
    env.define("exec", Builtin("exec", _exec), False)
    env.define("eval", Builtin("eval", _eval), False)
    env.define("now", Builtin("now", _now), False)
    env.define("sleep", Builtin("sleep", _sleep), False)
    env.define("spawn", Builtin("spawn", _spawn), False)
    env.define("task_join", Builtin("task_join", _task_join), False)
    env.define("task_done", Builtin("task_done", _task_done), False)
    env.define("cancel", Builtin("cancel", _cancel), False)
    env.define("task_cancelled", Builtin("task_cancelled", _task_cancelled), False)
    env.define("sandbox_enter", Builtin("sandbox_enter", _sandbox_enter), False)
    env.define("sandbox_exit", Builtin("sandbox_exit", _sandbox_exit), False)
    env.define("mutex", Builtin("mutex", _mutex), False)
    env.define("lock", Builtin("lock", _lock), False)
    env.define("unlock", Builtin("unlock", _unlock), False)
    env.define("ffi_load", Builtin("ffi_load", _ffi_load), False)
    env.define("list_dir", Builtin("list_dir", _list_dir), False)
    env.define("make_dir", Builtin("make_dir", _make_dir), False)
    env.define("exit", Builtin("exit", _exit), False)
    env.define("sha256", Builtin("sha256", _sha256), False)
    env.define("sha1", Builtin("sha1", _sha1), False)
    env.define("md5", Builtin("md5", _md5), False)
    env.define("pbkdf2_sha512", Builtin("pbkdf2_sha512", _pbkdf2_sha512), False)
    env.define("base64_encode", Builtin("base64_encode", _base64_encode), False)
    env.define("gzip_decompress", Builtin("gzip_decompress", _gzip_decompress), False)
    env.define("base64_decode", Builtin("base64_decode", _base64_decode), False)
    env.define("random_bytes", Builtin("random_bytes", _random_bytes), False)
    env.define("random", Builtin("random", _random), False)
    env.define("random_int", Builtin("random_int", _random_int), False)
    env.define("aes_ige_encrypt", Builtin("aes_ige_encrypt", _aes_ige_encrypt), False)
    env.define("aes_ige_decrypt", Builtin("aes_ige_decrypt", _aes_ige_decrypt), False)
    env.define("aes_ctr_crypt", Builtin("aes_ctr_crypt", _aes_ctr_crypt), False)
    env.define("rsa_encrypt", Builtin("rsa_encrypt", _rsa_encrypt), False)
    env.define("pow_mod", Builtin("pow_mod", _pow_mod), False)
    env.define("tcp_connect", Builtin("tcp_connect", _tcp_connect), False)
    env.define("tcp_tls_connect", Builtin("tcp_tls_connect", _tcp_tls_connect), False)
    env.define("tcp_listen", Builtin("tcp_listen", _tcp_listen), False)
    env.define("tcp_accept", Builtin("tcp_accept", _tcp_accept), False)
    env.define("tcp_close", Builtin("tcp_close", _tcp_close), False)
    env.define("tcp_write", Builtin("tcp_write", _tcp_write), False)
    env.define("tcp_read", Builtin("tcp_read", _tcp_read), False)
    env.define("tcp_set_timeout", Builtin("tcp_set_timeout", _tcp_set_timeout), False)
    env.define("h2_connect", Builtin("h2_connect", _h2_connect), False)
    env.define("h2_request", Builtin("h2_request", _h2_request), False)
    env.define("h2_close", Builtin("h2_close", _h2_close), False)
    env.define("bigint_from_bytes", Builtin("bigint_from_bytes", _bigint_from_bytes), False)
    env.define("bigint_to_bytes", Builtin("bigint_to_bytes", _bigint_to_bytes), False)
    env.define("bigint_from_int", Builtin("bigint_from_int", _bigint_from_int), False)
    env.define("bigint_to_int", Builtin("bigint_to_int", _bigint_to_int), False)
    env.define("bigint_mul", Builtin("bigint_mul", _bigint_mul), False)
    env.define("bigint_add", Builtin("bigint_add", _bigint_add), False)
    env.define("bigint_sub", Builtin("bigint_sub", _bigint_sub), False)
    env.define("bigint_mod", Builtin("bigint_mod", _bigint_mod), False)
    env.define("bigint_div", Builtin("bigint_div", _bigint_div), False)
    env.define("bigint_gcd", Builtin("bigint_gcd", _bigint_gcd), False)
    env.define("bigint_mul_mod", Builtin("bigint_mul_mod", _bigint_mul_mod), False)
    env.define("bigint_mul_mod_bytes", Builtin("bigint_mul_mod_bytes", _bigint_mul_mod_bytes), False)
    env.define("bigint_cmp", Builtin("bigint_cmp", _bigint_cmp), False)
    env.define("bigint_pow_mod", Builtin("bigint_pow_mod", _bigint_pow_mod), False)
    env.define("bigint_factorize", Builtin("bigint_factorize", _bigint_factorize), False)
    env.define("double_from_bits", Builtin("double_from_bits", _double_from_bits), False)
    env.define("double_to_bits", Builtin("double_to_bits", _double_to_bits), False)
    env.define("utf8_bytes", Builtin("utf8_bytes", _utf8_bytes), False)
    env.define("utf8_string", Builtin("utf8_string", _utf8_string), False)
    env.define("starts_with", Builtin("starts_with", _starts_with), False)
    env.define("ends_with", Builtin("ends_with", _ends_with), False)
    env.define("substring", Builtin("substring", _substring), False)
    env.define("index_of", Builtin("index_of", _index_of), False)
    env.define("split", Builtin("split", _split), False)
    env.define("join", Builtin("join", _join), False)
    env.define("replace", Builtin("replace", _replace), False)
    env.define("trim", Builtin("trim", _trim), False)
    env.define("lower", Builtin("lower", _lower), False)
    env.define("upper", Builtin("upper", _upper), False)
    env.define("Ok", Builtin("Ok", _Ok), False)
    env.define("Err", Builtin("Err", _Err), False)
    env.define("is_ok", Builtin("is_ok", _is_ok), False)
    env.define("is_err", Builtin("is_err", _is_err), False)
    env.define("some", Builtin("some", _some), False)
    env.define("none", Builtin("none", _none), False)
    env.define("is_some", Builtin("is_some", _is_some), False)
    env.define("is_none", Builtin("is_none", _is_none), False)
