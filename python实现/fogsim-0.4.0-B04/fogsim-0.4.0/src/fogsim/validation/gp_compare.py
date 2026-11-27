"""Strict v2 GP comparison. Numerical policy follows declared schema positions.

No scheduler imports this module; reference files are opened only by post-run callers.
"""
from copy import deepcopy
import hashlib,math,struct,re
from pathlib import Path
from fogsim.errors import InputError
from fogsim.gp.identity import validate_rule_manifest
from fogsim.serialization.f64 import decode_f64,encode_f64
from fogsim.rules.specs import SCORE_ENCODING_VERSION,NUMERIC_SEMANTICS_VERSION


def _bits(v):return struct.pack('>d',v).hex()
def _class(v):return 'NAN' if math.isnan(v) else 'POSITIVE_INFINITY' if v==math.inf else 'NEGATIVE_INFINITY' if v==-math.inf else 'NEGATIVE_ZERO' if v==0 and _bits(v).startswith('8') else 'POSITIVE_ZERO' if v==0 else 'FINITE'

def first_difference(expected,actual,*,metric_paths=frozenset(),raw_f64=False):
    """Type/order exact. All physical floats bit-exact; only named metrics tolerate."""
    def walk(a,b,path=(),nan_equal=True):
        display='$'+''.join(f'[{k}]' if type(k) is int else '.'+str(k) for k in path)
        def diff(reason,**extra):return dict(field_path=display,expected=a,actual=b,reason=reason,**extra)
        if type(a) is dict and set(a)=={'kind','bits'} and a.get('kind')=='f64':
            decode_f64(a,field_path=display);decode_f64(b,field_path=display)
        if type(a) is not type(b):return diff('type differs')
        if type(a) is dict:
            if set(a)=={'kind','bits'} and a.get('kind')=='f64':
                av,bv=decode_f64(a,field_path=display),decode_f64(b,field_path=display)
                if a['bits']==b['bits'] or nan_equal and not raw_f64 and math.isnan(av) and math.isnan(bv):return None
                return diff('binary64 score differs',expected_bits=a['bits'],actual_bits=b['bits'],expected_class=_class(av),actual_class=_class(bv))
            if a.keys()!=b.keys():return diff('object fields differ')
            for key in a:
                d=walk(a[key],b[key],path+(key,),nan_equal and a.get('kind')!='constant')
                if d is not None:return d
            return None
        if type(a) in (list,tuple):
            for i,(left,right) in enumerate(zip(a,b)):
                d=walk(left,right,path+(i,),nan_equal)
                if d is not None:return d
            return None if len(a)==len(b) else diff('array length differs after common prefix')
        if type(a) is float:
            if not math.isfinite(a) or not math.isfinite(b):raise InputError(display+': non-finite number outside declared f64 fields')
            if _bits(a)==_bits(b):return None
            if path in metric_paths and not (a==0.0 and b==0.0) and math.isclose(a,b,abs_tol=1e-9,rel_tol=1e-12):return None
            return diff('binary64 physical/metric value differs',expected_bits=_bits(a),actual_bits=_bits(b),expected_class=_class(a),actual_class=_class(b))
        return None if a==b else diff('value differs')
    return walk(expected,actual)


def compare_probes(common,python,java):
    """Compare independent observations; Java class names remain raw evidence."""
    if python.get('numeric_semantics_version')!=NUMERIC_SEMANTICS_VERSION or java.get('numeric_semantics_version')!=NUMERIC_SEMANTICS_VERSION:
        raise InputError('GP_RULE_IDENTITY_MISMATCH: same-semantics comparison requires frozen target versions')
    if [c['id'] for c in common['cases']]!=[c['id'] for c in python['cases']] or [c['id'] for c in common['cases']]!=[c['id'] for c in java['cases']]:
        return dict(passed=False,classification='FAILED',first_difference=dict(field_path='$.cases',reason='missing/reordered case coverage'))
    reports=[]
    for c,a,b in zip(common['cases'],python['cases'],java['cases']):
        b=deepcopy(b);classes=b.pop('loaded_node_classes',None)
        if c['mode']=='parse' and b['status']=='OK':
            nodes=b['expression']['ast']['nodes'];expected=[]
            op_classes={'+':'Add','-':'Sub','*':'Mul','/':'Div','Max':'Max','Min':'Min'}
            for n in nodes:expected.append('fogsim.adapter.StageDGP$ReadFeature' if n['kind']=='feature' else 'fogsim.adapter.StageDGP$ReadConstant' if n['kind']=='constant' else 'mengxu.gp.function.'+op_classes[n['op']])
            if classes!=expected:raise InputError('Java did not export the actual expected original GPNode classes')
        for row in (a,b):
            if 'rule_manifest' in row:validate_rule_manifest(row['rule_manifest'])
        difference=first_difference(a,b,raw_f64=c['mode']=='f64')
        reports.append(dict(id=c['id'],mode=c['mode'],passed=difference is None,classification=('NORMAL_PARITY_PASSED' if a['status']=='OK' else 'CONTRACT_CHECK_PASSED') if difference is None else 'FAILED',first_difference=difference))
    failure=next((r for r in reports if not r['passed']),None)
    categories={name:sum(r['classification']==name for r in reports) for name in ('NORMAL_PARITY_PASSED','CONTRACT_CHECK_PASSED','FAILED')}
    return dict(passed=failure is None,classification='CONTRACT_CHECK_PASSED' if failure is None else 'FAILED',classification_counts=categories,
        first_difference=None if failure is None else failure,counts=dict(planned=len(common['cases']),executed=len(reports),compared=len(reports),passed=sum(r['passed'] for r in reports)),cases=reports)


def validate_reference(value):
    fields={'format','schema_version','reference_kind','score_encoding_version','rule_manifest','payload','provenance','coverage'}
    if type(value) is not dict or set(value)!=fields or value['format']!='fogsim.gp-reference' or type(value['schema_version']) is not int or value['schema_version']!=2:
        raise InputError('invalid fogsim.gp-reference v2')
    if value['reference_kind'] not in ('fixed','dynamic'):raise InputError('unknown GP reference kind')
    if value['score_encoding_version']!=SCORE_ENCODING_VERSION:raise InputError('unsupported GP reference score encoding')
    validate_rule_manifest(value['rule_manifest'])
    provenance=value['provenance']
    if type(provenance) is not dict or set(provenance)!={'language','numeric_semantics_version','java_runtime','java_vendor','source_fingerprint','build_manifest_sha256','implementation'}:
        raise InputError('invalid GP reference provenance fields')
    for key in ('source_fingerprint','build_manifest_sha256'):
        if type(provenance[key]) is not str or re.fullmatch('[0-9a-f]{64}',provenance[key]) is None:raise InputError('invalid GP reference provenance digest')
    if value['provenance'].get('language')!='Java' or value['provenance'].get('numeric_semantics_version')!=NUMERIC_SEMANTICS_VERSION:
        raise InputError('GP_RULE_IDENTITY_MISMATCH: independent target Java reference required')
    from .gp_normalize import java_fixed,java_dynamic
    validate_payload(value['reference_kind'], (java_fixed if value['reference_kind']=='fixed' else java_dynamic)(value),value['rule_manifest'])
    return value


def compare_reference(reference,actual_payload,active_manifest,*,binding=None,coverage=None):
    reference=validate_reference(reference);validate_rule_manifest(active_manifest)
    if reference['rule_manifest']['rule_pair_id']!=active_manifest['rule_pair_id']:raise InputError('GP_RULE_IDENTITY_MISMATCH: active/reference rule pairs differ')
    metric_paths=frozenset({('result','makespan'),('result','mean_flow_time')}) if reference['reference_kind']=='fixed' else frozenset({('native','makespan'),('native','mean_flow_time')})
    from .gp_normalize import java_fixed,java_dynamic
    expected_payload=(java_fixed if reference['reference_kind']=='fixed' else java_dynamic)(reference)
    validate_payload(reference['reference_kind'],actual_payload,active_manifest)
    difference=first_difference(expected_payload,actual_payload,metric_paths=metric_paths)
    normal=(expected_payload['result']['status']==actual_payload['result']['status']=='SUCCEEDED') if reference['reference_kind']=='fixed' else bool(expected_payload['native']['target_reached'] and actual_payload['native']['target_reached'])
    if binding and binding.get('passed') and (binding.get('source_fingerprint')!=reference['provenance']['source_fingerprint'] or binding.get('build_manifest_sha256')!=reference['provenance']['build_manifest_sha256']):
        raise InputError('reference provenance/build binding mismatch')
    declared=reference['coverage']
    if type(declared) is not dict or set(declared)!=({'events','decisions','completed','trace_enabled'} if reference['reference_kind']=='fixed' else {'events','decisions','attempts','capture_complete','target_reached'}):raise InputError('invalid reference coverage fields')
    counts=expected_payload['result'] if reference['reference_kind']=='fixed' else expected_payload
    if type(declared['events']) is not int or type(declared['decisions']) is not int or declared['events']!=len(counts['events']) or declared['decisions']!=len(counts['decisions']):raise InputError('reference coverage count mismatch')
    if reference['reference_kind']=='fixed':normal &= declared['completed'] is True and declared['trace_enabled'] is True
    else:normal &= declared['capture_complete'] is True and declared['target_reached'] is True
    if difference is not None:difference=annotate_difference(expected_payload,actual_payload,difference)
    satisfied=normal and bool(binding and binding.get('passed')) and bool(coverage and coverage.get('passed'))
    passed=difference is None and satisfied
    return dict(passed=passed,classification='NORMAL_PARITY_PASSED' if passed else 'FAILED' if not normal or difference is not None or coverage and not coverage.get('passed') else 'NOT_EXECUTED',
        first_difference=difference,binding=binding,coverage=coverage,recorded_rule_manifest=deepcopy(reference['rule_manifest']),active_rule_manifest=deepcopy(active_manifest),
        input_rule_reference_source=dict(active_rule_pair_id=active_manifest['rule_pair_id'],reference_rule_pair_id=reference['rule_manifest']['rule_pair_id'],source_fingerprint=reference['provenance']['source_fingerprint'],build_manifest_sha256=reference['provenance']['build_manifest_sha256'],bound_files=None if binding is None else binding.get('files')),
        numeric_policy=dict(scores='binary64 exact except NaN category',physical='binary64 exact',metric_paths=[list(p) for p in sorted(metric_paths)],abs_tol=1e-9,rel_tol=1e-12))


def bind_reference(manifest_path,input_path,reference_path,*,rule_pair_id,source_fingerprint):
    from fogsim.replay.loader import read_replay_json
    manifest_path,input_path,reference_path=map(Path,(manifest_path,input_path,reference_path));base=manifest_path.parent.resolve();m=read_replay_json(manifest_path)
    required={'format','schema_version','files','rule_pair_id','source_fingerprint','build_manifest_sha256'}
    if type(m) is not dict or set(m)!=required or m['format']!='fogsim.gp-reference-manifest' or type(m['schema_version']) is not int or m['schema_version']!=2:
        raise InputError('invalid GP reference binding manifest')
    if m['rule_pair_id']!=rule_pair_id or m['source_fingerprint']!=source_fingerprint:raise InputError('GP_RULE_IDENTITY_MISMATCH: reference binding differs')
    for key in ('source_fingerprint','build_manifest_sha256'):
        if type(m[key]) is not str or re.fullmatch('[0-9a-f]{64}',m[key]) is None:raise InputError('invalid GP binding digest')
    if input_path.resolve()==reference_path.resolve():raise InputError('input and reference must be separate files')
    if type(m['files']) is not dict or len(m['files'])!=2:raise InputError('binding must cover exactly separate input/reference')
    expected={}
    for p in (input_path,reference_path):
        p=p.resolve()
        if not p.is_relative_to(base):raise InputError('binding path escapes manifest directory')
        expected[p.relative_to(base).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    if expected!=m['files']:raise InputError('GP reference binding hash mismatch')
    return dict(passed=True,manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),files=expected,source_fingerprint=source_fingerprint,build_manifest_sha256=m['build_manifest_sha256'])


def validate_payload(kind,payload,manifest):
    """Explicit v2 priority sites and ordered frame coverage, independently of values."""
    from fogsim.instances.fixed import object_fields
    def number(v,path,nullable=False):
        if v is None and nullable:return
        if type(v) not in (int,float) or not math.isfinite(v):raise InputError(path+': finite physical number required')
    def finite_json(v,path='$'):
        if type(v) is float and not math.isfinite(v):raise InputError(path+': non-finite JSON number')
        if type(v) is dict:
            for k,x in v.items():finite_json(x,path+'.'+k)
        elif type(v) is list:
            for i,x in enumerate(v):finite_json(x,f'{path}[{i}]')
    finite_json(payload)
    def readings(rows):
        for row in rows:
            object_fields(row,('event_sequence','time','role','option','reads'),where='feature observation')
            number(row['time'],'feature observation.time')
            for leaf in row['reads']:
                object_fields(leaf,('node_index','kind','name','value'),where='leaf observation')
                decode_f64(leaf['value'],field_path='feature_observations.reads.value')
    bindings=manifest['bindings']
    if kind=='fixed':
        object_fields(payload,('loaded_model','result','final_state','feature_observations'),where='fixed GP payload')
        result=payload['result']
        object_fields(result,('status','reason','final_clock_time','completed_workflow_count','processed_event_count','makespan','workflow_records','task_records','events','decisions'),where='fixed GP result')
        def state(s):
            object_fields(s,('clock_time','pending_arrivals','active_workflows','completed_workflows','tasks','resources','executions','workflows'),where='fixed state')
            number(s['clock_time'],'state.clock_time')
            for t in s['tasks']:
                for o in t['options']:
                    object_fields(o,('resource_id','ready_time','priority'),where='state.option')
                    number(o['ready_time'],'state.ready_time');decode_f64(o['priority'],field_path='state.option.priority')
            for r in s['resources']:
                object_fields(r,('id','numeric_id','type','available_time','queued_processing_time','queued_total_time','waiting_queue','pending_start','completed_task_count'),where='state.resource')
                for key in ('available_time','queued_processing_time','queued_total_time'):number(r[key],'state.resource.'+key)
        def decision(d):
            object_fields(d,('event_sequence','decision_sequence','time','kind','round','candidates','selected','candidate_state','resource_state','rule_id'),where='fixed decision')
            role={'ROUTING':'routing','SEQUENCING':'sequencing'}.get(d['kind'])
            if role is None or d['rule_id']!=bindings[role]['rule_id']:raise InputError('GP_RULE_IDENTITY_MISMATCH: decision rule binding')
            for score in d['candidates']:
                object_fields(score,('option','priority'),where='decision score');decode_f64(score['priority'],field_path='decision.priority')
            number(d['time'],'decision.time')
        state(payload['final_state'])
        for d in result['decisions']:decision(d)
        for event in result['events']:
            object_fields(event,('type','time','owner','workflow_id','task_id','resource_id','sequence','staging_device','before','after','emitted','actions','error'),where='fixed event')
            state(event['before']);state(event['after']);number(event['time'],'event.time')
            for a in event['actions']:
                if a['kind']=='DECISION':decision(a['decision'])
                elif a['kind']!='EMIT':raise InputError('unknown fixed action')
        if [e['sequence'] for e in result['events']]!=list(range(1,len(result['events'])+1)):raise InputError('fixed event sequence coverage')
        number(result['makespan'],'result.makespan',True);number(result['final_clock_time'],'final_clock_time')
    else:
        object_fields(payload,('events','decisions','actions','post_trigger_states','pre_trigger_states','event_errors','native','final_state','feature_observations'),where='dynamic GP payload')
        def option(o):
            object_fields(o,('workflow_id','task_java_index','resource_id','ready_time','priority'),where='dynamic option')
            number(o['ready_time'],'option.ready_time');decode_f64(o['priority'],field_path='dynamic.option.priority')
        def decision(d):
            object_fields(d,('event_sequence','clock_time','kind','options','selected','round','rule_id'),where='dynamic decision')
            if d['kind'] not in bindings or d['rule_id']!=bindings[d['kind']]['rule_id']:raise InputError('GP_RULE_IDENTITY_MISMATCH: dynamic decision binding')
            for o in d['options']:option(o)
            option(d['selected']);number(d['clock_time'],'decision.clock_time')
        def state(s):
            object_fields(s,('clock_time','G','B','statistical_workflow_ids','active_workflow_ids','resources','workflows'),where='dynamic state')
            for key in ('clock_time','B'):number(s[key],'state.'+key)
            for r in s['resources']:
                for key in ('available_time','total_processing','total_occupancy'):number(r[key],'resource.'+key)
                for o in r['queue']:option(o)
            for w in s['workflows']:
                number(w['completion_time'],'completion_time',True)
                for t in w['tasks']:
                    for o in t['options']:option(o)
        for d in payload['decisions']:decision(d)
        for a in payload['actions']:
            if a['kind']=='DECISION':decision(a['decision'])
            elif a['kind']!='EMIT':raise InputError('unknown dynamic action')
        for key in ('pre_trigger_states','post_trigger_states'):
            if len(payload[key])!=len(payload['events']) or [x['event_sequence'] for x in payload[key]]!=list(range(1,len(payload['events'])+1)):raise InputError('dynamic boundary coverage')
            for row in payload[key]:state(row['state'])
        if [x['event_sequence'] for x in payload['events']]!=list(range(1,len(payload['events'])+1)):raise InputError('dynamic event coverage')
        state(payload['final_state'])
        for key in ('clock_time','B','makespan','mean_flow_time'):number(payload['native'][key],'native.'+key)
    readings(payload['feature_observations'])


def compare_replay_reference(engine,result,reference,*,manifest_path,input_path,reference_path):
    """Post-run dynamic API. Neither source nor GP observers have a reference handle."""
    reference=validate_reference(reference)
    if reference['reference_kind']!='dynamic':raise InputError('dynamic replay needs dynamic GP reference')
    source=engine.admission.source
    base=dict(passed=False,classification='FAILED',first_difference=None)
    if source.purpose!='verify_reference':return base|dict(classification='NOT_COMPARED')
    if result.reason_code=='REPLAY_INPUT_EXHAUSTED':return base|dict(classification='INPUT_COVERAGE_INSUFFICIENT')
    if result.reason_code=='REPLAY_INPUT_DIVERGENCE':return base|dict(reason=result.reason)
    if not engine.config.trace_enabled or not hasattr(engine,'gp_observations'):return base|dict(classification='NOT_EXECUTED',reason='full observed trace required')
    from dataclasses import asdict
    from .gp_normalize import python_dynamic,MAPPINGS
    archive=engine.replay_input.archive
    diff=first_difference(asdict(archive),asdict(engine.admission.archive))
    coverage=dict(passed=engine.replay_input.capture.is_complete and source.position==len(archive.generation_attempts) and diff is None,
        consumed=source.position,available=len(archive.generation_attempts),input_first_difference=diff)
    if None in (manifest_path,input_path,reference_path):return base|dict(classification='NOT_EXECUTED',reason='bound input/reference manifest required')
    from fogsim.replay.loader import load_replay_input,read_replay_json
    if first_difference(load_replay_input(input_path).to_dict(),engine.replay_input.to_dict()) is not None or read_replay_json(reference_path)!=reference:
        raise InputError('executed input/reference differs from bound files')
    binding=bind_reference(manifest_path,input_path,reference_path,rule_pair_id=engine.prepared_rules.rule_pair_id,source_fingerprint=reference['provenance']['source_fingerprint'])
    report=compare_reference(reference,python_dynamic(engine,result),engine.prepared_rules.rule_manifest,binding=binding,coverage=coverage)
    if reference['coverage']['attempts']!=len(archive.generation_attempts):raise InputError('reference attempt coverage count mismatch')
    report['representation_mappings']=list(MAPPINGS);return report


def annotate_difference(expected,actual,difference):
    """Attach the nearest ordered frame/decision context without repairing values."""
    d=dict(difference);path=d['field_path'];parts=re.findall(r'\.([A-Za-z_][A-Za-z_0-9]*)|\[(\d+)\]',path);node=expected;ancestors=[]
    for key,index in parts:
        ancestors.append(node)
        try:node=node[int(index) if index else key]
        except (KeyError,IndexError,TypeError):break
    ancestors.append(node)
    for a in ancestors:
        if type(a) is not dict:continue
        for key,target in [('event_sequence','event_sequence'),('sequence','event_sequence'),('type','event_kind'),('time','event_time'),('clock_time','event_time'),('role','role'),('round','round')]:
            if key in a and type(a[key]) in (str,int,float):d[target]=a[key]
        if type(a.get('kind')) is str and a['kind'].endswith('Event'):d['event_kind']=a['kind']
        if a.get('kind') in ('routing','sequencing','ROUTING','SEQUENCING'):d['role']=a['kind'].lower()
        if 'option' in a:d['candidate_key']=a['option']
    match=re.search(r'(?:candidates|options)\[(\d+)\]',path)
    if match:d['candidate_index']=int(match[1])
    return d
