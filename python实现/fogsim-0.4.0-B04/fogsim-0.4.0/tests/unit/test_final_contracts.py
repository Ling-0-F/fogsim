"""Contracts found in the clause-by-clause 0.3.0 audit."""
from dataclasses import replace
from pathlib import Path
import json
import tomllib
import pytest
from conftest import ROOT
from fogsim import (__version__,AdmissionResult,load_replay_input,create_replay_engine,
                    load_experiment_config,run_experiment,create_dynamic_context,export_replay_input,parse_replay_input)
from fogsim.errors import StateError,InputError,NumericDerivationError
from fogsim.instances.generated import GenerationCause
from fogsim.replay.source import ReplayWorkflowSource
from fogsim.simulation.dynamic import DynamicEngine
from fogsim.simulation.engine import EventContext
from fogsim.environment.build import build_environment
from fogsim.experiment_config import RepeatConfig
from fogsim.validation.dynamic_compare import compare_dynamic_reference
from fogsim.replay.loader import read_replay_json


def engine_for(name):
    inp=load_replay_input(ROOT/'outputs/step4/cases'/name/'input.json')
    engine=DynamicEngine(build_environment(inp.archive.environment),inp.run_config,inp.archive.environment,
        inp.archive.templates,ReplayWorkflowSource(inp,purpose='verify_reference'))
    return engine


def test_formal_admit_success_result_is_canonical_and_published_once():
    engine=engine_for('minimal_chain');device=engine.state.mobile_devices[0]
    result=engine.admission.admit(GenerationCause('initialize',device.id,0),EventContext(engine,device))
    assert isinstance(result,AdmissionResult) and result.accepted and result.reason_code is None
    assert result.workflow is engine.state.workflows_by_id[0]
    assert len(engine.event_queue.staging_heaps[device])==1 and engine.statistics.generated_total==1
    assert len(engine.admission.archive.candidates)==len(engine.admission.archive.generation_attempts)==1


def test_formal_admit_rejection_is_a_normal_result_and_retains_full_candidate():
    engine=engine_for('all_devices_rejected');device=engine.state.mobile_devices[0]
    result=engine.admission.admit(GenerationCause('initialize',device.id,0),EventContext(engine,device))
    assert not result.accepted and result.workflow is None and result.reason_code=='REJECTED_RELEASE_NOT_FUTURE'
    assert engine.statistics.generated_total==0 and not engine.state.workflows_by_id
    assert not engine.event_queue.staging_heaps[device]
    assert engine.admission.archive.candidates[0].workflow_input.tasks


def test_admit_generation_exception_remains_exception_not_rejection(monkeypatch):
    engine=engine_for('minimal_chain');device=engine.state.mobile_devices[0]
    def fail(*args,**kwargs):raise NumericDerivationError('injected',float('inf'))
    monkeypatch.setattr(engine.admission.source,'generate',fail)
    with pytest.raises(NumericDerivationError):
        engine.admission.admit(GenerationCause('initialize',device.id,0),EventContext(engine,device))
    assert engine.admission.incomplete_attempt and not engine.admission.archive.candidates


def test_old_attempt_convenience_return_remains_compatible():
    engine=engine_for('minimal_chain');device=engine.state.mobile_devices[0]
    workflow=engine.admission.attempt(GenerationCause('initialize',device.id,0),EventContext(engine,device))
    assert workflow is engine.state.workflows_by_id[0]


@pytest.mark.parametrize('accepted,workflow,reason',[(1,None,None),(True,None,None),(False,None,None),(False,None,'UNKNOWN')])
def test_admission_result_rejects_inconsistent_values(accepted,workflow,reason):
    with pytest.raises(StateError):AdmissionResult(accepted,workflow,reason)


def test_release_version_and_python_capture_provenance():
    assert __version__=='0.4.0'==tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['version']
    cfg=load_experiment_config(ROOT/'configs/examples/step5_dynamic.json');ctx=create_dynamic_context(cfg);ctx.run()
    assert export_replay_input(ctx.engine,cfg.source).to_dict()['origin']['implementation_version']=='fogsim-0.4.0'


def test_progress_callback_cannot_mutate_final_results_or_later_checkpoints():
    cfg=replace(load_experiment_config(ROOT/'configs/examples/step5_dynamic.json'),repeat=RepeatConfig(2,'fresh_same_seed'))
    def observer(result):
        if result.runs and not result.batch_complete:result.runs[0].task_records[0]['finish_time']=-123
    result=run_experiment(cfg,on_progress=observer)
    assert all(r.task_records[0]['finish_time']!=-123 for r in result.runs)
    assert result.runs[0].to_dict()==result.runs[1].to_dict()


def test_present_normalized_seed_must_be_decimal_string_not_null():
    value=read_replay_json(ROOT/'tests/fixtures/dynamic_v1/input.json');value['initial_state']['rng_seed_decimal']=None
    with pytest.raises(InputError):parse_replay_input(value)


def test_legacy_reference_is_usable_but_does_not_prove_missing_trace_fields():
    path=ROOT/'outputs/step4/cases/minimal_chain';engine=create_replay_engine(load_replay_input(path/'input.json'));result=engine.run()
    report=compare_dynamic_reference(engine,result,read_replay_json(path/'reference.json'),require_full_trace=True)
    assert report['classification']=='NOT_EXECUTED' and not report['passed'] and not report['full_contract_verified']


@pytest.mark.parametrize('corrupt',[None,{'schema_version':1},[],{'format':'bad'}])
def test_invalid_reference_is_an_input_error(corrupt):
    from fogsim.validation.dynamic_compare import _reference
    with pytest.raises(InputError):_reference(corrupt)


def test_first_difference_follows_event_before_actions_after_error_order():
    from copy import deepcopy
    from fogsim.validation.dynamic_compare import _chronological_difference
    expected=dict(events=[dict(event_sequence=i,time=float(i)) for i in (1,2)],decisions=[],actions=[],
        pre_trigger_states=[dict(event_sequence=i,state={'clock_time':float(i)}) for i in (1,2)],
        post_trigger_states=[dict(event_sequence=i,state={'clock_time':float(i)}) for i in (1,2)],
        event_errors=[dict(event_sequence=i,error=None) for i in (1,2)],final_state={},native={})
    actual=deepcopy(expected)
    actual['pre_trigger_states'][0]['state']['clock_time']=99.0
    actual['events'][1]['time']=99.0
    assert _chronological_difference(expected,actual,extended=True)['path']=='$.pre_trigger_states[0].state.clock_time'
    actual=deepcopy(expected);actual['event_errors'][0]['error']='wrong';actual['final_state']['bad']=1
    assert _chronological_difference(expected,actual,extended=True)['path']=='$.event_errors[0].error'


def test_malformed_native_reference_fields_are_input_errors():
    from fogsim.validation.dynamic_compare import _reference
    value=read_replay_json(ROOT/'outputs/step4/cases/minimal_chain/reference.json')
    del value['native_result']['target_reached']
    with pytest.raises(InputError):_reference(value)


def test_fresh_reference_proves_pre_post_actual_owner_staging_and_errors():
    p=ROOT/'tests/fixtures/dynamic_full_v1';engine=create_replay_engine(load_replay_input(p/'input.json'));result=engine.run()
    report=compare_dynamic_reference(engine,result,read_replay_json(p/'reference.json'),manifest_path=p/'manifest.json',
        input_path=p/'input.json',reference_path=p/'reference.json',require_full_trace=True)
    assert report['passed'] and report['full_contract_verified'] and report['classification']=='NORMAL_PARITY_PASSED'


def test_reference_faults_find_earliest_pre_state_and_explicit_staging():
    from copy import deepcopy
    p=ROOT/'tests/fixtures/dynamic_full_v1';engine=create_replay_engine(load_replay_input(p/'input.json'));result=engine.run()
    ref=read_replay_json(p/'reference.json');changed=deepcopy(ref)
    changed['pre_trigger_states'][0]['state']['G']+=1;changed['events'][-1]['time']+=1
    report=compare_dynamic_reference(engine,result,changed,require_full_trace=True)
    assert report['first_difference']['path']=='$.pre_trigger_states[0].state.G'
    changed=deepcopy(ref);changed['events'][0]['staging_device_id']='M999'
    report=compare_dynamic_reference(engine,result,changed,require_full_trace=True)
    assert report['first_difference']['path']=='$.events[0].staging_device_id'
    assert result.status=='SUCCEEDED' and result.recorded_workflow_count==1


def test_performance_harness_activates_both_actual_policies(tmp_path):
    import sys
    sys.path.insert(0,str(ROOT/'tools'))
    from run_final_acceptance import performance
    report=performance(tmp_path)
    assert report['passed']
    for row in report['measurements']:
        assert row['events']>0
        if row['policy']=='retain':assert row['cleanup']['released_task_count']==0
        else:assert row['cleanup']['released_task_count']==row['tasks']>0


def test_direct_simulate_replay_optional_reference_is_post_run_and_bound(tmp_path):
    from fogsim import simulate_replay
    p=ROOT/'tests/fixtures/dynamic_full_v1'
    result=simulate_replay(p/'input.json',reference_path=p/'reference.json')
    assert result.status=='SUCCEEDED' and result.diagnostics['comparison']['full_contract_verified']
    reused=simulate_replay(p/'input.json',purpose='reuse_inputs',reference_path=tmp_path/'absent.json')
    assert reused.status=='SUCCEEDED' and reused.diagnostics['comparison_status']=='NOT_COMPARED'


def test_invalid_replay_path_type_is_input_error():
    from fogsim import simulate_replay
    with pytest.raises(InputError):load_replay_input(123)
    with pytest.raises(InputError):simulate_replay(b'unsupported-byte-path')
