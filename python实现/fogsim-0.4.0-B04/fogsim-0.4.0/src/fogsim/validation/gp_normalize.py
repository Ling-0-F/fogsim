"""Explicit Java/Python representation mappings; no event/decision reordering."""
from copy import deepcopy
from fogsim.errors import InputError
from fogsim.serialization.f64 import encode_f64,decode_f64

MAPPINGS=(
 'Java uncompleted workflow completion_time=0 -> None, guarded by completion_registered/task flags',
 'Java observed_pending_starts (at most one) -> Python pending_start task key',
 'Java native metric descriptor FINITE -> finite value; mean_flowtime -> mean_flow_time',
 'Java cleared edge-map flags are checked True; Python release_after_materialization is checked independently',
 'Source/RNG metadata remains in provenance; scalar observations are never used for scheduling',
)

def _tag(v):
    if type(v) is dict:decode_f64(v);return v
    return encode_f64(v)

def java_fixed(value):
    payload=deepcopy(value['payload'])
    def state(s):
        for r in s['resources']:
            pending=r.pop('observed_pending_starts')
            if len(pending)>1:raise InputError('multiple Java pending starts cannot be normalized')
            r['pending_start']=pending[0] if pending else None
        for w in s['workflows']:
            if not w['completion_registered']:
                if w['completion_time']!=0.:raise InputError('unexpected Java incomplete completion time')
                w['completion_time']=None
    state(payload['final_state'])
    for e in payload['result']['events']:
        state(e['before']);state(e['after'])
    return payload

def python_fixed(engine,result):
    wire=result.to_dict();final_state=wire['final_state'];model=dict(resources=[],workflows=[])
    for r in engine.state.resources_by_id.values():model['resources'].append(dict(id=r.id,type=r.resource_type.value,numeric_id=r.numeric_id,can_process_tasks=r.can_process_tasks if r.resource_type.value=='MOBILE' else None))
    for w in engine.state.workflows_by_id.values():
        model['workflows'].append(dict(id=w.id,owner_device_id=w.owner_device.id,release_time=w.release_time,
            tasks=[dict(id=t.id,numeric_id=i,parents=[p.id for p in t.parents],children=[c.id for c in t.children],options=[dict(resource_id=o.resource.id,processing_time=o.processing_time,upload_time=o.upload_time,download_time=o.download_time) for o in t.options]) for i,t in enumerate(w.tasks)]))
    if wire.get('diagnostics')!={'decision_errors':[]}:raise InputError('fixed normal reference requires empty, known decision diagnostics')
    for k in ['format','schema_version','score_encoding_version','rule_manifest','final_state','diagnostics']:wire.pop(k,None)
    return dict(loaded_model=model,result=wire,final_state=deepcopy(final_state),feature_observations=deepcopy(engine.gp_observations.feature_observations))

def _dynamic_scores(payload, *, require_tags=False):
    def option(o):
        if require_tags:
            # Java v2 is already a wire document. Validate before mapping;
            # accepting raw numbers here would silently repair invalid input.
            decode_f64(o['priority'], field_path='dynamic.option.priority')
        else:
            o['priority']=_tag(o['priority'])
    def decision(d):
        for o in d['options']:option(o)
        option(d['selected'])
    def state(s):
        for r in s['resources']:
            for o in r['queue']:option(o)
        for w in s['workflows']:
            for t in w['tasks']:
                for o in t['options']:option(o)
    for d in payload['decisions']:decision(d)
    for a in payload['actions']:
        if a['kind']=='DECISION':decision(a['decision'])
    for key in ('pre_trigger_states','post_trigger_states'):
        for row in payload[key]:state(row['state'])
    state(payload['final_state'])

def java_dynamic(value):
    p=deepcopy(value['payload'])
    for s in [p['final_state'],*[r['state'] for r in p['pre_trigger_states']],*[r['state'] for r in p['post_trigger_states']]]:
        for w in s['workflows']:
            if not all(t['completed'] for t in w['tasks']):
                if w['completion_time']!=0.:raise InputError('unexpected Java incomplete completion time')
                w['completion_time']=None
            for t in w['tasks']:
                if t.pop('edge_maps_cleared') is not True:raise InputError('Java edge maps not cleared as recorded')
    native=p['native'];normalized={k:native[k] for k in ('clock_time','G','B','R','statistical_workflow_ids','completed_workflow_ids','not_arrived_workflow_ids','unfinished_workflow_ids','pending_global_events','target_reached')}
    for name,target in [('makespan','makespan'),('mean_flowtime','mean_flow_time')]:
        d=native[name]
        if d['kind']!='FINITE':raise InputError('normal GP reference requires finite native metric')
        normalized[target]=d['value']
    p['native']=normalized;_dynamic_scores(p,require_tags=True);return p

def python_dynamic(engine,result):
    from fogsim.validation.dynamic_compare import normalize_python
    if not hasattr(engine,'gp_observations'):raise InputError('full GP reference comparison requires in-run observer')
    if engine.config.edge_data_policy!='release_after_materialization':raise InputError('Java GP dynamic comparison requires recorded release_after_materialization policy')
    for w in engine.state.workflows_by_id.values():
        for t in w.tasks:
            if t.input_data_by_parent is not None or t.output_data_by_child is not None:raise InputError('Python runtime edge maps were not released')
    if result.diagnostics.get('guard_hits') or result.diagnostics.get('decision_errors') or not result.diagnostics.get('initialization_complete'):
        raise InputError('normal dynamic comparison requires initialized run without guard/decision errors')
    # Supply independently observed staging counts to the legacy representation mapping.
    proxy=type('ObservedEngine',(),{})();proxy.__dict__.update(engine.__dict__)
    proxy._snapshot=lambda:engine._snapshot()|dict(staged_event_counts={d.id:len(engine.event_queue.staging_heaps[d]) for d in engine.state.mobile_devices})
    copy=deepcopy(result)
    for event in copy.events:
        frames=engine.gp_observations.boundaries.get(event['sequence'],[])
        if len(frames)!=2:raise InputError('missing in-run before/after staging observations')
        for phase,counts in zip(('before','after'),frames):event[phase]['staged_event_counts']=counts
    p=normalize_python(proxy,copy,include_extended=True)
    for d,actual in zip(p['decisions'],copy.decisions):d.update(rule_id=actual['rule_id'],round=actual['round'])
    p['native'].update(target_reached=result.status=='SUCCEEDED' and result.recorded_workflow_count>=engine.config.num_jobs_recorded,makespan=result.makespan,mean_flow_time=result.mean_flow_time)
    p['feature_observations']=deepcopy(engine.gp_observations.feature_observations)
    _dynamic_scores(p);return p
