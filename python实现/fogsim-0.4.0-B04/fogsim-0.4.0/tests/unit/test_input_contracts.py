"""Step 1 value/reference contracts; V09/V11 building blocks, not dynamic parity."""
from dataclasses import FrozenInstanceError, replace, fields
from copy import deepcopy
import random
import pytest
from fogsim import create_engine, parse_instance
from fogsim.errors import InputError, StateError
from fogsim.environment.spec import DeviceSnapshot, ServerSnapshot, EnvironmentSnapshot
from fogsim.instances.templates import DagTaskSpec, DagTemplate, TemplateRef
from fogsim.instances.identity import resource_identities, task_identities
from fogsim.instances.generated import (
    TaskInput, EdgeInput, WorkflowInput, GenerationCause, GenerationAttempt,
    CandidateRecord, AdmissionMapping, InputArchive,
)
from fogsim.instances.spec import OptionSpec, ResourceSpec
from fogsim.model.task import EdgeDataState
from fogsim.model.workflow import Workflow


HASH = "a" * 64


def template():
    # IDs intentionally do not sort like Java positions.
    return DagTemplate(0, "tiny.xml", HASH,
        [DagTaskSpec("node-Z", 0), DagTaskSpec("node-A", 1), DagTaskSpec("node-01", 2)],
        [["node-A", "node-01"], ["node-Z", "node-01"]])


def environment():
    return EnvironmentSnapshot([DeviceSnapshot("phone-X", 0, 125, True), DeviceSnapshot("phone-3", 1, 200, True)],
        [ServerSnapshot("edge-99", 0, "EDGE", 250, 1024, 1024),
         ServerSnapshot("cloud-00", 1, "CLOUD", 500, 512, 128)], "test-values")


def candidate(wid=0, owner="phone-X", release=1, delta=1):
    tasks = [TaskInput(t.xml_id, 5000, 5120, 0 if t.java_index != 2 else 250,
                       0 if t.java_index == 2 else 125,
                       [OptionSpec(owner, 0, 40, 0), OptionSpec("edge-99", 5, 20, 6),
                        OptionSpec("cloud-00", 10, 10, 20)]) for t in template().tasks]
    # Edge sampling order differs from template dependency order.
    return WorkflowInput(wid, owner, template().ref, release, delta, 2, tasks,
                         [EdgeInput("node-Z", "node-01", 125), EdgeInput("node-A", "node-01", 125)])


def archive():
    c1 = candidate()
    rejected = candidate(1, "phone-3", 0, 0)
    c3 = candidate(1, release=2, delta=1)
    return InputArchive([template()], environment(),
        [CandidateRecord("1", c1), CandidateRecord("2", rejected), CandidateRecord("3", c3)],
        [GenerationAttempt(1, GenerationCause("initialize", "phone-X", 0), "1", True),
         GenerationAttempt(2, GenerationCause("initialize", "phone-3", 0), "2", False, "REJECTED_RELEASE_NOT_FUTURE"),
         GenerationAttempt(3, GenerationCause("after_arrival", "phone-X", 1, 0, 1), "3", True)],
        [AdmissionMapping("1", 0), AdmissionMapping("3", 1)])


def test_deep_immutability_and_exact_orders():
    t = template()
    assert t.task_mapping == (("node-Z", 0), ("node-A", 1), ("node-01", 2))
    assert t.dependencies == (("node-A", "node-01"), ("node-Z", "node-01"))
    a = archive()
    assert isinstance(a.candidates, tuple) and isinstance(a.templates[0].dependencies[0], tuple)
    assert a.admissions == (AdmissionMapping("1", 0), AdmissionMapping("3", 1))
    assert a.workflow_input("2").candidate_id == a.workflow_input("3").candidate_id == 1
    assert a.workflow_input("1").tasks is not a.workflow_input("3").tasks
    with pytest.raises(FrozenInstanceError): a.candidates[0].workflow_input.tasks[0].workload = 1
    with pytest.raises(FrozenInstanceError): a.environment.devices[0].processing_rate = 1
    tasks = list(t.tasks); edges = [list(e) for e in t.dependencies]
    other = replace(t, tasks=tasks, dependencies=edges)
    tasks.clear(); edges[0].clear()
    assert other == t
    with pytest.raises(InputError): a.workflow_input("missing")


@pytest.mark.parametrize("changes", [
    {"dag_type_id": True}, {"dag_type_id": 20}, {"source_sha256": "bad"}, {"source_name": " "},
    {"tasks": []}, {"tasks": [DagTaskSpec("x", 1)]},
    {"tasks": [DagTaskSpec("x", 0), DagTaskSpec("x", 1)]},
    {"dependencies": [("node-Z", "missing")]}, {"dependencies": [("node-Z", "node-Z")]},
    {"dependencies": [("node-Z", "node-A"), ("node-Z", "node-A")]},
    {"dependencies": [("node-Z", "node-A"), ("node-A", "node-Z")]},
])
def test_template_contract_errors(changes):
    with pytest.raises(InputError): replace(template(), **changes)


@pytest.mark.parametrize("factory", [
    lambda: DagTaskSpec(" ", 0), lambda: DagTaskSpec("x", True), lambda: TemplateRef(-1, HASH),
    lambda: DeviceSnapshot("m", True, 1, True), lambda: DeviceSnapshot("m", 0, float("inf"), True),
    lambda: DeviceSnapshot("m", 0, 1, 1), lambda: ServerSnapshot("s", 0, "MOBILE", 1, 1, 1),
    lambda: ServerSnapshot("s", 0, "EDGE", 0, 1, 1), lambda: ServerSnapshot("s", 0, "EDGE", 1, True, 1),
    lambda: EdgeInput("x", "x", 0), lambda: EdgeInput("x", "y", -1),
    lambda: EdgeInput("x", "y", float("nan")), lambda: EdgeInput("x", "y", True),
])
def test_scalar_input_errors(factory):
    with pytest.raises(InputError): factory()


@pytest.mark.parametrize("changes", [
    {"workload": 0}, {"data_size": -1}, {"total_input_data": float("inf")}, {"total_output_data": True},
    {"options": []}, {"options": [OptionSpec("M0", 0, 0, 0)]},
    {"options": [OptionSpec("M0", 0, True, 0)]}, {"options": [OptionSpec("M0", 0, 10**400, 0)]},
    {"options": [OptionSpec("M0", 0, 1, 0), OptionSpec("M0", 0, 2, 0)]},
])
def test_task_input_errors(changes):
    with pytest.raises(InputError): replace(candidate().tasks[0], **changes)


@pytest.mark.parametrize("changes", [
    {"candidate_id": True}, {"candidate_id": -1}, {"candidate_id": 1 << 31}, {"template_ref": "hash"},
    {"release_time": float("inf")}, {"inter_release_time": -1}, {"weight": 0},
    {"tasks": []}, {"tasks": [candidate().tasks[0], candidate().tasks[0]]},
    {"edges": [EdgeInput("node-Z", "absent", 1)]},
])
def test_workflow_input_errors(changes):
    with pytest.raises(InputError): replace(candidate(), **changes)


def test_environment_identity_and_fingerprint():
    e = environment()
    assert e.eligible_resource_ids("phone-3") == ("phone-3", "edge-99", "cloud-00")
    assert e.fingerprint == deepcopy(e).fingerprint
    assert replace(e, parameter_source="other").fingerprint != e.fingerprint
    with pytest.raises(InputError): e.eligible_resource_ids("edge-99")
    for changes in (
        {"devices": []}, {"devices": [DeviceSnapshot("phone-X", 1, 1, True)]},
        {"servers": list(reversed(e.servers))},
        {"servers": [replace(e.servers[0], id="phone-X")]},
        {"devices": [replace(e.devices[0], can_process_tasks=False)], "servers": []},
        {"servers": [replace(e.servers[1], numeric_id=0), replace(e.servers[0], numeric_id=1)]},
    ):
        with pytest.raises(InputError): replace(e, **changes)


@pytest.mark.parametrize("factory", [
    lambda: GenerationCause("initialize", "m", 1),
    lambda: GenerationCause("initialize", "m", 0, 0),
    lambda: GenerationCause("initialize", "m", 0, event_sequence=1),
    lambda: GenerationCause("after_arrival", "m", 1),
    lambda: GenerationCause("after_arrival", "m", 1, 0, True),
    lambda: GenerationAttempt(0, GenerationCause("initialize", "m", 0), "0", True),
    lambda: GenerationAttempt(1, GenerationCause("initialize", "m", 0), "2", True),
    lambda: GenerationAttempt(1, GenerationCause("initialize", "m", 0), "1", 1),
    lambda: GenerationAttempt(1, GenerationCause("initialize", "m", 0), "1", True, "reason"),
    lambda: GenerationAttempt(1, GenerationCause("initialize", "m", 0), "1", False),
])
def test_attempt_errors(factory):
    with pytest.raises(InputError): factory()


@pytest.mark.parametrize("defect", ["unknown_template", "missing_edge", "task_order", "option_order",
    "other_mobile_option", "local_communication", "wrong_owner", "wrong_id", "release_addition",
    "wrong_trigger", "wrong_trigger_owner", "wrong_trigger_clock", "wrong_acceptance", "attempt_gap",
    "orphan_candidate", "missing_candidate", "duplicate_record", "missing_admission", "wrong_admission",
    "duplicate_template", "edge_sampling_order", "initialize_order", "duplicate_arrival_trigger"])
def test_archive_reference_errors(defect):
    a = archive(); candidates = list(a.candidates); attempts = list(a.generation_attempts)
    workflow = candidates[0].workflow_input
    if defect == "unknown_template": workflow = replace(workflow, template_ref=TemplateRef(1, HASH))
    elif defect == "missing_edge": workflow = replace(workflow, edges=workflow.edges[:1])
    elif defect == "edge_sampling_order": workflow = replace(workflow, edges=tuple(reversed(workflow.edges)))
    elif defect == "task_order": workflow = replace(workflow, tasks=tuple(reversed(workflow.tasks)))
    elif defect in ("option_order", "other_mobile_option", "local_communication"):
        task = workflow.tasks[0]
        options = list(task.options)
        if defect == "option_order": options.reverse()
        elif defect == "other_mobile_option": options[0] = replace(options[0], resource_id="phone-3")
        else: options[0] = replace(options[0], upload_time=1)
        workflow = replace(workflow, tasks=(replace(task, options=options), *workflow.tasks[1:]))
    elif defect == "wrong_owner": workflow = replace(workflow, owner_device_id="unknown")
    elif defect == "wrong_id": workflow = replace(workflow, candidate_id=1)
    elif defect == "release_addition": workflow = replace(workflow, release_time=3)
    elif defect.startswith("wrong_trigger"):
        cause = attempts[2].cause
        if defect == "wrong_trigger": cause = replace(cause, causing_workflow_id=9)
        elif defect == "wrong_trigger_owner": cause = replace(cause, owner_device_id="phone-3")
        else: cause = replace(cause, clock_time=2)
        attempts[2] = replace(attempts[2], cause=cause)
    elif defect == "wrong_acceptance":
        attempts[0] = replace(attempts[0], observed_acceptance=False, rejection_reason="REJECTED_RELEASE_NOT_FUTURE")
    elif defect == "attempt_gap": attempts.pop(1)
    elif defect == "orphan_candidate": attempts.pop()
    elif defect == "missing_candidate": candidates.pop()
    elif defect == "duplicate_record": candidates[1] = replace(candidates[1], record_id="1")
    elif defect == "missing_admission":
        with pytest.raises(InputError): replace(a, admissions=[])
        return
    elif defect == "wrong_admission":
        with pytest.raises(InputError): replace(a, admissions=[AdmissionMapping("1", 0), AdmissionMapping("2", 1)])
        return
    elif defect == "duplicate_template":
        with pytest.raises(InputError): replace(a, templates=[template(), template()])
        return
    elif defect == "initialize_order":
        attempts[0] = replace(attempts[0], cause=replace(attempts[0].cause, owner_device_id="phone-3"))
    elif defect == "duplicate_arrival_trigger":
        candidates.append(CandidateRecord("4", candidate(2, release=2, delta=1)))
        attempts.append(GenerationAttempt(4, attempts[2].cause, "4", True))
    candidates[0] = replace(candidates[0], workflow_input=workflow)
    with pytest.raises(InputError): replace(a, candidates=candidates, generation_attempts=attempts)


def test_no_rng_during_contract_construction(monkeypatch):
    state = random.getstate()
    def forbidden(*args, **kwargs): raise AssertionError("input validation cannot sample")
    monkeypatch.setattr(random, "Random", forbidden)
    monkeypatch.setattr(random, "random", forbidden)
    assert archive().environment.fingerprint
    assert random.getstate() == state


def test_resource_and_task_mapping_uses_positions_only():
    resources = [ResourceSpec("cloud-999", "CLOUD"), ResourceSpec("phone-42", "MOBILE"),
                 ResourceSpec("edge-10", "EDGE"), ResourceSpec("phone-00", "MOBILE"), ResourceSpec("edge-2", "EDGE")]
    assert [(r.id, r.numeric_id) for r in resource_identities(resources)] == [
        ("cloud-999", 2), ("phone-42", 0), ("edge-10", 0), ("phone-00", 1), ("edge-2", 1)]
    assert task_identities(["ID10", "ID2", " 原 ID "]) == (("ID10", 0), ("ID2", 1), (" 原 ID ", 2))


def test_fixed_graph_shares_canonical_resources_not_cross_run_objects(raw):
    data = deepcopy(raw)
    other = deepcopy(data["workflows"][0]); other["id"] = 37
    data["workflows"].append(other)
    spec = parse_instance(data)
    left = create_engine(spec); right = create_engine(spec)
    state = left.state
    for workflow in state.workflows_by_id.values():
        assert workflow.owner_device is state.resources_by_id[workflow.owner_device.id]
        assert workflow.weight is None and workflow.input_record_id is None
        for task in workflow.tasks:
            assert state.tasks_by_key[task.key] is task
            assert right.state.tasks_by_key[task.key] is not task
            assert task.workflow is workflow and task.edge_data_state == EdgeDataState.UNAVAILABLE
            assert task.java_index is None and task.workload is None
            for option in task.options:
                assert option.task is task and option.resource is state.resources_by_id[option.resource.id]
            for child in task.children:
                assert task in child.parents and child is state.tasks_by_key[child.key]
    assert state.tasks_by_key[(0, "A")] is not state.tasks_by_key[(37, "A")]
    assert state.tasks_by_key[(0, "A")].options[1].resource is state.tasks_by_key[(37, "A")].options[1].resource
    assert left.run().to_dict() == right.run().to_dict()
    assert not any(f.name in ("context", "archive", "catalog") for f in fields(Workflow))


def test_edge_data_state_accessors(engine):
    task = next(iter(engine.state.tasks_by_key.values()))
    with pytest.raises(StateError, match="UNAVAILABLE"): task.edge_data()
    task.edge_data_state = EdgeDataState.RETAINED
    with pytest.raises(StateError, match="inconsistent"): task.edge_data()
    task.input_data_by_parent = {}; task.output_data_by_child = {"B": 100}
    assert task.edge_data() == ({}, {"B": 100})
    task.edge_data_state = EdgeDataState.RELEASED
    with pytest.raises(StateError, match="inconsistent"): task.edge_data()
    task.input_data_by_parent = task.output_data_by_child = None
    with pytest.raises(StateError, match="RELEASED"): task.edge_data()


def test_retained_runtime_maps_cannot_mutate_archive(engine):
    a = archive()
    original = a.workflow_input("1")
    task = next(iter(engine.state.tasks_by_key.values()))
    task.input_data_by_parent = {}
    task.output_data_by_child = {e.child_id: e.data_size for e in original.edges if e.parent_id == "node-Z"}
    task.edge_data_state = EdgeDataState.RETAINED
    task.output_data_by_child["node-01"] = 999
    task.output_data_by_child.clear()
    assert original.edges[0].data_size == 125
    assert a.workflow_input("1") == original
