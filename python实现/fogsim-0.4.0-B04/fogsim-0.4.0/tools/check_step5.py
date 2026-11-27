"""V09-V15: fresh Python business-sampler probes plus original Java components.

This is not a production replay engine. Test-only samplers reconstruct their
script solely from V16 input values; archived references are only compared after
execution. Python and Java RNG algorithms/individual samples are not paired.
"""
from pathlib import Path
import argparse
from contextlib import ExitStack
from dataclasses import asdict, fields, replace
import hashlib
import json
import os
import shutil
import subprocess
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from fogsim import load_experiment_config, create_dynamic_context
from fogsim.experiment_config import EnvironmentConfig, WorkflowTypeRange, DynamicRunConfig
from fogsim.simulation.trace import event_snapshot
from java_support import ORIGINAL, sha, reference_jdk
from check_step3 import first_difference
from dynamic_export_contract import read_json, audit_input, write_json


class ScriptFeed:
    def __init__(self,archive):
        self.values=[];self.calls=[];self.position=0;self.inputs=None;self.roles={}
        def add(role,value):self.values.append(dict(role=role,value=value))
        for d in archive.environment.devices:add('processing_rate_device',d.processing_rate)
        for s in archive.environment.servers:
            suffix='edge' if s.type=='EDGE' else 'cloud'
            add('upload_bandwidth_'+suffix,s.upload_bandwidth);add('download_bandwidth_'+suffix,s.download_bandwidth)
            add('processing_rate_'+suffix,s.processing_rate)
        templates={t.ref:t for t in archive.templates}
        for c in archive.candidates:
            w=c.workflow_input;_,children=templates[w.template_ref].adjacency()
            edges={(e.parent_id,e.child_id):e.data_size for e in w.edges}
            add('workflow_type',w.template_ref.dag_type_id);add('inter_release_time',w.inter_release_time);add('weight',w.weight)
            for task in w.tasks:
                add('workload',task.workload);add('data_size',task.data_size)
                for child in children[task.id]:add('edge_data',edges[task.id,child])

    def attach(self,inputs):
        self.inputs=inputs
        self.roles={id(getattr(inputs.samplers,f.name)):f.name for f in fields(inputs.samplers)}

    def sample(self,sampler,rng):
        if self.position>=len(self.values):raise RuntimeError('scripted business input exhausted; no automatic samples')
        value=self.values[self.position];role=self.roles[id(sampler)]
        if value['role']!=role or rng is not self.inputs.rng:
            raise RuntimeError(f'script order/RNG mismatch at {self.position}: {role}')
        self.calls.append(value);self.position+=1
        return value['value']


def normalize_python(engine,result):
    state=engine.state
    def opt(key,ready,priority):
        t=state.tasks_by_key[key[0],key[1]]
        return dict(workflow_id=key[0],task_java_index=t.java_index,resource_id=key[2],ready_time=ready,priority=priority)
    events=[]
    def event(row):
        wid,tid=row['workflow_id'],row['task_id'];task=state.tasks_by_key[wid,tid] if tid is not None else None
        ex=state.executions_by_task.get((wid,tid)) if task is not None and row['type'] in ('ProcessStartEvent','ProcessFinishEvent') else None
        return dict(kind=row['type'],time=row['time'],producer_device_id=row['owner'],workflow_id=wid,
            task_java_index=task.java_index if task is not None else None,resource_id=row['resource_id'],
            start_time=ex.start_time if ex else None,finish_time=ex.finish_time if ex else None)
    decisions=[];decision_by_sequence={}
    for d in result.decisions:
        options=[opt(score['option'],observation['ready_time'],score['priority'])
                 for score,observation in zip(d['candidates'],d['candidate_state'])]
        selected=next(o for o in options if [o['workflow_id'],state.workflows_by_id[o['workflow_id']].tasks[o['task_java_index']].id,o['resource_id']]==d['selected'])
        converted=dict(event_sequence=d['event_sequence'],clock_time=d['time'],kind=d['kind'].lower(),options=options,selected=selected)
        decisions.append(converted);decision_by_sequence[d['decision_sequence']]=converted
    actions=[]
    for action in engine.initialization_actions:
        if action['kind']=='EMIT':actions.append(dict(event_sequence=None,kind='EMIT',event=event(action['event'])))
    for row in result.events:
        events.append(dict(event(row),event_sequence=row['sequence']))
        for action in row['actions']:
            if action['kind']=='EMIT':actions.append(dict(event_sequence=row['sequence'],kind='EMIT',event=event(action['event'])))
            else:actions.append(dict(event_sequence=row['sequence'],kind='DECISION',decision=decision_by_sequence[action['decision']['decision_sequence']]))
    final_resources=[]
    for r in state.resources_by_id.values():
        queue=[opt(o.key,o.ready_time,o.priority) for o in r.waiting_queue]
        item=dict(id=r.id,available_time=r.available_time,queue=queue,total_processing=r.queued_processing_time,
                  total_occupancy=r.queued_total_time,tasks_completed=r.completed_task_count)
        if r in state.mobile_devices:item['staged_events']=len(engine.event_queue.staging_heaps[r])
        final_resources.append(item)
    return dict(events=events,decisions=decisions,actions=actions,
        final=dict(clock_time=result.final_clock_time,G=result.generated_workflow_count,B=engine.statistics.cutoff_release_time,
            R=result.recorded_workflow_count,statistical_workflow_ids=list(engine.statistics.recorded_workflows),
            completed_workflow_ids=sorted(state.completed_workflows),not_arrived_workflow_ids=list(state.pending_arrivals),
            unfinished_workflow_ids=[wid for wid in state.workflows_by_id if wid not in state.completed_workflows],
            pending_global_events=len(engine.event_queue.global_heap),resources=final_resources))


def controlled_case(directory,output,*,compact=True,trusted_fcfs=False):
    value=read_json(directory/'input.json');archive=audit_input(value)
    # Origin and capture/reference fields cannot affect the actual source.
    cfg=load_experiment_config(ROOT/'configs/examples/step1_dynamic.json')
    env=archive.environment
    cfg=replace(cfg,source=replace(cfg.source,dag_root=(directory/'sources/dax').resolve(),
        seed=value['initial_state']['public_seed'],workflow_types=WorkflowTypeRange(archive.templates[0].dag_type_id,archive.templates[-1].dag_type_id),
        environment=EnvironmentConfig(len(env.devices),sum(s.type=='EDGE' for s in env.servers),sum(s.type=='CLOUD' for s in env.servers),env.devices[0].can_process_tasks)),
        run=DynamicRunConfig(value['effective_config']['num_jobs_recorded'],value['effective_config']['warmup_jobs']))
    feed=ScriptFeed(archive)
    import fogsim.simulation.context as module
    prepare=module.prepare_random_input
    def prep(config):
        inputs=prepare(config);feed.attach(inputs);return inputs
    # Distinct immutable sampler roles are identified by object identity.
    from fogsim.randomness.samplers import make_samplers
    bundle=make_samplers(cfg.source.samplers,cfg.source.workflow_types)
    classes={type(getattr(bundle,f.name)) for f in fields(bundle)}
    def sample(sampler,rng):return feed.sample(sampler,rng)
    from fogsim.simulation.trace import TraceRecorder
    import fogsim.simulation.engine as engine_module
    class OracleRecorder(TraceRecorder):
        def append(self,record):
            # The business oracle compares all actual events/actions and the final
            # state, not duplicate before/after graph snapshots. Production trace
            # stays unchanged; this test recorder retains every compared field.
            super().append({k:v for k,v in record.items() if k not in ('before','after')})
    with ExitStack() as stack:
        if compact:stack.enter_context(patch.object(engine_module,'TraceRecorder',OracleRecorder))
        if trusted_fcfs:
            # This lane evaluates only the existing FCFS body. Repeated complete
            # graph mutation scans are a diagnostic guard, not rule evaluation.
            # Keep production full graph guards and state/queue invariants intact;
            # full-guard equivalence is tested separately on the small fixture.
            import fogsim.rules.selection as selection
            stack.enter_context(patch.object(selection,'graph_fingerprint',lambda context: None))
        stack.enter_context(patch.object(module,'prepare_random_input',prep))
        for cls in classes:stack.enter_context(patch.object(cls,'sample',sample))
        ctx=create_dynamic_context(cfg);result=ctx.run()
    actual=normalize_python(ctx.engine,result)
    # Reference is read only after the production random-source path has finished.
    reference=read_json(directory/'reference.json');native=reference['native_result'];last=reference['final_state']
    expected=dict(events=reference['events'],decisions=reference['decisions'],actions=reference['actions'],
        final={k:native[k] for k in ('clock_time','G','B','R','statistical_workflow_ids','completed_workflow_ids',
                                   'not_arrived_workflow_ids','unfinished_workflow_ids','pending_global_events')} | {'resources':last['resources']})
    # pending array order in Java is accepted ID order, just as input admission order.
    actual['final']['not_arrived_workflow_ids']=sorted(actual['final']['not_arrived_workflow_ids'])
    comparisons={'generated_inputs':first_difference([asdict(c) for c in archive.candidates],[asdict(c) for c in ctx.input_archive.candidates]),
        'attempts':first_difference([asdict(a) for a in archive.generation_attempts],[asdict(a) for a in ctx.input_archive.generation_attempts]),
        'script_calls':None if feed.position==len(feed.values) else {'consumed':feed.position,'available':len(feed.values)},
        'trace_and_final':first_difference(expected,actual)}
    if native['target_reached']:
        comparisons['metrics']=first_difference({'makespan':native['makespan']['value'],'mean_flowtime':native['mean_flowtime']['value']},
            {'makespan':result.makespan,'mean_flowtime':result.mean_flow_time})
    else:
        comparisons['explicit_failure']=None if result.status=='FAILED' and result.makespan is None and result.mean_flow_time is None else {'status':result.status}
    passed=all(v is None for v in comparisons.values())
    report=dict(case=directory.name,passed=passed,priority_guard='trusted_existing_fcfs_body' if trusted_fcfs else 'production_full',trace_recorder='oracle_without_duplicate_state_snapshots' if compact else 'production_full',scope='scripted business samplers through production generation/admission/events; archived Java facts',
        classification=('NORMAL_PARITY_PASSED' if native['target_reached'] else 'EXPECTED_DIFFERENCE_CONFIRMED') if passed else 'FAILED',
        comparisons=comparisons,counts=dict(events=len(actual['events']),decisions=len(actual['decisions']),attempts=len(ctx.input_archive.generation_attempts)),
        python_status=result.status,python_reason_code=result.reason_code)
    output.mkdir(parents=True,exist_ok=True)
    write_json(output/'python-normalized.json',actual);write_json(output/'comparison.json',report)
    write_json(output/'python-result.json',result.to_dict())
    return report


def java_probes(output,explicit):
    java=Path(explicit or os.environ.get('FOGSIM_JAVA') or shutil.which('java') or '').resolve()
    version=reference_jdk(java)
    integrity=read_json(ROOT/'outputs/source-integrity-v2.json')['files']
    for relative,expected in integrity.items():
        if sha(ORIGINAL/relative)!=expected:raise RuntimeError(f'original source changed: {relative}')
    main=ROOT/'tools/java/step5/fogsim/adapter/Step5Probe.java';codec=ROOT/'tools/java/src/fogsim/adapter/Json.java'
    jars=sorted(p for p in (ORIGINAL/'libraries').glob('*.jar') if 'javadoc' not in p.name)
    hashes={str(p.relative_to(ROOT)):sha(p) for p in [*sorted((ORIGINAL/'src').rglob('*.java')),*jars,main,codec,Path(__file__)]}
    fingerprint=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    classes=output/'classes'/fingerprint[:16];classes.mkdir(parents=True,exist_ok=True)
    javac=java.with_name('javac.exe' if java.suffix=='.exe' else 'javac')
    compiler=[str(javac)] if javac.is_file() else [str(java),'-m','jdk.compiler/com.sun.tools.javac.Main']
    cp=os.pathsep.join(map(str,jars))
    command=[*compiler,'-encoding','UTF-8','-cp',cp,'-sourcepath',str(ORIGINAL/'src'),'-d',str(classes),str(main),str(codec)]
    compiled=subprocess.run(command,capture_output=True,text=True,timeout=60)
    (output/'javac-stdout.txt').write_text(compiled.stdout);(output/'javac-stderr.txt').write_text(compiled.stderr)
    write_json(output/'java-build.json',dict(reference_jdk=version,inputs=hashes,fingerprint=fingerprint,source_overlays=[],command=command,exit_code=compiled.returncode,
        compiler_executable_sha256=sha(javac if javac.is_file() else java),
        compiler_modules_sha256=sha(java.parent.parent/'lib/modules') if not javac.is_file() else None))
    if compiled.returncode:raise RuntimeError('Java probe compile failed; see javac-stderr.txt')
    dax=output/'dax';dax.mkdir(exist_ok=True)
    (dax/'CyberShake_30.xml').write_text('<adag><job id="Z"/><job id="a"/><child ref="a"><parent ref="Z"/></child></adag>')
    raw=output/'java-probes.json'
    command=[str(java),'-cp',os.pathsep.join([str(classes),cp]),'fogsim.adapter.Step5Probe',str(raw)]
    run=subprocess.run(command,cwd=output,capture_output=True,text=True,timeout=60)
    (output/'java-stdout.txt').write_text(run.stdout);(output/'java-stderr.txt').write_text(run.stderr)
    write_json(output/'java-run.json',dict(command=command,cwd=str(output),exit_code=run.returncode))
    if run.returncode:raise RuntimeError('Java probes failed; see java-stderr.txt')
    data=read_json(raw)
    items=[op for group in data['lifecycle'] for op in group['operations']]+data['completion']+data['admission']+data['guards']+[data['owner_producer']]
    return dict(passed=all(x['passed'] for x in items),checks=len(items),scope=data['scope'])


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--java');p.add_argument('--output',type=Path,default=ROOT/'outputs/step5')
    p.add_argument('--cases',nargs='*')
    args=p.parse_args(argv);output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    report=dict(passed=False,scope='V09-V15 components and scripted dynamic business input; production replay/V17-V19 NOT_EXECUTED',cases=[])
    try:
        report['java_probes']=java_probes(output,args.java)
        names=args.cases or [p.name for p in sorted((ROOT/'outputs/step4/cases').iterdir())]
        for name in names:
            case=controlled_case(ROOT/'outputs/step4/cases'/name,output/'cases'/name,
                                 trusted_fcfs=name in ('native_multiple_types','native_standard_dax'))
            report['cases'].append(case);print(name,case['classification'],case['comparisons'],flush=True)
        report['passed']=report['java_probes']['passed'] and all(c['passed'] for c in report['cases'])
        report['classification']='NORMAL_PARITY_PASSED' if report['passed'] else 'FAILED'
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc:
        report.update(classification='INFRASTRUCTURE_ERROR',error=f'{type(exc).__name__}: {exc}')
    write_json(output/'checks.json',report);print(json.dumps({k:v for k,v in report.items() if k!='cases'},indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
