"""Build a detached runtime graph with canonical resources, without registration."""
from fogsim.errors import InputError
from fogsim.input_validation import text, finite
from fogsim.model.resource import MobileDevice, ResourceType
from fogsim.model.workflow import Workflow
from fogsim.model.task import Task, TaskOption, EdgeDataState
from fogsim.simulation.state import SystemState
from .generated import WorkflowInput
from .templates import DagTemplate


def materialize_workflow(candidate: WorkflowInput, template: DagTemplate, state: SystemState,
                         *, input_record_id: str) -> Workflow:
    """Use recorded durations verbatim; create private edge maps in template order.

    No indexes, queues, clock, counts or events change. A later centralized
    admission service publishes this graph only after all preparation succeeds.
    This is neither a fixed projection nor a replay loader/formula auditor.
    """
    if type(candidate) is not WorkflowInput or type(template) is not DagTemplate or type(state) is not SystemState:
        raise InputError("materialization requires WorkflowInput, DagTemplate and SystemState")
    text(input_record_id, "input_record_id")
    if candidate.candidate_id in state.workflows_by_id:
        raise InputError("workflow ID is already registered")
    if candidate.template_ref != template.ref or tuple(t.id for t in candidate.tasks) != tuple(t.xml_id for t in template.tasks):
        raise InputError("candidate/template identity or task order mismatch")
    parents, children = template.adjacency()
    expected_edges = tuple((t.xml_id, child) for t in template.tasks for child in children[t.xml_id])
    if tuple((e.parent_id, e.child_id) for e in candidate.edges) != expected_edges:
        raise InputError("candidate edges/order do not match template sampling order")
    owner = state.resources_by_id.get(candidate.owner_device_id)
    if not isinstance(owner, MobileDevice) or not any(owner is d for d in state.mobile_devices):
        raise InputError("candidate owner is not a canonical MOBILE resource")
    resources = ([owner] if owner.can_process_tasks else []) + list(state.servers)
    if not resources or any(state.resources_by_id.get(r.id) is not r for r in resources):
        raise InputError("candidate resources must be canonical and nonempty")
    if any(r.resource_type not in (ResourceType.EDGE, ResourceType.CLOUD) for r in state.servers):
        raise InputError("server list contains a non-server resource")
    # Fixed models may legitimately have unknown physical parameters. This new
    # dynamic builder requires actual values and leaves the old fixed path alone.
    for resource in (owner, *state.servers):
        finite(resource.processing_rate, f"{resource.id}.processing_rate", positive=True)
        if resource is not owner:
            finite(resource.upload_bandwidth, f"{resource.id}.upload_bandwidth", positive=True)
            finite(resource.download_bandwidth, f"{resource.id}.download_bandwidth", positive=True)
    for task in candidate.tasks:
        if tuple(o.resource_id for o in task.options) != tuple(r.id for r in resources):
            raise InputError("candidate options/order do not match runtime resources")
        for option in task.options:
            if option.resource_id == owner.id and (option.upload_time != 0 or option.download_time != 0):
                raise InputError("local upload/download must be zero")
    workflow = Workflow(candidate.candidate_id, owner, candidate.release_time, weight=candidate.weight,
                        dag_type_id=template.dag_type_id, template_hash=template.source_sha256, input_record_id=input_record_id)
    values = {(e.parent_id, e.child_id): e.data_size for e in candidate.edges}
    by_id = {}
    for spec, template_task in zip(candidate.tasks, template.tasks):
        task = Task(spec.id, workflow, workload=spec.workload, data_size=spec.data_size,
                    input_data_by_parent={parent: values[parent, spec.id] for parent in parents[spec.id]},
                    output_data_by_child={child: values[spec.id, child] for child in children[spec.id]},
                    total_input_data=spec.total_input_data, total_output_data=spec.total_output_data,
                    edge_data_state=EdgeDataState.RETAINED, java_index=template_task.java_index)
        task.options = [TaskOption(task, state.resources_by_id[o.resource_id], processing_time=o.processing_time,
                                   upload_time=o.upload_time, download_time=o.download_time) for o in spec.options]
        workflow.tasks.append(task)
        by_id[task.id] = task
    for parent, child in template.dependencies:
        by_id[parent].children.append(by_id[child])
        by_id[child].parents.append(by_id[parent])
    return workflow
