"""Formal V2-01..V2-05, with actual JDK output and independent lifecycle checks."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import pytest

from fogsim import load_fixed_instance, simulate
from fogsim.config import load_config
from conftest import ROOT
sys.path.insert(0, str(ROOT / "tools"))
import run_fixed_parity as parity
from run_v2_acceptance import run_acceptance, positive_intervals, SWEEP_SIZE
from java_support import java_tools
from v2_cases import V2_CASES


@pytest.fixture(scope="module")
def acceptance():
    try: java_tools()
    except RuntimeError as exc: pytest.skip(str(exc))
    return run_acceptance()


def raw(name, language="python"):
    return json.loads((ROOT / f"outputs/v2/parity/{name}/{language}-raw.json").read_text())


@pytest.mark.parametrize("name,expected", V2_CASES.items())
def test_v2_05_named_parity(acceptance, name, expected):
    case = next(c for c in acceptance["named_parity"]["cases"] if c["case"] == name)
    makespan, events, decisions = expected
    assert case["passed"] and case["first_difference"] is None
    assert case["events"] == {"python": events, "java": events}
    assert case["decisions"] == {"python": decisions, "java": decisions}
    for language in ("python", "java"):
        trace = raw(name, language); result = trace["result"]
        assert result["makespan"] == makespan
        assert result["status"] == "SUCCEEDED"
        assert not positive_intervals(result)
        ntasks = sum(len(w["tasks"]) for w in trace["input"]["workflows"])
        assert result["processed_event_count"] == len(trace["input"]["workflows"]) + 3 * ntasks
        for row in result["task_records"]:
            events_for_task = [e for e in result["events"] if e["workflow_id"] == row["workflow_id"] and e["task_id"] == row["task_id"]]
            assert sorted(e["type"] for e in events_for_task) == ["ProcessFinishEvent", "ProcessStartEvent", "TaskVisitEvent"]


def test_v2_01_diamond_join_two_full_routing_rounds(acceptance):
    result = raw("v2_diamond")["result"]
    rows = {r["task_id"]: r for r in result["task_records"]}
    assert [(t, rows[t]["resource_id"], rows[t]["start_time"], rows[t]["finish_time"]) for t in "ABCD"] == [
        ("A", "M0", 0, 2), ("B", "E0", 2, 6), ("C", "E0", 6, 7), ("D", "C0", 8, 11)]
    fork = [d for d in result["decisions"] if d["event_sequence"] == 4]
    assert [(d["selected"][1], d["round"]) for d in fork] == [("B",1),("C",1),("B",2),("C",2)]
    assert [a["kind"] for a in result["events"][3]["actions"]] == ["DECISION"]*4 + ["EMIT"]*2
    assert rows["D"]["dispatch_time"] == max(rows[t]["finish_time"] for t in "BC") == 7
    # Finishing B sees an empty ready query while C still has to finish.
    after_b = next(e["after"] for e in result["events"] if e["type"] == "ProcessFinishEvent" and e["task_id"] == "B")
    assert after_b["active_workflows"] == [0] and after_b["completed_workflows"] == []
    registrations = [e for e in result["events"] if e["before"]["completed_workflows"] != e["after"]["completed_workflows"]]
    assert len(registrations) == 1 and registrations[0]["task_id"] == "D"


def test_v2_02_fcfs_release_beats_queue_arrival_and_cache_includes_upload(acceptance):
    result = raw("v2_contention")["result"]
    sequence = [d for d in result["decisions"] if d["kind"] == "SEQUENCING"]
    first = sequence[0]
    assert [c["option"][0] for c in first["candidates"]] == [2, 1]
    assert [c["priority"] for c in first["candidates"]] == [2, 1]
    assert [c["ready_time"] for c in first["candidate_state"]] == [2, 6]
    assert first["selected"] == [1, "A", "E0"]
    edge = next(r for r in first["resource_state"] if r["id"] == "E0")
    assert len(edge["queue"]) == 2
    assert edge["queued_processing_time"] == 3 and edge["queued_total_time"] == 10
    assert [(r["workflow_id"], r["start_time"], r["finish_time"]) for r in result["task_records"]] == [(0,0,12),(1,12,15),(2,15,17)]
    assert all(r["queued_processing_time"] == r["queued_total_time"] == 0
               for r in result["events"][-1]["after"]["resources"])


def test_v2_03_candidate_order_state_and_score(acceptance):
    result = raw("v2_candidates")["result"]
    route = [d for d in result["decisions"] if d["kind"] == "ROUTING"]
    assert [d["selected"][2] for d in route] == ["M0","M0","E0","C0","M0","M0","M0"]
    assert [[c["priority"] for c in d["candidates"]] for d in route] == [
        [0,0,0],[0,0,0],[6,0,0],[6,6,0],[6,6,6],[6,6,6],[6,6,6]]
    for d in route:
        assert [c["option"][2] for c in d["candidates"]] == ["M0","E0","C0"]
    # Queue-related source getters (NIQ/WIQ/TTIQ), and raw MRT before t=3 routing.
    m = route[4]["resource_state"][0]
    assert (len(m["queue"]), m["queued_processing_time"], m["queued_total_time"], m["available_time"]) == (1,4,4,6)
    # All three Finish events at t=6; source numeric resource ordering is retained.
    assert [e["resource_id"] for e in result["events"] if e["time"] == 6 and e["type"] == "ProcessFinishEvent"] == ["M0","E0","C0"]


@pytest.mark.parametrize("rid", ["M0", "E0"])
def test_v2_04_new_same_time_start_old_finish_and_future_reservation(acceptance, rid):
    result = raw("v2_collision_" + rid.lower())["result"]
    same_time = [e for e in result["events"] if e["time"] == 4]
    assert [e["type"] for e in same_time] == ["JobArrivalEvent","TaskVisitEvent","ProcessStartEvent","ProcessFinishEvent"]
    after_visit = next(r for r in same_time[1]["after"]["resources"] if r["id"] == rid)
    assert after_visit["pending_start"] == [3,"A"] and after_visit["available_time"] == 4
    after_finish = next(r for r in same_time[-1]["after"]["resources"] if r["id"] == rid)
    assert after_finish["pending_start"] == [1,"A"] and after_finish["available_time"] == 5
    planned = same_time[-1]["after"]["executions"][-1]
    assert planned["planned_start_time"] == 5
    # New JA at 5 sees the reservation; its TV runs only after the queued Start.
    assert [(e["type"],e["workflow_id"]) for e in result["events"] if e["time"] == 5] == [
        ("JobArrivalEvent",4),("ProcessStartEvent",1),("TaskVisitEvent",4),("ProcessFinishEvent",3)]


def test_v2_04_heap_ties_are_not_fifo(acceptance):
    result = raw("v2_equal_heap")["result"]
    arrivals = [e["workflow_id"] for e in result["events"] if e["type"] == "JobArrivalEvent"]
    assert arrivals == [3,7,9]
    first_started = next(e for e in result["events"] if e["type"] == "ProcessStartEvent")
    assert (first_started["workflow_id"],first_started["task_id"]) == (7,"B")


def test_shared_server_emits_to_current_device_with_other_owner(acceptance):
    events = raw("v2_shared_server")["result"]["events"]
    cross = [e for e in events if e["owner"] != e["staging_device"]]
    assert [(e["type"],e["owner"],e["staging_device"],e["time"]) for e in cross] == [
        ("ProcessStartEvent","M1","M0",4),("ProcessStartEvent","M0","M1",6),("ProcessStartEvent","M1","M0",7)]


@pytest.mark.parametrize("name", V2_CASES)
def test_named_replay_and_logging_do_not_change_scheduling(acceptance, name, tmp_path):
    path, config = load_config(ROOT / f"configs/{name}.json")
    spec = load_fixed_instance(path)
    expected = raw(name)["result"]
    assert simulate(spec, config).to_dict() == expected
    quiet = simulate(spec, replace(config, trace_enabled=False)).to_dict()
    assert quiet == dict(expected, events=[], decisions=[])
    build = json.loads((ROOT / "outputs/v2/parity/build/build-manifest.json").read_text())
    java, _ = java_tools()
    request = json.loads((ROOT / f"outputs/v2/parity/{name}/java-request.json").read_text())
    original = raw(name,"java")
    repeated = parity.run_java_request(java, build["runtime_classpath"], request, tmp_path, stem="repeat")
    assert repeated == original
    request["record_trace"] = False
    quiet_java = parity.run_java_request(java, build["runtime_classpath"], request, tmp_path, stem="quiet")
    assert quiet_java["result"] == dict(original["result"], events=[], decisions=[])


@pytest.mark.parametrize("index", range(SWEEP_SIZE))
def test_v2_05_generated_fixed_input_sweep(acceptance, index):
    c = acceptance["sweep_cases"][index]
    assert c["passed"] and c["first_difference"] is None
    for language in ("python", "java"):
        trace = json.loads((ROOT / f"outputs/v2/sweep/case-{index:03}/{language}-raw.json").read_text())
        result = trace["result"]
        assert not positive_intervals(result)
        assert result["completed_workflow_count"] == len(trace["input"]["workflows"])


def test_pending_guard_boundary_and_normal_run_observations(acceptance):
    rows = acceptance["injected_boundary"]["cases"]
    assert [(c["scenario"],c["equal"]) for c in rows] == [
        ("empty",True),("staged_only",False),("matching_root",True),("matching_below_other_root",False)]
    assert not any(c["reachable_run"] for c in rows)
    obs = acceptance["reservation_checks"]
    assert obs["canAddToQueue_calls"] > 100
    assert obs["guard_disagreements_in_normal_runs"] == []


def test_precision_counterexample_is_an_explicit_failure_not_false_parity(acceptance):
    p = acceptance["precision_boundary"]
    assert p["expected_boundary_detected"] and not p["parity_passed"]
    assert p["python_status"] == "FAILED" and p["java_status"] == "SUCCEEDED"
    assert p["java_overlaps"] == [{"resource_id":"M0", "first":[2,"A"], "second":[5,"A"],
                                   "first_finish":9007199254741000.0,"second_start":9007199254740996.0}]
    result = json.loads((ROOT / "outputs/v2/precision-collapse/python-raw.json").read_text())["result"]
    assert result["makespan"] is None
    failed_task = next(t for t in result["task_records"] if t["workflow_id"] == 3)
    assert failed_task["plan"] is failed_task["start_time"] is failed_task["finish_time"] is None


def test_empty_half_open_intervals_are_not_reported_as_overlap():
    result = {"task_records": [
        {"resource_id":"M0","workflow_id":1,"task_id":"A","start_time":1,"finish_time":2},
        {"resource_id":"M0","workflow_id":2,"task_id":"A","start_time":1,"finish_time":1}]}
    assert positive_intervals(result) == []


def test_acceptance_gate(acceptance):
    assert acceptance["passed"], json.dumps(acceptance, ensure_ascii=False)
