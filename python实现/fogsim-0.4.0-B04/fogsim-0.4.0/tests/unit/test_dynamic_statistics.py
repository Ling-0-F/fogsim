from types import SimpleNamespace as NS
import pytest
from fogsim import create_dynamic_context
from fogsim.simulation.statistics import DynamicStatistics
from fogsim.experiment_config import DynamicRunConfig
from dynamic_helpers import config, intervals


def statistics(N=3,W=2,B=0):
    return DynamicStatistics.create(DynamicRunConfig(N,W),[NS(id='M0'),NS(id='M1')],B)


def workflow(wid,release,owner='M0'):
    return NS(id=wid,release_time=release,owner_device=NS(id=owner))


def test_B_is_assignment_and_freezes_at_G_equal_N_plus_W():
    s=statistics(N=2,W=2)
    for wid,release in enumerate([20,10,30,5,1]):
        s.accepted(workflow(wid,release))
        assert s.cutoff_release_time==[20,10,30,30,30][wid]
    assert s.generated_total==5


@pytest.mark.parametrize('G,W,wid,release,B,qualifies',[(2,2,0,1,10,False),(3,2,0,1,10,True),
    (3,2,-1,1,10,False),(3,2,10,10,10,True),(3,2,1,11,10,False),(5,2,0,10,10,True)])
def test_qualification_uses_current_G_B_not_an_ID_window(G,W,wid,release,B,qualifies):
    s=statistics(W=W,B=B);s.generated_total=G
    s.completed(workflow(wid,release))
    assert s.recorded_total==int(qualifies) and s.completed_by_device['M0']==1


def test_completed_workflows_are_not_retroactively_recorded():
    s=statistics(B=0);s.generated_total=4
    s.completed(workflow(0,10));s.cutoff_release_time=100;s.accepted(workflow(4,100,'M1'))
    assert s.recorded_total==0 and s.completed_by_device['M0']==1


def test_global_nonrecording_counter_is_not_reset_by_completion():
    s=statistics(W=0);s.recorded_workflows[0]=workflow(0,1);s.after_event(1)
    assert s.legacy_nonrecording_events==1
    s.recorded_workflows[1]=workflow(1,1);s.after_event(1)
    assert s.legacy_nonrecording_events==1
    s.after_event(2)
    assert s.legacy_nonrecording_events==2
    s.warmup_jobs=2;s.after_event(2)
    assert s.legacy_nonrecording_events==2


@pytest.mark.parametrize('boundary,over',[(400,False),(401,True)])
@pytest.mark.parametrize('kind',['device','server'])
def test_queue_guard_strict_boundary(kind,boundary,over):
    s=statistics();d=NS(id='M0',can_process_tasks=True,waiting_queue=[None]*boundary)
    r=NS(id='E0',waiting_queue=[None]*boundary)
    state=NS(mobile_devices=[d] if kind=='device' else [],servers=[r] if kind=='server' else [])
    assert bool(s.guard_hits(state)) is over


@pytest.mark.parametrize('count,hit',[(400000,False),(400001,True)])
def test_nonrecording_guard_strict_boundary(count,hit):
    s=statistics();s.legacy_nonrecording_events=count
    assert bool(s.guard_hits(NS(mobile_devices=[],servers=[]))) is hit


@pytest.mark.parametrize('extra,hit',[(0,False),(1,True)])
def test_generated_guard_boundary(extra,hit):
    s=statistics();s.generated_total=500*(s.num_jobs_recorded+s.warmup_jobs)+extra
    assert bool(s.guard_hits(NS(mobile_devices=[],servers=[]))) is hit


def test_guard_order_and_disabled_local_exclusion():
    s=statistics(N=1,W=0);s.legacy_nonrecording_events=400001;s.generated_total=501
    devices=[NS(id='M0',can_process_tasks=False,waiting_queue=[None]*401),
             NS(id='M1',can_process_tasks=True,waiting_queue=[None]*401)]
    hits=s.guard_hits(NS(mobile_devices=devices,servers=[NS(id='E0',waiting_queue=[None]*401)]))
    assert [h['reason_code'] for h in hits]==['JAVA_NONRECORDING_EVENT_LIMIT','JAVA_DEVICE_QUEUE_LIMIT',
        'JAVA_SERVER_QUEUE_LIMIT','JAVA_GENERATED_JOB_LIMIT']
    assert hits[1]['resource_id']=='M1'


@pytest.mark.parametrize('maximum,success',[(3,False),(4,True)])
def test_budget_before_next_poll_and_target_has_precedence(tmp_path,monkeypatch,maximum,success):
    intervals(monkeypatch,[1,100]);ctx=create_dynamic_context(config(tmp_path,max_events=maximum));r=ctx.run()
    assert (r.status=='SUCCEEDED') is success and r.processed_event_count==maximum
    if not success:
        assert r.reason_code=='MAX_EVENTS_EXCEEDED' and r.makespan is None and r.final_clock_time==1
    else:assert r.recorded_workflow_count==1 and r.makespan is not None


def test_N1_W0_unreachable_target_is_not_silently_repaired(tmp_path,monkeypatch):
    intervals(monkeypatch,[1,0]);ctx=create_dynamic_context(config(tmp_path,N=1,W=0));r=ctx.run()
    assert r.status=='FAILED' and r.reason_code=='EVENTS_EXHAUSTED_BEFORE_TARGET'
    assert r.completed_workflow_count==1 and r.recorded_workflow_count==0
    assert r.workflow_records[0]['completion_time'] is not None
    assert r.makespan is None and r.mean_flow_time is None


def test_runtime_domain_failure_preserves_partial_trace_and_original_clock(tmp_path,monkeypatch):
    intervals(monkeypatch,[float(1<<53),0]);ctx=create_dynamic_context(config(tmp_path));r=ctx.run()
    assert r.status=='FAILED' and r.reason_code=='STATE_INVARIANT_VIOLATION'
    assert r.final_clock_time==float(1<<53) and r.events[-1]['error'] and 'precision' in r.reason
    assert r.task_records[0]['plan'] is None and not ctx.engine.state.executions_by_task


@pytest.mark.parametrize('kind',['device','server'])
def test_actual_queue_limit_does_not_clear_queues_or_write_max_clock(tmp_path,monkeypatch,kind):
    intervals(monkeypatch,[1,1000])
    xml='<adag>'+''.join(f'<job id="t{i}"/>' for i in range(402))+'</adag>'
    ctx=create_dynamic_context(config(tmp_path,xml=xml,edges=int(kind=='server'),local=kind=='device',
        target='E0' if kind=='server' else None,trace=False,invariants=False,max_events=2000));r=ctx.run()
    assert r.status=='FAILED'
    assert r.reason_code==('JAVA_DEVICE_QUEUE_LIMIT' if kind=='device' else 'JAVA_SERVER_QUEUE_LIMIT')
    resource=ctx.engine.state.mobile_devices[0] if kind=='device' else ctx.engine.state.servers[0]
    assert len(resource.waiting_queue)==401
    assert r.final_clock_time<2 and ctx.engine.event_queue.has_pending()
    assert r.makespan is None and r.mean_flow_time is None


def test_guard_failure_wins_if_target_reached_on_same_event(tmp_path,monkeypatch):
    intervals(monkeypatch,[1,100]);ctx=create_dynamic_context(config(tmp_path,edges=1,trace=False,invariants=False))
    original=ctx.engine.workflow_completed
    def inject(w):
        original(w)
        # Deliberate component probe, not a naturally reachable queue state.
        ctx.engine.state.servers[0].waiting_queue.extend([None]*401)
    monkeypatch.setattr(ctx.engine,'workflow_completed',inject);r=ctx.run()
    assert r.recorded_workflow_count==1 and r.status=='FAILED' and r.reason_code=='JAVA_SERVER_QUEUE_LIMIT'
    assert r.makespan is None and r.diagnostics['guard_hits'][0]['actual']==401


def test_B_survives_reset_before_first_new_admission(tmp_path,monkeypatch):
    intervals(monkeypatch,[20,10,40,30]);ctx=create_dynamic_context(config(tmp_path,devices=2,N=2,W=2))
    assert ctx.cutoff_release_time==10
    old=ctx.engine;ctx.reset()
    assert ctx.engine.initial_cutoff==10 and ctx.cutoff_release_time==30 and old.statistics.cutoff_release_time==10


def test_statistical_metrics_use_recorded_subset_not_all_completions():
    from fogsim.simulation.dynamic_result import collect_dynamic_result
    s=statistics(N=1,W=1,B=10)
    def w(wid,release,finish):
        return NS(id=wid,owner_device=NS(id='M0'),release_time=release,completion_time=finish,flow_time=finish-release,
            weight=4,dag_type_id=0,template_hash='a'*64,input_record_id=str(wid+1))
    early=w(0,1,20);selected=w(1,10,30);s.recorded_workflows={1:selected};s.generated_total=2
    state=NS(clock_time=30,completed_workflows={0:early,1:selected},workflows_by_id={0:early,1:selected},
        arrived_workflow_count=2,mobile_devices=[],tasks_by_key={})
    engine=NS(state=state,statistics=s,run_status='SUCCEEDED',stop_reason=None,reason_code=None,admission=None,
        trace=NS(tasks={},events=[],decisions=[]),run_index=0,operation='test',public_seed=7,initial_cutoff=0,
        failure_hits=[],initialization_complete=True,initialization_actions=[],environment=None,processed_event_count=0)
    r=collect_dynamic_result(engine)
    assert r.makespan==20 and r.mean_flow_time==20 and r.completed_workflow_count==2 and r.recorded_workflow_count==1


def test_metric_overflow_becomes_FAILED_with_complete_physical_facts(tmp_path,monkeypatch):
    from dataclasses import replace
    from fogsim.experiment_config import RealRange
    from fogsim.randomness.samplers import UniformRealSampler
    intervals(monkeypatch,[1,1,0,0])
    cfg=config(tmp_path,devices=2,N=2,W=1)
    cfg=replace(cfg,source=replace(cfg.source,samplers=replace(cfg.source.samplers,
        workload=RealRange(1e308,1.1e308),processing_rate_device=RealRange(1,1.1))))
    monkeypatch.setattr(UniformRealSampler,'sample',lambda self,rng:0.5*self.lower+0.5*self.upper)
    ctx=create_dynamic_context(cfg);r=ctx.run()
    assert r.status=='FAILED' and r.reason_code=='NUMERIC_DERIVATION_ERROR'
    assert r.recorded_workflow_count==2 and r.completed_workflow_count==2
    assert r.makespan is None and r.mean_flow_time is None and r.final_clock_time==1e308
    assert all(row['finish_time']==1e308 for row in r.task_records if row['finish_time'] is not None)


def test_physical_completion_idempotent_callback_not_reapplied(tmp_path,monkeypatch):
    intervals(monkeypatch,[1,100]);ctx=create_dynamic_context(config(tmp_path));r=ctx.run()
    w=ctx.engine.state.completed_workflows[0]
    assert ctx.engine.state.register_completion(w) is False
    ctx.engine.statistics.check_invariants(ctx.engine.state)
    assert ctx.engine.statistics.completed_by_device['M0']==1 and r.recorded_workflow_count==1
