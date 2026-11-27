from dataclasses import replace
from itertools import repeat
import math
import pytest
from fogsim import create_dynamic_context
from fogsim.errors import StateError, NumericDerivationError
from fogsim.input_validation import INT32_MAX
from fogsim.instances.generated import GenerationCause
from fogsim.simulation.engine import EventContext
from fogsim.simulation.events import JobArrivalEvent
from fogsim.rules.contexts import StateView, graph_fingerprint
from dynamic_helpers import config, intervals, DIAMOND, CHAIN


def test_two_workflows_share_servers_but_no_tasks_or_edge_storage(tmp_path,monkeypatch):
    intervals(monkeypatch,repeat(10))
    ctx=create_dynamic_context(config(tmp_path,devices=2,edges=1,clouds=1,xml=DIAMOND))
    state=ctx.engine.state;w0,w1=state.workflows_by_id.values()
    assert w0.id==0 and w1.id==1 and w0.owner_device is state.mobile_devices[0]
    assert [t.id for t in w0.tasks]==[t.id for t in w1.tasks]
    assert all(a is not b for a,b in zip(w0.tasks,w1.tasks))
    for a,b in zip(w0.tasks,w1.tasks):
        assert a.options[1].resource is b.options[1].resource is state.servers[0]
        assert a.options[0].resource is w0.owner_device and b.options[0].resource is w1.owner_device
        assert a.output_data_by_child is not b.output_data_by_child
    immutable=ctx.input_archive
    w0.tasks[0].output_data_by_child.clear()
    assert immutable.candidates[0].workflow_input.edges
    assert ctx.input_archive==immutable
    assert all(w.input_record_id is not None for w in (w0,w1))


def test_all_entry_dispatches_precede_one_generation_and_finish_never_generates(tmp_path,monkeypatch):
    xml='<adag><job id="x"/><job id="y"/></adag>'
    intervals(monkeypatch,[1,100])
    ctx=create_dynamic_context(config(tmp_path,xml=xml))
    result=ctx.run()
    arrival=result.events[0]
    assert arrival['type']=='JobArrivalEvent'
    assert [a['kind'] for a in arrival['actions']]==['DECISION','EMIT','DECISION','EMIT','EMIT']
    assert [e['type'] for e in arrival['emitted']]==['TaskVisitEvent','TaskVisitEvent','JobArrivalEvent']
    assert len(ctx.input_archive.generation_attempts)==2
    after=ctx.input_archive.generation_attempts[1].cause
    assert (after.phase,after.causing_workflow_id,after.event_sequence)==('after_arrival',0,1)
    assert all(not any(e['type']=='JobArrivalEvent' for e in row['emitted'])
               for row in result.events if row['type']=='ProcessFinishEvent')


@pytest.mark.parametrize('values,accepted,rejected', [([0,0],0,2),([0,10,100],2,1),([10,0,100],2,1)])
def test_rejection_does_not_take_id_or_interrupt_other_device(tmp_path,monkeypatch,values,accepted,rejected):
    calls=intervals(monkeypatch,values)
    ctx=create_dynamic_context(config(tmp_path,devices=2,edges=1))
    before=ctx.inputs.snapshot()
    result=ctx.run()
    archive=ctx.input_archive
    assert result.generated_workflow_count==accepted
    assert result.source_summary['rejected_count']==rejected
    assert [a.workflow_id for a in archive.admissions]==list(range(accepted))
    assert [c.workflow_input.candidate_id for c in archive.candidates][:2]==([0,0] if values[0]==0 else [0,1])
    assert len(calls)==len(archive.generation_attempts)
    if not accepted:
        assert result.reason_code=='EVENTS_EXHAUSTED_BEFORE_TARGET' and result.processed_event_count==0
        assert before==ctx.inputs.snapshot()
    else:
        assert result.status=='SUCCEEDED' and before!=ctx.inputs.snapshot()
    assert result.makespan is None if not accepted else result.makespan is not None


def test_zero_interval_still_consumes_full_generation_and_leaves_B_unchanged(tmp_path,monkeypatch):
    intervals(monkeypatch,[0,10])
    from fogsim.randomness.samplers import UniformRealSampler
    calls=[];original=UniformRealSampler.sample
    def sample(self,rng):calls.append((self,rng));return original(self,rng)
    monkeypatch.setattr(UniformRealSampler,'sample',sample)
    ctx=create_dynamic_context(config(tmp_path,xml=CHAIN,devices=2))
    # two rates, then two tasks' workload/data and one edge for each device.
    assert len(calls)==2+2*(2*2+1)
    assert all(rng is ctx.inputs.rng for _,rng in calls)
    stats=ctx.engine.statistics
    assert stats.generated_total==1 and stats.cutoff_release_time==10
    assert len(ctx.input_archive.candidates)==2 and len(ctx.input_archive.candidates[0].workflow_input.edges)==1
    assert len(ctx.engine.event_queue.pending_events())==1


def test_positive_interval_rounds_to_current_clock_without_redraw(tmp_path,monkeypatch):
    intervals(monkeypatch,[float(1<<53),1])
    cfg=config(tmp_path,max_events=1)
    ctx=create_dynamic_context(cfg)
    r=ctx.run()
    assert r.reason_code=='MAX_EVENTS_EXCEEDED'
    assert r.generated_workflow_count==1 and r.source_summary['rejected_count']==1
    candidate=ctx.input_archive.candidates[1].workflow_input
    assert candidate.inter_release_time==1 and candidate.release_time==float(1<<53)
    assert len(ctx.engine.event_queue.pending_events())==1 # Visit, no new Arrival


def test_normal_stop_merges_once_but_does_not_poll_same_time_events(tmp_path,monkeypatch):
    # Simultaneous workflows complete on separate local devices. The first Finish
    # reaches N; the other same-time Finish remains in the global heap.
    intervals(monkeypatch,[1,1,100,100])
    from fogsim.randomness.samplers import UniformRealSampler
    monkeypatch.setattr(UniformRealSampler,'sample',lambda self,rng: (self.lower+self.upper)*0.5)
    ctx=create_dynamic_context(config(tmp_path,devices=2))
    r=ctx.run()
    assert r.status=='SUCCEEDED' and r.completed_workflow_count==1
    pending=ctx.engine.event_queue.pending_events()
    assert any(type(e).__name__=='ProcessFinishEvent' and e.time==r.final_clock_time for e in pending)
    assert all(not h for h in ctx.engine.event_queue.staging_heaps.values())
    assert ctx.engine.event_queue.global_heap
    assert r.generated_workflow_count==4 and r.recorded_workflow_count==1


def test_generation_continues_beyond_N_plus_W(tmp_path,monkeypatch):
    intervals(monkeypatch,repeat(0.001))
    ctx=create_dynamic_context(config(tmp_path,N=1,W=1,max_events=10000,trace=False,invariants=False))
    result=ctx.run()
    assert result.status=='SUCCEEDED'
    assert result.generated_workflow_count>2
    assert result.source_summary['attempt_count']==result.arrived_workflow_count+1


def test_trace_disabled_preserves_facts_and_same_schedule(tmp_path,monkeypatch):
    cfg=config(tmp_path,devices=2,edges=1,xml=DIAMOND,N=2,W=2)
    enabled=create_dynamic_context(cfg);a=enabled.run()
    disabled=create_dynamic_context(replace(cfg,run=replace(cfg.run,trace_enabled=False)));b=disabled.run()
    assert not b.events and not b.decisions
    assert b.task_records==a.task_records and b.workflow_records==a.workflow_records
    assert (a.status,a.final_clock_time,a.makespan,a.mean_flow_time)==(b.status,b.final_clock_time,b.makespan,b.mean_flow_time)
    assert enabled.input_archive==disabled.input_archive
    assert enabled.engine.rng_final==disabled.engine.rng_final


def test_rule_view_has_no_future_or_archive_backreferences(tmp_path,monkeypatch):
    intervals(monkeypatch,[10])
    ctx=create_dynamic_context(config(tmp_path,xml=CHAIN))
    view=StateView.from_state(ctx.engine.state)
    assert not view.active_workflows and not view.completed_workflows
    assert not hasattr(view,'context') and not hasattr(view,'input_archive')
    from dataclasses import is_dataclass, fields
    from fogsim.simulation.context import SimulationContext
    from fogsim.simulation.engine import Engine
    from fogsim.instances.generated import InputArchive
    seen=set()
    def visit(obj):
        if obj is None or isinstance(obj,(int,float,str,bool)) or id(obj) in seen:return
        seen.add(id(obj))
        assert not isinstance(obj,(SimulationContext,Engine,InputArchive))
        if is_dataclass(obj):
            for f in fields(obj):visit(getattr(obj,f.name))
        elif isinstance(obj,dict):
            for k,v in obj.items():visit(k);visit(v)
        elif isinstance(obj,(tuple,list)):
            for x in obj:visit(x)
    visit(view)
    assert id(ctx.engine.state.workflows_by_id[0]) not in seen
    w=ctx.engine.state.workflows_by_id[0]
    assert not hasattr(w,'context') and not hasattr(w,'archive')
    assert not hasattr(w.tasks[0],'context')


def test_capacity_error_before_any_graph_commit(tmp_path,monkeypatch):
    intervals(monkeypatch,[0,1])
    ctx=create_dynamic_context(config(tmp_path))
    stats=ctx.engine.statistics;stats.generated_total=INT32_MAX
    ctx.engine.admission.source.generate # source accepts the proposed MAX; commit must not wrap.
    with pytest.raises(NumericDerivationError):
        ctx.engine.admission.attempt(GenerationCause('initialize','M0',0),EventContext(ctx.engine,ctx.engine.state.mobile_devices[0]))
    assert not ctx.engine.state.workflows_by_id and stats.generated_total==INT32_MAX
    assert len(ctx.engine.admission._attempts)==1


def test_runtime_source_unknown_identity_is_explicit_failure(tmp_path,monkeypatch):
    intervals(monkeypatch,[1,1])
    ctx=create_dynamic_context(config(tmp_path))
    source=ctx.engine.admission.source;original=source.generate
    def wrong(cause,*,candidate_id):return replace(original(cause,candidate_id=candidate_id),candidate_id=99)
    monkeypatch.setattr(source,'generate',wrong)
    r=ctx.run()
    assert r.status=='FAILED' and r.reason_code=='STATE_INVARIANT_VIOLATION'
    assert r.source_summary['incomplete_attempt'] and r.generated_workflow_count==1


def test_cross_owner_server_queue_continuation_uses_current_producer(tmp_path,monkeypatch):
    intervals(monkeypatch,[1,1,100,100])
    ctx=create_dynamic_context(config(tmp_path,devices=2,edges=1,local=False,target='E0',N=2,W=2))
    r=ctx.run()
    transitions=[e for row in r.events for e in row['emitted'] if e['type']=='ProcessStartEvent' and e['owner']!=e['staging_device']]
    assert transitions
    assert {transitions[0]['owner'],transitions[0]['staging_device']}=={'M0','M1'}
    for row in r.events:
        for emitted in row['emitted']:
            if emitted in transitions:
                assert row['type']=='ProcessFinishEvent' and emitted['staging_device']==row['owner']
