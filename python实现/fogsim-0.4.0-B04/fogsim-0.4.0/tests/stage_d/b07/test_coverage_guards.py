from copy import deepcopy
import pytest
from fogsim.serialization.f64 import encode_f64
from stage_d_b07.coverage import fixed_coverage,dynamic_coverage

@pytest.mark.parametrize('attack',['missing','single','nonfirst','owners','queue','not-gp'])
def test_F03_never_accepts_offline_single_or_first_candidate(fixed_data,record,attack):
    c,p=fixed_data('F03-multidevice-queue');assert fixed_coverage(c,p)['passed']
    rows=[d for d in p['result']['decisions'] if d['kind']=='SEQUENCING' and len(d['candidates'])>=2]
    if attack=='missing':p['result']['events']=[]
    elif attack=='single':
        for d in rows:d['candidates']=d['candidates'][:1];d['candidate_state']=d['candidate_state'][:1];d['selected']=d['candidates'][0]['option']
    elif attack=='nonfirst':
        for d in rows:d['selected']=d['candidates'][0]['option']
    elif attack=='owners':
        for d in rows:
            for x in d['candidate_state']:x['owner_numeric_id']=0
    elif attack=='queue':
        for d in rows:
            for r in d['resource_state']:r['queue']=[]
    else:c['sequencing_rule']={'kind':'fcfs'}
    report=fixed_coverage(c,p);assert not report['passed'];record(report)

@pytest.mark.parametrize('attack',['branch-order','join-wait','reservation-order'])
def test_F02_requires_actual_order_and_join_wait(fixed_data,record,attack):
    c,p=fixed_data('F02-gp-gp');assert fixed_coverage(c,p)['passed']
    if attack=='branch-order':
        ds=p['result']['decisions'];indices=[i for i,d in enumerate(ds) if d['kind']=='ROUTING' and d['candidates'][0]['option'][:2] in ([0,'A'],[0,'B'])]
        ds[indices[0]],ds[indices[1]]=ds[indices[1]],ds[indices[0]]
    elif attack=='join-wait':
        for e in p['result']['events']:
            if e['type']=='ProcessFinishEvent' and e['workflow_id']==0 and e['task_id'] in ('A','B'):
                for t in e['after']['tasks']:
                    if t['key']==[0,'J']:t['dispatched']=True
    else:
        for e in p['result']['events']:
            if e['type']=='ProcessFinishEvent' and e['workflow_id']==0 and e['task_id']=='R':e['actions'].reverse()
    report=fixed_coverage(c,p);assert not report['passed'];record(report)

@pytest.mark.parametrize('resource',['M0','E0','C0'])
@pytest.mark.parametrize('sign',['positive','negative'])
def test_F05_cannot_replace_event_history_with_fresh_sum(fixed_data,record,resource,sign):
    c,p=fixed_data(f'F05-{resource}-{sign}');assert fixed_coverage(c,p)['passed']
    paths={(w['id'],t['id'],o['resource_id']):o for w in p['loaded_model']['workflows'] for t in w['tasks'] for o in t['options']}
    for d in p['result']['decisions']:
        if d['kind']=='SEQUENCING':
            for r in d['resource_state']:
                if r['id']==resource:
                    rebuilt=0.
                    for key in r['queue']:rebuilt+=paths[tuple(key)]['processing_time']
                    r['queued_processing_time']=rebuilt
    report=fixed_coverage(c,p);assert not report['passed'];record(report)

@pytest.mark.parametrize('family,name',[('F01','F01-chain'),('F04','F04-state-routing')])
def test_state_sensitive_scene_requires_actual_feature_reads(fixed_data,record,family,name):
    c,p=fixed_data(name);assert fixed_coverage(c,p)['passed']
    p['feature_observations']=[]
    report=fixed_coverage(c,p);assert not report['passed'];record(report)

@pytest.mark.parametrize('kind',['NAN','POSITIVE_INFINITY','NEGATIVE_INFINITY','POSITIVE_ZERO','NEGATIVE_ZERO'])
def test_F06_requires_special_scores_in_actual_both_roles(fixed_data,record,kind):
    c,p=fixed_data('F06-'+kind);assert fixed_coverage(c,p)['passed']
    p['result']['decisions']=[d for d in p['result']['decisions'] if d['kind']!='SEQUENCING']
    report=fixed_coverage(c,p);assert not report['passed'];record(report)

@pytest.mark.parametrize('attack',['nonfirst','owners','actual-queue','join-wait'])
def test_dynamic_shared_coverage_cannot_be_inferred_from_config(dynamic_data,record,attack):
    c,p,inp,_=dynamic_data();assert dynamic_coverage(c,p,inp)['passed']
    if attack=='nonfirst':
        for d in p['decisions']:
            if d['kind']=='sequencing':d['selected']=deepcopy(d['options'][0])
    elif attack=='owners':
        for x in inp['candidates']:x['workflow_input']['owner_device_id']='M0'
    elif attack=='actual-queue':
        for row in p['pre_trigger_states']:
            for r in row['state']['resources']:r['queue']=[]
    else:
        for row in p['post_trigger_states']:
            for w in row['state']['workflows']:w['tasks'][3]['dispatched']=True
    report=dynamic_coverage(c,p,inp);assert not report['passed'];record(report)
