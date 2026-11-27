"""Coverage is computed from actual ordered runs, independently on each side."""
import math
import struct
from fogsim.serialization.f64 import decode_f64,encode_f64

def bits(x):return struct.pack('>d',float(x)).hex()
def number(x):return decode_f64(x)
def fclass(x):
    x=number(x)
    return ('NAN' if math.isnan(x) else 'POSITIVE_INFINITY' if x==math.inf else
        'NEGATIVE_INFINITY' if x==-math.inf else 'NEGATIVE_ZERO' if x==0. and bits(x).startswith('8') else
        'POSITIVE_ZERO' if x==0. else 'FINITE')
def finish(checks,evidence):return dict(passed=bool(checks) and all(checks.values()),checks=checks,evidence=evidence)
def task_state(snapshot,wid,name):return next(t for t in snapshot['tasks'] if t['key']==[wid,name])
def reads(row):return {r['name']:r['value'] for r in row['reads'] if r['kind']=='feature'}
def durations(payload):
    return {(w['id'],t['id'],o['resource_id']):o for w in payload['loaded_model']['workflows'] for t in w['tasks'] for o in t['options']}
def finite(value):
    if type(value) is float:return math.isfinite(value)
    if type(value) is dict:return all(finite(v) for v in value.values())
    if type(value) is list:return all(finite(v) for v in value)
    return True

def fixed_coverage(case,payload):
    result=payload['result'];ds=result['decisions'];events=result['events'];obs=payload['feature_observations']
    checks=dict(succeeded=result['status']=='SUCCEEDED',all_workflows_completed=result['completed_workflow_count']==len(case['instance']['workflows']),
        actual_event_coverage=bool(events) and result['processed_event_count']==len(events),physical_values_finite=finite(payload))
    proof=dict(events=len(events),decisions=len(ds))
    family=case['family']
    if family=='F01':
        workflow=case['instance']['workflows'][0];root=workflow['tasks'][0]['id'];successor=workflow['tasks'][1]['id']
        rr=[r for r in obs if r['role']=='routing' and r['option'][:2]==[workflow['id'],root]]
        sr=[r for r in obs if r['role']=='routing' and r['option'][:2]==[workflow['id'],successor]]
        paths=durations(payload)
        records=result['task_records']
        checks.update(nonzero_actual_communication=any(paths[(r['workflow_id'],r['task_id'],r['resource_id'])]['upload_time']>0 and paths[(r['workflow_id'],r['task_id'],r['resource_id'])]['download_time']>0 for r in records),
            root_TWT=bool(rr) and all(reads(r).get('TWT')==encode_f64(0.) for r in rr),
            successor_TWT=bool(sr) and all(reads(r).get('TWT')==encode_f64(r['time']) for r in sr),
            finish_registered_NTR=bool(sr) and all(reads(r).get('NTR')==encode_f64(float(len(workflow['tasks'])-1)) for r in sr),
            successor_two_rounds=[d['round'] for d in ds if d['kind']=='ROUTING' and d['candidates'][0]['option'][:2]==[workflow['id'],successor]]==[1,2])
        proof.update(root_reads=rr,successor_reads=sr)
    elif family=='F02':
        branch=[(d['candidates'][0]['option'][1],d['round']) for d in ds if d['kind']=='ROUTING' and d['candidates'][0]['option'][0]==0 and d['candidates'][0]['option'][1] in ('A','B')]
        checks['A1_B1_A2_B2']=branch==[('A',1),('B',1),('A',2),('B',2)]
        waits=[];join=[];reservations=[]
        for e in events:
            if e['workflow_id']==0 and e['type']=='ProcessFinishEvent' and e['task_id'] in ('A','B'):
                after=e['after'];states=[task_state(after,0,t)['completed'] for t in ('A','B')]
                if sum(states)==1:waits.append(dict(event_sequence=e['sequence'],join_not_dispatched=not task_state(after,0,'J')['dispatched']))
                if all(states):join.append(dict(event_sequence=e['sequence'],join_dispatched=task_state(after,0,'J')['dispatched']))
            if e['workflow_id']==0 and e['type']=='ProcessFinishEvent' and e['task_id']=='R':
                actions=e['actions']
                seq=[i for i,a in enumerate(actions) if a['kind']=='DECISION' and a['decision']['kind']=='SEQUENCING']
                reserve=[i for i,a in enumerate(actions) if a['kind']=='EMIT' and a['event']['type']=='ProcessStartEvent']
                route=[i for i,a in enumerate(actions) if a['kind']=='DECISION' and a['decision']['kind']=='ROUTING']
                ordered=bool(seq and reserve and route) and seq[0]<reserve[0]<route[0]
                unchanged=False
                if ordered:
                    rid=actions[reserve[0]]['event']['resource_id']
                    before=next(r for r in e['before']['resources'] if r['id']==rid)
                    during=next(r for r in actions[route[0]]['decision']['resource_state'] if r['id']==rid)
                    unchanged=bits(before['available_time'])==bits(during['available_time'])
                reservations.append(dict(event_sequence=e['sequence'],sequencing_indices=seq,reservation_indices=reserve,routing_indices=route,ordered=ordered,MRT_not_advanced=unchanged))
        checks.update(real_join_wait=bool(waits) and all(x['join_not_dispatched'] for x in waits),
            join_after_both_parents=bool(join) and all(x['join_dispatched'] for x in join),
            sequencing_reservation_before_successor_routing=bool(reservations) and all(x['ordered'] for x in reservations),
            reservation_does_not_advance_MRT=bool(reservations) and all(x['MRT_not_advanced'] for x in reservations))
        proof.update(branch_order=branch,join_waits=waits,join_dispatch=join,reservations=reservations,
            routing=case['routing_rule']['kind'],sequencing=case['sequencing_rule']['kind'])
    elif family=='F03':
        qualifying=[]
        for d in ds:
            if d['kind']!='SEQUENCING' or len(d['candidates'])<2:continue
            keys=[s['option'] for s in d['candidates']]
            owners={x['owner_numeric_id'] for x in d['candidate_state']}
            queue=next(r['queue'] for r in d['resource_state'] if r['id']==keys[0][2])
            qualifying.append(dict(event_sequence=d['event_sequence'],time=d['time'],candidates=keys,owners=sorted(owners),
                selected_index=keys.index(d['selected']),queue=queue,scores=[s['priority'] for s in d['candidates']]))
        checks.update(real_multidevice_wait=any(len(x['owners'])>=2 and x['queue']==x['candidates'] for x in qualifying),
            GP_sequencing_active=case['sequencing_rule']['kind']=='gp',
            real_GP_selected_nonfirst=any(len(x['owners'])>=2 and x['selected_index']>=1 for x in qualifying),
            specified_scores_and_time=any(bits(x['time'])==bits(12.) and x['scores']==[encode_f64(-2.),encode_f64(-4.)] and x['selected_index']==1 for x in qualifying))
        proof['actual_multicandidate_decisions']=qualifying
    elif family=='F04':
        route=[d for d in ds if d['kind']=='ROUTING'];paths=durations(payload)
        signature=lambda d:[(s['option'][2],*[bits(paths[tuple(s['option'])][k]) for k in ('processing_time','upload_time','download_time')]) for s in d['candidates']]
        changed=len(route)>=2 and signature(route[0])==signature(route[1]) and route[0]['selected'][2]!=route[1]['selected'][2]
        rr=[r for r in obs if r['role']=='routing']
        checks.update(identical_durations_different_actual_choice=changed,
            MRT_and_WIQ_actually_read=bool(rr) and all({'MRT','WIQ'}<=set(reads(r)) for r in rr),
            distinct_actual_state=len({tuple((r['id'],bits(r['available_time']),bits(r['queued_processing_time'])) for r in d['resource_state']) for d in route})>=2)
        proof.update(route_states=[dict(event_sequence=d['event_sequence'],selected=d['selected'],durations=signature(d),resources=d['resource_state']) for d in route],reads=rr)
    elif family=='F05':
        target=case['target_resource'];probe=case['instance']['workflows'][-1]['id'];paths=durations(payload)
        pr=[r for r in obs if r['role']=='routing' and r['option']==[probe,'T',target]]
        pd=[d for d in ds if d['kind']=='ROUTING' and d['candidates'][0]['option'][:2]==[probe,'T']]
        empty=bool(pd) and next(r for r in pd[0]['resource_state'] if r['id']==target)
        nonempty=[]
        for d in ds:
            if d['kind']!='SEQUENCING':continue
            rs=next(r for r in d['resource_state'] if r['id']==target)
            if not rs['queue']:continue
            rebuilt=0.
            for key in rs['queue']:rebuilt+=paths[tuple(key)]['processing_time']
            nonempty.append(dict(event_sequence=d['event_sequence'],queue=rs['queue'],cache_bits=bits(rs['queued_processing_time']),
                rebuilt_bits=bits(rebuilt),total_cache_bits=bits(rs['queued_total_time']),historical_residual_read=bits(rs['queued_processing_time'])!=bits(rebuilt)))
        visit=[e for e in events if e['type']=='TaskVisitEvent' and e['resource_id']==target and e['after']['resources']]
        before_probe=reads(pr[0]) if pr else {}
        checks.update(actual_queue_events=bool(visit),actual_nonempty_history_residual=any(x['historical_residual_read'] for x in nonempty),
            empty_branch_actually_read=bool(pr and empty) and empty['queue']==[],
            WIQ_TTIQ_both_actually_read=bool(pr) and {'WIQ','TTIQ'}<=set(before_probe),
            read_matches_real_cache=bool(pr and empty) and before_probe.get('WIQ')==encode_f64(empty['queued_processing_time']) and before_probe.get('TTIQ')==encode_f64(empty['queued_total_time']))
        if target.startswith('M'):
            residual=number(before_probe['WIQ']) if 'WIQ' in before_probe else 0.
            checks['local_empty_historical_signed_residual']=residual>0 if case['residual_sign']=='positive' else residual<0
        else:
            checks['server_empty_positive_zero']=before_probe.get('WIQ')==before_probe.get('TTIQ')==encode_f64(0.)
        proof.update(target_resource=target,nonempty_cache_reads=nonempty,empty_probe=pr,empty_resource_state=empty,
            cache_values_never_assigned_by_fixture=True)
    elif family=='F06':
        desired=case['score_class']
        route=[s['priority'] for d in ds if d['kind']=='ROUTING' for s in d['candidates']]
        sequence=[s['priority'] for d in ds if d['kind']=='SEQUENCING' for s in d['candidates']]
        checks.update(routing_special_class=bool(route) and all(fclass(x)==desired for x in route),
            sequencing_special_class=bool(sequence) and all(fclass(x)==desired for x in sequence))
        proof.update(score_class=desired,routing_score_bits=[x['bits'] for x in route],sequencing_score_bits=[x['bits'] for x in sequence])
    else:raise ValueError('unknown fixed coverage family')
    return finish(checks,proof)

def dynamic_coverage(case,payload,input_document):
    """Observe native-statistics stop, real joins, source owners and shared queues."""
    events=payload['events'];ds=payload['decisions'];native=payload['native']
    records={c['record_id']:c['workflow_input'] for c in input_document['candidates']}
    accepted={records[a['candidate_ref']]['candidate_id']:records[a['candidate_ref']]
        for a in input_document['generation_attempts'] if a['observed_acceptance']}
    owners={wid:w['owner_device_id'] for wid,w in accepted.items()}
    checks=dict(actual_complete_capture=input_document['capture']['complete'] is True,
        target_reached=native['target_reached'] is True and native['R']>=case['N'],
        original_statistics_lifecycle=native['R']==len(native['statistical_workflow_ids']),
        physical_values_finite=finite(payload),actual_GP_observations=bool(payload['feature_observations']),
        both_rule_roles_executed=all(any(d['kind']==role for d in ds) for role in ('routing','sequencing')))
    shared=[]
    for d in ds:
        if d['kind']!='sequencing' or len(d['options'])<2:continue
        key=lambda x:[x['workflow_id'],x['task_java_index'],x['resource_id']]
        keys=[key(o) for o in d['options']];selected=key(d['selected'])
        pre=payload['pre_trigger_states'][d['event_sequence']-1]['state']
        queue=next(r['queue'] for r in pre['resources'] if r['id']==keys[0][2])
        shared.append(dict(event_sequence=d['event_sequence'],time=d['clock_time'],candidates=keys,
            selected=selected,selected_index=keys.index(selected),owner_devices=sorted({owners[k[0]] for k in keys}),
            candidates_still_in_actual_waiting_queue=[key(o) for o in queue]==keys,
            scores=[o['priority'] for o in d['options']]))
    waits=[]
    if case['shape']=='fork_join':
        for e in events:
            if e['kind']!='ProcessFinishEvent' or e['task_java_index'] not in (1,2):continue
            w=next(w for w in payload['post_trigger_states'][e['event_sequence']-1]['state']['workflows'] if w['id']==e['workflow_id'])
            branches=[w['tasks'][i]['completed'] for i in (1,2)]
            if sum(branches)==1:
                waits.append(dict(event_sequence=e['event_sequence'],workflow_id=w['id'],join_waiting=not w['tasks'][3]['dispatched']))
        checks['actual_fork_join_wait']=bool(waits) and all(w['join_waiting'] for w in waits)
    if case['require_shared_nonfirst']:
        checks.update(two_devices_really_waiting=any(len(d['owner_devices'])>=2 and d['candidates_still_in_actual_waiting_queue'] for d in shared),
            actual_multidevice_GP_nonfirst=any(len(d['owner_devices'])>=2 and d['selected_index']>=1 and d['candidates_still_in_actual_waiting_queue'] for d in shared))
    if not case['local']:
        checks.update(no_local_option=all(not o['resource_id'].startswith('M') for c in input_document['candidates'] for t in c['workflow_input']['tasks'] for o in t['options']),
            no_local_selected=all(not d['selected']['resource_id'].startswith('M') for d in ds),
            environment_disables_local=all(not d['can_process_tasks'] for d in input_document['environment']['devices']))
    return finish(checks,dict(events=len(events),decisions=len(ds),attempts=len(input_document['generation_attempts']),
        G=native['G'],B=native['B'],R=native['R'],statistical_workflow_ids=native['statistical_workflow_ids'],
        unfinished_workflows_at_native_stop=native['unfinished_workflow_ids'],
        shared_multicandidate_decisions=shared,actual_join_waits=waits))
