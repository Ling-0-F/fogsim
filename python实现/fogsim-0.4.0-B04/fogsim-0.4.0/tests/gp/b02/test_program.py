from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
import json
import math
import sys
from types import SimpleNamespace

import pytest

from fogsim.gp import evaluator
from fogsim.gp.ast import BinaryNode, ConstantNode, FeatureNode, ParsedExpression, SourceSpan, export_ast, structural_key
from fogsim.gp.features import Feature
from fogsim.gp.numerics import apply_binary
from fogsim.gp.parser import parse_expression
from fogsim.gp.program import CompiledExpression, Instruction, Opcode, compile_expression, validate_instructions
from fogsim.gp.evaluator import evaluate
from fogsim.model.resource import ResourceType
from fogsim.rules.contexts import graph_fingerprint
from ..feature_fixtures import fixture
from ..f64_oracle import VALUES, bits, expected, from_bits


def spelling(raw):
    value = from_bits(raw)
    return ("-1e309" if value < 0 else "1e309") if math.isinf(value) else repr(value)


@pytest.mark.parametrize("op", ["+", "-", "*", "/", "Max", "Min"])
@pytest.mark.parametrize("a_bits", VALUES[:14])
@pytest.mark.parametrize("b_bits", VALUES[:14])
def test_parsed_constant_expression_matrix(op, a_bits, b_bits, evidence_b02):
    text = f"({op} {spelling(a_bits)} {spelling(b_bits)})"
    compiled = compile_expression(parse_expression(text))
    actual = evaluate(compiled, None, None)
    want = expected(op, from_bits(a_bits), from_bits(b_bits))
    assert math.isnan(actual) if want == "nan" else bits(actual) == want
    assert [instruction.opcode for instruction in compiled.instructions] == [Opcode.PUSH_CONST, Opcode.PUSH_CONST, Opcode.APPLY_BINARY]
    assert compiled.max_stack == 2
    evidence_b02("expression-matrix", dict(text=text, a_bits=a_bits, b_bits=b_bits,
        expected=want, actual_bits=bits(actual), passed=True))


@pytest.mark.parametrize("resource_type", list(ResourceType))
@pytest.mark.parametrize("role", ["routing", "sequencing"])
def test_ten_features_through_live_model_program(resource_type, role, evidence_b02):
    f = fixture(resource_type, role)
    text = "(+ NIQ (+ WIQ (+ MRT (+ UT (+ DT (+ PT (+ TTIQ (+ TIS (+ TWT NTR)))))))))"
    compiled = compile_expression(parse_expression(text))
    before = graph_fingerprint(f.context)
    try:
        actual = evaluate(compiled, f.option, f.context)
        assert actual == (86.0 if role == "routing" else 88.75)
        assert compiled.max_stack == 10
    finally:
        assert graph_fingerprint(f.context) == before
    evidence_b02("live-feature-programs", dict(resource_type=resource_type.value, role=role,
        expression=text, actual_bits=bits(actual), max_stack=compiled.max_stack, readonly=True, passed=True))


def test_postorder_reads_and_operations_not_short_circuited(monkeypatch, evidence_b02):
    text = "(/ (- PT UT) (* WIQ DT))"
    compiled = compile_expression(parse_expression(text))
    visits = []

    def read(feature, option, context):
        visits.append(["read", feature.value])
        return {Feature.PT: math.inf, Feature.UT: math.inf, Feature.WIQ: 0.0, Feature.DT: 1.0}[feature]

    def apply(op, a, b):
        visits.append(["apply", op.value, bits(a), bits(b)])
        return apply_binary(op, a, b)

    monkeypatch.setattr(evaluator, "read_feature", read)
    monkeypatch.setattr(evaluator, "apply_binary", apply)
    result = evaluate(compiled, None, None)
    assert bits(result) == "3ff0000000000000"
    assert [v[:2] for v in visits] == [["read", "PT"], ["read", "UT"], ["apply", "-"],
        ["read", "WIQ"], ["read", "DT"], ["apply", "*"], ["apply", "/"]]
    assert math.isnan(from_bits(visits[-1][2]))
    evidence_b02("evaluation-order", dict(expression=text, visits=visits, result_bits=bits(result), passed=True))


def test_shared_node_occurrences_and_no_feature_cache(monkeypatch, evidence_b02):
    leaf = FeatureNode("PT")
    root = BinaryNode("+", leaf, leaf)
    assert root.left is root.right
    parsed = ParsedExpression("(+ PT PT)", root, (SourceSpan(0, 9), SourceSpan(3, 5), SourceSpan(6, 8)))
    compiled = compile_expression(parsed)
    reads = []
    def read(feature, option, context):
        reads.append(feature.value)
        return float(len(reads))
    monkeypatch.setattr(evaluator, "read_feature", read)
    assert evaluate(compiled, None, None) == 3.0
    assert reads == ["PT", "PT"]
    assert len(export_ast(root)["nodes"]) == 3
    assert [i.node_index for i in compiled.instructions] == [1, 2, 0]
    assert len(compile_expression(parse_expression("(+ 1 2)")).instructions) == 3
    evidence_b02("repeated-occurrences", dict(ast=export_ast(root), visits=reads,
        instruction_node_indices=[i.node_index for i in compiled.instructions], passed=True))


def test_exception_order_cleanup_and_next_call(monkeypatch):
    compiled = compile_expression(parse_expression("(+ PT (* UT DT))"))
    sentinel = RuntimeError("intentional read failure")
    visits = []
    def broken(feature, option, context):
        visits.append(feature.value)
        if feature == Feature.UT:
            raise sentinel
        return 7.0
    monkeypatch.setattr(evaluator, "read_feature", broken)
    with pytest.raises(RuntimeError) as caught:
        evaluate(compiled, None, None)
    assert caught.value is sentinel and visits == ["PT", "UT"]
    monkeypatch.setattr(evaluator, "read_feature", lambda feature, option, context: 2.0)
    assert evaluate(compiled, None, None) == 6.0
    assert not hasattr(compiled, "last_score") and not hasattr(compiled, "current_option")


def test_reentrant_and_parallel_use_without_captured_runtime(monkeypatch):
    compiled = compile_expression(parse_expression("(+ PT (* UT PT))"))
    original = evaluator.read_feature
    nested = []
    entered = False
    other = SimpleNamespace(processing_time=10.0, upload_time=2.0)
    def read(feature, option, context):
        nonlocal entered
        if not entered:
            entered = True
            nested.append(evaluate(compiled, other, None))
        return original(feature, option, context)
    monkeypatch.setattr(evaluator, "read_feature", read)
    assert evaluate(compiled, SimpleNamespace(processing_time=3.0, upload_time=2.0), None) == 9.0
    assert nested == [30.0]
    monkeypatch.setattr(evaluator, "read_feature", original)
    fingerprint = hash(compiled)
    def run(value):
        option = SimpleNamespace(processing_time=float(value), upload_time=2.0)
        return evaluate(compiled, option, None)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(run, range(1, 65))) == [3.0 * value for value in range(1, 65)]
    assert hash(compiled) == fingerprint


@pytest.mark.parametrize("op", ["Max", "Min"])
@pytest.mark.parametrize("a,b", [(VALUES[14], VALUES[15]), (VALUES[15], VALUES[14]),
    (VALUES[0], VALUES[1]), (VALUES[1], VALUES[0])])
def test_programmatic_raw_nan_and_zero_right_branch(op, a, b):
    compiled = CompiledExpression(BinaryNode(op, ConstantNode(a), ConstantNode(b)))
    assert bits(evaluate(compiled, None, None)) == b


@pytest.mark.parametrize("text,want", [
    ("(/ 1 -0.0)", "3ff0000000000000"),
    ("(/ 0 -0.0)", "3ff0000000000000"),
    ("(/ (* 1e309 0) 0)", "3ff0000000000000"),
    ("(+ (+ 1e16 -1e16) 1)", "3ff0000000000000"),
    ("(+ 1e16 (+ -1e16 1))", "0000000000000000"),
    ("(* 1e308 1e308)", "7ff0000000000000"),
    ("(* (* 1e308 1e308) 0)", "nan"),
    ("(/ -1e-300 1e300)", "8000000000000000"),
    ("(Max (* 1e309 0) 4)", "4010000000000000"),
    ("(Max 4 (* 1e309 0))", "nan"),
    ("(Min (* 1e309 0) 4)", "4010000000000000"),
    ("(Min 4 (* 1e309 0))", "nan"),
    ("(- (- 100 5) (/ 12 3))", "4056c00000000000"),
])
def test_frozen_nested_numeric_examples(text, want, evidence_b02):
    compiled = compile_expression(parse_expression(text))
    result = evaluate(compiled, None, None)
    assert math.isnan(result) if want == "nan" else bits(result) == want
    evidence_b02("nested-numerics", dict(text=text, expected=want, actual_bits=bits(result), passed=True))


def test_one_program_alternates_actual_model_graphs():
    a = fixture(ResourceType.EDGE, "routing")
    b = fixture(ResourceType.CLOUD, "sequencing")
    compiled = compile_expression(parse_expression("(+ PT WIQ)"))
    fingerprints = [graph_fingerprint(f.context) for f in (a, b)]
    program_hash = hash(compiled)
    for _ in range(10):
        assert evaluate(compiled, a.option, a.context) == 9.0
        assert evaluate(compiled, b.option, b.context) == 10.0
    assert [graph_fingerprint(f.context) for f in (a, b)] == fingerprints
    assert hash(compiled) == program_hash


@pytest.mark.parametrize("side", ["left", "right"])
def test_depth_2500_text_to_export_and_program(side, evidence_b02):
    limit = sys.getrecursionlimit()
    depth = 2500
    text = "(+ " * depth + "1" + " 1)" * depth if side == "left" else "(+ 1 " * depth + "1" + ")" * depth
    parsed = parse_expression(text)
    compiled = compile_expression(parsed)
    result = evaluate(compiled, None, None)
    exported = parsed.export_ast()
    assert result == 2501.0
    assert len(exported["nodes"]) == len(compiled.instructions) == len(parsed.spans) == 5001
    assert compiled.max_stack == (2 if side == "left" else 2501)
    variant = parse_expression(text.replace("1", "1d"))
    assert parsed.root == variant.root
    assert hash(parsed.root) == hash(variant.root)
    assert compiled == compile_expression(variant)
    assert len(repr(parsed.root)) < 100
    assert json.loads(json.dumps(exported)) == exported
    assert sys.getrecursionlimit() == limit
    evidence_b02("deep-2500", dict(side=side, depth=depth, text=text,
        ast=exported, spans=[dict(start=s.start,end=s.end) for s in parsed.spans],
        instruction_node_indices=[i.node_index for i in compiled.instructions],
        instruction_count=len(compiled.instructions), max_stack=compiled.max_stack,
        result_bits=bits(result), recursion_limit=limit, recursion_limit_unchanged=True, passed=True))


def test_deep_eof_diagnostic_is_iterative():
    from fogsim.gp.diagnostics import GPInputError
    text = "(+ 1 " * 2500 + "1"
    with pytest.raises(GPInputError) as caught:
        parse_expression(text)
    d = caught.value.diagnostic
    assert d.code == "GP_UNBALANCED_PARENTHESES"
    assert (d.start, d.end, d.line, d.column) == (len(text), len(text), 1, len(text) + 1)


def test_ast_program_and_metadata_are_deeply_immutable():
    parsed = parse_expression("(+ PT -0.0)")
    compiled = compile_expression(parsed)
    for obj, name, value in [(parsed,"text","UT"), (parsed.root,"left",None),
        (parsed.root.left,"feature",Feature.UT), (parsed.root.right,"bits","0000000000000000"),
        (parsed.spans[0],"start",3), (compiled,"max_stack",999),
        (compiled.instructions[0],"operand",Feature.UT)]:
        with pytest.raises(FrozenInstanceError):
            setattr(obj, name, value)
    export = parsed.export_ast()
    export["nodes"][1]["name"] = "UT"
    assert parsed.export_ast()["nodes"][1]["name"] == "PT"
    assert type(compiled.instructions) is tuple and type(compiled.structure_key) is tuple
    assert parse_expression("-0.0").root != parse_expression("0.0").root
    assert parse_expression("(- PT UT)").root != parse_expression("(- UT PT)").root


def test_compilation_never_reads_features(monkeypatch):
    def forbidden(*args):
        raise AssertionError("compiler attempted runtime feature read")
    monkeypatch.setattr(evaluator, "read_feature", forbidden)
    compiled = compile_expression(parse_expression("(+ PT PT)"))
    assert [i.opcode for i in compiled.instructions] == [Opcode.READ_FEATURE, Opcode.READ_FEATURE, Opcode.APPLY_BINARY]


@pytest.mark.parametrize("value", [None, [], 1, "PT"])
def test_compile_and_evaluate_programming_error_types(value):
    with pytest.raises(TypeError):
        compile_expression(value)
    with pytest.raises(TypeError):
        evaluate(value, None, None)


def test_static_validation_and_malformed_ast_rejected():
    with pytest.raises(TypeError):
        BinaryNode("+", FeatureNode("PT"), None)
    with pytest.raises(ValueError):
        BinaryNode("if", FeatureNode("PT"), FeatureNode("PT"))
    with pytest.raises(ValueError):
        FeatureNode("WR")
    with pytest.raises(ValueError):
        ConstantNode("7FF0000000000000")
    with pytest.raises(ValueError):
        Instruction("UNKNOWN", "+", 0)
    with pytest.raises(ValueError):
        validate_instructions(())
    with pytest.raises(ValueError):
        validate_instructions((Instruction(Opcode.APPLY_BINARY, "+", 0),))
    with pytest.raises(ValueError):
        validate_instructions((Instruction(Opcode.READ_FEATURE, "PT", 0), Instruction(Opcode.READ_FEATURE, "PT", 1)))
    # Defensive cycle check for corruption by trusted-Python escape hatches.
    node = BinaryNode("+", FeatureNode("PT"), FeatureNode("UT"))
    object.__setattr__(node, "left", node)
    try:
        with pytest.raises(ValueError, match="cyclic"):
            structural_key(node)
        with pytest.raises(ValueError, match="cyclic"):
            CompiledExpression(node)
    finally:
        object.__setattr__(node, "left", FeatureNode("PT"))
