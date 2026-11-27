"""Step 1: frozen design sections 8/9/16/17/18; no sampling or DAX I/O."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import json
import random
import pytest
from fogsim import load_experiment_config, parse_experiment_config, RunConfig
from fogsim.config import load_config
from fogsim.errors import InputError
from fogsim.experiment_config import (
    RealRange, SamplerParameters, EnvironmentConfig, DynamicRunConfig,
    WorkflowTypeRange, RepeatConfig, ReplayRunOptions, RuleConfig, DynamicSourceConfig,
)
from fogsim.seed import encode_seed, rotated_seed, SEED_ENCODING


def dynamic():
    return {
        "format": "fogsim.experiment", "schema_version": 1, "mode": "dynamic",
        "source": {"seed": 0, "dag_root": "dax", "workflow_types": {"lower": 0, "upper": 19},
                   "environment": {"num_mobile_devices": 2, "num_edge_servers": 1, "num_cloud_servers": 1,
                                   "can_mobile_devices_process_tasks": True}},
        "run": {"num_jobs_recorded": 10, "warmup_jobs": 0},
    }


def replay():
    return {"format": "fogsim.experiment", "schema_version": 1, "mode": "replay",
            "source": {"input_path": "input.json", "reference_path": "reference.json"}}


def set_value(data, path, value):
    parts = path.split(".")
    for part in parts[:-1]:
        data = data.setdefault(part, {})
    data[parts[-1]] = value


def test_normalization_paths_defaults_and_immutability(tmp_path, monkeypatch):
    data = dynamic()
    path = tmp_path / "experiment.json"
    path.write_text(json.dumps(data))
    monkeypatch.chdir(tmp_path.parent)
    cfg = load_experiment_config(path)
    assert cfg.source.dag_root == tmp_path / "dax"
    assert not cfg.source.dag_root.exists()  # pure config, not DAX validation
    assert cfg.run.max_events is None and RunConfig().max_events == 100000
    assert cfg.run.statistics_policy == "java_legacy"
    assert cfg.repeat.mode == "fresh_same_seed" and cfg.output.dataset_role == "debug"
    assert cfg.source.samplers.data_size == RealRange(5120, 20480)
    params = cfg.effective_parameters()["source"]["samplers"]
    assert params["distributions"]["cloud_bandwidth"] == {"values": [256, 512, 128], "thresholds": [0.2, 0.8]}
    assert parse_experiment_config(cfg.to_dict()) == cfg
    with pytest.raises(FrozenInstanceError):
        cfg.source.samplers.workload.lower = 1
    data["source"]["environment"]["num_mobile_devices"] = 99
    params["workload"]["lower"] = 1
    assert cfg.source.environment.num_mobile_devices == 2
    assert cfg.source.samplers.workload.lower == 5000


@pytest.mark.parametrize("path,value", [
    ("format", "fixed"), ("schema_version", True), ("schema_version", 3), ("mode", "fixed"),
    ("source.seed", True), ("source.seed", 1.0), ("source.seed", "1"), ("source.seed", None),
    ("source.seed", -(1 << 63) - 1), ("source.seed", 1 << 63),
    ("source.workflow_types.lower", -1), ("source.workflow_types.upper", 20),
    ("source.workflow_types.lower", True), ("source.workflow_types.lower", 20),
    ("source.environment.num_mobile_devices", 0), ("source.environment.num_mobile_devices", True),
    ("source.environment.num_edge_servers", -1), ("source.environment.num_cloud_servers", 1 << 31),
    ("source.environment.can_mobile_devices_process_tasks", 1),
    ("source.environment.num_mobile_devices", 1.0),
    ("run.num_jobs_recorded", 0), ("run.num_jobs_recorded", True), ("run.warmup_jobs", -1),
    ("run.num_jobs_recorded", ((1 << 31) - 1) // 500 + 1),
    ("run.max_events", 0), ("run.max_events", True), ("run.max_events", 3.5),
    ("run.check_invariants", 1), ("run.trace_enabled", "false"),
    ("run.statistics_policy", "all_completed"), ("run.failure_policy", "continue"),
    ("run.event_policy", "stable"), ("run.edge_data_policy", "drop"),
    ("run.routing_rule", {"kind": "gp"}), ("run.routing_rule", {"kind": "fcfs", "resource_id": "E0"}),
    ("run.sequencing_rule", {"kind": "fixed_resource", "resource_id": "E0"}),
    ("repeat.count", 0), ("repeat.count", True), ("repeat.count", 2),
    ("repeat.mode", "same_input"), ("repeat.mode", "rotate_seed"),
    ("output.dataset_role", "validation"), ("source.dag_root", ""), ("source.dag_root", None),
    ("source.samplers.inter_release_mean", 101), ("source.samplers.inter_release_mean", True),
    ("source.samplers.edge_bandwidth", 1000), ("source.samplers.weight_profile", "uniform"),
    ("source.samplers.cloud_bandwidth_profile", "constant"),
    ("source.samplers.workload", {"lower": 0, "upper": 1}),
    ("source.samplers.workload", {"lower": 10, "upper": 10}),
    ("source.samplers.data_size", {"lower": -1, "upper": 1}),
    ("source.samplers.edge_data", {"lower": 0, "upper": float("inf")}),
    ("source.samplers.processing_rate_edge", {"lower": float("nan"), "upper": 10}),
    ("source.samplers.processing_rate_cloud", {"lower": 1, "upper": 10**400}),
    ("source.samplers.processing_rate_device", {"lower": True, "upper": 10}),
])
def test_invalid_config_before_sampling(path, value, tmp_path):
    data = dynamic()
    set_value(data, path, value)
    with pytest.raises(InputError):
        parse_experiment_config(data, base_dir=tmp_path)


@pytest.mark.parametrize("path", ["unknown", "source.unknown", "source.environment.unknown",
    "source.workflow_types.unknown", "source.samplers.unknown", "run.unknown", "repeat.unknown", "output.unknown"])
def test_unknown_fields_at_every_layer(path, tmp_path):
    data = dynamic()
    set_value(data, path, 1)
    with pytest.raises(InputError, match="unknown"):
        parse_experiment_config(data, base_dir=tmp_path)


def test_cross_field_limits_and_warmup_boundary(tmp_path):
    data = dynamic()
    data["run"] = {"num_jobs_recorded": 1, "warmup_jobs": 0}
    assert parse_experiment_config(data, base_dir=tmp_path).run.warmup_jobs == 0
    data["run"] = {"num_jobs_recorded": ((1 << 31) - 1) // 500, "warmup_jobs": 1}
    with pytest.raises(InputError): parse_experiment_config(data, base_dir=tmp_path)
    with pytest.raises(InputError): EnvironmentConfig(1, (1 << 31) - 1, 1, True)
    with pytest.raises(InputError): EnvironmentConfig(1, 0, 0, False)


@pytest.mark.parametrize("devices,local,target,valid", [
    (2, True, "E0", True), (2, False, "C0", True), (2, True, "M0", False),
    (1, True, "M0", True), (1, False, "M0", False), (1, True, "E1", False),
    (1, True, "E00", False), (1, True, "E-1", False), (1, True, "C1", False),
    (1, True, "E" + "9" * 5000, False),
])
def test_fixed_target_must_work_for_all_devices(devices, local, target, valid, tmp_path):
    data = dynamic()
    data["source"]["environment"].update(num_mobile_devices=devices, can_mobile_devices_process_tasks=local)
    data["run"]["routing_rule"] = {"kind": "fixed_resource", "resource_id": target}
    if valid:
        assert parse_experiment_config(data, base_dir=tmp_path).run.routing_rule.resource_id == target
    else:
        with pytest.raises(InputError): parse_experiment_config(data, base_dir=tmp_path)


def test_seed_list_and_single_run_expansion(tmp_path):
    data = dynamic()
    del data["source"]["seed"]
    seeds = [-(1 << 63), -1, (1 << 63) - 1]
    data["repeat"] = {"count": 3, "mode": "fresh_seed_list", "seeds": seeds}
    cfg = parse_experiment_config(data, base_dir=tmp_path)
    seeds[0] = 99
    assert [cfg.single_run(i).source.seed for i in range(3)] == [-(1 << 63), -1, (1 << 63) - 1]
    assert cfg.source.seed is None
    assert cfg.single_run(1).repeat.count == 1
    assert parse_experiment_config(cfg.to_dict()) == cfg
    with pytest.raises(InputError): cfg.single_run(True)
    with pytest.raises(InputError): cfg.single_run(3)
    data["source"]["seed"] = 0
    with pytest.raises(InputError): parse_experiment_config(data, base_dir=tmp_path)


@pytest.mark.parametrize("repeat", [
    {"mode": "fresh_seed_list"}, {"count": 2, "mode": "fresh_seed_list", "seeds": [0]},
    {"mode": "fresh_seed_list", "seeds": [True]}, {"mode": "fresh_seed_list", "seeds": [1 << 63]},
    {"mode": "fresh_same_seed", "seeds": []}, {"mode": "java_rerun", "seeds": None},
])
def test_invalid_repeat(repeat, tmp_path):
    data = dynamic(); data["repeat"] = repeat
    with pytest.raises(InputError): parse_experiment_config(data, base_dir=tmp_path)


def test_replay_defaults_rules_and_no_regeneration(tmp_path):
    data = replay()
    cfg = parse_experiment_config(data, base_dir=tmp_path)
    assert cfg.repeat.mode == "same_input"
    assert cfg.source.input_path == tmp_path / "input.json"
    assert parse_experiment_config(cfg.to_dict()) == cfg
    data["run"] = {"routing_rule": {"kind": "fixed_resource", "resource_id": "custom-server"}}
    with pytest.raises(InputError): parse_experiment_config(data, base_dir=tmp_path)
    data["source"]["purpose"] = "reuse_inputs"
    del data["source"]["reference_path"]
    cfg = parse_experiment_config(data, base_dir=tmp_path)
    assert cfg.run.routing_rule.resource_id == "custom-server"  # validated against input later
    assert parse_experiment_config(cfg.to_dict()) == cfg


@pytest.mark.parametrize("path,value", [
    ("source.seed", 0), ("source.environment", {}), ("source.reference_path", None),
    ("source.purpose", "unknown"), ("run.num_jobs_recorded", 1), ("run.warmup_jobs", 0),
    ("run.event_policy", "java_compatible"), ("repeat.mode", "java_rerun"),
    ("repeat.seeds", [0]), ("run.max_events", float("inf")),
])
def test_replay_forbidden_overrides(path, value, tmp_path):
    data = replay(); set_value(data, path, value)
    with pytest.raises(InputError): parse_experiment_config(data, base_dir=tmp_path)


def test_missing_fields_and_path_requirements(tmp_path):
    for path in ("source.seed", "source.dag_root", "source.workflow_types", "source.environment", "run.num_jobs_recorded"):
        data = dynamic(); parts = path.split("."); del data[parts[0]][parts[1]]
        with pytest.raises(InputError): parse_experiment_config(data, base_dir=tmp_path)
    with pytest.raises(InputError): parse_experiment_config(dynamic())
    data = replay(); del data["source"]["reference_path"]
    with pytest.raises(InputError): parse_experiment_config(data, base_dir=tmp_path)
    with pytest.raises(InputError): DynamicSourceConfig(Path("dax"), WorkflowTypeRange(0, 0), EnvironmentConfig(1, 1, 0, True), 0)


def test_duplicate_json_and_old_loader_stays_strict(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"format":"fogsim.experiment","format":"fogsim.experiment"}')
    with pytest.raises(InputError, match="duplicate JSON key"): load_experiment_config(path)
    path.write_text(json.dumps(dynamic()))
    with pytest.raises(InputError): load_config(path)
    path.write_text('{"instance":"x","routing_rule":{"kind":"fcfs"},"sequencing_rule":{"kind":"fcfs"}}')
    with pytest.raises(InputError): load_experiment_config(path)


def test_programmatic_contracts():
    for factory in (
        lambda: SamplerParameters(workload={"lower": 1, "upper": 2}),
        lambda: DynamicRunConfig(1, 0, routing_rule={"kind": "fcfs"}),
        lambda: ReplayRunOptions(sequencing_rule=RuleConfig("fixed_resource", "E0")),
        lambda: RepeatConfig(seeds=[0]),
        lambda: WorkflowTypeRange(0, 0.0),
    ):
        with pytest.raises(InputError): factory()


@pytest.mark.parametrize("seed,bits", [(0, 0), (1, 1), (-1, (1 << 64) - 1),
    (-(1 << 63), 1 << 63), ((1 << 63) - 1, (1 << 63) - 1)])
def test_seed_bits(seed, bits):
    assert SEED_ENCODING == "signed64-bits-v1"
    assert encode_seed(seed) == bits


@pytest.mark.parametrize("seed", [True, False, 1.0, "1", None, -(1 << 63) - 1, 1 << 63])
def test_invalid_seeds(seed):
    with pytest.raises(InputError): encode_seed(seed)
    with pytest.raises(InputError): rotated_seed(seed)


def test_seed_wrap_and_pure_validation(tmp_path, monkeypatch):
    assert rotated_seed((1 << 63) - 1) == -(1 << 63) + 9999
    assert rotated_seed(-1) == 9999
    assert encode_seed(1) != encode_seed(-1)
    state = random.getstate()
    def forbidden(*args, **kwargs):
        raise AssertionError("pure validation must not create or consume RNG")
    monkeypatch.setattr(random, "Random", forbidden)
    for method in ("random", "seed", "randint", "getrandbits", "expovariate"):
        monkeypatch.setattr(random, method, forbidden)
    cfg = parse_experiment_config(dynamic(), base_dir=tmp_path)
    assert cfg.fingerprint == parse_experiment_config(deepcopy(cfg.to_dict())).fingerprint
    assert cfg.single_run().source.seed == 0
    assert random.getstate() == state
