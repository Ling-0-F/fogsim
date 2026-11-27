"""Workflow-level edge-map release. Validate the entire graph before any writes."""
from dataclasses import dataclass
from fogsim.errors import InputError, require
from fogsim.instances.generated import InputArchive
from fogsim.model.workflow import Workflow
from fogsim.model.task import EdgeDataState


@dataclass(frozen=True)
class CleanupReport:
    workflow_id: int
    status: str
    released_task_count: int = 0
    removed_mapping_entry_count: int = 0
    already_released_task_count: int = 0
    unavailable_task_count: int = 0


def release_edge_data(workflow, archive):
    """Release only runtime maps; immutable archive, topology and durations survive.

    A complete per-workflow record suffices; the run need not have terminated.
    Legacy fixed UNAVAILABLE graphs are skipped without requiring an archive.
    """
    if type(workflow) is not Workflow:
        raise InputError('release_edge_data requires Workflow')
    require(bool(workflow.tasks), 'cannot release an incomplete empty workflow')
    for task in workflow.tasks:
        task.validate_edge_data()
    if all(t.edge_data_state == EdgeDataState.UNAVAILABLE for t in workflow.tasks):
        return CleanupReport(workflow.id, 'UNAVAILABLE', unavailable_task_count=len(workflow.tasks))
    if type(archive) is not InputArchive:
        raise InputError('release_edge_data requires independent InputArchive')
    require(workflow.input_record_id is not None, 'workflow has no archived input record')
    records = {r.record_id: r.workflow_input for r in archive.candidates}
    candidate = records.get(workflow.input_record_id)
    require(candidate is not None, 'complete workflow input is missing from archive')
    require(any(a.record_id == workflow.input_record_id and a.workflow_id == workflow.id for a in archive.admissions),
            'workflow has no matching successful admission in archive')
    require((workflow.id, workflow.owner_device.id, workflow.release_time, workflow.weight,
             workflow.dag_type_id, workflow.template_hash) ==
            (candidate.candidate_id, candidate.owner_device_id, candidate.release_time, candidate.weight,
             candidate.template_ref.dag_type_id, candidate.template_ref.source_sha256), 'workflow/archive identity mismatch')
    template = next(t for t in archive.templates if t.ref == candidate.template_ref)
    require(tuple(t.id for t in workflow.tasks) == tuple(t.id for t in candidate.tasks),
            'runtime/archive task order mismatch')
    parents, children = template.adjacency()
    by_id = {t.id: t for t in workflow.tasks}
    edges = {(e.parent_id, e.child_id): e.data_size for e in candidate.edges}
    maps_seen = set()
    resources = {}
    releasing = []
    already = 0
    entries = 0
    for task, spec, template_task in zip(workflow.tasks, candidate.tasks, template.tasks):
        require(task.workflow is workflow and task.java_index == template_task.java_index, 'noncanonical task identity')
        require(tuple(task.parents) == tuple(by_id[p] for p in parents[task.id]) and
                tuple(task.children) == tuple(by_id[c] for c in children[task.id]), 'runtime topology mismatch')
        require((task.workload, task.data_size, task.total_input_data, task.total_output_data) ==
                (spec.workload, spec.data_size, spec.total_input_data, spec.total_output_data), 'incomplete task physical fields')
        require(len(task.options) == len(spec.options) and bool(task.options), 'incomplete candidate options')
        for option, saved in zip(task.options, spec.options):
            require(option.task is task and (option.resource.id, option.processing_time, option.upload_time, option.download_time) ==
                    (saved.resource_id, saved.processing_time, saved.upload_time, saved.download_time), 'candidate option mismatch')
            previous = resources.setdefault(option.resource.id, option.resource)
            require(previous is option.resource, 'noncanonical shared resource')
        if task.edge_data_state == EdgeDataState.RELEASED:
            already += 1
            continue
        require(task.edge_data_state == EdgeDataState.RETAINED, 'mixed UNAVAILABLE and dynamic edge states')
        wanted_input = {p: edges[p, task.id] for p in parents[task.id]}
        wanted_output = {c: edges[task.id, c] for c in children[task.id]}
        for mapping, wanted in ((task.input_data_by_parent, wanted_input), (task.output_data_by_child, wanted_output)):
            require(id(mapping) not in maps_seen, 'edge dictionaries must not alias')
            maps_seen.add(id(mapping))
            require(list(mapping.items()) == list(wanted.items()), 'runtime edge values/order differ from archive')
            entries += len(mapping)
        releasing.append(task)
    # No task was changed above. This commit does not invoke callbacks or RNGs.
    for task in releasing:
        task.input_data_by_parent = None
        task.output_data_by_child = None
        task.edge_data_state = EdgeDataState.RELEASED
    return CleanupReport(workflow.id, 'RELEASED' if releasing else 'ALREADY_RELEASED',
                         len(releasing), entries, already)
