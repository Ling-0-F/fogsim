"""Integration against actual original Java event/rule/model classes."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import pytest
from fogsim.validation.trace_compare import compare_traces
from conftest import ROOT

sys.path.insert(0, str(ROOT / "tools"))
import run_fixed_parity as parity
from java_support import java_tools, ORIGINAL


@pytest.fixture(scope="module")
def suite():
    try: java_tools()
    except RuntimeError as exc: pytest.skip(str(exc))
    summary = parity.run_suite()
    return summary


@pytest.mark.parametrize("case,expected,events,decisions",[
    ("single_local",3,4,1),("single_local_release5",3,4,1),
    ("chain_remote",13,7,3),("chain_fcfs",17,7,3)])
def test_existing_fixed_cases(suite,case,expected,events,decisions):
    report = next(c for c in suite["cases"] if c["case"] == case)
    assert report["passed"] and report["first_difference"] is None
    assert report["events"] == {"python":events,"java":events}
    assert report["decisions"] == {"python":decisions,"java":decisions}
    raw = json.loads((ROOT/f"outputs/parity/{case}/java-raw.json").read_text(encoding="utf-8"))
    assert raw["result"]["makespan"] == expected
    assert raw["observations"]["random_generator_is_null"]
    assert raw["observations"]["suppressed_generation_calls"] == 1
    if case.startswith("chain"):
        assert [d["round"] for d in raw["result"]["decisions"]] == [1,1,2]
        assert [d["selected"] for d in raw["result"]["decisions"]] == [
            [0,"A","M0" if case == "chain_fcfs" else "E0"],[0,"B","E0"],[0,"B","E0"]]
    if case == "single_local_release5": assert raw["result"]["final_clock_time"] == 8


def test_overlays_only_add_constructors_and_originals_unchanged(suite):
    build = ROOT/"outputs/parity/build"
    manifest = json.loads((build/"build-manifest.json").read_text())
    for name, package in (("MobileDevice","taskscheduling"),("DynamicSimulation","simulation")):
        original = ORIGINAL/f"src/mengxu/{package}/{name}.java"
        addition = (ROOT/f"tools/java/constructors/{name}.java.inc").read_text()
        overlay = (build/f"overlay/mengxu/{package}/{name}.java").read_text()
        anchor = f"public class {name} {{"
        assert overlay == original.read_text(encoding="utf-8").replace(anchor,anchor+"\n\n"+addition,1)
    for relative,expected in manifest["original_sources"].items(): assert parity.sha(ORIGINAL/relative) == expected
    classes = build/"classes"/manifest["fingerprint"][:16]
    for name in ("JobArrivalEvent","TaskVisitEvent","ProcessStartEvent","ProcessFinishEvent"):
        assert (classes/f"mengxu/simulation/event/{name}.class").is_file()
    assert (classes/"mengxu/algorithm/FCFS.class").is_file()


def java_context():
    manifest = json.loads((ROOT/"outputs/parity/build/build-manifest.json").read_text())
    java,_ = java_tools()
    return java,manifest["runtime_classpath"]


def test_java_observer_has_no_effect_and_fresh_rerun(suite,tmp_path):
    java,classpath = java_context()
    request = json.loads((ROOT/"outputs/parity/chain_remote/java-request.json").read_text())
    original = json.loads((ROOT/"outputs/parity/chain_remote/java-raw.json").read_text())
    repeated = parity.run_java_request(java,classpath,request,tmp_path,stem="repeat")
    assert repeated == original
    request["record_trace"] = False
    quiet = parity.run_java_request(java,classpath,request,tmp_path,stem="quiet")
    assert quiet["result"]["events"] == quiet["result"]["decisions"] == []
    for key in ("task_records","workflow_records","makespan","processed_event_count","status"):
        assert quiet["result"][key] == original["result"][key]


def test_observer_pending_is_not_java_reservation(suite):
    raw = json.loads((ROOT/"outputs/parity/chain_remote/java-raw.json").read_text())
    state = raw["result"]["events"][1]["after"]
    edge = next(r for r in state["resources"] if r["id"] == "E0")
    assert edge["observed_pending_starts"] == [[0,"A"]] and "pending_start" not in edge
    assert edge["available_time"] == 0
    assert state["workflows"][0]["completion_time"] == 0.0


def test_real_trace_fault_injection_preserves_raw_and_reports_first(suite):
    case = ROOT/"outputs/parity/chain_fcfs"
    python = json.loads((case/"python-raw.json").read_text())
    java = json.loads((case/"java-raw.json").read_text())
    raw_hash = parity.sha(case/"java-raw.json")
    altered = deepcopy(java)
    altered["result"]["events"][0]["actions"][0]["decision"]["candidates"][0]["priority"] = 99.0
    report = compare_traces(python,altered)
    assert not report["passed"] and report["first_difference"]["event_sequence"] == 1
    assert report["first_difference"]["path"] == "$.result.events[0].actions[0].decision.candidates[0].priority"
    target=ROOT/"outputs/parity/fault_injection";target.mkdir(exist_ok=True)
    parity.write_json(target/"java-score-altered.json",altered)
    parity.write_json(target/"comparison.json",dict(report,injection={
        "intentional":True,"original_trace":"../chain_fcfs/java-raw.json","original_sha256":raw_hash,
        "change":"first decision first candidate score changed from 0.0 to 99.0; comparator test only"}))
    assert parity.sha(case/"java-raw.json") == raw_hash


def test_invalid_request_cannot_reuse_previous_trace(suite,tmp_path):
    java,classpath=java_context()
    request=json.loads((ROOT/"outputs/parity/single_local/java-request.json").read_text())
    assert parity.run_java_request(java,classpath,request,tmp_path)["result"]["status"] == "SUCCEEDED"
    request["input"]["workflows"][0]["release_time"]=-1
    with pytest.raises(RuntimeError,match="no trace"):parity.run_java_request(java,classpath,request,tmp_path)
    assert not (tmp_path/"java-raw.json").exists()


def test_java_json_roundtrip_string_ids(suite,tmp_path):
    java,classpath=java_context()
    request=json.loads((ROOT/"outputs/parity/chain_remote/java-request.json").read_text())
    workflow=request["input"]["workflows"][0]
    names=['任务"甲\n🙂','β']
    for task,name in zip(workflow["tasks"],names):task["id"]=name
    workflow["dependencies"]=[names]
    trace=parity.run_java_request(java,classpath,request,tmp_path)
    assert [r["task_id"] for r in trace["result"]["task_records"]] == names
    assert trace["result"]["makespan"] == 13
