from dataclasses import replace
import hashlib
from pathlib import Path
import pytest
from fogsim import create_dynamic_context
from fogsim.errors import InputError
from fogsim.experiment_config import RuleConfig,ReplayRunOptions,parse_experiment_config
from fogsim.replay import export_replay_input,parse_replay_input,create_replay_engine,simulate_replay
from fogsim.replay.source import ReplayWorkflowSource
from fogsim.instances.generated import GenerationCause
from ..b03.helpers import gp_dynamic
from conftest import ROOT

@pytest.fixture
def captured(tmp_path):
    cfg=gp_dynamic(tmp_path,devices=2,edges=1,N=2,W=2,max_events=100);ctx=create_dynamic_context(cfg);ctx.run()
    return export_replay_input(ctx.engine,cfg.source)

@pytest.mark.parametrize('path,value',[
 ('rule_manifest.rule_pair_id','sha256:'+'0'*64),('rule_manifest.identity_encoding_version','other'),
 ('rule_manifest.bindings.routing.role','sequencing'),('rule_manifest.bindings.routing.source.expression','NIQ'),
 ('rule_manifest.bindings.routing.source.source_sha256','sha256:'+'0'*64),('rule_manifest.bindings.routing.rule_id','sha256:'+'0'*64),
 ('rule_manifest.bindings.routing.expression_id','sha256:'+'0'*64),
 ('rule_manifest.expressions.0.numeric_semantics_version','java-original-positive-zero-v1'),
 ('rule_manifest.expressions.0.ast.nodes.0.kind','feature_bad'),('effective_config.routing_rule.expression','NIQ'),
 ('origin.rules.routing.expression','NIQ'),('schema_version',3),('schema_version',True),('score_encoding_version','wrong'),
 ('candidates.0.workflow_input.tasks.0.options.0.processing_time',{'kind':'f64','bits':'3ff0000000000000'}),
 ('candidates.0.workflow_input.tasks.0.options.0.priority',{'kind':'f64','bits':'7ff8000000000000'}),('effective_config.max_events',1)])
def test_tampering_before_source(captured,path,value,monkeypatch,evidence):
    data=captured.to_dict();target=data;keys=path.split('.')
    for key in keys[:-1]:target=target[int(key)] if isinstance(target,list) else target[key]
    target[keys[-1]]=value
    import fogsim.replay.engine as module
    calls=[];monkeypatch.setattr(module,'ReplayWorkflowSource',lambda *a,**kw:calls.append(True))
    with pytest.raises(InputError) as caught:parse_replay_input(data)
    assert not calls;evidence('rejected.json',dict(path=path,error=str(caught.value),source_constructions=calls))

@pytest.mark.parametrize('case',['bad_expression','changed_identity','ineligible_target','forged_object'])
def test_invalid_active_before_source_rng(captured,monkeypatch,case,evidence):
    import fogsim.replay.engine as module
    import random
    calls=[]
    def forbidden(*a,**kw):calls.append(True);raise AssertionError('source or RNG')
    monkeypatch.setattr(module,'ReplayWorkflowSource',forbidden);monkeypatch.setattr(random,'Random',forbidden)
    inp=captured;purpose='verify_reference'
    if case=='bad_expression':options=ReplayRunOptions(routing_rule=RuleConfig('gp',expression='(+ PT)'))
    elif case=='changed_identity':options=ReplayRunOptions(routing_rule=RuleConfig('gp',expression='NIQ'))
    elif case=='ineligible_target':options=ReplayRunOptions(routing_rule=RuleConfig('fixed_resource','absent'));purpose='reuse_inputs'
    else:inp=replace(inp,run_config=replace(inp.run_config,num_jobs_recorded=20));options=None
    with pytest.raises(InputError) as caught:create_replay_engine(inp,options,purpose=purpose)
    assert not calls;evidence('early-failure.json',dict(error=str(caught.value),calls=calls))

@pytest.mark.parametrize('role',['routing','sequencing'])
@pytest.mark.parametrize('expression',['PT','(+ PT 1)'])
def test_verify_json_no_overrides(tmp_path,role,expression):
    value=dict(format='fogsim.experiment',schema_version=2,mode='replay',source=dict(input_path=str(tmp_path/'input.json'),reference_path=str(tmp_path/'reference.json')),
        run={role+'_rule':dict(kind='gp',expression=expression)})
    with pytest.raises(InputError,match='rule overrides'):parse_experiment_config(value)

@pytest.mark.parametrize('field',['phase','owner_device_id','clock_time','causing_workflow_id','candidate_id'])
@pytest.mark.parametrize('purpose',['verify_reference','reuse_inputs'])
def test_global_cursor_no_search(captured,field,purpose,evidence):
    source=ReplayWorkflowSource(captured,purpose=purpose);attempts=captured.archive.generation_attempts
    index=next(i for i,a in enumerate(attempts) if a.cause.phase=='after_arrival')
    for prior,record in zip(attempts[:index],captured.archive.candidates[:index]):
        candidate=source.generate(prior.cause,candidate_id=record.workflow_input.candidate_id)
        source.validate_admission(candidate,prior.cause,prior.rejection_reason)
    cause=attempts[index].cause;cid=captured.archive.candidates[index].workflow_input.candidate_id
    if field=='candidate_id':cid+=999
    elif field=='phase':cause=GenerationCause('initialize',cause.owner_device_id,0.)
    elif field=='owner_device_id':cause=replace(cause,owner_device_id='M1' if cause.owner_device_id=='M0' else 'M0')
    elif field=='clock_time':cause=replace(cause,clock_time=cause.clock_time+1.)
    else:cause=replace(cause,causing_workflow_id=cause.causing_workflow_id+999)
    with pytest.raises(Exception,match='REPLAY_INPUT_DIVERGENCE'):source.generate(cause,candidate_id=cid)
    assert source.position==index+1 and source.validated_count==index
    evidence('cursor.json',source.summary())

def test_event_sequence_not_consume_condition(captured,evidence):
    data=captured.to_dict()
    for a in data['generation_attempts']:
        if a['phase']=='after_arrival':a['event_sequence']+=10000
    inp=parse_replay_input(data);engine=create_replay_engine(inp);result=engine.run()
    assert result.status=='SUCCEEDED' and engine.admission.source.position==len(inp.archive.generation_attempts)
    assert engine.admission.archive.generation_attempts!=inp.archive.generation_attempts
    evidence('event-sequence.json',result.to_dict())

@pytest.mark.parametrize('purpose',['verify_reference','reuse_inputs'])
def test_exhaustion_coverage(captured,purpose,evidence):
    data=captured.to_dict();count=len(captured.archive.environment.devices)
    data['candidates']=data['candidates'][:count];data['generation_attempts']=data['generation_attempts'][:count];data['capture']['complete_attempt_count']=count
    r=simulate_replay(parse_replay_input(data),purpose=purpose)
    assert r.reason_code=='REPLAY_INPUT_EXHAUSTED' and r.status=='FAILED'
    assert r.diagnostics['coverage_status']=='INPUT_COVERAGE_INSUFFICIENT' and r.diagnostics['comparison_status']=='NOT_COMPARED'
    assert r.source_summary['consumed_record_count']==count;evidence('exhausted.json',r.to_dict())

@pytest.mark.parametrize('purpose',['verify_reference','reuse_inputs'])
def test_divergence_classification(captured,purpose,monkeypatch,evidence):
    original=ReplayWorkflowSource.generate
    def inject(self,cause,**kw):
        if cause.phase=='after_arrival':cause=replace(cause,clock_time=cause.clock_time+.5)
        return original(self,cause,**kw)
    monkeypatch.setattr(ReplayWorkflowSource,'generate',inject);r=simulate_replay(captured,purpose=purpose)
    assert r.reason_code=='REPLAY_INPUT_DIVERGENCE' and r.status=='FAILED'
    assert r.diagnostics['coverage_status']==('SOURCE_DIVERGED' if purpose=='verify_reference' else 'INPUT_COVERAGE_INSUFFICIENT')
    evidence('divergence.json',r.to_dict())

def test_legal_unused_suffix(tmp_path,evidence):
    cfg=gp_dynamic(tmp_path,N=3,W=1);ctx=create_dynamic_context(cfg);ctx.run()
    data=export_replay_input(ctx.engine,cfg.source).to_dict();data['effective_config']['num_jobs_recorded']=1
    r=simulate_replay(parse_replay_input(data),purpose='reuse_inputs')
    assert r.status=='SUCCEEDED' and r.source_summary['remaining_attempt_count']>0;evidence('suffix.json',r.to_dict())

@pytest.mark.parametrize('route',['fcfs','fixed_resource','gp'])
@pytest.mark.parametrize('seq',['fcfs','gp'])
@pytest.mark.parametrize('trace',[True,False])
def test_v1_migration_reuse_no_reference(tmp_path,monkeypatch,evidence,route,seq,trace):
    path=ROOT/'tests/fixtures/dynamic_full_v1/input.json';before=path.read_bytes()
    ref=tmp_path/'forbidden-reference.json';ref.write_text('MUST NOT READ');opened=Path.open;calls=[]
    def guarded(self,*a,**kw):
        if self==ref:calls.append(True);raise AssertionError('reference read')
        return opened(self,*a,**kw)
    monkeypatch.setattr(Path,'open',guarded)
    routing=RuleConfig('gp',expression='PT') if route=='gp' else RuleConfig(route,'M0' if route=='fixed_resource' else None)
    sequence=RuleConfig('gp',expression='(- 0 PT)') if seq=='gp' else RuleConfig()
    r=simulate_replay(path,ReplayRunOptions(routing_rule=routing,sequencing_rule=sequence,trace_enabled=trace),purpose='reuse_inputs',reference_path=ref,output_profile='v2')
    assert r.diagnostics['comparison_status']=='NOT_COMPARED' and not calls
    rules=r.diagnostics['replay_rules'];assert rules['migration']['from_schema_version']==1
    assert rules['migration']['input_sha256']==hashlib.sha256(before).hexdigest() and rules['active']==r.rule_manifest
    assert path.read_bytes()==before and r.reason_code in (None,'REPLAY_INPUT_DIVERGENCE','REPLAY_INPUT_EXHAUSTED')
    evidence('migration.json',r.to_dict())
