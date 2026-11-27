"""Export Python's complete observed input stream, independently of trace/results."""
from dataclasses import asdict
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import platform
from fogsim.errors import InputError
from fogsim.seed import SEED_ENCODING, encode_seed
from .loader import parse_replay_input


@lru_cache(maxsize=1)
def implementation_fingerprint():
    root = Path(__file__).resolve().parents[1]
    files = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(root.rglob('*.py'))}
    payload = dict(files=files, python=platform.python_version(), implementation=platform.python_implementation())
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def export_replay_input(engine, source_config, *, dataset_role='debug'):
    """Only a terminated Python random round is exported; no sampling occurs.

    Preparation failures without an environment cannot form a standalone input.
    An unfinished generation is explicitly an incomplete capture, usable only
    for diagnosis. A normal domain failure after complete attempts may still
    have a complete (finite) capture.
    """
    version = 2 if getattr(engine, 'output_profile', 'v1') == 'v2' else 1
    if not hasattr(getattr(engine.admission, 'source', None), 'inputs'):
        raise InputError('native input capture requires a Python random source')
    rule = (lambda r: r.to_dict()) if version == 2 else _v1_rule
    if engine.run_status not in ('SUCCEEDED', 'FAILED') or engine.admission is None or engine.environment is None:
        raise InputError('input export requires a terminated round and complete environment')
    if version == 2:
        from fogsim.experiment_config import DynamicSourceConfig
        if type(source_config) is not DynamicSourceConfig:
            raise InputError('native input capture requires DynamicSourceConfig')
        inputs = engine.admission.source.inputs
        parameters = dict(environment=asdict(source_config.environment), samplers=source_config.samplers.effective_parameters())
        fingerprint = hashlib.sha256(json.dumps(parameters, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if (engine.environment.parameter_source != fingerprint or source_config.workflow_types != inputs.catalog.workflow_types):
            raise InputError('capture source configuration differs from the observed native source')
    from fogsim import __version__
    archive = engine.admission.archive
    samplers = source_config.samplers
    parameters = {k: [getattr(samplers, k).lower, getattr(samplers, k).upper] for k in
                  ('workload','data_size','edge_data','processing_rate_device','processing_rate_edge','processing_rate_cloud')}
    parameters.update(inter_release_time=dict(family='python_exponential', effective_mean=samplers.inter_release_mean),
        weight='python_two_six_two', upload_bandwidth_edge='constant_1024', download_bandwidth_edge='constant_1024',
        upload_bandwidth_cloud='python_bandwidth_cloud', download_bandwidth_cloud='python_bandwidth_cloud',
        workflow_type=[source_config.workflow_types.lower, source_config.workflow_types.upper])
    cfg = engine.config
    interrupted = engine.run_status == 'FAILED' and engine.reason_code is None
    complete = engine.initialization_complete and not engine.admission.incomplete_attempt and not interrupted
    value = dict(format='fogsim.dynamic-replay', schema_version=version,
        origin=dict(language='Python',implementation_version='fogsim-'+__version__,
            code_dependency_fingerprint=implementation_fingerprint(),
            rules=dict(sequencing=rule(cfg.sequencing_rule) if version == 2 or cfg.sequencing_rule.kind!='fcfs' else 'FCFS',
                       routing=rule(cfg.routing_rule) if version == 2 or cfg.routing_rule.kind!='fcfs' else 'FCFS'),
            operation=engine.operation, fixture_kind='native_random', label='python-observed-input'),
        initial_state=dict(B=engine.initial_cutoff, public_seed=engine.public_seed, seed_encoding_version=SEED_ENCODING,
            rng_seed_decimal=str(encode_seed(engine.public_seed)), run_index=engine.run_index),
        effective_config=dict(num_jobs_recorded=cfg.num_jobs_recorded,warmup_jobs=cfg.warmup_jobs,
            statistics_policy=cfg.statistics_policy,sequencing_rule=rule(cfg.sequencing_rule),routing_rule=rule(cfg.routing_rule),
            exception_policy=cfg.failure_policy,event_order=cfg.event_policy,
            guards=dict(resource_queue_greater_than=400,stagnation_greater_than=400000,generated_greater_than_multiplier=500),
            samplers=parameters,additional_budget=cfg.max_events),
        units=dict(time='s',workload='model_workload',data='model_data'),
        environment=asdict(archive.environment) | dict(fingerprint=archive.environment.fingerprint),
        templates=[asdict(t) for t in archive.templates],candidates=[asdict(c) for c in archive.candidates],
        generation_attempts=[dict(attempt_sequence=a.attempt_sequence,phase=a.cause.phase,owner_device_id=a.cause.owner_device_id,
            generation_clock_time=a.cause.clock_time,causing_workflow_id=a.cause.causing_workflow_id,event_sequence=a.cause.event_sequence,
            candidate_ref=a.workflow_input_ref,observed_acceptance=a.observed_acceptance,rejection_reason=a.rejection_reason)
            for a in archive.generation_attempts],
        capture=dict(complete=complete,complete_attempt_count=len(archive.generation_attempts),write_interrupted=False,
            process_interrupted=interrupted,termination='PYTHON_RUN_RETURNED' if complete else 'PARTIAL_GENERATION_FAILURE'),
        diagnostics=dict(dataset_role=dataset_role,edge_data_policy=cfg.edge_data_policy,
            rng_start_fingerprint=engine.rng_start.fingerprint if engine.rng_start else None,
            rng_final_fingerprint=engine.rng_final.fingerprint if engine.rng_final else None))
    if version == 2:
        from fogsim.rules.specs import SCORE_ENCODING_VERSION
        value.update(rule_manifest=engine.prepared_rules.rule_manifest, score_encoding_version=SCORE_ENCODING_VERSION)
        value['effective_config'].update(check_invariants=cfg.check_invariants,
            trace_enabled=cfg.trace_enabled, edge_data_policy=cfg.edge_data_policy)
    # JSON round trip converts ordered tuples into schema arrays. Validation is
    # identical to imported inputs; no XML, Java or reference is read here.
    return parse_replay_input(json.loads(json.dumps(value,allow_nan=False)),require_complete=False)


def _v1_rule(rule):
    # Preserve the pre-B03 v1 shape, including its existing resource_id null.
    return dict(kind=rule.kind, resource_id=rule.resource_id)
