"""Controlled S02/S08/S09/S12/S14/S15 cases; no probabilistic branch coverage."""
from copy import deepcopy
from pathlib import Path
import json,random,struct,subprocess,sys,os
import pytest
from fogsim.errors import InputError
from fogsim.training.config import TREES,load_training_config,parse_training_config
from fogsim.training.plans import build_training_plans,parse_training_plan,_plan
from fogsim.training.protocols import write_json,read_json,canonical,read_jsonl
from fogsim.training.deap_adapter import from_expression,to_expression,clone_tree,prepare_single,Individual,check_tree
from fogsim.training.operators import generate,initialize,tournament,select_node,crossover,mutate,reproduce,choose_operator
from fogsim.training.evolution import next_generation,TrialEvaluator,run_trial
from fogsim.training.selection import CandidateArchive,choose_validation,load_selected_rule
from fogsim.training.runtime import run_entry
from fogsim.training.trainer import train

ROOT=Path(__file__).resolve().parents[2]

class Draws:
    def __init__(self,ints=(),reals=()):self.ints=list(ints);self.reals=list(reals);self.bounds=[]
    def randrange(self,start,stop=None):
        if stop is None:start,stop=0,start
        self.bounds.append([start,stop]);x=self.ints.pop(0)
        assert start<=x<stop,(start,stop,x)
        return x
    def random(self):return self.reals.pop(0)


def individual(expr,birth=0,fitness=1,status='FEASIBLE',plan='same'):
    i=Individual(from_expression(expr),f'i{birth}',birth,{})
    i.set_evaluation(dict(plan_id=plan,status=status,fitness=fitness if status=='FEASIBLE' else None))
    return i


def chain(h,feature='PT'):
    for _ in range(h):feature=f'(+ {feature} UT)'
    return feature


@pytest.mark.parametrize('expr',['(- PT UT)','(+ PT PT)','(Min -0.0 0.0)','(/ 1e309 -1e-9999)','(+ .5 (Max 1e-320 -1e309))'])
def test_adapter_identity_order_bits(expr,tmp_path):
    tree=from_expression(expr);prepared=prepare_single(tree)
    from fogsim.rules.factory import prepare_rules
    from fogsim.rules.specs import RuleSpec
    original=prepare_rules(RuleSpec('routing','gp',expression=expr),RuleSpec('sequencing','fcfs'))
    assert prepared.rule_pair_id==original.rule_pair_id
    assert prepared.rule_manifest['expressions']==original.rule_manifest['expressions']
    assert prepared.sequencing_spec.to_dict()=={'kind':'fcfs'}
    cloned=clone_tree(tree);assert cloned is not tree
    assert all(a is not b for a,b in zip(cloned,tree))
    write_json(tmp_path/'roundtrip.json',dict(original=original.rule_manifest,adapted=prepared.rule_manifest))


def test_java_grow_entry_and_full_controlled(tmp_path):
    # Every possible root entry, independently controlling the terminal draw.
    rows=[]
    for entry in range(7):
        rng=Draws([entry,2,4] if entry<6 else [6,9])
        tree=generate(1,'grow',rng)
        assert tree.height==(1 if entry<6 else 0)
        assert rng.bounds[0]==[0,7]
        rows.append(dict(entry=entry,expression=to_expression(tree),bounds=rng.bounds))
    for feature in range(10):assert to_expression(generate(0,'grow',Draws([feature])))==('NIQ','WIQ','MRT','UT','DT','PT','TTIQ','TIS','TWT','NTR')[feature]
    full=generate(2,'full',Draws([0,1,2,3,4,5,6]));assert full.height==2 and len(full)==7
    tree,meta=initialize(TREES,Draws([1,6,5],[.9]));assert to_expression(tree)=='PT' and meta['attempts'][0]['target_height']==1
    write_json(tmp_path/'generation.json',rows)


def test_tournament_replacement_first_tie_and_plan_rejection(tmp_path):
    pop=[individual('PT',0),individual('UT',1),individual('DT',2,2)]
    winner,record=tournament(pop,3,Draws([1,1,0]));assert winner is pop[1]
    assert record['sampled']==['i1','i1','i0']
    winner2,_=tournament([individual('PT',0,status='INFEASIBLE'),pop[2]],2,Draws([0,1]));assert winner2 is pop[2]
    with pytest.raises(RuntimeError):tournament([pop[0],individual('UT',1,plan='different')],2,Draws([0,1]))
    write_json(tmp_path/'tournament.json',record)


@pytest.mark.parametrize('draw,position,eligible',[(.1,0,[0,1]),(.1,1,[0,1]),(.99,0,[2,3,4]),(.99,2,[2,3,4])])
def test_node_categories_root_occurrences(draw,position,eligible,tmp_path):
    t=from_expression('(+ (- PT PT) PT)');i,record=select_node(t,rng=Draws([position],[draw]))
    assert record['eligible_positions']==eligible and i==eligible[position]
    assert select_node(from_expression('PT'),rng=Draws([0],[draw]))[0]==0
    write_json(tmp_path/'node.json',record)


@pytest.mark.parametrize('pair,positions,reals,expected',[
    (('(+ PT UT)','(- DT MRT)'),(0,0),(.1,.1),(True,True)),
    ((chain(7),'(+ PT UT)'),(0,0),(.99,.1),(False,True)),
    (('(+ PT UT)',chain(7)),(0,0),(.1,.99),(True,False)),
    # Node budget independently rejects each direction when neither larger whole tree fits.
])
def test_cross_directional_own_parent_fallback(pair,positions,reals,expected,tmp_path):
    a,b=map(from_expression,pair);before=list(map(to_expression,(a,b)))
    result,meta=crossover(a,b,TREES,rng=Draws(positions,reals))
    assert tuple(meta['attempts'][-1]['legal'])==expected
    for k,ok in enumerate(expected):
        if not ok:assert to_expression(result[k])==before[k]
    assert list(map(to_expression,(a,b)))==before
    for child in result:
        assert all(n is not q for n in child for parent in (a,b) for q in parent)
    write_json(tmp_path/'operation.json',dict(meta=meta,parents=before,children=list(map(to_expression,result))))


def test_tail_checks_only_first_and_multiple_attempts_last(tmp_path):
    a=from_expression('(+ PT UT)');b=from_expression(chain(7))
    children,meta=crossover(a,b,TREES,outputs=1,rng=Draws([0,0],[.1,.99]))
    assert len(children)==1 and meta['attempts'][0]['legal']==[True] and meta['tail_single_output']
    # First attempt fails direction 1; second root/root succeeds. Fixed parents.
    _,multiple=crossover(b,a,TREES,attempts=2,rng=Draws([0,0,0,0],[.99,.1,.1,.1]))
    assert len(multiple['attempts'])==2 and multiple['attempts'][-1]['legal']==[True,True]
    write_json(tmp_path/'tail.json',dict(tail=meta,multiple=multiple))


@pytest.mark.parametrize('height',[0,1,2,3])
def test_mutation_actual_height_0_to_3(height,tmp_path):
    # target remains 3; produce an actual left chain of precisely height.
    def draws(h,depth=0):
        if h==0:return ([6] if depth<3 else [])+[5]
        return [0]+draws(h-1,depth+1)+draws(0,depth+1)
    children,meta=mutate(from_expression('PT'),TREES,rng=Draws([0]+draws(height),[.1]))
    assert meta['attempts'][0]['subtree_height']==height and children[0].height==height
    write_json(tmp_path/'mutation.json',meta)


def test_mutation_failure_clone_and_copy_clear(tmp_path):
    tree=from_expression(chain(7));children,meta=mutate(tree,TREES,rng=Draws([0,0,6,5,6,5],[.99]))
    assert meta['fallback_children']==1 and to_expression(children[0])==to_expression(tree)
    copied,_=reproduce(tree);copied[0][1].name='SUB'
    assert to_expression(tree)==chain(7)
    check_tree(from_expression(chain(7)),TREES)
    with pytest.raises(InputError):check_tree(from_expression(chain(8)),TREES)
    with pytest.raises(InputError):check_tree(from_expression('(+ PT UT)'),dict(TREES,max_nodes=2))
    write_json(tmp_path/'fallback.json',meta)


def test_elite_shortage_order_reproduction_and_no_shared_nodes(monkeypatch,tmp_path):
    cfg=load_training_config(ROOT/'configs/training/smoke-single.json').to_dict()
    cfg['evolution'].update(population_size=3,elite_count=2,operator_weights=dict(crossover=0,mutation=0,reproduction=1))
    pop=[individual('PT',0,2),individual('UT',1,status='INFEASIBLE'),individual('DT',2,status='INFEASIBLE')]
    from fogsim.training import evolution
    monkeypatch.setattr(evolution,'tournament',lambda pop,size:(pop[0],dict(sampled=['i0']*size,winner='i0')))
    children,ops,summary,_=next_generation(pop,cfg,'trial',1,3)
    assert [i.lineage['operator'] for i in children]==['reproduction','reproduction','elite']
    assert summary['elite_count']==1 and summary['accepted_children']==2 and len(ops)==2
    assert all(i.evaluation is None and not i.fitness.valid for i in children)
    assert all(x.tree is not y.tree and all(a is not b for a in x.tree for b in y.tree) for k,x in enumerate(children) for y in children[k+1:])
    write_json(tmp_path/'breeding.json',dict(summary=summary,operations=ops,individuals=[i.record() for i in children]))


def test_archive_dedup_validation_first_occurrence_and_freeze(tmp_path):
    archive=CandidateArchive();a=individual('PT',0,99,plan='p0');b=individual('UT',1,1,plan='p1')
    archive.add(a,0,'a');archive.add(b,1,'b');a.evaluation['plan_id']='p2';a.evaluation['fitness']=.1;archive.add(a,2,'c')
    doc=archive.freeze(tmp_path/'archive.json').to_dict();a.tree[0].value='DT'
    assert len(doc['candidates'])==2 and len(doc['candidates'][0]['occurrences'])==2
    assert doc['candidates'][0]['rules']['routing']['expression']=='PT'
    with pytest.raises(RuntimeError):archive.add(a,3,'d')
    equal=[dict(plan_id='validation',status='FEASIBLE',fitness=10)]*2
    assert choose_validation(doc['candidates'],equal)==0
    assert choose_validation(doc['candidates'],[dict(plan_id='v',status='INFEASIBLE',fitness=None)]*2) is None


class LocalPipe:
    def __init__(self):self.messages=[]
    def send(self,msg):self.messages.append(deepcopy(msg))
    def recv(self):return 'START'


def small_config():
    raw=load_training_config(ROOT/'configs/training/smoke-single.json').to_dict();raw.pop('resolution_root')
    raw['evolution'].update(population_size=2,generations=2,elite_count=1,operator_weights=dict(crossover=0,mutation=0,reproduction=1))
    raw['trials']['evolution_seeds']=[123]
    return parse_training_config(raw,ROOT).to_dict()


def map_plans(cfg):
    from fogsim.training.protocols import Snapshot
    p=build_training_plans(Snapshot(canonical(cfg)))
    return dict(training=[x.to_dict() for x in p.training],validation=p.validation.to_dict(),test=p.test.to_dict())


def test_real_decisions_fcfs_and_different_routing(tmp_path):
    cfg=small_config();p=map_plans(cfg);rows=[]
    ev=TrialEvaluator(LocalPipe(),tmp_path,'decision',TREES)
    before=random.getstate()
    for i,text in enumerate(('PT','(- 0 PT)')):
        value=ev(prepare_single(from_expression(text)),parse_training_plan(p['training'][0]),f'rule-{i}')
        assert value['status']=='FEASIBLE' and value['evolution_rng_unchanged']
        rows.append(value)
    assert random.getstate()==before
    results=[read_json(tmp_path/f'rule-{i}/runs/0000/result.json') for i in range(2)]
    assert results[0]['makespan']!=results[1]['makespan']
    # Assert actual multi-candidate ROUTING decisions and installed FCFS sequencing.
    for result in results:
        assert result['rule_manifest']['bindings']['sequencing']['kind']=='fcfs'
        decisions=result['decisions']
        assert any(d['kind']=='ROUTING' and len(d['candidates'])>1 for d in decisions)
    write_json(tmp_path/'decision-evidence.json',dict(makespans=[r['makespan'] for r in results]))


def test_real_trial_reevaluation_last_generation_and_no_test_switch(tmp_path):
    cfg=small_config();plans=map_plans(cfg);pipe=LocalPipe()
    result=run_trial(pipe,cfg,plans,tmp_path/'trial','t',123)
    assert result['status']=='COMPLETED' and result['generations_evaluated']==2
    gens=read_jsonl(tmp_path/'trial/generations.jsonl')['rows']
    assert gens[-1]['reproduction'] is None
    inds=read_jsonl(tmp_path/'trial/individuals.jsonl')['rows'];assert len(inds)==4
    assert [x['lineage']['operator'] for x in inds[-2:]]==['reproduction','elite']
    evals=read_jsonl(tmp_path/'trial/evaluated-individuals.jsonl')['rows']
    assert [x['plan_id'] for x in evals[:2]]!=[x['plan_id'] for x in evals[2:]]
    assert all(read_json(tmp_path/'trial'/x['evaluation_ref'])['completed_runs']==2 for x in evals)
    frozen=read_json(tmp_path/'trial/selected_rule.json');load_selected_rule(tmp_path/'trial/selected_rule.json')
    assert [m['kind'] for m in pipe.messages].index('selected_rule_frozen')<[i for i,m in enumerate(pipe.messages) if m.get('evaluation_ref')=='test/evaluation.json'][0]
    frozen['rules']['routing']['expression']='PT'
    write_json(tmp_path/'tampered.json',frozen)
    with pytest.raises(InputError):load_selected_rule(tmp_path/'tampered.json')


@pytest.mark.parametrize('phase',['training','validation','test'])
def test_domain_failure_boundaries_real_b08(phase,tmp_path):
    cfg=small_config();plans=map_plans(cfg)
    keys=plans['training'] if phase=='training' else [plans[phase]]
    for original in keys:
        entries=deepcopy(original['entries'])
        for entry in entries:
            entry['effective_config']['run']['max_events']=1
            from fogsim.training.plans import _identities
            from fogsim.training.protocols import content_sha
            entry['scene_id'],entry['input_family_id'],entry['input_content_id']=_identities(entry)
            entry['effective_config_sha256']=content_sha(canonical(entry['effective_config']).encode())
        changed=_plan(original['split'],entries,original['limits']).to_dict()
        original.clear();original.update(changed)
    result=run_trial(LocalPipe(),cfg,plans,tmp_path/'trial','t',123)
    assert result['status']=='DOMAIN_FAILED'
    assert result[dict(training='training_status',validation='validation_status',test='test_status')[phase]]==dict(training='NO_FEASIBLE_INDIVIDUAL',validation='NO_VALIDATION_WINNER',test='TEST_FAILED')[phase]
    assert (tmp_path/'trial/selected_rule.json').exists()==(phase=='test')
    assert (tmp_path/'trial/test').exists()==(phase=='test')
    if phase=='test':
        test=read_json(tmp_path/'trial/test/evaluation.json');assert test['failed_runs']==2 and test['fitness'] is None
        assert len(list((tmp_path/'trial').glob('selected_rule*')))==1


def test_spawn_rng_isolation_and_callback_interruption(tmp_path):
    raw=small_config();raw.pop('resolution_root');cfg=parse_training_config(raw,ROOT)
    before=random.getstate()
    result=train(cfg,tmp_path/'normal').to_dict();assert result['status']=='COMPLETED' and random.getstate()==before
    def fault(msg):
        if msg['kind']=='run_started':raise RuntimeError('controlled callback failure')
    with pytest.raises(RuntimeError,match='controlled callback'):train(cfg,tmp_path/'callback',fault)
    assert random.getstate()==before
    doc=read_json(tmp_path/'callback/trial-0001/failures/interruption.json')
    assert doc['classification']=='CONTROLLER_EXCEPTION'
    raw['limits']['wallclock_seconds_per_run']=1e-9
    result=train(parse_training_config(raw,ROOT),tmp_path/'wallclock').to_dict()
    assert result['status']=='INCOMPLETE' and result['interruption']['classification']=='WALLCLOCK_INTERRUPTED'
    assert read_json(tmp_path/'wallclock/trial-0001/evaluations/000000/evaluation.json')['status']=='INCOMPLETE'


def test_unknown_program_exception_aborts_with_chain(monkeypatch,tmp_path):
    from fogsim.training import evolution
    def broken(*args,**kwargs):raise TypeError('B02 controlled scoring defect')
    monkeypatch.setattr(evolution,'run_entry',broken)
    cfg=small_config()
    with pytest.raises(TypeError,match='scoring defect'):run_trial(LocalPipe(),cfg,map_plans(cfg),tmp_path/'trial','t',123)
    doc=read_json(tmp_path/'trial/evaluations/000000/evaluation.json')
    assert doc['status']=='INCOMPLETE' and doc['interruption']['classification']=='PROGRAM_EXCEPTION'
    assert 'TypeError' in read_json(tmp_path/'trial/failures/exception.json')['traceback']


def test_cross_both_fail_independent_limits_and_exhaustion(tmp_path):
    def full(h):return 'PT' if h==0 else f'(+ {full(h-1)} {full(h-1)})'
    a=from_expression(chain(4,full(3)));b=from_expression(f'(+ (+ {chain(4)} UT) {full(3)})')
    children,meta=crossover(a,b,dict(TREES,max_nodes=31),rng=Draws([4,2],[.1,.1]))
    assert meta['attempts'][0]['legal']==[False,False]
    assert meta['fallback_children']==2
    assert [to_expression(t) for t in children]==[to_expression(a),to_expression(b)]
    _,exhausted=crossover(from_expression(chain(7)),from_expression('(+ PT UT)'),TREES,attempts=2,
        rng=Draws([0,0,0,0],[.99,.1,.99,.1]))
    assert len(exhausted['attempts'])==2 and exhausted['fallback_children']==1
    write_json(tmp_path/'both-fail.json',dict(both=meta,exhausted=exhausted))


def test_operator_exclusive_thresholds_and_structural_defect_propagates(monkeypatch):
    assert [choose_operator(dict(crossover=.8,mutation=.15,reproduction=.05),Draws(reals=[d]))[0]
            for d in (0,.799,.8,.949,.9501,.999)]==['crossover','crossover','mutation','mutation','reproduction','reproduction']
    from fogsim.training import operators
    def defect(*args):raise InputError('controlled invalid tree implementation')
    monkeypatch.setattr(operators,'check_tree',defect)
    with pytest.raises(InputError,match='implementation'):
        crossover(from_expression('PT'),from_expression('UT'),TREES,rng=Draws([0,0],[.1,.1]))


def _early_exit_worker(conn,*args):
    os._exit(42)


def _child_program_defect(*args,**kwargs):
    raise TypeError('spawned controlled program defect')


def _program_error_worker(conn,*args):
    from fogsim.training import evolution
    evolution.run_entry=_child_program_defect
    evolution.trial_worker(conn,*args)


def test_training_controller_worker_exit_and_remote_exception(monkeypatch,tmp_path):
    from fogsim.training import evolution
    from fogsim.training.trainer import RemoteTrainingError
    raw=small_config();raw.pop('resolution_root');cfg=parse_training_config(raw,ROOT)
    monkeypatch.setattr(evolution,'trial_worker',_early_exit_worker)
    result=train(cfg,tmp_path/'exit').to_dict()
    assert result['status']=='INCOMPLETE' and result['interruption']['classification']=='WORKER_EXIT'
    assert result['interruption']['exitcode']==42
    monkeypatch.setattr(evolution,'trial_worker',_program_error_worker)
    with pytest.raises(RemoteTrainingError,match='spawned controlled program defect'):
        train(cfg,tmp_path/'program')
    assert read_json(tmp_path/'program/trial-0001/evaluations/000000/evaluation.json')['status']=='INCOMPLETE'


def test_initialization_finite_exhaustion_and_node_boundary(monkeypatch):
    from fogsim.training import operators
    calls=[]
    def too_large(*args):calls.append(1);return from_expression(chain(8))
    monkeypatch.setattr(operators,'generate',too_large)
    with pytest.raises(InputError,match='exhausted'):
        initialize(dict(TREES,initialization_attempts=2),Draws([1,1],[.1,.1]))
    assert len(calls)==2
    assert select_node(from_expression('(+ PT UT)'),rng=Draws([0],[.9]))[1]['category']=='function'


@pytest.mark.parametrize('value',[None,[],1,True,'PT'])
def test_cli_non_object_rules_are_input_errors(value,tmp_path):
    from fogsim.training.cli import main
    rules=tmp_path/'rules.json';write_json(rules,value)
    output=tmp_path/'must-not-exist'
    with pytest.raises(SystemExit) as exc:
        main(['evaluate','--rules',str(rules),'--plan',str(tmp_path/'not-read-plan.json'),'--output',str(output)])
    assert exc.value.code==2 and not output.exists()
