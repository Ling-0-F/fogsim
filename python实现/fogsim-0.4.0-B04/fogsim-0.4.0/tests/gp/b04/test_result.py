from copy import deepcopy
from dataclasses import replace
import json
import struct
import pytest
from fogsim import create_engine, load_fixed_instance, RunConfig, create_dynamic_context
from fogsim.gp import evaluator
from fogsim.errors import InputError, StateError
from fogsim.serialization.f64 import encode_f64, decode_f64
from fogsim.serialization.result import decode_result, read_result
from fogsim.simulation.metrics import collect_result
from ..b03.helpers import gp_dynamic, dynamic_config
from ..b03.test_runtime import shared_spec
from conftest import ROOT

BITS=['0000000000000000','8000000000000000','3ff0000000000000','bff0000000000000',
      '0000000000000001','8000000000000001','0010000000000000','8010000000000000',
      '7fefffffffffffff','ffefffffffffffff','7ff0000000000000','fff0000000000000',
      '7ff8000000000001','7ff8000000000002','fff8000000001234','7ff0000000000001']
INVALID=[0,1.0,None,True,{},dict(kind='f64'),dict(bits='0'*16),dict(kind='float',bits='0'*16),
    dict(kind='f64',bits='F'*16),dict(kind='f64',bits='0'*15),dict(kind='f64',bits='g'*16),
    dict(kind='f64',bits='0'*17),dict(kind='f64',bits='0'*16,value=0),dict(kind='f64',bits=0)]

@pytest.mark.parametrize('bits',BITS)
def test_all_binary64_tags_raw(bits,evidence_b04):
    value=struct.unpack('>d',bytes.fromhex(bits))[0]
    tag=dict(kind='f64',bits=bits)
    assert encode_f64(value)==tag
    assert struct.pack('>d',decode_f64(json.loads(json.dumps(tag)))).hex()==bits
    evidence_b04('f64',dict(input_bits=bits,tag=tag))

@pytest.mark.parametrize('tag',INVALID)
def test_strict_tag(tag):
    with pytest.raises(InputError,match='GP_F64_ENCODING_INVALID'):decode_f64(tag)

EXPRESSIONS=['(* 1e309 0)','1e309','-1e309','-0.0','0.0','1e-320']
@pytest.mark.parametrize('expression',EXPRESSIONS)
@pytest.mark.parametrize('trace',[True,False])
@pytest.mark.parametrize('slot',['routing','sequencing','both'])
def test_real_result_all_score_sites_and_unchanged_physical(expression,trace,slot,tmp_path,evidence_b04):
    cfg=RunConfig(routing_kind='gp' if slot!='sequencing' else 'fixed_resource',
        fixed_resource_id='E0' if slot=='sequencing' else None,
        sequencing_kind='gp' if slot!='routing' else 'fcfs',trace_enabled=trace,
        routing_expression=expression if slot!='sequencing' else None,
        sequencing_expression=expression if slot!='routing' else None)
    engine=create_engine(shared_spec(),cfg);result=engine.run()
    assert result.status=='SUCCEEDED'
    output=result.to_dict();decoded=decode_result(json.loads(json.dumps(output,allow_nan=False)))
    assert output['format']=='fogsim.fixed-result'
    assert output['rule_manifest']==engine.prepared_rules.rule_manifest
    assert not trace or all('rule_id' in d for d in output['decisions'])
    for raw,restored in zip(result.decisions,decoded['decisions']):
        for a,b in zip(raw['candidates'],restored['candidates']):
            assert struct.pack('>d',a['priority'])==struct.pack('>d',b['priority'])
    for task in decoded['final_state']['tasks']:
        for option in task['options']:
            actual=engine.state.tasks_by_key[tuple(task['key'])].options
            original=next(o for o in actual if o.resource.id==option['resource_id'])
            assert struct.pack('>d',original.priority)==struct.pack('>d',option['priority'])
    # A full JSON round trip covers independent actions/before/after copies too.
    assert decoded['makespan']==result.makespan
    assert type(output['final_clock_time']) is float
    if not trace: assert not output['events'] and not output['decisions']
    path=tmp_path/'result.json';path.write_text(json.dumps(output,allow_nan=False))
    assert read_result(path)['status']=='SUCCEEDED'
    evidence_b04('real-results',dict(expression=expression,slot=slot,trace=trace,output=output))


def score_sites(output):
    # Test traversal is independent of the encoder, including the first event
    # both state copies, successful decision/actions, and final-state score.
    event=output['events'][0]
    return [output['decisions'][0]['candidates'][0],
        event['before']['tasks'][0]['options'][0],event['after']['tasks'][0]['options'][0],
        next(a['decision'] for a in event['actions'] if a['kind']=='DECISION')['candidates'][0],
        output['final_state']['tasks'][0]['options'][0]]

@pytest.mark.parametrize('site',range(5))
@pytest.mark.parametrize('tag',INVALID)
def test_invalid_score_at_each_site_is_rejected(site,tag):
    out=create_engine(load_fixed_instance(ROOT/'data/cases/chain_remote.json'),
        RunConfig('gp',routing_expression='PT')).run().to_dict()
    score_sites(out)[site]['priority']=tag
    with pytest.raises(InputError,match='GP_F64_ENCODING_INVALID'):decode_result(out)


@pytest.mark.parametrize('trace',[True,False])
@pytest.mark.parametrize('domain',[True,False])
@pytest.mark.parametrize('bits',['8000000000000000','7ff0000000000000','7ff8000000000002'])
def test_partial_failure_records_prefix_and_snapshot_without_reevaluation(trace,domain,bits,monkeypatch,evidence_b04):
    engine=create_engine(load_fixed_instance(ROOT/'data/cases/chain_remote.json'),
        RunConfig('gp',trace_enabled=trace,routing_expression='PT'))
    options=engine.state.workflows_by_id[0].tasks[0].options
    calls=[];failure=StateError('domain failure') if domain else TypeError('program failure')
    def fail(feature,option,ctx):
        calls.append(option)
        if option is options[1]:
            option.priority=-float('inf')  # observable failing-candidate write must be retained
            raise failure
        return struct.unpack('>d',bytes.fromhex(bits))[0]
    monkeypatch.setattr(evaluator,'read_feature',fail)
    if domain: result=engine.run()
    else:
        with pytest.raises(TypeError) as caught:engine.run()
        assert caught.value is failure
        result=collect_result(engine)
    assert engine.run_status=='FAILED' and calls==options[:2]
    assert not options[0].task.dispatched and not result.decisions
    output=result.to_dict();restored=decode_result(output)
    error=output['diagnostics']['decision_errors'][0]
    assert error['failed_candidate_index']==1 and error['failed_candidate_key']==list(options[1].key)
    assert error['scored_prefix']==[dict(option=list(options[0].key),priority=dict(kind='f64',bits=bits))]
    assert 'selected' not in error
    assert error['error']['code']==('STATE_INVARIANT_VIOLATION' if domain else 'UNEXPECTED_PROGRAMMING_EXCEPTION')
    assert output['final_state']['tasks'][0]['options'][1]['priority']['bits']=='fff0000000000000'
    if trace:
        event=output['events'][-1]
        assert event['error'] and event['before'] and event['after']
        assert [a['kind'] for a in event['actions']]==['DECISION_ERROR']
        assert event['actions'][0]['decision_error']==error
    else:assert output['events']==[]
    assert calls==options[:2]  # serializing/decoding never reruns any feature
    evidence_b04('partial-errors',dict(trace=trace,domain=domain,output=output))


@pytest.mark.parametrize('trace',[True,False])
@pytest.mark.parametrize('gp',[True,False])
def test_dynamic_v2_and_explicit_baselines(tmp_path,trace,gp):
    cfg=gp_dynamic(tmp_path) if gp else replace(dynamic_config(tmp_path),schema_version=2)
    cfg=replace(cfg,run=replace(cfg.run,trace_enabled=trace))
    result=create_dynamic_context(cfg).run();output=result.to_dict()
    assert output['format']=='fogsim.dynamic-result'
    assert decode_result(output)['status']=='SUCCEEDED'
    assert 'source_summary' in output and 'decision_errors' in output['diagnostics']

@pytest.mark.parametrize('trace',[True,False])
def test_v1_output_byte_shape_matches_b03(trace):
    result=create_engine(load_fixed_instance(ROOT/'data/cases/chain_remote.json'),RunConfig(trace_enabled=trace)).run()
    output=result.to_dict()
    assert set(output)=={'status','reason','final_clock_time','completed_workflow_count','processed_event_count',
        'makespan','workflow_records','task_records','events','decisions'}
    assert all('rule_id' not in d for d in output['decisions'])
    assert all(type(c['priority']) is float for d in output['decisions'] for c in d['candidates'])

@pytest.mark.parametrize('change',[lambda o:o.update(schema_version=True),lambda o:o.update(schema_version=3),
    lambda o:o.update(format='unknown'),lambda o:o.update(score_encoding_version='unknown'),
    lambda o:o.update(extra=0),lambda o:o.update(final_clock_time=float('inf')),
    lambda o:o['decisions'][0].update(rule_id='bad')])
def test_result_metadata_rejected(change):
    out=create_engine(load_fixed_instance(ROOT/'data/cases/chain_remote.json'),RunConfig('gp',routing_expression='PT')).run().to_dict()
    change(out)
    with pytest.raises(InputError):decode_result(out)

@pytest.mark.parametrize('site',['clock','metric','state-ready','state-cache','event-time','candidate-time'])
@pytest.mark.parametrize('value',[dict(kind='f64',bits='7ff0000000000000'),True,'1',float('nan'),float('inf')])
def test_physical_fields_reject_tags_bool_and_nonfinite(site,value):
    out=create_engine(load_fixed_instance(ROOT/'data/cases/chain_remote.json'),RunConfig('gp',routing_expression='PT')).run().to_dict()
    if site=='clock':out['final_clock_time']=value
    elif site=='metric':out['makespan']=value
    elif site=='state-ready':out['final_state']['tasks'][0]['options'][0]['ready_time']=value
    elif site=='state-cache':out['final_state']['resources'][0]['queued_total_time']=value
    elif site=='event-time':out['events'][0]['time']=value
    else:out['decisions'][0]['candidate_state'][0]['ready_time']=value
    with pytest.raises(InputError):decode_result(out)
