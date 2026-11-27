"""B03 gates: independent lineage arithmetic, exact replayed trial artifacts."""
from pathlib import Path
from collections import Counter
import json,argparse
from fogsim.training.protocols import read_json,read_jsonl,write_json,source_provenance
from fogsim.gp.parser import parse_expression
from fogsim.gp.ast import structural_key
from fogsim.training.selection import load_selected_rule
from accept_s9_b02 import junit
from compare_s9_b02 import compare_roots
from freeze_s9_b03 import files,ROOT
ROLES=('sequencing','routing')


def prefix(expr):
    return tuple(tuple(r[:2]) for r in structural_key(parse_expression(expr).root))


def end(nodes,start):
    balance=1;i=start
    while balance:
        balance+=1 if nodes[i][0]=='binary' else -1;i+=1
    return i


def replace_prefix(recipient,i,donor,j):
    return recipient[:i]+donor[j:end(donor,j)]+recipient[end(recipient,i):]


def height(nodes):
    depths=[0];maximum=0
    for node in nodes:
        d=depths.pop();maximum=max(maximum,d)
        if node[0]=='binary':depths.extend((d+1,d+1))
    assert not depths
    return maximum


def legal(nodes,limits):return height(nodes)<=limits['max_height'] and len(nodes)<=limits['max_nodes']


def genome(record):return {r:prefix(record['rules'][r]['expression']) for r in ROLES}


def assert_points(tree,selection):
    indices=[i for i,n in enumerate(tree) if (n[0]=='binary')==(selection['category']=='function')]
    if not indices:indices=[0]
    assert selection['eligible_positions']==indices and selection['index'] in indices
    assert selection['root']==(selection['index']==0)


def audit_lineage(individuals,ops,limits):
    by_id={r['individual_id']:r for r in individuals};checked=0
    for op in ops:
        parents=[genome(by_id[p]) for p in op['parents']]
        role=op['role'];name=op['operator'];actual=[genome(by_id[p]) for p in op['children']]
        if name=='crossover':
            assert ROLES[op['tree_slot']]==role and op['other_role']==ROLES[1-op['tree_slot']]
            for attempt in op['attempts']:
                pa,pb=attempt['nodes'];assert_points(parents[0][role],pa);assert_points(parents[1][role],pb)
                proposals=[replace_prefix(parents[0][role],pa['index'],parents[1][role],pb['index'])]
                if len(actual)==2:proposals.append(replace_prefix(parents[1][role],pb['index'],parents[0][role],pa['index']))
                assert attempt['legal']==[legal(p,limits) for p in proposals]
            last=op['attempts'][-1]
            assert op['fallback_children']==sum(not x for x in last['legal'])
            assert op['tail_single_output']==(len(actual)==1)
            for direction,ok in enumerate(last['legal']):
                donor=1-direction;expected=dict(parents[donor])
                if ok:expected[role]=proposals[direction]
                assert actual[direction]==expected
                origin=op['sources'][direction]
                assert origin['fallback_parent']==(None if ok else donor)
                assert set(origin['trees'])==set(ROLES)
                for r in ROLES:
                    source=origin['trees'][r]
                    if not ok:assert source['kind']=='complete_pair_fallback' and source['parent_id']==op['parents'][donor]
                    elif r!=role:assert source['kind']=='whole_tree_swap' and source['parent_id']==op['parents'][donor]
                    else:assert source['recipient_id']==op['parents'][direction] and source['donor_id']==op['parents'][donor]
        elif name=='mutation':
            assert ROLES[op['tree_slot']]==role and len(actual)==1
            for attempt in op['attempts']:
                assert_points(parents[0][role],attempt['node']);sub=prefix(attempt['subtree'])
                assert height(sub)==attempt['subtree_height']<=limits['mutation_max_height']
                candidate=replace_prefix(parents[0][role],attempt['node']['index'],sub,0)
                assert attempt['legal']==legal(candidate,limits)
            ok=op['attempts'][-1]['legal'];expected=dict(parents[0])
            if ok:expected[role]=candidate
            assert actual[0]==expected and op['fallback_children']==int(not ok)
            origin=op['sources'][0];assert set(origin['trees'])==set(ROLES)
            for r in ROLES:
                if not ok or r!=role:assert origin['trees'][r]['parent_id']==op['parents'][0]
        else:
            assert name=='reproduction' and len(actual)==1 and actual[0]==parents[0]
            assert all(op['sources'][0]['trees'][r]['parent_id']==op['parents'][0] for r in ROLES)
        assert op['accepted_children']==len(actual);checked+=len(actual)
    for child in individuals:
        if child['lineage']['operator']=='elite':
            parent=by_id[child['lineage']['parents'][0]]
            assert genome(child)==genome(parent)
            assert all(child['lineage']['source']['trees'][r]['parent_id']==parent['individual_id'] for r in ROLES)
    return checked


def audit_trial(root,limits):
    result=read_json(root/'evolution-result.json');gens=read_jsonl(root/'generations.jsonl')['rows']
    individuals=read_jsonl(root/'individuals.jsonl')['rows'];evaluations=read_jsonl(root/'evaluated-individuals.jsonl')['rows'];ops=read_jsonl(root/'operations.jsonl')['rows']
    assert result['status']=='COMPLETED' and result['mode']=='dual_tree' and len(gens)==4
    assert len(individuals)==len(evaluations)==48 and len({i['individual_id'] for i in individuals})==48
    assert all(i['roles']=={'0':'sequencing','1':'routing'} and not i['evaluated'] and not i['fitness_valid'] for i in individuals)
    assert all(i['rules'][r]['kind']=='gp' and i['trees'][r]['height']<=7 and i['trees'][r]['nodes']<=255 for i in individuals for r in ROLES)
    checked=audit_lineage(individuals,ops,limits)
    assert checked==33
    by_id={i['individual_id']:i for i in individuals}
    for g,row in enumerate(gens):
        assert row['generation']==g and row['population_size']==12
        if g==3:assert row['reproduction'] is None
        else:
            own=[o for o in ops if f'/g{g+1:04d}/' in o['operation_id']];s=row['reproduction']
            assert s['accepted_children']+s['elite_count']==s['next_population_size']==12
            assert s['accepted_children']==sum(o['accepted_children'] for o in own)
            assert s['fallback_children']==sum(o['fallback_children'] for o in own)
            assert s['operator_selections']=={k:sum(o['operator']==k for o in own) for k in ('crossover','mutation','reproduction')}
            assert s['scores_cleared']
        own=[e for e in evaluations if e['generation']==g];assert len(own)==12 and {e['plan_id'] for e in own}=={row['plan_id']}
        best=min((e for e in own if e['status']=='FEASIBLE'),key=lambda e:(e['fitness'],by_id[e['individual_id']]['birth_sequence']))
        assert best['individual_id']==row['generation_winner']
    assert len({g['plan_id'] for g in gens})==4
    archive=read_json(root/'candidates/archive.json');candidates=archive['candidates']
    assert len({c['rule_pair_id'] for c in candidates})==len(candidates)<=4
    assert sum(len(c['occurrences']) for c in candidates)==4
    for candidate in candidates:
        assert candidate['first_occurrence']==candidate['occurrences'][0]
        for source in candidate['occurrences']:
            assert candidate['rule_pair_id']==by_id[source['individual_id']]['rule_pair_id']
            assert source['individual_id']==gens[source['generation']]['generation_winner']
    multi=Counter();nonfirst=Counter();calls=completed=failed=0;ids=set()
    for p in sorted(root.rglob('evaluation.json')):
        e=read_json(p);assert e['status'] in ('FEASIBLE','INFEASIBLE') and e['completed_runs']==e['planned_runs']==2 and e['evolution_rng_unchanged']
        assert e['evaluation_id'] not in ids;ids.add(e['evaluation_id']);calls+=1;completed+=e['completed_runs'];failed+=e['failed_runs']
        for run in e['runs']:
            raw=read_json(p.parent/run['result_ref']);assert raw['rule_manifest']['rule_pair_id']==e['rule_pair_id']
            for d in raw['decisions']:
                if len(d['candidates'])>1:
                    r=d['kind'].lower();multi[r]+=1;nonfirst[r]+=d['selected']!=d['candidates'][0]['option']
    assert calls==48+len(candidates)+1 and completed==result['completed_simulations']
    assert all(multi[r]>0 for r in ROLES)
    prepared,selected=load_selected_rule(root/'selected_rule.json');selected=selected.to_dict()
    validations=[read_json(p/'evaluation.json') for p in sorted((root/'validation').iterdir())]
    expected=min((i for i,e in enumerate(validations) if e['status']=='FEASIBLE'),key=lambda i:(validations[i]['fitness'],i))
    assert selected['candidate_index']==expected and selected['rule_pair_id']==read_json(root/'test/evaluation.json')['rule_pair_id']==prepared.rule_pair_id
    return dict(trial_id=result['trial_id'],seed=result['evolution_seed'],candidates=len(candidates),training_simulations=96,
        validation_simulations=2*len(candidates),test_simulations=2,completed_simulations=completed,failed_runs=failed,
        multi_candidate_decisions=dict(multi),nonfirst_selected=dict(nonfirst),lineage_offspring_checked=checked,
        operator_selections=dict(Counter(o['operator'] for o in ops)),fallback_offspring=sum(o['fallback_children'] for o in ops),selected_rule_id=selected['selected_rule_id'])


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'outputs/step9/B03');a=p.parse_args();out=a.output
    unit=junit(out/'unit-final.xml');regression=junit(out/'regression.xml')
    assert unit['tests']>=141 and regression['tests']>=5908
    assert all(r[k]==0 for r in (unit,regression) for k in ('failures','errors','skipped'))
    java=read_json(out/'java-final/checks.json');assert java['passed'] and java['executed']==38
    repeat=compare_roots(out/'dual-first',out/'dual-repeat');assert repeat['passed'];write_json(out/'reproducibility.json',repeat)
    cfg=read_json(out/'dual-first/resolved_config.json');assert cfg==read_json(out/'dual-repeat/resolved_config.json')
    trials=[dict(execution=label,**audit_trial(t,cfg['trees'])) for label in ('dual-first','dual-repeat') for t in sorted((out/label).glob('trial-*'))]
    assert sum(t['completed_simulations'] for t in trials)<=424
    frozen=read_json(out/'source-freeze.json');assert files()==frozen['files']
    for name in ('independent-selected-check','no-deap','schema-final','baseline-retention'):
        assert read_json(out/(name+'.json'))['passed']
    progress=read_jsonl(out/'dual-first/progress.jsonl')['rows']
    for trial in ('trial-0001','trial-0002'):
        own=[e for e in progress if e.get('trial_id')==trial]
        frozen_index=next(i for i,e in enumerate(own) if e['kind']=='selected_rule_frozen')
        test_index=next(i for i,e in enumerate(own) if e.get('evaluation_ref')=='test/evaluation.json')
        assert next(i for i,e in enumerate(own) if e['kind']=='candidates_frozen')<frozen_index<test_index
    result=dict(format='fogsim.training-acceptance',schema_version=1,batch='S9-B03',design='S9-frozen-1',acceptance_passed=True,
        source=source_provenance(),source_freeze_id=frozen['source_freeze_id'],unit_tests=unit,combined_regression=regression,
        java_local=dict(executed=38,passed=True,evidence='java-final/checks.json'),closure=trials,
        closure_simulations=sum(t['completed_simulations'] for t in trials),closure_upper_bound=424,reproducibility=repeat,
        baseline='B02 accepted results reused; original B02 full configuration not rerun',
        gates={k:dict(status='B03_SCOPE_PASSED',scope=scope) for k,scope in {
            'S02':'two-role DEAP/B08 identities/constants, independent initialization and cloning',
            'S08':'shared same-generation plans, pair elite/copy re-evaluation, final-generation stop, actual counters',
            'S10':'both real multi-candidate roles, same-role point/other whole swap, all four controlled branches, tails and retries',
            'S11':'38 actual independent Java original dual operators/initialization/mutation controlled cases; prior J01-J03/J05/J06 retained',
            'S12':'unchanged generic archive/fixed validation/freeze-before-test and real failure no-switch paths',
            'S13':'two distinct dual evolution seeds and exact complete-configuration repetition, per trial semantic comparison',
            'S14':'per-tree height/nodes, two mutation slots and 0..3 subtree heights, event failure and wallclock interruption',
            'S15':'dual API/CLI, full two-tree lineage and parent IDs, original results/inputs, independent loader, faults/output protection',
            'S16':'new compatibility regression after modified training source, including single mode and DEAP-free old paths'
        }.items()},
        deferred=[dict(gate='S01-S17 final joint audit / S17',status='NOT_EXECUTED',reason='B04 final delivery and user large-scale template')],
        limitations=['No paper-scale training or B04 acceptance.','Native Java/Python random sequences are not compared.',
            'Early overload diagnostics and cancelled component run are retained as incomplete evidence, not domain fitness.',
            'Legacy regression test counts are not an instrumented total simulation count.'])
    write_json(out/'acceptance.json',result)
    print(json.dumps(dict(acceptance_passed=True,closure_simulations=result['closure_simulations'],unit=unit,regression=regression)))
if __name__=='__main__':main()
