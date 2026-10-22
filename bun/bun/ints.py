"""The width of the integers of the language.

The integers of Bun are 64 bits wide, in every engine.  A program that
leaves the range is an error and not a number that wraps around: the
native backend holds its integers in 64 bits, and a program that
behaves differently under one engine is a bug in the engine, never a
difference in the language.

The helpers of `bun:bigint` are there for the protocols that need more
than 64 bits; they work on lists of bytes and not on the integers of the
language.
"""

from .errors import BunRuntimeError

INT_MIN = -(2 ** 63)
INT_MAX = 2 ** 63 - 1


def fits(value):
    """Report whether an integer fits in the width of the language."""
    return INT_MIN <= value <= INT_MAX


def check(value, message="integer overflow"):
    """Return the value, or fail when it does not fit in 64 bits."""
    if value < INT_MIN or value > INT_MAX:
        raise BunRuntimeError(message)
    return value
