"""HPACK header compression (RFC 7541).

The encoder emits literal header fields without indexing and without Huffman
coding, which every HPACK decoder accepts. The decoder supports the full
representation set, including Huffman coded strings and the dynamic table.
"""

from .errors import BunRuntimeError
from .hpack_table import HUFFMAN_CODES, HUFFMAN_LENGTHS

STATIC_TABLE = [
    (":authority", ""),
    (":method", "GET"),
    (":method", "POST"),
    (":path", "/"),
    (":path", "/index.html"),
    (":scheme", "http"),
    (":scheme", "https"),
    (":status", "200"),
    (":status", "204"),
    (":status", "206"),
    (":status", "304"),
    (":status", "400"),
    (":status", "404"),
    (":status", "500"),
    ("accept-charset", ""),
    ("accept-encoding", "gzip, deflate"),
    ("accept-language", ""),
    ("accept-ranges", ""),
    ("accept", ""),
    ("access-control-allow-origin", ""),
    ("age", ""),
    ("allow", ""),
    ("authorization", ""),
    ("cache-control", ""),
    ("content-disposition", ""),
    ("content-encoding", ""),
    ("content-language", ""),
    ("content-length", ""),
    ("content-location", ""),
    ("content-range", ""),
    ("content-type", ""),
    ("cookie", ""),
    ("date", ""),
    ("etag", ""),
    ("expect", ""),
    ("expires", ""),
    ("from", ""),
    ("host", ""),
    ("if-match", ""),
    ("if-modified-since", ""),
    ("if-none-match", ""),
    ("if-range", ""),
    ("if-unmodified-since", ""),
    ("last-modified", ""),
    ("link", ""),
    ("location", ""),
    ("max-forwards", ""),
    ("proxy-authenticate", ""),
    ("proxy-authorization", ""),
    ("range", ""),
    ("referer", ""),
    ("refresh", ""),
    ("retry-after", ""),
    ("server", ""),
    ("set-cookie", ""),
    ("strict-transport-security", ""),
    ("transfer-encoding", ""),
    ("user-agent", ""),
    ("vary", ""),
    ("via", ""),
    ("www-authenticate", ""),
]

STATIC_TABLE_SIZE = 61


def _build_huffman_tree():
    tree = {}
    for symbol in range(257):
        code = HUFFMAN_CODES[symbol]
        length = HUFFMAN_LENGTHS[symbol]
        node = tree
        for index in range(length - 1, -1, -1):
            bit = (code >> index) & 1
            if index == 0:
                node[bit] = symbol
            else:
                child = node.get(bit)
                if not isinstance(child, dict):
                    child = {}
                    node[bit] = child
                node = child
    return tree


HUFFMAN_TREE = _build_huffman_tree()
HUFFMAN_EOS = 256


def huffman_decode(data):
    """Decode a Huffman coded string into raw bytes."""
    out = bytearray()
    node = HUFFMAN_TREE
    bits_since_symbol = 0
    for byte in data:
        for shift in range(7, -1, -1):
            bit = (byte >> shift) & 1
            child = node.get(bit)
            if child is None:
                raise BunRuntimeError("hpack: invalid huffman code")
            if isinstance(child, dict):
                node = child
                bits_since_symbol += 1
                continue
            if child == HUFFMAN_EOS:
                raise BunRuntimeError("hpack: unexpected huffman EOS symbol")
            out.append(child)
            node = HUFFMAN_TREE
            bits_since_symbol = 0
    if bits_since_symbol > 7:
        raise BunRuntimeError("hpack: huffman padding too long")
    return bytes(out)


def huffman_encode(data):
    """Encode raw bytes with the HPACK Huffman code."""
    out = bytearray()
    bits = 0
    count = 0
    for byte in data:
        code = HUFFMAN_CODES[byte]
        length = HUFFMAN_LENGTHS[byte]
        bits = (bits << length) | code
        count += length
        while count >= 8:
            count -= 8
            out.append((bits >> count) & 0xFF)
    if count > 0:
        out.append(((bits << (8 - count)) | ((1 << (8 - count)) - 1)) & 0xFF)
    return bytes(out)


def encode_integer(value, prefix_bits):
    """Encode an integer with an N bit prefix (RFC 7541 section 5.1)."""
    if value < 0:
        raise BunRuntimeError("hpack: negative integer")
    limit = (1 << prefix_bits) - 1
    if value < limit:
        return bytes([value])
    out = bytearray([limit])
    value -= limit
    while value >= 128:
        out.append((value % 128) + 128)
        value //= 128
    out.append(value)
    return bytes(out)


def decode_integer(data, offset, prefix_bits):
    """Decode an integer with an N bit prefix, returning (value, next_offset)."""
    if offset >= len(data):
        raise BunRuntimeError("hpack: truncated integer")
    limit = (1 << prefix_bits) - 1
    value = data[offset] & limit
    offset += 1
    if value < limit:
        return value, offset
    shift = 0
    while True:
        if offset >= len(data):
            raise BunRuntimeError("hpack: truncated integer")
        byte = data[offset]
        offset += 1
        value += (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            break
    return value, offset


def encode_string(text):
    """Encode a header string, optionally with Huffman coding.

    The Huffman flag lives in the top bit of the first byte, so a multi byte
    length keeps the 0x7F prefix marker and only flips the flag bit.
    """
    raw = text.encode("utf-8") if isinstance(text, str) else bytes(text)
    encoded = huffman_encode(raw)
    if len(encoded) < len(raw):
        length_bytes = encode_integer(len(encoded), 7)
        return bytes([length_bytes[0] | 0x80]) + length_bytes[1:] + encoded
    return encode_integer(len(raw), 7) + raw


def decode_string(data, offset):
    """Decode a header string, returning (text, next_offset)."""
    if offset >= len(data):
        raise BunRuntimeError("hpack: truncated string")
    huffman = bool(data[offset] & 0x80)
    length, offset = decode_integer(data, offset, 7)
    end = offset + length
    if end > len(data):
        raise BunRuntimeError("hpack: truncated string")
    raw = data[offset:end]
    if huffman:
        raw = huffman_decode(raw)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    return text, end


def encode_headers(headers):
    """Encode a list of (name, value) pairs into a header block."""
    out = bytearray()
    for name, value in headers:
        name = name.lower()
        out.extend(encode_integer(0, 4))  # literal without indexing, new name
        out.extend(encode_string(name))
        out.extend(encode_string(value))
    return bytes(out)


class DynamicTable(object):
    """The HPACK dynamic table used while decoding a header block."""

    def __init__(self, max_size=4096):
        self.max_size = max_size
        self.entries = []
        self.size = 0

    def add(self, name, value):
        entry_size = len(name.encode("utf-8")) + len(value.encode("utf-8")) + 32
        self.entries.insert(0, (name, value))
        self.size += entry_size
        self._evict()

    def _evict(self):
        while self.size > self.max_size and self.entries:
            name, value = self.entries.pop()
            self.size -= len(name.encode("utf-8")) + len(value.encode("utf-8")) + 32

    def set_max_size(self, max_size):
        self.max_size = max_size
        self._evict()

    def get(self, index):
        if index <= 0:
            raise BunRuntimeError("hpack: invalid header index 0")
        if index <= STATIC_TABLE_SIZE:
            return STATIC_TABLE[index - 1]
        offset = index - STATIC_TABLE_SIZE - 1
        if offset >= len(self.entries):
            raise BunRuntimeError("hpack: header index out of range")
        return self.entries[offset]


def decode_headers(block, table=None):
    """Decode a header block into a list of (name, value) pairs."""
    if table is None:
        table = DynamicTable()
    headers = []
    offset = 0
    data = bytes(block)
    while offset < len(data):
        byte = data[offset]
        if byte & 0x80:
            index, offset = decode_integer(data, offset, 7)
            headers.append(table.get(index))
            continue
        if byte & 0x40:
            index, offset = decode_integer(data, offset, 6)
            if index:
                name = table.get(index)[0]
            else:
                name, offset = decode_string(data, offset)
            value, offset = decode_string(data, offset)
            table.add(name, value)
            headers.append((name, value))
            continue
        if byte & 0x20:
            size, offset = decode_integer(data, offset, 5)
            table.set_max_size(size)
            continue
        index, offset = decode_integer(data, offset, 4)
        if index:
            name = table.get(index)[0]
        else:
            name, offset = decode_string(data, offset)
        value, offset = decode_string(data, offset)
        headers.append((name, value))
    return headers
