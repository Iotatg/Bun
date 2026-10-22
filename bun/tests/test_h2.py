"""Tests for the HPACK codec, the HTTP/2 client and the byte oriented builtins."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bun import h2, hpack  # noqa: E402


class FakeSocket(object):
    """A socket stub that replays canned server bytes."""

    def __init__(self, incoming=b"", alpn="h2"):
        self.incoming = bytearray(incoming)
        self.sent = bytearray()
        self.alpn = alpn
        self.closed = False

    def sendall(self, data):
        self.sent.extend(data)

    def recv(self, size):
        chunk = bytes(self.incoming[:size])
        del self.incoming[:size]
        return chunk

    def settimeout(self, timeout):
        pass

    def close(self):
        self.closed = True

    def selected_alpn_protocol(self):
        return self.alpn


# -- Huffman coding ------------------------------------------------------
def test_huffman_matches_rfc7541_vectors():
    vectors = {
        b"www.example.com": "f1e3c2e5f23a6ba0ab90f4ff",
        b"no-cache": "a8eb10649cbf",
        b"custom-key": "25a849e95ba97d7f",
        b"custom-value": "25a849e95bb8e8b4bf",
    }
    for raw, expected in vectors.items():
        assert hpack.huffman_encode(raw).hex() == expected
        assert hpack.huffman_decode(bytes.fromhex(expected)) == raw


def test_hpack_decodes_rfc7541_request_sequence():
    table = hpack.DynamicTable()
    blocks = [
        "828684410f7777772e6578616d706c652e636f6d",
        "828684be58086e6f2d6361636865",
        "828785bf400a637573746f6d2d6b65790c637573746f6d2d76616c7565",
    ]
    first = hpack.decode_headers(bytes.fromhex(blocks[0]), table)
    assert first == [
        (":method", "GET"),
        (":scheme", "http"),
        (":path", "/"),
        (":authority", "www.example.com"),
    ]
    second = hpack.decode_headers(bytes.fromhex(blocks[1]), table)
    assert ("cache-control", "no-cache") in second
    third = hpack.decode_headers(bytes.fromhex(blocks[2]), table)
    assert ("custom-key", "custom-value") in third


def test_hpack_decodes_huffman_coded_response():
    block = bytes.fromhex(
        "48826402588"
        "5aec3771a4b6196d07abe941054d444a82005950"
        "40b8166e082a62d1bff6e919d29ad171863c78f0b97c8e9ae82ae43d3"
    )
    headers = hpack.decode_headers(block)
    assert headers[0] == (":status", "302")
    assert ("date", "Mon, 21 Oct 2013 20:13:21 GMT") in headers


def test_hpack_encodes_headers_as_literals():
    block = hpack.encode_headers([(":method", "POST"), ("x-test", "bun")])
    headers = hpack.decode_headers(block)
    assert headers == [(":method", "POST"), ("x-test", "bun")]


def test_hpack_integer_round_trip():
    for value in (0, 1, 126, 127, 128, 255, 16384, 1000000):
        encoded = hpack.encode_integer(value, 5)
        decoded, offset = hpack.decode_integer(encoded, 0, 5)
        assert decoded == value
        assert offset == len(encoded)


# -- HTTP/2 framing ------------------------------------------------------
def test_h2_frame_header_layout():
    header = h2._frame_header(258, h2.FRAME_DATA, h2.FLAG_END_STREAM, 5)
    assert len(header) == 9
    assert header[0:3] == bytes([0x00, 0x01, 0x02])
    assert header[3] == h2.FRAME_DATA
    assert header[4] == h2.FLAG_END_STREAM
    assert header[5:9] == bytes([0, 0, 0, 5])


def test_h2_reads_frames_from_the_buffer():
    connection = h2.H2Connection(FakeSocket())
    connection.buffer.extend(h2._frame_header(3, h2.FRAME_PING, 0, 0) + b"abc")
    frame = connection._next_frame()
    assert frame is not None
    assert frame[0] == h2.FRAME_PING
    assert frame[3] == b"abc"
    assert connection._next_frame() is None


def test_h2_handshake_sends_preface_and_settings():
    server_settings = h2._frame_header(0, h2.FRAME_SETTINGS, 0, 0)
    socket = FakeSocket(incoming=server_settings)
    connection = h2.H2Connection(socket)
    connection.handshake()
    assert socket.sent.startswith(h2.CLIENT_PREFACE)
    assert h2.FRAME_SETTINGS in socket.sent
    assert h2.FLAG_ACK in socket.sent


def test_h2_request_writes_headers_and_data():
    response = (
        h2._frame_header(0, h2.FRAME_SETTINGS, h2.FLAG_ACK, 0)
        + h2._frame_header(0, h2.FRAME_HEADERS, h2.FLAG_END_HEADERS | h2.FLAG_END_STREAM, 1)
    )
    socket = FakeSocket(incoming=response)
    connection = h2.H2Connection(socket)
    connection.request("POST", "/apiw1", [], b"payload")
    assert h2.FRAME_HEADERS in socket.sent
    assert h2.FRAME_DATA in socket.sent
    assert b"payload" in bytes(socket.sent)


def test_h2_close_releases_the_socket():
    socket = FakeSocket()
    connection = h2.H2Connection(socket)
    connection.close()
    assert socket.closed is True


# -- Byte oriented builtins ---------------------------------------------
def test_crypto_builtins_return_byte_lists():
    from bun import builtins
    from bun.dict import BunDict

    digest = builtins._sha256([b"abc"])
    assert isinstance(digest, list)
    assert len(digest) == 32
    assert digest[:3] == [0xBA, 0x78, 0x16]

    encrypted = builtins._aes_ige_encrypt([list(range(16)), list(range(32)), list(range(32))])
    assert isinstance(encrypted, list)
    assert len(encrypted) == 16

    decrypted = builtins._aes_ige_decrypt([encrypted, list(range(32)), list(range(32))])
    assert decrypted == list(range(16))

    assert isinstance(builtins._random_bytes([4]), list)
    assert len(builtins._random_bytes([4])) == 4
    assert isinstance(BunDict(), BunDict)


def test_aes_matches_the_published_test_vectors():
    from bun.aes import AES

    plaintext = bytes.fromhex("00112233445566778899aabbccddeeff")
    vectors = [
        ("000102030405060708090a0b0c0d0e0f",
         "69c4e0d86a7b0430d8cdb78070b4c55a"),
        ("000102030405060708090a0b0c0d0e0f1011121314151617",
         "dda97ca4864cdfe06eaf70a0ec0d7191"),
        ("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f",
         "8ea2b7ca516745bfeafc49904b496089"),
    ]
    for key, expected in vectors:
        cipher = AES(bytes.fromhex(key))
        encrypted = cipher.encrypt_block(plaintext)
        assert encrypted.hex() == expected
        assert cipher.decrypt_block(encrypted) == plaintext


def test_aes_ige_chains_both_halves_of_the_vector():
    from bun.aes import ige_decrypt, ige_encrypt

    key = bytes(range(32))
    iv = bytes(range(32, 64))
    data = bytes(range(64))
    encrypted = ige_encrypt(data, key, iv)
    assert len(encrypted) == len(data)
    assert ige_decrypt(encrypted, key, iv) == data


def test_crypto_builtins_reject_unaligned_data():
    from bun import builtins
    from bun.errors import BunRuntimeError

    try:
        builtins._aes_ige_encrypt([[1, 2, 3], list(range(32)), list(range(32))])
    except BunRuntimeError as error:
        assert "multiple of 16" in error.msg
    else:
        raise AssertionError("expected a runtime error")


def test_crypto_builtins_reject_invalid_bytes():
    from bun import builtins
    from bun.errors import BunRuntimeError

    try:
        builtins._sha256([[256]])
    except BunRuntimeError as error:
        assert "between 0 and 255" in error.msg
    else:
        raise AssertionError("expected a runtime error")
