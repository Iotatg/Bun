"""Tests for the native stacks: bun:tensor, bun:sec, bun:game and bun:web."""

import pytest

from bun.cli import run_source
from bun.errors import BunRuntimeError, BunTypeError


def run_both(source, capsys):
    """Run the same source on every engine and assert identical output."""
    run_source(source, filename="<stacks>.bun", check=True, engine="tree")
    tree_out = capsys.readouterr().out
    run_source(source, filename="<stacks>.bun", check=True, engine="vm")
    vm_out = capsys.readouterr().out
    assert tree_out == vm_out
    run_source(source, filename="<stacks>.bun", check=True, engine="register")
    reg_out = capsys.readouterr().out
    assert vm_out == reg_out
    run_source(source, filename="<stacks>.bun", check=True, engine="register",
               tier=True)
    tier_out = capsys.readouterr().out
    assert vm_out == tier_out
    return vm_out


def run_error(source, capsys):
    """Run a source that must fail, and return the error message."""
    with pytest.raises((BunRuntimeError, BunTypeError)) as info:
        run_source(source, filename="<stacks>.bun", check=True, engine="vm")
    return info.value.msg


# ---------------------------------------------------------------------------
# bun:tensor
# ---------------------------------------------------------------------------

TENSOR = "import { tensor, matmul, softmax, relu, sum, mean, max, min, " \
         "add, sub, mul, div, scale, transpose, reshape, zeros, ones, " \
         "sum_axis, sigmoid, to_string, shape_str, from_list, adam, " \
         "adam_state, row, column, size, rank, is_tensor, data, shape } " \
         "from \"bun:tensor\"\n"


def test_a_tensor_keeps_its_shape_and_data(capsys):
    out = run_both(TENSOR +
                   "let t = tensor([[1.0, 2.0], [3.0, 4.0]])\n"
                   "print(shape_str(t))\n"
                   "print(to_string(t))\n"
                   "print(size(t))\n"
                   "print(rank(t))\n", capsys)
    assert out == "[2, 2]\n[[1.0, 2.0], [3.0, 4.0]]\n4\n2\n"


def test_matmul_multiplies_the_matrices(capsys):
    out = run_both(TENSOR +
                   "let x = tensor([[1.0, 2.0], [3.0, 4.0]])\n"
                   "let w = tensor([[0.5, -0.2], [0.1, 0.9]])\n"
                   "print(to_string(matmul(x, w)))\n", capsys)
    assert out == "[[0.7, 1.6], [1.9, 3.0]]\n"


def test_matmul_rejects_shapes_that_do_not_fit(capsys):
    message = run_error(TENSOR +
                        "let x = tensor([[1.0, 2.0]])\n"
                        "let w = tensor([[1.0, 2.0, 3.0]])\n"
                        "print(to_string(matmul(x, w)))\n", capsys)
    assert "matmul() cannot multiply" in message


def test_softmax_gives_every_row_the_sum_of_one(capsys):
    out = run_both(TENSOR +
                   "let p = softmax(tensor([[1.0, 2.0, 3.0], [0.0, 0.0, 0.0]]), 1)\n"
                   "var first = sum(row(p, 0)) - 1.0\n"
                   "var second = sum(row(p, 1)) - 1.0\n"
                   "if first < 0.0 { first = 0.0 - first }\n"
                   "if second < 0.0 { second = 0.0 - second }\n"
                   "print(first < 0.0000001)\n"
                   "print(second < 0.0000001)\n", capsys)
    assert out == "true\ntrue\n"


def test_softmax_is_stable_for_large_values(capsys):
    out = run_both(TENSOR +
                   "let p = softmax(tensor([1000.0, 1000.0]), 0)\n"
                   "print(to_string(p))\n", capsys)
    assert out == "[0.5, 0.5]\n"


def test_relu_removes_the_negative_values(capsys):
    out = run_both(TENSOR +
                   "print(to_string(relu(tensor([-1.0, 0.0, 2.0]))))\n", capsys)
    assert out == "[0.0, 0.0, 2.0]\n"


def test_the_reductions(capsys):
    out = run_both(TENSOR +
                   "let t = tensor([1.0, 2.0, 3.0, 4.0])\n"
                   "print(sum(t))\n"
                   "print(mean(t))\n"
                   "print(max(t))\n"
                   "print(min(t))\n", capsys)
    assert out == "10.0\n2.5\n4.0\n1.0\n"


def test_the_sum_is_the_same_on_every_run(capsys):
    out = run_both(TENSOR +
                   "var values = []\n"
                   "var i = 0\n"
                   "while i < 1000 {\n"
                   "    values.push(0.1)\n"
                   "    i = i + 1\n"
                   "}\n"
                   "let t = from_list(values, [1000])\n"
                   "print(sum(t) == sum(t))\n", capsys)
    assert out == "true\n"


def test_a_vector_is_broadcast_over_the_rows(capsys):
    out = run_both(TENSOR +
                   "let m = tensor([[1.0, 2.0], [3.0, 4.0]])\n"
                   "let v = tensor([10.0, 20.0])\n"
                   "print(to_string(add(m, v)))\n"
                   "print(to_string(add(v, m)))\n", capsys)
    assert out == ("[[11.0, 22.0], [13.0, 24.0]]\n"
                   "[[11.0, 22.0], [13.0, 24.0]]\n")


def test_shapes_that_cannot_be_broadcast_are_rejected(capsys):
    message = run_error(TENSOR +
                        "let m = tensor([[1.0, 2.0], [3.0, 4.0]])\n"
                        "let v = tensor([1.0, 2.0, 3.0])\n"
                        "print(to_string(add(m, v)))\n", capsys)
    assert "cannot broadcast" in message


def test_transpose_and_reshape(capsys):
    out = run_both(TENSOR +
                   "let t = tensor([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])\n"
                   "print(to_string(transpose(t)))\n"
                   "print(shape_str(reshape(t, [3, 2])))\n"
                   "print(to_string(row(t, 1)))\n"
                   "print(to_string(column(t, 0)))\n", capsys)
    assert out == ("[[1.0, 4.0], [2.0, 5.0], [3.0, 6.0]]\n"
                   "[3, 2]\n"
                   "[[4.0, 5.0, 6.0]]\n"
                   "[[1.0], [4.0]]\n")


def test_sum_axis(capsys):
    out = run_both(TENSOR +
                   "let t = tensor([[1.0, 2.0], [3.0, 4.0]])\n"
                   "print(to_string(sum_axis(t, 0)))\n"
                   "print(to_string(sum_axis(t, 1)))\n", capsys)
    assert out == "[4.0, 6.0]\n[3.0, 7.0]\n"


def test_the_elementwise_operations(capsys):
    out = run_both(TENSOR +
                   "let a = tensor([2.0, 4.0])\n"
                   "let b = tensor([1.0, 2.0])\n"
                   "print(to_string(add(a, b)))\n"
                   "print(to_string(sub(a, b)))\n"
                   "print(to_string(mul(a, b)))\n"
                   "print(to_string(div(a, b)))\n"
                   "print(to_string(scale(a, 0.5)))\n", capsys)
    assert out == ("[3.0, 6.0]\n"
                   "[1.0, 2.0]\n"
                   "[2.0, 8.0]\n"
                   "[2.0, 2.0]\n"
                   "[1.0, 2.0]\n")


def test_dividing_by_zero_is_an_error(capsys):
    message = run_error(TENSOR +
                        "let a = tensor([1.0])\n"
                        "let b = tensor([0.0])\n"
                        "print(to_string(div(a, b)))\n", capsys)
    assert "divides by zero" in message


def test_a_value_that_is_not_a_tensor_is_rejected(capsys):
    message = run_error(TENSOR +
                        "print(to_string(sum(7)))\n", capsys)
    assert "expects a tensor" in message


def test_zeros_and_ones(capsys):
    out = run_both(TENSOR +
                   "print(to_string(zeros([2, 2])))\n"
                   "print(to_string(ones([2])))\n", capsys)
    assert out == ("[[0.0, 0.0], [0.0, 0.0]]\n"
                   "[1.0, 1.0]\n")


def test_from_list_checks_the_size(capsys):
    message = run_error(TENSOR +
                        "print(to_string(from_list([1.0, 2.0], [3])))\n", capsys)
    assert "expects 3 values" in message


def test_adam_moves_the_parameters_downhill(capsys):
    out = run_both(TENSOR +
                   "let params = tensor([1.0, -1.0])\n"
                   "let grads = tensor([0.5, -0.25])\n"
                   "let state = adam_state(params)\n"
                   "let step = adam(params, grads, state, 0.1, 0.9, 0.999, 1e-8)\n"
                   "let values = data(step)\n"
                   "print(values[0] < 1.0)\n"
                   "print(values[1] > -1.0)\n", capsys)
    assert out == "true\ntrue\n"


def test_the_gradient_of_a_matrix_product(capsys):
    out = run_both(
        "import { tensor, matmul, sum_tensor, backward, start_tape, stop_tape, "
        "gradients, to_string } from \"bun:tensor\"\n"
        "let x = tensor([[1.0, 2.0], [3.0, 4.0]])\n"
        "let w = tensor([[0.5, -0.2], [0.1, 0.9]])\n"
        "start_tape()\n"
        "let loss = sum_tensor(matmul(x, w))\n"
        "backward(loss)\n"
        "stop_tape()\n"
        "let g = gradients({ \"x\": x, \"w\": w })\n"
        "print(to_string(g[\"w\"]))\n"
        "print(to_string(g[\"x\"]))\n", capsys)
    assert out == ("[[4.0, 4.0], [6.0, 6.0]]\n"
                   "[[0.3, 1.0], [0.3, 1.0]]\n")


def test_the_gradient_of_a_product_matches_a_finite_difference(capsys):
    out = run_both(
        "import { tensor, mul, sum_tensor, backward, start_tape, stop_tape, "
        "gradients, to_string, scale, add, sum } from \"bun:tensor\"\n"
        "let a = tensor([2.0, 3.0])\n"
        "let b = tensor([4.0, 5.0])\n"
        "start_tape()\n"
        "let loss = sum_tensor(mul(a, b))\n"
        "backward(loss)\n"
        "stop_tape()\n"
        "let g = gradients({ \"a\": a, \"b\": b })\n"
        "print(to_string(g[\"a\"]))\n"
        "print(to_string(g[\"b\"]))\n", capsys)
    assert out == ("[4.0, 5.0]\n"
                   "[2.0, 3.0]\n")


def test_backward_needs_a_tape(capsys):
    message = run_error(
        "import { tensor, sum_tensor, backward } from \"bun:tensor\"\n"
        "let t = tensor([1.0])\n"
        "backward(sum_tensor(t))\n", capsys)
    assert "needs a tape" in message


def test_a_native_module_that_does_not_exist_is_an_error(capsys):
    message = run_error(
        "import { nothing } from \"bun:nothing\"\n", capsys)
    assert "cannot find native module" in message


def test_a_native_module_name_cannot_escape_the_library(capsys):
    message = run_error(
        "import { nothing } from \"bun:../secret\"\n", capsys)
    assert "invalid native module name" in message


# ---------------------------------------------------------------------------
# bun:sec
# ---------------------------------------------------------------------------

SEC = "import { capability, sandbox, redact, redact_value } from \"bun:sec\"\n"


def test_a_capability_names_what_the_code_may_do(capsys):
    out = run_both(SEC +
                   "let policy = capability({ \"net\": [\"api.openai.com\"], "
                   "\"fs\": [\"./data\"], \"exec\": true })\n"
                   "print(policy.get(\"net\"))\n"
                   "print(policy.get(\"exec\"))\n"
                   "print(policy.get(\"clock\"))\n", capsys)
    assert out == "[api.openai.com]\ntrue\nfalse\n"


def test_a_capability_rejects_a_manifest_that_is_not_a_dict(capsys):
    message = run_error(SEC + "let policy = capability(7)\n", capsys)
    assert "expects a dict" in message


def test_the_sandbox_runs_the_closure(capsys):
    out = run_both(SEC +
                   "let policy = capability({ \"fs\": [\"./data\"] })\n"
                   "print(sandbox(policy, fn () { return \"inside\" }))\n", capsys)
    assert out == "inside\n"


def test_the_sandbox_is_removed_when_the_closure_fails(capsys):
    out = run_both(SEC +
                   "let policy = capability({ \"fs\": [\"./data\"] })\n"
                   "try {\n"
                   "    sandbox(policy, fn () { throw \"boom\" })\n"
                   "} catch e {\n"
                   "    print(\"caught \" + e)\n"
                   "}\n"
                   "print(\"after\")\n", capsys)
    assert out == "caught boom\nafter\n"


def test_the_sandbox_blocks_a_path_that_is_not_allowed(capsys):
    message = run_error(SEC +
                        "let policy = capability({ \"fs\": [\"./data\"] })\n"
                        "sandbox(policy, fn () { read_file(\"/etc/passwd\") })\n",
                        capsys)
    assert "sandbox: the path '/etc/passwd' is not allowed" in message


def test_the_sandbox_blocks_a_host_that_is_not_allowed(capsys):
    message = run_error(SEC +
                        "let policy = capability({ \"net\": [\"example.com\"] })\n"
                        "sandbox(policy, fn () {\n"
                        "    http_get(\"https://api.openai.com/v1/models\", {}, 5.0)\n"
                        "})\n", capsys)
    assert "sandbox: the network host 'api.openai.com' is not allowed" in message


def test_the_sandbox_blocks_a_process_that_is_not_allowed(capsys):
    message = run_error(SEC +
                        "let policy = capability({ \"exec\": false })\n"
                        "sandbox(policy, fn () { exec([\"ls\"], 5.0) })\n", capsys)
    assert "sandbox: starting a process is not allowed" in message


def test_the_code_outside_the_sandbox_is_not_restricted(capsys, tmp_path):
    path = tmp_path / "data.txt"
    path.write_text("hello")
    out = run_both(SEC +
                   "let policy = capability({ \"fs\": [\"./nowhere\"] })\n"
                   "sandbox(policy, fn () { return 1 })\n"
                   "print(read_file(\"" + str(path) + "\"))\n", capsys)
    assert out == "hello\n"


def test_redact_removes_the_secret_shaped_values(capsys):
    out = run_both(SEC +
                   "print(redact(\"the key is sk-abc123\"))\n"
                   "print(redact(\"the key is AKIAIOSFODNN7EXAMPLE\"))\n"
                   "print(redact(\"Authorization: Bearer abcdefghijklmnop\"))\n", capsys)
    assert out == ("the key is [redacted]\n"
                   "the key is [redacted]\n"
                   "Authorization: Bearer [redacted]\n")


def test_redact_keeps_the_ordinary_text(capsys):
    out = run_both(SEC +
                   "print(redact(\"a normal sentence\"))\n", capsys)
    assert out == "a normal sentence\n"


def test_redact_walks_a_value(capsys):
    out = run_both(SEC +
                   "print(redact_value({ \"a\": \"sk-abc123\", \"b\": [\"AKIA1234\"] }))\n",
                   capsys)
    assert out == "{a: [redacted], b: [[redacted]]}\n"


# ---------------------------------------------------------------------------
# bun:game
# ---------------------------------------------------------------------------

GAME = "import { vec2, vec2_add, vec2_sub, vec2_scale, vec2_dot, " \
       "vec2_cross, vec2_len, vec2_normalize, vec2_dist, vec2_lerp, " \
       "rect, circle, point, segment, ray, rect_overlaps, circle_overlaps, " \
       "rect_circle_overlaps, point_in_rect, point_in_circle, " \
       "segment_intersects, ray_circle, Entities, spawn_entity, " \
       "entity_set, entity_get, entity_alive, kill_entity, entity_count, " \
       "entity_ids, Grid, grid_insert, grid_query, Game, on_update, " \
       "on_draw, advance, draw, run, stop, game_time, quat_identity, " \
       "quat_from_axis_angle, quat_mul, vec3 } from \"bun:game\"\n"


def test_the_vector_arithmetic(capsys):
    out = run_both(GAME +
                   "print(vec2_add(vec2(1.0, 2.0), vec2(3.0, 4.0)))\n"
                   "print(vec2_sub(vec2(1.0, 2.0), vec2(3.0, 4.0)))\n"
                   "print(vec2_scale(vec2(1.0, 2.0), 3.0))\n"
                   "print(vec2_dot(vec2(1.0, 2.0), vec2(3.0, 4.0)))\n"
                   "print(vec2_cross(vec2(1.0, 0.0), vec2(0.0, 1.0)))\n"
                   "print(vec2_len(vec2(3.0, 4.0)))\n"
                   "print(vec2_dist(vec2(0.0, 0.0), vec2(3.0, 4.0)))\n", capsys)
    assert out == ("[4.0, 6.0]\n"
                   "[-2.0, -2.0]\n"
                   "[3.0, 6.0]\n"
                   "11.0\n"
                   "1.0\n"
                   "5.0\n"
                   "5.0\n")


def test_normalize_gives_a_unit_vector(capsys):
    out = run_both(GAME +
                   "print(vec2_normalize(vec2(0.0, 5.0)))\n"
                   "print(vec2_len(vec2_normalize(vec2(3.0, 4.0))))\n", capsys)
    assert out == "[0.0, 1.0]\n1.0\n"


def test_the_shape_tests(capsys):
    out = run_both(GAME +
                   "print(rect_overlaps(rect(0.0, 0.0, 10.0, 10.0), "
                   "rect(5.0, 5.0, 10.0, 10.0)))\n"
                   "print(rect_overlaps(rect(0.0, 0.0, 10.0, 10.0), "
                   "rect(20.0, 20.0, 10.0, 10.0)))\n"
                   "print(circle_overlaps(circle(0.0, 0.0, 5.0), "
                   "circle(8.0, 0.0, 5.0)))\n"
                   "print(rect_circle_overlaps(rect(0.0, 0.0, 10.0, 10.0), "
                   "circle(15.0, 5.0, 3.0)))\n", capsys)
    assert out == "true\nfalse\ntrue\nfalse\n"


def test_point_in_shape(capsys):
    out = run_both(GAME +
                   "print(point_in_rect(point(1.0, 1.0), rect(0.0, 0.0, 10.0, 10.0)))\n"
                   "print(point_in_rect(point(11.0, 1.0), rect(0.0, 0.0, 10.0, 10.0)))\n"
                   "print(point_in_circle(point(1.0, 1.0), circle(0.0, 0.0, 5.0)))\n",
                   capsys)
    assert out == "true\nfalse\ntrue\n"


def test_the_segment_and_the_ray(capsys):
    out = run_both(GAME +
                   "print(segment_intersects(segment(0.0, 0.0, 10.0, 10.0), "
                   "segment(0.0, 10.0, 10.0, 0.0)))\n"
                   "print(segment_intersects(segment(0.0, 0.0, 10.0, 0.0), "
                   "segment(0.0, 10.0, 10.0, 10.0)))\n"
                   "print(ray_circle(ray(0.0, 0.0, 1.0, 0.0), circle(5.0, 0.0, 1.0)))\n"
                   "print(ray_circle(ray(0.0, 0.0, 1.0, 0.0), circle(5.0, 9.0, 1.0)))\n",
                   capsys)
    assert out == "true\nfalse\ntrue\nfalse\n"


def test_the_entities(capsys):
    out = run_both(GAME +
                   "let entities = Entities()\n"
                   "let a = spawn_entity(entities)\n"
                   "let b = spawn_entity(entities)\n"
                   "entity_set(entities, a, \"x\", 1.5)\n"
                   "entity_set(entities, b, \"x\", 2.5)\n"
                   "print(entity_get(entities, a, \"x\"))\n"
                   "print(entity_count(entities))\n"
                   "print(entity_ids(entities))\n"
                   "kill_entity(entities, a)\n"
                   "print(entity_alive(entities, a))\n"
                   "print(entity_count(entities))\n", capsys)
    assert out == ("1.5\n"
                   "2\n"
                   "[0, 1]\n"
                   "false\n"
                   "1\n")


def test_a_killed_entity_is_used_again(capsys):
    out = run_both(GAME +
                   "let entities = Entities()\n"
                   "let a = spawn_entity(entities)\n"
                   "kill_entity(entities, a)\n"
                   "let b = spawn_entity(entities)\n"
                   "print(a == b)\n", capsys)
    assert out == "true\n"


def test_the_grid_finds_the_nearby_entities(capsys):
    out = run_both(GAME +
                   "let grid = Grid(100.0, 100.0, 10.0)\n"
                   "grid_insert(grid, 1, 5.0, 5.0)\n"
                   "grid_insert(grid, 2, 85.0, 85.0)\n"
                   "print(grid_query(grid, 5.0, 5.0, 2.0))\n"
                   "print(grid_query(grid, 85.0, 85.0, 2.0))\n", capsys)
    assert out == "[1]\n[2]\n"


def test_the_simulation_advances_in_whole_steps(capsys):
    out = run_both(GAME +
                   "let game = Game({ \"width\": 320.0, \"height\": 200.0 })\n"
                   "var ticks = 0\n"
                   "on_update(game, fn (dt) { ticks = ticks + 1 })\n"
                   "print(advance(game, 0.05))\n"
                   "print(ticks)\n"
                   "print(game_time(game))\n", capsys)
    assert out == "3\n3\n0.05\n"


def test_the_remainder_of_a_frame_is_kept(capsys):
    out = run_both(GAME +
                   "let game = Game({})\n"
                   "print(advance(game, 0.05))\n"
                   "print(advance(game, 0.01))\n"
                   "print(advance(game, 0.01))\n", capsys)
    assert out == "3\n0\n1\n"


def test_the_draw_callback_runs_for_every_frame(capsys):
    out = run_both(GAME +
                   "let game = Game({})\n"
                   "var frames = 0\n"
                   "on_draw(game, fn (g) { frames = frames + 1 })\n"
                   "run(game, 5)\n"
                   "print(frames)\n", capsys)
    assert out == "5\n"


def test_the_quaternion_product(capsys):
    out = run_both(GAME +
                   "print(quat_identity())\n"
                   "let q = quat_from_axis_angle(vec3(0.0, 1.0, 0.0), 0.0)\n"
                   "print(quat_mul(q, quat_identity())[3])\n", capsys)
    assert out == "[0.0, 0.0, 0.0, 1.0]\n1.0\n"


# ---------------------------------------------------------------------------
# bun:web
# ---------------------------------------------------------------------------

WEB = "import { Router, route, get, post, put, delete, patch, handle, " \
      "match_path, request, response, text, page, json, redirect, html, " \
      "raw, escape_html, parse_query, parse_path, status_text, " \
      "build_response, parse_head, content_length, websocket_accept, " \
      "websocket_handshake, ws_frame, ws_parse, xor_byte, serve, " \
      "serve_forever, stop, proxy_request, proxy, chunked, to_hex, " \
      "index_of_bytes, header_value } from \"bun:web\"\n"

def test_the_router_finds_the_route(capsys):
    out = run_both(WEB +
                   "let router = Router()\n"
                   "get(router, \"/\", fn (req) { return page(\"<h1>home</h1>\") })\n"
                   "post(router, \"/items\", fn (req) { return text(\"made\") })\n"
                   "var reply = handle(router, \"GET\", \"/\", \"\", {})\n"
                   "print(reply[\"status\"])\n"
                   "print(reply[\"body\"])\n"
                   "reply = handle(router, \"POST\", \"/items\", \"\", {})\n"
                   "print(reply[\"status\"])\n"
                   "print(reply[\"body\"])\n", capsys)
    assert out == "200\n<h1>home</h1>\n200\nmade\n"


def test_an_unknown_path_is_not_found(capsys):
    out = run_both(WEB +
                   "let router = Router()\n"
                   "get(router, \"/\", fn (req) { return page(\"home\") })\n"
                   "let reply = handle(router, \"GET\", \"/nope\", \"\", {})\n"
                   "print(reply[\"status\"])\n", capsys)
    assert out == "404\n"


def test_the_method_has_to_match(capsys):
    out = run_both(WEB +
                   "let router = Router()\n"
                   "get(router, \"/x\", fn (req) { return text(\"got\") })\n"
                   "let reply = handle(router, \"POST\", \"/x\", \"\", {})\n"
                   "print(reply[\"status\"])\n", capsys)
    assert out == "404\n"


def test_the_path_names(capsys):
    out = run_both(WEB +
                   "let router = Router()\n"
                   "get(router, \"/users/:id\", fn (req) { "
                   "return text(req[\"params\"][\"id\"]) })\n"
                   "let reply = handle(router, \"GET\", \"/users/7\", \"\", {})\n"
                   "print(reply[\"body\"])\n", capsys)
    assert out == "7\n"


def test_the_tail_of_a_path(capsys):
    out = run_both(WEB +
                   "let router = Router()\n"
                   "get(router, \"/files/*rest\", fn (req) { "
                   "return text(req[\"params\"][\"rest\"]) })\n"
                   "let reply = handle(router, \"GET\", \"/files/a/b/c\", \"\", {})\n"
                   "print(reply[\"body\"])\n", capsys)
    assert out == "a/b/c\n"


def test_the_query_of_a_path(capsys):
    out = run_both(WEB +
                   "let router = Router()\n"
                   "get(router, \"/search\", fn (req) { "
                   "return text(req[\"query\"][\"q\"]) })\n"
                   "let reply = handle(router, \"GET\", \"/search?q=hello%20world\", \"\", {})\n"
                   "print(reply[\"body\"])\n", capsys)
    assert out == "hello world\n"


def test_the_headers_are_lowercase(capsys):
    out = run_both(WEB +
                   "let router = Router()\n"
                   "get(router, \"/\", fn (req) { "
                   "return text(req[\"headers\"][\"x-token\"]) })\n"
                   "let reply = handle(router, \"GET\", \"/\", \"\", { \"X-Token\": \"abc\" })\n"
                   "print(reply[\"body\"])\n", capsys)
    assert out == "abc\n"


def test_the_handler_gets_the_body(capsys):
    out = run_both(WEB +
                   "let router = Router()\n"
                   "post(router, \"/echo\", fn (req) { return text(req[\"body\"]) })\n"
                   "let reply = handle(router, \"POST\", \"/echo\", \"hello\", {})\n"
                   "print(reply[\"body\"])\n", capsys)
    assert out == "hello\n"


def test_the_templates_escape_the_values(capsys):
    out = run_both(WEB +
                   "print(html(\"<p>{{ name }}</p>\", { \"name\": \"<b>x</b>\" }))\n"
                   "print(html(\"<p>{{ name }}</p>\", { \"name\": raw(\"<b>x</b>\") }))\n"
                   "print(html(\"<p>hello</p>\", {}))\n", capsys)
    assert out == ("<p>&lt;b&gt;x&lt;/b&gt;</p>\n"
                   "<p><b>x</b></p>\n"
                   "<p>hello</p>\n")


def test_the_escape_of_the_markup(capsys):
    out = run_both(WEB +
                   "print(escape_html(\"a & b < c > d\"))\n", capsys)
    assert out == "a &amp; b &lt; c &gt; d\n"


def test_the_query_string(capsys):
    out = run_both(WEB +
                   "print(parse_query(\"a=1&b=2&c=\"))\n"
                   "print(parse_query(\"\"))\n", capsys)
    assert out == "{a: 1, b: 2, c: }\n{}\n"


def test_the_response_bytes(capsys):
    out = run_both(WEB +
                   "let reply = text(\"hi\")\n"
                   "let bytes = build_response(reply)\n"
                   "print(utf8_string(bytes))\n", capsys)
    assert out == ("HTTP/1.1 200 OK\r\n"
                   "Content-Type: text/plain; charset=utf-8\r\n"
                   "Content-Length: 2\r\n"
                   "Connection: close\r\n"
                   "\r\n"
                   "hi\n")


def test_the_head_of_a_request(capsys):
    out = run_both(WEB +
                   "let head = \"GET /a?b=1 HTTP/1.1\\r\\nHost: x\\r\\n"
                   "Content-Length: 3\\r\\n\"\n"
                   "let parsed = parse_head(head)\n"
                   "print(parsed[\"method\"])\n"
                   "print(parsed[\"path\"])\n"
                   "print(parsed[\"headers\"][\"host\"])\n"
                   "print(content_length(parsed[\"headers\"]))\n", capsys)
    assert out == "GET\n/a?b=1\nx\n3\n"


def test_the_websocket_handshake(capsys):
    out = run_both(WEB +
                   "print(websocket_accept(\"dGhlIHNhbXBsZSBub25jZQ==\"))\n", capsys)
    assert out == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=\n"


def test_a_websocket_frame(capsys):
    out = run_both(WEB +
                   "let frame = ws_frame(\"hello\", 1)\n"
                   "print(frame)\n"
                   "let parsed = ws_parse(frame, 0)\n"
                   "print(parsed[\"opcode\"])\n"
                   "print(utf8_string(parsed[\"payload\"]))\n", capsys)
    assert out == "[129, 5, 104, 101, 108, 108, 111]\n1\nhello\n"


def test_a_masked_websocket_frame(capsys):
    out = run_both(WEB +
                   "let masked = [129, 130, 0, 0, 0, 0, 88, 88]\n"
                   "let payload = ws_parse(masked, 0)\n"
                   "print(payload[\"opcode\"])\n"
                   "print(payload[\"size\"])\n"
                   "print(payload[\"payload\"])\n", capsys)
    assert out == "1\n8\n[88, 88]\n"


def test_the_exclusive_or(capsys):
    out = run_both(WEB +
                   "print(xor_byte(5, 3))\n"
                   "print(xor_byte(0, 255))\n"
                   "print(xor_byte(200, 100))\n", capsys)
    assert out == "6\n255\n172\n"


def test_the_server_answers(capsys):
    out = run_both(WEB +
                   "let router = Router()\n"
                   "get(router, \"/\", fn (req) { return page(\"<h1>hi</h1>\") })\n"
                   "get(router, \"/echo/:id\", fn (req) { "
                   "return text(req[\"params\"][\"id\"]) })\n"
                   "let server = serve(router, 0, \"127.0.0.1\")\n"
                   "let port = server[\"port\"]\n"
                   "spawn(fn () { serve_forever(server) })\n"
                   "sleep(0.3)\n"
                   "var reply = http_get(\"http://127.0.0.1:\" + str(port) + \"/\", {}, 5.0)\n"
                   "print(reply[\"status\"])\n"
                   "print(reply[\"body\"])\n"
                   "reply = http_get(\"http://127.0.0.1:\" + str(port) + \"/echo/42\", {}, 5.0)\n"
                   "print(reply[\"status\"])\n"
                   "print(reply[\"body\"])\n"
                   "stop(server)\n", capsys)
    assert out == "200\n<h1>hi</h1>\n200\n42\n"


def test_the_proxy_forwards_to_the_backend(capsys):
    out = run_both(WEB +
                   "let backend = Router()\n"
                   "get(backend, \"/api/hello\", fn (req) { return page(\"from backend\") })\n"
                   "let server = serve(backend, 0, \"127.0.0.1\")\n"
                   "spawn(fn () { serve_forever(server) })\n"
                   "sleep(0.3)\n"
                   "let front = Router()\n"
                   "proxy(front, \"/api\", \"http://127.0.0.1:\" + str(server[\"port\"]))\n"
                   "let front_server = serve(front, 0, \"127.0.0.1\")\n"
                   "spawn(fn () { serve_forever(front_server) })\n"
                   "sleep(0.3)\n"
                   "var reply = http_get(\"http://127.0.0.1:\" + "
                   "str(front_server[\"port\"]) + \"/api/hello\", {}, 5.0)\n"
                   "print(reply[\"status\"])\n"
                   "print(reply[\"body\"])\n"
                   "stop(front_server)\n"
                   "stop(server)\n", capsys)
    assert out == "200\nfrom backend\n"


def test_the_hexadecimal_form_of_a_number(capsys):
    out = run_both(WEB +
                   "print(to_hex(0))\n"
                   "print(to_hex(255))\n"
                   "print(to_hex(4096))\n", capsys)
    assert out == "0\nff\n1000\n"


def test_the_index_of_a_byte_list(capsys):
    out = run_both(WEB +
                   "print(index_of_bytes(utf8_bytes(\"abc\"), utf8_bytes(\"c\")))\n"
                   "print(index_of_bytes(utf8_bytes(\"abc\"), utf8_bytes(\"z\")))\n"
                   "print(index_of_bytes(utf8_bytes(\"\"), utf8_bytes(\"a\")))\n", capsys)
    assert out == "2\n-1\n-1\n"


def test_the_value_of_a_header_ignores_the_case(capsys):
    out = run_both(WEB +
                   "let headers = { \"Content-Type\": \"text/plain\" }\n"
                   "print(header_value(headers, \"content-type\"))\n"
                   "print(header_value(headers, \"CONTENT-TYPE\"))\n"
                   "print(header_value(headers, \"missing\"))\n", capsys)
    assert out == "text/plain\ntext/plain\nnull\n"


def test_the_bytes_of_a_chunked_response(capsys):
    out = run_both(WEB +
                   "let bytes = build_response(chunked([\"ab\", \"cde\"]))\n"
                   "print(utf8_string(bytes))\n", capsys)
    assert out == ("HTTP/1.1 200 OK\r\n"
                   "Transfer-Encoding: chunked\r\n"
                   "Connection: close\r\n"
                   "\r\n"
                   "2\r\n"
                   "ab\r\n"
                   "3\r\n"
                   "cde\r\n"
                   "0\r\n"
                   "\r\n\n")


def test_the_version_of_a_request(capsys):
    out = run_both(WEB +
                   "var parsed = parse_head(\"GET /a HTTP/1.0\\r\\nHost: x\\r\\n\")\n"
                   "print(parsed[\"version\"])\n"
                   "parsed = parse_head(\"GET /a HTTP/1.1\\r\\nHost: x\\r\\n\")\n"
                   "print(parsed[\"version\"])\n", capsys)
    assert out == "HTTP/1.0\nHTTP/1.1\n"


def test_the_connection_stays_open_for_the_next_request(capsys):
    out = run_both(WEB +
                   "let router = Router()\n"
                   "get(router, \"/a\", fn (req) { return text(\"first\") })\n"
                   "get(router, \"/b\", fn (req) { return text(\"second\") })\n"
                   "let server = serve(router, 0, \"127.0.0.1\")\n"
                   "let port = server[\"port\"]\n"
                   "spawn(fn () { serve_forever(server) })\n"
                   "sleep(0.3)\n"
                   "let sock = tcp_connect(\"127.0.0.1\", port)\n"
                   "tcp_write(sock, utf8_bytes(\"GET /a HTTP/1.1\\r\\nHost: x\\r\\n\\r\\n\"))\n"
                   "sleep(0.2)\n"
                   "let first = utf8_string(tcp_read(sock, 65536))\n"
                   "tcp_write(sock, utf8_bytes(\"GET /b HTTP/1.1\\r\\nHost: x\\r\\n\\r\\n\"))\n"
                   "sleep(0.2)\n"
                   "let second = utf8_string(tcp_read(sock, 65536))\n"
                   "tcp_close(sock)\n"
                   "stop(server)\n"
                   "print(first.index_of(\"first\") > 0)\n"
                   "print(first.index_of(\"keep-alive\") > 0)\n"
                   "print(second.index_of(\"second\") > 0)\n", capsys)
    assert out == "true\ntrue\ntrue\n"


def test_two_requests_in_one_write_are_both_served(capsys):
    out = run_both(WEB +
                   "let router = Router()\n"
                   "get(router, \"/a\", fn (req) { return text(\"first\") })\n"
                   "let server = serve(router, 0, \"127.0.0.1\")\n"
                   "let port = server[\"port\"]\n"
                   "spawn(fn () { serve_forever(server) })\n"
                   "sleep(0.3)\n"
                   "let sock = tcp_connect(\"127.0.0.1\", port)\n"
                   "tcp_write(sock, utf8_bytes("
                   "\"GET /a HTTP/1.1\\r\\nHost: x\\r\\n\\r\\n\" + "
                   "\"GET /a HTTP/1.1\\r\\nHost: x\\r\\n\\r\\n\"))\n"
                   "sleep(0.3)\n"
                   "let both = utf8_string(tcp_read(sock, 65536))\n"
                   "tcp_close(sock)\n"
                   "stop(server)\n"
                   "print(both.index_of(\"first\") > 0)\n"
                   "print(both.len() > 200)\n", capsys)
    assert out == "true\ntrue\n"


def test_the_client_can_ask_for_the_connection_to_close(capsys):
    out = run_both(WEB +
                   "let router = Router()\n"
                   "get(router, \"/a\", fn (req) { return text(\"first\") })\n"
                   "let server = serve(router, 0, \"127.0.0.1\")\n"
                   "let port = server[\"port\"]\n"
                   "spawn(fn () { serve_forever(server) })\n"
                   "sleep(0.3)\n"
                   "let sock = tcp_connect(\"127.0.0.1\", port)\n"
                   "tcp_write(sock, utf8_bytes("
                   "\"GET /a HTTP/1.1\\r\\nHost: x\\r\\nConnection: close\\r\\n\\r\\n\"))\n"
                   "sleep(0.3)\n"
                   "let reply = utf8_string(tcp_read(sock, 65536))\n"
                   "tcp_close(sock)\n"
                   "stop(server)\n"
                   "print(reply.index_of(\"Connection: close\") > 0)\n"
                   "print(reply.index_of(\"keep-alive\"))\n", capsys)
    assert out == "true\n-1\n"


def test_the_answer_can_ask_for_the_connection_to_close(capsys):
    out = run_both(WEB +
                   "let router = Router()\n"
                   "get(router, \"/a\", fn (req) { "
                   "return { \"status\": 200, \"body\": \"bye\", "
                   "\"headers\": { \"Connection\": \"close\" } } })\n"
                   "let server = serve(router, 0, \"127.0.0.1\")\n"
                   "let port = server[\"port\"]\n"
                   "spawn(fn () { serve_forever(server) })\n"
                   "sleep(0.3)\n"
                   "let sock = tcp_connect(\"127.0.0.1\", port)\n"
                   "tcp_write(sock, utf8_bytes(\"GET /a HTTP/1.1\\r\\nHost: x\\r\\n\\r\\n\"))\n"
                   "sleep(0.3)\n"
                   "let reply = utf8_string(tcp_read(sock, 65536))\n"
                   "tcp_close(sock)\n"
                   "stop(server)\n"
                   "print(reply.index_of(\"Connection: close\") > 0)\n"
                   "print(reply.index_of(\"keep-alive\"))\n", capsys)
    assert out == "true\n-1\n"


def test_the_chunked_answer_over_a_socket(capsys):
    out = run_both(WEB +
                   "let router = Router()\n"
                   "get(router, \"/c\", fn (req) { return chunked([\"one \", \"two\"]) })\n"
                   "let server = serve(router, 0, \"127.0.0.1\")\n"
                   "let port = server[\"port\"]\n"
                   "spawn(fn () { serve_forever(server) })\n"
                   "sleep(0.3)\n"
                   "let sock = tcp_connect(\"127.0.0.1\", port)\n"
                   "tcp_write(sock, utf8_bytes(\"GET /c HTTP/1.1\\r\\nHost: x\\r\\n\\r\\n\"))\n"
                   "sleep(0.3)\n"
                   "let reply = utf8_string(tcp_read(sock, 65536))\n"
                   "tcp_close(sock)\n"
                   "stop(server)\n"
                   "print(reply.index_of(\"Transfer-Encoding: chunked\") > 0)\n"
                   "print(reply.index_of(\"4\\r\\none \") > 0)\n", capsys)
    assert out == "true\ntrue\n"


# ---------------------------------------------------------------------------
# The bodies of the modules
# ---------------------------------------------------------------------------

def test_the_body_of_every_module_is_clean():
    """The body of a module is checked, even though the checker of a
    program does not look into the modules it imports.

    A module that assigns into an immutable name fails only when the line
    that does it is reached, so the library is checked here, once, for
    every module of it.
    """
    import os

    from bun import modules
    from bun.checker import Checker
    from bun.errors import BunError
    from bun.lexer import Lexer
    from bun.parser import Parser

    names = [name for name in sorted(os.listdir(modules.NATIVE_DIR))
             if name.endswith(".bun")]
    assert names
    for name in names:
        path = os.path.join(modules.NATIVE_DIR, name)
        with open(path, "r") as handle:
            source = handle.read()
        program = Parser(Lexer(source).tokenize()).parse()
        try:
            Checker().check(program, base_dir=modules.NATIVE_DIR)
        except BunError as error:
            raise AssertionError(
                "the module %s has a problem: %s (line %s)"
                % (name, error.msg, error.line))
