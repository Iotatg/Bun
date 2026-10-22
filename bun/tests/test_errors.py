from bun.errors import BunRuntimeError, format_error


def test_format_error_with_location():
    err = BunRuntimeError("boom", line=2, col=3)
    out = format_error(err, "a\nbbb\nc", "f.bun")
    assert "error: boom" in out
    assert "f.bun:2:3" in out
    assert "bbb" in out
    assert "^" in out


def test_format_error_without_location():
    err = BunRuntimeError("boom")
    assert format_error(err, "", "f.bun") == "error: boom"
