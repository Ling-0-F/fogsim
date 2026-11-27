"""B03 controlled dual-tree contracts, true B08 decisions and process paths."""
from pathlib import Path
from copy import deepcopy
import json,random,subprocess,sys,os
import pytest
from fogsim.errors import InputError
from fogsim.training.config import TREES,load_training_config,parse_training_config
from fogsim.training.deap_adapter import (from_expression,to_expression,prepare_dual,DualIndividual,clone_dual,TreeLimitError)
from fogsim.training.dual_operators import initialize_dual,crossover_dual,mutate_dual,reproduce_dual,check_dual
from fogsim.training.evolution import next_generation,run_trial,TrialEvaluator
from fogsim.training.plans import build_training_plans,parse_training_plan,_entry,_plan,_identities
from fogsim.training.protocols import canonical,read_json,write_json,read_jsonl,content_sha,Snapshot
from fogsim.training.selection import CandidateArchive,load_selected_rule
from fogsim.training.trainer import train,RemoteTrainingError
from test_b02 import Draws,LocalPipe,chain
ROOT=Path(__file__).resolve().parents[2]
ROLES=('sequencing','routing')


def pair(seq='PT',routing='UT'):return tuple(map(from_expression,(seq,routing)))
def expressions(trees):return list(map(to_expression,trees))
def full(h):return 'PT' if h==0 else f'(+ {full(h-1)} {full(h-1)})'
def individual(seq,route,birth=0,fitness=1,status='FEASIBLE'):
    ind=DualIndividual(pair(seq,route),f'd{birth}',birth,{})
    ind.set_evaluation(dict(plan_id='same',status=status,fitness=fitness if status=='FEASIBLE' else None))
    return ind

def disjoint(*genomes):
    groups=[{id(n) for tree in g for n in tree} for g in genomes]
    assert all(not x&y for i,x in enumerate(groups) for y in groups[i+1:])
    for genome in genomes:
        assert genome[0] is not genome[1]
        assert all(a is not b for a in genome[0] for b in genome[1])


def config_small():
    cfg=load_training_config(ROOT/'configs/training/smoke-dual.json').to_dict();cfg.pop('resolution_root')
    cfg['evolution'].update(population_size=2,generations=2,elite_count=1,operator_weights=dict(crossover=0,mutation=0,reproduction=1))
    cfg['trials']['evolution_seeds']=[60001]
    return parse_training_config(cfg,ROOT)

def plans_dict(cfg):
    plans=build_training_plans(cfg)
    return dict(training=[p.to_dict() for p in plans.training],validation=plans.validation.to_dict(),test=plans.test.to_dict())


@pytest.mark.parametrize('seq,route',[('(- PT UT)','(Max NIQ MRT)'),('(+ PT PT)','(+ PT PT)'),('(Min -0.0 0.0)','(/ 1e309 -1e-9999)')])
def test_dual_role_identity_and_constant_roundtrip(seq,route,tmp_path):
    from fogsim.rules.factory import prepare_rules
    from fogsim.rules.specs import RuleSpec
    trees=pair(seq,route);ind=DualIndividual(trees,'d',0,{})
    p=ind.prepare();original=prepare_rules(RuleSpec('routing','gp',expression=route),RuleSpec('sequencing','gp',expression=seq))
    assert p.rule_pair_id==original.rule_pair_id
    assert p.rule_manifest['expressions']==original.rule_manifest['expressions']
    row=ind.record();assert row['roles']=={'0':'sequencing','1':'routing'}
    assert row['rules']['routing']==p.routing_spec.to_dict() and row['rules']['sequencing']==p.sequencing_spec.to_dict()
    disjoint(trees,ind.trees)
    for r in ROLES:assert row['rules'][r]['kind']=='gp'
    write_json(tmp_path/'adaptation.json',dict(original=original.rule_manifest,adapted=p.rule_manifest,individual=row))


def test_dual_init_independent_full_grow_roles(tmp_path):
    # seq: grow at root -> NTR; routing: full target1 -> (+ PT UT).
    trees,meta=initialize_dual(TREES,Draws([1,6,9,1,0,5,3],[.9,.1]))
    assert expressions(trees)==['NTR','(+ PT UT)']
    assert meta['tree_initializations']['sequencing']['attempts'][0]['method']=='grow'
    assert meta['tree_initializations']['routing']['attempts'][0]['method']=='full'
    disjoint(trees,clone_dual(trees))
    with pytest.raises(InputError):prepare_dual([trees[0]])
    with pytest.raises(InputError):check_dual([trees[0]],TREES)
    write_json(tmp_path/'initialization.json',dict(trees=expressions(trees),record=meta))


# Common *inputs*, not injected expected children; four legality combinations.
BRANCHES=[
    ('TT','(+ PT UT)','(- DT MRT)',0,0,[.1,.1],(True,True),255),
    ('TF','(+ PT UT)',chain(7,'DT'),0,0,[.1,.99],(True,False),255),
    ('FT',chain(7),'(+ DT MRT)',0,0,[.99,.1],(False,True),255),
    ('FF',chain(4,full(3)),f'(+ (+ {chain(4)} UT) {full(3)})',4,2,[.1,.1],(False,False),31),
]


@pytest.mark.parametrize('slot',[0,1])
@pytest.mark.parametrize('label,a,b,i,j,reals,legal,nodes',BRANCHES)
def test_j04_four_branches_opposite_complete_fallback(slot,label,a,b,i,j,reals,legal,nodes,tmp_path):
    parents=[list(pair('NIQ','PT')),list(pair('TIS','DT'))]
    parents[0][slot]=from_expression(a);parents[1][slot]=from_expression(b)
    before=[expressions(p) for p in parents]
    children,record=crossover_dual(*parents,dict(TREES,max_nodes=nodes),rng=Draws([slot,i,j],reals))
    assert tuple(record['attempts'][-1]['legal'])==legal
    assert record['tree_slot']==slot and record['role']==ROLES[slot]
    for direction,ok in enumerate(legal):
        source=record['sources'][direction]
        if not ok:
            assert expressions(children[direction])==before[1-direction]
            assert source['fallback_parent']==1-direction
            assert all(o['kind']=='complete_pair_fallback' and o['parent']==1-direction for o in source['trees'].values())
        else:
            assert to_expression(children[direction][1-slot])==before[1-direction][1-slot]
            assert source['trees'][ROLES[1-slot]]['kind']=='whole_tree_swap'
    assert record['fallback_children']==sum(not x for x in legal)
    assert [expressions(p) for p in parents]==before
    disjoint(*parents,*children)
    write_json(tmp_path/'operation.json',dict(parents=before,children=[expressions(p) for p in children],record=record))


@pytest.mark.parametrize('slot',[0,1])
def test_j04_success_preserves_recipient_outside_selected_subtree(slot,tmp_path):
    a=list(pair('NIQ','PT'));b=list(pair('TIS','DT'))
    a[slot]=from_expression('(+ PT (* UT DT))');b[slot]=from_expression('(- MRT NIQ)')
    children,meta=crossover_dual(a,b,TREES,rng=Draws([slot,0,0],[.99,.1]))
    assert to_expression(children[0][slot])=='(+ (- MRT NIQ) (* UT DT))'
    assert to_expression(children[1][slot])=='PT'
    assert meta['sources'][0]['recipient_position']==1
    write_json(tmp_path/'nonroot.json',dict(children=[expressions(p) for p in children],record=meta))


@pytest.mark.parametrize('slot',[0,1])
@pytest.mark.parametrize('first_legal',[True,False])
def test_tail_only_direction_one(slot,first_legal,tmp_path):
    a=list(pair('NIQ','PT'));b=list(pair('TIS','DT'))
    a[slot]=from_expression('(+ PT UT)' if first_legal else chain(7))
    b[slot]=from_expression(chain(7,'DT') if first_legal else '(+ DT MRT)')
    children,meta=crossover_dual(a,b,TREES,attempts=1,outputs=1,rng=Draws([slot,0,0],[.1,.99] if first_legal else [.99,.1]))
    assert len(children)==1 and meta['tail_single_output']
    assert meta['attempts'][0]['legal']==[first_legal]
    if not first_legal:assert expressions(children[0])==expressions(b)
    assert meta['fallback_children']==int(not first_legal)
    write_json(tmp_path/'tail.json',dict(children=[expressions(p) for p in children],record=meta))


@pytest.mark.parametrize('slot',[0,1])
def test_retry_last_attempt_no_direction_stitching(slot,tmp_path):
    a=list(pair('NIQ','PT'));b=list(pair('TIS','DT'))
    a[slot]=from_expression(chain(7));b[slot]=from_expression(chain(7,'DT'))
    children,meta=crossover_dual(a,b,TREES,attempts=2,rng=Draws([slot,0,0,0,0],[.99,.1,.1,.99]))
    assert [r['legal'] for r in meta['attempts']]==[[False,True],[True,False]]
    assert to_expression(children[0][slot])=='DT'
    assert expressions(children[1])==expressions(a) and meta['fallback_children']==1
    assert len(meta['attempts'])==2
    write_json(tmp_path/'retry.json',dict(record=meta,children=[expressions(p) for p in children]))


def test_retry_early_stop_and_tail_ignores_unemitted_direction(tmp_path):
    a=pair(chain(7),'NIQ');b=pair('(+ DT MRT)','TIS')
    rng=Draws([0,0,0,0,0,99],[.99,.1,.1,.1,.5])
    _,meta=crossover_dual(a,b,TREES,attempts=3,rng=rng)
    assert len(meta['attempts'])==2 and meta['attempts'][-1]['legal']==[True,True] and rng.ints==[99]
    rng=Draws([0,0,0,99],[.1,.99,.5])
    _,meta=crossover_dual(b,a,TREES,attempts=3,outputs=1,rng=rng)
    assert len(meta['attempts'])==1 and meta['attempts'][0]['legal']==[True] and rng.ints==[99]
    write_json(tmp_path/'early-stop.json',meta)


@pytest.mark.parametrize('slot',[0,1])
@pytest.mark.parametrize('height',[0,1,2,3])
def test_mutation_selected_role_actual_height(slot,height,tmp_path):
    def draws(h,depth=0):
        if h==0:return ([6] if depth<3 else [])+[5]
        return [0]+draws(h-1,depth+1)+draws(0,depth+1)
    a=pair('PT','UT')
    children,meta=mutate_dual(a,TREES,rng=Draws([slot,0]+draws(height),[.1]))
    assert children[0][slot].height==height and meta['attempts'][0]['subtree_height']==height
    assert to_expression(children[0][1-slot])==to_expression(a[1-slot])
    assert meta['tree_slot']==slot and meta['role']==ROLES[slot]
    disjoint(a,*children)
    write_json(tmp_path/'mutation.json',dict(record=meta,children=[expressions(p) for p in children]))


@pytest.mark.parametrize('slot',[0,1])
def test_mutation_failure_complete_clone_and_retry(slot,tmp_path):
    a=list(pair('NIQ','DT'));a[slot]=from_expression(chain(7))
    children,meta=mutate_dual(a,TREES,attempts=2,rng=Draws([slot,0,0,6,5,6,5,0,6,4],[.99,.99]))
    assert [x['legal'] for x in meta['attempts']]==[False,True]
    assert meta['fallback_children']==0
    children,failed=mutate_dual(a,TREES,rng=Draws([slot,0,0,6,5,6,5],[.99]))
    assert failed['fallback_children']==1 and expressions(children[0])==expressions(a)
    disjoint(a,*children)
    write_json(tmp_path/'failed-mutation.json',dict(retry=meta,failure=failed))


def test_per_tree_limits_and_full_copy(tmp_path):
    both=pair(chain(7),chain(7));check_dual(both,TREES)
    # 255 nodes independently in each tree, not a combined 255-node genome.
    check_dual(pair(full(7),full(7)),TREES)
    with pytest.raises(TreeLimitError):check_dual(pair(chain(8),'PT'),TREES)
    with pytest.raises(TreeLimitError):check_dual(pair('PT',chain(8)),TREES)
    children,meta=reproduce_dual(both);disjoint(both,*children)
    children[0][0][0].name='SUB'
    assert to_expression(both[0])==chain(7)
    write_json(tmp_path/'copy.json',meta)


def test_dual_elite_copy_layout_source_ids_and_reevaluation_state(monkeypatch,tmp_path):
    from fogsim.training import evolution
    cfg=config_small().to_dict();cfg['evolution'].update(population_size=3,elite_count=2)
    pop=[individual('PT','UT',0,5),individual('DT','MRT',1,status='INFEASIBLE'),individual('TIS','TWT',2,status='INFEASIBLE')]
    monkeypatch.setattr(evolution,'tournament',lambda p,size:(p[0],dict(sampled=['d0']*size,winner='d0')))
    children,ops,summary,_=next_generation(pop,cfg,'trial',1,3)
    assert summary['elite_count']==1 and summary['accepted_children']==2
    assert [c.lineage['operator'] for c in children]==['reproduction','reproduction','elite']
    assert all(c.evaluation is None and not c.fitness.valid for c in children)
    assert all(op['sources'][0]['trees'][r]['parent_id']=='d0' for op in ops for r in ROLES)
    disjoint(*(p.trees for p in pop),*(c.trees for c in children))
    write_json(tmp_path/'breeding.json',dict(operations=ops,summary=summary,individuals=[c.record() for c in children]))


def test_dual_archive_immutable_pair_dedup(tmp_path):
    a=individual('PT','UT',0);b=individual('DT','UT',1)
    archive=CandidateArchive();archive.add(a,0,'a');archive.add(b,1,'b');archive.add(a,2,'c')
    doc=archive.freeze(tmp_path/'archive.json').to_dict()
    assert len(doc['candidates'])==2 and len(doc['candidates'][0]['occurrences'])==2
    a.trees[0][0].value='NIQ';a.trees[1][0].value='MRT'
    assert doc['candidates'][0]['rules']==dict(sequencing=dict(kind='gp',expression='PT'),routing=dict(kind='gp',expression='UT'))


def test_true_b08_both_roles_change_multicandidate_decisions(tmp_path):
    cfg=config_small().to_dict()
    entry=_entry(ROOT/'development/b07/evidence/fixed-final/F03-multidevice-queue/config.json','controlled','validation',0,cfg['output'])
    plan=_plan('validation',[entry],cfg['limits']);ev=TrialEvaluator(LocalPipe(),tmp_path,'dual-decision',TREES,'fogsim-training-dual-B03-v1')
    triples=[('PT','PT'),('(- 0 PT)','PT'),('PT','(- 0 PT)')]
    results=[]
    for index,(seq,route) in enumerate(triples):
        result=ev(prepare_dual(pair(seq,route)),plan,f'rule-{index}')
        assert result['status']=='FEASIBLE' and result['evolution_rng_unchanged']
        results.append(read_json(tmp_path/f'rule-{index}/runs/0000/result.json'))
    # Sequencing rules see the same genuinely non-single queue before diverging.
    sequences=[[d for d in result['decisions'] if d['kind']=='SEQUENCING' and len(d['candidates'])>1] for result in results[:2]]
    assert sequences[0] and sequences[1]
    left,right=sequences[0][0],sequences[1][0]
    assert [x['option'] for x in left['candidates']]==[x['option'] for x in right['candidates']]
    assert left['selected']!=right['selected']
    assert any(d['selected']!=d['candidates'][0]['option'] for seqs in sequences for d in seqs)
    routes=[[d for d in result['decisions'] if d['kind']=='ROUTING' and len(d['candidates'])>1] for result in (results[0],results[2])]
    assert routes[0][0]['selected']!=routes[1][0]['selected']
    for result in results:assert all(result['rule_manifest']['bindings'][r]['kind']=='gp' for r in ROLES)
    write_json(tmp_path/'decision-evidence.json',dict(sequencing=[left,right],routing=[r[0] for r in routes],makespans=[r['makespan'] for r in results]))


def test_real_dual_trial_shared_selection_freeze_test_and_last_generation(tmp_path):
    cfg=config_small();pipe=LocalPipe();result=run_trial(pipe,cfg.to_dict(),plans_dict(cfg),tmp_path/'trial','dual',60001)
    assert result['status']=='COMPLETED' and result['mode']=='dual_tree' and result['generations_evaluated']==2
    gens=read_jsonl(tmp_path/'trial/generations.jsonl')['rows'];assert gens[-1]['reproduction'] is None
    inds=read_jsonl(tmp_path/'trial/individuals.jsonl')['rows'];assert len(inds)==4
    assert [i['lineage']['operator'] for i in inds[-2:]]==['reproduction','elite']
    evals=read_jsonl(tmp_path/'trial/evaluated-individuals.jsonl')['rows'];assert len(evals)==4 and len({x['plan_id'] for x in evals})==2
    assert all(read_json(tmp_path/'trial'/e['evaluation_ref'])['completed_runs']==2 for e in evals)
    prepared,selected=load_selected_rule(tmp_path/'trial/selected_rule.json')
    assert prepared.routing_spec.kind==prepared.sequencing_spec.kind=='gp'
    kinds=[m['kind'] for m in pipe.messages]
    assert kinds.index('candidates_frozen')<kinds.index('selected_rule_frozen')<next(i for i,m in enumerate(pipe.messages) if m.get('evaluation_ref')=='test/evaluation.json')


@pytest.mark.parametrize('phase',['training','validation','test'])
def test_dual_domain_failure_no_test_selection(phase,tmp_path):
    cfg=config_small();plans=plans_dict(cfg)
    for plan in (plans['training'] if phase=='training' else [plans[phase]]):
        entries=deepcopy(plan['entries'])
        for e in entries:
            e['effective_config']['run']['max_events']=1
            e['scene_id'],e['input_family_id'],e['input_content_id']=_identities(e)
            e['effective_config_sha256']=content_sha(canonical(e['effective_config']).encode())
        rebuilt=_plan(plan['split'],entries,plan['limits']).to_dict();plan.clear();plan.update(rebuilt)
    result=run_trial(LocalPipe(),cfg.to_dict(),plans,tmp_path/'trial','dual',60001)
    key={'training':'training_status','validation':'validation_status','test':'test_status'}[phase]
    assert result[key]==dict(training='NO_FEASIBLE_INDIVIDUAL',validation='NO_VALIDATION_WINNER',test='TEST_FAILED')[phase]
    assert result['status']=='DOMAIN_FAILED'
    assert (tmp_path/'trial/selected_rule.json').exists()==(phase=='test')
    assert (tmp_path/'trial/test').exists()==(phase=='test')
    if phase=='test':assert read_json(tmp_path/'trial/test/evaluation.json')['failed_runs']==2


def test_dual_spawn_rng_callback_wallclock_and_output_protection(tmp_path):
    cfg=config_small();before=random.getstate()
    result=train(cfg,tmp_path/'normal').to_dict()
    assert result['status']=='COMPLETED' and random.getstate()==before
    with pytest.raises(InputError):train(cfg,tmp_path/'normal')
    def fail(message):
        if message['kind']=='run_started':raise RuntimeError('B03 controlled callback')
    with pytest.raises(RuntimeError,match='controlled callback'):train(cfg,tmp_path/'callback',fail)
    assert random.getstate()==before
    raw=cfg.to_dict();raw.pop('resolution_root');raw['limits']['wallclock_seconds_per_run']=1e-9
    result=train(parse_training_config(raw,ROOT),tmp_path/'wallclock').to_dict()
    assert result['status']=='INCOMPLETE' and result['interruption']['classification']=='WALLCLOCK_INTERRUPTED'


def test_dual_program_fault_preserves_remote_chain(monkeypatch,tmp_path):
    from fogsim.training import evolution
    from test_b02 import _program_error_worker
    monkeypatch.setattr(evolution,'trial_worker',_program_error_worker)
    with pytest.raises(RemoteTrainingError,match='spawned controlled program defect'):train(config_small(),tmp_path/'program')
    result=read_json(tmp_path/'program/trial-0001/evaluations/000000/evaluation.json')
    assert result['status']=='INCOMPLETE' and result['interruption']['classification']=='PROGRAM_EXCEPTION'


def test_breeding_same_parent_exclusive_cross_call_counts_and_tail(monkeypatch,tmp_path):
    from fogsim.training import evolution
    cfg=config_small().to_dict();cfg['evolution'].update(population_size=3,elite_count=0,operator_weights=dict(crossover=1,mutation=0,reproduction=0))
    pop=[individual('NIQ','UT',0),individual('DT','MRT',1)]
    monkeypatch.setattr(evolution,'choose_operator',lambda weights:('crossover',.2))
    monkeypatch.setattr(evolution,'tournament',lambda p,size:(p[0],dict(sampled=['d0']*size,winner='d0')))
    calls=[]
    def controlled(a,b,limits,attempts,outputs):
        slot=len(calls);calls.append(outputs)
        return crossover_dual(a,b,limits,attempts,outputs,Draws([slot,0,0],[.1,.1]))
    monkeypatch.setattr(evolution,'crossover_dual',controlled)
    children,ops,summary,_=next_generation(pop,cfg,'dual',1,2)
    assert calls==[2,1] and summary['operator_selections']==dict(crossover=2,mutation=0,reproduction=0)
    assert summary['accepted_children']==3 and summary['fallback_children']==0 and summary['elite_count']==0
    assert all(o['parents']==['d0','d0'] for o in ops)
    assert ops[-1]['tail_single_output'] and ops[-1]['attempts'][0]['legal']==[True]
    assert [o['tree_slot'] for o in ops]==[0,1]
    assert all(v.get('parent_id')=='d0' or v.get('recipient_id')=='d0' for o in ops for s in o['sources'] for v in s['trees'].values())
    disjoint(*(c.trees for c in children))
    write_json(tmp_path/'exclusive-breeding.json',dict(operations=ops,summary=summary,individuals=[c.record() for c in children]))
