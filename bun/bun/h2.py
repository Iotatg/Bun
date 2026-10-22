"""Minimal HTTP/2 client used by the MTProto transport.

The implementation covers what the Telegram protocol needs: one TLS connection
with ALPN "h2", request/response streams carrying binary payloads, and the
control frames required to keep the connection healthy.
"""

import socket
import ssl

from .errors import BunRuntimeError
from .hpack import DynamicTable, decode_headers, encode_headers

CLIENT_PREFACE = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"

FRAME_DATA = 0x0
FRAME_HEADERS = 0x1
FRAME_PRIORITY = 0x2
FRAME_RST_STREAM = 0x3
FRAME_SETTINGS = 0x4
FRAME_PUSH_PROMISE = 0x5
FRAME_PING = 0x6
FRAME_GOAWAY = 0x7
FRAME_WINDOW_UPDATE = 0x8
FRAME_CONTINUATION = 0x9

FLAG_END_STREAM = 0x1
FLAG_ACK = 0x1
FLAG_END_HEADERS = 0x4
FLAG_PADDED = 0x8
FLAG_PRIORITY = 0x20

SETTINGS_MAX_CONCURRENT_STREAMS = 0x3
SETTINGS_INITIAL_WINDOW_SIZE = 0x4
SETTINGS_MAX_FRAME_SIZE = 0x5

MAX_FRAME_SIZE = 16384
WINDOW_TARGET = 1048576


class H2Error(BunRuntimeError):
    """Raised when the HTTP/2 peer violates the protocol."""


def _frame_header(length, frame_type, flags, stream_id):
    return bytes([
        (length >> 16) & 0xFF,
        (length >> 8) & 0xFF,
        length & 0xFF,
        frame_type & 0xFF,
        flags & 0xFF,
        (stream_id >> 24) & 0x7F,
        (stream_id >> 16) & 0xFF,
        (stream_id >> 8) & 0xFF,
        stream_id & 0xFF,
    ])


class H2Connection(object):
    """A single HTTP/2 connection over a TLS socket."""

    def __init__(self, sock, authority=None):
        self.sock = sock
        self.authority = authority
        self.buffer = bytearray()
        self.next_stream_id = 1
        self.peer_settings = {}
        self.peer_max_frame_size = MAX_FRAME_SIZE
        self.peer_initial_window = 65535
        self.goaway = None
        self.table = DynamicTable()
        self._closed = False

    # -- low level helpers -------------------------------------------------
    def _send(self, data):
        try:
            self.sock.sendall(data)
        except Exception as error:
            raise H2Error("h2: send failed: %s" % error)

    def _read_more(self):
        try:
            chunk = self.sock.recv(65536)
        except socket.timeout:
            raise H2Error("h2: timed out waiting for data")
        except Exception as error:
            raise H2Error("h2: read failed: %s" % error)
        if not chunk:
            raise H2Error("h2: connection closed by peer")
        self.buffer.extend(chunk)

    def _next_frame(self):
        """Return (frame_type, flags, stream_id, payload) or None when short."""
        if len(self.buffer) < 9:
            return None
        length = (self.buffer[0] << 16) | (self.buffer[1] << 8) | self.buffer[2]
        frame_type = self.buffer[3]
        flags = self.buffer[4]
        stream_id = ((self.buffer[5] & 0x7F) << 24) | (self.buffer[6] << 16) | (self.buffer[7] << 8) | self.buffer[8]
        if len(self.buffer) < 9 + length:
            return None
        payload = bytes(self.buffer[9:9 + length])
        del self.buffer[:9 + length]
        return (frame_type, flags, stream_id, payload)

    # -- control frames ----------------------------------------------------
    def _send_settings(self):
        payload = b""
        for key, value in (
            (SETTINGS_MAX_CONCURRENT_STREAMS, 100),
            (SETTINGS_INITIAL_WINDOW_SIZE, 1048576),
            (SETTINGS_MAX_FRAME_SIZE, MAX_FRAME_SIZE),
        ):
            payload += bytes([(key >> 8) & 0xFF, key & 0xFF])
            payload += bytes([
                (value >> 24) & 0xFF,
                (value >> 16) & 0xFF,
                (value >> 8) & 0xFF,
                value & 0xFF,
            ])
        self._send(_frame_header(len(payload), FRAME_SETTINGS, 0, 0) + payload)

    def _send_settings_ack(self):
        self._send(_frame_header(0, FRAME_SETTINGS, FLAG_ACK, 0))

    def _send_ping_ack(self, payload):
        self._send(_frame_header(len(payload), FRAME_PING, FLAG_ACK, 0) + payload)

    def _send_window_update(self, stream_id, increment):
        payload = bytes([
            (increment >> 24) & 0xFF,
            (increment >> 16) & 0xFF,
            (increment >> 8) & 0xFF,
            increment & 0xFF,
        ])
        self._send(_frame_header(len(payload), FRAME_WINDOW_UPDATE, 0, stream_id) + payload)

    def _send_rst_stream(self, stream_id, error_code):
        payload = bytes([(error_code >> 24) & 0xFF, (error_code >> 16) & 0xFF, (error_code >> 8) & 0xFF, error_code & 0xFF])
        self._send(_frame_header(len(payload), FRAME_RST_STREAM, 0, stream_id) + payload)

    # -- connection setup --------------------------------------------------
    def handshake(self, timeout=20):
        self.sock.settimeout(timeout)
        self._send(CLIENT_PREFACE)
        self._send_settings()
        self._send_window_update(0, WINDOW_TARGET)
        # Wait for the server settings frame, answering control frames on the way.
        while True:
            frame = self._next_frame()
            if frame is None:
                self._read_more()
                continue
            frame_type, flags, stream_id, payload = frame
            if frame_type == FRAME_SETTINGS:
                if flags & FLAG_ACK:
                    break
                self._apply_settings(payload)
                self._send_settings_ack()
                break
            if frame_type == FRAME_PING:
                if not flags & FLAG_ACK:
                    self._send_ping_ack(payload)
            elif frame_type == FRAME_GOAWAY:
                raise H2Error("h2: peer sent GOAWAY during handshake")

    def _apply_settings(self, payload):
        for index in range(0, len(payload) - 5, 6):
            key = (payload[index] << 8) | payload[index + 1]
            value = (
                (payload[index + 2] << 24)
                | (payload[index + 3] << 16)
                | (payload[index + 4] << 8)
                | payload[index + 5]
            )
            self.peer_settings[key] = value
            if key == SETTINGS_MAX_FRAME_SIZE:
                self.peer_max_frame_size = value
            elif key == SETTINGS_INITIAL_WINDOW_SIZE:
                self.peer_initial_window = value

    # -- request/response --------------------------------------------------
    def request(self, method, path, headers=None, body=b"", authority=None):
        """Send a request and return (status, headers, body)."""
        stream_id = self.next_stream_id
        self.next_stream_id += 2

        request_headers = [
            (":method", method),
            (":path", path),
            (":scheme", "https"),
            (":authority", authority or self.authority or ""),
            ("user-agent", "TelegramBot/1.0"),
            ("accept-encoding", "identity"),
        ]
        if headers:
            for name, value in headers:
                request_headers.append((name, value))
        if body:
            request_headers.append(("content-length", str(len(body))))
            request_headers.append(("content-type", "application/octet-stream"))

        block = encode_headers(request_headers)
        end_stream = not body
        self._send(_frame_header(len(block), FRAME_HEADERS, FLAG_END_HEADERS | (FLAG_END_STREAM if end_stream else 0), stream_id) + block)

        if body:
            offset = 0
            while offset < len(body):
                chunk = body[offset:offset + self.peer_max_frame_size]
                offset += len(chunk)
                last = offset >= len(body)
                self._send(_frame_header(len(chunk), FRAME_DATA, FLAG_END_STREAM if last else 0, stream_id) + chunk)

        return self._read_response(stream_id)

    def _read_response(self, stream_id):
        header_block = bytearray()
        body = bytearray()
        status = 0
        response_headers = []
        received = 0
        while True:
            frame = self._next_frame()
            if frame is None:
                self._read_more()
                continue
            frame_type, flags, frame_stream, payload = frame

            if frame_type == FRAME_SETTINGS:
                if not flags & FLAG_ACK:
                    self._apply_settings(payload)
                    self._send_settings_ack()
                continue
            if frame_type == FRAME_PING:
                if not flags & FLAG_ACK:
                    self._send_ping_ack(payload)
                continue
            if frame_type == FRAME_WINDOW_UPDATE:
                continue
            if frame_type == FRAME_GOAWAY:
                error_code = int.from_bytes(payload[4:8], "big") if len(payload) >= 8 else 0
                self.goaway = error_code
                raise H2Error("h2: peer sent GOAWAY (code %d)" % error_code)
            if frame_type == FRAME_RST_STREAM:
                if frame_stream == stream_id:
                    code = int.from_bytes(payload[0:4], "big") if len(payload) >= 4 else 0
                    raise H2Error("h2: stream reset (code %d)" % code)
                continue
            if frame_type == FRAME_HEADERS and frame_stream == stream_id:
                block = payload
                if flags & FLAG_PADDED:
                    pad_length = payload[0]
                    block = payload[1:len(payload) - pad_length]
                if flags & FLAG_PRIORITY:
                    block = block[5:]
                header_block.extend(block)
                if not flags & FLAG_END_HEADERS:
                    header_block.extend(self._read_continuation(stream_id))
                response_headers = decode_headers(bytes(header_block), self.table)
                for name, value in response_headers:
                    if name == ":status":
                        status = int(value)
                if flags & FLAG_END_STREAM:
                    return (status, response_headers, bytes(body))
                continue
            if frame_type == FRAME_CONTINUATION:
                header_block.extend(self._read_continuation(stream_id))
                response_headers = decode_headers(bytes(header_block), self.table)
                for name, value in response_headers:
                    if name == ":status":
                        status = int(value)
                continue
            if frame_type == FRAME_DATA and frame_stream == stream_id:
                chunk = payload
                if flags & FLAG_PADDED:
                    pad_length = payload[0]
                    chunk = payload[1:len(payload) - pad_length]
                body.extend(chunk)
                received += len(chunk)
                if received >= 32768:
                    received = 0
                    self._send_window_update(0, WINDOW_TARGET)
                    self._send_window_update(stream_id, WINDOW_TARGET)
                if flags & FLAG_END_STREAM:
                    return (status, response_headers, bytes(body))
                continue

    def _read_continuation(self, stream_id):
        out = bytearray()
        while True:
            frame = self._next_frame()
            if frame is None:
                self._read_more()
                continue
            frame_type, flags, frame_stream, payload = frame
            if frame_type != FRAME_CONTINUATION:
                raise H2Error("h2: expected CONTINUATION frame")
            out.extend(payload)
            if flags & FLAG_END_HEADERS:
                return bytes(out)

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.sock.close()
        except Exception:
            pass


def connect(host, port, sni=None, alpn=("h2",), timeout=20):
    """Open a TLS connection that negotiates the given ALPN protocols."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    if alpn:
        try:
            context.set_alpn_protocols(list(alpn))
        except NotImplementedError:
            pass
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
    except Exception as error:
        raise H2Error("h2: connect to %s:%d failed: %s" % (host, port, error))
    try:
        tls_sock = context.wrap_socket(sock, server_hostname=sni or host)
    except Exception as error:
        raise H2Error("h2: TLS handshake failed: %s" % error)
    return tls_sock
