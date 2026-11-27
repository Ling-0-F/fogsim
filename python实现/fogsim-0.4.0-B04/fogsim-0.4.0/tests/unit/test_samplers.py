"""V04/V05 deterministic boundary, draw-order and parameter ownership checks."""
from dataclasses import FrozenInstanceError, fields
import math
import random
import pytest
from fogsim.errors import InputError
from fogsim.experiment_config import SamplerParameters, WorkflowTypeRange
from fogsim.randomness.samplers import (
    UniformRealSampler, UniformIntegerSampler, ExponentialSampler, WeightSampler,
    CloudBandwidthSampler, EdgeBandwidthSampler, make_samplers,
)


class ScriptedRng:
    def __init__(self, values=()):
        self.values = iter(values)
        self.calls = []

    def random(self):
        self.calls.append(("random",))
        return next(self.values)

    def randint(self, lower, upper):
        self.calls.append(("randint", lower, upper))
        return next(self.values)

    def expovariate(self, rate):
        self.calls.append(("expovariate", rate))
        return next(self.values)


def test_uniform_rejects_only_zero_and_preserves_scaling():
    sampler = UniformRealSampler(0.1, 0.3)
    rng = ScriptedRng([0.0, -0.0, 0.3])
    value = sampler.sample(rng)
    assert value.hex() == "0x1.47ae147ae147ap-3"
    assert value != 0.1 + 0.3 * (0.3 - 0.1)
    assert rng.calls == [("random",)] * 3
    assert UniformRealSampler(-10, -2).sample(ScriptedRng([0.5])) == -6


def test_rounded_endpoints_are_not_clamped_or_redrawn():
    sampler = UniformRealSampler(1.0, math.nextafter(1.0, math.inf))
    rng = ScriptedRng([math.nextafter(0.0, 1.0)])
    assert sampler.sample(rng) == sampler.lower
    assert rng.calls == [("random",)]
    rng = ScriptedRng([0.75])
    assert sampler.sample(rng) == sampler.upper
    assert rng.calls == [("random",)]
    # With u=1-2^-53, u*(1+2^-52) rounds down to 1; adding
    # (1-u)=2^-53 is a tie that rounds to 1 again. Do not "fix" it.
    rng = ScriptedRng([math.nextafter(1.0, 0.0)])
    assert sampler.sample(rng).hex() == "0x1.0000000000000p+0"
    assert rng.calls == [("random",)]


@pytest.mark.parametrize("u,weight,bandwidth", [
    (math.nextafter(0.0, 1.0), 4, 256), (math.nextafter(0.2, 0), 4, 256),
    (0.2, 2, 512), (math.nextafter(0.8, 0), 2, 512),
    (0.8, 1, 128), (math.nextafter(1.0, 0), 1, 128),
])
def test_discrete_thresholds(u, weight, bandwidth):
    for sampler, expected in ((WeightSampler(), weight), (CloudBandwidthSampler(), bandwidth)):
        rng = ScriptedRng([0, u])
        assert sampler.sample(rng) == expected
        assert len(rng.calls) == 2


def test_integer_inclusive_and_singleton_always_call_randint():
    rng = ScriptedRng([-2, 4])
    sampler = UniformIntegerSampler(-2, 4)
    assert [sampler.sample(rng), sampler.sample(rng)] == [-2, 4]
    assert rng.calls == [("randint", -2, 4)] * 2
    actual = random.Random(123)
    before = actual.getstate()
    assert UniformIntegerSampler(7, 7).sample(actual) == 7
    assert actual.getstate() != before


def test_exponential_zero_is_not_retried():
    rng = ScriptedRng([0.0])
    assert ExponentialSampler(100).sample(rng) == 0.0
    assert rng.calls == [("expovariate", 0.01)]


def test_constant_does_not_touch_rng():
    rng = ScriptedRng()
    assert EdgeBandwidthSampler().sample(rng) == 1024
    assert rng.calls == []


@pytest.mark.parametrize("factory", [
    lambda: UniformRealSampler(1, 1), lambda: UniformRealSampler(2, 1),
    lambda: UniformRealSampler(True, 2), lambda: UniformRealSampler(0, float("nan")),
    lambda: UniformRealSampler(-float("inf"), 1), lambda: UniformRealSampler(0, 10**400),
    lambda: UniformIntegerSampler(False, 1), lambda: UniformIntegerSampler(0, 1.0),
    lambda: UniformIntegerSampler(1, 0), lambda: UniformIntegerSampler(0, 1 << 31),
    lambda: ExponentialSampler(0), lambda: ExponentialSampler(-1),
    lambda: ExponentialSampler(True), lambda: ExponentialSampler(float("inf")),
])
def test_invalid_parameters(factory):
    with pytest.raises(InputError): factory()


def test_construction_copy_and_parameter_freezing_do_not_draw(monkeypatch):
    state = random.getstate()
    def forbidden(*args, **kwargs): raise AssertionError("construction/clone cannot use random")
    monkeypatch.setattr(random, "Random", forbidden)
    monkeypatch.setattr(random, "random", forbidden)
    bundle = make_samplers(SamplerParameters(), WorkflowTypeRange(0, 19))
    copied = bundle.clone()
    assert copied == bundle and copied is not bundle
    for item in fields(bundle):
        sampler = getattr(bundle, item.name)
        assert getattr(copied, item.name) is not sampler
        assert "rng" not in {f.name for f in fields(sampler)}
    assert bundle.upload_bandwidth_cloud is not bundle.download_bandwidth_cloud
    assert bundle.upload_bandwidth_edge is not bundle.download_bandwidth_edge
    with pytest.raises(FrozenInstanceError): bundle.workload.lower = 1
    with pytest.raises(FrozenInstanceError): bundle.workload = UniformRealSampler(1, 2)
    assert random.getstate() == state


def test_samplers_follow_python_methods_and_one_shared_stream():
    rng = random.Random(20261104); expected = random.Random(20261104)
    bundle = make_samplers(SamplerParameters(), WorkflowTypeRange(4, 4))
    assert bundle.workflow_type.sample(rng) == expected.randint(4, 4)
    assert bundle.inter_release_time.sample(rng) == expected.expovariate(.01)
    u = expected.random()
    assert bundle.workload.sample(rng) == u * 15000 + (1 - u) * 5000
    u = expected.random()
    assert bundle.upload_bandwidth_cloud.sample(rng) == (256 if u < .2 else 512 if u < .8 else 128)
    u = expected.random()
    assert bundle.download_bandwidth_cloud.sample(rng) == (256 if u < .2 else 512 if u < .8 else 128)
    assert rng.getstate() == expected.getstate()
