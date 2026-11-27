import math

import pytest

from fogsim.gp.numerics import BinaryFunction, apply_binary
from .f64_oracle import VALUES, bits, expected, from_bits


@pytest.mark.parametrize("op", ("+", "-", "*", "/", "Max", "Min"))
@pytest.mark.parametrize("a_bits", VALUES)
@pytest.mark.parametrize("b_bits", VALUES)
def test_six_by_sixteen_by_sixteen(op, a_bits, b_bits, evidence):
    a, b = from_bits(a_bits), from_bits(b_bits)
    want = expected(op, a, b)
    actual = apply_binary(op, a, b)
    passed = math.isnan(actual) if want == "nan" else bits(actual) == want
    evidence("numeric-matrix", dict(op=op, a_bits=a_bits, b_bits=b_bits,
        expected=want, actual_bits=bits(actual), actual_class="nan" if math.isnan(actual) else "non_nan",
        passed=passed, classification="CONTRACT_CHECK_PASSED" if passed else "FAILED"))
    assert passed, (op, a_bits, b_bits, want, bits(actual))


def test_dual_zero_generated_from_nonnegative_features():
    negative = apply_binary("-", 0.0, 4.0)
    zero = apply_binary("-", 0.2, 0.2)
    denominator = apply_binary("*", negative, zero)
    assert bits(denominator) == "8000000000000000"
    assert bits(apply_binary("/", 0.0, denominator)) == "3ff0000000000000"
    assert bits(apply_binary("/", float("nan"), denominator)) == "3ff0000000000000"


def test_grouping_overflow_and_underflow():
    assert bits(apply_binary("+", apply_binary("+", 1e16, -1e16), 1.0)) == "3ff0000000000000"
    assert bits(apply_binary("+", 1e16, apply_binary("+", -1e16, 1.0))) == "0000000000000000"
    overflow = apply_binary("*", 1e308, 1e308)
    assert bits(overflow) == "7ff0000000000000"
    assert math.isnan(apply_binary("*", overflow, 0.0))
    assert bits(apply_binary("/", -1e-300, 1e300)) == "8000000000000000"
    assert bits(apply_binary("/", 1.0, from_bits(VALUES[6]))) == "7ff0000000000000"


def test_alphabet_and_programming_errors():
    assert tuple(x.value for x in BinaryFunction) == ("+", "-", "*", "/", "Max", "Min")
    for op in ("max", "min", "if", "**"):
        with pytest.raises(ValueError):
            apply_binary(op, 1.0, 2.0)
    with pytest.raises(TypeError):
        apply_binary("+", True, 1.0)
    with pytest.raises(TypeError):
        apply_binary("+", 1, 1.0)
