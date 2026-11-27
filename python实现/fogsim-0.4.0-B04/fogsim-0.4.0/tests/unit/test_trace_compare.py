"""Synthetic fault tests for the comparator, not Java execution evidence."""
from copy import deepcopy
import json
import math
import sys
import pytest
from fogsim import load_fixed_instance, simulate, create_engine
from fogsim.config import load_config
from fogsim.validation.trace_compare import compare_traces, main
from conftest import ROOT


@pytest.fixture
def traces():
    sys.path.insert(0, str(ROOT / "tools"))
    from run_fixed_parity import loaded_model
    path, config = load_config(ROOT / "configs/chain_remote.json")
    spec = load_fixed_instance(path)
    python = {"schema_version": 1, "language": "python", "input": spec.to_dict(),
              "config": config.to_dict(), "loaded_model": loaded_model(create_engine(spec, config).state),
              "result": simulate(spec, config).to_dict()}
    java = deepcopy(python); java["language"] = "java"
    java["observations"] = {"anomalies": [], "random_generator_is_null": True, "suppressed_generation_calls": 1}
    for event in java["result"]["events"]:
        for phase in ("before", "after"):
            for resource in event[phase]["resources"]:
                pending = resource.pop("pending_start")
                resource["observed_pending_starts"] = [] if pending is None else [pending]
            for w in event[phase]["workflows"]:
                if not w["completion_registered"]: w["completion_time"] = 0.0
    return python, java


def test_representation_mappings_are_explicit_and_no_mutation(traces):
    original = deepcopy(traces)
    report = compare_traces(*traces)
    assert report["passed"] and report["first_difference"] is None
    assert len(report["representation_mappings"]) == 3 and traces == original
    # Object key order is irrelevant; array/candidate/event order is not.
    reordered = json.loads(json.dumps(traces[1], sort_keys=True))
    assert compare_traces(traces[0], reordered)["passed"]


@pytest.mark.parametrize("mutation,sequence,fragment", [
    ("time", 5, ".time"), ("event_order", 2, ".type"),
    ("decision_score", 1, ".priority"), ("decision_selected", 1, ".selected"),
    ("omit_second_round", 4, ".actions[1].kind"),
    ("ready_time", 2, ".ready_time"), ("pending_duplicate", 2, ".pending_starts"),
    ("unexpected_completion", 1, ".completion_time"),
])
def test_first_difference_is_localized(traces, mutation, sequence, fragment):
    python, java = traces; events = java["result"]["events"]
    if mutation == "time": events[4]["time"] += 1
    elif mutation == "event_order": events[1], events[2] = events[2], events[1]; events[1]["sequence"] = 2
    elif mutation == "decision_score": events[0]["actions"][0]["decision"]["candidates"][0]["priority"] += 1
    elif mutation == "decision_selected": events[0]["actions"][0]["decision"]["selected"][-1] = "C0"
    elif mutation == "omit_second_round": del events[3]["actions"][1]
    elif mutation == "ready_time": events[1]["after"]["tasks"][0]["options"][1]["ready_time"] += 1
    elif mutation == "pending_duplicate": events[1]["after"]["resources"][1]["observed_pending_starts"].append([0,"B"])
    elif mutation == "unexpected_completion": events[0]["before"]["workflows"][0]["completion_time"] = 4
    report = compare_traces(python, java); diff = report["first_difference"]
    assert not report["passed"] and diff["event_sequence"] == sequence and fragment in diff["path"]


def test_earlier_difference_beats_later_missing_event(traces):
    python, java = traces
    java["result"]["events"][0]["actions"][0]["decision"]["round"] = 2
    java["result"]["events"].pop()
    diff = compare_traces(python, java)["first_difference"]
    assert diff["event_sequence"] == 1 and diff["path"].endswith(".round")


def test_loaded_input_parameters_checked_before_events(traces):
    python, java = traces
    java["loaded_model"]["workflows"][0]["tasks"][0]["options"][2]["upload_time"] += 1
    report = compare_traces(python, java)
    assert not report["passed"] and report["first_difference"]["path"].startswith("$.loaded_model")


def test_tolerance_never_relaxes_ids_or_signed_priorities(traces):
    python, java = traces
    java["result"]["events"][0]["time"] = 1e-10
    assert compare_traces(python, java)["passed"]
    assert not compare_traces(python, java, abs_tol=0, rel_tol=0)["passed"]
    java["result"]["events"][0]["time"] = 0
    java["result"]["events"][0]["workflow_id"] = 1e-12
    assert not compare_traces(python, java)["passed"]
    java["result"]["events"][0]["workflow_id"] = 0
    java["result"]["events"][0]["actions"][0]["decision"]["candidates"][1]["priority"] = -0.0
    assert compare_traces(python, java)["first_difference"]["reason"] == "priority signed zero differs"


@pytest.mark.parametrize("mode", ["failed", "no_events", "flat_decision_corrupt", "generation_leak", "rng_leak"])
def test_cannot_report_false_success(traces, mode):
    python, java = traces
    if mode == "failed":
        for trace in traces: trace["result"]["status"] = "FAILED"; trace["result"]["makespan"] = None
    elif mode == "no_events":
        for trace in traces: trace["result"]["events"] = []
    elif mode == "flat_decision_corrupt": java["result"]["decisions"][0]["round"] = 9
    elif mode == "generation_leak": java["observations"]["suppressed_generation_calls"] = 0
    elif mode == "rng_leak": java["observations"]["random_generator_is_null"] = False
    assert not compare_traces(python, java)["passed"]


def test_compare_cli_writes_failure(traces, tmp_path):
    python, java = traces
    java["result"]["events"][0]["owner"] = "M9"
    for name, trace in (("python",python),("java",java)):
        (tmp_path/f"{name}.json").write_text(json.dumps(trace),encoding="utf-8")
    output = tmp_path/"diff.json"
    assert main([str(tmp_path/"python.json"),str(tmp_path/"java.json"),"--output",str(output)]) == 1
    assert json.loads(output.read_text())["first_difference"]["path"].endswith(".owner")
    with pytest.raises(ValueError): compare_traces(python, java, abs_tol=math.nan)
