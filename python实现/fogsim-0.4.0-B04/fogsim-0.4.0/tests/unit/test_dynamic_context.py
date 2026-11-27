from dataclasses import replace
from copy import deepcopy
from itertools import repeat
import random
import pytest
from fogsim import create_dynamic_context, simulate_dynamic, PreparationError, DynamicRunResult
from fogsim.errors import EngineUsageError, InputError, NumericDerivationError
from fogsim.randomness.samplers import ExponentialSampler, UniformRealSampler
from fogsim.seed import encode_seed, rotated_seed
from fogsim.instances.generation import generate_workflow_input
from fogsim.instances.generated import GenerationCause
from dynamic_helpers import config, intervals, CHAIN


def test_real_dynamic_success_result_facts_and_rng(tmp_path,monkeypatch):
    intervals(monkeypatch,repeat(10))
    ctx = create_dynamic_context(config(tmp_path))
    assert ctx.engine.run_status=='READY' and ctx.engine.state.clock_time==0
    result = ctx.run()
    assert isinstance(result,DynamicRunResult) and result.status=='SUCCEEDED'
    assert (result.generated_workflow_count,result.arrived_workflow_count,result.completed_workflow_count,result.recorded_workflow_count)==(2,1,1,1)
    assert result.makespan==result.mean_flow_time
    assert result.diagnostics['rng_final_fingerprint']==ctx.inputs.snapshot().fingerprint
    assert result.workflow_records[0]['recorded'] and not result.workflow_records[1]['recorded']
    assert result.task_records[1]['start_time'] is None
    assert result.task_records[1]['plan'] is None
    with pytest.raises(EngineUsageError): ctx.run()
    with pytest.raises(EngineUsageError): ctx.engine.run()


@pytest.mark.parametrize('seed',[-(1<<63),(1<<63)-1,-1,0,7])
def test_reset_uses_seed_origin_without_resource_prefix_and_isolates_graph(tmp_path,seed):
    ctx=create_dynamic_context(config(tmp_path,seed=seed,devices=2,edges=1,clouds=1))
    old=ctx.engine; env=ctx.environment; samplers=ctx.inputs.samplers; catalog=ctx.inputs.catalog
    snapshot=ctx.inputs.snapshot()
    ready=ctx.reset(seed)
    assert ctx.environment is env and ctx.inputs.samplers is samplers and ctx.inputs.catalog is catalog
    assert ready is not old and old.run_status=='SUPERSEDED' and ready.run_status=='READY'
    with pytest.raises(EngineUsageError):old.run()
    assert all(a is not b for a,b in zip(old.state.resources_by_id.values(),ready.state.resources_by_id.values()))
    assert all(a is not b for a,b in zip(old.state.tasks_by_key.values(),ready.state.tasks_by_key.values()))
    assert all(a is not b for a,b in zip(old.state.workflows_by_id.values(),ready.state.workflows_by_id.values()))
    rng=random.Random(encode_seed(seed))
    # Use an independent test RNG and the frozen existing source; no resource sampling.
    inputs=replace(ctx.inputs,rng=rng)
    expected=[generate_workflow_input(inputs,env,GenerationCause('initialize',d.id,0),candidate_id=i)
              for i,d in enumerate(env.devices)]
    assert [r.workflow_input for r in ctx.input_archive.candidates]==expected
    assert ctx.inputs.snapshot().native_state==rng.getstate()
    assert old.rng_start.native_state==random.Random(encode_seed(seed)).getstate()
    # Ready-state snapshots are immutable even after another round reseeds the shared stream.
    assert snapshot==old.rng_ready


@pytest.mark.parametrize('seed',[-(1<<63),(1<<63)-1,0,7])
def test_rotate_signed64_and_current_seed_reset(tmp_path,seed):
    ctx=create_dynamic_context(config(tmp_path,seed=seed))
    old=ctx.engine
    ctx.rotate_seed()
    assert ctx.public_seed==rotated_seed(seed) and ctx.inputs.public_seed==ctx.public_seed
    assert ctx.engine.operation=='rotate_seed' and ctx.engine.run_status=='READY'
    assert ctx.engine.rng_start.native_state==random.Random(encode_seed(ctx.public_seed)).getstate()
    first=ctx.input_archive
    ctx.reset()
    assert ctx.public_seed==rotated_seed(seed) and ctx.input_archive==first
    assert old.run_status=='SUPERSEDED'


def test_rerun_continues_stream_B_and_preserves_previous_result(tmp_path,monkeypatch):
    intervals(monkeypatch,repeat(10))
    ctx=create_dynamic_context(config(tmp_path,xml=CHAIN))
    first=ctx.run(); frozen=deepcopy(first.to_dict()); old=ctx.engine; end=old.rng_final
    cutoff=ctx.cutoff_release_time; env=ctx.environment
    result=ctx.rerun()
    assert result.status=='SUCCEEDED'
    assert ctx.engine.rng_start==end and ctx.engine.initial_cutoff==cutoff
    assert ctx.environment is env and ctx.engine is not old
    assert first.to_dict()==frozen
    assert ctx.engine.processed_event_count==7 and ctx.engine.run_index==1
    assert all(old.state.resources_by_id[x] is not ctx.engine.state.resources_by_id[x] for x in old.state.resources_by_id)
    assert ctx.inputs.rng is old.admission.source.inputs.rng


def test_no_DAX_reread_or_environment_resampling_on_reset(tmp_path,monkeypatch):
    ctx=create_dynamic_context(config(tmp_path)); ctx.config.source.dag_root.joinpath('CyberShake_30.xml').unlink()
    import fogsim.simulation.context as module
    def wrong(*args,**kwargs): raise AssertionError('must reuse frozen environment')
    monkeypatch.setattr(module,'sample_environment',wrong)
    ctx.reset()
    assert ctx.engine.run_status=='READY'


@pytest.mark.parametrize('operation',['reset','rerun','rotate_seed','snapshot_rng'])
def test_lifecycle_forbidden_while_RUNNING(tmp_path,operation):
    ctx=create_dynamic_context(config(tmp_path));ctx.engine.run_status='RUNNING'
    with pytest.raises(EngineUsageError):getattr(ctx,operation)()


@pytest.mark.parametrize('seed',[True,1.5,'7',1<<63,-(1<<63)-1])
def test_bad_reset_seed_has_no_side_effect(tmp_path,seed):
    ctx=create_dynamic_context(config(tmp_path)); before=ctx.snapshot_rng(); old=ctx.engine
    with pytest.raises(InputError):ctx.reset(seed)
    assert ctx.engine is old and old.run_status=='READY' and ctx.snapshot_rng()==before


def test_preparation_domain_failure_partial_archive_and_recovery(tmp_path,monkeypatch):
    calls=intervals(monkeypatch,[1,2,3,4,5,6])
    import fogsim.instances.source as source_module
    original=source_module.generate_workflow_input
    n=0
    def fail_second(*args,**kwargs):
        nonlocal n
        n+=1
        if n==2: raise NumericDerivationError('forced generator failure',float('inf'))
        return original(*args,**kwargs)
    monkeypatch.setattr(source_module,'generate_workflow_input',fail_second)
    with pytest.raises(PreparationError) as caught:
        create_dynamic_context(config(tmp_path,devices=2))
    exc=caught.value;ctx=exc.context;r=exc.result
    assert r.status=='FAILED' and r.reason_code=='NUMERIC_DERIVATION_ERROR'
    assert r.generated_workflow_count==1 and r.final_clock_time==0
    assert r.source_summary['incomplete_attempt'] and r.source_summary['attempt_count']==1
    assert r.makespan is None and ctx.engine.rng_final is not None
    assert len(ctx.input_archive.candidates)==1
    assert ctx.reset().run_status=='READY'


def test_simulate_and_rerun_normalize_preparation_failure(tmp_path,monkeypatch):
    cfg=config(tmp_path)
    ctx=create_dynamic_context(cfg)
    import fogsim.instances.source as source_module
    def fail(*args,**kwargs):raise NumericDerivationError('forced',float('inf'))
    monkeypatch.setattr(source_module,'generate_workflow_input',fail)
    for result in (simulate_dynamic(cfg),ctx.rerun()):
        assert result.status=='FAILED' and result.reason_code=='NUMERIC_DERIVATION_ERROR'
        assert result.processed_event_count==0 and result.makespan is None
    with pytest.raises(EngineUsageError):ctx.run()


@pytest.mark.parametrize('stage',['generation','environment','runtime'])
def test_unknown_programming_exception_propagates(tmp_path,monkeypatch,stage):
    cfg=config(tmp_path)
    def wrong(*args,**kwargs):raise RuntimeError('original bug')
    if stage=='generation':
        import fogsim.instances.source as module
        monkeypatch.setattr(module,'generate_workflow_input',wrong)
        with pytest.raises(RuntimeError,match='original bug'):simulate_dynamic(cfg)
    elif stage=='environment':
        import fogsim.simulation.context as module
        monkeypatch.setattr(module,'sample_environment',wrong)
        with pytest.raises(RuntimeError,match='original bug'):simulate_dynamic(cfg)
    else:
        ctx=create_dynamic_context(cfg)
        monkeypatch.setattr(ctx.engine,'after_arrival',wrong)
        with pytest.raises(RuntimeError,match='original bug'):ctx.run()
        assert ctx.engine.run_status=='FAILED' and ctx.engine.rng_final is not None


def test_unexpanded_repeat_rejected_before_rng(tmp_path,monkeypatch):
    cfg=config(tmp_path)
    import fogsim.simulation.context as module
    def wrong(*args):raise AssertionError('must validate before RNG')
    monkeypatch.setattr(module,'prepare_random_input',wrong)
    from fogsim.experiment_config import RepeatConfig
    with pytest.raises(InputError):create_dynamic_context(replace(cfg,repeat=RepeatConfig(2,'fresh_same_seed')))


def test_environment_failure_exposes_failed_round_and_can_retry(tmp_path,monkeypatch):
    import fogsim.simulation.context as module
    original=module.sample_environment
    def fail(*args,**kwargs):raise NumericDerivationError('forced environment failure',float('inf'))
    monkeypatch.setattr(module,'sample_environment',fail)
    with pytest.raises(PreparationError) as caught:create_dynamic_context(config(tmp_path))
    exc=caught.value;ctx=exc.context
    assert ctx.environment is None and exc.result.generated_workflow_count==0
    assert exc.result.reason_code=='NUMERIC_DERIVATION_ERROR' and ctx.engine.rng_final is not None
    with pytest.raises(EngineUsageError):ctx.run()
    monkeypatch.setattr(module,'sample_environment',original)
    assert ctx.reset().run_status=='READY' and ctx.environment is not None
    assert ctx.engine.run_index==1


def test_context_does_not_retain_prior_runtime_graphs(tmp_path):
    import weakref,gc
    ctx=create_dynamic_context(config(tmp_path))
    old=weakref.ref(ctx.engine)
    ctx.reset();gc.collect()
    assert old() is None and ctx.engine.run_index==1


def test_failed_runtime_can_rerun_from_its_actual_input_state(tmp_path,monkeypatch):
    intervals(monkeypatch,repeat(1))
    ctx=create_dynamic_context(config(tmp_path,max_events=1))
    first=ctx.run();old=ctx.engine
    assert first.status=='FAILED' and first.reason_code=='MAX_EVENTS_EXCEEDED'
    before=ctx.snapshot_rng();cutoff=ctx.cutoff_release_time
    second=ctx.rerun()
    assert second.status=='FAILED' and ctx.engine.rng_start==before
    assert ctx.engine.initial_cutoff==cutoff and ctx.engine is not old


def test_environment_provenance_ignores_run_only_diagnostics(tmp_path):
    cfg=config(tmp_path)
    first=create_dynamic_context(cfg)
    second=create_dynamic_context(replace(cfg,run=replace(cfg.run,trace_enabled=False,max_events=2,check_invariants=False)))
    assert first.environment==second.environment and first.input_archive==second.input_archive


@pytest.mark.parametrize('name',['config','inputs','public_seed','environment','engine'])
def test_context_effective_parameters_cannot_be_reassigned(tmp_path,name):
    ctx=create_dynamic_context(config(tmp_path))
    with pytest.raises(AttributeError):setattr(ctx,name,None)
