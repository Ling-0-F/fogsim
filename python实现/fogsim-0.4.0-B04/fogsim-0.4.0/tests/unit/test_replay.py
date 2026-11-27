"""Production replay contracts. Historical V16/step5 expected files stay unchanged."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, asdict, replace
from pathlib import Path
import json
import random
import pytest
from conftest import ROOT
from fogsim import (load_replay_input, parse_replay_input, create_replay_engine, simulate_replay,
    export_fixed_instance, fixed_projection_metadata, audit_formulas, create_engine, simulate, parse_instance)
from fogsim.errors import InputError, SimulationFailure, PreparationError
from fogsim.experiment_config import ReplayRunOptions, RuleConfig
from fogsim.instances.generated import GenerationCause
from fogsim.replay.source import ReplayWorkflowSource
from fogsim.replay.loader import read_replay_json
from fogsim.validation.dynamic_compare import compare_dynamic_reference, normalize_python, first_difference

CASES=ROOT/'outputs/step4/cases'

@pytest.fixture
def data(): return read_replay_json(ROOT/'tests/fixtures/dynamic_v1/input.json')


def test_input_alone_runs_without_xml_java_reference_or_rng(data,tmp_path,monkeypatch):
    p=tmp_path/'input.json';p.write_text(json.dumps(data))
    def forbidden(*a,**kw): raise AssertionError('replay must not sample or construct RNG')
    monkeypatch.setattr(random,'Random',forbidden)
    import fogsim.randomness.samplers as s
    for cls in (s.UniformRealSampler,s.UniformIntegerSampler,s.ExponentialSampler) if hasattr(s,'UniformRealSampler') else ():
        monkeypatch.setattr(cls,'sample',forbidden)
    rng_before=random.getstate()
    inp=load_replay_input(p);engine=create_replay_engine(inp);result=engine.run()
    assert random.getstate()==rng_before
    assert result.status=='SUCCEEDED' and result.processed_event_count==7
    assert result.diagnostics['comparison_status']=='NOT_COMPARED'
    assert result.source_summary['rng_used'] is False
    assert result.diagnostics['rng_final_fingerprint'] is None
    assert list(tmp_path.iterdir())==[p]


def test_immutable_document_and_run_graph_isolation(data):
    inp=parse_replay_input(data)
    with pytest.raises(FrozenInstanceError): inp.capture.complete=False
    data['initial_state']['B']=10000
    detached=inp.to_dict();detached['candidates'].clear()
    assert inp.initial_state.B==0 and len(inp.archive.candidates)==2
    a=create_replay_engine(inp);b=create_replay_engine(inp)
    ta=next(iter(a.state.tasks_by_key.values()));tb=next(iter(b.state.tasks_by_key.values()))
    assert ta is not tb and ta.workflow is not tb.workflow
    assert all(o.task is ta and o.resource is a.state.resources_by_id[o.resource.id] for o in ta.options)
    assert a.run().to_dict()==b.run().to_dict()


@pytest.mark.parametrize('version',[True,0,2,'1',None])
def test_version(data,version):
    data['schema_version']=version
    with pytest.raises(InputError): parse_replay_input(data)

@pytest.mark.parametrize('location',['root','origin','rules','units','config','guards','samplers','interval','capture','environment',
    'device','template','template_task','candidate','workflow','template_ref','task','option','edge','attempt','initial_state'])
def test_unknown_fields(data,location):
    w=data['candidates'][0]['workflow_input']
    targets={'root':data,'origin':data['origin'],'rules':data['origin']['rules'],'units':data['units'],
        'config':data['effective_config'],'guards':data['effective_config']['guards'],'samplers':data['effective_config']['samplers'],
        'interval':data['effective_config']['samplers']['inter_release_time'],'capture':data['capture'],
        'environment':data['environment'],'device':data['environment']['devices'][0], 'template':data['templates'][0],
        'template_task':data['templates'][0]['tasks'][0],'candidate':data['candidates'][0], 'workflow':w,
        'template_ref':w['template_ref'],'task':w['tasks'][0],'option':w['tasks'][0]['options'][0],
        'edge':w['edges'][0],'attempt':data['generation_attempts'][0],'initial_state':data['initial_state']}
    targets[location]['unknown']=1
    with pytest.raises(InputError): parse_replay_input(data)

@pytest.mark.parametrize('path',[
    ('templates',),('candidates',),('generation_attempts',),('environment','devices'),('environment','servers'),
    ('templates',0,'dependencies'),('templates',0,'diagnostics'),('templates',0,'tasks'),
    ('candidates',0,'workflow_input','tasks'),('candidates',0,'workflow_input','edges'),
    ('candidates',0,'workflow_input','tasks',0,'options')])
@pytest.mark.parametrize('invalid',[None,{},'bad',7])
def test_structure_errors_are_input_errors(data,path,invalid):
    target=data
    for key in path[:-1]:target=target[key]
    target[path[-1]]=invalid
    with pytest.raises(InputError):parse_replay_input(data)

@pytest.mark.parametrize('seed',[-(1<<63),(1<<63)-1,-1,0])
def test_exact_seed(data,seed,tmp_path):
    data['initial_state']['public_seed']=seed;p=tmp_path/'input.json';p.write_text(json.dumps(data))
    assert load_replay_input(p).initial_state.public_seed==seed

@pytest.mark.parametrize('seed',[True,1.0,1<<63,-(1<<63)-1])
def test_invalid_seed(data,seed):
    data['initial_state']['public_seed']=seed
    with pytest.raises(InputError):parse_replay_input(data)

@pytest.mark.parametrize('raw',['{"a":1,"a":2}','{"a":NaN}','{"a":Infinity}','{"a":1e999}'])
def test_strict_json(tmp_path,raw):
    p=tmp_path/'bad.json';p.write_text(raw)
    with pytest.raises(InputError):load_replay_input(p)

@pytest.mark.parametrize('mutation',['task','edge','option','candidate','attempt','order','acceptance','id','clock',
    'owner','fingerprint','count','numeric_bool','numeric_inf','numeric_int','init_missing'])
def test_invalid_contracts(data,mutation):
    w=data['candidates'][0]['workflow_input']
    if mutation=='task':w['tasks'].pop()
    elif mutation=='edge':w['edges'].pop()
    elif mutation=='option':w['tasks'][0]['options'].pop()
    elif mutation=='candidate':data['candidates'].pop()
    elif mutation=='attempt':data['generation_attempts'].pop()
    elif mutation=='order':data['generation_attempts'].reverse()
    elif mutation=='acceptance':data['generation_attempts'][0]['observed_acceptance']=False
    elif mutation=='id':w['candidate_id']=9
    elif mutation=='clock':w['release_time']+=1
    elif mutation=='owner':w['owner_device_id']='UNKNOWN'
    elif mutation=='fingerprint':data['environment']['fingerprint']='0'*64
    elif mutation=='count':data['capture']['complete_attempt_count']+=1
    elif mutation=='numeric_bool':w['tasks'][0]['workload']=True
    elif mutation=='numeric_inf':w['tasks'][0]['workload']=float('inf')
    elif mutation=='numeric_int':w['candidate_id']=0.0
    elif mutation=='init_missing':data['candidates'].clear();data['generation_attempts'].clear();data['capture']['complete_attempt_count']=0
    with pytest.raises(InputError):parse_replay_input(data)


def test_durations_authoritative_and_formula_audit_separate(data):
    original=parse_replay_input(data)
    data['candidates'][0]['workflow_input']['tasks'][0]['options'][0]['processing_time']+=5
    inp=parse_replay_input(data)
    before=inp.to_dict();audit=audit_formulas(inp)
    assert not audit['passed'] and audit['differences'][0]['field']=='M0.processing_time'
    assert inp.to_dict()==before
    assert simulate_replay(inp).makespan==pytest.approx(simulate_replay(original).makespan+5)


def test_missing_record_is_coverage_failure_with_partial_trace(data):
    data['candidates'].pop();data['generation_attempts'].pop();data['capture']['complete_attempt_count']=1
    r=simulate_replay(parse_replay_input(data))
    assert r.status=='FAILED' and r.reason_code=='REPLAY_INPUT_EXHAUSTED'
    assert r.makespan is None and len(r.events)==1 and r.events[0]['error']
    assert r.source_summary['last_call']['requested_attempt_sequence']==2
    assert r.generated_workflow_count==1 and r.source_summary['incomplete_attempt']


def test_incomplete_capture_diagnostic_only(data):
    data['capture'].update(complete=False,process_interrupted=True)
    with pytest.raises(InputError,match='REPLAY_CAPTURE_INCOMPLETE'):parse_replay_input(data)
    inp=parse_replay_input(data,require_complete=False);e=create_replay_engine(inp);r=e.run()
    report=compare_dynamic_reference(e,r,read_replay_json(CASES/'minimal_chain/reference.json'))
    assert not report['passed'] and not r.source_summary['input_capture_complete']
    with pytest.raises(InputError):export_fixed_instance(inp)

@pytest.mark.parametrize('change',[
    {'phase':'after_arrival','causing_workflow_id':0,'event_sequence':1},
    {'owner_device_id':'M9'}, {'clock_time':1,'phase':'after_arrival','causing_workflow_id':0},
])
def test_source_never_searches_forward(data,change):
    source=ReplayWorkflowSource(parse_replay_input(data),purpose='verify_reference')
    cause=dict(phase='initialize',owner_device_id='M0',clock_time=0);cause.update(change)
    with pytest.raises(SimulationFailure,match='REPLAY_INPUT_DIVERGENCE'):source.generate(GenerationCause(**cause),candidate_id=0)
    assert source.position==1 and source.validated_count==0


def test_id_gate_and_acceptance_checked_independently(data):
    inp=parse_replay_input(data);s=ReplayWorkflowSource(inp,purpose='verify_reference')
    with pytest.raises(SimulationFailure):s.generate(GenerationCause('initialize','M0',0),candidate_id=5)
    s=ReplayWorkflowSource(inp,purpose='verify_reference');c=s.generate(GenerationCause('initialize','M0',0),candidate_id=0)
    with pytest.raises(SimulationFailure):s.validate_admission(c,GenerationCause('initialize','M0',0),'REJECTED_RELEASE_NOT_FUTURE')


def test_event_sequence_is_diagnostic_and_not_schedule(data):
    data['generation_attempts'][1]['event_sequence']=999
    r=simulate_replay(parse_replay_input(data))
    assert r.status=='SUCCEEDED' and r.processed_event_count==7
    assert r.source_summary['validated_attempt_count']==2


def test_rule_modes_and_new_experiment_coverage():
    inp=load_replay_input(CASES/'multi_device_diamond/input.json')
    options=ReplayRunOptions(routing_rule=RuleConfig('fixed_resource','E0'))
    with pytest.raises(InputError,match='verify_reference'):create_replay_engine(inp,options)
    e=create_replay_engine(inp,options,purpose='reuse_inputs');r=e.run()
    assert r.reason_code=='REPLAY_INPUT_EXHAUSTED' and r.source_summary['new_experiment']
    report=compare_dynamic_reference(e,r,{})
    assert report['classification']=='INPUT_COVERAGE_INSUFFICIENT' and not report['passed']
    assert not r.diagnostics['original_reference_trajectory_eligible']
    with pytest.raises(InputError):create_replay_engine(inp,ReplayRunOptions(routing_rule=RuleConfig('fixed_resource','M0')),purpose='reuse_inputs')


def test_normal_stop_allows_unused_records(data):
    candidate=deepcopy(data['candidates'][1]);w=candidate['workflow_input'];cause=data['candidates'][1]['workflow_input']
    candidate['record_id']='3';w['candidate_id']=2;w['release_time']=cause['release_time']+w['inter_release_time']
    attempt=deepcopy(data['generation_attempts'][1]);attempt.update(attempt_sequence=3,candidate_ref='3',
        causing_workflow_id=1,generation_clock_time=cause['release_time'],event_sequence=8)
    data['candidates'].append(candidate);data['generation_attempts'].append(attempt);data['capture']['complete_attempt_count']=3
    r=simulate_replay(parse_replay_input(data))
    assert r.status=='SUCCEEDED' and r.source_summary['remaining_attempt_count']==1


def test_initial_B_and_immutable_behavior_config(data):
    data['initial_state']['B']=12
    inp=parse_replay_input(data);e=create_replay_engine(inp)
    assert e.initial_cutoff==12
    released=create_replay_engine(inp,ReplayRunOptions(edge_data_policy='release_after_materialization'))
    assert all(t.edge_data_state.value=='RELEASED' for t in released.state.tasks_by_key.values())
    r=simulate_replay(inp,ReplayRunOptions(max_events=1,trace_enabled=False))
    assert r.reason_code=='MAX_EVENTS_EXCEEDED' and not r.events
    from fogsim.experiment_config import parse_experiment_config
    with pytest.raises(InputError):
        parse_experiment_config(dict(format='fogsim.experiment',schema_version=1,mode='replay',
            source=dict(input_path='/input.json',purpose='reuse_inputs'),run=dict(num_jobs_recorded=3)))


def test_fixed_projection_preserves_orders_and_values():
    inp=load_replay_input(CASES/'first_device_rejected/input.json');fixed=export_fixed_instance(inp)
    accepted=[c.workflow_input for c,a in zip(inp.archive.candidates,inp.archive.generation_attempts) if a.observed_acceptance]
    assert [w.id for w in fixed.workflows]==[w.candidate_id for w in accepted]
    assert parse_instance(fixed.to_dict())==fixed
    for a,w in zip(accepted,fixed.workflows):
        assert [t.id for t in w.tasks]==[t.id for t in a.tasks]
        assert [t.options for t in w.tasks]==[t.options for t in a.tasks]
    a=create_engine(fixed);b=create_engine(fixed)
    assert a.state.workflows_by_id[0] is not b.state.workflows_by_id[0]
    assert a.run()==b.run()
    assert fixed_projection_metadata(inp)['kind']=='fixed_projection'
    empty=load_replay_input(CASES/'all_devices_rejected/input.json')
    with pytest.raises(InputError,match='no accepted'):export_fixed_instance(empty)

@pytest.mark.parametrize('name',['minimal_chain','multi_device_diamond','pending_at_stop','first_device_rejected','local_disabled','arrival_rejected','all_devices_rejected'])
def test_production_replay_against_independent_java_capture(name):
    p=CASES/name;inp=load_replay_input(p/'input.json');e=create_replay_engine(inp);r=e.run()
    report=compare_dynamic_reference(e,r,read_replay_json(p/'reference.json'),manifest_path=p/'manifest.json',input_path=p/'input.json',reference_path=p/'reference.json')
    assert report['passed'],report
    assert report['classification']==('EXPECTED_DIFFERENCE_CONFIRMED' if name in ('arrival_rejected','all_devices_rejected') else 'NORMAL_PARITY_PASSED')


def test_comparison_detects_faults_and_requires_binding():
    p=CASES/'minimal_chain';e=create_replay_engine(load_replay_input(p/'input.json'));r=e.run();ref=read_replay_json(p/'reference.json')
    report=compare_dynamic_reference(e,r,ref)
    assert not report['passed'] and report['classification']=='NOT_EXECUTED'
    ref['actions'][0]['event']['producer_device_id']='M9'
    report=compare_dynamic_reference(e,r,ref)
    assert report['first_difference']['path'].startswith('$.actions')
    assert first_difference({'priority':-0.0},{'priority':0.0})


def test_runtime_global_order_divergence_keeps_failed_event_and_position(data):
    from fogsim.environment.spec import DeviceSnapshot,EnvironmentSnapshot
    base=deepcopy(data['candidates'][0]['workflow_input'])
    data['environment']['devices'].append(dict(id='M1',numeric_id=1,processing_rate=200.0,can_process_tasks=True))
    data['environment']['fingerprint']=EnvironmentSnapshot(tuple(DeviceSnapshot(**d) for d in data['environment']['devices']),(),data['environment']['parameter_source']).fingerprint
    data['candidates']=[];data['generation_attempts']=[]
    for i,owner in enumerate(('M0','M1','M1','M0')):
        w=deepcopy(base);w.update(candidate_id=i,owner_device_id=owner,inter_release_time=100.0,release_time=100.0 if i<2 else 200.0)
        for t in w['tasks']:t['options'][0]['resource_id']=owner
        data['candidates'].append(dict(record_id=str(i+1),workflow_input=w))
        data['generation_attempts'].append(dict(attempt_sequence=i+1,phase='initialize' if i<2 else 'after_arrival',
            owner_device_id=owner,generation_clock_time=0.0 if i<2 else 100.0,causing_workflow_id=None if i<2 else 1 if i==2 else 0,
            event_sequence=None if i<2 else i-1,candidate_ref=str(i+1),observed_acceptance=True,rejection_reason=None))
    data['capture']['complete_attempt_count']=4
    result=simulate_replay(parse_replay_input(data))
    assert result.reason_code=='REPLAY_INPUT_DIVERGENCE'
    assert result.source_summary['consumed_record_count']==3 and result.source_summary['validated_attempt_count']==2
    assert result.source_summary['failure']['expected']['owner_device_id']=='M1'
    assert result.source_summary['failure']['actual']['owner_device_id']=='M0'
    assert len(result.events)==1 and result.generated_workflow_count==2


def test_preparation_exhaustion_preserves_engine_and_convenience_result(data):
    data['capture'].update(complete=False,complete_attempt_count=0,process_interrupted=True)
    data['candidates'].clear();data['generation_attempts'].clear()
    inp=parse_replay_input(data,require_complete=False)
    with pytest.raises(PreparationError) as err:create_replay_engine(inp)
    assert err.value.reason_code=='REPLAY_INPUT_EXHAUSTED'
    assert err.value.engine.run_status=='FAILED'
    assert simulate_replay(inp).reason_code=='REPLAY_INPUT_EXHAUSTED'


def test_single_run_config_reference_comparison_and_reuse_ignores_reference(tmp_path):
    from fogsim import load_experiment_config,simulate_replay_config
    case=CASES/'minimal_chain'
    config=dict(format='fogsim.experiment',schema_version=1,mode='replay',
        source=dict(input_path=str(case/'input.json'),reference_path=str(case/'reference.json'),purpose='verify_reference'))
    p=tmp_path/'config.json';p.write_text(json.dumps(config))
    r=simulate_replay_config(load_experiment_config(p))
    assert r.diagnostics['comparison_status']=='NORMAL_PARITY_PASSED'
    config['source'].update(purpose='reuse_inputs',reference_path=str(tmp_path/'nonexistent-reference.json'))
    p.write_text(json.dumps(config));r=simulate_replay_config(load_experiment_config(p))
    assert r.status=='SUCCEEDED' and r.diagnostics['comparison_status']=='NOT_COMPARED'


def test_reference_is_not_used_to_control_execution():
    case=CASES/'minimal_chain';inp=load_replay_input(case/'input.json')
    e=create_replay_engine(inp);r=e.run();ref=read_replay_json(case/'reference.json')
    ref['native_result']['R']=999;ref['native_result']['clock_time']=0
    report=compare_dynamic_reference(e,r,ref)
    assert not report['passed'] and report['first_difference']
    assert r.status=='SUCCEEDED' and r.recorded_workflow_count==1 and r.final_clock_time>0
    assert first_difference({'count':1},{'count':1.0})


def test_behavior_mutation_and_diagnostic_event_sequence_detected_after_run(data):
    data['generation_attempts'][1]['event_sequence']=999
    e=create_replay_engine(parse_replay_input(data));r=e.run()
    report=compare_dynamic_reference(e,r,read_replay_json(CASES/'minimal_chain/reference.json'))
    assert report['first_difference']['path'].endswith('cause.event_sequence')
    e.config=replace(e.config,warmup_jobs=2)
    report=compare_dynamic_reference(e,r,read_replay_json(CASES/'minimal_chain/reference.json'))
    assert 'warmup_jobs' in report['reason']


def test_json_integer_duration_restores_binary64(data):
    duration=(1<<53)+1
    data['candidates'][0]['workflow_input']['tasks'][0]['options'][0]['processing_time']=duration
    inp=parse_replay_input(data)
    value=inp.archive.candidates[0].workflow_input.tasks[0].options[0].processing_time
    assert type(value) is float and value==float(1<<53)
    assert not audit_formulas(inp)['passed']


def test_optional_normalized_seed_decimal_is_exact_metadata(data):
    data['initial_state'].update(public_seed=-1,seed_encoding_version='signed64-bits-v1',rng_seed_decimal='18446744073709551615')
    inp=parse_replay_input(data)
    assert inp.initial_state.rng_seed_decimal=='18446744073709551615'
    assert simulate_replay(inp).status=='SUCCEEDED'
    for value in ('-1','18446744073709551616',18446744073709551615,True):
        data['initial_state']['rng_seed_decimal']=value
        with pytest.raises(InputError):parse_replay_input(data)
