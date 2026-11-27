from copy import deepcopy
from dataclasses import asdict, replace
from itertools import repeat
import json
import pytest

from fogsim import (RunConfig, create_engine, load_fixed_instance, parse_instance,
                    create_dynamic_context)
from fogsim.errors import StateError, EngineUsageError, InputError
from fogsim.experiment_config import RuleConfig
from fogsim.gp import evaluator
from fogsim.rules.gp import GPRule
from fogsim.rules.specs import RuleSpec
from fogsim.rules.factory import prepare_rules
from fogsim.rules.contexts import RoutingContext, StateView
from fogsim.simulation.engine import EventContext
from fogsim.simulation.events import ProcessFinishEvent
from conftest import ROOT
from .helpers import prepared, gp_dynamic, dynamic_config


def fixed_config(route, sequence, trace=True):
    return RunConfig(route, "E0" if route=="fixed_resource" else None, sequence, trace,
        routing_expression="(+ PT (+ UT DT))" if route=="gp" else None,
        sequencing_expression="(- 0 PT)" if sequence=="gp" else None)


@pytest.mark.parametrize("route", ["fcfs", "fixed_resource", "gp"])
@pytest.mark.parametrize("sequence", ["fcfs", "gp"])
def test_fixed_diamond_all_six_combinations_keep_two_round_order(route, sequence, evidence_b03):
    spec=load_fixed_instance(ROOT/"data/cases/v2_diamond.json")
    engine=create_engine(spec, fixed_config(route,sequence)); result=engine.run()
    assert result.status=="SUCCEEDED" and result.completed_workflow_count==1
    decisions=[d for d in result.decisions if d["kind"]=="ROUTING"]
    assert [(d["candidates"][0]["option"][1],d["round"]) for d in decisions] == [
        ("A",1),("B",1),("C",1),("B",2),("C",2),("D",1),("D",2)]
    assert (engine.routing_rule is engine.prepared_rules.routing and
            engine.sequencing_rule is engine.prepared_rules.sequencing)
    if route=="gp" or sequence=="gp":
        assert result.to_dict()["schema_version"] == 2
    else: assert result.to_dict()["status"]=="SUCCEEDED"
    evidence_b03("fixed-six",dict(routing=route,sequencing=sequence,
        initial=spec.to_dict(),result=asdict(result),final=engine.trace.events[-1]["after"]))


@pytest.mark.parametrize("route", ["fcfs", "fixed_resource", "gp"])
@pytest.mark.parametrize("sequence", ["fcfs", "gp"])
def test_dynamic_all_six_slots_with_actual_events(tmp_path, route, sequence, evidence_b03):
    cfg=dynamic_config(tmp_path,devices=2,edges=1,clouds=1,N=1,W=1)
    cfg=replace(cfg,schema_version=2,run=replace(cfg.run,
        routing_rule=RuleConfig(route,"E0" if route=="fixed_resource" else None,
            "PT" if route=="gp" else None),
        sequencing_rule=RuleConfig(sequence,expression="(- 0 PT)" if sequence=="gp" else None)))
    context=create_dynamic_context(cfg); engine=context.engine
    assert engine.routing_rule is engine.prepared_rules.routing
    assert engine.sequencing_rule is engine.prepared_rules.sequencing
    result=context.run()
    assert result.status=="SUCCEEDED" and result.recorded_workflow_count==1
    assert result.output_profile=="v2"
    evidence_b03("dynamic-six",dict(routing=route,sequencing=sequence,events=result.processed_event_count,
        decisions=result.decisions,rng_before=engine.rng_start.fingerprint,rng_final=engine.rng_final.fingerprint))


def shared_spec():
    resources=[dict(id="M0",type="MOBILE"),dict(id="M1",type="MOBILE"),dict(id="E0",type="EDGE")]
    workflows=[]
    for i,pt in enumerate((10,2,4)):
        owner="M0" if i<2 else "M1"
        workflows.append(dict(id=i,owner_device_id=owner,release_time=i,tasks=[dict(id="A",
            execution_times={owner:dict(processing_time=50,upload_time=0,download_time=0),
                "E0":dict(processing_time=pt,upload_time=1,download_time=1)})],dependencies=[]))
    return parse_instance(dict(time_unit="s",resources=resources,workflows=workflows))


@pytest.mark.parametrize("trace", [True,False])
def test_real_shared_queue_gp_selects_second_while_queued(trace, monkeypatch, evidence_b03):
    cfg=RunConfig("gp",sequencing_kind="gp",trace_enabled=trace,
                  routing_expression="PT",sequencing_expression="(- 0 PT)")
    engine=create_engine(shared_spec(),cfg)
    observations=[]; original=evaluator.read_feature
    def observe(feature,option,ctx):
        if ctx.kind.value=="SEQUENCING":
            observations.append(dict(clock=ctx.view.clock_time,option=option.key,
                queue=[o.key for o in option.resource.waiting_queue],
                mrt=option.resource.available_time,pending=option.resource.pending_start))
        return original(feature,option,ctx)
    monkeypatch.setattr(evaluator,"read_feature",observe)
    result=engine.run()
    assert result.status=="SUCCEEDED"
    assert [r["option"] for r in observations[:2]]==[(1,"A","E0"),(2,"A","E0")]
    assert all(len(r["queue"])==2 and r["clock"]==12. for r in observations[:2])
    assert all(r["mrt"]==12. and r["pending"] is None for r in observations[:2])
    records={r["workflow_id"]:r for r in result.task_records}
    assert records[2]["start_time"]==12. and records[1]["start_time"]==17.
    if trace:
        decision=next(d for d in result.decisions if d["kind"]=="SEQUENCING")
        assert decision["selected"]==[2,"A","E0"]
        assert [c["priority"] for c in decision["candidates"]]==[-2.,-4.]
    else: assert result.events==result.decisions==[]
    evidence_b03("shared-fixed",dict(trace=trace,observations=observations,result=asdict(result)))


def test_fresh_context_finish_ntr_successor_twt_and_unstarted_mrt(monkeypatch,evidence_b03):
    cfg=RunConfig("gp",sequencing_kind="gp",routing_expression="(+ NTR (+ TWT MRT))",
                  sequencing_expression="(- 0 PT)")
    spec=load_fixed_instance(ROOT/"data/cases/chain_remote.json")
    engine=create_engine(spec,cfg); observations=[]
    original=GPRule.priority
    def observe(self,option,ctx):
        observations.append(dict(context=ctx,task=option.task.id,round=ctx.round_number,
            clock=ctx.view.clock_time,mrt=option.resource.available_time,
            twt=ctx.view.clock_time-option.ready_time,ntr=option.task.workflow.task_count-
            option.task.workflow.completed_task_count,pending=option.resource.pending_start is not None))
        return original(self,option,ctx)
    monkeypatch.setattr(GPRule,"priority",observe)
    result=engine.run(); assert result.status=="SUCCEEDED"
    groups=[]
    for row in observations:
        if not groups or groups[-1] is not row["context"]: groups.append(row["context"])
    assert len(groups)==3 and len({id(c) for c in groups})==3
    assert len({id(c.view) for c in groups})==3
    assert all(r["twt"]==0. and r["ntr"]==2 for r in observations if r["task"]=="A")
    assert all(r["twt"]==r["clock"] and r["ntr"]==1 for r in observations if r["task"]=="B")
    old=groups[0]; current=StateView.from_state(engine.state)
    assert old.view.clock_time==0. and current.clock_time>0.
    evidence_b03("context-lifecycle",[dict((k,v) for k,v in r.items() if k!="context") for r in observations])


def test_dynamic_real_multi_candidate_gp_nonfirst_and_cleanup(tmp_path,monkeypatch,evidence_b03):
    from fogsim.randomness.samplers import ExponentialSampler
    from fogsim.experiment_config import RealRange
    cfg=gp_dynamic(tmp_path,devices=2,edges=1,local=False,N=3,W=1,max_events=500,
                   sequence="TWT")
    cfg=replace(cfg,source=replace(cfg.source,samplers=replace(cfg.source.samplers,
        workload=RealRange(100,101))))
    original=ExponentialSampler.sample
    calls=[]
    def sample(self,rng):
        original(self,rng); calls.append(True)
        # A finite four-arrival burst, then enough space to drain it. Sampling
        # still consumes its real draw; only this business fixture's times vary.
        return .1 if len(calls)<=4 else 1000.
    monkeypatch.setattr(ExponentialSampler,"sample",sample)
    context=create_dynamic_context(cfg); result=context.run()
    assert result.status=="SUCCEEDED"
    decisions=[d for d in result.decisions if d["kind"]=="SEQUENCING" and len(d["candidates"])>1]
    assert decisions
    nonfirst=[d for d in decisions if d["selected"]!=d["candidates"][0]["option"]]
    assert nonfirst
    assert any(len({c["owner_numeric_id"] for c in d["candidate_state"]})==2 for d in decisions)
    assert result.recorded_workflow_count==3
    evidence_b03("shared-dynamic",dict(result=asdict(result),nonfirst_count=len(nonfirst),
        multicandidate_count=len(decisions)))


@pytest.mark.parametrize("domain",[True,False])
@pytest.mark.parametrize("trace",[True,False])
def test_partial_score_failure_keeps_prefix_no_decision_dispatch_or_retry(domain,trace,monkeypatch,evidence_b03):
    cfg=RunConfig("gp",trace_enabled=trace,routing_expression="PT")
    engine=create_engine(load_fixed_instance(ROOT/"data/cases/chain_remote.json"),cfg)
    options=engine.state.workflows_by_id[0].tasks[0].options
    for option,priority in zip(options,(101.,202.,303.)): option.priority=priority
    calls=[]; original=evaluator.read_feature
    failure=StateError("injected scoring domain failure") if domain else TypeError("injected scoring program failure")
    def broken(feature,option,ctx):
        calls.append(option)
        if option is options[1]: raise failure
        return original(feature,option,ctx)
    monkeypatch.setattr(evaluator,"read_feature",broken)
    if domain:
        result=engine.run(); assert result.status=="FAILED"
    else:
        with pytest.raises(TypeError) as caught: engine.run()
        assert caught.value is failure
    assert calls==options[:2]
    assert [o.priority for o in options]==[10.,202.,303.]
    assert engine.run_status=="FAILED" and not options[0].task.dispatched
    assert engine.trace.decisions==[] and engine.state.executions_by_task=={}
    assert not any(a["kind"]=="DECISION" for a in engine.trace.actions)
    with pytest.raises(EngineUsageError): engine.run()
    evidence_b03("partial-failures",dict(domain=domain,trace=trace,priorities=[o.priority for o in options],
        calls=[o.key for o in calls],events=engine.trace.events,status=engine.run_status,dispatch=False))


@pytest.mark.parametrize("expression",["(* 1e309 0)","1e309","-1e309","-0.0","0.0"])
def test_legal_special_scores_real_run_are_not_errors(expression,evidence_b03):
    cfg=RunConfig("gp",routing_expression=expression)
    engine=create_engine(load_fixed_instance(ROOT/"data/cases/chain_remote.json"),cfg)
    result=engine.run(); assert result.status=="SUCCEEDED"
    evidence_b03("special-runtime",dict(expression=expression,result=asdict(result)))


def test_reservation_precedes_successor_routing_and_keeps_mrt(evidence_b03):
    spec=load_fixed_instance(ROOT/"data/cases/v2_diamond.json")
    # A second workflow waits on the same resource when root A finishes.
    raw=spec.to_dict(); other=deepcopy(raw["workflows"][0]); other.update(id=1,release_time=1.)
    other["tasks"]=other["tasks"][:1]; other["dependencies"]=[]; raw["workflows"].append(other)
    cfg=RunConfig("fixed_resource","E0","gp",sequencing_expression="PT")
    engine=create_engine(parse_instance(raw),cfg)
    result=engine.run(); assert result.status=="SUCCEEDED"
    event=next(e for e in result.events if e["type"]=="ProcessFinishEvent" and
        any(a["kind"]=="DECISION" and a["decision"]["kind"]=="SEQUENCING" for a in e["actions"]) and
        any(a["kind"]=="DECISION" and a["decision"]["kind"]=="ROUTING" for a in e["actions"]))
    actions=event["actions"]
    seq_index=next(i for i,a in enumerate(actions) if a["kind"]=="DECISION" and a["decision"]["kind"]=="SEQUENCING")
    reserve_index=next(i for i,a in enumerate(actions) if a["kind"]=="EMIT" and a["event"]["type"]=="ProcessStartEvent")
    route_index=next(i for i,a in enumerate(actions) if a["kind"]=="DECISION" and a["decision"]["kind"]=="ROUTING")
    assert seq_index<reserve_index<route_index
    before=next(r for r in event["before"]["resources"] if r["id"]=="E0")
    routed=actions[route_index]["decision"]
    during=next(r for r in routed["resource_state"] if r["id"]=="E0")
    assert during["available_time"]==before["available_time"]
    evidence_b03("reservation-order",dict(event=event,indices=[seq_index,reserve_index,route_index]))
