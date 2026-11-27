import ast as python_ast
import hashlib
import json
from pathlib import Path
import random
import sys

import pytest

from fogsim import create_dynamic_context
from fogsim.gp import ast, evaluator, parser, program
from fogsim.gp.diagnostics import GPInputError
from fogsim.gp.evaluator import evaluate
from fogsim.gp.features import Feature
from fogsim.gp.parser import parse_expression
from fogsim.gp.program import compile_expression
from fogsim.instances.source import RandomWorkflowSource
from fogsim.randomness import samplers
from fogsim.rules.contexts import RoutingContext, StateView
from ..test_purity import snapshot
from conftest import step


@pytest.mark.parametrize("layer", ["parse", "compile", "evaluate"])
@pytest.mark.parametrize("failure", [False, True])
def test_each_layer_finally_state_and_rng(tmp_path, monkeypatch, layer, failure, evidence_b02):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "unit"))
    from dynamic_helpers import config
    context = create_dynamic_context(config(tmp_path, devices=2, edges=1, clouds=1))
    step(context.engine)  # Legitimate sampling window closes before observation.
    engine = context.engine
    workflow = next(iter(engine.state.active_workflows.values()))
    candidate = workflow.tasks[0].options[0]
    ctx = RoutingContext(candidate.task, tuple(candidate.task.options), StateView.from_state(engine.state))
    parsed = parse_expression("(+ PT (* UT DT))")
    compiled = compile_expression(parsed)
    malformed = parse_expression("(+ PT UT)")
    # Trusted-Python corruption forces failure after traversal has started.
    object.__setattr__(malformed.root.right, "feature", "WR")
    program_before = hash(compiled)
    state_before = snapshot(context)
    original_getstate = random.Random.getstate
    rng_before = original_getstate(context.inputs.rng)
    module_before = random.getstate()
    attempts = []

    def forbidden(name):
        def fail(*args, **kwargs):
            attempts.append(name)
            raise AssertionError(f"forbidden RNG/source entry: {name}")
        return fail

    for name in dir(random.Random):
        if not name.startswith("_") and name != "getstate" and callable(getattr(random.Random, name)):
            monkeypatch.setattr(random.Random, name, forbidden("Random." + name))
            if callable(getattr(random, name, None)):
                monkeypatch.setattr(random, name, forbidden("random." + name))
    monkeypatch.setattr(random.Random, "__init__", forbidden("Random.__init__"))
    monkeypatch.setattr(random.SystemRandom, "__init__", forbidden("SystemRandom.__init__"))
    monkeypatch.setattr(random.SystemRandom, "random", forbidden("SystemRandom.random"))
    monkeypatch.setattr(random.SystemRandom, "getrandbits", forbidden("SystemRandom.getrandbits"))
    for cls in (samplers.UniformRealSampler, samplers.UniformIntegerSampler, samplers.ExponentialSampler,
                samplers.WeightSampler, samplers.CloudBandwidthSampler, samplers.EdgeBandwidthSampler):
        monkeypatch.setattr(cls, "sample", forbidden(cls.__name__ + ".sample"))
    monkeypatch.setattr(RandomWorkflowSource, "generate", forbidden("source.generate"))
    sentinel = RuntimeError("intentional second feature failure")
    if layer == "evaluate" and failure:
        read = evaluator.read_feature
        def broken(feature, option, context):
            if feature == Feature.UT:
                raise sentinel
            return read(feature, option, context)
        monkeypatch.setattr(evaluator, "read_feature", broken)
    try:
        if layer == "parse":
            if failure:
                with pytest.raises(GPInputError):
                    parse_expression("(+ PT UT)\u00a0")
            else:
                parse_expression("(+ PT (* UT DT))")
        elif layer == "compile":
            if failure:
                with pytest.raises(TypeError):
                    compile_expression(malformed)
            else:
                compile_expression(parsed)
        elif failure:
            with pytest.raises(RuntimeError) as caught:
                evaluate(compiled, candidate, ctx)
            assert caught.value is sentinel
        else:
            evaluate(compiled, candidate, ctx)
    finally:
        assert snapshot(context) == state_before
        assert original_getstate(context.inputs.rng) == rng_before
        assert random.getstate() == module_before
        assert hash(compiled) == program_before
        assert attempts == []
        digest = hashlib.sha256(json.dumps(rng_before).encode()).hexdigest()
        evidence_b02("purity", dict(layer=layer, path="failure" if failure else "normal",
            state_identity_order_unchanged=True, native_rng_state_sha256=digest, native_rng_unchanged=True,
            module_rng_unchanged=True, program_unchanged=True, rng_source_attempts=attempts,
            snapshot_scope=["context", "model", "queues", "event_heaps", "source", "archive", "statistics", "trace"], passed=True))


def test_new_modules_no_runtime_random_or_dynamic_execution_dependencies():
    blocked = {"random", "secrets", "os", "numpy", "samplers", "source", "engine", "simulation", "context"}
    for module in (ast, parser, program, evaluator):
        tree = python_ast.parse(Path(module.__file__).read_text())
        for node in python_ast.walk(tree):
            names = ([alias.name for alias in node.names] if isinstance(node, python_ast.Import) else
                     [node.module or ""] if isinstance(node, python_ast.ImportFrom) else [])
            assert not any(blocked.intersection(name.split(".")) for name in names)
            if isinstance(node, python_ast.Call) and isinstance(node.func, python_ast.Name):
                assert node.func.id not in ("eval", "exec", "__import__", "compile")


def test_conversion_failure_cause_and_unknown_exception_propagation(monkeypatch):
    failure = ValueError("injected conversion failure")
    def broken(number):
        raise failure
    monkeypatch.setattr(parser, "float", broken, raising=False)
    with pytest.raises(GPInputError) as caught:
        parse_expression("1.0", role="sequencing", field_path="run.sequencing_rule.expression")
    assert caught.value.__cause__ is failure
    assert caught.value.code == "GP_INVALID_CONSTANT"
    assert caught.value.diagnostic.token == "1.0"
    error = RuntimeError("unknown implementation error")
    def unknown(number):
        raise error
    monkeypatch.setattr(parser, "float", unknown)
    with pytest.raises(RuntimeError) as caught:
        parse_expression("1.0")
    assert caught.value is error
