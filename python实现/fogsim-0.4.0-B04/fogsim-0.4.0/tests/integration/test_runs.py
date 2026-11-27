from copy import deepcopy
from dataclasses import replace
import pytest
from fogsim import load_fixed_instance, create_engine, simulate, RunConfig
from fogsim.errors import EngineUsageError
from fogsim.simulation.event_queue import EventQueue
from conftest import ROOT


@pytest.mark.parametrize("case,target,makespan,clock",[
    ("single_local","M0",3,3),("single_local_release5","M0",3,8),
    ("chain_remote","E0",13,13),("chain_remote",None,17,17)])
def test_hand_calculated_full_runs(case,target,makespan,clock):
    cfg=RunConfig(routing_kind="fixed_resource",fixed_resource_id=target) if target else RunConfig()
    result=simulate(load_fixed_instance(ROOT/f"data/cases/{case}.json"),cfg)
    assert result.status=="SUCCEEDED" and result.reason is None
    assert result.makespan==makespan and result.final_clock_time==clock
    assert result.completed_workflow_count==1
    if case.startswith("single"):
        assert result.processed_event_count==4
        row=result.task_records[0];release=0 if clock==3 else 5
        assert [row[k] for k in ("dispatch_time","arrival_time","start_time","compute_finish_time","finish_time")]==[release,release,release,clock,clock]
    else:
        assert result.processed_event_count==7 and len(result.decisions)==3
        expected=[[0,2,2,5,6],[6,7,7,11,13]] if target else [[0,0,0,10,10],[10,11,11,15,17]]
        assert [[r[k] for k in ("dispatch_time","arrival_time","start_time","compute_finish_time","finish_time")] for r in result.task_records]==expected
        assert [r["resource_id"] for r in result.task_records]==(["E0","E0"] if target else ["M0","E0"])
        assert [d["round"] for d in result.decisions]==[1,1,2]
    assert all(e["error"] is None for e in result.events)


def test_chain_stable_boundaries(engine):
    result=engine.run();ev=result.events
    assert [e["time"] for e in ev]==[0,2,2,6,7,7,13]
    assert [e["type"] for e in ev]==["JobArrivalEvent","TaskVisitEvent","ProcessStartEvent","ProcessFinishEvent","TaskVisitEvent","ProcessStartEvent","ProcessFinishEvent"]
    assert ev[0]["after"]["executions"]==[]
    e0=lambda index:next(r for r in ev[index]["after"]["resources"] if r["id"]=="E0")
    assert e0(1)["pending_start"]==[0,"A"] and e0(1)["available_time"]==0
    assert e0(2)["pending_start"] is None and e0(2)["available_time"]==6
    assert not ev[2]["after"]["tasks"][0]["completed"]
    assert all(o["ready_time"]==0 for o in ev[3]["after"]["tasks"][1]["options"])
    assert e0(4)["pending_start"]==[0,"B"] and e0(4)["available_time"]==6
    assert e0(6)["completed_task_count"]==2
    s=engine.state;w=s.workflows_by_id[0]
    assert w.completed_executions==[s.executions_by_task[0,"A"],s.executions_by_task[0,"B"]]
    assert len(w.tasks)==2 and w.completion_registered


def test_log_off_and_fresh_rerun(spec):
    cfg=RunConfig(routing_kind="fixed_resource",fixed_resource_id="E0")
    first=create_engine(spec,cfg);second=create_engine(spec,cfg)
    result1=first.run();snapshot=deepcopy(result1.to_dict())
    assert second.run().to_dict()==snapshot and result1.to_dict()==snapshot
    for key,t in first.state.tasks_by_key.items():
        assert second.state.tasks_by_key[key] is not t
    for rid,r in first.state.resources_by_id.items():
        assert second.state.resources_by_id[rid] is not r
    off=simulate(spec,replace(cfg,trace_enabled=False))
    assert off.task_records==result1.task_records and off.workflow_records==result1.workflow_records
    assert off.makespan==result1.makespan and off.processed_event_count==result1.processed_event_count
    assert off.events==off.decisions==[]
    with pytest.raises(EngineUsageError):first.run()
    fresh=create_engine(spec,cfg)
    assert fresh.processed_event_count==0 and fresh.run_status=="READY"
    assert all(not t.dispatched and not t.completed and all(o.priority==o.ready_time==0 for o in t.options) for t in fresh.state.tasks_by_key.values())
    assert fresh.state.clock_time==0 and fresh.state.executions_by_task=={}


@pytest.mark.parametrize("limit,has_start",[(2,False),(3,True)])
def test_failure_preserves_plan_vs_actual(spec,limit,has_start):
    result=simulate(spec,RunConfig(routing_kind="fixed_resource",fixed_resource_id="E0",max_events=limit))
    assert result.status=="FAILED" and "limit" in result.reason and result.makespan is None
    row=result.task_records[0]
    assert row["plan"]=={"start_time":2,"compute_finish_time":5,"finish_time":6}
    assert row["start_time"]==(2 if has_start else None) and row["finish_time"] is None
    assert result.workflow_records[0]["completion_time"] is None


def test_event_exhaustion(engine):
    engine.event_queue=EventQueue(engine.state.mobile_devices)
    result=engine.run()
    assert result.status=="FAILED" and "exhausted" in result.reason and result.makespan is None


def test_duplicate_arrival_fails_with_trace(engine):
    from fogsim.simulation.events import JobArrivalEvent
    w=engine.state.workflows_by_id[0]
    engine.event_queue.stage(JobArrivalEvent(w),w.owner_device)
    result=engine.run()
    assert result.status=="FAILED" and "arrival" in result.reason and result.makespan is None
    assert result.events[-1]["error"]==result.reason


def test_unexpected_rule_bug_propagates(engine):
    class Bug:
        def priority(self,*args):raise TypeError("programming bug")
    engine.routing_rule=Bug()
    with pytest.raises(TypeError,match="programming bug"):engine.run()
    assert engine.run_status=="FAILED"


def test_derived_overflow(raw):
    from fogsim import parse_instance
    w=raw["workflows"][0];w["release_time"]=1e308
    w["tasks"][0]["execution_times"]["E0"]["upload_time"]=1e308
    result=simulate(parse_instance(raw),RunConfig(routing_kind="fixed_resource",fixed_resource_id="E0"))
    assert result.status=="FAILED" and "overflow" in result.reason and result.makespan is None


def test_cli_roundtrip(tmp_path):
    from fogsim.cli import main
    import json
    target=tmp_path/"result.json"
    assert main(["--config",str(ROOT/"configs/chain_fcfs.json"),"--repeat","2","--output",str(target)])==0
    output=json.loads(target.read_text())
    assert output["identical"] and output["runs"][0]["makespan"]==17


def test_logging_switch_preserves_actual_pop_sequence(spec):
    from fogsim.simulation.trace import event_snapshot
    sequences=[]
    for enabled in (True,False):
        e=create_engine(spec,RunConfig(trace_enabled=enabled))
        sequence=[];original=e.event_queue.pop_next
        def observed_pop():
            event=original()
            if event is not None:sequence.append(event_snapshot(event))
            return event
        e.event_queue.pop_next=observed_pop
        assert e.run().status=="SUCCEEDED"
        sequences.append(sequence)
    assert sequences[0]==sequences[1]


def test_execution_time_overflow_fails(raw):
    from fogsim import parse_instance
    w=raw["workflows"][0];w["release_time"]=1e308
    w["tasks"][0]["execution_times"]["M0"]["processing_time"]=1e308
    result=simulate(parse_instance(raw),RunConfig())
    assert result.status=="FAILED" and "execution time" in result.reason
    assert result.task_records[0]["plan"] is None and result.task_records[0]["finish_time"] is None
