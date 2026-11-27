"""Lossy fixed projection; both fixed engines must consume this same InstanceSpec."""
from fogsim.errors import InputError
from fogsim.instances.spec import InstanceSpec, ResourceSpec, WorkflowSpec, TaskSpec
from .spec import ReplayInput, ReplayInputError


def export_fixed_instance(replay_input):
    if type(replay_input) is not ReplayInput: raise InputError('expected ReplayInput')
    if not replay_input.capture.is_complete:
        raise ReplayInputError('fixed acceptance requires complete capture', 'REPLAY_CAPTURE_INCOMPLETE')
    archive = replay_input.archive
    templates = {t.ref: t for t in archive.templates}
    resources = tuple(ResourceSpec(d.id, 'MOBILE', d.can_process_tasks) for d in archive.environment.devices)
    resources += tuple(ResourceSpec(s.id, s.type) for s in archive.environment.servers)
    workflows = []
    for record, attempt in zip(archive.candidates, archive.generation_attempts):
        if not attempt.observed_acceptance: continue
        w = record.workflow_input
        workflows.append(WorkflowSpec(w.candidate_id, w.owner_device_id, w.release_time,
            tuple(TaskSpec(t.id, t.options) for t in w.tasks), templates[w.template_ref].dependencies))
    if not workflows: raise InputError('fixed projection has no accepted workflows; legacy fixed format requires nonempty input')
    return InstanceSpec(resources, tuple(workflows))


def fixed_projection_metadata(replay_input):
    return dict(kind='fixed_projection', source_format='fogsim.dynamic-replay', schema_version=1,
        accepted_record_ids=[a.workflow_input_ref for a in replay_input.archive.generation_attempts if a.observed_acceptance],
        losses=['rejected_attempts', 'dynamic_generation_call_positions', 'statistical_window',
                'physical_input_fields_not_representable_in_legacy_format'],
        metrics_scope='all projected workflows run to completion in both fixed engines; do not compare original dynamic metrics',
        java_adapter_scope='FCFS/fixed_resource only; physical rate/bandwidth placeholders are not validated')
