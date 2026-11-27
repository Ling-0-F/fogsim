"""Java-ordered two-pass generation of complete immutable workflow inputs.

The only mutable dependency is the caller's shared input RNG. Generation never
publishes runtime objects, assigns the next G, changes B or stages events.
"""
from fogsim.errors import InputError
from fogsim.environment.spec import EnvironmentSnapshot
from fogsim.input_validation import integer, INT32_MAX
from fogsim.numerics import checked_number
from fogsim.randomness.state import RandomInputState
from .generated import EdgeInput, TaskInput, WorkflowInput, GenerationCause
from .spec import OptionSpec

REJECTED_RELEASE_NOT_FUTURE = "REJECTED_RELEASE_NOT_FUTURE"


def generate_workflow_input(inputs: RandomInputState, environment: EnvironmentSnapshot,
                            cause: GenerationCause, *, candidate_id: int) -> WorkflowInput:
    """Generate a full candidate, including when release <= the current clock.

    candidate_id is the caller's G before admission. The caller retains that G
    after rejection. A derived numeric failure raises NumericDerivationError;
    it is never converted into an ordinary release rejection or auto-retried.
    """
    if type(inputs) is not RandomInputState or type(environment) is not EnvironmentSnapshot or type(cause) is not GenerationCause:
        raise InputError("generation requires RandomInputState, EnvironmentSnapshot and GenerationCause")
    integer(candidate_id, "candidate_id", 0, INT32_MAX)
    # Pure owner/candidate validation occurs before the first draw.
    environment.eligible_resource_ids(cause.owner_device_id)
    owner = next(d for d in environment.devices if d.id == cause.owner_device_id)
    samplers, rng = inputs.samplers, inputs.rng
    template = inputs.catalog.template(samplers.workflow_type.sample(rng))
    delta = checked_number(samplers.inter_release_time.sample(rng), "inter_release_time")
    release = checked_number(cause.clock_time + delta, "clock_time + inter_release_time")
    weight = checked_number(samplers.weight.sample(rng), "workflow.weight", positive=True)
    parents, children = template.adjacency()
    values, edges, raw_tasks = {}, [], {}
    # First pass: workload, base data, then this task's children in adjacency order.
    for task in template.tasks:
        tid = task.xml_id
        workload = checked_number(samplers.workload.sample(rng), f"{tid}.workload", positive=True)
        data = checked_number(samplers.data_size.sample(rng), f"{tid}.data_size")
        output_total = 0.0
        for child in children[tid]:
            value = checked_number(samplers.edge_data.sample(rng), f"edge {tid}->{child}")
            values[tid, child] = value
            edges.append(EdgeInput(tid, child, value))
            output_total = checked_number(output_total + value, f"{tid}.total_output_data")
        raw_tasks[tid] = workload, data, output_total
    # Second pass: input accumulation order comes from parents, not sampled edges.
    tasks = []
    for task in template.tasks:
        tid = task.xml_id
        workload, data, output_total = raw_tasks[tid]
        input_total = 0.0
        for parent in parents[tid]:
            input_total = checked_number(input_total + values[parent, tid], f"{tid}.total_input_data")
        options = []
        if owner.can_process_tasks:
            pt = checked_number(workload / owner.processing_rate, f"{tid}/{owner.id}.PT", positive=True)
            options.append(OptionSpec(owner.id, 0.0, pt, 0.0))
        for server in environment.servers:
            pt = checked_number(workload / server.processing_rate, f"{tid}/{server.id}.PT", positive=True)
            # Keep addition before division, and do not include base data in totals.
            upload_data = checked_number(data + input_total, f"{tid}/{server.id}.data + input_total")
            ut = checked_number(upload_data / server.upload_bandwidth, f"{tid}/{server.id}.UT")
            download_data = checked_number(data + output_total, f"{tid}/{server.id}.data + output_total")
            dt = checked_number(download_data / server.download_bandwidth, f"{tid}/{server.id}.DT")
            options.append(OptionSpec(server.id, ut, pt, dt))
        tasks.append(TaskInput(tid, workload, data, input_total, output_total, tuple(options)))
    return WorkflowInput(candidate_id, owner.id, template.ref, release, delta, weight, tuple(tasks), tuple(edges))


def release_rejection_reason(candidate: WorkflowInput, cause: GenerationCause) -> str | None:
    """Pure release gate for future admission; None means eligible, not registered."""
    if type(candidate) is not WorkflowInput or type(cause) is not GenerationCause:
        raise InputError("release check requires WorkflowInput and GenerationCause")
    if candidate.owner_device_id != cause.owner_device_id or candidate.release_time != cause.clock_time + candidate.inter_release_time:
        raise InputError("candidate/cause owner or release-time derivation mismatch")
    return REJECTED_RELEASE_NOT_FUTURE if candidate.release_time <= cause.clock_time else None
