from copy import deepcopy
import pytest
from fogsim import parse_instance, create_engine, RunConfig
from fogsim.errors import StateError
from fogsim.model.task import TaskOption
from fogsim.model.execution import Execution
from fogsim.simulation.engine import EventContext
from fogsim.simulation.events import ProcessStartEvent, ProcessFinishEvent
from conftest import step, two_workflows


@pytest.mark.parametrize("rid", ["M0", "E0", "C0"])
def test_cache_order_identity_and_resource_difference(raw, rid):
    w=raw["workflows"][0]
    c=deepcopy(w["tasks"][1]); c["id"]="C";w["tasks"].append(c)
    e=create_engine(parse_instance(raw));r=e.state.resources_by_id[rid]
    options=[]
    for task,pt in zip(e.state.workflows_by_id[0].tasks,(0.1,0.2,0.3)):
        task.dispatched=True
        o=next(o for o in task.options if o.resource is r);o.processing_time=pt
        o.upload_time=o.download_time=0
        r.enqueue(o);options.append(o)
    assert r.queued_processing_time.hex()==(0.6000000000000001).hex()
    with pytest.raises(StateError):r.enqueue(options[0])
    fake=TaskOption(options[0].task,r,0.1,0,0)
    with pytest.raises(StateError):r.remove_waiting(fake)
    r.remove_waiting(options[1])
    assert r.waiting_queue==[options[0],options[2]]
    r.remove_waiting(options[0]);r.remove_waiting(options[2])
    # Original Java method oracle: +.1,+.2,+.3,-.2,-.1,-.3 => binary64 0x3c90000000000000.
    expected=5.551115123125783e-17 if rid=="M0" else 0.0
    assert r.queued_processing_time==r.waiting_processing_time==expected
    assert r.queued_total_time==r.waiting_total_time==expected


def test_integer_cache_includes_upload(engine):
    w=engine.state.workflows_by_id[0];a,b=[t.options[1] for t in w.tasks];r=a.resource
    for o in (a,b):o.task.dispatched=True;r.enqueue(o)
    assert r.queued_processing_time==7 and r.queued_total_time==13
    r.remove_waiting(a)
    assert r.waiting_queue==[b] and r.queued_processing_time==4 and r.queued_total_time==7
    r.remove_waiting(b)
    assert r.queued_processing_time==r.queued_total_time==0


def test_pending_reservation_before_start_and_queue_continuation(raw):
    e=create_engine(parse_instance(two_workflows(raw)),RunConfig(routing_kind="fixed_resource",fixed_resource_id="E0"))
    step(e);step(e)  # both arrivals, both uploading
    s=e.state;r=s.resources_by_id["E0"];s.clock_time=2
    a=s.tasks_by_key[0,"A"].options[1];b=s.tasks_by_key[1,"A"].options[1]
    ctx=EventContext(e,s.mobile_devices[0]);ctx.visit(a);ex=r.pending_start
    assert r.available_time==0 and ex is s.executions_by_task[a.task.key]
    assert not a.task.completed and not a.task.workflow.completed_executions
    ctx.visit(b)
    assert r.pending_start is ex and r.waiting_queue==[b] and b.task.key not in s.executions_by_task
    with pytest.raises(StateError):ctx.reserve_start(b,2)
    with pytest.raises(StateError):ctx.visit(a)
    ctx.begin_execution(ex)
    assert r.pending_start is None and r.available_time==6
    with pytest.raises(StateError):ctx.begin_execution(ex)
    s.clock_time=6
    ProcessFinishEvent(ex).trigger(ctx)
    next_ex=r.pending_start
    assert next_ex.task is b.task and next_ex.start_time==6 and r.available_time==6
    assert not r.waiting_queue and r.queued_total_time==0
    assert e.trace.decisions[-1]["kind"]=="SEQUENCING"
    assert e.trace.decisions[-1]["resource_state"][1]["queue"]==[[1,"A","E0"]]
    before=(len(a.task.workflow.completed_executions),r.completed_task_count)
    with pytest.raises(StateError):ctx.finish_execution(ex)
    assert (len(a.task.workflow.completed_executions),r.completed_task_count)==before
    assert s.register_completion(a.task.workflow) is False


def test_mismatch_reservation_and_foreign_objects(engine, spec):
    step(engine);step(engine)
    s=engine.state;r=s.resources_by_id["E0"];ex=r.pending_start;ctx=EventContext(engine,s.mobile_devices[0])
    wrong=Execution(ex.option,2)
    with pytest.raises(StateError):ctx.begin_execution(wrong)
    assert r.pending_start is ex
    foreign=create_engine(spec).state.tasks_by_key[0,"A"].options[1]
    with pytest.raises(StateError):ctx.dispatch(foreign)
    with pytest.raises(StateError):ctx.dispatch(ex.option)
    with pytest.raises(StateError):ctx.finish_execution(ex)


@pytest.mark.parametrize("already_started", [False,True])
def test_old_finish_does_not_clear_new_reservation_or_availability(raw,already_started):
    e=create_engine(parse_instance(two_workflows(raw)),RunConfig(routing_kind="fixed_resource",fixed_resource_id="E0"))
    step(e);step(e)
    s=e.state;r=s.resources_by_id["E0"];ctx=EventContext(e,s.mobile_devices[0])
    a=s.tasks_by_key[0,"A"].options[1];b=s.tasks_by_key[1,"A"].options[1]
    s.clock_time=2;ctx.visit(a);old=r.pending_start;ctx.begin_execution(old)
    s.clock_time=6;ctx.visit(b);new=r.pending_start
    if already_started:ctx.begin_execution(new)
    availability=r.available_time;pending=r.pending_start
    ProcessFinishEvent(old).trigger(ctx)
    assert r.available_time==availability and r.pending_start is pending
    assert new.start_time==old.finish_time


def test_registration_inconsistent_flag(engine):
    engine.run();w=engine.state.workflows_by_id[0]
    assert engine.state.register_completion(w) is False
    w.completion_registered=False
    with pytest.raises(StateError):engine.state.register_completion(w)


def test_registration_inconsistent_records(engine):
    engine.run();w=engine.state.workflows_by_id[0]
    w.completed_executions.clear()
    with pytest.raises(StateError,match="inconsistent"):engine.state.register_completion(w)


def test_finish_dequeues_before_successor_routing(raw):
    data=deepcopy(raw);other=deepcopy(raw["workflows"][0]);other["id"]=1
    other["tasks"]=other["tasks"][:1];other["dependencies"]=[]
    data["workflows"].append(other)
    e=create_engine(parse_instance(data),RunConfig(routing_kind="fixed_resource",fixed_resource_id="E0"))
    for _ in range(6):step(e)  # JA0,JA1,TV0,PS0,TV1,PF0
    decisions=e.trace.decisions
    assert [d["kind"] for d in decisions[-3:]]==["SEQUENCING","ROUTING","ROUTING"]
    assert decisions[-3]["resource_state"][1]["queue"]==[[1,"A","E0"]]
    for d in decisions[-2:]:
        assert d["resource_state"][1]["queue"]==[]
        assert d["resource_state"][1]["queued_total_time"]==0
        assert d["resource_state"][1]["available_time"]==6
    assert e.state.resources_by_id["E0"].pending_start.task.key==(1,"A")


def test_queue_overflow_rejected_before_commit(engine):
    a=engine.state.tasks_by_key[0,"A"].options[1];a.task.dispatched=True
    a.processing_time=a.upload_time=1e308
    with pytest.raises(StateError,match="overflow"):a.resource.enqueue(a)
    assert not a.resource.waiting_queue and a.resource.queued_total_time==0
