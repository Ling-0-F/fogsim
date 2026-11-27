"""V20/V21: cleanup transactions, explicit experiments, archival and CLI contracts."""
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
import hashlib
import json
import pytest
from conftest import ROOT
from fogsim import (load_experiment_config,create_dynamic_context,load_replay_input,create_replay_engine,
    simulate_replay,export_replay_input,release_edge_data,run_experiment,load_fixed_instance,create_engine)
from fogsim.experiment_config import RepeatConfig,parse_experiment_config
from fogsim.errors import InputError,StateError,NumericDerivationError
from fogsim.model.task import EdgeDataState
from fogsim.cli import main


def config():
    return load_experiment_config(ROOT/'configs/examples/step5_dynamic.json')


def workflow():
    ctx=create_dynamic_context(config())
    return ctx,ctx.engine.state.workflows_by_id[0]


def replay_config(count=1,purpose='reuse_inputs'):
    source=dict(input_path=str(ROOT/'outputs/step4/cases/minimal_chain/input.json'),purpose=purpose)
    if purpose=='verify_reference':source['reference_path']=str(ROOT/'outputs/step4/cases/minimal_chain/reference.json')
    return parse_experiment_config(dict(format='fogsim.experiment',schema_version=1,mode='replay',source=source,repeat=dict(count=count)))


def test_cleanup_is_atomic_idempotent_and_archive_independent():
    ctx,w=workflow();archive=ctx.input_archive;before=asdict(archive);rng=ctx.snapshot_rng()
    options=tuple(o for t in w.tasks for o in t.options);topology=[(tuple(t.parents),tuple(t.children)) for t in w.tasks]
    events=len(ctx.engine.event_queue.staging_heaps[w.owner_device]);clock=ctx.engine.state.clock_time
    report=release_edge_data(w,archive)
    assert report.released_task_count==2 and report.removed_mapping_entry_count==2
    assert all(t.edge_data_state==EdgeDataState.RELEASED for t in w.tasks)
    for t in w.tasks:
        with pytest.raises(StateError,match='RELEASED'):t.edge_data()
    assert asdict(archive)==before and ctx.snapshot_rng()==rng and ctx.engine.state.clock_time==clock
    assert tuple(o for t in w.tasks for o in t.options)==options
    assert [(tuple(t.parents),tuple(t.children)) for t in w.tasks]==topology
    assert len(ctx.engine.event_queue.staging_heaps[w.owner_device])==events
    again=release_edge_data(w,archive)
    assert again.released_task_count==again.removed_mapping_entry_count==0 and again.already_released_task_count==2
    assert ctx.run().status=='SUCCEEDED'


@pytest.mark.parametrize('corruption',['option','edge_value','task_owner','topology','total','mixed','aliased_maps','missing_archive'])
def test_cleanup_preflights_entire_workflow_before_any_mutation(corruption):
    ctx,w=workflow();archive=ctx.input_archive;first=w.tasks[0];last=w.tasks[-1]
    if corruption=='option':last.options.clear()
    elif corruption=='edge_value':last.input_data_by_parent[first.id]+=1
    elif corruption=='task_owner':last.workflow=deepcopy(w)
    elif corruption=='topology':last.parents.clear()
    elif corruption=='total':last.total_input_data+=1
    elif corruption=='mixed':last.edge_data_state=EdgeDataState.UNAVAILABLE;last.input_data_by_parent=last.output_data_by_child=None
    elif corruption=='aliased_maps':last.output_data_by_child=first.input_data_by_parent
    elif corruption=='missing_archive':archive=replace(archive,candidates=(),generation_attempts=(),admissions=())
    first_map=first.output_data_by_child
    with pytest.raises(StateError):release_edge_data(w,archive)
    assert first.output_data_by_child is first_map and first.edge_data_state==EdgeDataState.RETAINED


def test_fixed_unavailable_is_skipped_and_unknown_archive_rejected():
    e=create_engine(load_fixed_instance(ROOT/'data/cases/chain_remote.json'))
    report=release_edge_data(e.state.workflows_by_id[0],None)
    assert report.status=='UNAVAILABLE' and report.unavailable_task_count==2
    ctx,w=workflow()
    with pytest.raises(InputError):release_edge_data(w,None)
    with pytest.raises(InputError):release_edge_data(None,ctx.input_archive)


def comparable(result):
    value=result.to_dict();value['diagnostics'].pop('edge_data_cleanup')
    return value


def test_random_release_preserves_all_facts_trace_statistics_and_rng():
    c=config();a=create_dynamic_context(c);b=create_dynamic_context(replace(c,run=replace(c.run,edge_data_policy='release_after_materialization')))
    assert a.input_archive==b.input_archive and a.snapshot_rng()==b.snapshot_rng()
    left=a.run();right=b.run()
    assert comparable(left)==comparable(right)
    assert a.input_archive==b.input_archive and a.snapshot_rng()==b.snapshot_rng()
    assert all(t.edge_data_state==EdgeDataState.RELEASED for t in b.engine.state.tasks_by_key.values())
    assert right.diagnostics['edge_data_cleanup']['released_task_count']==len(b.engine.state.tasks_by_key)
    assert len(b.engine.state.workflows_by_id)==right.generated_workflow_count


def test_replay_release_preserves_exact_trace_and_reference_verdict():
    c=replay_config(purpose='verify_reference')
    left=run_experiment(c);right=run_experiment(replace(c,run=replace(c.run,edge_data_policy='release_after_materialization')))
    assert left.status==right.status=='SUCCEEDED'
    assert comparable(left.runs[0])==comparable(right.runs[0])
    assert right.runs[0].diagnostics['comparison_status']=='NORMAL_PARITY_PASSED'


@pytest.mark.parametrize('policy',['retain','release_after_materialization'])
def test_python_input_export_alone_replays_recorded_durations_and_events(policy,tmp_path):
    c=config();ctx=create_dynamic_context(replace(c,run=replace(c.run,edge_data_policy=policy)))
    r=ctx.run();rng=ctx.snapshot_rng();inp=export_replay_input(ctx.engine,c.source,dataset_role='test')
    p=tmp_path/'input.json';p.write_text(json.dumps(inp.to_dict()))
    e=create_replay_engine(load_replay_input(p));replay=e.run()
    assert ctx.snapshot_rng()==rng and replay.status==r.status=='SUCCEEDED'
    assert (r.makespan,r.mean_flow_time)==(replay.makespan,replay.mean_flow_time)
    assert r.workflow_records==replay.workflow_records and r.task_records==replay.task_records and r.decisions==replay.decisions
    original=deepcopy(r.events);actual=deepcopy(replay.events)
    for event in actual:
        for boundary in ('before','after'):event[boundary].pop('staged_event_counts')
    assert original==actual
    assert inp.to_dict()['origin']['language']=='Python' and inp.to_dict()['diagnostics']['dataset_role']=='test'
    assert list(tmp_path.iterdir())==[p]


def test_fresh_same_seed_results_and_inputs_are_identical_but_graphs_fresh():
    c=replace(config(),repeat=RepeatConfig(3,'fresh_same_seed'));snapshots=[]
    out=run_experiment(c,on_progress=lambda x:snapshots.append(x.to_dict()))
    assert out.status=='SUCCEEDED' and out.succeeded_runs==3 and out.not_run==out.failed_runs==0
    assert all(r.to_dict()==out.runs[0].to_dict() for r in out.runs)
    assert out.runs[0] is not out.runs[1] and out.runs[0].task_records is not out.runs[1].task_records
    assert all(a.to_dict()==out.input_archives[0].to_dict() for a in out.input_archives)
    assert snapshots[0]['runs']==[] and not snapshots[0]['batch_complete']
    assert len(snapshots[1]['runs'])==1 and snapshots[1]['all_runs_mean'] is None
    assert snapshots[-1]['batch_complete'] and out.sample_stddev==dict(makespan=0.0,mean_flow_time=0.0)
    assert out.all_runs_mean==out.mean_over_successes


def test_seed_list_uses_exact_signed64_seeds_and_new_environments():
    c=config();c=replace(c,source=replace(c.source,seed=None),repeat=RepeatConfig(2,'fresh_seed_list',(-(1<<63),(1<<63)-1)))
    out=run_experiment(c)
    assert [r.diagnostics['public_seed'] for r in out.runs]==[-(1<<63),(1<<63)-1]
    assert out.run_metadata[0]['environment_fingerprint']!=out.run_metadata[1]['environment_fingerprint']
    assert all(r.diagnostics['run_index']==0 for r in out.runs)


def test_java_rerun_matches_manual_lifecycle_without_extra_reset_or_rotation(monkeypatch):
    c=replace(config(),repeat=RepeatConfig(3,'java_rerun'))
    from fogsim.simulation.context import SimulationContext
    def forbidden(*a,**k):raise AssertionError('unrequested lifecycle call')
    monkeypatch.setattr(SimulationContext,'reset',forbidden);monkeypatch.setattr(SimulationContext,'rotate_seed',forbidden)
    out=run_experiment(c);manual=create_dynamic_context(c.single_run(0));expected=[manual.run(),manual.rerun(),manual.rerun()]
    assert [r.to_dict() for r in out.runs]==[r.to_dict() for r in expected]
    for previous,current in zip(out.runs,out.runs[1:]):
        assert current.diagnostics['rng_start_fingerprint']==previous.diagnostics['rng_final_fingerprint']
        assert current.diagnostics['initial_cutoff_release_time']==previous.diagnostics['cutoff_release_time']
        assert current.diagnostics['environment_fingerprint']==previous.diagnostics['environment_fingerprint']
    assert manual.engine.run_index==2


@pytest.mark.parametrize('mode',['fresh_same_seed','java_rerun'])
def test_domain_preparation_failure_continues_with_partial_input_and_honest_means(monkeypatch,mode):
    import fogsim.instances.source as source
    original=source.generate_workflow_input;calls=0
    def first_failure(*a,**kw):
        nonlocal calls
        calls+=1
        if calls==1:raise NumericDerivationError('injected generation overflow',float('inf'))
        return original(*a,**kw)
    monkeypatch.setattr(source,'generate_workflow_input',first_failure)
    out=run_experiment(replace(config(),repeat=RepeatConfig(3,mode)))
    assert out.failed_runs==1 and out.succeeded_runs==2 and out.not_run==0 and out.status=='FAILED'
    assert out.all_runs_mean is None and out.mean_over_successes is not None and out.sample_stddev is not None
    assert not out.input_archives[0].capture.complete
    assert out.to_dict()['failure_rate']==1/3 and out.to_dict()['success_denominator']==2
    assert out.runs[0].reason_code=='NUMERIC_DERIVATION_ERROR'


def test_all_failed_and_single_success_statistics():
    c=config();failed=run_experiment(replace(c,run=replace(c.run,max_events=1),repeat=RepeatConfig(2,'fresh_same_seed')))
    assert failed.status=='FAILED' and failed.mean_over_successes is None and failed.sample_stddev is None
    single=run_experiment(c)
    assert single.status=='SUCCEEDED' and single.sample_stddev is None
    assert failed.to_dict()['failure_rate']==1


def test_replay_repeat_resets_cursor_and_verification_is_post_execution():
    out=run_experiment(replay_config(3,'verify_reference'))
    assert out.status=='SUCCEEDED' and all(r.diagnostics['comparison_status']=='NORMAL_PARITY_PASSED' for r in out.runs)
    assert all(r.source_summary['consumed_record_count']==2 for r in out.runs)
    assert out.runs[0].events is not out.runs[1].events


def test_unknown_exception_propagates_and_checkpoint_remains_incomplete(monkeypatch):
    import fogsim.experiments.runner as runner
    original=runner.simulate_replay_config;count=0;snapshots=[]
    def bug(*a,**kw):
        nonlocal count
        count+=1
        if count==2:raise TypeError('injected programming defect')
        return original(*a,**kw)
    monkeypatch.setattr(runner,'simulate_replay_config',bug)
    with pytest.raises(TypeError,match='programming defect'):
        run_experiment(replay_config(3),on_progress=lambda r:snapshots.append(r.to_dict()))
    assert snapshots[-1]['completed_runs']==1 and snapshots[-1]['not_run']==2
    assert not snapshots[-1]['batch_complete'] and snapshots[-1]['all_runs_mean'] is None


def test_cli_dynamic_archive_replay_projection_and_old_repeat(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    path=tmp_path/'batch.json';archive=tmp_path/'inputs'
    assert main(['dynamic','--config',str(ROOT/'configs/examples/step5_dynamic.json'),'--repeat','2','--repeat-mode','fresh_same_seed',
                 '--seed','-1','--no-trace','--edge-data-policy','release_after_materialization','--output',str(path),'--archive-dir',str(archive)])==0
    value=json.loads(path.read_text());assert value['batch_complete'] and value['succeeded_runs']==2 and value['inputs']
    assert all(not r['events'] and r['task_records'] for r in value['runs'])
    assert json.loads((archive/'batch-manifest.json').read_text())['files']==['run-000000.input.json','run-000001.input.json']
    p=archive/'run-000000.input.json';replay=tmp_path/'replay.json'
    assert main(['replay','--input',str(p),'--repeat','2','--output',str(replay)])==0
    assert json.loads(replay.read_text())['succeeded_runs']==2
    fixed=tmp_path/'fixed.json'
    assert main(['export-fixed','--input',str(p),'--output',str(fixed)])==0
    meta=json.loads(fixed.with_suffix('.projection.json').read_text())
    assert meta['kind']=='fixed_projection' and meta['complete']
    assert meta['fixed_input_sha256']==hashlib.sha256(fixed.read_bytes()).hexdigest()
    assert main(['--instance',str(fixed),'--repeat','2','--output',str(tmp_path/'old.json')])==0
    old=json.loads((tmp_path/'old.json').read_text());assert old['identical'] and 'batch_complete' not in old


@pytest.mark.parametrize('args',[
    ['dynamic','--config','configs/examples/step5_dynamic.json','--repeat','2'],
    ['dynamic','--config','configs/examples/step5_dynamic.json','--seed',str(1<<63)],
    ['dynamic','--config','configs/examples/step5_dynamic.json','--repeat','0'],
    ['dynamic','--config','configs/examples/step5_dynamic.json','--repeat-mode','fresh_seed_list','--repeat','2','--seeds','1'],
    ['dynamic','--config','configs/examples/step6_verify.json'],
    ['replay','--config','configs/examples/step5_dynamic.json'],
])
def test_cli_bad_config_exits_two_before_rng(args,tmp_path,monkeypatch):
    import fogsim.simulation.context as context
    def forbidden(*a,**kw):raise AssertionError('invalid config reached sampling')
    monkeypatch.setattr(context,'prepare_random_input',forbidden)
    args=[str(ROOT/x) if x.startswith('configs/') else x for x in args]
    out=tmp_path/'result.json';out.write_text('{"status":"SUCCEEDED"}')
    with pytest.raises(SystemExit) as exc:main([*args,'--output',str(out)])
    assert exc.value.code==2 and not out.exists()


def test_cli_replay_cannot_override_seed_or_statistics():
    for flag,value in [('--seed','1'),('--num-jobs-recorded','2'),('--warmup-jobs','2')]:
        with pytest.raises(SystemExit) as exc:main(['replay','--input',str(ROOT/'tests/fixtures/dynamic_v1/input.json'),flag,value])
        assert exc.value.code==2


def test_cli_domain_failure_returns_one_and_full_failure_denominator(tmp_path):
    p=tmp_path/'failed.json'
    code=main(['dynamic','--config',str(ROOT/'configs/examples/step5_dynamic.json'),'--repeat','2','--repeat-mode','java_rerun',
               '--max-events','1','--output',str(p)])
    value=json.loads(p.read_text())
    assert code==1 and value['batch_complete'] and value['failed_runs']==2 and value['not_run']==0
    assert value['all_runs_mean'] is None and value['mean_over_successes'] is None


def test_cli_programming_exception_replaces_stale_success_with_incomplete_batch(tmp_path,monkeypatch):
    import fogsim.experiments.runner as runner
    def bug(*a,**kw):raise RuntimeError('injected original bug')
    monkeypatch.setattr(runner,'create_dynamic_context',bug)
    p=tmp_path/'result.json';p.write_text('{"status":"SUCCEEDED"}')
    with pytest.raises(RuntimeError,match='original bug'):
        main(['dynamic','--config',str(ROOT/'configs/examples/step5_dynamic.json'),'--output',str(p)])
    value=json.loads(p.read_text())
    assert value['status']=='INCOMPLETE' and not value['batch_complete'] and value['all_runs_mean'] is None
    assert value['interruption']['type']=='RuntimeError' and value['not_run']==1


def test_old_cli_programming_bug_removes_stale_success(tmp_path,monkeypatch):
    import fogsim.cli as cli
    def bug(*a,**kw):raise TypeError('fixed bug')
    monkeypatch.setattr(cli,'simulate',bug)
    p=tmp_path/'result.json';p.write_text('{"status":"SUCCEEDED"}')
    with pytest.raises(TypeError):main(['--instance',str(ROOT/'data/cases/single_local.json'),'--output',str(p)])
    assert not p.exists()


def test_cli_does_not_overwrite_input_config_or_reference(tmp_path):
    p=tmp_path/'input.json';p.write_text((ROOT/'tests/fixtures/dynamic_v1/input.json').read_text());before=p.read_bytes()
    with pytest.raises(SystemExit) as exc:main(['replay','--input',str(p),'--output',str(p)])
    assert exc.value.code==2 and p.read_bytes()==before
    c=tmp_path/'cfg.json';raw=dict(format='fogsim.experiment',schema_version=1,mode='replay',source=dict(input_path='input.json',purpose='reuse_inputs'),run=dict(unknown=1))
    c.write_text(json.dumps(raw))
    with pytest.raises(SystemExit):main(['replay','--config',str(c),'--output',str(p)])
    assert p.read_bytes()==before


def test_verify_reference_without_trace_is_not_reported_as_passed(tmp_path):
    p=tmp_path/'result.json'
    assert main(['replay','--config',str(ROOT/'configs/examples/step6_verify.json'),'--no-trace','--output',str(p)])==1
    value=json.loads(p.read_text())
    assert value['runs'][0]['status']=='SUCCEEDED' and value['status']=='FAILED' and value['verification_failures']
    assert value['all_runs_mean'] is None and value['succeeded_runs']==1 and value['failed_runs']==0


def test_changed_template_between_fresh_rounds_disables_aggregation(tmp_path):
    directory=tmp_path/'dax';directory.mkdir()
    p=directory/'CyberShake_30.xml';p.write_text((ROOT/'examples/step5/dax/CyberShake_30.xml').read_text())
    c=config();c=replace(c,source=replace(c.source,dag_root=directory),repeat=RepeatConfig(2,'fresh_same_seed'))
    changed=False
    def progress(result):
        nonlocal changed
        if len(result.runs)==1 and not changed:
            p.write_text(p.read_text()+'\n<!-- different source version -->\n');changed=True
    out=run_experiment(c,on_progress=progress)
    assert out.succeeded_runs==2 and not out.aggregation_compatible and out.status=='FAILED'
    assert out.all_runs_mean is None and out.mean_over_successes is None and out.sample_stddev is None


def test_cli_protects_source_dax_directory(tmp_path):
    directory=tmp_path/'dax';directory.mkdir();xml=directory/'CyberShake_30.xml'
    xml.write_text((ROOT/'examples/step5/dax/CyberShake_30.xml').read_text());before=xml.read_bytes()
    c=config().to_dict();c['source']['dag_root']=str(directory)
    path=tmp_path/'config.json';path.write_text(json.dumps(c))
    with pytest.raises(SystemExit) as exc:main(['dynamic','--config',str(path),'--output',str(xml)])
    assert exc.value.code==2 and xml.read_bytes()==before
