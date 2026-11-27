from decimal import Decimal
from fractions import Fraction
import math

import pytest

from fogsim.gp.ast import ConstantNode
from fogsim.gp.diagnostics import GPInputError
from fogsim.gp.parser import parse_expression
from fogsim.gp.program import compile_expression
from fogsim.gp.evaluator import evaluate
from ..f64_oracle import bits


VALID = [
    ("-1", "bff0000000000000"), (".5", "3fe0000000000000"), ("1.", "3ff0000000000000"),
    ("1e+3", "408f400000000000"), ("1d", "3ff0000000000000"), ("1F", "3ff0000000000000"),
    ("010", "4024000000000000"), ("-077", "c053400000000000"), ("00", "0000000000000000"),
    ("-00", "8000000000000000"), ("16777217F", "4170000010000000"),
    ("1e309", "7ff0000000000000"), ("-1e309", "fff0000000000000"),
    ("1e-9999", "0000000000000000"), ("-1e-9999", "8000000000000000"),
    ("1.00000000000000011102230246251565404236316680908203125", "3ff0000000000000"),
    ("1.00000000000000011102230246251565404236316680908203126", "3ff0000000000001"),
    ("1.7976931348623157e308", "7fefffffffffffff"),
    ("1.7976931348623158e308", "7fefffffffffffff"),
    ("1.7976931348623159e308", "7ff0000000000000"),
    ("2.2250738585072014e-308", "0010000000000000"),
    ("2.225073858507201e-308", "000fffffffffffff"),
    ("4.9406564584124654e-324", "0000000000000001"),
    ("2.4703282292062327e-324", "0000000000000000"),
    ("2.4703282292062328e-324", "0000000000000001"),
    ("-2.4703282292062327e-324", "8000000000000000"),
]


@pytest.mark.parametrize("text,want", VALID)
def test_decimal_boundaries_and_suffixes(text, want, evidence_b02):
    parsed = parse_expression(text)
    assert type(parsed.root) is ConstantNode
    assert parsed.root.bits == want
    actual = evaluate(compile_expression(parsed), None, None)
    assert bits(actual) == want
    # Independent lexical-input-to-exact-rational route; no parser float result
    # is fed back as the oracle input. Overflow and signed zero stay explicit.
    decimal = Decimal(text[:-1] if text[-1] in "dDfF" else text)
    try:
        expected = float(Fraction(decimal))
    except OverflowError:
        expected = -math.inf if decimal.is_signed() else math.inf
    if expected == 0.0 and decimal.is_signed():
        expected = -0.0
    assert bits(expected) == want
    evidence_b02("constant-boundaries", dict(text=text, expected_bits=want, actual_bits=bits(actual),
        original_token=parsed.text[parsed.spans[0].start:parsed.spans[0].end],
        java17_compared=False, passed=True))


@pytest.mark.parametrize("text", ["+1", "+0.0", "08", "01.2", "01e2", "0x10", "1L", "1_000",
    "-08", "--1", ".", "-.", "1e", "1e+", "00F", "010d", "1ff", "1.0dd", "NaN", "nan", "Infinity", "inf"])
def test_unapproved_constant_spellings_rejected(text):
    with pytest.raises(GPInputError):
        parse_expression(text)


@pytest.mark.parametrize("text", ["1", "1.0", "1d", "1D", "1f", "1F", "1e0", "01"])
def test_equivalent_constant_structure_without_source_rewriting(text):
    parsed = parse_expression(text)
    assert parsed.text == text
    assert parsed.root == parse_expression("1").root
    assert parsed.root.bits == "3ff0000000000000"


def test_long_number_avoids_python_integer_string_limit():
    token = "9" * 5000
    assert parse_expression(token).root.bits == "7ff0000000000000"
    assert parse_expression("-" + "0" * 5000).root.bits == "8000000000000000"
