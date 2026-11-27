from copy import deepcopy
from dataclasses import fields, is_dataclass
import math
import pytest
from fogsim import create_engine, parse_instance
from fogsim.errors import StateError
from fogsim.model.execution import Execution
from fogsim.rules.contexts import StateView, RoutingContext, SequencingContext, graph_fingerprint
from fogsim.rules.baselines import FCFS
from fogsim.rules.selection import choose_route, choose_next, is_preferred, double_compare
from fogsim.simulation.readiness import ready_tasks
from fogsim.simulation.events import JobArrivalEvent, TaskVisitEvent, ProcessStartEvent, ProcessFinishEvent
from conftest import step, two_workflows


def test_initialization_and_identity(engine):
    s = engine.state; a, b = s.workflows_by_id[0].tasks
    assert s.clock_time == 0 and list(s.pending_arrivals) == [0]
    assert not s.active_workflows and not s.completed_workflows and not s.executions_by_task
    assert a.children == [b] and b.parents == [a]
    assert s.tasks_by_key[0, "A"] is a
    for t in (a, b):
        assert not t.completed and not t.dispatched
        assert [o.resource.id for o in t.options] == ["M0", "E0", "C0"]
        for o in t.options:
            assert o.task is t and o.resource is s.resources_by_id[o.resource.id]
            assert o.priority == o.ready_time == 0
    for r in s.resources_by_id.values():
        assert not r.waiting_queue and r.pending_start is None and r.available_time == 0
        assert r.queued_processing_time == r.queued_total_time == r.completed_task_count == 0
    assert s.resources_by_id["M0"].numeric_id == s.resources_by_id["E0"].numeric_id == 0
    assert len(engine.event_queue.pending_events()) == 1


def test_constructors_pure_and_identity_equality(engine):
    s = engine.state; w = s.workflows_by_id[0]; o = w.tasks[0].options[1]
    before = graph_fingerprint(s)
    ex = Execution(o, 2)
    events = [JobArrivalEvent(w), TaskVisitEvent(2, o), ProcessStartEvent(ex), ProcessFinishEvent(ex)]
    assert graph_fingerprint(s) == before
    assert [e.time for e in events] == [0, 2, 2, 6]
    assert all(e.owner is w.owner_device for e in events)
    assert Execution(o, 2) != ex
    with pytest.raises(Exception): ex.start_time = 99


def test_query_is_pure_and_empty_not_done(engine):
    s = engine.state; w = s.workflows_by_id[0]
    assert ready_tasks(w, StateView.from_state(s)) == []
    s.activate_workflow(w)
    before = graph_fingerprint(s)
    assert ready_tasks(w, StateView.from_state(s)) == [w.tasks[0]]
    assert graph_fingerprint(s) == before
    w.tasks[0].dispatched = True
    assert ready_tasks(w, StateView.from_state(s)) == [] and not w.is_done


def test_view_cannot_reach_future_even_at_same_release(raw):
    e = create_engine(parse_instance(two_workflows(raw)))
    step(e)  # only W0 activates; W1 has same release/clock but still future
    view = StateView.from_state(e.state)
    future = e.state.workflows_by_id[1]
    seen = set()
    def walk(x):
        assert x is not future and x is not e.state and x is not e
        if id(x) in seen: return
        seen.add(id(x))
        if is_dataclass(x):
            for f in fields(x): walk(getattr(x, f.name))
        elif isinstance(x, (list, tuple)):
            for item in x: walk(item)
        elif isinstance(x, dict):
            for item in x.values(): walk(item)
    walk(view)
    assert ready_tasks(future, view) == []
    assert not hasattr(view, "pending_arrivals") and not hasattr(view, "workflows_by_id")


@pytest.mark.parametrize("a,b,expected", [(-0.0, 0.0, -1), (0.0, -0.0, 1),
    (math.nan, math.inf, 1), (math.nan, math.nan, 0), (-math.inf, -1, -1), (1, 1, 0)])
def test_double_compare(a, b, expected):
    assert double_compare(a, b) == expected


def test_selection_tie_hierarchy(raw):
    data = two_workflows(raw)
    data["resources"].insert(1, {"id": "M1", "type": "MOBILE"})
    w = data["workflows"][1]; w["owner_device_id"] = "M1"
    w["tasks"][0]["execution_times"]["M1"] = w["tasks"][0]["execution_times"].pop("M0")
    e = create_engine(parse_instance(data)); a = e.state.tasks_by_key[0,"A"].options[0]; b = e.state.tasks_by_key[1,"A"].options[0]
    assert is_preferred(a,b) and not is_preferred(b,a)  # owner IDs
    a.priority = 2
    assert is_preferred(b,a)  # score wins
    b.priority = 2; a.task.workflow.release_time = 5
    assert is_preferred(b,a)  # release before owner
    a.task.workflow.release_time = 0
    b.task.workflow.owner_device.numeric_id = 0
    assert is_preferred(a,b)  # workflow ID
    b.task.workflow.id = 0
    assert not is_preferred(a,b) and not is_preferred(b,a)
    a.priority = -0.0; b.priority = 0.0
    assert is_preferred(a,b)


def test_fcfs_scores_overwrite_and_queue_selection_keeps_members(engine):
    s=engine.state; w=s.workflows_by_id[0]; s.activate_workflow(w)
    s.clock_time=20; options=w.tasks[0].options
    s.resources_by_id["M0"].available_time=10
    context=RoutingContext(w.tasks[0],tuple(options),StateView.from_state(s))
    selected=choose_route(context,FCFS(),engine.trace)
    assert selected is options[1] and [o.priority for o in options] == [10,0,0]
    historical=deepcopy(engine.trace.decisions)
    selected.task.dispatched=True; selected.ready_time=20
    selected.resource.enqueue(selected)
    qctx=SequencingContext(selected.resource,(selected,),StateView.from_state(s))
    assert choose_next(qctx,FCFS()) is selected
    assert selected.priority==0 and selected.resource.waiting_queue==[selected]
    assert selected.resource.queued_total_time==6
    selected.priority=999
    assert engine.trace.decisions==historical


def test_empty_selection_and_mutating_rule(engine):
    s=engine.state; w=s.workflows_by_id[0]; s.activate_workflow(w)
    with pytest.raises(StateError,match="empty"):
        choose_route(RoutingContext(w.tasks[0],(),StateView.from_state(s)),FCFS())
    class BadRule:
        def priority(self, option, context):
            option.resource.available_time=50
            return 0
    with pytest.raises(StateError,match="mutated"):
        choose_route(RoutingContext(w.tasks[0],tuple(w.tasks[0].options),StateView.from_state(s)),BadRule())


def test_first_score_then_remaining_comparisons_only(engine,monkeypatch):
    from fogsim.rules import selection
    s=engine.state;w=s.workflows_by_id[0];s.activate_workflow(w)
    calls=[];original=selection.is_preferred
    class ObservedRule:
        def priority(self,option,context):
            calls.append(("score",option.resource.id))
            return 0
    def compare(a,b):
        calls.append(("compare",a.resource.id,b.resource.id))
        return original(a,b)
    monkeypatch.setattr(selection,"is_preferred",compare)
    choose_route(RoutingContext(w.tasks[0],tuple(w.tasks[0].options),StateView.from_state(s)),ObservedRule())
    assert calls==[("score","M0"),("score","E0"),("compare","E0","M0"),
                   ("score","C0"),("compare","C0","M0")]


def test_two_complete_routing_rounds_and_no_early_dispatch(raw):
    w=raw["workflows"][0]
    c=deepcopy(w["tasks"][1]);c["id"]="C";w["tasks"].append(c)
    w["dependencies"].append(["A","C"])
    e=create_engine(parse_instance(raw))
    calls=[]
    class Spy:
        def priority(self, option, context):
            if option.resource.id=="M0":
                calls.append((option.task.id,context.round_number,
                              tuple(t.dispatched for t in option.task.workflow.tasks[1:])))
            return 0 if option.resource.id=="E0" else 1
    e.routing_rule=Spy()
    for _ in range(4): step(e)
    assert [(t,r) for t,r,_ in calls]==[("A",1),("B",1),("C",1),("B",2),("C",2)]
    assert all(flags==(False,False) for _,_,flags in calls)
    assert all(t.dispatched for t in e.state.workflows_by_id[0].tasks)
    assert all(o.ready_time==0 for t in e.state.workflows_by_id[0].tasks[1:] for o in t.options)
