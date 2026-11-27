"""Post-run V17 comparison. No reference object is reachable from scheduling rules/source."""
from dataclasses import asdict
import hashlib
import math
from pathlib import Path
from fogsim.errors import InputError
from fogsim.instances.fixed import object_fields, items
from fogsim.replay.loader import read_replay_json
from fogsim.simulation.trace import state_snapshot


def first_difference(expected, actual, path='$'):
    def diff(reason): return dict(path=path, expected=expected, actual=actual, reason=reason)
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in expected:
            if key not in actual: return dict(path=path+'.'+key,reason='missing key')
            d=first_difference(expected[key],actual[key],path+'.'+key)
            if d is not None: return d
        if expected.keys() != actual.keys(): return diff('object fields differ')
        return None
    if isinstance(expected, list) and isinstance(actual, list):
        for i,(a,b) in enumerate(zip(expected,actual)):
            d=first_difference(a,b,f'{path}[{i}]')
            if d is not None: return d
        return None if len(expected)==len(actual) else diff('list length differs after common prefix')
    if type(expected) is bool or type(actual) is bool:
        return None if type(expected) is type(actual) and expected==actual else diff('boolean differs')
    if type(expected) is int and type(actual) is int:
        return None if expected==actual else diff('integer differs')
    if type(expected) in (int,float) and type(actual) in (int,float):
        numeric_fields = ('time','clock_time','priority','available_time','completion_time','ready_time',
            'processing_time','upload_time','download_time','release_time','inter_release_time','workload',
            'data_size','total_input_data','total_output_data','total_processing','total_occupancy','B',
            'makespan','mean_flow_time')
        if type(expected) is not type(actual) and path.rsplit('.',1)[-1] not in numeric_fields:
            return diff('identifier/count numeric type differs')
        if not math.isfinite(expected) or not math.isfinite(actual): return diff('nonfinite comparison')
        if path.endswith('.priority') and expected==actual==0 and math.copysign(1,expected)!=math.copysign(1,actual):
            return diff('priority signed zero differs')
        return None if math.isclose(expected,actual,abs_tol=1e-9,rel_tol=1e-12) else diff('numeric differs')
    return None if type(expected) is type(actual) and expected==actual else diff('value/type differs')


def normalize_python(engine, result, *, include_extended=False):
    """Representation mapping only; no event reordering or missing decisions added."""
    state=engine.state
    def opt(key,ready,priority):
        return dict(workflow_id=key[0],task_java_index=state.tasks_by_key[key[0],key[1]].java_index,
                    resource_id=key[2],ready_time=ready,priority=priority)
    def event(row):
        wid,tid=row['workflow_id'],row['task_id']
        task=state.tasks_by_key[wid,tid] if tid is not None else None
        ex=state.executions_by_task.get((wid,tid)) if task is not None and row['type'] in ('ProcessStartEvent','ProcessFinishEvent') else None
        # Historical V16 producer_device_id contains event owner, not staging.
        record = dict(kind=row['type'],time=row['time'],producer_device_id=row['owner'],workflow_id=wid,
            task_java_index=task.java_index if task else None,resource_id=row['resource_id'],
            start_time=ex.start_time if ex else None,finish_time=ex.finish_time if ex else None)
        if include_extended:
            record.update(owner_device_id=row['owner'],staging_device_id=row['staging_device'])
        return record
    decisions=[];by_sequence={}
    for d in result.decisions:
        options=[opt(score['option'],observation['ready_time'],score['priority'])
            for score,observation in zip(d['candidates'],d['candidate_state'])]
        selected=opt(d['selected'],next(o['ready_time'] for o,s in zip(d['candidate_state'],d['candidates']) if s['option']==d['selected']),
                     next(s['priority'] for s in d['candidates'] if s['option']==d['selected']))
        row=dict(event_sequence=d['event_sequence'],clock_time=d['time'],kind=d['kind'].lower(),options=options,selected=selected)
        decisions.append(row);by_sequence[d['decision_sequence']]=row
    events=[];actions=[]
    for action in engine.initialization_actions:
        if action['kind']=='EMIT': actions.append(dict(event_sequence=None,kind='EMIT',event=event(action['event'])))
    for row in result.events:
        events.append(dict(event(row),event_sequence=row['sequence']))
        for a in row['actions']:
            actions.append(dict(event_sequence=row['sequence'],kind=a['kind'],
                **({'event':event(a['event'])} if a['kind']=='EMIT' else {'decision':by_sequence[a['decision']['decision_sequence']]})))
    def snapshot(snap):
        task_index={tuple(t['key']):t for t in snap['tasks']}
        workflows=[]
        for w in snap['workflows']:
            wid=w['id'];tasks=[]
            for task in state.workflows_by_id[wid].tasks:
                t=task_index[wid,task.id]
                tasks.append(dict(java_index=task.java_index,dispatched=t['dispatched'],completed=t['completed'],
                    options=[dict(workflow_id=wid,task_java_index=task.java_index,**o) for o in t['options']]))
            workflows.append(dict(id=wid,completion_time=w['completion_time'],tasks=tasks))
        resources=[]
        for r in snap['resources']:
            queue=[]
            for key in r['waiting_queue']:
                option=next(o for o in task_index[key[0],key[1]]['options'] if o['resource_id']==key[2])
                queue.append(opt(key,option['ready_time'],option['priority']))
            item=dict(id=r['id'],available_time=r['available_time'],queue=queue,total_processing=r['queued_processing_time'],
                total_occupancy=r['queued_total_time'],tasks_completed=r['completed_task_count'])
            if r['id'] in snap['staged_event_counts']: item['staged_events']=snap['staged_event_counts'][r['id']]
            resources.append(item)
        stats=snap['dynamic_statistics'];completed=set(snap['completed_workflows'])
        return dict(clock_time=snap['clock_time'],G=stats['generated_total'],B=stats['cutoff_release_time'],
            statistical_workflow_ids=stats['recorded_workflow_ids'],
            active_workflow_ids=[w['id'] for w in snap['workflows'] if w['id'] not in completed],resources=resources,workflows=workflows)
    post=[dict(event_sequence=row['sequence'],state=snapshot(row['after'])) for row in result.events]
    final_state=snapshot(engine._snapshot())
    completed=state.completed_workflows
    native=dict(clock_time=result.final_clock_time,G=result.generated_workflow_count,B=engine.statistics.cutoff_release_time,
        R=result.recorded_workflow_count,statistical_workflow_ids=list(engine.statistics.recorded_workflows),
        completed_workflow_ids=[wid for wid in state.workflows_by_id if wid in completed],
        not_arrived_workflow_ids=[wid for wid in state.workflows_by_id if wid in state.pending_arrivals],
        unfinished_workflow_ids=[wid for wid in state.workflows_by_id if wid not in completed],
        pending_global_events=len(engine.event_queue.global_heap))
    value = dict(events=events,decisions=decisions,actions=actions,post_trigger_states=post,final_state=final_state,native=native)
    if include_extended:
        value['pre_trigger_states']=[dict(event_sequence=row['sequence'],state=snapshot(row['before'])) for row in result.events]
        value['event_errors']=[dict(event_sequence=row['sequence'],error=row['error']) for row in result.events]
    return value


def _decode_reference(value):
    from copy import deepcopy
    object_fields(value, ('format','schema_version','events','decisions','actions','post_trigger_states','native_result','final_state','diagnostics'), ('pre_trigger_states','event_errors'), where='reference')
    if value['format']!='fogsim.dynamic-reference' or type(value['schema_version']) is not int or value['schema_version']!=1:
        raise InputError('unsupported dynamic reference')
    for key in ('events','decisions','actions','post_trigger_states'): items(value[key],key,False)
    if len(value['events'])!=len(value['post_trigger_states']): raise InputError('reference lacks post-trigger states')
    extended='pre_trigger_states' in value or 'event_errors' in value
    if extended:
        if not all(k in value for k in ('pre_trigger_states','event_errors')):
            raise InputError('extended reference needs both pre-trigger states and event errors')
        for key in ('pre_trigger_states','event_errors'):
            items(value[key],key,False)
            if [r['event_sequence'] for r in value[key]]!=list(range(1,len(value['events'])+1)):
                raise InputError('extended reference boundary coverage mismatch')
        rows=[*value['events'],*[a['event'] for a in value['actions'] if a['kind']=='EMIT']]
        if any(type(e.get(k)) is not str for e in rows for k in ('owner_device_id','staging_device_id')):
            raise InputError('extended reference lacks actual owner/staging')
    expected=deepcopy(value)
    all_states=[expected['final_state'],*[s['state'] for s in expected['post_trigger_states']]]
    if extended:all_states.extend(s['state'] for s in expected['pre_trigger_states'])
    for state in all_states:
        for w in state['workflows']:
            if w['completion_time']==0.0 and not all(t['completed'] for t in w['tasks']): w['completion_time']=None
            # Explicit retained-vs-cleared edge-map difference; verify the Java observation.
            for t in w['tasks']:
                if t.pop('edge_maps_cleared') is not True: raise InputError('unexpected Java edge-map state')
    native=expected['native_result']
    object_fields(native,('target_reached','clock_time','G','B','R','completed_workflow_ids','statistical_workflow_ids',
        'not_arrived_workflow_ids','unfinished_workflow_ids','pending_global_events','makespan','mean_flowtime'),where='reference.native_result')
    if type(native['target_reached']) is not bool:raise InputError('reference target_reached must be boolean')
    for key in ('makespan','mean_flowtime'):
        descriptor=native[key]
        object_fields(descriptor,('kind','value','java_text'),where='reference.native_result.'+key)
        if descriptor['kind'] not in ('FINITE','DOUBLE_MAX_VALUE','POSITIVE_INFINITY','NEGATIVE_INFINITY','NAN') or type(descriptor['java_text']) is not str:
            raise InputError('invalid Java native metric descriptor')
        value=descriptor['value']
        if descriptor['kind'] in ('FINITE','DOUBLE_MAX_VALUE'):
            if type(value) not in (int,float) or not math.isfinite(value):raise InputError('finite native metric value required')
        elif value is not None:raise InputError('nonfinite native metric must use a null value')
    if [e['event_sequence'] for e in expected['events']]!=list(range(1,len(expected['events'])+1)):
        raise InputError('reference event sequences must be contiguous')
    last=0
    for action in expected['actions']:
        seq=action['event_sequence']
        if seq is None:
            if last:raise InputError('initialization actions must precede event actions')
        elif type(seq) is not int or seq<last or not 1<=seq<=len(expected['events']):
            raise InputError('reference action sequence/order is invalid')
        else:last=seq
    normalized = dict(events=expected['events'],decisions=expected['decisions'],actions=expected['actions'],
        post_trigger_states=expected['post_trigger_states'],final_state=expected['final_state'],
        native={k:native[k] for k in ('clock_time','G','B','R','statistical_workflow_ids','completed_workflow_ids',
            'not_arrived_workflow_ids','unfinished_workflow_ids','pending_global_events')})
    if extended:
        normalized['pre_trigger_states']=expected['pre_trigger_states']
        normalized['event_errors']=expected['event_errors']
    return normalized


def _reference(value):
    try:
        return _decode_reference(value)
    except InputError:
        raise
    except (KeyError,TypeError,IndexError) as exc:
        raise InputError(f'malformed dynamic reference: {exc}') from exc


def _chronological_difference(expected,actual,*,extended):
    """Compare ordinal events with their own before/actions/after/error boundary.

    Grouping uses existing integer sequences and preserves action order; no
    sorting, timestamp alignment, missing-call synthesis or event matching.
    """
    def groups(actions):
        result={}
        for row in actions:result.setdefault(row['event_sequence'],[]).append(row)
        return result
    left,right=groups(expected['actions']),groups(actual['actions'])
    difference=first_difference(left.get(None,[]),right.get(None,[]),'$.actions.initialize')
    if difference is not None:return difference
    for i,(a,b) in enumerate(zip(expected['events'],actual['events'])):
        difference=first_difference(a,b,f'$.events[{i}]')
        if difference is not None:return difference
        if extended:
            difference=first_difference(expected['pre_trigger_states'][i],actual['pre_trigger_states'][i],f'$.pre_trigger_states[{i}]')
            if difference is not None:return difference
        seq=a['event_sequence']
        difference=first_difference(left.get(seq,[]),right.get(seq,[]),f'$.actions.event[{seq}]')
        if difference is not None:return difference
        difference=first_difference(expected['post_trigger_states'][i],actual['post_trigger_states'][i],f'$.post_trigger_states[{i}]')
        if difference is not None:return difference
        if extended:
            difference=first_difference(expected['event_errors'][i],actual['event_errors'][i],f'$.event_errors[{i}]')
            if difference is not None:return difference
    if len(expected['events'])!=len(actual['events']):
        return first_difference(len(expected['events']),len(actual['events']),'$.events.length')
    for key in ('decisions','actions','final_state','native'):
        difference=first_difference(expected[key],actual[key],'$.'+key)
        if difference is not None:return difference
    return None


def _binding(engine, reference, manifest_path, input_path, reference_path):
    if manifest_path is None or input_path is None or reference_path is None:
        return dict(passed=False,reason='manifest and exact input/reference paths required for complete acceptance')
    manifest_path=Path(manifest_path);base=manifest_path.parent.resolve();manifest=read_replay_json(manifest_path)
    if manifest.get('format')!='fogsim.dynamic-manifest' or type(manifest.get('schema_version')) is not int or manifest['schema_version']!=1:
        raise InputError('invalid manifest')
    files=manifest.get('files')
    if not isinstance(files,dict): raise InputError('manifest.files must be object')
    for p in (Path(input_path).resolve(),Path(reference_path).resolve()):
        if not p.is_relative_to(base) or p.relative_to(base).as_posix() not in files:
            raise InputError('manifest does not cover exact input/reference')
    for name,sha in files.items():
        p=(base/name).resolve()
        if not p.is_relative_to(base) or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:
            raise InputError(f'manifest hash mismatch: {name}')
    if read_replay_json(input_path)!=engine.replay_input.to_dict() or read_replay_json(reference_path)!=reference:
        raise InputError('executed input/reference differs from manifest-bound files')
    return dict(passed=True,manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest())


def compare_dynamic_reference(engine, result, reference, *, manifest_path=None, input_path=None, reference_path=None, require_full_trace=False):
    source=engine.admission.source
    if not isinstance(reference,dict):raise InputError('dynamic reference must be an object')
    extended='pre_trigger_states' in reference and 'event_errors' in reference
    report=dict(passed=False,classification='FAILED',first_difference=None,
        tolerance=dict(abs_tol=1e-9,rel_tol=1e-12),
        mappings=['V16 producer_device_id is event owner; Python staging_device retained separately in raw trace',
            'Java jobsInSystem includes Python pending+active in admission order',
            'Java physical completion ID membership is observed in admission order',
            'uncompleted Java completion_time 0 -> None'],
        known_differences=['Java clears edge maps; Python retains immutable archive and runtime edge maps'],
        full_trace_available=extended,full_contract_verified=False,
        trace_coverage='pre/post trigger, owner/staging and errors' if extended else 'legacy post-trigger and owner only',
        scope='input consumption, events, decisions, chronological actions, post-trigger states, final state, statistics, normal metrics; legacy references have no pre-trigger/staging evidence')
    if require_full_trace and not extended:
        report.update(classification='NOT_EXECUTED',reason='strict acceptance requires freshly observed pre-trigger states, owner/staging and errors');return report
    if source.purpose!='verify_reference':
        report.update(classification='NOT_COMPARED',reason='reuse_inputs is a new experiment; original trajectory parity is disabled')
        if result.reason_code in ('REPLAY_INPUT_EXHAUSTED','REPLAY_INPUT_DIVERGENCE'):
            report['classification']='INPUT_COVERAGE_INSUFFICIENT'
        return report
    if result.reason_code=='REPLAY_INPUT_EXHAUSTED':
        report.update(classification='INPUT_COVERAGE_INSUFFICIENT',reason=result.reason);return report
    if not engine.replay_input.capture.is_complete:
        report.update(reason='capture incomplete; full acceptance forbidden');return report
    if not engine.config.trace_enabled:
        report.update(classification='NOT_EXECUTED',reason='detailed trace disabled');return report
    original=engine.replay_input.run_config
    for name in ('num_jobs_recorded','warmup_jobs','statistics_policy','failure_policy','event_policy','routing_rule','sequencing_rule'):
        if getattr(engine.config,name)!=getattr(original,name):
            report.update(reason='active behavior config differs from recorded input: '+name);return report
    initial=engine.replay_input.initial_state
    if (engine.initial_cutoff!=initial.B or engine.public_seed!=initial.public_seed or
            engine.environment.fingerprint!=engine.replay_input.archive.environment.fingerprint):
        report.update(reason='initial B/seed/environment differs from recorded input');return report
    report['binding']=_binding(engine,reference,manifest_path,input_path,reference_path)
    expected=_reference(reference);actual=normalize_python(engine,result,include_extended=extended)
    recorded=engine.replay_input.archive
    consumed=engine.admission.archive
    # Includes diagnostic event sequence, but only after running the real source.
    for key in ('candidates','generation_attempts','admissions'):
        diff=first_difference([asdict(x) for x in getattr(recorded,key)[:len(getattr(consumed,key))]],
                              [asdict(x) for x in getattr(consumed,key)], '$.input_consumption.'+key)
        if diff is not None: report['first_difference']=diff;return report
    diff=_chronological_difference(expected,actual,extended=extended)
    report['first_difference']=diff
    report['counts']=dict(events=len(result.events),decisions=len(result.decisions),attempts=len(consumed.generation_attempts))
    if diff is not None:return report
    if source.position!=len(recorded.generation_attempts):
        # Unconsumed records are legal during ordinary execution, but this exact
        # full Java run must reproduce the export's observed call count.
        report['first_difference']=dict(path='$.input_consumption.count',expected=len(recorded.generation_attempts),actual=source.position);return report
    native=reference['native_result']
    if not native['target_reached']:
        if result.status=='FAILED' and result.reason_code=='EVENTS_EXHAUSTED_BEFORE_TARGET' and result.makespan is None and result.mean_flow_time is None:
            report.update(classification='EXPECTED_DIFFERENCE_CONFIRMED',passed=report['binding']['passed'],
                reason='Java returned nonnormal sentinel metrics; Python explicit failure; not normal parity')
        return report
    if result.status!='SUCCEEDED' or not result.events:
        report['reason']='normal parity requires both successful runs and full events';return report
    diff=first_difference(dict(makespan=native['makespan']['value'],mean_flow_time=native['mean_flowtime']['value']),
                          dict(makespan=result.makespan,mean_flow_time=result.mean_flow_time),'$.metrics')
    report['first_difference']=diff
    if diff is None and report['binding']['passed']:
        report.update(passed=True,classification='NORMAL_PARITY_PASSED',full_contract_verified=extended)
    elif diff is None:
        report.update(classification='NOT_EXECUTED',reason='trajectory comparison matched; provenance binding incomplete')
    return report
