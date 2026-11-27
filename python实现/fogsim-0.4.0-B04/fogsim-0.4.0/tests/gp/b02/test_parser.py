import json
from pathlib import Path

import pytest

from fogsim.gp.diagnostics import GPInputError
from fogsim.gp.parser import ASCII_WHITESPACE, parse_expression
from fogsim.gp.program import compile_expression
from fogsim.gp.evaluator import evaluate
from ..f64_oracle import bits

ERRORS = json.loads((Path(__file__).parent / "cases/parser-errors.json").read_text())


@pytest.mark.parametrize("case", ERRORS, ids=lambda c: c["name"])
def test_diagnostic_golden_cases(case, evidence_b02):
    with pytest.raises(GPInputError) as error:
        parse_expression(case["text"], role="routing", field_path="run.routing_rule.expression")
    d = error.value.diagnostic.to_dict()
    expected = dict(case["expected"], role="routing", field_path="run.routing_rule.expression")
    for key, value in expected.items():
        assert d[key] == value, (case["name"], d)
    evidence_b02("parser-errors", dict(name=case["name"], text=case["text"], expected=expected,
        actual=d, passed=True))


@pytest.mark.parametrize("white", list(ASCII_WHITESPACE))
@pytest.mark.parametrize("text", ["(+{w}PT{w}UT)", "{w}(+{w}PT{w}(Min{w}UT{w}DT){w}){w}", "{w}PT{w}", "{w}-0.0{w}"])
def test_all_six_ascii_whitespace_characters(white, text):
    source = text.format(w=white)
    parsed = parse_expression(source)
    assert parsed.text == source
    assert len(parsed.spans) == len(parsed.export_ast()["nodes"])
    assert parsed.spans[0].start == len(source) - len(source.lstrip(ASCII_WHITESPACE))


@pytest.mark.parametrize("text,want", [
    ("(+(* 2 3)(- 9 4))", 11.0),
    ("( /\r\n\t 2\v-0.0\f)", 1.0),
    ("(Max 0.0 -0.0)", -0.0),
    ("(Min -0.0 0.0)", 0.0),
])
def test_adjacent_calls_and_exact_case(text, want, evidence_b02):
    parsed = parse_expression(text)
    actual = evaluate(compile_expression(parsed), None, None)
    assert bits(actual) == bits(want)
    evidence_b02("parser-valid", dict(text=text, ast=parsed.export_ast(),
        spans=[dict(start=s.start, end=s.end) for s in parsed.spans], actual_bits=bits(actual), passed=True))


def test_preorder_spans_and_source_preserved():
    text = " \t(+ 010\r\n(* -0.0 PT))\n"
    parsed = parse_expression(text)
    assert parsed.text == text
    assert [(s.start, s.end) for s in parsed.spans] == [(2, 22), (5, 8), (10, 21), (13, 17), (18, 20)]
    assert [text[s.start:s.end] for s in parsed.spans] == ["(+ 010\r\n(* -0.0 PT))", "010", "(* -0.0 PT)", "-0.0", "PT"]
    assert parsed.export_ast() == {"root": 0, "nodes": [
        {"kind": "binary", "op": "+", "left": 1, "right": 2},
        {"kind": "constant", "bits": bits(10.0)},
        {"kind": "binary", "op": "*", "left": 3, "right": 4},
        {"kind": "constant", "bits": "8000000000000000"},
        {"kind": "feature", "name": "PT"}]}


@pytest.mark.parametrize("value", [None, True, 1, [], b"PT"])
def test_nontext_is_a_programming_error(value):
    with pytest.raises(TypeError):
        parse_expression(value)
