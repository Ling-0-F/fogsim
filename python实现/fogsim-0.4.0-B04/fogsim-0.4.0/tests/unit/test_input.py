from copy import deepcopy
from dataclasses import FrozenInstanceError
import pytest
from fogsim import parse_instance, load_fixed_instance, create_engine
from fogsim.config import RunConfig, load_config
from fogsim.errors import InputError


@pytest.mark.parametrize("field,value", [
    ("upload_time", -1), ("upload_time", float("inf")), ("download_time", float("nan")),
    ("processing_time", 0), ("processing_time", -1), ("processing_time", True),
    ("processing_time", "3"), ("processing_time", 10**400),
])
def test_invalid_times(raw, field, value):
    raw["workflows"][0]["tasks"][0]["execution_times"]["E0"][field] = value
    with pytest.raises(InputError):
        parse_instance(raw)


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True, "0"])
def test_invalid_release(raw, value):
    raw["workflows"][0]["release_time"] = value
    with pytest.raises(InputError): parse_instance(raw)


@pytest.mark.parametrize("defect", ["resource_id", "workflow_id", "task_id", "owner", "owner_server",
    "missing_candidate", "extra_candidate", "missing_time", "local_upload", "local_download",
    "runtime_task", "runtime_resource", "empty_tasks", "empty_workflows", "time_unit", "bool_id",
    "cycle", "self", "missing_node", "duplicate_edge", "edge_shape"])
def test_reject_invalid_instance(raw, defect):
    w = raw["workflows"][0]; t = w["tasks"][0]
    if defect == "resource_id": raw["resources"].append(deepcopy(raw["resources"][0]))
    elif defect == "workflow_id": raw["workflows"].append(deepcopy(w))
    elif defect == "task_id": w["tasks"].append(deepcopy(t))
    elif defect == "owner": w["owner_device_id"] = "M99"
    elif defect == "owner_server": w["owner_device_id"] = "E0"
    elif defect == "missing_candidate": del t["execution_times"]["E0"]
    elif defect == "extra_candidate": t["execution_times"]["M1"] = t["execution_times"]["M0"]
    elif defect == "missing_time": del t["execution_times"]["E0"]["upload_time"]
    elif defect == "local_upload": t["execution_times"]["M0"]["upload_time"] = 1
    elif defect == "local_download": t["execution_times"]["M0"]["download_time"] = 1
    elif defect == "runtime_task": t["dispatched"] = True
    elif defect == "runtime_resource": raw["resources"][0]["available_time"] = 5
    elif defect == "empty_tasks": w["tasks"] = []
    elif defect == "empty_workflows": raw["workflows"] = []
    elif defect == "time_unit": raw["time_unit"] = "ms"
    elif defect == "bool_id": w["id"] = True
    elif defect == "cycle": w["dependencies"].append(["B", "A"])
    elif defect == "self": w["dependencies"] = [["A", "A"]]
    elif defect == "missing_node": w["dependencies"] = [["A", "C"]]
    elif defect == "duplicate_edge": w["dependencies"].append(["A", "B"])
    elif defect == "edge_shape": w["dependencies"] = [["A"]]
    with pytest.raises(InputError): parse_instance(raw)


def test_disabled_local_and_order(raw):
    raw["resources"] = [raw["resources"][2], raw["resources"][0], raw["resources"][1]]
    raw["resources"][1]["can_process_tasks"] = False
    for t in raw["workflows"][0]["tasks"]: del t["execution_times"]["M0"]
    spec = parse_instance(raw)
    assert [o.resource_id for o in spec.workflows[0].tasks[0].options] == ["E0", "C0"]
    state = create_engine(spec).state
    assert list(state.resources_by_id) == ["C0", "M0", "E0"]
    assert [r.id for r in state.servers] == ["E0", "C0"]
    assert [r.numeric_id for r in state.servers] == [0, 1]
    with pytest.raises(InputError): create_engine(spec, RunConfig(routing_kind="fixed_resource", fixed_resource_id="M0"))


def test_spec_immutable_and_independent(raw):
    spec = parse_instance(raw)
    raw["workflows"][0]["tasks"].clear()
    assert len(spec.workflows[0].tasks) == 2
    with pytest.raises(FrozenInstanceError): spec.workflows[0].release_time = 7


def test_duplicate_json_keys_and_parse_errors(tmp_path):
    path = tmp_path / "input.json"
    for text in ['{"resources": [], "resources": []}', '{bad json', '[]']:
        path.write_text(text)
        with pytest.raises(InputError): load_fixed_instance(path)
    with pytest.raises(InputError): load_fixed_instance(tmp_path / "missing")


@pytest.mark.parametrize("kwargs", [{"routing_kind": "heft"}, {"event_policy": "stable"},
    {"routing_kind": "fixed_resource"}, {"max_events": 0}, {"max_events": True},
    {"trace_enabled": "false"}, {"sequencing_kind": "fifo"}, {"fixed_resource_id": "E0"}])
def test_config_errors(kwargs):
    with pytest.raises(InputError): RunConfig(**kwargs)


def test_config_relative_path():
    from conftest import ROOT
    path, cfg = load_config(ROOT / "configs/chain_remote.json")
    assert path == ROOT / "data/cases/chain_remote.json"
    assert cfg.fixed_resource_id == "E0"
