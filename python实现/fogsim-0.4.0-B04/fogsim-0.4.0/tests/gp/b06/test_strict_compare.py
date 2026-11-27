"""Comparator attacks and observer isolation, separate from actual Java acceptance."""
from copy import deepcopy
import json,math,struct
from pathlib import Path
import pytest
from fogsim.errors import InputError
from fogsim.serialization.f64 import encode_f64
from fogsim.validation.gp_compare import first_difference,validate_reference,validate_payload,compare_reference,bind_reference
from fogsim.validation.gp_normalize import java_fixed
HERE=Path(__file__).parent/'fixtures'
def read(name):return json.loads((HERE/name).read_text())
def bits(b):return dict(kind='f64',bits=b)

@pytest.mark.parametrize('path',[('time',),('clock_time',),('ready_time',),('available_time',),('processing_time',),('queued_processing_time',),('plan','finish_time'),('unknown_metric',)])
def test_no_ulp_tolerance_for_physical_or_unknown_fields(path):
    def nest(value):
        for k in reversed(path):value={k:value}
        return value
    d=first_difference(nest(1.),nest(math.nextafter(1.,2.)))
    assert d and d['expected_bits']=='3ff0000000000000' and d['actual_bits']=='3ff0000000000001'

@pytest.mark.parametrize('path',[('result','makespan'),('result','mean_flow_time'),('native','mean_flow_time')])
def test_only_explicit_schema_metric_path_tolerates(path):
    def nest(value):
        for k in reversed(path):value={k:value}
        return value
    assert first_difference(nest(1.),nest(math.nextafter(1.,2.)),metric_paths=frozenset({path})) is None
    assert first_difference(nest(0.),nest(-0.),metric_paths=frozenset({path})) is not None

@pytest.mark.parametrize('value',[None,False,0.,{'kind':'f64','bits':'A'*16},{'kind':'f64','bits':'0'*15},{'kind':'f64','bits':'0'*16,'x':0},{'kind':'f32','bits':'0'*16}])
def test_invalid_tag_never_compares_as_number(value):
    with pytest.raises(InputError,match='GP_F64_ENCODING_INVALID'):first_difference(bits('0000000000000000'),value)

@pytest.mark.parametrize('a,b',[('0000000000000000','8000000000000000'),('7ff0000000000000','fff0000000000000'),('3ff0000000000000','3ff0000000000001')])
def test_score_bit_difference(a,b):
    assert first_difference(bits(a),bits(b))['reason']=='binary64 score differs'

def test_nan_category_but_raw_constants_exact():
    a,b=bits('7ff8000000000011'),bits('7ff8000000000022')
    assert first_difference(a,b) is None
    assert first_difference(a,b,raw_f64=True)
    assert first_difference({'kind':'constant','value':a},{'kind':'constant','value':b})
    assert first_difference({'kind':'constant','bits':a['bits']},{'kind':'constant','bits':b['bits']})

@pytest.mark.parametrize('a,b',[(1,1.),(True,1),([1,2],[2,1]),([1],[1,2]),({'x':1},{'x':1,'y':2})])
def test_types_counts_order_members_exact(a,b):assert first_difference(a,b)

@pytest.mark.parametrize('value',[math.nan,math.inf,-math.inf])
def test_nonfinite_physical_forbidden(value):
    with pytest.raises(InputError,match='non-finite'):first_difference(value,value)

@pytest.mark.parametrize('key,value',[('schema_version',1),('schema_version',True),('reference_kind','other'),('score_encoding_version','unknown')])
def test_reference_versions_strict(key,value):
    r=read('fixed-reference.json');r[key]=value
    with pytest.raises(InputError):validate_reference(r)

@pytest.mark.parametrize('key',['source_fingerprint','build_manifest_sha256'])
def test_reference_provenance_strict(key):
    r=read('fixed-reference.json');r['provenance'][key]='unbound'
    with pytest.raises(InputError,match='digest'):validate_reference(r)

def test_original_semantics_never_normal_reference():
    r=read('fixed-reference.json');r['provenance']['numeric_semantics_version']='java-original-positive-zero-v1'
    with pytest.raises(InputError,match='GP_RULE_IDENTITY_MISMATCH'):validate_reference(r)

@pytest.mark.parametrize('mutate',['unknown_expression','pair','source','binding','ast'])
def test_identity_tamper(mutate):
    r=read('fixed-reference.json');m=r['rule_manifest']
    if mutate=='pair':m['rule_pair_id']='sha256:'+'0'*64
    if mutate=='unknown_expression':m['bindings']['routing']['expression_id']='sha256:'+'0'*64
    if mutate=='source':m['bindings']['routing']['source']['expression']='PT'
    if mutate=='binding':m['bindings']['sequencing']['rule_id']=m['bindings']['routing']['rule_id']
    if mutate=='ast':m['expressions'][0]['ast']['nodes'][0]['op']='*'
    with pytest.raises(InputError,match='GP_RULE_IDENTITY_MISMATCH'):validate_reference(r)

def tags(v,path=()):
    if type(v) is dict:
        if set(v)=={'kind','bits'} and v['kind']=='f64':yield path
        else:
            for k,x in v.items():yield from tags(x,path+(k,))
    elif type(v) is list:
        for i,x in enumerate(v):yield from tags(x,path+(i,))
TAG_PATHS=list(tags(java_fixed(read('fixed-reference.json'))))
@pytest.mark.parametrize('path',TAG_PATHS)
def test_every_declared_fixed_score_site_is_tagged(path):
    ref=read('fixed-reference.json');p=java_fixed(ref);node=p
    for k in path[:-1]:node=node[k]
    node[path[-1]]=0.
    with pytest.raises(InputError,match='GP_F64_ENCODING_INVALID'):validate_payload('fixed',p,ref['rule_manifest'])

@pytest.mark.parametrize('coverage',[None,{'passed':False}])
def test_no_normal_pass_without_coverage_or_binding(coverage):
    ref=read('fixed-reference.json');p=java_fixed(ref)
    r=compare_reference(ref,p,ref['rule_manifest'],coverage=coverage)
    assert not r['passed'] and r['classification']!='NORMAL_PARITY_PASSED'

def test_missing_or_reordered_event_cannot_be_repaired():
    ref=read('fixed-reference.json');p=java_fixed(ref);p['result']['events'].reverse()
    with pytest.raises(InputError,match='sequence coverage'):validate_payload('fixed',p,ref['rule_manifest'])

@pytest.mark.parametrize('field',['input.json','reference.json'])
def test_binding_file_hash_attack(tmp_path,field):
    import shutil
    for p in (HERE/'dynamic').iterdir():shutil.copyfile(p,tmp_path/p.name)
    (tmp_path/field).write_text('{}')
    r=json.loads((tmp_path/'reference.json').read_text()) if field!='reference.json' else read('dynamic/reference.json')
    with pytest.raises(InputError,match='hash mismatch'):bind_reference(tmp_path/'manifest.json',tmp_path/'input.json',tmp_path/'reference.json',rule_pair_id=r['rule_manifest']['rule_pair_id'],source_fingerprint=r['provenance']['source_fingerprint'])


from fogsim.validation.gp_normalize import java_dynamic
DYNAMIC_TAG_PATHS=list(tags(java_dynamic(read('dynamic/reference.json'))))
@pytest.mark.parametrize('path',DYNAMIC_TAG_PATHS)
def test_every_declared_dynamic_score_site_is_tagged(path):
    ref=read('dynamic/reference.json');p=java_dynamic(ref);node=p
    for k in path[:-1]:node=node[k]
    node[path[-1]]=0.
    with pytest.raises(InputError,match='GP_F64_ENCODING_INVALID'):validate_payload('dynamic',p,ref['rule_manifest'])

@pytest.mark.parametrize('key',['pre_trigger_states','post_trigger_states'])
def test_dynamic_missing_boundaries_are_coverage_failure(key):
    ref=read('dynamic/reference.json');p=java_dynamic(ref);p[key].pop()
    with pytest.raises(InputError,match='boundary coverage'):validate_payload('dynamic',p,ref['rule_manifest'])

def test_no_normal_pass_for_build_binding_mismatch():
    ref=read('fixed-reference.json');p=java_fixed(ref)
    with pytest.raises(InputError,match='build binding mismatch'):
        compare_reference(ref,p,ref['rule_manifest'],binding=dict(passed=True,source_fingerprint=ref['provenance']['source_fingerprint'],build_manifest_sha256='0'*64),coverage=dict(passed=True))

def test_first_difference_includes_actual_event_role_candidate_and_bits():
    ref=read('fixed-reference.json');p=java_fixed(ref);p['result']['events'][0]['actions'][0]['decision']['candidates'][0]['priority']=encode_f64(123.)
    report=compare_reference(ref,p,ref['rule_manifest']);d=report['first_difference']
    assert d['event_kind']=='JobArrivalEvent'
    assert d['event_sequence']==1 and d['role']=='routing' and d['candidate_index']==0 and d['candidate_key']==[0,'A','M0']
    assert d['expected_bits']!=d['actual_bits']
