"""V16 export audits against existing immutable contracts (not a replay engine).

Recorded PT/UT/DT remain untouched. Formula and cumulative-value checks report
errors here; nothing recalculates values for use by the scheduler.
"""
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import struct
from fogsim.environment.spec import DeviceSnapshot, ServerSnapshot, EnvironmentSnapshot
from fogsim.errors import InputError
from fogsim.input_validation import integer, finite, text
from fogsim.instances.generated import (TaskInput, EdgeInput, WorkflowInput, GenerationCause,
    GenerationAttempt, CandidateRecord, AdmissionMapping, InputArchive)
from fogsim.instances.templates import DagTaskSpec, DagDiagnostic, DagTemplate, TemplateRef
from fogsim.instances.spec import OptionSpec

TOP = {'format','schema_version','origin','initial_state','effective_config','units','environment',
       'templates','candidates','generation_attempts','capture'}


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise InputError(f'duplicate JSON field: {key}')
            result[key] = value
        return result
    def reject(value):
        raise InputError(f'non-finite JSON literal: {value}')
    try:
        result = json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=pairs, parse_constant=reject)
    except (ValueError, OSError) as exc:
        raise InputError(f'cannot read export: {exc}') from exc
    def finite(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise InputError('non-finite JSON number')
        if isinstance(value, dict):
            for item in value.values(): finite(item)
        elif isinstance(value, list):
            for item in value: finite(item)
    finite(result)
    return result


def keys(value, required, label, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise InputError(f'{label}: incorrect fields')


def same(a, b, label):
    if struct.pack('>d', a) != struct.pack('>d', b):
        raise InputError(f'{label}: binary64 mismatch: {a!r} != {b!r}')


def audit_input(value, *, require_complete=True):
    keys(value, TOP, 'input', ('diagnostics',))
    if value['format'] != 'fogsim.dynamic-replay' or type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise InputError('unsupported export format/version')
    origin = value['origin']
    keys(origin, {'language','implementation_version','code_dependency_fingerprint','rules','operation','fixture_kind','label'}, 'origin')
    keys(origin['rules'], {'sequencing','routing'}, 'origin.rules')
    if origin['language'] != 'Java' or origin['operation'] != 'fresh' or origin['fixture_kind'] not in ('native_random','scripted_boundary'):
        raise InputError('unsupported V16 Java origin')
    if origin['rules'] != {'sequencing':'FCFS','routing':'FCFS'}:
        raise InputError('V16 tool supports FCFS rules only')
    keys(value['units'], {'time','workload','data'}, 'units')
    cfg = value['effective_config']
    keys(cfg, {'num_jobs_recorded','warmup_jobs','statistics_policy','sequencing_rule','routing_rule',
               'exception_policy','event_order','guards','samplers','additional_budget'}, 'effective_config')
    integer(cfg['num_jobs_recorded'],'N',1,2**31-1); integer(cfg['warmup_jobs'],'W',0,2**31-1)
    if cfg['num_jobs_recorded']+cfg['warmup_jobs'] > 2**31-1:
        raise InputError('N+W overflow')
    keys(cfg['guards'], {'resource_queue_greater_than','stagnation_greater_than','generated_greater_than_multiplier'}, 'guards')
    keys(cfg['samplers'], {'workload','data_size','edge_data','inter_release_time','weight',
        'upload_bandwidth_edge','download_bandwidth_edge','upload_bandwidth_cloud','download_bandwidth_cloud',
        'processing_rate_device','processing_rate_edge','processing_rate_cloud','workflow_type'}, 'samplers')
    keys(cfg['samplers']['inter_release_time'], {'family','effective_mean'}, 'inter_release_time')
    capture = value['capture']
    keys(capture, {'complete','complete_attempt_count','write_interrupted','process_interrupted','termination'}, 'capture')
    if any(type(capture[k]) is not bool for k in ('complete','write_interrupted','process_interrupted')):
        raise InputError('capture flags must be boolean')
    if (type(capture['complete_attempt_count']) is not int or
            capture['complete_attempt_count'] != len(value['generation_attempts'])):
        raise InputError('capture attempt count mismatch')
    if require_complete and (not capture['complete'] or capture['write_interrupted'] or capture['process_interrupted']):
        raise InputError('capture is incomplete')
    if capture['complete'] and (capture['write_interrupted'] or capture['process_interrupted']):
        raise InputError('complete capture has interruption flag')
    initial = value['initial_state']
    keys(initial, {'B','public_seed','seed_encoding_version','run_index'}, 'initial_state')
    if type(initial['public_seed']) is not int or not -(1 << 63) <= initial['public_seed'] < 1 << 63:
        raise InputError('public seed must be signed64')
    integer(initial['run_index'],'run_index',0); finite(initial['B'],'B')
    if initial['seed_encoding_version'] != 'java-signed64-v1' or initial['run_index'] != 0 or initial['B'] != 0:
        raise InputError('V16 fresh exporter requires Java seed version, run_index=0, B=0')
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
            tasks.append(TaskInput(**dict(t, options=tuple(OptionSpec(**o) for o in t['options']))))
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
    resources = {r.id:r for r in (*environment.devices,*environment.servers)}
    by_ref = {t.ref:t for t in templates}
    for c in candidates:
        w = c.workflow_input; parents, children = by_ref[w.template_ref].adjacency()
        edges = {(e.parent_id,e.child_id):e.data_size for e in w.edges}
        for task in w.tasks:
            ti = to = 0.0
            for parent in parents[task.id]: ti += edges[parent,task.id]
            for child in children[task.id]: to += edges[task.id,child]
            same(task.total_input_data,ti,'total_input_data'); same(task.total_output_data,to,'total_output_data')
            for o in task.options:
                r = resources[o.resource_id]
                same(o.processing_time,task.workload / r.processing_rate,'PT')
                same(o.upload_time,0.0 if isinstance(r,DeviceSnapshot) else (task.data_size+ti)/r.upload_bandwidth,'UT')
                same(o.download_time,0.0 if isinstance(r,DeviceSnapshot) else (task.data_size+to)/r.download_bandwidth,'DT')
    return archive


def normalize_environment(input_value):
    """Serialization-only normalization; no input number or duration is changed."""
    e = input_value['environment']
    e['fingerprint'] = EnvironmentSnapshot(tuple(DeviceSnapshot(**d) for d in e['devices']),
        tuple(ServerSnapshot(**s) for s in e['servers']),e['parameter_source']).fingerprint


def write_json(path, value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def write_manifest(directory, provenance):
    directory = Path(directory)
    records = {p.relative_to(directory).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(directory.rglob('*')) if p.is_file() and p.relative_to(directory).as_posix() != 'manifest.json'}
    manifest = {'format':'fogsim.dynamic-manifest','schema_version':1,
                'files':records,'provenance':provenance,'scope':'V16 Java capture; Python replay NOT_EXECUTED'}
    write_json(directory/'manifest.json',manifest)
    return manifest


def verify_manifest(directory):
    directory = Path(directory); m = read_json(directory/'manifest.json')
    if m['format'] != 'fogsim.dynamic-manifest' or m['schema_version'] != 1:
        raise InputError('manifest version mismatch')
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file() and p.relative_to(directory).as_posix() != 'manifest.json'}
    if actual != set(m['files']):
        raise InputError('manifest file coverage mismatch')
    for name, expected in m['files'].items():
        p = directory/name
        if not p.resolve().is_relative_to(directory.resolve()) or hashlib.sha256(p.read_bytes()).hexdigest() != expected:
            raise InputError(f'manifest hash mismatch: {name}')
    return m
