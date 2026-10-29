from bun.cli import main, run_source, run_file


def test_run_source_returns_globals():
    env = run_source("let x = 21\nlet y = x * 2")
    assert env.get("y") == 42


def test_run_source_prints(capsys):
    run_source('print("hi")')
    assert capsys.readouterr().out == "hi\n"


def test_run_file_missing(tmp_path):
    assert run_file(str(tmp_path / "nope.bun")) == 1


def test_run_file_ok(tmp_path):
    program = tmp_path / "ok.bun"
    program.write_text("print(1 + 1)\n")
    assert run_file(str(program)) == 0


def test_run_file_error_exit_code(capsys, tmp_path):
    program = tmp_path / "bad.bun"
    program.write_text("let x = unknown\n")
    assert run_file(str(program)) == 1
    assert "error:" in capsys.readouterr().err


def test_run_file_top_level_return_exit_code(capsys, tmp_path):
    program = tmp_path / "ret.bun"
    program.write_text("return 1\n")
    assert run_file(str(program)) == 1
    out = capsys.readouterr().err
    assert "error: 'return' outside of a function" in out
    assert "Traceback" not in out


def test_type_error_blocks_run(capsys, tmp_path):
    program = tmp_path / "bad.bun"
    program.write_text('let x: int = "s"\nprint("ran")\n')
    assert main([str(program)]) == 1
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "ran" not in captured.out


def test_no_check_flag_runs_unchecked(capsys, tmp_path):
    program = tmp_path / "bad.bun"
    program.write_text('let x: int = "s"\nprint("ran")\n')
    assert main(["--no-check", str(program)]) == 0
    assert "ran" in capsys.readouterr().out


def test_repl_checker_tracks_state(monkeypatch, capsys):
    from bun.cli import repl
    lines = iter(["let x: int = 1", 'x = "oops"', "x"])

    def fake_input(prompt):
        try:
            return next(lines)
        except StopIteration:
            raise EOFError

    monkeypatch.setattr("builtins.input", fake_input)
    assert repl() == 0
    out = capsys.readouterr().out
    assert "cannot assign value of type 'string' to variable 'x' of type 'int'" in out
    assert "1" in out


def test_engine_flag_selects_engine(capsys, tmp_path):
    program = tmp_path / "e.bun"
    program.write_text('print("engine ok")')
    assert main(["--engine", "tree", str(program)]) == 0
    tree_out = capsys.readouterr().out
    assert main(["--engine", "vm", str(program)]) == 0
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out == "engine ok\n"


def test_default_engine_is_vm(capsys, tmp_path):
    program = tmp_path / "e.bun"
    program.write_text('print("default")')
    assert main([str(program)]) == 0
    assert capsys.readouterr().out == "default\n"


def test_invalid_engine_flag_errors(capsys, tmp_path):
    program = tmp_path / "e.bun"
    program.write_text('print("x")')
    assert main(["--engine", "bogus", str(program)]) == 2


def test_front_end_bad_value_exits_2(capsys, tmp_path):
    program = tmp_path / "e.bun"
    program.write_text('print("x")')
    assert main(["--front-end", "bogus", str(program)]) == 2


def test_front_end_bun_requires_vm_engine(capsys, tmp_path):
    program = tmp_path / "e.bun"
    program.write_text('print("x")')
    assert main(["--front-end", "bun", "--engine", "tree", str(program)]) == 2


def test_front_end_bun_requires_a_file(capsys):
    assert main(["--front-end", "bun"]) == 2


def test_front_end_bun_runs_a_program(capsys, tmp_path):
    program = tmp_path / "e.bun"
    program.write_text('let xs = [1, 2, 3]\nprint(xs.len())\n')
    assert main(["--front-end", "bun", str(program)]) == 0
    assert capsys.readouterr().out == "3\n"


def test_api_json_lists_the_builtins(capsys):
    import json

    assert main(["api", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert "print" in data["builtins"]
    assert data["builtins"]["print"] == [[["*"], "null"]]


def test_api_human_output_lists_the_builtins(capsys):
    assert main(["api"]) == 0
    out = capsys.readouterr().out
    assert "print(args: any...) -> null" in out
    assert "len(arg0: any) -> int" in out


def test_doc_prints_a_symbol(capsys):
    assert main(["doc", "print"]) == 0
    out = capsys.readouterr().out
    assert "print(values: any...)" in out
    assert "Print the values" in out


def test_doc_without_a_symbol_lists_the_names(capsys):
    assert main(["doc"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert "print" in out
    assert "secret" in out


def test_doc_json_is_machine_readable(capsys):
    import json

    assert main(["doc", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["print"]["summary"].startswith("Print the values")


def test_doc_unknown_symbol_fails(capsys):
    assert main(["doc", "nope"]) == 1
    assert "no documentation" in capsys.readouterr().err


def test_test_doc_runs_the_examples(capsys):
    assert main(["test", "--doc"]) == 0
    assert "example(s) passed" in capsys.readouterr().out


def test_test_doc_runs_a_single_example(capsys):
    assert main(["test", "--doc", "secret"]) == 0
    assert "1 documentation example(s) passed" in capsys.readouterr().out


def test_test_doc_unknown_symbol_fails(capsys):
    assert main(["test", "--doc", "nope"]) == 1
    assert "no documentation" in capsys.readouterr().err


def test_test_runs_the_golden_corpus(capsys):
    assert main(["test"]) == 0
    assert "golden case(s) passed" in capsys.readouterr().out


def test_test_json_reports_the_cases(capsys):
    import json
    assert main(["test", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["failed"] == 0
    assert report["total"] > 0
    assert report["cases"][0]["passed"] is True


def test_check_passes_on_a_good_file(capsys, tmp_path):
    program = tmp_path / "good.bun"
    program.write_text("let x: int = 1\nprint(x)\n")
    assert main(["check", str(program)]) == 0


def test_check_reports_a_type_error(capsys, tmp_path):
    program = tmp_path / "bad.bun"
    program.write_text("let x: int = \"text\"\n")
    assert main(["check", str(program)]) == 1
    err = capsys.readouterr().err
    assert "cannot assign value of type 'string'" in err


def test_check_json_is_machine_readable(capsys, tmp_path):
    import json

    program = tmp_path / "bad.bun"
    program.write_text("let x: int = \"text\"\n")
    assert main(["check", "--json", str(program)]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is False
    assert len(data["diagnostics"]) == 1
    diagnostic = data["diagnostics"][0]
    assert diagnostic["kind"] == "type"
    assert diagnostic["severity"] == "error"
    assert diagnostic["line"] == 1
    assert "string" in diagnostic["message"]


def test_check_json_of_a_good_file(capsys, tmp_path):
    import json

    program = tmp_path / "good.bun"
    program.write_text("print(1)\n")
    assert main(["check", "--json", str(program)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data == {"ok": True, "diagnostics": []}


def test_check_reports_an_undefined_name(capsys, tmp_path):
    import json

    program = tmp_path / "bad.bun"
    program.write_text("print(nosuchname)\n")
    assert main(["check", "--json", str(program)]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["diagnostics"][0]["message"] == (
        "undefined variable 'nosuchname'")


def test_check_without_a_file_fails(capsys):
    assert main(["check"]) == 2


def test_a_program_can_be_read_from_stdin(capsys, monkeypatch):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO('print("from stdin")\n'))
    assert main(["-"]) == 0
    assert capsys.readouterr().out == "from stdin\n"


def test_a_stdin_program_reports_its_errors(capsys, monkeypatch):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("let x: int = \"text\"\n"))
    assert main(["-"]) == 1
    assert "error:" in capsys.readouterr().err


def test_compile_lists_the_bytecode(capsys, tmp_path):
    program = tmp_path / "prog.bun"
    program.write_text("print(1)\n")
    assert main(["compile", str(program)]) == 0
    out = capsys.readouterr().out
    assert "LOAD_CONST" in out
    assert "HALT" in out


def test_compile_profile_reports_the_hot_instructions(capsys, tmp_path):
    program = tmp_path / "prog.bun"
    program.write_text(
        "var total = 0\n"
        "for i in range(0, 100) {\n"
        "    total = total + i\n"
        "}\n"
        "print(total)\n")
    assert main(["compile", "--profile", str(program)]) == 0
    out = capsys.readouterr().out
    assert "instruction profile:" in out
    assert "BINARY" in out
    assert "%" in out


def test_compile_without_a_file_fails(capsys):
    assert main(["compile"]) == 2


def test_compile_reports_a_type_error(capsys, tmp_path):
    program = tmp_path / "bad.bun"
    program.write_text("let x: int = \"text\"\n")
    assert main(["compile", str(program)]) == 1
    assert "cannot assign value of type 'string'" in capsys.readouterr().err
