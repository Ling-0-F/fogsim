"""B01 read-only/RNG checks on a real, prepared dynamic runtime, in finally."""
import ast
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
import random

import pytest

from fogsim import create_dynamic_context
from fogsim.gp import diagnostics, features, numerics
from fogsim.gp.diagnostics import GPCode, GPDiagnostic, GPInputError
from fogsim.gp.features import Feature, read_feature
from fogsim.gp.numerics import BinaryFunction, apply_binary
from fogsim.instances.source import RandomWorkflowSource
from fogsim.randomness import samplers
from fogsim.rules import specs
from fogsim.rules.contexts import RoutingContext, StateView
from fogsim.rules.specs import RuleSpec
from .f64_oracle import bits


def snapshot(root):
    """Observe identity, order and fields, including non-dataclass runtime objects."""
    seen = set()

    def walk(value):
        if type(value) is float:
            return ("f64", bits(value))
        if value is None or isinstance(value, (str, int, bool, bytes, Enum)):
            return value
        identity = id(value)
        if identity in seen:
            return ("ref", identity)
        seen.add(identity)
        if isinstance(value, Path):
            return ("path", identity, str(value))
        if isinstance(value, dict):
            content = tuple((walk(k), walk(v)) for k, v in value.items())
        elif isinstance(value, (list, tuple)):
            content = tuple(walk(v) for v in value)
        elif is_dataclass(value):
            content = tuple((f.name, walk(getattr(value, f.name))) for f in fields(value))
        elif isinstance(value, (set, frozenset)):
            content = frozenset(walk(v) for v in value)
        elif hasattr(value, "__dict__"):
            content = walk(vars(value))
        else:
            raise TypeError(f"unobserved object: {type(value)}")
        return (type(value).__qualname__, identity, content)

    return walk(root)


@pytest.mark.parametrize("failure", [False, True])
def test_b01_no_writes_no_rng_attempts(tmp_path, monkeypatch, failure, evidence):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))
    from dynamic_helpers import config
    context = create_dynamic_context(config(tmp_path, devices=2, edges=1, clouds=1))
    engine = context.engine
    workflow = next(iter(engine.state.pending_arrivals.values()))
    candidate = workflow.tasks[0].options[0]
    view = StateView(engine.state.clock_time, tuple(engine.state.resources_by_id.values()), (workflow,), ())
    ctx = RoutingContext(candidate.task, tuple(candidate.task.options), view)
    before = snapshot(context)
    original_getstate = random.Random.getstate
    rng_before = original_getstate(context.inputs.rng)
    module_rng_before = random.getstate()
    attempts = []

    def forbidden(name):
        def fail(*args, **kwargs):
            attempts.append(name)
            raise AssertionError(f"forbidden RNG/source entry: {name}")
        return fail

    for name in ("random", "randint", "randrange", "getrandbits", "uniform", "choice", "choices",
                 "sample", "shuffle", "expovariate", "gauss", "normalvariate", "seed", "setstate"):
        monkeypatch.setattr(random, name, forbidden("random." + name))
        monkeypatch.setattr(random.Random, name, forbidden("Random." + name))
    monkeypatch.setattr(random.Random, "__init__", forbidden("Random.__init__"))
    monkeypatch.setattr(random.SystemRandom, "__init__", forbidden("SystemRandom.__init__"))
    monkeypatch.setattr(random.SystemRandom, "random", forbidden("SystemRandom.random"))
    monkeypatch.setattr(random.SystemRandom, "getrandbits", forbidden("SystemRandom.getrandbits"))
    for cls in (samplers.UniformRealSampler, samplers.UniformIntegerSampler, samplers.ExponentialSampler,
                samplers.WeightSampler, samplers.CloudBandwidthSampler, samplers.EdgeBandwidthSampler):
        monkeypatch.setattr(cls, "sample", forbidden(cls.__name__ + ".sample"))
    monkeypatch.setattr(RandomWorkflowSource, "generate", forbidden("source.generate"))
    try:
        RuleSpec.from_mapping("routing", {"kind": "gp", "expression": "(+ PT UT)"})
        for feature in Feature:
            read_feature(feature, candidate, ctx)
        for op in BinaryFunction:
            apply_binary(op, 1.0, -0.0)
        if failure:
            with pytest.raises(ValueError):
                read_feature("WR", candidate, ctx)
            with pytest.raises(TypeError):
                apply_binary("+", 1, 2.0)
            with pytest.raises(GPInputError):
                RuleSpec.from_mapping("routing", {"kind": "gp", "expression": "\r\n\t"})
        d = GPDiagnostic.at_source(GPCode.UNKNOWN_FEATURE, "unknown", text="x\r\n?", start=3, end=4,
            field_path="rule.expression")
        assert d.line == 2
    finally:
        assert snapshot(context) == before
        assert original_getstate(context.inputs.rng) == rng_before
        assert random.getstate() == module_rng_before
        assert attempts == []
        evidence("purity", dict(path="error" if failure else "normal", state_identity_order_unchanged=True,
            native_rng_unchanged=True, module_rng_unchanged=True, rng_source_attempts=attempts,
            scope=["model", "queue", "event_heap", "source", "archive", "statistics", "trace", "context"], passed=True))


def test_new_modules_have_no_random_source_or_engine_dependencies():
    blocked = {"random", "secrets", "os", "numpy", "sampler", "samplers", "source", "engine", "context", "simulation"}
    for module in (diagnostics, features, numerics, specs):
        tree = ast.parse(Path(module.__file__).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert not any(blocked.intersection(name.split(".")) for name in names)
