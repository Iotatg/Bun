"""AES block cipher and the IGE mode.

The runtime only depends on the standard library, so the block cipher is
implemented here. The implementation follows the AES specification: the state
is kept as a list of bytes in column major order and every round applies the
substitution, the row shift, the column mix and the round key.

The cipher works on tables. Every table holds the result of the substitution
and of the column mix for one byte, so a round needs four lookups and a few
operations on words of thirty two bits. The words of the state are the columns
of it, counted from the top, and every word holds the bytes of its column
from the top to the bottom.

Telegram uses the IGE mode, which chains both the plaintext and the
ciphertext of the previous block into the next one.

When the system holds the library of OpenSSL, the cipher takes the blocks from
it, because the library works in the language of the machine and is much
faster. The tables above stay the way of the cipher when the library is not
there, and both ways give the same bytes.
"""

import ctypes
import ctypes.util


# The library of the cipher of the system, or false when it is not there.
_OPENSSL = None


def _load_openssl():
    """Load the cipher of the system library when it is there.

    The result holds the library, or false when the library is not there.
    """
    global _OPENSSL
    if _OPENSSL is not None:
        return _OPENSSL
    _OPENSSL = False
    try:
        name = ctypes.util.find_library("crypto")
        candidates = []
        if name:
            candidates.append(name)
        candidates.extend(["libcrypto.so.3", "libcrypto.so.1.1", "libcrypto.so"])
        library = None
        for candidate in candidates:
            try:
                library = ctypes.CDLL(candidate)
                break
            except OSError:
                continue
        if library is None:
            return False
        library.EVP_CIPHER_CTX_new.restype = ctypes.c_void_p
        library.EVP_CIPHER_CTX_free.argtypes = [ctypes.c_void_p]
        library.EVP_CIPHER_CTX_set_padding.argtypes = [ctypes.c_void_p, ctypes.c_int]
        for name in ("EVP_aes_128_ecb", "EVP_aes_192_ecb", "EVP_aes_256_ecb"):
            function = getattr(library, name)
            function.restype = ctypes.c_void_p
        for name in ("EVP_EncryptInit_ex", "EVP_DecryptInit_ex"):
            function = getattr(library, name)
            function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                 ctypes.c_char_p, ctypes.c_char_p]
            function.restype = ctypes.c_int
        for name in ("EVP_EncryptUpdate", "EVP_DecryptUpdate"):
            function = getattr(library, name)
            function.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                 ctypes.POINTER(ctypes.c_int), ctypes.c_char_p, ctypes.c_int]
            function.restype = ctypes.c_int
        for name in ("EVP_EncryptFinal_ex", "EVP_DecryptFinal_ex"):
            function = getattr(library, name)
            function.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
            function.restype = ctypes.c_int
        _OPENSSL = library
        return library
    except Exception:
        _OPENSSL = False
        return False


def _library_blocks(library, key, data, encrypt):
    """Encrypt or decrypt many blocks of sixteen bytes at once.

    The library holds the cipher of the system and the key holds the key of
    the cipher. The data holds the blocks and the flag says whether they are
    encrypted or decrypted. The result holds the blocks that came out.
    """
    if len(data) % 16 != 0:
        raise ValueError("the data must hold whole blocks of sixteen bytes")
    context = _library_context(library, key, encrypt)
    if context is None:
        raise ValueError("the cipher of the system library failed")
    try:
        out = ctypes.create_string_buffer(len(data) + 32)
        written = ctypes.c_int(0)
        if encrypt:
            library.EVP_EncryptUpdate(context, out, ctypes.byref(written), data, len(data))
        else:
            library.EVP_DecryptUpdate(context, out, ctypes.byref(written), data, len(data))
        total = written.value
        final = ctypes.create_string_buffer(32)
        final_written = ctypes.c_int(0)
        if encrypt:
            library.EVP_EncryptFinal_ex(context, final, ctypes.byref(final_written))
        else:
            library.EVP_DecryptFinal_ex(context, final, ctypes.byref(final_written))
        return out.raw[:total] + final.raw[:final_written.value]
    finally:
        library.EVP_CIPHER_CTX_free(context)


def _library_context(library, key, encrypt):
    """Open the cipher of the system library for many blocks.

    The library holds the cipher of the system, the key holds the key of the
    cipher and the flag says whether the cipher encrypts or decrypts. The
    result holds the context of the cipher, or null when it did not open.
    """
    if len(key) not in (16, 24, 32):
        raise ValueError("AES key must be 16, 24 or 32 bytes")
    context = library.EVP_CIPHER_CTX_new()
    if not context:
        return None
    if len(key) == 16:
        cipher = library.EVP_aes_128_ecb()
    elif len(key) == 24:
        cipher = library.EVP_aes_192_ecb()
    else:
        cipher = library.EVP_aes_256_ecb()
    if encrypt:
        library.EVP_EncryptInit_ex(context, cipher, None, key, None)
    else:
        library.EVP_DecryptInit_ex(context, cipher, None, key, None)
    library.EVP_CIPHER_CTX_set_padding(context, 0)
    return context


def _library_block(library, context, block, encrypt):
    """Encrypt or decrypt one block of sixteen bytes.

    The context holds the cipher of the system and the block holds the bytes.
    The result holds the block that came out.
    """
    out = ctypes.create_string_buffer(48)
    written = ctypes.c_int(0)
    if encrypt:
        library.EVP_EncryptUpdate(context, out, ctypes.byref(written), block, 16)
    else:
        library.EVP_DecryptUpdate(context, out, ctypes.byref(written), block, 16)
    total = written.value
    final = ctypes.create_string_buffer(32)
    final_written = ctypes.c_int(0)
    if encrypt:
        library.EVP_EncryptFinal_ex(context, final, ctypes.byref(final_written))
    else:
        library.EVP_DecryptFinal_ex(context, final, ctypes.byref(final_written))
    return out.raw[:total] + final.raw[:final_written.value]


def _xor_bytes(left, right):
    """XOR two byte strings of the same length."""
    size = len(left)
    if size == 0:
        return b""
    value = int.from_bytes(left, "big") ^ int.from_bytes(right, "big")
    return value.to_bytes(size, "big")


def _gf_multiply(left, right):
    """Multiply two bytes in the Galois field."""
    result = 0
    for _ in range(8):
        if right & 1:
            result ^= left
        high = left & 0x80
        left = (left << 1) & 0xFF
        if high:
            left ^= 0x1B
        right >>= 1
    return result


def _build_sbox():
    """Return the AES substitution box.

    Every byte is replaced by its multiplicative inverse and the result is
    rotated and combined with the constant 0x63.
    """
    sbox = [0] * 256
    for value in range(256):
        inverse = 0
        for candidate in range(1, 256):
            if _gf_multiply(value, candidate) == 1:
                inverse = candidate
                break
        rotated = inverse
        combined = inverse
        for _ in range(4):
            rotated = ((rotated << 1) | (rotated >> 7)) & 0xFF
            combined ^= rotated
        sbox[value] = combined ^ 0x63
    return sbox


SBOX = _build_sbox()
INV_SBOX = [0] * 256
for _index in range(256):
    INV_SBOX[SBOX[_index]] = _index

RCON = [0x01]
for _index in range(1, 14):
    RCON.append(((RCON[-1] << 1) ^ 0x1B) & 0xFF if RCON[-1] & 0x80 else RCON[-1] << 1)


def _xtime(value):
    """Multiply a byte by two in the Galois field."""
    value <<= 1
    if value & 0x100:
        value = (value ^ 0x1B) & 0xFF
    return value


def _multiply(value, factor):
    """Multiply a byte by a small factor in the Galois field."""
    result = 0
    while factor:
        if factor & 1:
            result ^= value
        value = _xtime(value)
        factor >>= 1
    return result


def _build_tables():
    """Build the tables of the cipher.

    The first four tables hold the work of the encryption, and the last four
    hold the work of the decryption. Every table holds a word of thirty two
    bits for every byte, and the three tables that follow the first one hold
    the same word turned to the right.
    """
    encrypt = []
    decrypt = []
    for value in range(256):
        sub = SBOX[value]
        encrypt.append((_multiply(sub, 2) << 24) | (sub << 16) | (sub << 8) | _multiply(sub, 3))
        inv = INV_SBOX[value]
        decrypt.append((_multiply(inv, 14) << 24) | (_multiply(inv, 9) << 16)
                       | (_multiply(inv, 13) << 8) | _multiply(inv, 11))
    tables = []
    for table in (encrypt, decrypt):
        for shift in (0, 8, 16, 24):
            rotated = []
            for word in table:
                if shift == 0:
                    rotated.append(word)
                elif shift == 8:
                    rotated.append(((word >> 8) | (word << 24)) & 0xFFFFFFFF)
                elif shift == 16:
                    rotated.append(((word >> 16) | (word << 16)) & 0xFFFFFFFF)
                else:
                    rotated.append(((word >> 24) | (word << 8)) & 0xFFFFFFFF)
            tables.append(rotated)
    return tables


T0, T1, T2, T3, D0, D1, D2, D3 = _build_tables()


def _expand_key(key):
    """Expand the key into the words of every round.

    The result holds the words of the round keys, and every round holds four
    words of thirty two bits.
    """
    count = len(key) // 4
    rounds = count + 6
    words = [int.from_bytes(bytes(key[index * 4:index * 4 + 4]), "big")
             for index in range(count)]
    for index in range(count, 4 * (rounds + 1)):
        word = words[index - 1]
        if index % count == 0:
            word = ((word << 8) | (word >> 24)) & 0xFFFFFFFF
            word = ((SBOX[(word >> 24) & 0xFF] << 24) | (SBOX[(word >> 16) & 0xFF] << 16)
                    | (SBOX[(word >> 8) & 0xFF] << 8) | SBOX[word & 0xFF])
            word ^= RCON[index // count - 1] << 24
        elif count > 6 and index % count == 4:
            word = ((SBOX[(word >> 24) & 0xFF] << 24) | (SBOX[(word >> 16) & 0xFF] << 16)
                    | (SBOX[(word >> 8) & 0xFF] << 8) | SBOX[word & 0xFF])
        words.append(words[index - count] ^ word)
    keys = []
    for round_index in range(rounds + 1):
        keys.append(tuple(words[round_index * 4:round_index * 4 + 4]))
    return keys


def _inv_mix_word(word):
    """Apply the inverse mix column to one word of a round key.

    The word holds one column of the key. The inverse cipher adds the key
    before it mixes the columns, so the words of the middle rounds have to
    carry the mix of their own column.
    """
    b0 = (word >> 24) & 0xFF
    b1 = (word >> 16) & 0xFF
    b2 = (word >> 8) & 0xFF
    b3 = word & 0xFF
    r0 = _multiply(b0, 14) ^ _multiply(b1, 11) ^ _multiply(b2, 13) ^ _multiply(b3, 9)
    r1 = _multiply(b0, 9) ^ _multiply(b1, 14) ^ _multiply(b2, 11) ^ _multiply(b3, 13)
    r2 = _multiply(b0, 13) ^ _multiply(b1, 9) ^ _multiply(b2, 14) ^ _multiply(b3, 11)
    r3 = _multiply(b0, 11) ^ _multiply(b1, 13) ^ _multiply(b2, 9) ^ _multiply(b3, 14)
    return ((r0 << 24) | (r1 << 16) | (r2 << 8) | r3) & 0xFFFFFFFF


class AES:
    """The AES block cipher with a 128, 192 or 256 bit key."""

    def __init__(self, key):
        if len(key) not in (16, 24, 32):
            raise ValueError("AES key must be 16, 24 or 32 bytes")
        self.nk = len(key) // 4
        self.rounds = self.nk + 6
        self.round_keys = _expand_key(bytes(key))
        dec_keys = [self.round_keys[0]]
        for round_index in range(1, self.rounds):
            words = self.round_keys[round_index]
            dec_keys.append(tuple(_inv_mix_word(word) for word in words))
        dec_keys.append(self.round_keys[self.rounds])
        self.dec_keys = dec_keys

    def encrypt_block(self, block):
        """Encrypt a single 16 byte block."""
        data = bytes(block)
        w0 = int.from_bytes(data[0:4], "big")
        w1 = int.from_bytes(data[4:8], "big")
        w2 = int.from_bytes(data[8:12], "big")
        w3 = int.from_bytes(data[12:16], "big")
        keys = self.round_keys
        k0, k1, k2, k3 = keys[0]
        w0 ^= k0
        w1 ^= k1
        w2 ^= k2
        w3 ^= k3
        for round_index in range(1, self.rounds):
            a0 = (w0 >> 24) & 0xFF
            a1 = (w0 >> 16) & 0xFF
            a2 = (w0 >> 8) & 0xFF
            a3 = w0 & 0xFF
            b0 = (w1 >> 24) & 0xFF
            b1 = (w1 >> 16) & 0xFF
            b2 = (w1 >> 8) & 0xFF
            b3 = w1 & 0xFF
            c0 = (w2 >> 24) & 0xFF
            c1 = (w2 >> 16) & 0xFF
            c2 = (w2 >> 8) & 0xFF
            c3 = w2 & 0xFF
            d0 = (w3 >> 24) & 0xFF
            d1 = (w3 >> 16) & 0xFF
            d2 = (w3 >> 8) & 0xFF
            d3 = w3 & 0xFF
            t0 = T0[a0] ^ T1[b1] ^ T2[c2] ^ T3[d3]
            t1 = T0[b0] ^ T1[c1] ^ T2[d2] ^ T3[a3]
            t2 = T0[c0] ^ T1[d1] ^ T2[a2] ^ T3[b3]
            t3 = T0[d0] ^ T1[a1] ^ T2[b2] ^ T3[c3]
            k0, k1, k2, k3 = keys[round_index]
            w0 = t0 ^ k0
            w1 = t1 ^ k1
            w2 = t2 ^ k2
            w3 = t3 ^ k3
        a0 = (w0 >> 24) & 0xFF
        a1 = (w0 >> 16) & 0xFF
        a2 = (w0 >> 8) & 0xFF
        a3 = w0 & 0xFF
        b0 = (w1 >> 24) & 0xFF
        b1 = (w1 >> 16) & 0xFF
        b2 = (w1 >> 8) & 0xFF
        b3 = w1 & 0xFF
        c0 = (w2 >> 24) & 0xFF
        c1 = (w2 >> 16) & 0xFF
        c2 = (w2 >> 8) & 0xFF
        c3 = w2 & 0xFF
        d0 = (w3 >> 24) & 0xFF
        d1 = (w3 >> 16) & 0xFF
        d2 = (w3 >> 8) & 0xFF
        d3 = w3 & 0xFF
        k0, k1, k2, k3 = keys[self.rounds]
        w0 = ((SBOX[a0] << 24) | (SBOX[b1] << 16) | (SBOX[c2] << 8) | SBOX[d3]) ^ k0
        w1 = ((SBOX[b0] << 24) | (SBOX[c1] << 16) | (SBOX[d2] << 8) | SBOX[a3]) ^ k1
        w2 = ((SBOX[c0] << 24) | (SBOX[d1] << 16) | (SBOX[a2] << 8) | SBOX[b3]) ^ k2
        w3 = ((SBOX[d0] << 24) | (SBOX[a1] << 16) | (SBOX[b2] << 8) | SBOX[c3]) ^ k3
        return (w0.to_bytes(4, "big") + w1.to_bytes(4, "big")
                + w2.to_bytes(4, "big") + w3.to_bytes(4, "big"))

    def decrypt_block(self, block):
        """Decrypt a single 16 byte block."""
        data = bytes(block)
        w0 = int.from_bytes(data[0:4], "big")
        w1 = int.from_bytes(data[4:8], "big")
        w2 = int.from_bytes(data[8:12], "big")
        w3 = int.from_bytes(data[12:16], "big")
        keys = self.dec_keys
        k0, k1, k2, k3 = keys[self.rounds]
        w0 ^= k0
        w1 ^= k1
        w2 ^= k2
        w3 ^= k3
        for round_index in range(self.rounds - 1, 0, -1):
            a0 = (w0 >> 24) & 0xFF
            a1 = (w0 >> 16) & 0xFF
            a2 = (w0 >> 8) & 0xFF
            a3 = w0 & 0xFF
            b0 = (w1 >> 24) & 0xFF
            b1 = (w1 >> 16) & 0xFF
            b2 = (w1 >> 8) & 0xFF
            b3 = w1 & 0xFF
            c0 = (w2 >> 24) & 0xFF
            c1 = (w2 >> 16) & 0xFF
            c2 = (w2 >> 8) & 0xFF
            c3 = w2 & 0xFF
            d0 = (w3 >> 24) & 0xFF
            d1 = (w3 >> 16) & 0xFF
            d2 = (w3 >> 8) & 0xFF
            d3 = w3 & 0xFF
            t0 = D0[a0] ^ D1[d1] ^ D2[c2] ^ D3[b3]
            t1 = D0[b0] ^ D1[a1] ^ D2[d2] ^ D3[c3]
            t2 = D0[c0] ^ D1[b1] ^ D2[a2] ^ D3[d3]
            t3 = D0[d0] ^ D1[c1] ^ D2[b2] ^ D3[a3]
            k0, k1, k2, k3 = keys[round_index]
            w0 = t0 ^ k0
            w1 = t1 ^ k1
            w2 = t2 ^ k2
            w3 = t3 ^ k3
        a0 = (w0 >> 24) & 0xFF
        a1 = (w0 >> 16) & 0xFF
        a2 = (w0 >> 8) & 0xFF
        a3 = w0 & 0xFF
        b0 = (w1 >> 24) & 0xFF
        b1 = (w1 >> 16) & 0xFF
        b2 = (w1 >> 8) & 0xFF
        b3 = w1 & 0xFF
        c0 = (w2 >> 24) & 0xFF
        c1 = (w2 >> 16) & 0xFF
        c2 = (w2 >> 8) & 0xFF
        c3 = w2 & 0xFF
        d0 = (w3 >> 24) & 0xFF
        d1 = (w3 >> 16) & 0xFF
        d2 = (w3 >> 8) & 0xFF
        d3 = w3 & 0xFF
        k0, k1, k2, k3 = keys[0]
        w0 = ((INV_SBOX[a0] << 24) | (INV_SBOX[d1] << 16) | (INV_SBOX[c2] << 8) | INV_SBOX[b3]) ^ k0
        w1 = ((INV_SBOX[b0] << 24) | (INV_SBOX[a1] << 16) | (INV_SBOX[d2] << 8) | INV_SBOX[c3]) ^ k1
        w2 = ((INV_SBOX[c0] << 24) | (INV_SBOX[b1] << 16) | (INV_SBOX[a2] << 8) | INV_SBOX[d3]) ^ k2
        w3 = ((INV_SBOX[d0] << 24) | (INV_SBOX[c1] << 16) | (INV_SBOX[b2] << 8) | INV_SBOX[a3]) ^ k3
        return (w0.to_bytes(4, "big") + w1.to_bytes(4, "big")
                + w2.to_bytes(4, "big") + w3.to_bytes(4, "big"))


def ige_encrypt(data, key, iv):
    """Encrypt data with AES in IGE mode.

    The initialisation vector holds the previous ciphertext in its first half
    and the previous plaintext in its second half. The data length has to be
    a multiple of the block size.
    """
    if len(iv) != 32:
        raise ValueError("IGE initialisation vector must be 32 bytes")
    if len(data) % 16:
        raise ValueError("IGE data length must be a multiple of 16")
    library = _load_openssl()
    if library is not None:
        return _ige_with_library(library, data, key, iv, True)
    cipher = AES(key)
    encrypt = cipher.encrypt_block
    previous_cipher = iv[0:16]
    previous_plain = iv[16:32]
    result = bytearray()
    for offset in range(0, len(data), 16):
        plain = data[offset:offset + 16]
        mixed = bytes(a ^ b for a, b in zip(plain, previous_cipher))
        block = encrypt(mixed)
        encrypted = bytes(a ^ b for a, b in zip(block, previous_plain))
        result.extend(encrypted)
        previous_cipher = encrypted
        previous_plain = plain
    return bytes(result)


def ige_decrypt(data, key, iv):
    """Decrypt data with AES in IGE mode."""
    if len(iv) != 32:
        raise ValueError("IGE initialisation vector must be 32 bytes")
    if len(data) % 16:
        raise ValueError("IGE data length must be a multiple of 16")
    library = _load_openssl()
    if library is not None:
        return _ige_with_library(library, data, key, iv, False)
    cipher = AES(key)
    decrypt = cipher.decrypt_block
    previous_cipher = iv[0:16]
    previous_plain = iv[16:32]
    result = bytearray()
    for offset in range(0, len(data), 16):
        encrypted = data[offset:offset + 16]
        mixed = bytes(a ^ b for a, b in zip(encrypted, previous_plain))
        block = decrypt(mixed)
        plain = bytes(a ^ b for a, b in zip(block, previous_cipher))
        result.extend(plain)
        previous_cipher = encrypted
        previous_plain = plain
    return bytes(result)


def _ige_with_library(library, data, key, iv, encrypt):
    """Encrypt or decrypt data with AES in IGE mode through the library.

    The mode chains the blocks one after the other, so the library is asked
    for one block at a time. The bytes of the blocks are joined with the
    number of the blocks, which is much faster than a loop over the bytes.
    """
    previous_cipher = iv[0:16]
    previous_plain = iv[16:32]
    result = bytearray()
    context = _library_context(library, key, encrypt)
    if context is None:
        raise ValueError("the cipher of the system library failed")
    try:
        for offset in range(0, len(data), 16):
            block = data[offset:offset + 16]
            if encrypt:
                mixed = _xor_bytes(block, previous_cipher)
                encrypted = _library_block(library, context, mixed, True)
                # The chain of the mode keeps the ciphertext of the block, not
                # the output of the cipher alone.
                encrypted = _xor_bytes(encrypted, previous_plain)
                result.extend(encrypted)
                previous_cipher = encrypted
                previous_plain = block
            else:
                mixed = _xor_bytes(block, previous_plain)
                plain = _library_block(library, context, mixed, False)
                # The chain of the mode keeps the plaintext of the block, not
                # the output of the cipher alone.
                plain = _xor_bytes(plain, previous_cipher)
                result.extend(plain)
                previous_cipher = block
                previous_plain = plain
    finally:
        library.EVP_CIPHER_CTX_free(context)
    return bytes(result)


def ctr_crypt(data, key, iv):
    """Encrypt or decrypt data with AES in counter mode.

    The counter is the whole 16 byte block, counted up in big endian, and the
    key stream is the encryption of the counter under the key. The mode is its
    own inverse, so the same function both encrypts and decrypts.

    The transport of the Telegram protocol needs the mode: the bytes of the
    handshake and the bytes of every frame travel through one cipher whose
    counter never stops.
    """
    if len(iv) != 16:
        raise ValueError("CTR initialisation vector must be 16 bytes")
    library = _load_openssl()
    if library is not None:
        return _ctr_with_library(library, data, key, iv)
    cipher = AES(key)
    encrypt = cipher.encrypt_block
    counter = int.from_bytes(bytes(iv), "big")
    result = bytearray()
    for offset in range(0, len(data), 16):
        block = encrypt(counter.to_bytes(16, "big"))
        chunk = data[offset:offset + 16]
        result.extend(bytes(a ^ b for a, b in zip(chunk, block)))
        counter = (counter + 1) & ((1 << 128) - 1)
    return bytes(result)


def _ctr_with_library(library, data, key, iv):
    """Encrypt or decrypt data with AES in counter mode through the library.

    The blocks of the counter do not lean on each other, so the library is
    asked for the whole key stream at once.
    """
    size = len(data)
    if size == 0:
        return b""
    blocks = (size + 15) // 16
    counter = int.from_bytes(bytes(iv), "big")
    counters = bytearray()
    for _ in range(blocks):
        counters.extend(counter.to_bytes(16, "big"))
        counter = (counter + 1) & ((1 << 128) - 1)
    stream = _library_blocks(library, key, bytes(counters), True)
    return _xor_bytes(bytes(data), stream[:size])
