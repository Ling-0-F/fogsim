from dataclasses import replace, fields
import pytest
from test_workflow_generation import inputs_for, template, environment
from fogsim import generate_workflow_input, build_environment, materialize_workflow
from fogsim.errors import InputError
from fogsim.instances.generated import GenerationCause
from fogsim.instances.templates import TemplateRef
from fogsim.model.task import EdgeDataState


def test_materialization_preserves_all_values_and_canonical_references():
    inputs = inputs_for(); env = environment(); state = build_environment(env)
    candidate = generate_workflow_input(inputs, env, GenerationCause("initialize", "phone-X", 0), candidate_id=0)
    before = inputs.snapshot()
    workflow = materialize_workflow(candidate, template(), state, input_record_id="1")
    assert inputs.snapshot() == before
    assert not state.workflows_by_id and not state.tasks_by_key and not state.pending_arrivals
    assert workflow.owner_device is state.mobile_devices[0]
    assert workflow.id == 0 and workflow.weight == candidate.weight
    assert workflow.input_record_id == "1" and workflow.template_hash == template().source_sha256
    assert workflow.dag_type_id == 0 and workflow.completion_time is None
    assert not workflow.completed_executions and not workflow.completion_registered
    for index, (task, spec) in enumerate(zip(workflow.tasks, candidate.tasks)):
        assert task.java_index == index and task.id == spec.id
        assert task.workflow is workflow and not task.completed and not task.dispatched
        assert (task.workload, task.data_size, task.total_input_data, task.total_output_data) == (
            spec.workload, spec.data_size, spec.total_input_data, spec.total_output_data)
        assert task.edge_data_state is EdgeDataState.RETAINED
        for option, original in zip(task.options, spec.options):
            assert option.task is task and option.resource is state.resources_by_id[original.resource_id]
            assert (option.processing_time, option.upload_time, option.download_time) == (
                original.processing_time, original.upload_time, original.download_time)
            assert option.ready_time == option.priority == 0
    z, a, join = workflow.tasks
    assert join.parents == [a, z] and z.children == a.children == [join]
    assert list(join.input_data_by_parent) == ["A", "Z"]
    assert z.input_data_by_parent == {} and join.output_data_by_child == {}
    assert z.output_data_by_child["join"] == join.input_data_by_parent["Z"] == candidate.edges[0].data_size
    assert not any(f.name in ("context", "archive", "catalog", "rng") for f in fields(workflow))


def test_multiple_devices_share_servers_but_not_workflows_maps_or_cross_run_resources():
    inputs = inputs_for(); env = environment()
    state = build_environment(env); other_state = build_environment(env)
    candidates = [generate_workflow_input(inputs, env, GenerationCause("initialize", d.id, 0), candidate_id=i)
                  for i, d in enumerate(env.devices)]
    graphs = [materialize_workflow(c, template(), state, input_record_id=str(i + 1)) for i, c in enumerate(candidates)]
    other = materialize_workflow(candidates[0], template(), other_state, input_record_id="1")
    assert graphs[0].tasks[0] is not graphs[1].tasks[0]
    assert graphs[0].tasks[0].options[1].resource is graphs[1].tasks[0].options[1].resource is state.servers[0]
    assert other.tasks[0].options[1].resource is not state.servers[0]
    assert other.tasks[0].output_data_by_child is not graphs[0].tasks[0].output_data_by_child
    graphs[0].tasks[0].output_data_by_child.clear()
    assert candidates[0].edges and other.tasks[0].output_data_by_child
    assert graphs[1].tasks[0].output_data_by_child


@pytest.mark.parametrize("defect", ["template_hash", "task_order", "edge_order", "missing_edge", "owner",
    "option_order", "other_device_option", "local_communication", "duplicate_registered_id", "record_id"])
def test_invalid_materialization_does_not_publish_any_state(defect):
    inputs = inputs_for(); env = environment(); state = build_environment(env)
    c = generate_workflow_input(inputs, env, GenerationCause("initialize", "phone-X", 0), candidate_id=0)
    record_id = "1"
    if defect == "template_hash": c = replace(c, template_ref=TemplateRef(0, "b" * 64))
    elif defect == "task_order": c = replace(c, tasks=tuple(reversed(c.tasks)))
    elif defect == "edge_order": c = replace(c, edges=tuple(reversed(c.edges)))
    elif defect == "missing_edge": c = replace(c, edges=c.edges[:1])
    elif defect == "owner": c = replace(c, owner_device_id="absent")
    elif defect == "duplicate_registered_id": state.workflows_by_id[0] = object()
    elif defect == "record_id": record_id = " "
    else:
        options = list(c.tasks[0].options)
        if defect == "option_order": options.reverse()
        elif defect == "other_device_option": options[0] = replace(options[0], resource_id="phone-Y")
        else: options[0] = replace(options[0], upload_time=1)
        c = replace(c, tasks=(replace(c.tasks[0], options=tuple(options)), *c.tasks[1:]))
    before = dict(state.workflows_by_id)
    with pytest.raises(InputError): materialize_workflow(c, template(), state, input_record_id=record_id)
    assert state.workflows_by_id == before and not state.tasks_by_key and not state.pending_arrivals
    assert state.clock_time == 0 and all(not r.waiting_queue for r in state.resources_by_id.values())


def test_materialization_uses_recorded_durations_without_recalculating():
    inputs = inputs_for(); env = environment(); state = build_environment(env)
    c = generate_workflow_input(inputs, env, GenerationCause("initialize", "phone-X", 0), candidate_id=0)
    altered = replace(c.tasks[0].options[1], processing_time=123.5)
    c = replace(c, tasks=(replace(c.tasks[0], options=(c.tasks[0].options[0], altered, c.tasks[0].options[2])), *c.tasks[1:]))
    graph = materialize_workflow(c, template(), state, input_record_id="1")
    assert graph.tasks[0].options[1].processing_time == 123.5
    # Replay formula auditing will be separate; materialization never overwrites input.


@pytest.mark.parametrize("resource,field,value", [
    ("phone-X", "processing_rate", None), ("phone-X", "processing_rate", 0),
    ("edge-X", "processing_rate", float("nan")), ("edge-X", "upload_bandwidth", None),
    ("cloud-X", "download_bandwidth", 0),
])
def test_dynamic_materialization_requires_actual_physical_values(resource, field, value):
    inputs = inputs_for(); env = environment(); state = build_environment(env)
    c = generate_workflow_input(inputs, env, GenerationCause("initialize", "phone-X", 0), candidate_id=0)
    setattr(state.resources_by_id[resource], field, value)
    with pytest.raises(InputError): materialize_workflow(c, template(), state, input_record_id="1")
    assert not state.workflows_by_id and not state.tasks_by_key
