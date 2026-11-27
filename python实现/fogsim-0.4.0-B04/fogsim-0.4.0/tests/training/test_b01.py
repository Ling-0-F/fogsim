"""S9-B01 contract tests: real B08 runs plus explicit fault injection in child."""
from copy import deepcopy
from dataclasses import replace
import json
import math
import multiprocessing
import os
from pathlib import Path
import random
import subprocess
import sys
import pytest

from fogsim.errors import InputError
from fogsim import create_dynamic_context
from fogsim.rules.factory import prepare_rules
from fogsim.rules.specs import RuleSpec
from fogsim.training.config import parse_training_config, load_training_config
from fogsim.training.plans import build_training_plans, parse_training_plan, _entry, _plan
from fogsim.training.evaluation import evaluate_rule_pair, RemoteEvaluationError
from fogsim.training.fitness import compare, summarize, classify, EvaluationContractError
from fogsim.training.protocols import canonical, identity, write_json, read_json
from fogsim.training.runtime import bind_config, run_entry

ROOT=Path(__file__).resolve().parents[2]
DEFAULT=dict(format='fogsim.training-config',schema_version=1,mode='single_routing',
             plans=dict(training='train-sources.json',validation='validation-sources.json',test='test-sources.json'))


def rules(expr='PT', sequencing='fcfs'):
    return prepare_rules(RuleSpec('routing','gp',expression=expr),RuleSpec('sequencing',sequencing))


@pytest.fixture
def config():return load_training_config(ROOT/'configs/training/B01.json')


@pytest.fixture
def plan(config):return build_training_plans(config).training[0]


@pytest.mark.parametrize('path,value',[
    (('extra',),1), (('schema_version',),True), (('mode',),'java_lifecycle'),
    (('evolution','population_size'),True), (('evolution','generations'),0),
    (('evolution','elite_count'),13), (('evolution','crossover_attempts'),0),
    (('evolution','unknown'),1), (('evolution','operator_weights'),dict(crossover=.7,mutation=.1,reproduction=.1)),
    (('evolution','operator_weights'),dict(crossover=float('nan'),mutation=.1,reproduction=.1)),
    (('evolution','operator_weights'),dict(crossover=-.1,mutation=.5,reproduction=.6)),
    (('trees','init_full_probability'),1.1), (('trees','max_height'),8),
    (('trees','max_nodes'),True), (('trees','max_nodes'),2), (('trees','init_min_height'),4),
    (('trees','numeric_erc'),True), (('trees','grow_policy'),'deap_default'),
    (('evaluation','lifecycle'),'reset'), (('evaluation','seed_rotation_step'),1),
    (('evaluation','rotation_period'),0), (('evaluation','aggregation'),'scene_mean'),
    (('limits','wallclock_seconds_per_run'),0), (('limits','wallclock_seconds_per_run'),float('inf')),
    (('output','save_run_results'),False), (('trials','evolution_seeds'),[1,1]),
    (('trials','evolution_seeds'),[2**63]), (('semantics','numeric_semantics_version'),'other'),
    (('plans','extra'),'foo'),
])
def test_strict_config(path,value):
    d=deepcopy(DEFAULT);target=d
    for key in path[:-1]:target=target.setdefault(key,{})
    target[path[-1]]=value
    with pytest.raises(InputError):parse_training_config(d,ROOT/'configs/training')


def test_defaults_and_rotation_do_not_consume_rng(config):
    before=random.getstate();plans=build_training_plans(config)
    assert random.getstate()==before
    assert [[e['seed'] for e in p.to_dict()['entries']] for p in plans.training]==[[101,102],[10101,10102],[20101,20102],[30101,30102]]
    assert plans.validation.to_dict()['dataset_role']=='debug'
    assert plans.validation.to_dict()['split']=='validation'
    d=config.to_dict();d['evaluation']['rotation_period']=2;d.pop('resolution_root')
    c=parse_training_config(d,ROOT)
    pp=build_training_plans(c)
    assert pp.training[0].plan_id==pp.training[1].plan_id
    assert pp.training[1].plan_id!=pp.training[2].plan_id
    assert len(pp.training)==4


def configured(tmp_path, **changes):
    tmp_path.mkdir(exist_ok=True)
    source=read_json(ROOT/'configs/training/train-a.json')
    source['source']['dag_root']=str(ROOT/'examples/step5/dax')
    for split,seed in [('train',101),('validation',11001),('test',21001)]:
        raw=deepcopy(source);raw['source']['seed']=seed
        for k,v in changes.get(split,{}).items():
            if k=='seed':raw['source'][k]=v
            else:raw['run'][k]=v
        write_json(tmp_path/(split+'.json'),raw)
        write_json(tmp_path/(split+'-sources.json'),dict(format='fogsim.training-source-plan',schema_version=1,
            entries=[dict(run_id=split,config=split+'.json')]))
    d=deepcopy(DEFAULT);d['plans']['training']='train-sources.json'
    return parse_training_config(d,tmp_path)


def test_split_collision_ignores_statistics_and_event_budget(tmp_path):
    c=configured(tmp_path,validation=dict(seed=101,num_jobs_recorded=3,max_events=100))
    with pytest.raises(InputError,match='cross-split'):build_training_plans(c)


def test_signed64_overflow_and_missing_file(tmp_path):
    c=configured(tmp_path,train=dict(seed=2**63-1))
    with pytest.raises(InputError,match='seed'):build_training_plans(c)
    (tmp_path/'test.json').unlink()
    with pytest.raises(InputError):build_training_plans(c)


def test_scene_family_identity_and_order(tmp_path):
    c=configured(tmp_path);a=build_training_plans(c).training[0].to_dict()['entries'][0]
    raw=read_json(tmp_path/'train.json');raw['run']['max_events']=1
    write_json(tmp_path/'train.json',raw);b=build_training_plans(c).training[0].to_dict()['entries'][0]
    assert a['input_family_id']==b['input_family_id'] and a['scene_id']!=b['scene_id']
    raw['run']['routing_rule']=dict(kind='gp',expression='(- PT WIQ)')
    raw['source']['seed']=404;write_json(tmp_path/'train.json',raw)
    cc=build_training_plans(c).training[0].to_dict()['entries'][0]
    assert (cc['input_family_id'],cc['scene_id'])==(b['input_family_id'],b['scene_id'])
    p=_plan('validation',[a,b],dict(wallclock_seconds_per_run=None))
    assert p.plan_id!=_plan('validation',[b,a],dict(wallclock_seconds_per_run=None)).plan_id


def test_same_input_different_paths_rejected(tmp_path):
    c=configured(tmp_path)
    for split in ['validation','test']:
        raw=dict(instance=str(ROOT/'data/cases/chain_remote.json'),routing_rule=dict(kind='fcfs'),sequencing_rule=dict(kind='fcfs'))
        # Two physical copies of identical JSON with distinct filenames.
        inp=read_json(ROOT/'data/cases/chain_remote.json');write_json(tmp_path/(split+'-input.json'),inp)
        raw['instance']=split+'-input.json';write_json(tmp_path/(split+'.json'),raw)
    with pytest.raises(InputError,match='cross-split'):build_training_plans(c)


def test_native_capture_cannot_evade_split_identity_as_replay(tmp_path,plan):
    native=evaluate_rule_pair(rules(),plan,tmp_path/'capture').to_dict()
    c=configured(tmp_path/'configs')
    archive=tmp_path/'capture'/native['runs'][0]['input_ref']
    replay=dict(format='fogsim.experiment',schema_version=2,mode='replay',
        source=dict(input_path=str(archive),purpose='reuse_inputs'),run=dict(max_events=2000))
    write_json(tmp_path/'configs/validation.json',replay)
    e=_entry(tmp_path/'configs/validation.json','v','validation',0,dict(trace='all'))
    assert e['input_family_id']==plan.to_dict()['entries'][0]['input_family_id'] and e['seed']==101
    with pytest.raises(InputError,match='cross-split'):build_training_plans(c)


def test_frozen_plan_content_portable_tamper_and_detachment(plan,tmp_path):
    raw=plan.to_dict();raw['entries'][0]['seed']=111
    with pytest.raises(InputError):parse_training_plan(raw)
    assert plan.to_dict()['entries'][0]['seed']==101
    copy=parse_training_plan(json.loads(plan.document))
    assert copy==plan
    # XML is frozen as bytes, no source path is needed at execution.
    result=evaluate_rule_pair(rules(),copy,tmp_path/'frozen').to_dict()
    assert result['status']=='FEASIBLE'
    assert all(read_json(tmp_path/'frozen'/r['result_ref'])['diagnostics']['initial_cutoff_release_time']==0 for r in result['runs'])


def fixed_entry(tmp_path,name,pt):
    inp=read_json(ROOT/'data/cases/single_local.json')
    inp['workflows'][0]['tasks'][0]['execution_times']['M0']['processing_time']=pt
    write_json(tmp_path/(name+'-input.json'),inp)
    write_json(tmp_path/(name+'.json'),dict(instance=name+'-input.json',routing_rule=dict(kind='fcfs'),sequencing_rule=dict(kind='fcfs')))
    return _entry(tmp_path/(name+'.json'),name,'validation',0,dict(trace='all'))


def test_real_fixed_multiscene_equal_weight_mean(tmp_path):
    entries=[fixed_entry(tmp_path,'a',1),fixed_entry(tmp_path,'b',1),fixed_entry(tmp_path,'c',10)]
    plan=_plan('validation',entries,dict(wallclock_seconds_per_run=None))
    actual=evaluate_rule_pair(rules(),plan,tmp_path/'evidence').to_dict()
    assert actual['status']=='FEASIBLE' and actual['fitness']==4
    assert actual['diagnostic_sample_stddev_over_successes']==math.sqrt(27)
    assert [read_json(tmp_path/'evidence'/r['result_ref'])['makespan'] for r in actual['runs']]==[1,1,10]


def test_event_budget_domain_continues_complete_plan(tmp_path):
    c=configured(tmp_path,train=dict(max_events=1));p=build_training_plans(c).training[0]
    good=build_training_plans(load_training_config(ROOT/'configs/training/B01.json')).training[0].to_dict()['entries'][0]
    bad=p.to_dict()['entries'][0]
    p=_plan('train',[bad,good],dict(wallclock_seconds_per_run=None))
    actual=evaluate_rule_pair(rules(),p,tmp_path/'failed').to_dict()
    assert (actual['status'],actual['fitness'],actual['completed_runs'],actual['failed_runs'],actual['succeeded_runs'])==('INFEASIBLE',None,2,1,1)
    assert actual['failure_rate']==.5 and actual['not_run']==0
    assert actual['runs'][0]['classification']=='EVENT_BUDGET_EXHAUSTED'
    raw=read_json(tmp_path/'failed'/actual['runs'][0]['result_ref'])
    assert raw['status']=='FAILED' and raw['makespan'] is None and raw['reason_code']=='MAX_EVENTS_EXCEEDED'
    assert actual['diagnostic_mean_over_successes'] is not None
    feasible=actual|dict(status='FEASIBLE',fitness=1e300)
    assert compare(feasible,actual)==-1
    assert compare(actual,actual|dict(failed_runs=123))==0


def injected_worker(conn,rules_desc,plan,seed):
    from fogsim.training import worker
    from fogsim.training import runtime
    original=runtime.run_entry
    def fail(entry,*args,**kwargs):
        if entry['seed']==102:
            from fogsim.rules.gp import GPRule
            def broken(*a,**kw):
                try:raise KeyError('injected cause')
                except KeyError as exc:raise TypeError('injected program fault') from exc
            GPRule.priority=broken
        return original(entry,*args,**kwargs)
    worker.run_entry=fail
    worker.evaluation_worker(conn,rules_desc,plan,seed)


def exit_worker(conn,*args):
    conn.send(dict(kind='run_started',index=0,run_id='exit'))
    conn.recv();os._exit(17)


def domain_worker(conn,rules_desc,plan,seed):
    from fogsim.training import worker
    from fogsim.rules.gp import GPRule
    from fogsim.errors import StateError
    original=GPRule.priority
    calls=[0]
    def domain(*args,**kwargs):
        calls[0]+=1
        if calls[0]==1:raise StateError('injected real B08 domain failure')
        return original(*args,**kwargs)
    GPRule.priority=domain
    worker.evaluation_worker(conn,rules_desc,plan,seed)


def extra_draw_worker(conn,rules_desc,plan,seed):
    from fogsim.training import worker
    original=worker.run_entry
    def extra(*args,**kwargs):
        for _ in range(137):random.random()
        return original(*args,**kwargs)
    worker.run_entry=extra
    worker.evaluation_worker(conn,rules_desc,plan,seed)


def slow_b08_worker(conn,rules_desc,plan,seed):
    from fogsim.training import worker
    from fogsim.rules.gp import GPRule
    import time
    original=GPRule.priority
    def slow(*args,**kwargs):
        # Marker is sent from an actual B08 scoring call, after engine enters run.
        conn.send(dict(kind='active_config',index=0,config=dict(test_observation='inside_B08_priority')))
        time.sleep(.5)
        return original(*args,**kwargs)
    GPRule.priority=slow
    worker.evaluation_worker(conn,rules_desc,plan,seed)


def invalid_metric_worker(conn,rules_desc,plan,seed):
    from fogsim.training import worker
    original=worker.run_entry
    def invalid(*args,**kwargs):
        raw,archive=original(*args,**kwargs)
        raw['makespan']=None
        return raw,archive
    worker.run_entry=invalid
    worker.evaluation_worker(conn,rules_desc,plan,seed)


def test_result_contract_error_keeps_returned_raw_result(plan,tmp_path,monkeypatch):
    import fogsim.training.evaluation as e
    monkeypatch.setattr(e,'evaluation_worker',invalid_metric_worker)
    with pytest.raises(RemoteEvaluationError) as exc:evaluate_rule_pair(rules(),plan,tmp_path/'invalid-metric')
    assert exc.value.error['classification']=='RESULT_CONTRACT_ERROR'
    raw=read_json(tmp_path/'invalid-metric/failures/exception.json')['partial']['result']
    assert raw['status']=='SUCCEEDED' and raw['makespan'] is None
    assert read_json(tmp_path/'invalid-metric/evaluation.json')['status']=='INCOMPLETE'


def test_wallclock_interrupts_actual_b08_scoring(plan,tmp_path,monkeypatch):
    import fogsim.training.evaluation as e
    monkeypatch.setattr(e,'evaluation_worker',slow_b08_worker)
    p=plan.to_dict();p=_plan(p['split'],p['entries'],dict(wallclock_seconds_per_run=.2))
    result=evaluate_rule_pair(rules(),p,tmp_path/'in-run-timeout').to_dict()
    assert result['status']=='INCOMPLETE' and result['interruption']['classification']=='WALLCLOCK_INTERRUPTED'
    assert read_json(tmp_path/'in-run-timeout/runs/0000/active_config.json')['test_observation']=='inside_B08_priority'
    assert result['completed_runs']==0 and result['fitness'] is None


def test_actual_extra_evolution_draws_leave_simulation_unchanged(plan,monkeypatch,tmp_path):
    import fogsim.training.evaluation as e
    before=random.getstate()
    ordinary=evaluate_rule_pair(rules(),plan).to_dict()
    monkeypatch.setattr(e,'evaluation_worker',extra_draw_worker)
    extra=evaluate_rule_pair(rules(),plan).to_dict()
    write_json(tmp_path/'ordinary.json',ordinary)
    write_json(tmp_path/'extra-evolution-draws.json',extra)
    assert ordinary['runs']==extra['runs'] and ordinary['fitness']==extra['fitness']
    assert ordinary['evolution_rng_unchanged'] and extra['evolution_rng_unchanged'] is False
    assert before==random.getstate()


def test_jsonl_tail_and_finite_canonical_contract(tmp_path):
    from fogsim.training.protocols import append_jsonl,read_jsonl
    path=tmp_path/'progress.jsonl'
    append_jsonl(path,dict(index=0));append_jsonl(path,dict(index=1))
    with path.open('ab') as stream:stream.write(b'{"index":')
    assert read_jsonl(path)==dict(rows=[dict(index=0),dict(index=1)],interrupted_tail=True,tail_bytes=9)
    with pytest.raises(InputError):canonical(dict(value=float('nan')))


def test_utf16_dax_bytes_frozen_exactly(tmp_path):
    import base64
    c=configured(tmp_path)
    folder=tmp_path/'utf16';folder.mkdir()
    raw='<?xml version="1.0" encoding="UTF-16"?><adag><job id="R"/></adag>'.encode('utf-16')
    (folder/'CyberShake_30.xml').write_bytes(raw)
    for name in ['train','validation','test']:
        cfg=read_json(tmp_path/(name+'.json'));cfg['source']['dag_root']=str(folder);write_json(tmp_path/(name+'.json'),cfg)
    p=build_training_plans(c).training[0]
    assert base64.b64decode(p.to_dict()['entries'][0]['templates']['CyberShake_30.xml'])==raw
    actual=evaluate_rule_pair(rules(),p).to_dict()
    write_json(tmp_path/'utf16-evaluation.json',actual)
    assert actual['status']=='FEASIBLE'


def test_actual_domain_error_has_separate_reason(plan,tmp_path,monkeypatch):
    import fogsim.training.evaluation as e
    monkeypatch.setattr(e,'evaluation_worker',domain_worker)
    result=evaluate_rule_pair(rules(),plan,tmp_path/'domain').to_dict()
    assert result['status']=='INFEASIBLE' and result['completed_runs']==2 and result['failed_runs']==1
    assert result['runs'][0]['classification']=='DOMAIN_FAILURE'
    assert result['runs'][0]['reason_code']=='STATE_INVARIANT_VIOLATION'


def test_actual_replay_and_changed_rule_coverage_abort(tmp_path,plan):
    original=evaluate_rule_pair(rules(),plan,tmp_path/'native').to_dict()
    archive=tmp_path/'native'/original['runs'][0]['input_ref']
    cfg=dict(format='fogsim.experiment',schema_version=2,mode='replay',
        source=dict(input_path=str(archive),purpose='reuse_inputs'),run=dict(max_events=2000,trace_enabled=True))
    write_json(tmp_path/'replay.json',cfg)
    entry=_entry(tmp_path/'replay.json','replay','validation',0,dict(trace='all'))
    replay=_plan('validation',[entry],dict(wallclock_seconds_per_run=None))
    result=evaluate_rule_pair(rules(),replay,tmp_path/'replay').to_dict()
    assert result['status']=='FEASIBLE' and result['fitness']==original['runs'][0]['makespan']
    # Complete finite recording may stop too soon for another rule; use an
    # intentionally much slower, still eligible local rule against the capture.
    from fogsim.rules.factory import prepare_rules
    slow=prepare_rules(RuleSpec('routing','fixed_resource','M0'),RuleSpec('sequencing','fcfs'))
    try:
        changed=evaluate_rule_pair(slow,replay,tmp_path/'changed').to_dict()
    except RemoteEvaluationError as exc:
        assert exc.error['classification']=='INPUT_OR_PLAN_ERROR'
        assert exc.evaluation.to_dict()['status']=='INCOMPLETE'
    else:
        # Coverage is only insufficient if a required call actually diverges.
        assert changed['status']=='FEASIBLE'


def test_replay_exhaustion_is_actual_plan_error(tmp_path):
    # Use the supplied complete finite archive, then deliberately reduce its
    # independent accepted statistical target by overriding only runtime config
    # in a test worker to require another input. No production fault flag.
    from fogsim.replay.loader import load_replay_input
    path=ROOT/'tests/fixtures/dynamic_v1/input.json'
    inp=load_replay_input(path)
    from fogsim.replay.engine import create_replay_engine
    engine=create_replay_engine(inp,purpose='reuse_inputs')
    engine.admission.source.position=len(inp.archive.generation_attempts)
    result=engine.run().to_dict()
    write_json(tmp_path/'exhaustion-result.json',result)
    write_json(tmp_path/'original-input.json',inp.to_dict())
    assert result['status']=='FAILED' and result['reason_code']=='REPLAY_INPUT_EXHAUSTED'
    with pytest.raises(EvaluationContractError):classify(result)


def test_unknown_exception_aborts_preserves_chain_and_prior_failure(monkeypatch,plan,tmp_path):
    import fogsim.training.evaluation as e
    monkeypatch.setattr(e,'evaluation_worker',injected_worker)
    p=plan.to_dict();p['entries'][0]['effective_config']['run']['max_events']=1
    # Rebuild a legitimate event-budget entry rather than bypassing identity validation.
    c=configured(tmp_path,train=dict(max_events=1))
    bad=build_training_plans(c).training[0].to_dict()['entries'][0]
    p=_plan('train',[bad,plan.to_dict()['entries'][1],plan.to_dict()['entries'][0]],dict(wallclock_seconds_per_run=None))
    with pytest.raises(RemoteEvaluationError) as exc:evaluate_rule_pair(rules(),p,tmp_path/'fault')
    record=read_json(tmp_path/'fault/evaluation.json')
    assert record['status']=='INCOMPLETE' and record['failed_runs']==1 and record['not_run']==2
    assert 'KeyError' in str(exc.value) and 'TypeError' in str(exc.value)
    assert read_json(tmp_path/'fault/failures/exception.json')['error_type']=='TypeError'
    partial=read_json(tmp_path/'fault/failures/exception.json')['partial']
    assert partial['input']['capture']['complete'] is False
    assert partial['result']['makespan'] is None


def test_wallclock_worker_exit_progress_exception(plan,tmp_path,monkeypatch):
    p=plan.to_dict();p=_plan(p['split'],p['entries'],dict(wallclock_seconds_per_run=1e-9))
    result=evaluate_rule_pair(rules(),p,tmp_path/'timeout').to_dict()
    assert result['status']=='INCOMPLETE' and result['interruption']['classification']=='WALLCLOCK_INTERRUPTED'
    assert result['fitness'] is None and result['completed_runs']==0
    def callback(fact):raise RuntimeError('callback fault')
    with pytest.raises(RuntimeError,match='callback fault'):evaluate_rule_pair(rules(),plan,tmp_path/'callback',on_progress=callback)
    assert read_json(tmp_path/'callback/evaluation.json')['interruption']['classification']=='CONTROLLER_EXCEPTION'
    import fogsim.training.evaluation as e
    monkeypatch.setattr(e,'evaluation_worker',exit_worker)
    result=evaluate_rule_pair(rules(),plan,tmp_path/'exit').to_dict()
    assert result['status']=='INCOMPLETE' and result['interruption']['classification']=='WORKER_EXIT'
    assert not multiprocessing.active_children()


@pytest.mark.parametrize('expression',['(* 1e309 0)','1e309','-1e309','-0.0','(/ 1 -0.0)'])
def test_special_scores_real_b08_unchanged(plan,tmp_path,expression):
    r=rules(expression);result=evaluate_rule_pair(r,plan,tmp_path/'special').to_dict()
    assert result['status']=='FEASIBLE' and result['rule_manifest']==r.rule_manifest
    raw=read_json(tmp_path/'special'/result['runs'][0]['result_ref'])
    assert raw['rule_manifest']==r.rule_manifest and raw['schema_version']==2
    assert raw['decisions']


def test_order_fresh_objects_and_two_rng_streams(plan,tmp_path,monkeypatch):
    a,b=rules('PT'),rules('(+ MRT PT)')
    before=random.getstate()
    first={}
    for name,rule in [('a',a),('b',b),('b-again',b),('a-again',a)]:
        first[name]=evaluate_rule_pair(rule,plan,evolution_seed=700 if name.endswith('again') else 50001).to_dict()
        write_json(tmp_path/(name+'.json'),first[name])
    assert random.getstate()==before
    for name in ['a','b']:
        assert first[name]['fitness']==first[name+'-again']['fitness']
        assert first[name]['runs']==first[name+'-again']['runs']
        assert first[name]['evolution_rng_unchanged']
    # Actual B08 construction, including resources, queues, source and RNG, must be fresh.
    entry=plan.to_dict()['entries'][0]
    from tempfile import TemporaryDirectory
    import base64
    with TemporaryDirectory() as t:
        root=Path(t)
        for n,v in entry['templates'].items():(root/n).write_bytes(base64.b64decode(v))
        cfg=bind_config(entry,a,root)
        x=create_dynamic_context(cfg,prepared_rules=a);y=create_dynamic_context(cfg,prepared_rules=a)
        assert x.engine is not y.engine and x.environment is not y.environment
        assert x.inputs.rng is not y.inputs.rng and x.engine.state is not y.engine.state
        assert x.engine.admission is not y.engine.admission and x.engine.statistics is not y.engine.statistics
        assert all(u is not v for u,v in zip(x.engine.state.resources_by_id.values(),y.engine.state.resources_by_id.values()))
        assert x.engine.initial_cutoff==y.engine.initial_cutoff==0
        old_rng=random.Random(19);state=old_rng.getstate()
        for _ in range(87):random.random()
        xr,yr=x.run().to_dict(),y.run().to_dict()
        write_json(tmp_path/'direct-context-x.json',xr)
        write_json(tmp_path/'direct-context-y.json',yr)
        from fogsim.replay.export_input import export_replay_input
        write_json(tmp_path/'direct-input-x.json',export_replay_input(x.engine,cfg.source).to_dict())
        write_json(tmp_path/'direct-input-y.json',export_replay_input(y.engine,cfg.source).to_dict())
        assert xr==yr
        assert old_rng.getstate()==state
    random.setstate(before)


def test_limits_legacy_deep_parser_untouched(plan,tmp_path):
    def deep(n):return '(+ PT '*n+'PT'+')'*n
    assert evaluate_rule_pair(rules(deep(7)),plan,tmp_path/'height7').to_dict()['status']=='FEASIBLE'
    # B08 parses this depth; only training admission rejects it.
    r=rules(deep(8))
    with pytest.raises(InputError,match='height/node'):evaluate_rule_pair(r,plan,tmp_path/'height8')
    with pytest.raises(InputError,match='height/node'):evaluate_rule_pair(rules(deep(7)),plan,trees=dict(max_nodes=14,init_max_height=2))
    assert not (tmp_path/'height8').exists()


@pytest.mark.parametrize('value',[None,-1,float('nan'),float('inf')])
def test_success_missing_metric_aborts(value):
    with pytest.raises(EvaluationContractError):classify(dict(status='SUCCEEDED',makespan=value))


def test_replay_coverage_errors_and_fixed_program_errors():
    for code in ['REPLAY_INPUT_EXHAUSTED','REPLAY_INPUT_DIVERGENCE']:
        with pytest.raises(EvaluationContractError):classify(dict(status='FAILED',reason_code=code))
    with pytest.raises(EvaluationContractError):classify(dict(status='FAILED',reason_code=None,reason='unexpected program error'))


def test_cli_and_no_deap(config,tmp_path):
    code="""import sys,importlib.abc
class Guard(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,*args):
  if fullname=='deap' or fullname.startswith('deap.'):raise ImportError('DEAP deliberately unavailable')
sys.meta_path.insert(0,Guard())
from fogsim import RunConfig,simulate,load_fixed_instance
from fogsim.training import load_training_config,build_training_plans
assert simulate(load_fixed_instance('data/cases/single_local.json'),RunConfig()).status=='SUCCEEDED'
assert len(build_training_plans(load_training_config('configs/training/B01.json')).training)==4
assert 'deap' not in sys.modules
"""
    run=subprocess.run([sys.executable,'-c',code],cwd=ROOT,capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    from fogsim.training.cli import main
    out=tmp_path/'validate'
    assert main(['validate','--config',str(ROOT/'configs/training/B01.json'),'--output',str(out)])==0
    assert read_json(out/'preflight.json')['simulations_executed']==0
    with pytest.raises(SystemExit) as exc:main(['validate','--config',str(ROOT/'configs/training/B01.json'),'--output',str(out)])
    assert exc.value.code==2
