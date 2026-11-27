from copy import deepcopy
from dataclasses import asdict,replace
import json
from pathlib import Path
import pytest
from fogsim import create_dynamic_context
from fogsim.experiment_config import RuleConfig,ReplayRunOptions,RepeatConfig
from fogsim.replay import export_replay_input,create_replay_engine,simulate_replay,write_native_replay_bundle,compare_native_results
from fogsim.replay.native import strict_difference,NATIVE_EXCLUSIONS
from ..b03.helpers import gp_dynamic
from dynamic_helpers import DIAMOND,RealRange

@pytest.mark.parametrize('route',['fcfs','fixed_resource','gp'])
@pytest.mark.parametrize('seq',['fcfs','gp'])
@pytest.mark.parametrize('trace',[True,False])
@pytest.mark.parametrize('policy',['retain','release_after_materialization'])
def test_native_v2_six_combinations(tmp_path,evidence,route,seq,trace,policy):
    cfg=gp_dynamic(tmp_path,xml=DIAMOND,devices=2,edges=1,clouds=1,N=1,W=1,trace=trace,max_events=100)
    routing=RuleConfig('gp',expression='(+ MRT (+ PT (+ UT DT)))') if route=='gp' else RuleConfig(route,'E0' if route=='fixed_resource' else None)
    sequence=RuleConfig('gp',expression='(- 0 (+ PT TWT))') if seq=='gp' else RuleConfig()
    cfg=replace(cfg,run=replace(cfg.run,routing_rule=routing,sequencing_rule=sequence,edge_data_policy=policy))
    ctx=create_dynamic_context(cfg);native=ctx.run();state=ctx.snapshot_rng();inp=export_replay_input(ctx.engine,cfg.source)
    engine=create_replay_engine(inp);replay=engine.run();report=compare_native_results(native,replay)
    assert native.status==replay.status=='SUCCEEDED' and report['passed'],report
    assert inp.schema_version==2 and inp.capture.is_complete and inp.run_config==cfg.run
    assert inp.recorded_rule_manifest==native.rule_manifest and ctx.snapshot_rng()==state
    assert strict_difference(asdict(inp.archive),asdict(engine.admission.archive)) is None
    assert replay.source_summary['consumed_record_count']==len(inp.archive.generation_attempts)
    evidence('observations.json',dict(input=inp.to_dict(),native=native.to_dict(),replay=replay.to_dict(),comparison=report))

def test_bound_reference_read_only_after_termination(tmp_path,monkeypatch,evidence):
    cfg=gp_dynamic(tmp_path,xml=DIAMOND,edges=1,N=2,W=1);ctx=create_dynamic_context(cfg);native=ctx.run()
    d=tmp_path/'bundle';write_native_replay_bundle(ctx.engine,cfg.source,d)
    import fogsim.replay.engine as module
    ended=[];calls=[];run=module.ReplayEngine.run;read=Path.read_text
    def wrapped(self):
        result=run(self);ended.append(self.run_status);return result
    def guarded(self,*a,**kw):
        if self.name in ('reference.json','manifest.json'):
            assert ended and ended[-1] in ('SUCCEEDED','FAILED');calls.append(self.name)
        return read(self,*a,**kw)
    monkeypatch.setattr(module.ReplayEngine,'run',wrapped);monkeypatch.setattr(Path,'read_text',guarded)
    result=simulate_replay(d/'input.json',reference_path=d/'reference.json')
    assert result.diagnostics['comparison_status']=='NORMAL_PARITY_PASSED' and calls
    evidence('bound-loop.json',dict(native=native.to_dict(),replay=result.to_dict(),accesses=calls))

@pytest.mark.parametrize('role',['routing','sequencing'])
def test_verify_equivalent_identity_keeps_current_source(tmp_path,role,evidence):
    cfg=gp_dynamic(tmp_path,route='(+ PT 1)',sequence='(+ PT 1)');ctx=create_dynamic_context(cfg);ctx.run()
    d=tmp_path/'bundle';write_native_replay_bundle(ctx.engine,cfg.source,d)
    current=' ( + PT 1d ) \n'
    result=simulate_replay(d/'input.json',ReplayRunOptions(**{role+'_rule':RuleConfig('gp',expression=current)}),reference_path=d/'reference.json')
    assert result.diagnostics['comparison_status']=='NORMAL_PARITY_PASSED'
    rules=result.diagnostics['replay_rules'];assert rules['recorded']['rule_pair_id']==rules['active']['rule_pair_id']
    assert rules['recorded']['bindings'][role]['source']['expression']=='(+ PT 1)'
    assert rules['active']['bindings'][role]['source']['expression']==current
    evidence('sources.json',result.to_dict())

@pytest.mark.parametrize('expr',['-0.0','1e309','-1e309','(* 1e309 0)','(/ 1 -0.0)','(/ -1e-300 1e300)'])
@pytest.mark.parametrize('trace',[True,False])
def test_special_scores_capture_replay_repeat(tmp_path,expr,trace,evidence):
    from fogsim.serialization.result import decode_result
    from fogsim.experiments import run_experiment
    cfg=gp_dynamic(tmp_path,route=expr,sequence=expr,trace=trace,N=2);ctx=create_dynamic_context(cfg);native=ctx.run()
    inp=export_replay_input(ctx.engine,cfg.source);replay=create_replay_engine(inp).run()
    assert compare_native_results(native,replay)['passed']
    decoded=decode_result(json.loads(json.dumps(replay.to_dict(),allow_nan=False)))
    assert decoded['rule_manifest']==inp.recorded_rule_manifest
    batch=run_experiment(replace(cfg,repeat=RepeatConfig(2,'fresh_same_seed'))).to_dict()
    assert batch['schema_version']==2 and batch['status']=='SUCCEEDED' and batch['runs'][0]==batch['runs'][1]
    evidence('scores.json',dict(input=inp.to_dict(),native=native.to_dict(),replay=replay.to_dict(),batch=batch))

@pytest.mark.parametrize('path',['diagnostics.legacy_nonrecording_events','diagnostics.edge_data_cleanup.workflows_released','final_state.clock_time','events.0.after.clock_time','source_summary.attempt_count'])
def test_diagnostics_state_not_ignored(tmp_path,path):
    cfg=gp_dynamic(tmp_path);ctx=create_dynamic_context(cfg);native=ctx.run();inp=export_replay_input(ctx.engine,cfg.source)
    replay=create_replay_engine(inp).run().to_dict();target=replay;keys=path.split('.')
    for key in keys[:-1]:target=target[int(key)] if isinstance(target,list) else target[key]
    target[keys[-1]]+=1
    report=compare_native_results(native,replay)
    assert not report['passed'] and report['first_difference']['field_path']=='$.'+path.replace('.0','[0]')
    assert all(p not in (('diagnostics',),('final_state',),('events',)) for p in NATIVE_EXCLUSIONS)

def test_congested_gp_loop_selects_nonfirst(tmp_path,evidence):
    cfg=gp_dynamic(tmp_path,devices=2,edges=1,local=False,N=1,W=1,max_events=100,route='(+ PT MRT)',sequence='(- 0 PT)')
    cfg=replace(cfg,source=replace(cfg.source,samplers=replace(cfg.source.samplers,workload=RealRange(5000,15000))))
    ctx=create_dynamic_context(cfg);native=ctx.run();inp=export_replay_input(ctx.engine,cfg.source);replay=create_replay_engine(inp).run()
    rows=[d for d in native.decisions if d['kind']=='SEQUENCING' and len(d['candidates'])>1]
    assert rows and any(d['selected']!=d['candidates'][0]['option'] for d in rows)
    assert native.status=='SUCCEEDED' and compare_native_results(native,replay)['passed']
    evidence('congested-loop.json',dict(input=inp.to_dict(),native=native.to_dict(),replay=replay.to_dict(),multiple_candidate_decisions=rows))
