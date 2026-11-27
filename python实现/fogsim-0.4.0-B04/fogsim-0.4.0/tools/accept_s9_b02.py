"""Assemble only the executed B02 gates, leaving B01/B08 records read-only."""
from pathlib import Path
import argparse,json,xml.etree.ElementTree as ET,hashlib,subprocess
from collections import Counter
from fogsim.training.protocols import write_json,read_json,read_jsonl,source_provenance
from compare_s9_b02 import compare_roots
ROOT=Path(__file__).resolve().parents[1]

def junit(path):
    suites=list(ET.parse(path).getroot().iter('testsuite'))
    return {key:sum(int(s.get(key,0)) for s in suites) for key in ('tests','failures','errors','skipped')}

def audit_trial(root):
    result=read_json(root/'evolution-result.json');generations=read_jsonl(root/'generations.jsonl')['rows']
    inds=read_jsonl(root/'individuals.jsonl')['rows'];evals=read_jsonl(root/'evaluated-individuals.jsonl')['rows']
    ops=read_jsonl(root/'operations.jsonl')['rows'];archive=read_json(root/'candidates/archive.json');selected=read_json(root/'selected_rule.json')
    assert result['status']=='COMPLETED' and len(generations)==4 and len(inds)==len(evals)==48
    assert len({i['individual_id'] for i in inds})==48
    assert all(i['rules']['sequencing']==dict(kind='fcfs') and not i['evaluated'] and not i['fitness_valid'] for i in inds)
    assert generations[-1]['reproduction'] is None
    assert len({g['plan_id'] for g in generations})==4
    assert len({c['rule_pair_id'] for c in archive['candidates']})==len(archive['candidates'])<=4
    assert sum(len(c['occurrences']) for c in archive['candidates'])==4
    for g in generations[:-1]:
        summary=g['reproduction'];relevant=[o for o in ops if f'/g{g["generation"]+1:04d}/' in o['operation_id']]
        assert summary['accepted_children']+summary['elite_count']==12==summary['next_population_size']
        assert summary['accepted_children']==sum(o['accepted_children'] for o in relevant)
        assert summary['fallback_children']==sum(o['fallback_children'] for o in relevant)
        assert summary['operator_selections']=={k:sum(o['operator']==k for o in relevant) for k in ('crossover','mutation','reproduction')}
    calls=0;multi=0;identities=set();completed=0
    for p in root.rglob('evaluation.json'):
        e=read_json(p);assert e['status']=='FEASIBLE' and e['completed_runs']==e['planned_runs']==2
        assert e['evolution_rng_unchanged'];assert e['evaluation_id'] not in identities;identities.add(e['evaluation_id']);calls+=1;completed+=e['completed_runs']
        for run in e['runs']:
            raw=read_json(p.parent/run['result_ref'])
            assert raw['rule_manifest']['rule_pair_id']==e['rule_pair_id']
            multi+=sum(d['kind']=='ROUTING' and len(d['candidates'])>1 for d in raw['decisions'])
    assert calls==48+len(archive['candidates'])+1 and completed==result['completed_simulations']
    test=read_json(root/'test/evaluation.json');assert selected['rule_pair_id']==test['rule_pair_id']
    validation=[read_json(p/'evaluation.json') for p in sorted((root/'validation').iterdir())]
    assert selected['candidate_index']==min(range(len(validation)),key=lambda i:(validation[i]['fitness'],i))
    assert multi>0
    return dict(trial_id=result['trial_id'],seed=result['evolution_seed'],candidates=len(archive['candidates']),
        training_simulations=96,validation_simulations=2*len(archive['candidates']),test_simulations=2,
        completed_simulations=completed,evaluations=calls,multi_candidate_routing_decisions=multi,
        operator_selections=dict(Counter(o['operator'] for o in ops)),accepted_offspring=sum(o['accepted_children'] for o in ops),
        fallback_offspring=sum(o['fallback_children'] for o in ops),selected_rule_id=selected['selected_rule_id'])

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'outputs/step9/B02');a=p.parse_args();out=a.output
    unit=junit(out/'unit-final.xml');regression=junit(out/'regression.xml')
    assert unit['tests']>0 and regression['tests']>=5858
    assert all(x[k]==0 for x in (unit,regression) for k in ('failures','errors','skipped'))
    java=read_json(out/'java-final/checks.json');assert java['passed']
    repeat=compare_roots(out/'single-first',out/'single-repeat');assert repeat['passed'];write_json(out/'reproducibility.json',repeat)
    assert read_json(out/'single-first/resolved_config.json')==read_json(out/'single-repeat/resolved_config.json')
    closure=[]
    for label in ('single-first','single-repeat'):
        for trial in sorted((out/label).glob('trial-*')):closure.append(dict(execution=label,**audit_trial(trial)))
    assert sum(r['completed_simulations'] for r in closure)<=424
    from accept_s9_b01 import audit
    retention=audit();assert retention['passed'];write_json(out/'b08-source-retention.json',retention)
    no_deap=read_json(out/'no-deap.json');assert no_deap['passed']
    frozen=read_json(out/'source-freeze.json')
    from freeze_s9_b02 import files
    assert files()==frozen['files']
    independent=read_json(out/'independent-selected-check.json');assert independent['passed']
    result=dict(format='fogsim.training-acceptance',schema_version=1,batch='S9-B02',design='S9-frozen-1',acceptance_passed=True,
        source=source_provenance(),source_freeze_id=frozen['source_freeze_id'],unit_tests=unit,combined_regression=regression,
        java_local=dict(executed=java['executed'],passed=True,evidence='java-final/checks.json'),closure=closure,
        closure_simulations=sum(r['completed_simulations'] for r in closure),closure_upper_bound=424,reproducibility=repeat,
        gates={k:dict(status='B02_SCOPE_PASSED',scope=scope) for k,scope in {
            'S02':'DEAP adapter ordering/constants/identity, Java grow/full/terminal entry, independent cloning',
            'S08':'same-generation plans, elite/copy re-evaluation, final-generation stop, counts and stable layout',
            'S09':'single routing real multi-candidate decisions, explicit FCFS, controlled tournament/nodes/crossover/mutation',
            'S11':'J01/J02/J03, ordinary single-tree crossover/mutation and J06 actual ECJ local execution; B01 J05 retained',
            'S12':'dedup+all occurrences, frozen candidates, fixed validation, selected-rule freeze before test, failure no-switch',
            'S13':'single mode two evolution seeds, same configuration repeated, every trial semantic artifact compared',
            'S14':'height/node limits, mutation 0..3, finite init retry, real event failures, wallclock and worker exit',
            'S15':'train/API/CLI, lineage and artifacts, independent selected-rule loading, exceptions and output protection',
            'S16':'full current regression in independent restored copy; DEAP-free legacy+selected rule loading'
        }.items()},
        deferred=[dict(gate='S10 / J04',status='NOT_EXECUTED',reason='dual-tree special crossover belongs B03'),
            dict(gate='S13 dual mode',status='NOT_EXECUTED',reason='B03'),
            dict(gate='S01-S17 final joint audit / S17',status='NOT_EXECUTED',reason='B04 final delivery and large-scale template')],
        limitations=['No paper-scale training or dual-tree acceptance.','Java/Python native RNG streams are not compared.',
            'Legacy regression test counts are not simulation counts; no instrumented total is claimed for that lane.',
            'Earlier development failures remain separate from final passed checks.'],
        independent_selected_rule=independent,b08_retention_passed=True,no_deap_passed=True)
    write_json(out/'acceptance.json',result)
    print(json.dumps(dict(acceptance_passed=True,closure_simulations=result['closure_simulations'],unit=unit,regression=regression)))
if __name__=='__main__':main()
