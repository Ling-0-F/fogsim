"""Python-only native capture/replay evidence; no Java GP comparator.

Only the explicit provenance/source-operation paths below are excluded.
All other diagnostics, decisions, physical values and state are compared.
"""
from copy import deepcopy
from dataclasses import asdict
import hashlib
from pathlib import Path
import struct
from fogsim.errors import InputError
from fogsim.io import write_json_atomic
from fogsim.serialization.result import decode_result
from .loader import read_replay_json, load_replay_input

NATIVE_EXCLUSIONS = (
    ('diagnostics', 'operation'),
    ('diagnostics', 'rng_start_fingerprint'),
    ('diagnostics', 'rng_ready_fingerprint'),
    ('diagnostics', 'rng_final_fingerprint'),
    ('diagnostics', 'comparison'),
    ('diagnostics', 'comparison_status'),
    ('diagnostics', 'replay_purpose'),
    ('diagnostics', 'original_reference_trajectory_eligible'),
    ('diagnostics', 'coverage_status'),
    ('diagnostics', 'recorded_behavior_config'),
    ('source_summary', 'kind'),
    ('source_summary', 'coverage'),
    ('source_summary', 'purpose'),
    ('source_summary', 'new_experiment'),
    ('source_summary', 'available_attempt_count'),
    ('source_summary', 'consumed_record_count'),
    ('source_summary', 'validated_attempt_count'),
    ('source_summary', 'remaining_attempt_count'),
    ('source_summary', 'input_capture_complete'),
    ('source_summary', 'last_call'),
    ('source_summary', 'failure'),
    ('source_summary', 'rng_used'),
    ('rule_manifest', 'bindings', 'routing', 'source', 'expression'),
    ('rule_manifest', 'bindings', 'routing', 'source', 'source_sha256'),
    ('rule_manifest', 'bindings', 'sequencing', 'source', 'expression'),
    ('rule_manifest', 'bindings', 'sequencing', 'source', 'source_sha256'),
)


def strict_difference(expected, actual, path='$'):
    def diff(reason):return dict(field_path=path, expected=expected, actual=actual, reason=reason)
    if type(expected) is not type(actual): return diff('type differs')
    if type(expected) is dict:
        if set(expected) != set(actual): return diff('object fields differ')
        if set(expected) == {'kind','bits'} and expected['kind'] == actual['kind'] == 'f64':
            def nan(bits):
                n=int(bits,16)
                return n & 0x7ff0000000000000 == 0x7ff0000000000000 and n & 0xfffffffffffff != 0
            if nan(expected['bits']) and nan(actual['bits']):return None
        for key in expected:
            d=strict_difference(expected[key],actual[key],path+'.'+key)
            if d is not None:return d
        return None
    if type(expected) in (list,tuple):
        for i,(a,b) in enumerate(zip(expected,actual)):
            d=strict_difference(a,b,f'{path}[{i}]')
            if d is not None:return d
        return None if len(expected)==len(actual) else diff('array length differs')
    if type(expected) is float:
        if struct.pack('>d',expected)==struct.pack('>d',actual):return None
        return dict(diff('binary64 differs'),expected_bits=struct.pack('>d',expected).hex(),actual_bits=struct.pack('>d',actual).hex())
    return None if expected==actual else diff('value differs')


def _project(value):
    value=deepcopy(value)
    for path in NATIVE_EXCLUSIONS:
        parent=value
        for key in path[:-1]:
            if type(parent) is not dict or key not in parent:break
            parent=parent[key]
        else:
            if type(parent) is dict:parent.pop(path[-1],None)
    return value


def compare_native_results(native,replay):
    native=native.to_dict() if hasattr(native,'to_dict') else native
    replay=replay.to_dict() if hasattr(replay,'to_dict') else replay
    decode_result(native);decode_result(replay)
    expected=deepcopy(native)
    if 'replay_rules' in replay['diagnostics']:
        expected['diagnostics']['replay_rules']=dict(recorded=deepcopy(native['rule_manifest']),active=deepcopy(replay['rule_manifest']),migration=None)
    difference=strict_difference(_project(expected),_project(replay))
    return dict(passed=difference is None,
        classification=('NORMAL_PARITY_PASSED' if native['status']==replay['status']=='SUCCEEDED'
            and native['events'] and replay['events'] else 'CONTRACT_CHECK_PASSED') if difference is None else 'FAILED',
        first_difference=difference,exclusion_whitelist=['.'.join(p) for p in NATIVE_EXCLUSIONS],
        scope='Python native/replay only; all non-excluded diagnostics/state/trace retained',cross_language_acceptance=False)


def _sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_native_replay_bundle(engine,source_config,directory,*,dataset_role='debug'):
    from .export_input import export_replay_input
    if engine.output_profile!='v2':raise InputError('native v2 bundle requires v2 output')
    inp=export_replay_input(engine,source_config,dataset_role=dataset_role)
    if not inp.capture.is_complete:raise InputError('native verification bundle requires complete capture')
    result=engine.result().to_dict();directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    write_json_atomic(directory/'input.json',inp.to_dict());write_json_atomic(directory/'reference.json',result)
    manifest=dict(format='fogsim.native-replay-manifest',schema_version=2,reference_kind='python-native-result',
        rule_pair_id=result['rule_manifest']['rule_pair_id'],input_format='fogsim.dynamic-replay',input_schema_version=inp.schema_version,
        source_code_fingerprint=inp.to_dict()['origin']['code_dependency_fingerprint'],
        files={name:_sha(directory/name) for name in ('input.json','reference.json')},exclusion_whitelist=['.'.join(p) for p in NATIVE_EXCLUSIONS])
    write_json_atomic(directory/'manifest.json',manifest);return manifest


def compare_native_reference(engine,result,reference,*,manifest_path,input_path,reference_path):
    report=compare_native_results(reference,result);report.update(passed=False,classification='FAILED')
    inp,source=engine.replay_input,engine.admission.source
    if source.purpose!='verify_reference':report['classification']='NOT_COMPARED';return report
    if result.reason_code=='REPLAY_INPUT_EXHAUSTED':report['classification']='INPUT_COVERAGE_INSUFFICIENT';return report
    if result.reason_code=='REPLAY_INPUT_DIVERGENCE':return report
    if not engine.config.trace_enabled or not reference['events']:
        report.update(classification='NOT_EXECUTED',reason='full native verification requires two detailed traces');return report
    if not inp.capture.is_complete or result.status!='SUCCEEDED' or reference['status']!='SUCCEEDED':
        report['reason']='normal closed loop requires complete capture and two successful runs';return report
    recorded=inp.recorded_rule_manifest
    if recorded['rule_pair_id']!=reference['rule_manifest']['rule_pair_id'] or recorded['rule_pair_id']!=engine.prepared_rules.rule_pair_id:
        raise InputError('GP_RULE_IDENTITY_MISMATCH: native reference rule pair differs')
    rules=result.diagnostics['replay_rules']
    if rules['recorded']!=recorded or rules['active']!=result.rule_manifest or rules['migration'] is not None:
        raise InputError('GP_RULE_IDENTITY_MISMATCH: native replay provenance differs')
    if source.position!=len(inp.archive.generation_attempts):
        report['first_difference']=dict(field_path='$.input_consumption.count',expected=len(inp.archive.generation_attempts),actual=source.position);return report
    report['input_first_difference']=strict_difference(asdict(inp.archive),asdict(engine.admission.archive),'$.input_consumption')
    if report['input_first_difference'] is not None:return report
    if None in (manifest_path,input_path,reference_path):
        report.update(classification='NOT_EXECUTED',reason='exact input/reference/manifest binding required');return report
    manifest_path,input_path,reference_path=map(Path,(manifest_path,input_path,reference_path));manifest=read_replay_json(manifest_path)
    expected=dict(format='fogsim.native-replay-manifest',schema_version=2,reference_kind='python-native-result',rule_pair_id=recorded['rule_pair_id'],
        input_format='fogsim.dynamic-replay',input_schema_version=inp.schema_version,source_code_fingerprint=inp.to_dict()['origin']['code_dependency_fingerprint'],
        files={name:_sha(path) for name,path in [('input.json',input_path),('reference.json',reference_path)]},
        exclusion_whitelist=['.'.join(p) for p in NATIVE_EXCLUSIONS])
    if (manifest!=expected or input_path.resolve()!=manifest_path.resolve().parent/'input.json' or
            reference_path.resolve()!=manifest_path.resolve().parent/'reference.json' or
            load_replay_input(input_path).to_dict()!=inp.to_dict() or read_replay_json(reference_path)!=reference):
        raise InputError('native reference manifest binding mismatch')
    report['binding']=dict(passed=True,manifest_sha256=_sha(manifest_path),files=expected['files'],rule_pair_id=recorded['rule_pair_id'])
    report['counts']=dict(events=len(result.events),decisions=len(result.decisions),attempts=source.position)
    if report['first_difference'] is None:report.update(passed=True,classification='NORMAL_PARITY_PASSED')
    return report
