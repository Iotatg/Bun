import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from bun.cli import main, run_source
from bun.errors import BunError


def run(tmp_path, source, args=None):
    path = tmp_path / "prog.bun"
    path.write_text(source)
    code = main([str(path)] + list(args or []))
    assert code == 0
    return code


def test_json_roundtrip(capsys):
    run_source('let d = json_parse("{\\"a\\": 1, \\"b\\": [true, null]}")\n'
               'print(str(d["a"]) + " " + str(len(d["b"])))')
    assert capsys.readouterr().out == "1 2\n"


def test_json_stringify_is_deterministic(capsys):
    run_source('print(json_stringify({"x": 1, "y": [1, 2]}))')
    text = capsys.readouterr().out.strip()
    assert json.loads(text) == {"x": 1, "y": [1, 2]}


def test_getenv_or_default(capsys, monkeypatch):
    monkeypatch.delenv("ANKITA_MISSING", raising=False)
    run_source('print(getenv_or("ANKITA_MISSING", "fallback"))')
    assert capsys.readouterr().out == "fallback\n"


def test_getenv_returns_null(capsys, monkeypatch):
    monkeypatch.delenv("ANKITA_MISSING", raising=False)
    run_source('let v = getenv("ANKITA_MISSING")\nprint(str(v))')
    assert capsys.readouterr().out == "null\n"


def test_exec_captures_stdout(capsys):
    run_source('let r = exec(["echo", "ankita"])\nprint(str(r["status"]))\n'
               'print(r["stdout"].trim())')
    assert capsys.readouterr().out == "0\nankita\n"


def test_exec_with_timeout(capsys):
    run_source('let r = exec(["echo", "quick"], 30)\nprint(str(r["status"]))')
    assert capsys.readouterr().out == "0\n"


def test_exec_timeout_stops_a_slow_command(capsys):
    with pytest.raises(BunError) as error:
        run_source('exec(["sleep", "5"], 1)')
    assert "timed out" in str(error.value)


def test_exec_rejects_a_negative_timeout(capsys):
    with pytest.raises(BunError) as error:
        run_source('exec(["echo", "hi"], -1)')
    assert "non-negative" in str(error.value)


def test_args_builtin(capsys):
    run_source('let a = args()\nprint(a.join("-"))', program_args=["one", "two"])
    assert capsys.readouterr().out == "one-two\n"


def test_spawn_and_join(capsys):
    run_source("let t = spawn(fn() {\n    sleep(0.02)\n    return 21 * 2\n})\n"
               "print(str(task_join(t)))")
    assert capsys.readouterr().out == "42\n"


def test_task_done_flag(capsys):
    run_source("let t = spawn(fn() {\n    sleep(0.05)\n    return 1\n})\n"
               "let first = task_done(t)\nlet value = task_join(t)\n"
               'print(str(first) + " " + str(value))')
    assert capsys.readouterr().out == "false 1\n"


def test_mutex_roundtrip(capsys):
    run_source('let m = mutex()\nlock(m)\nunlock(m)\nprint("ok")')
    assert capsys.readouterr().out == "ok\n"


def test_ffi_load_math(capsys):
    run_source('let m = ffi_load("math")\n'
               'print(str(m.get("sqrt")(81)))\n'
               'print(str(m.get("floor")(2.9)))')
    assert capsys.readouterr().out == "9.0\n2\n"


def test_ffi_load_refuses_unknown_module(capsys, tmp_path):
    path = tmp_path / "ffi.bun"
    path.write_text('let m = ffi_load("os")\n')
    assert main([str(path)]) == 1
    assert "refuses module" in capsys.readouterr().err


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length)
        body = b'{"len": ' + str(len(payload)).encode() + b"}"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:%d" % httpd.server_address[1]
    httpd.shutdown()


def test_http_get(capsys, server):
    run_source('let r = http_get("%s/x", {}, 5)\n'
               'print(str(r["status"]))\n'
               'print(r["body"])' % server)
    out = capsys.readouterr().out
    assert out == '200\n{"ok": true}\n'


def test_http_post(capsys, server):
    run_source('let r = http_post("%s/x", {}, "abcd", 5)\n'
               'print(r["body"])' % server)
    assert capsys.readouterr().out == '{"len": 4}\n'


def test_http_post_multipart(capsys, server, tmp_path):
    """A multipart body carries the fields and the files."""
    payload = tmp_path / "track.ogg"
    payload.write_bytes(b"\x00\x01\x02\xff")
    run_source(
        'let r = http_post_multipart("%s/x", {}, ['
        '{ "name": "chat_id", "value": "42" },'
        '{ "name": "voice", "path": "%s", "filename": "track.ogg",'
        ' "content_type": "audio/ogg" }'
        '], 5)\n'
        'print(str(r["status"]))' % (server, payload))
    assert capsys.readouterr().out == "200\n"


def test_the_multipart_body_holds_the_file(server, tmp_path):
    """The body of the request holds the bytes of the file."""
    payload = tmp_path / "track.ogg"
    payload.write_bytes(b"\x00\x01\x02\xff")
    received = {}

    class Recorder(_Handler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            received["body"] = self.rfile.read(length)
            received["type"] = self.headers.get("Content-Type", "")
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Recorder)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        url = "http://127.0.0.1:%d" % httpd.server_address[1]
        run_source(
            'http_post_multipart("%s/x", {}, ['
            '{ "name": "chat_id", "value": "42" },'
            '{ "name": "voice", "path": "%s" }'
            '], 5)' % (url, payload))
    finally:
        httpd.shutdown()
    body = received["body"]
    assert received["type"].startswith("multipart/form-data; boundary=")
    assert b'name="chat_id"' in body
    assert b"42" in body
    assert b'name="voice"; filename="track.ogg"' in body
    assert b"\x00\x01\x02\xff" in body


def test_list_dir_and_make_dir(capsys, tmp_path):
    target = tmp_path / "made"
    run_source('make_dir("%s")\nlet names = list_dir("%s")\n'
               'print(str(len(names)))' % (target, tmp_path))
    assert capsys.readouterr().out == "1\n"
    assert os.path.isdir(str(target))
