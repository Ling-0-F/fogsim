import json,math,os
from copy import deepcopy
from pathlib import Path
import pytest
from fogsim.errors import InputError
from fogsim.serialization.result import decode_result,_score_fields
from fogsim.serialization.f64 import encode_f64
from fogsim.validation.gp_compare import compare_reference,first_difference,bind_reference
from fogsim.replay.native import compare_native_results,NATIVE_EXCLUSIONS

ROOT=Path(__file__).resolve().parents[3]
FIXED=Path(os.environ.get('FOGSIM_B07_FIXED_RESULTS',str(ROOT/'development/b07/evidence/fixed-final')))
NATIVE=Path(os.environ.get('FOGSIM_B07_NATIVE_RESULTS',str(ROOT/'development/b07/evidence/native-final')))
def read(path):return json.loads(path.read_text())

@pytest.mark.parametrize('kind',['NAN','POSITIVE_INFINITY','NEGATIVE_INFINITY','POSITIVE_ZERO','NEGATIVE_ZERO'])
def test_actual_F06_formal_write_read_and_all_score_bits_roundtrip(kind,record):
    folder=FIXED/('F06-'+kind)
    wire=read(folder/'python-result.json');decoded=decode_result(wire)
    _score_fields(decoded,encode_f64)
    assert first_difference(wire,decoded,raw_f64=True) is None
    assert math.isfinite(wire['final_clock_time'])
    scores=[c['priority'] for d in wire['decisions'] for c in d['candidates']]
    assert scores and all(type(v) is dict and set(v)=={'kind','bits'} for v in scores)
    record(dict(score_class=kind,bits=[v['bits'] for v in scores],physical_clock=wire['final_clock_time']))

@pytest.mark.parametrize('field',['final_clock_time','makespan'])
@pytest.mark.parametrize('value',[math.inf,-math.inf,math.nan])
def test_special_GP_scores_never_relax_physical_finite_contract(field,value,record):
    p=FIXED/'F06-NAN/python-result.json';wire=read(p);wire[field]=value
    with pytest.raises(InputError):decode_result(wire)
    record(dict(field=field,invalid_class='NAN' if math.isnan(value) else 'POSITIVE_INFINITY' if value>0 else 'NEGATIVE_INFINITY',rejected=True))

@pytest.mark.parametrize('site',['event-time','state-cache','state-ready','event-order','metric','signed-zero'])
def test_full_dynamic_schema_uses_exact_physical_and_named_metric_policy(dynamic_data,record,site):
    _,p,_,folder=dynamic_data();reference=read(folder/'reference.json')
    b=bind_reference(folder/'manifest.json',folder/'input.json',folder/'reference.json',
        rule_pair_id=reference['rule_manifest']['rule_pair_id'],source_fingerprint=reference['provenance']['source_fingerprint'])
    if site=='event-time':p['events'][0]['time']=math.nextafter(p['events'][0]['time'],math.inf)
    elif site=='state-cache':p['post_trigger_states'][0]['state']['resources'][0]['total_processing']=math.nextafter(p['post_trigger_states'][0]['state']['resources'][0]['total_processing'],math.inf)
    elif site=='state-ready':p['final_state']['workflows'][0]['tasks'][0]['options'][0]['ready_time']=math.nextafter(p['final_state']['workflows'][0]['tasks'][0]['options'][0]['ready_time'],math.inf)
    elif site=='event-order':p['events'].reverse()
    elif site=='metric':p['native']['mean_flow_time']=math.nextafter(p['native']['mean_flow_time'],math.inf)
    else:
        p['post_trigger_states'][0]['state']['resources'][0]['total_processing']=-0.
    if site=='event-order':
        with pytest.raises(InputError,match='event coverage'):compare_reference(reference,p,reference['rule_manifest'],binding=b,coverage=dict(passed=True))
        record(dict(site=site,rejected=True));return
    report=compare_reference(reference,p,reference['rule_manifest'],binding=b,coverage=dict(passed=True))
    assert report['passed']==(site=='metric')
    if site!='metric':assert report['first_difference'] and report['first_difference']['expected_bits']!=report['first_difference']['actual_bits']
    record(dict(site=site,report=report))

@pytest.mark.parametrize('scene',['chain','shared-fork-join','no-local'])
def test_fresh_native_loop_compares_full_result_and_explicit_whitelist(scene,record):
    folder=NATIVE/('D09B-'+scene)
    native,replay=read(folder/'native-result.json'),read(folder/'replay-result.json')
    report=compare_native_results(native,replay);assert report['passed']
    assert all(p not in (('diagnostics',),('final_state',),('events',)) for p in NATIVE_EXCLUSIONS)
    record(report)

@pytest.mark.parametrize('attack',['guard-diagnostics','unknown-diagnostics','final-cache','event-time'])
def test_native_loop_never_blanket_ignores_diagnostics_or_state(record,attack):
    folder=NATIVE/'D09B-shared-fork-join'
    native,replay=read(folder/'native-result.json'),read(folder/'replay-result.json')
    assert compare_native_results(native,replay)['passed']
    if attack=='guard-diagnostics':replay['diagnostics']['guard_hits']=[{'injected':'guard'}]
    elif attack=='unknown-diagnostics':replay['diagnostics']['b07_unexcluded_diagnostic']='changed'
    elif attack=='final-cache':replay['final_state']['resources'][0]['queued_processing_time']=math.nextafter(replay['final_state']['resources'][0]['queued_processing_time'],math.inf)
    else:replay['events'][0]['time']=math.nextafter(replay['events'][0]['time'],math.inf)
    report=compare_native_results(native,replay);assert not report['passed'] and report['first_difference']
    record(dict(attack=attack,report=report))
