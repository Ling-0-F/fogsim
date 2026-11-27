from dataclasses import fields, replace
import random
import pytest
from conftest import ROOT
from fogsim import load_experiment_config, prepare_random_input, sample_environment, build_environment
from fogsim.errors import InputError, NumericDerivationError
from fogsim.experiment_config import EnvironmentConfig, WorkflowTypeRange
from fogsim.model.resource import ResourceType


def prepared(seed=0):
    config = load_experiment_config(ROOT / "configs/examples/step1_dynamic.json")
    config = replace(config, source=replace(config.source, seed=seed, workflow_types=WorkflowTypeRange(0, 0)))
    return config, prepare_random_input(config)


def trace_roles(monkeypatch, inputs, scripted=None):
    """Observe actual sampler calls; optional values isolate arithmetic boundaries."""
    names = {id(getattr(inputs.samplers, f.name)): f.name for f in fields(inputs.samplers)}
    calls = []
    streams = {name: iter(values) for name, values in (scripted or {}).items()}
    for cls in {type(getattr(inputs.samplers, f.name)) for f in fields(inputs.samplers)}:
        original = cls.sample
        def traced(self, rng, original=original):
            if id(self) not in names:
                return original(self, rng)
            role = names[id(self)]
            assert rng is inputs.rng
            calls.append(role)
            if role in streams:
                return next(streams[role])
            return original(self, rng)
        monkeypatch.setattr(cls, "sample", traced)
    return calls


@pytest.mark.parametrize("local", [True, False])
def test_exact_environment_call_order_even_without_local(local, monkeypatch):
    _, inputs = prepared()
    calls = trace_roles(monkeypatch, inputs)
    snapshot = sample_environment(EnvironmentConfig(3, 2, 2, local), inputs, parameter_source="test")
    assert calls == (["processing_rate_device"] * 3 +
        ["upload_bandwidth_edge", "download_bandwidth_edge", "processing_rate_edge"] * 2 +
        ["upload_bandwidth_cloud", "download_bandwidth_cloud", "processing_rate_cloud"] * 2)
    assert [(r.id, r.numeric_id) for r in snapshot.devices] == [("M0", 0), ("M1", 1), ("M2", 2)]
    assert [(r.id, r.numeric_id, r.type) for r in snapshot.servers] == [
        ("E0", 0, "EDGE"), ("E1", 1, "EDGE"), ("C0", 2, "CLOUD"), ("C1", 3, "CLOUD")]
    assert all(d.can_process_tasks is local for d in snapshot.devices)


def test_environment_values_follow_the_same_rng_without_constant_draws():
    _, inputs = prepared(-1)
    control = random.Random((1 << 64) - 1)
    def uniform(a, b):
        u = control.random()
        while u == 0: u = control.random()
        return u * b + (1 - u) * a
    expected_devices = [uniform(125, 250), uniform(125, 250)]
    edge_rate = uniform(250, 500)
    up_u, down_u = control.random(), control.random()
    cloud_rate = uniform(500, 1000)
    snapshot = sample_environment(EnvironmentConfig(2, 1, 1, True), inputs, parameter_source="test")
    assert [d.processing_rate for d in snapshot.devices] == expected_devices
    assert snapshot.servers[0].processing_rate == edge_rate
    assert snapshot.servers[0].upload_bandwidth == snapshot.servers[0].download_bandwidth == 1024
    expected_bw = lambda u: 256 if u < .2 else 512 if u < .8 else 128
    assert snapshot.servers[1].upload_bandwidth == expected_bw(up_u)
    assert snapshot.servers[1].download_bandwidth == expected_bw(down_u)
    assert snapshot.servers[1].processing_rate == cloud_rate
    assert inputs.rng.getstate() == control.getstate()


def test_build_environment_preserves_snapshot_values_and_uses_fresh_objects():
    config, inputs = prepared()
    snapshot = sample_environment(config.source.environment, inputs, parameter_source=config.fingerprint)
    before = inputs.snapshot()
    first = build_environment(snapshot); second = build_environment(snapshot)
    assert inputs.snapshot() == before
    assert first.clock_time == 0 and not first.workflows_by_id and not first.tasks_by_key
    for spec, resource in zip((*snapshot.devices, *snapshot.servers), first.resources_by_id.values()):
        assert resource is not second.resources_by_id[spec.id]
        assert resource.numeric_id == spec.numeric_id and resource.processing_rate == spec.processing_rate
        assert resource.available_time == 0 and resource.pending_start is None
        assert resource.completed_task_count == 0 and not resource.waiting_queue
        assert resource.queued_processing_time == resource.queued_total_time == 0
        if resource.resource_type != ResourceType.MOBILE:
            assert resource.upload_bandwidth == spec.upload_bandwidth
            assert resource.download_bandwidth == spec.download_bandwidth
    first.servers[0].available_time = 99
    assert second.servers[0].available_time == 0 and snapshot.servers[0].processing_rate > 0
    second.check_invariants()


@pytest.mark.parametrize("role,value", [
    ("processing_rate_device", 0), ("processing_rate_device", float("nan")),
    ("upload_bandwidth_edge", 0), ("download_bandwidth_edge", float("inf")),
    ("processing_rate_edge", -1), ("upload_bandwidth_cloud", 0),
    ("download_bandwidth_cloud", float("nan")), ("processing_rate_cloud", float("inf")),
])
def test_invalid_sampled_resource_is_domain_failure(role, value, monkeypatch):
    _, inputs = prepared()
    trace_roles(monkeypatch, inputs, {role: [value]})
    with pytest.raises(NumericDerivationError) as exc:
        sample_environment(EnvironmentConfig(1, 1, 1, True), inputs, parameter_source="test")
    assert exc.value.reason_code == "NUMERIC_DERIVATION_ERROR"


def test_environment_api_validation_precedes_draws():
    _, inputs = prepared()
    before = inputs.snapshot()
    with pytest.raises(InputError): sample_environment({}, inputs, parameter_source="x")
    with pytest.raises(InputError): sample_environment(EnvironmentConfig(1, 0, 0, True), inputs, parameter_source=" ")
    with pytest.raises(InputError): build_environment({})
    assert inputs.snapshot() == before
