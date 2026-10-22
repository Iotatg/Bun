"""Arbitrary precision integer helpers.

The runtime works with 64 bit integers, but a few protocols (RSA, Diffie
Hellman) need much larger numbers. These helpers represent big integers as
lists of bytes in little endian order, which keeps them printable with the
regular list tooling and cheap to pass around.
"""


def _to_bytes(value, name):
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if not isinstance(value, list):
        raise ValueError("%s expects a list of bytes" % name)
    out = bytearray()
    for item in value:
        if not isinstance(item, int) or isinstance(item, bool):
            raise ValueError("%s expects a list of byte values" % name)
        if item < 0 or item > 255:
            raise ValueError("%s expects byte values between 0 and 255" % name)
        out.append(item)
    return bytes(out)


def _to_int(value, name="bigint"):
    return int.from_bytes(_to_bytes(value, name), "little")


def _int_to_bytes(value):
    """Return the minimal little endian representation of a non-negative int."""
    length = (value.bit_length() + 7) // 8
    return value.to_bytes(length, "little") if length else b""


def from_bytes(data):
    """Return the normalised little endian representation of a byte list.

    The bytes are little endian, so the most important byte comes last.  The
    normalisation drops the empty bytes at the end of the list, because they do
    not change the value of the number.  The bytes at the start of the list
    must stay, because they hold the least important bytes of the number.
    """
    raw = _to_bytes(data, "bigint")
    end = len(raw)
    while end > 0 and raw[end - 1] == 0:
        end -= 1
    return list(raw[:end])


def to_bytes(value, size=0):
    """Return the little endian representation of a big integer."""
    raw = _to_bytes(value, "bigint")
    if size <= 0:
        size = len(raw)
    if len(raw) > size:
        raise ValueError("bigint does not fit into %d bytes" % size)
    return list(raw) + [0] * (size - len(raw))


def to_int(value):
    """Return the value of a big integer as a regular integer."""
    return _to_int(value)


def from_int(value):
    """Return the little endian representation of a regular integer."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("bigint expects an integer")
    if value < 0:
        raise ValueError("bigint expects a non-negative integer")
    length = (value.bit_length() + 7) // 8
    return list(value.to_bytes(length, "little")) if length else []


def compare(left, right):
    """Compare two big integers, returning -1, 0 or 1."""
    a = _to_int(left)
    b = _to_int(right)
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def add(left, right):
    """Return the sum of two big integers."""
    return from_bytes(_int_to_bytes(_to_int(left) + _to_int(right)))


def subtract(left, right):
    """Return the difference of two big integers, assuming left >= right."""
    a = _to_int(left)
    b = _to_int(right)
    if a < b:
        raise ValueError("bigint subtraction would go negative")
    return from_bytes(_int_to_bytes(a - b))


def multiply(left, right):
    """Return the product of two big integers."""
    product = _to_int(left) * _to_int(right)
    return from_bytes(_int_to_bytes(product))


def remainder(left, right):
    """Return the remainder of a division of two big integers."""
    divisor = _to_int(right)
    if divisor == 0:
        raise ValueError("bigint division by zero")
    value = _to_int(left) % divisor
    return from_bytes(_int_to_bytes(value))


def divide(left, right):
    """Return the quotient of a division of two big integers."""
    divisor = _to_int(right)
    if divisor == 0:
        raise ValueError("bigint division by zero")
    value = _to_int(left) // divisor
    return from_bytes(_int_to_bytes(value))


def gcd(left, right):
    """Return the greatest common divisor of two big integers."""
    a = _to_int(left)
    b = _to_int(right)
    while b:
        a, b = b, a % b
    return from_bytes(_int_to_bytes(a))


def multiply_mod(left, right, modulus):
    """Return the product of two integers reduced modulo a modulus.

    The operands and the result have to fit into a regular integer, the
    intermediate product may be larger. This keeps modular arithmetic exact
    without the caller having to switch to the byte list representation.
    """
    mod = int(modulus)
    if mod == 0:
        raise ValueError("bigint division by zero")
    if mod < 0:
        mod = -mod
    return (int(left) * int(right)) % mod


def multiply_mod_bytes(left, right, modulus):
    """Return the product of two big integers reduced modulo a modulus.

    The operands and the result are little endian byte lists, so the
    arithmetic works on numbers of any size. The intermediate product may be
    larger than the modulus.
    """
    mod = _to_int(modulus)
    if mod == 0:
        raise ValueError("bigint division by zero")
    if mod < 0:
        mod = -mod
    return from_bytes(_int_to_bytes((_to_int(left) * _to_int(right)) % mod))


def pow_mod(base, exponent, modulus):
    """Raise a big integer to a power modulo another big integer."""
    mod = _to_int(modulus)
    if mod <= 0:
        raise ValueError("bigint modulus must be positive")
    power = _to_int(exponent)
    if power < 0:
        raise ValueError("bigint exponent must be non-negative")
    value = pow(_to_int(base), power, mod)
    return from_bytes(_int_to_bytes(value))


def _rho_step(value, constant, modulus):
    """One step of the rho walk."""
    return (value * value + constant) % modulus


def _brent_factor(number, constant):
    """Return a factor of the number found by the Brent variant of the rho method.

    The walk keeps a window of the values it visited, and the product of the
    differences of the window gives a factor of the number.
    """
    value = 2
    window = 128
    divisor = 1
    radius = 1
    product = 1
    steps = 0
    while divisor == 1 and steps < 1_000_000:
        anchor = value
        index = 0
        while index < radius and steps < 1_000_000:
            value = _rho_step(value, constant, number)
            steps += 1
            index += 1
        taken = 0
        while taken < radius and divisor == 1 and steps < 1_000_000:
            mark = value
            limit = min(radius - taken, window)
            inner = 0
            while inner < limit:
                value = _rho_step(value, constant, number)
                difference = abs(anchor - value)
                if difference == 0:
                    product = 0
                else:
                    product = (product * difference) % number
                steps += 1
                inner += 1
                if product == 0 or steps >= 1_000_000:
                    break
            if product != 0:
                divisor = gcd_int(product, number)
            else:
                difference = abs(anchor - mark)
                if difference == 0:
                    return 1
                divisor = gcd_int(difference, number)
            taken += limit
        radius *= 2
    if divisor == number:
        return 1
    return divisor


def gcd_int(left, right):
    """Return the greatest common divisor of two plain integers."""
    while right:
        left, right = right, left % right
    return left


def factorize(value):
    """Return the two factors of a semiprime as little endian byte lists.

    The handshake of the Telegram protocol asks the client to factor a product
    of two large primes. The walk of the rho method needs tens of thousands of
    steps, so the runtime keeps the arithmetic of the walk in plain integers.
    The result holds the two factors, the smaller one first, or an empty list
    when the number has no factor the walk can find.
    """
    number = _to_int(value)
    if number <= 1:
        return []
    if number % 2 == 0:
        return [from_bytes(_int_to_bytes(2)), from_bytes(_int_to_bytes(number // 2))]
    for constant in range(1, 32):
        factor = _brent_factor(number, constant)
        if factor > 1 and factor < number:
            other = number // factor
            low, high = (factor, other) if factor < other else (other, factor)
            return [from_bytes(_int_to_bytes(low)), from_bytes(_int_to_bytes(high))]
    return []
