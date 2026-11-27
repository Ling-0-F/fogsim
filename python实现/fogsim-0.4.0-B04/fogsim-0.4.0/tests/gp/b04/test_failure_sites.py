from copy import deepcopy
import json
import pytest
from fogsim import create_engine, RunConfig, create_dynamic_context
from fogsim.gp import evaluator
from fogsim.errors import StateError, InputError
from fogsim.serialization.result import decode_result
from ..b03.helpers import gp_dynamic
from ..b03.test_runtime import shared_spec
from .test_result import INVALID

@pytest.mark.parametrize('site',['diagnostics','actions','after'])
@pytest.mark.parametrize('tag',INVALID)
def test_failed_prefix_and_failed_state_strict_tag(monkeypatch,site,tag):
    engine=create_engine(shared_spec(),RunConfig('gp',routing_expression='PT'))
    calls=[]
    def fail(feature,option,ctx):
        calls.append(option)
        if len(calls)==2:raise StateError('injected')
        return -0.0
    monkeypatch.setattr(evaluator,'read_feature',fail)
    out=engine.run().to_dict()
    if site=='diagnostics':row=out['diagnostics']['decision_errors'][0]['scored_prefix'][0]
    elif site=='actions':row=out['events'][-1]['actions'][0]['decision_error']['scored_prefix'][0]
    else:row=out['events'][-1]['after']['tasks'][0]['options'][0]
    row['priority']=tag
    with pytest.raises(InputError,match='GP_F64_ENCODING_INVALID'):decode_result(out)
    assert len(calls)==2


@pytest.mark.parametrize('trace',[True,False])
def test_real_sequencing_error_in_complete_queue(monkeypatch,trace,evidence_b04):
    engine=create_engine(shared_spec(),RunConfig('fixed_resource','E0','gp',trace,sequencing_expression='PT'))
    calls=[]
    def fail(feature,option,ctx):
        assert len(ctx.candidates)==2
        assert all(any(o is c for o in option.resource.waiting_queue) for c in ctx.candidates)
        calls.append(option)
        if len(calls)==2:raise StateError('sequencing failure')
        return float('inf')
    monkeypatch.setattr(evaluator,'read_feature',fail)
    result=engine.run();out=result.to_dict();decode_result(json.loads(json.dumps(out,allow_nan=False)))
    error=out['diagnostics']['decision_errors'][0]
    assert error['role']=='sequencing' and error['failed_candidate_index']==1
    assert len(engine.state.resources_by_id['E0'].waiting_queue)==2
    assert engine.state.resources_by_id['E0'].pending_start is None
    assert error['scored_prefix'][0]['priority']['bits']=='7ff0000000000000'
    assert not any(d['kind']=='SEQUENCING' for d in out['decisions'])
    evidence_b04('sequencing-errors',out)


@pytest.mark.parametrize('trace',[True,False])
def test_dynamic_failure_still_has_manifest_and_error(tmp_path,monkeypatch,trace,evidence_b04):
    from dataclasses import replace
    cfg=gp_dynamic(tmp_path,edges=1);cfg=replace(cfg,run=replace(cfg.run,trace_enabled=trace))
    context=create_dynamic_context(cfg);calls=[]
    def fail(feature,option,ctx):
        calls.append(option)
        if len(calls)==2:raise StateError('dynamic failure')
        return float('nan')
    monkeypatch.setattr(evaluator,'read_feature',fail)
    result=context.run();out=result.to_dict();decode_result(out)
    assert out['status']=='FAILED' and out['diagnostics']['decision_errors'][0]['role']=='routing'
    assert len(calls)==2 and not out['decisions']
    evidence_b04('dynamic-errors',out)
