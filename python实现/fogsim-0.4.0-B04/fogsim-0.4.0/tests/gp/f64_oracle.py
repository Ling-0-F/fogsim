"""Test-only exact-rational IEEE oracle, not another float arithmetic kernel.

Non-NaN finite results are computed as exact fractions then rounded once by
Python's fraction-to-binary64 conversion. This is Python contract evidence,
not an independent Java reference or a cross-language parity claim.
"""
from fractions import Fraction
import math
import struct


def bits(value):
    return struct.pack(">d", value).hex()


def from_bits(value):
    return struct.unpack(">d", bytes.fromhex(value))[0]


VALUES = (
    "0000000000000000", "8000000000000000",  # +/- zero
    "3ff0000000000000", "bff0000000000000",  # +/- one
    "4000000000000000", "c000000000000000",  # +/- two
    "0000000000000001", "8000000000000001",  # +/- min subnormal
    "0010000000000000", "8010000000000000",  # +/- min normal
    "7fefffffffffffff", "ffefffffffffffff",  # +/- max finite
    "7ff0000000000000", "fff0000000000000",  # +/- infinity
    "7ff8000000000001", "fff8000000000042",  # distinct quiet NaNs
)


def sign(value):
    return int(bits(value)[0], 16) >> 3


def signed_zero(negative):
    return "8000000000000000" if negative else "0000000000000000"


def infinity(negative):
    return "fff0000000000000" if negative else "7ff0000000000000"


def ordered(value):
    if math.isinf(value):
        return (0 if sign(value) else 2, Fraction(0))
    return (1, Fraction.from_float(value))


def rounded(exact, zero_sign=0):
    if not exact:
        return signed_zero(zero_sign)
    try:
        return bits(float(exact))
    except OverflowError:
        return infinity(exact < 0)


def expected(op, a, b):
    """Return raw bits, or 'nan' when only the arithmetic class is prescribed."""
    if op in ("Max", "Min"):
        if math.isnan(a) or math.isnan(b):
            return bits(b)
        ka, kb = ordered(a), ordered(b)
        chosen = b if ka == kb else (a if (ka > kb if op == "Max" else ka < kb) else b)
        return bits(chosen)
    if op == "/" and b == 0.0:
        return "3ff0000000000000"
    if math.isnan(a) or math.isnan(b):
        return "nan"
    if op in ("+", "-"):
        # Subtraction negates b exactly, before applying the addition oracle.
        if op == "-":
            b = from_bits(f"{int(bits(b), 16) ^ (1 << 63):016x}")
        if math.isinf(a) or math.isinf(b):
            if math.isinf(a) and math.isinf(b) and sign(a) != sign(b):
                return "nan"
            return bits(a if math.isinf(a) else b)
        return rounded(Fraction.from_float(a) + Fraction.from_float(b), sign(a) & sign(b))
    negative = sign(a) ^ sign(b)
    if op == "*":
        if (math.isinf(a) and b == 0.0) or (math.isinf(b) and a == 0.0):
            return "nan"
        if math.isinf(a) or math.isinf(b):
            return infinity(negative)
        return rounded(Fraction.from_float(a) * Fraction.from_float(b), negative)
    if math.isinf(a) and math.isinf(b):
        return "nan"
    if math.isinf(a):
        return infinity(negative)
    if math.isinf(b):
        return signed_zero(negative)
    return rounded(Fraction.from_float(a) / Fraction.from_float(b), negative)
