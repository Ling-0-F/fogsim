"""Schema-v1 structural decoder; production has no dependency on tools/."""
from fogsim.environment.spec import DeviceSnapshot, ServerSnapshot, EnvironmentSnapshot
from fogsim.errors import InputError
from fogsim.instances.generated import (TaskInput, EdgeInput, WorkflowInput, GenerationCause,
    GenerationAttempt, CandidateRecord, AdmissionMapping, InputArchive)
from fogsim.instances.templates import DagTaskSpec, DagDiagnostic, DagTemplate, TemplateRef
from fogsim.instances.spec import OptionSpec
from fogsim.instances.fixed import object_fields
from fogsim.input_validation import finite

def keys(value, required, label, optional=()):
    object_fields(value, required, optional, label)

def decode_archive(value):
    capture = value['capture']
    env = value['environment']
    keys(env, {'devices','servers','parameter_source','fingerprint'}, 'environment')
    for d in env['devices']:
        keys(d, {'id','numeric_id','processing_rate','can_process_tasks'}, 'device')
    for r in env['servers']:
        keys(r, {'id','numeric_id','type','processing_rate','upload_bandwidth','download_bandwidth'}, 'server')
    environment = EnvironmentSnapshot(tuple(DeviceSnapshot(**d) for d in env['devices']),
        tuple(ServerSnapshot(**s) for s in env['servers']), env['parameter_source'])
    # Exporter canonicalizes this to the existing Python snapshot fingerprint.
    if env['fingerprint'] != environment.fingerprint:
        raise InputError('environment fingerprint mismatch')
    templates = []
    for t in value['templates']:
        keys(t, {'dag_type_id','source_name','source_sha256','tasks','dependencies','diagnostics'}, 'template')
        for task in t['tasks']: keys(task, {'xml_id','java_index'}, 'template.task')
        for d in t['diagnostics']: keys(d, {'code','attribute','declared_value','actual_count'}, 'diagnostic')
        templates.append(DagTemplate(t['dag_type_id'],t['source_name'],t['source_sha256'],
            tuple(DagTaskSpec(**x) for x in t['tasks']), tuple(tuple(x) for x in t['dependencies']),
            tuple(DagDiagnostic(**d) for d in t['diagnostics'])))
    candidates = []
    for c in value['candidates']:
        keys(c, {'record_id','workflow_input'}, 'candidate')
        w = c['workflow_input']
        keys(w, {'candidate_id','owner_device_id','template_ref','release_time','inter_release_time','weight','tasks','edges'}, 'workflow_input')
        keys(w['template_ref'], {'dag_type_id','source_sha256'}, 'template_ref')
        tasks = []
        for t in w['tasks']:
            keys(t, {'id','workload','data_size','total_input_data','total_output_data','options'}, 'task')
            for o in t['options']:
                keys(o, {'resource_id','processing_time','upload_time','download_time'}, 'option')
            tasks.append(TaskInput(**dict(t, options=tuple(OptionSpec(
                resource_id=o['resource_id'],
                processing_time=finite(o['processing_time'], 'processing_time', True),
                upload_time=finite(o['upload_time'], 'upload_time'),
                download_time=finite(o['download_time'], 'download_time')) for o in t['options']))))
        for e in w['edges']: keys(e, {'parent_id','child_id','data_size'}, 'edge')
        candidates.append(CandidateRecord(c['record_id'], WorkflowInput(**dict(w,
            template_ref=TemplateRef(**w['template_ref']),tasks=tuple(tasks),edges=tuple(EdgeInput(**e) for e in w['edges'])))))
    attempts = []
    for a in value['generation_attempts']:
        keys(a, {'attempt_sequence','phase','owner_device_id','generation_clock_time','causing_workflow_id',
                 'event_sequence','candidate_ref','observed_acceptance','rejection_reason'}, 'attempt')
        cause = GenerationCause(a['phase'], a['owner_device_id'], a['generation_clock_time'],
                                a['causing_workflow_id'], a['event_sequence'])
        attempts.append(GenerationAttempt(a['attempt_sequence'], cause, a['candidate_ref'],
                                         a['observed_acceptance'], a['rejection_reason']))
    admissions = tuple(AdmissionMapping(c.record_id,c.workflow_input.candidate_id)
                       for c,a in zip(candidates,attempts) if a.observed_acceptance)
    archive = InputArchive(tuple(templates),environment,tuple(candidates),tuple(attempts),admissions)
    if capture['complete'] and sum(a.cause.phase == 'initialize' for a in attempts) != len(environment.devices):
        raise InputError('complete capture missing initialization attempts')
    return archive
