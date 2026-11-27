from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import random
import pytest
from fogsim import create_dynamic_context
from fogsim.errors import NumericDerivationError
from fogsim.experiment_config import RepeatConfig,ReplaySourceConfig,ReplayRunOptions,ExperimentConfig
from fogsim.experiments import run_experiment
from fogsim.replay import export_replay_input,create_replay_engine,write_native_replay_bundle
from fogsim.rules.factory import install_rules
from fogsim.simulation.context import SimulationContext
from ..b03.helpers import gp_dynamic
from dynamic_helpers import DIAMOND

@pytest.mark.parametrize('mode',['fresh_same_seed','fresh_seed_list','java_rerun'])
@pytest.mark.parametrize('policy',['retain','release_after_materialization'])
def test_repeat_lifecycle_statistics_isolation(tmp_path,mode,policy,evidence,monkeypatch):
    cfg=gp_dynamic(tmp_path,xml=DIAMOND,devices=2,edges=1,N=1,W=1,max_events=100)
    cfg=replace(cfg,run=replace(cfg.run,edge_data_policy=policy),repeat=RepeatConfig(3,mode,(7,8,9) if mode=='fresh_seed_list' else None))
    calls=[];original=SimulationContext._prepare
    def prepare(self,op,*a,**kw):calls.append(op);return original(self,op,*a,**kw)
    monkeypatch.setattr(SimulationContext,'_prepare',prepare);checkpoints=[]
    out=run_experiment(cfg,on_progress=lambda r:checkpoints.append(r.to_dict()))
    assert out.status=='SUCCEEDED' and out.to_dict()['schema_version']==2
    assert calls==(['fresh','rerun','rerun'] if mode=='java_rerun' else ['fresh']*3)
    assert all(a.schema_version==2 and a.capture.is_complete for a in out.input_archives)
    assert all(r.rule_manifest==out.runs[0].rule_manifest for r in out.runs)
    saved=deepcopy(out.runs[0].to_dict());assert out.runs[0].events is not out.runs[1].events
    out.runs[1].events[0]['before']['clock_time']+=1;assert out.runs[0].to_dict()==saved
    if mode=='fresh_same_seed':assert out.input_archives[0].to_dict()==out.input_archives[1].to_dict()
    if mode=='java_rerun':
        assert [r.diagnostics['run_index'] for r in out.runs]==[0,1,2]
        assert out.runs[1].diagnostics['rng_start_fingerprint']==out.runs[0].diagnostics['rng_final_fingerprint']
        assert out.runs[1].diagnostics['initial_cutoff_release_time']==out.runs[0].diagnostics['cutoff_release_time']
    else:assert [r.diagnostics['run_index'] for r in out.runs]==[0,0,0]
    assert not checkpoints[0]['batch_complete'] and checkpoints[-1]['batch_complete'];evidence('checkpoints.json',checkpoints)

@pytest.mark.parametrize('operation',['reset','rerun','rotate_seed'])
def test_shared_program_contexts_and_lifecycle(tmp_path,operation,evidence):
    cfg=gp_dynamic(tmp_path,edges=1,N=2,W=1);prepared=install_rules(cfg.run);program=prepared.routing.compiled
    a=create_dynamic_context(cfg,prepared_rules=prepared);b=create_dynamic_context(cfg,prepared_rules=prepared)
    first=a.run();saved=deepcopy(first.to_dict());b.run();previous=a.engine
    if operation=='rerun':r=a.rerun()
    else:getattr(a,operation)();r=a.run()
    assert a.engine is not previous and a.engine.state is not previous.state and a.engine.state is not b.engine.state
    assert a.engine.prepared_rules.routing.compiled is b.engine.prepared_rules.routing.compiled is program
    assert first.to_dict()==saved and prepared.rule_manifest==install_rules(cfg.run).rule_manifest
    assert a.engine.admission.source is not previous.admission.source and a.engine.run_index==1 and r.status=='SUCCEEDED'
    evidence('lifecycle.json',dict(first=saved,following=r.to_dict(),operation=operation))

@pytest.mark.parametrize('mode',['fresh_same_seed','java_rerun'])
def test_domain_failure_partial_capture_honest_means(tmp_path,mode,monkeypatch,evidence):
    import fogsim.instances.source as source
    original=source.generate_workflow_input;calls=[]
    def generate(*a,**kw):
        calls.append(1)
        if len(calls)==1:raise NumericDerivationError('injected',float('inf'))
        return original(*a,**kw)
    monkeypatch.setattr(source,'generate_workflow_input',generate)
    out=run_experiment(replace(gp_dynamic(tmp_path),repeat=RepeatConfig(3,mode)))
    assert out.status=='FAILED' and out.failed_runs==1 and out.succeeded_runs==2
    assert out.all_runs_mean is None and out.mean_over_successes is not None and not out.input_archives[0].capture.is_complete
    assert out.runs[0].to_dict()['schema_version']==2 and out.runs[0].rule_manifest==out.runs[1].rule_manifest
    assert out.to_dict()['failure_rate']==1/3 and out.to_dict()['success_denominator']==2;evidence('failed.json',out.to_dict())

def test_unknown_exception_keeps_incomplete_checkpoint(tmp_path,monkeypatch,evidence):
    import fogsim.experiments.runner as runner
    original=runner.create_dynamic_context;calls=[];checkpoints=[]
    def create(*a,**kw):
        calls.append(1)
        if len(calls)==2:raise TypeError('injected bug')
        return original(*a,**kw)
    monkeypatch.setattr(runner,'create_dynamic_context',create)
    with pytest.raises(TypeError,match='injected bug'):
        run_experiment(replace(gp_dynamic(tmp_path),repeat=RepeatConfig(3,'fresh_same_seed')),on_progress=lambda r:checkpoints.append(r.to_dict()))
    assert checkpoints[-1]['completed_runs']==1 and checkpoints[-1]['not_run']==2
    assert checkpoints[-1]['status']=='INCOMPLETE' and checkpoints[-1]['all_runs_mean'] is None;evidence('interrupted.json',checkpoints)

def test_capture_replay_no_rng_entry_attempts(tmp_path,monkeypatch,evidence):
    cfg=gp_dynamic(tmp_path,edges=1,N=2);ctx=create_dynamic_context(cfg);ctx.run();before=ctx.snapshot_rng();calls=[]
    def forbidden(*a,**kw):calls.append(True);raise AssertionError('RNG operation')
    with monkeypatch.context() as m:
        for name in ('random','seed','setstate','getrandbits','randrange','randint','uniform','expovariate','__init__'):m.setattr(random.Random,name,forbidden)
        try:inp=export_replay_input(ctx.engine,cfg.source);r=create_replay_engine(inp).run()
        finally:after=ctx.snapshot_rng()
    assert before==after and not calls and r.status=='SUCCEEDED'
    evidence('rng.json',dict(before_fingerprint=before.fingerprint,after_fingerprint=after.fingerprint,native_states_equal=before.native_state==after.native_state,attempts=calls,replay=r.to_dict()))

@pytest.mark.parametrize('purpose',['verify_reference','reuse_inputs'])
def test_repeat_same_input_cursors_reference_sentinel(tmp_path,monkeypatch,purpose,evidence):
    cfg=gp_dynamic(tmp_path,N=2);ctx=create_dynamic_context(cfg);ctx.run();d=tmp_path/'bundle';write_native_replay_bundle(ctx.engine,cfg.source,d)
    original=Path.open
    if purpose=='reuse_inputs':
        def guard(self,*a,**kw):
            if self.name in ('reference.json','manifest.json'):raise AssertionError('reference access')
            return original(self,*a,**kw)
        monkeypatch.setattr(Path,'open',guard)
    plan=ExperimentConfig('replay',ReplaySourceConfig(d/'input.json',purpose,d/'reference.json'),ReplayRunOptions(),RepeatConfig(3),schema_version=2)
    out=run_experiment(plan)
    assert out.status=='SUCCEEDED' and out.runs[0].to_dict()==out.runs[1].to_dict()
    assert all(r.diagnostics['comparison_status']==('NORMAL_PARITY_PASSED' if purpose=='verify_reference' else 'NOT_COMPARED') for r in out.runs)
    assert all(r.source_summary['consumed_record_count']==len(out.input_archives[0].archive.generation_attempts) for r in out.runs);evidence('repeat.json',out.to_dict())

def test_cleanup_preserves_gp_results_rng(tmp_path,evidence):
    cfg=gp_dynamic(tmp_path,xml=DIAMOND,edges=1,N=2)
    a=create_dynamic_context(cfg);b=create_dynamic_context(replace(cfg,run=replace(cfg.run,edge_data_policy='release_after_materialization')))
    x,y=a.run(),b.run()
    assert x.decisions==y.decisions and x.task_records==y.task_records and x.workflow_records==y.workflow_records
    assert x.makespan==y.makespan and x.mean_flow_time==y.mean_flow_time and a.snapshot_rng()==b.snapshot_rng()
    assert y.diagnostics['edge_data_cleanup']['removed_mapping_entry_count']>0 and x.rule_manifest==y.rule_manifest
    evidence('cleanup.json',dict(retain=x.to_dict(),release=y.to_dict()))
