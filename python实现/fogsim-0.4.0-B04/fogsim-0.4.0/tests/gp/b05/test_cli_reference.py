from dataclasses import replace
import hashlib,json
from pathlib import Path
import pytest
from fogsim import create_dynamic_context
from fogsim.cli import main
from fogsim.errors import InputError,StateError
from fogsim.experiment_config import ReplayRunOptions,WorkflowTypeRange
from fogsim.replay import export_replay_input,create_replay_engine,load_replay_input,simulate_replay,write_native_replay_bundle
from fogsim.io import write_json_atomic
from fogsim.serialization.result import read_result
from ..b03.helpers import gp_dynamic
from conftest import ROOT

@pytest.mark.parametrize('mode',['fresh_same_seed','fresh_seed_list','java_rerun'])
def test_cli_archived_repeat_replay_manifest(tmp_path,mode,evidence):
    cfg=gp_dynamic(tmp_path,edges=1);path=tmp_path/'config.json';write_json_atomic(path,cfg.to_dict());out=tmp_path/'result.json';archive=tmp_path/'archive'
    args=['dynamic','--config',str(path),'--output',str(out),'--archive-dir',str(archive),'--repeat','2','--repeat-mode',mode]
    if mode=='fresh_seed_list':args+=['--seeds','7','8']
    assert main(args)==0
    result=json.loads(out.read_text());manifest=json.loads((archive/'batch-manifest.json').read_text())
    assert result['schema_version']==manifest['schema_version']==2 and manifest['batch_complete']
    assert result['completed_runs']==2 and result['not_run']==0
    for i,row in enumerate(manifest['inputs']):
        f=archive/row['path'];inp=load_replay_input(f)
        assert inp.schema_version==2 and hashlib.sha256(f.read_bytes()).hexdigest()==row['sha256'] and inp.recorded_rule_manifest['rule_pair_id']==row['rule_pair_id']
        config=tmp_path/f'replay-{i}.json';r=tmp_path/f'out-{i}.json'
        write_json_atomic(config,dict(format='fogsim.experiment',schema_version=2,mode='replay',source=dict(input_path=str(f),purpose='reuse_inputs'),repeat=dict(count=2)))
        assert main(['replay','--config',str(config),'--output',str(r)])==0
        repeated=json.loads(r.read_text());assert repeated['runs'][0]==repeated['runs'][1] and repeated['runs'][0]['rule_manifest']==inp.recorded_rule_manifest
    evidence('batch.json',dict(result=result,manifest=manifest))

def test_cli_override_preserves_other_slot_no_trace(tmp_path):
    cfg=gp_dynamic(tmp_path,edges=1);ctx=create_dynamic_context(cfg);ctx.run();p=tmp_path/'input.json';write_json_atomic(p,export_replay_input(ctx.engine,cfg.source).to_dict())
    config=tmp_path/'reuse.json';out=tmp_path/'out.json';write_json_atomic(config,dict(format='fogsim.experiment',schema_version=2,mode='replay',source=dict(input_path=str(p),purpose='reuse_inputs')))
    assert main(['replay','--config',str(config),'--fixed-resource','E0','--no-trace','--output',str(out)])==0
    r=read_result(out);assert not r['events'] and not r['decisions'] and r['rule_manifest']['bindings']['routing']['kind']=='fixed_resource'
    assert r['rule_manifest']['bindings']['sequencing']['source']['expression']=='(- 0 PT)' and r['diagnostics']['comparison_status']=='NOT_COMPARED'

def test_v1_command_rejects_v2_input(tmp_path):
    cfg=gp_dynamic(tmp_path);ctx=create_dynamic_context(cfg);ctx.run();p=tmp_path/'input.json';write_json_atomic(p,export_replay_input(ctx.engine,cfg.source).to_dict())
    with pytest.raises(SystemExit) as e:main(['replay','--input',str(p)])
    assert e.value.code==2

@pytest.mark.parametrize('mutate',['input_hash','rule_pair','reference_hash','whitelist','reference_value'])
def test_reference_manifest_tamper_after_run(tmp_path,mutate,evidence):
    cfg=gp_dynamic(tmp_path);ctx=create_dynamic_context(cfg);ctx.run();d=tmp_path/'bundle';write_native_replay_bundle(ctx.engine,cfg.source,d)
    manifest=json.loads((d/'manifest.json').read_text());reference=json.loads((d/'reference.json').read_text())
    if mutate=='input_hash':manifest['files']['input.json']='0'*64
    if mutate=='rule_pair':manifest['rule_pair_id']='sha256:'+'0'*64
    if mutate=='reference_hash':manifest['files']['reference.json']='0'*64
    if mutate=='whitelist':manifest['exclusion_whitelist'].append('diagnostics')
    if mutate=='reference_value':
        reference['diagnostics']['legacy_nonrecording_events']+=1;write_json_atomic(d/'reference.json',reference)
        manifest['files']['reference.json']=hashlib.sha256((d/'reference.json').read_bytes()).hexdigest()
    write_json_atomic(d/'manifest.json',manifest)
    if mutate=='reference_value':
        r=simulate_replay(d/'input.json',reference_path=d/'reference.json')
        assert r.diagnostics['comparison_status']=='FAILED' and r.diagnostics['comparison']['first_difference']['field_path']=='$.diagnostics.legacy_nonrecording_events'
        evidence('difference.json',r.to_dict())
    else:
        with pytest.raises(InputError,match='binding mismatch'):simulate_replay(d/'input.json',reference_path=d/'reference.json')

def test_event_sequence_only_compared_after_execution(tmp_path,evidence):
    cfg=gp_dynamic(tmp_path,N=2);ctx=create_dynamic_context(cfg);ctx.run();d=tmp_path/'bundle';write_native_replay_bundle(ctx.engine,cfg.source,d)
    data=json.loads((d/'input.json').read_text())
    for a in data['generation_attempts']:
        if a['phase']=='after_arrival':a['event_sequence']+=100
    write_json_atomic(d/'input.json',data);manifest=json.loads((d/'manifest.json').read_text());manifest['files']['input.json']=hashlib.sha256((d/'input.json').read_bytes()).hexdigest();write_json_atomic(d/'manifest.json',manifest)
    r=simulate_replay(d/'input.json',reference_path=d/'reference.json')
    assert r.status=='SUCCEEDED' and r.diagnostics['comparison_status']=='FAILED'
    assert r.diagnostics['comparison']['input_first_difference']['field_path'].endswith('.cause.event_sequence');evidence('sequence-postrun.json',r.to_dict())

@pytest.mark.parametrize('field',['samplers','workflow_types','environment'])
def test_false_source_metadata_no_rng(tmp_path,field):
    from fogsim.experiment_config import RealRange
    cfg=gp_dynamic(tmp_path,edges=1);ctx=create_dynamic_context(cfg);ctx.run();state=ctx.snapshot_rng()
    if field=='samplers':source=replace(cfg.source,samplers=replace(cfg.source.samplers,workload=RealRange(100,200)))
    elif field=='workflow_types':source=replace(cfg.source,workflow_types=WorkflowTypeRange(0,1))
    else:source=replace(cfg.source,environment=replace(cfg.source.environment,num_edge_servers=2))
    with pytest.raises(InputError,match='source configuration'):export_replay_input(ctx.engine,source)
    assert ctx.snapshot_rng()==state

@pytest.mark.parametrize('trace',[True,False])
def test_replay_partial_scoring_failure_tags_no_dispatch(tmp_path,monkeypatch,trace,evidence):
    from fogsim.rules.gp import GPRule
    cfg=gp_dynamic(tmp_path,edges=1,route='-1e309',trace=trace);ctx=create_dynamic_context(cfg);ctx.run();inp=export_replay_input(ctx.engine,cfg.source);engine=create_replay_engine(inp)
    original=GPRule.priority;calls=[]
    def fail(self,option,context):
        if self.spec.role.value=='routing':
            calls.append(option.key)
            if len(calls)==2:raise StateError('injected scoring failure')
        return original(self,option,context)
    monkeypatch.setattr(GPRule,'priority',fail);r=engine.run();wire=r.to_dict()
    assert r.status=='FAILED' and len(calls)==2 and not r.decisions
    error=wire['diagnostics']['decision_errors'][0];assert error['scored_prefix'][0]['priority']==dict(kind='f64',bits='fff0000000000000')
    assert 'selected' not in error and all(x['dispatch_time'] is None for x in r.task_records);evidence('failure.json',wire)

def test_input_no_reference_score_future_state(tmp_path):
    cfg=gp_dynamic(tmp_path);ctx=create_dynamic_context(cfg);ctx.run();inp=export_replay_input(ctx.engine,cfg.source);work=[inp.to_dict()]
    forbidden={'priority','selected','final_state','events','decisions','reference','reference_path','makespan','mean_flow_time'}
    while work:
        v=work.pop()
        if isinstance(v,dict):assert not (set(v)&forbidden);work.extend(v.values())
        elif isinstance(v,list):work.extend(v)
    e=create_replay_engine(inp);assert set(vars(e.admission.source))=={'archive','capture','purpose','position','validated_count','last_call','failure'}
    assert e.admission.source.archive is inp.archive

def test_v2_baseline_legacy_reference():
    from fogsim.experiment_config import parse_experiment_config
    from fogsim.replay import simulate_replay_config
    d=ROOT/'outputs/step4/cases/minimal_chain'
    cfg=parse_experiment_config(dict(format='fogsim.experiment',schema_version=2,mode='replay',source=dict(input_path=str(d/'input.json'),reference_path=str(d/'reference.json'))))
    r=simulate_replay_config(cfg);assert r.to_dict()['schema_version']==2 and r.diagnostics['comparison_status']=='NORMAL_PARITY_PASSED'

def test_no_trace_verify_not_complete_parity(tmp_path,evidence):
    cfg=gp_dynamic(tmp_path);ctx=create_dynamic_context(cfg);ctx.run();d=tmp_path/'bundle';write_native_replay_bundle(ctx.engine,cfg.source,d)
    r=simulate_replay(d/'input.json',ReplayRunOptions(trace_enabled=False),reference_path=d/'reference.json')
    assert r.status=='SUCCEEDED' and not r.events and r.diagnostics['comparison_status']=='NOT_EXECUTED' and not r.diagnostics['comparison']['passed']
    evidence('no-trace.json',r.to_dict())

@pytest.mark.parametrize('priority',[0.0,{'kind':'f64','bits':'7FF8000000000000'}])
def test_reference_invalid_f64_only_after_execution(tmp_path,monkeypatch,priority,evidence):
    cfg=gp_dynamic(tmp_path);ctx=create_dynamic_context(cfg);ctx.run();d=tmp_path/'bundle';write_native_replay_bundle(ctx.engine,cfg.source,d)
    ref=json.loads((d/'reference.json').read_text());ref['decisions'][0]['candidates'][0]['priority']=priority;write_json_atomic(d/'reference.json',ref)
    import fogsim.replay.engine as module
    completed=[];original=module.ReplayEngine.run
    def run(self):
        result=original(self);completed.append(self.run_status);return result
    monkeypatch.setattr(module.ReplayEngine,'run',run)
    with pytest.raises(InputError,match='GP_F64_ENCODING_INVALID') as caught:simulate_replay(d/'input.json',reference_path=d/'reference.json')
    assert completed==['SUCCEEDED'];evidence('invalid-score.json',dict(error=str(caught.value),completed=completed,priority=priority))
