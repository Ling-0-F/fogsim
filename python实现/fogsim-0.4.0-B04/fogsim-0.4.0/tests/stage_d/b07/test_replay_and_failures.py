from copy import deepcopy
import json
from pathlib import Path
import pytest
import builtins,io,shutil
from unittest.mock import patch
from fogsim.errors import InputError,StateError,EngineUsageError,PreparationError
from fogsim.experiment_config import ReplayRunOptions,RuleConfig,parse_experiment_config
from fogsim.replay.engine import simulate_replay,create_replay_engine,ReplayEngine
from fogsim.replay.loader import load_replay_input,parse_replay_input
from fogsim.serialization.result import decode_result
from fogsim.serialization.f64 import encode_f64
from fogsim.gp import evaluator

@pytest.mark.parametrize('method',['read_text','read_bytes','copy'])
def test_validation_driver_blocks_even_copy_and_byte_reads_before_stop(tmp_path,record,method):
    from stage_d_b07.dynamic import ReferenceAccessGuard
    ref=tmp_path/'reference.json';ref.write_text('{}')
    guard=ReferenceAccessGuard(tmp_path)
    with patch.object(builtins,'open',guard.wrap(builtins.open)),patch.object(io,'open',guard.wrap(io.open)):
        with pytest.raises(AssertionError,match='before independent Python'):
            if method=='copy':shutil.copyfile(ref,tmp_path/'copy.json')
            else:getattr(ref,method)()
        guard.stopped=True
        assert ref.read_text()=='{}'
    assert guard.reads[0]['after_python_stop'] is False and guard.reads[-1]['after_python_stop'] is True
    record(dict(method=method,access=guard.reads))

@pytest.mark.parametrize('purpose',['verify_reference','reuse_inputs'])
def test_new_Java_shared_scene_reference_read_timing(dynamic_data,monkeypatch,record,purpose):
    _,_,_,folder=dynamic_data();stopped=False;access=[]
    execute=ReplayEngine.run;open_path=Path.open
    def run(self):
        nonlocal stopped
        result=execute(self);stopped=True;return result
    def watched(path,*args,**kwargs):
        if path.name in ('reference.json','manifest.json'):
            access.append(path.name)
            assert purpose=='verify_reference' and stopped
        return open_path(path,*args,**kwargs)
    monkeypatch.setattr(ReplayEngine,'run',run);monkeypatch.setattr(Path,'open',watched)
    result=simulate_replay(folder/'input.json',purpose=purpose,reference_path=folder/'reference.json')
    assert result.status=='SUCCEEDED'
    assert result.diagnostics['comparison_status']==('NORMAL_PARITY_PASSED' if purpose=='verify_reference' else 'NOT_COMPARED')
    assert bool(access)==(purpose=='verify_reference')
    record(dict(purpose=purpose,reference_access=access,after_stop=stopped,diagnostics=result.to_dict()['diagnostics']))

def test_equivalent_direct_API_rule_keeps_current_source(dynamic_data,record):
    _,_,_,folder=dynamic_data();text=' ( -  0\tTIS ) '
    result=simulate_replay(folder/'input.json',ReplayRunOptions(
        sequencing_rule=RuleConfig('gp',expression=text),edge_data_policy='release_after_materialization'),reference_path=folder/'reference.json')
    assert result.status=='SUCCEEDED' and result.diagnostics['comparison_status']=='NORMAL_PARITY_PASSED'
    rules=result.diagnostics['replay_rules']
    assert rules['active']['bindings']['sequencing']['rule_id']==rules['recorded']['bindings']['sequencing']['rule_id']
    assert rules['active']['bindings']['sequencing']['source']['expression']==text
    assert rules['recorded']['bindings']['sequencing']['source']['expression']!=text
    record(rules)

@pytest.mark.parametrize('role',['routing','sequencing'])
@pytest.mark.parametrize('expression',['PT','(+ 0 PT)'])
def test_verify_JSON_forbids_any_rule_override_before_execution(dynamic_data,role,expression,record):
    _,_,_,folder=dynamic_data()
    value=dict(format='fogsim.experiment',schema_version=2,mode='replay',
        source=dict(input_path=str(folder/'input.json'),purpose='verify_reference',reference_path=str(folder/'reference.json')),
        run={role+'_rule':dict(kind='gp',expression=expression)})
    with pytest.raises(InputError) as caught:parse_experiment_config(value)
    assert 'rule overrides' in str(caught.value)
    record(dict(role=role,expression=expression,rejected=True,error=str(caught.value)))

@pytest.mark.parametrize('role',['routing','sequencing'])
def test_reuse_changed_slot_never_accesses_reference(dynamic_data,role,monkeypatch,record):
    _,_,_,folder=dynamic_data();open_path=Path.open;access=[]
    def watched(path,*a,**kw):
        if path.name in ('reference.json','manifest.json'):
            access.append(str(path));raise AssertionError('reuse reference access')
        return open_path(path,*a,**kw)
    monkeypatch.setattr(Path,'open',watched)
    options=ReplayRunOptions(**{role+'_rule':RuleConfig('gp',expression='0.0')},edge_data_policy='release_after_materialization')
    result=simulate_replay(folder/'input.json',options,purpose='reuse_inputs',reference_path=folder/'reference.json')
    assert not access and result.diagnostics['comparison_status']=='NOT_COMPARED'
    assert result.diagnostics['replay_rules']['recorded']['rule_pair_id']!=result.diagnostics['replay_rules']['active']['rule_pair_id']
    if result.status=='FAILED':assert result.reason_code in ('REPLAY_INPUT_EXHAUSTED','REPLAY_INPUT_DIVERGENCE')
    record(dict(role=role,status=result.status,reason_code=result.reason_code,diagnostics=result.to_dict()['diagnostics']))

def test_global_cursor_does_not_search_later_real_records(dynamic_data,record):
    from fogsim.replay.source import ReplayWorkflowSource
    _,_,_,folder=dynamic_data();inp=load_replay_input(folder/'input.json')
    source=ReplayWorkflowSource(inp,purpose='verify_reference')
    later=inp.archive.generation_attempts[1]
    candidate=inp.archive.candidates[1].workflow_input
    with pytest.raises(Exception,match='REPLAY_INPUT_DIVERGENCE'):
        source.generate(later.cause,candidate_id=candidate.candidate_id)
    # Runtime mismatch consumes exactly the current record before failing;
    # no searching for the otherwise valid later call, skipping, or retry.
    assert source.position==1 and source.validated_count==0
    record(source.summary())

def test_invalid_initialize_cause_rejected_before_source_creation(dynamic_data,monkeypatch,record):
    from fogsim.replay.source import ReplayWorkflowSource
    _,_,value,_=dynamic_data();value['generation_attempts'][0]['generation_clock_time']=1.
    called=[]
    def forbidden(*a,**kw):called.append(True);raise AssertionError('source created')
    monkeypatch.setattr(ReplayWorkflowSource,'__init__',forbidden)
    with pytest.raises(InputError,match='initialize cause'):parse_replay_input(value)
    assert called==[]
    record(dict(source_creation_attempts=called,rejected_before_source=True))

def test_recorded_event_sequence_remains_postrun_diagnostic(dynamic_data,record):
    _,_,value,_=dynamic_data()
    for a in value['generation_attempts']:
        if a['event_sequence'] is not None:a['event_sequence']+=1000
    inp=parse_replay_input(value);e=create_replay_engine(inp);result=e.run()
    assert result.status=='SUCCEEDED' and e.admission.source.position==len(inp.archive.generation_attempts)
    from dataclasses import asdict
    from fogsim.validation.gp_compare import first_difference
    difference=first_difference(asdict(inp.archive),asdict(e.admission.archive))
    assert difference and 'event_sequence' in difference['field_path']
    record(dict(source_succeeded=True,consumed=e.admission.source.position,postrun_first_difference=difference))

@pytest.mark.parametrize('domain',[True,False])
@pytest.mark.parametrize('trace',[True,False])
def test_actual_multidevice_queue_partial_failure_preserves_prefix(dynamic_data,monkeypatch,record,domain,trace):
    _,_,_,folder=dynamic_data();inp=load_replay_input(folder/'input.json')
    e=create_replay_engine(inp,ReplayRunOptions(trace_enabled=trace,edge_data_policy='release_after_materialization'))
    original=evaluator.read_feature;seen={};failure=StateError('B07 injected second queue candidate failure') if domain else TypeError('B07 injected unknown program exception')
    def broken(feature,option,ctx):
        if (ctx.kind.value=='SEQUENCING' and len(ctx.candidates)>=2
                and len({o.task.workflow.owner_device.numeric_id for o in ctx.candidates})>=2):
            if not seen:
                seen.update(candidates=ctx.candidates,before=[o.priority for o in ctx.candidates],source_position=e.admission.source.position,
                    event_sequence=e.processed_event_count,calls=[])
            seen['calls'].append(option)
            if option is ctx.candidates[1]:raise failure
        return original(feature,option,ctx)
    monkeypatch.setattr(evaluator,'read_feature',broken)
    if domain:result=e.run();assert result.status=='FAILED'
    else:
        with pytest.raises(TypeError) as caught:e.run()
        assert caught.value is failure
        result=e.result()
    assert seen and seen['calls']==list(seen['candidates'][:2])
    after=[o.priority for o in seen['candidates']]
    assert after[0]!=seen['before'][0] and after[1:]==seen['before'][1:]
    assert e.admission.source.position==seen['source_position'] and e.run_status=='FAILED'
    assert not any(d['kind']=='SEQUENCING' and d['event_sequence']==seen['event_sequence'] for d in e.trace.decisions)
    assert e.trace.decision_errors and len(e.trace.decision_errors[-1]['scored_prefix'])==1
    assert 'selected' not in e.trace.decision_errors[-1]
    if trace:
        assert not any(a['kind']=='EMIT' for a in e.trace.events[-1]['actions'])
    with pytest.raises(EngineUsageError):e.run()
    wire=result.to_dict();decode_result(wire)
    record(dict(domain=domain,trace=trace,source_position=seen['source_position'],
        before=[encode_f64(x) for x in seen['before']],after=[encode_f64(x) for x in after],result=wire))
