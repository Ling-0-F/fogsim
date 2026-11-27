from copy import deepcopy
from pathlib import Path
import json
import pytest
from fogsim.config import RunConfig
from fogsim.instances.fixed import parse_instance
from fogsim.simulation.engine import create_engine
from fogsim.validation.gp_observe import attach_observer
from fogsim.validation.gp_compare import first_difference
from fogsim.replay.engine import simulate_replay,ReplayEngine
from fogsim.replay.loader import load_replay_input
from fogsim.experiment_config import ReplayRunOptions,RuleConfig
HERE=Path(__file__).parent/'fixtures'

def test_observer_single_read_order_no_model_or_output_change():
    x=json.loads((HERE/'fixed-input.json').read_text());spec=parse_instance(x['input']);config=RunConfig(routing_kind='gp',routing_expression='(+ (* PT PT) (+ UT PT))',sequencing_kind='gp',sequencing_expression='(- 0 NTR)')
    plain=create_engine(spec,config);observed=create_engine(spec,config,prepared_rules=plain.prepared_rules)
    program=plain.prepared_rules.routing.compiled
    before=repr(program);collector=attach_observer(observed)
    a,b=plain.run().to_dict(),observed.run().to_dict()
    assert first_difference(a,b) is None
    assert observed.prepared_rules.routing.compiled is program and repr(program)==before
    assert not hasattr(plain,'gp_observations')
    rows=[r for r in collector.feature_observations if r['role']=='routing']
    assert rows and all([v['name'] for v in r['reads']]==['PT','PT','UT','PT'] for r in rows)
    assert all([v['node_index'] for v in r['reads']]==[2,3,5,6] for r in rows)
    assert all(r['reads'][0]['value']==r['reads'][1]['value']==r['reads'][3]['value'] for r in rows)
    with pytest.raises(ValueError,match='already'):attach_observer(observed)

def test_scalar_callback_failure_propagates_no_priority_write():
    from stage_d_probe import load_fixture
    from stage_d_cases import fixture
    from fogsim.rules.contexts import StateView,RoutingContext
    from fogsim.rules.factory import prepare_rules
    from fogsim.rules.specs import RuleSpec
    from fogsim.gp.evaluator import evaluate
    state,options=load_fixture(fixture());o=options[0,'T0','E0'];ctx=RoutingContext(o.task,(o,),StateView.from_state(state));p=prepare_rules(RuleSpec('routing','gp',expression='(+ PT PT)'),RuleSpec('sequencing','fcfs'));calls=[]
    def callback(i,v):calls.append((i.node_index,v));raise RuntimeError('observer failure')
    before=o.priority
    with pytest.raises(RuntimeError,match='observer failure'):evaluate(p.routing.compiled,o,ctx,observer=callback)
    assert calls==[(1,o.processing_time)] and o.priority==before

@pytest.mark.parametrize('purpose',['reuse_inputs','verify_reference'])
def test_actual_java_reference_read_timing_and_reuse_sentinel(monkeypatch,purpose):
    stopped=False;reads=[];run=ReplayEngine.run;original=Path.read_text
    def execute(self):
        nonlocal stopped
        result=run(self);stopped=True;return result
    def checked(self,*a,**kw):
        if self.name in ('reference.json','manifest.json'):
            assert purpose=='verify_reference' and stopped
            reads.append(self.name)
        return original(self,*a,**kw)
    monkeypatch.setattr(ReplayEngine,'run',execute);monkeypatch.setattr(Path,'read_text',checked)
    r=simulate_replay(HERE/'dynamic/input.json',purpose=purpose,reference_path=HERE/'dynamic/reference.json')
    assert r.status=='SUCCEEDED'
    assert r.diagnostics['comparison_status']==('NORMAL_PARITY_PASSED' if purpose=='verify_reference' else 'NOT_COMPARED')
    assert bool(reads)==(purpose=='verify_reference')

def test_executed_object_must_equal_bound_input():
    from dataclasses import replace
    from fogsim.errors import InputError
    from fogsim.replay.loader import parse_replay_input
    value=load_replay_input(HERE/'dynamic/input.json').to_dict();value['initial_state']['public_seed']=32;inp=parse_replay_input(value)
    with pytest.raises(InputError,match='executed input/reference differs'):
        simulate_replay(inp,input_path=HERE/'dynamic/input.json',reference_path=HERE/'dynamic/reference.json')

def test_trace_off_and_insufficient_input_never_normal():
    r=simulate_replay(HERE/'dynamic/input.json',ReplayRunOptions(trace_enabled=False,edge_data_policy='release_after_materialization'),reference_path=HERE/'dynamic/reference.json')
    assert r.status=='SUCCEEDED' and r.diagnostics['comparison_status']=='NOT_EXECUTED'
