"""The tests of the machine surface.

The language is queryable, not just readable: an assistant drives a
session of Bun over JSON-RPC 2.0, one object per line.  The tests of
this file drive the protocol over a pipe and compare the answers.
"""

import io
import json
import os
import subprocess
import sys

import pytest

from bun.rpc import Server, Session

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(lines, session=None):
    """Drive the server with the lines and return the answers."""
    output = io.StringIO()
    server = Server(session=session, input_stream=io.StringIO("\n".join(lines) + "\n"),
                    output_stream=output)
    server.serve()
    answers = []
    for line in output.getvalue().splitlines():
        if line.strip():
            answers.append(json.loads(line))
    return answers


def _request(method, identifier=1, **params):
    return json.dumps({"jsonrpc": "2.0", "id": identifier, "method": method,
                       "params": params})


def test_an_expression_comes_back_as_a_value():
    answers = _run([_request("eval", source="1 + 1")])
    assert answers[0]["result"]["value"] == 2
    assert answers[0]["result"]["type"] == "int"


def test_the_answer_carries_the_text_of_the_value():
    answers = _run([_request("eval", source='"hello"')])
    assert answers[0]["result"]["value"] == "hello"
    assert answers[0]["result"]["printed"] == "hello"


def test_the_session_keeps_its_state():
    session = Session()
    answers = _run([
        _request("eval", 1, source="let x = 41"),
        _request("eval", 2, source="x + 1"),
    ], session=session)
    assert answers[0]["result"]["value"] is None
    assert answers[1]["result"]["value"] == 42


def test_the_names_of_the_session_are_the_names_of_the_program():
    session = Session()
    answers = _run([
        _request("eval", 1, source="let x = 41"),
        _request("eval", 2, source="let y = 2"),
        _request("symbols", 3),
    ], session=session)
    assert answers[2]["result"]["names"] == ["x", "y"]


def test_the_reset_empties_the_session():
    session = Session()
    answers = _run([
        _request("eval", 1, source="let x = 41"),
        _request("reset", 2),
        _request("eval", 3, source="x + 1"),
    ], session=session)
    assert answers[1]["result"]["ok"] is True
    assert answers[2]["error"]["data"]["kind"] == "type"


def test_the_values_of_the_containers():
    answers = _run([
        _request("eval", 1, source="[1, 2, 3]"),
        _request("eval", 2, source='{"a": 1}'),
        _request("eval", 3, source="1.5"),
        _request("eval", 4, source="true"),
        _request("eval", 5, source="null"),
    ])
    assert answers[0]["result"]["value"] == [1, 2, 3]
    assert answers[0]["result"]["type"] == "list"
    assert answers[1]["result"]["value"] == {"a": 1}
    assert answers[1]["result"]["type"] == "dict"
    assert answers[2]["result"]["value"] == 1.5
    assert answers[2]["result"]["type"] == "float"
    assert answers[3]["result"]["value"] is True
    assert answers[4]["result"]["value"] is None


def test_a_secret_is_masked():
    answers = _run([_request("eval", source='secret("x")')])
    assert answers[0]["result"]["value"] == "***"
    assert answers[0]["result"]["type"] == "secret"


def test_a_static_error_is_an_error_of_the_protocol():
    answers = _run([_request("eval", source="1 +")])
    error = answers[0]["error"]
    assert error["code"] == -32000
    assert error["data"]["kind"] == "parse"
    assert error["data"]["line"] == 1


def test_an_undefined_name_is_an_error_of_the_protocol():
    answers = _run([_request("eval", source="nothing_here")])
    error = answers[0]["error"]
    assert error["data"]["kind"] == "type"
    assert "nothing_here" in error["message"]


def test_a_runtime_error_is_an_error_of_the_protocol():
    answers = _run([_request("eval", source="[1][5]")])
    error = answers[0]["error"]
    assert error["data"]["kind"] == "runtime"
    assert "out of range" in error["message"]


def test_a_malformed_line_does_not_kill_the_session():
    answers = _run([
        "{not json",
        _request("eval", 2, source="1 + 1"),
    ])
    assert answers[0]["error"]["code"] == -32700
    assert answers[1]["result"]["value"] == 2


def test_an_unknown_method_is_an_error_of_the_protocol():
    answers = _run([_request("no_such_method")])
    assert answers[0]["error"]["code"] == -32601


def test_a_request_without_a_method_is_an_error_of_the_protocol():
    answers = _run([json.dumps({"jsonrpc": "2.0", "id": 1})])
    assert answers[0]["error"]["code"] == -32600


def test_the_params_need_a_source():
    answers = _run([json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eval",
                                "params": {}})])
    assert answers[0]["error"]["code"] == -32602


def test_the_check_method_reports_a_failure_as_an_error():
    answers = _run([_request("check", source="1 +")])
    assert answers[0]["error"]["data"]["kind"] == "parse"
    answers = _run([_request("check", source="let x = 1")])
    assert answers[0]["result"]["ok"] is True


def test_the_compile_method_returns_the_bytecode():
    answers = _run([_request("compile", source="let x = 1")])
    instructions = answers[0]["result"]["instructions"]
    assert instructions
    assert all("op" in entry for entry in instructions)


def test_the_api_method_returns_the_builtins():
    answers = _run([_request("api")])
    builtins = answers[0]["result"]["builtins"]
    assert "print" in builtins
    assert "len" in builtins


def test_the_docs_method_returns_the_documentation():
    answers = _run([_request("docs", symbol="print")])
    assert answers[0]["result"]["signature"].startswith("print")
    answers = _run([_request("docs")])
    assert "print" in answers[0]["result"]["symbols"]


def test_the_shutdown_ends_the_session():
    output = io.StringIO()
    server = Server(input_stream=io.StringIO(_request("shutdown") + "\n"),
                    output_stream=output)
    assert server.serve() == 0
    answers = [json.loads(line) for line in output.getvalue().splitlines() if line]
    assert answers[0]["result"]["ok"] is True


def test_the_command_speaks_the_protocol():
    """The command over a pipe, the way an assistant uses it."""
    lines = [
        _request("eval", 1, source="1 + 1"),
        _request("shutdown", 2),
    ]
    result = subprocess.run(
        [sys.executable, "-m", "bun", "repl", "--json"],
        input="\n".join(lines) + "\n", capture_output=True, text=True,
        cwd=ROOT)
    assert result.returncode == 0
    answers = [json.loads(line) for line in result.stdout.splitlines() if line]
    assert answers[0]["result"]["value"] == 2
    assert answers[1]["result"]["ok"] is True


def test_the_answer_of_a_notification_has_no_id():
    """A request without an id is a notification."""
    answers = _run([json.dumps({"jsonrpc": "2.0", "method": "eval",
                                "params": {"source": "1"}})])
    assert "id" not in answers[0] or answers[0]["id"] is None
