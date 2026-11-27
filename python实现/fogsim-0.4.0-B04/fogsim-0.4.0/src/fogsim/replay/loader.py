"""Strict self-contained v1/v2 input. Formula audits never replace durations."""
import json
import math
from pathlib import Path
from fogsim.errors import InputError
from fogsim.instances.fixed import object_fields, items
from fogsim.input_validation import finite, integer, text, choice, sha256
from fogsim.experiment_config import DynamicRunConfig, RuleConfig
from .spec import ReplayInput, ReplayInitialState, ReplayCapture, ReplayInputError
from ._decode import decode_archive
from fogsim.rules.specs import RuleSpec, SCORE_ENCODING_VERSION
from fogsim.rules.factory import install_rules, validate_rules_for_environment
from fogsim.gp.identity import validate_rule_manifest
from fogsim.gp.diagnostics import GPInputError

TOP = ('format', 'schema_version', 'origin', 'initial_state', 'effective_config', 'units',
       'environment', 'templates', 'candidates', 'generation_attempts', 'capture')


def _json_values(value):
    if type(value) is float and not math.isfinite(value):
        raise InputError('non-finite JSON number')
    if isinstance(value, dict):
        if any(type(k) is not str for k in value):
            raise InputError('JSON object keys must be strings')
        for x in value.values(): _json_values(x)
    elif isinstance(value, list):
        for x in value: _json_values(x)
    elif value is not None and type(value) not in (str, int, float, bool):
        raise InputError('expected JSON values')


def read_replay_json(path):
    def pairs(rows):
        result = {}
        for k, v in rows:
            if k in result: raise InputError(f'duplicate JSON key: {k}')
            result[k] = v
        return result
    def reject(value):
        raise InputError(f'non-finite JSON literal: {value}')
    try:
        result = json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=pairs, parse_constant=reject)
        _json_values(result)
        return result
    except (InputError, OSError, UnicodeError, ValueError, TypeError) as exc:
        raise ReplayInputError(str(exc)) from exc


def _rule(value, role="routing", version=1):
    if version == 2:
        spec = RuleSpec.from_mapping(role, value, field_path="effective_config." + role + "_rule")
        return RuleConfig(spec.kind, spec.resource_id, spec.expression)
    if value == 'FCFS': return RuleConfig()
    object_fields(value, ('kind',), ('resource_id',), 'recorded rule')
    return RuleConfig(**value)


def _config(value, origin, version):
    object_fields(value, ('num_jobs_recorded', 'warmup_jobs', 'statistics_policy', 'sequencing_rule',
        'routing_rule', 'exception_policy', 'event_order', 'guards', 'samplers', 'additional_budget',
        *(('check_invariants', 'trace_enabled', 'edge_data_policy') if version == 2 else ())), where='effective_config')
    # Explicit mapping of Java recording vocabulary to the frozen Python policy.
    choice(value['statistics_policy'], ('java_jobsCompleted', 'java_legacy'), 'statistics_policy')
    choice(value['exception_policy'], ('java_original', 'explicit_failure'), 'exception_policy')
    choice(value['event_order'], ('java_two_level_priority_queue', 'java_compatible'), 'event_order')
    guards = value['guards']
    expected = dict(resource_queue_greater_than=400, stagnation_greater_than=400000, generated_greater_than_multiplier=500)
    object_fields(guards, expected, where='guards')
    for key, v in expected.items(): integer(guards[key], 'guards.' + key, v, v)
    samplers = value['samplers']
    ranges = ('workload', 'data_size', 'edge_data', 'processing_rate_device', 'processing_rate_edge', 'processing_rate_cloud')
    profiles = dict(weight='java_TwoSixTwo', upload_bandwidth_edge='java_BandwidthEdge',
        download_bandwidth_edge='java_BandwidthEdge', upload_bandwidth_cloud='java_BandwidthCloud',
        download_bandwidth_cloud='java_BandwidthCloud')
    object_fields(samplers, (*ranges, *profiles, 'workflow_type', 'inter_release_time'), where='samplers')
    for key in (*ranges, 'workflow_type'):
        pair = items(samplers[key], key)
        if len(pair) != 2: raise InputError(f'{key}: expected lower/upper pair')
        if key == 'workflow_type':
            for x in pair: integer(x, key, 0, 19)
            if pair[0] > pair[1]: raise InputError('invalid workflow_type range')
        else:
            lo, hi = [finite(x, key, key not in ('data_size', 'edge_data')) for x in pair]
            if lo >= hi: raise InputError(f'{key}: lower must be less than upper')
    if origin['language'] == 'Python':
        profiles = dict(weight='python_two_six_two', upload_bandwidth_edge='constant_1024',
            download_bandwidth_edge='constant_1024',upload_bandwidth_cloud='python_bandwidth_cloud',
            download_bandwidth_cloud='python_bandwidth_cloud')
    for key, v in profiles.items(): choice(samplers[key], (v,), key)
    interval = samplers['inter_release_time']
    object_fields(interval, ('family', 'effective_mean'), where='inter_release_time')
    choice(interval['family'], ('python_exponential',) if origin['language']=='Python' else ('java_exponential',), 'inter_release_time.family')
    if finite(interval['effective_mean'], 'effective_mean', True) != 100:
        raise InputError('unsupported inter-release mean')
    config = DynamicRunConfig(value['num_jobs_recorded'], value['warmup_jobs'],
        routing_rule=_rule(value['routing_rule'], 'routing', version),
        sequencing_rule=_rule(value['sequencing_rule'], 'sequencing', version),
        max_events=value['additional_budget'],
        **({k: value[k] for k in ('check_invariants', 'trace_enabled', 'edge_data_policy')} if version == 2 else {}))
    if (_rule(origin['rules']['routing'], 'routing', version) != config.routing_rule or
            _rule(origin['rules']['sequencing'], 'sequencing', version) != config.sequencing_rule):
        raise InputError('origin rules disagree with effective_config')
    return config


def _arrays(value):
    """Validate JSON arrays before iterating or constructing immutable values."""
    for k in ('templates', 'candidates', 'generation_attempts'):
        items(value[k], k, nonempty=k == 'templates')
    env = value['environment']
    object_fields(env, ('devices', 'servers', 'parameter_source', 'fingerprint'), where='environment')
    items(env['devices'], 'devices'); items(env['servers'], 'servers', False)
    for t in value['templates']:
        object_fields(t, ('dag_type_id', 'source_name', 'source_sha256', 'tasks', 'dependencies', 'diagnostics'), where='template')
        items(t['tasks'], 'template.tasks'); items(t['dependencies'], 'template.dependencies', False)
        items(t['diagnostics'], 'template.diagnostics', False)
        for edge in t['dependencies']:
            if not isinstance(edge, list) or len(edge) != 2: raise InputError('dependency must be a pair')
    for c in value['candidates']:
        object_fields(c, ('record_id', 'workflow_input'), where='candidate')
        w = c['workflow_input']
        object_fields(w, ('candidate_id','owner_device_id','template_ref','release_time','inter_release_time','weight','tasks','edges'), where='workflow_input')
        items(w['tasks'], 'tasks'); items(w['edges'], 'edges', False)
        for task in w['tasks']:
            object_fields(task, ('id','workload','data_size','total_input_data','total_output_data','options'), where='task')
            items(task['options'], 'options')


def parse_replay_input(value, *, require_complete=True):
    try:
        _json_values(value)
        if type(value) is not dict: raise InputError('replay input must be an object')
        version = integer(value.get('schema_version'), 'schema_version', 1, 2)
        object_fields(value, (*TOP, *(('rule_manifest', 'score_encoding_version') if version == 2 else ())),
                      ('diagnostics',), 'replay input')
        if 'diagnostics' in value: object_fields(value['diagnostics'], (), tuple(value['diagnostics']) if isinstance(value['diagnostics'], dict) else (), 'diagnostics')
        choice(value['format'], ('fogsim.dynamic-replay',), 'format')
        integer(value['schema_version'], 'schema_version', 1, 2)
        origin = value['origin']
        object_fields(origin, ('language','implementation_version','code_dependency_fingerprint','rules','operation','fixture_kind','label'), where='origin')
        for key in ('language','implementation_version','operation','fixture_kind','label'): text(origin[key], 'origin.' + key)
        choice(origin['language'], ('Java', 'Python'), 'origin.language')
        choice(origin['operation'], ('fresh','reset','rerun','rotate_seed'), 'origin.operation')
        sha256(origin['code_dependency_fingerprint'], 'code_dependency_fingerprint')
        object_fields(origin['rules'], ('sequencing','routing'), where='origin.rules')
        units = value['units']
        object_fields(units, ('time','workload','data'), where='units')
        for k, v in dict(time='s',workload='model_workload',data='model_data').items(): choice(units[k], (v,), 'units.' + k)
        object_fields(value['initial_state'], ('B','public_seed','seed_encoding_version','run_index'), ('rng_seed_decimal',), where='initial_state')
        if 'rng_seed_decimal' in value['initial_state']:
            text(value['initial_state']['rng_seed_decimal'], 'rng_seed_decimal')
        initial = ReplayInitialState(**value['initial_state'])
        object_fields(value['capture'], ('complete','complete_attempt_count','write_interrupted','process_interrupted','termination'), where='capture')
        capture = ReplayCapture(**value['capture'])
        if require_complete and not capture.is_complete:
            raise ReplayInputError('capture is incomplete', 'REPLAY_CAPTURE_INCOMPLETE')
        config = _config(value['effective_config'], origin, version)
        if version == 2:
            choice(value['score_encoding_version'], (SCORE_ENCODING_VERSION,), 'score_encoding_version')
            validate_rule_manifest(value['rule_manifest'], prepared_rules=install_rules(config))
        _arrays(value)
        archive = decode_archive(value)
        if version == 2:
            validate_rules_for_environment(install_rules(config), archive.environment)
        # A fixed target must work for every device, independent of rejections.
        if config.routing_rule.kind == 'fixed_resource' and any(config.routing_rule.resource_id not in archive.environment.eligible_resource_ids(d.id) for d in archive.environment.devices):
            raise InputError('recorded fixed resource is not eligible for all devices')
        return ReplayInput(archive, initial, capture, config,
                           json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False))
    except (ReplayInputError, GPInputError):
        raise
    except InputError as exc:
        raise ReplayInputError(str(exc)) from exc


def load_replay_input(path, *, require_complete=True):
    import hashlib
    from dataclasses import replace
    value = parse_replay_input(read_replay_json(path), require_complete=require_complete)
    return replace(value, input_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())
