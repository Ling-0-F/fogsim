from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
import hashlib
import json
import random
import pytest

from fogsim import create_dynamic_context, create_engine, load_fixed_instance, RunConfig
from fogsim.gp import evaluator
from fogsim.gp.diagnostics import GPInputError
from fogsim.instances.source import RandomWorkflowSource
from fogsim.randomness import samplers
from fogsim.rules.factory import prepare_rules, install_rules
from fogsim.rules.specs import RuleSpec
from fogsim.rules.contexts import RoutingContext, StateView
from ..test_purity import snapshot
from conftest import ROOT, step
from .helpers import prepared, gp_dynamic, pair


@pytest.mark.parametrize("layer", ["prepare", "install", "priority"])
@pytest.mark.parametrize("failure", [False,True])
def test_purity_finally_and_zero_rng_source_attempts(layer,failure,tmp_path,monkeypatch,evidence_b03):
    CHAIN='<adag><job id="Z"/><job id="a"/><child ref="a"><parent ref="Z"/></child></adag>'
    cfg=gp_dynamic(tmp_path,xml=CHAIN,devices=2,edges=1,clouds=1)
    context=create_dynamic_context(cfg); step(context.engine)
    workflow=next(iter(context.engine.state.active_workflows.values()))
    option=workflow.tasks[1].options[0]
    ctx=RoutingContext(option.task,tuple(option.task.options),StateView.from_state(context.engine.state))
    p=context.engine.prepared_rules
    before=snapshot(context); original_getstate=random.Random.getstate
    native_before=original_getstate(context.inputs.rng); module_before=random.getstate()
    immutable_before=hash(p.routing.compiled); attempts=[]
    def forbidden(name):
        def fail(*args,**kwargs): attempts.append(name); raise AssertionError(name)
        return fail
    for name in dir(random.Random):
        if not name.startswith("_") and name!="getstate" and callable(getattr(random.Random,name)):
            monkeypatch.setattr(random.Random,name,forbidden("Random."+name))
            if callable(getattr(random,name,None)):monkeypatch.setattr(random,name,forbidden("random."+name))
    for cls in (random.Random,random.SystemRandom):monkeypatch.setattr(cls,"__init__",forbidden(cls.__name__+".__init__"))
    monkeypatch.setattr(random.SystemRandom,"random",forbidden("SystemRandom.random"))
    monkeypatch.setattr(random.SystemRandom,"getrandbits",forbidden("SystemRandom.getrandbits"))
    for cls in (samplers.UniformRealSampler,samplers.UniformIntegerSampler,samplers.ExponentialSampler,
                samplers.WeightSampler,samplers.CloudBandwidthSampler,samplers.EdgeBandwidthSampler):
        monkeypatch.setattr(cls,"sample",forbidden(cls.__name__+".sample"))
    monkeypatch.setattr(RandomWorkflowSource,"generate",forbidden("source.generate"))
    error=RuntimeError("injected read failure")
    if layer=="priority" and failure:
        def broken(*args): raise error
        monkeypatch.setattr(evaluator,"read_feature",broken)
    try:
        if layer=="prepare":
            if failure:
                with pytest.raises(GPInputError): prepared("PT","(+ PT)")
            else: prepared()
        elif layer=="install":
            if failure:
                with pytest.raises(GPInputError): install_rules(RunConfig(),p)
            else: assert install_rules(cfg.run,p) is p
        elif failure:
            with pytest.raises(RuntimeError) as caught: p.routing.priority(option,ctx)
            assert caught.value is error
        else: assert p.routing.priority(option,ctx)==option.processing_time
    finally:
        assert snapshot(context)==before
        assert original_getstate(context.inputs.rng)==native_before
        assert random.getstate()==module_before
        assert hash(p.routing.compiled)==immutable_before
        assert attempts==[]
        evidence_b03("purity",dict(layer=layer,failure=failure,unchanged=True,attempts=attempts,
            native_state_sha256=hashlib.sha256(json.dumps(native_before).encode()).hexdigest(),
            scope=["context","models","queue","events","source","archive","statistics","trace"]))


def test_program_shared_parallel_and_interleaved_models_no_runtime_capture(evidence_b03):
    p=prepared(); program=p.routing.compiled; before=hash(program)
    cfg=RunConfig("gp",sequencing_kind="gp",routing_expression="PT",sequencing_expression="(- 0 PT)")
    spec=load_fixed_instance(ROOT/"data/cases/chain_remote.json")
    engines=[create_engine(spec,cfg,prepared_rules=p) for _ in range(3)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda e:e.run(),engines[:2]))
    while engines[2].event_queue.has_pending(): step(engines[2])
    assert all(r.status=="SUCCEEDED" for r in results)
    assert asdict(results[0])==asdict(results[1])
    assert all(e.routing_rule.compiled is program for e in engines)
    assert len({id(e.state.workflows_by_id[0]) for e in engines})==3
    assert hash(program)==before
    evidence_b03("isolation",dict(shared_program=True,separate_models=True,parallel_results_equal=True,
        interleaved_completed=len(engines[2].state.completed_workflows)))


def test_gp_dynamic_rerun_reset_rotate_share_only_immutable_bindings(tmp_path,evidence_b03):
    cfg=gp_dynamic(tmp_path); context=create_dynamic_context(cfg); p=context.engine.prepared_rules
    result=context.run(); saved=asdict(result); models=[context.engine.state]
    next_result=context.rerun(); models.append(context.engine.state)
    assert context.engine.prepared_rules is p and next_result.status=="SUCCEEDED"
    context.reset(); models.append(context.engine.state); assert context.run().status=="SUCCEEDED"
    context.rotate_seed(); models.append(context.engine.state); assert context.run().status=="SUCCEEDED"
    assert context.engine.prepared_rules is p
    assert len({id(s) for s in models})==4
    assert asdict(result)==saved
    evidence_b03("dynamic-isolation",dict(operations=["fresh","rerun","reset","rotate_seed"],
        shared_bindings=True,states_distinct=True,previous_result_unchanged=True))


def test_retain_release_use_same_program_and_preserve_gp_behavior(tmp_path,evidence_b03):
    cfg=gp_dynamic(tmp_path); p=prepared(); contexts=[];results=[]
    for policy in ("retain","release_after_materialization"):
        context=create_dynamic_context(replace(cfg,run=replace(cfg.run,edge_data_policy=policy)),prepared_rules=p)
        contexts.append(context);results.append(context.run())
    a,b=results
    for key in ("status","makespan","mean_flow_time","processed_event_count","recorded_workflow_count",
                "workflow_records","task_records","events","decisions"):
        assert getattr(a,key)==getattr(b,key), key
    assert contexts[0].engine.rng_final.fingerprint==contexts[1].engine.rng_final.fingerprint
    for c in contexts: assert c.engine.prepared_rules is p
    assert any(t.input_data_by_parent is not None for t in contexts[0].engine.state.tasks_by_key.values())
    assert all(t.input_data_by_parent is None for t in contexts[1].engine.state.tasks_by_key.values())
    evidence_b03("cleanup-isolation",dict(shared_program=True,identical_behavior=True,
        retained_has_maps=True,released_has_no_maps=True,same_rng=True))
