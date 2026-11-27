"""Fresh, scoped 0.3.0 acceptance. Historical references are never overwritten."""
from pathlib import Path
from dataclasses import replace
import argparse
import json
import sys
import tempfile
import time
import gc
import tracemalloc

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from fogsim import load_replay_input,create_replay_engine,load_experiment_config,create_dynamic_context
from fogsim.errors import PreparationError
from fogsim.replay.loader import read_replay_json
from fogsim.validation.dynamic_compare import compare_dynamic_reference,normalize_python
from fogsim.io import write_json_atomic
from fogsim.experiment_config import EnvironmentConfig, ReplayRunOptions
from java_dynamic_support import compile_dynamic
from export_java_dynamic import export_case
from check_step4 import cases,check_interruption
from check_step5 import java_probes
from check_step6 import fixed_case,negative_cases
from java_support import prepare_and_compile


def fresh_dynamic(output,java):
    output.mkdir(parents=True,exist_ok=True)
    runtime,build=compile_dynamic(output/'java-build',java)
    fixed_runtime=prepare_and_compile(output/'fixed-build',java)
    report=dict(passed=False,status='RUNNING',cases=[],scope='V16 fresh original Java, V17 full pre/post owner/staging/errors, V18 and V19 selected nonempty projections; full production guards/trace')
    write_json_atomic(output/'checks.json',report)
    for name,request,xml,script in cases():
        if name.startswith('native_'):continue
        print(name,'starting',flush=True)
        case=output/'java-cases'/name
        with tempfile.TemporaryDirectory(prefix='final-dax-',dir=output) as temp:
            dax=Path(temp);(dax/'CyberShake_30.xml').write_text(xml)
            capture=export_case(request,dax,case,runtime,build,scripted_values=script,label=name)
        inp=load_replay_input(case/'input.json')
        try:
            engine=create_replay_engine(inp);result=engine.run()
        except PreparationError as exc:engine,result=exc.engine,exc.result
        ref=read_replay_json(case/'reference.json')
        parity=compare_dynamic_reference(engine,result,ref,manifest_path=case/'manifest.json',
            input_path=case/'input.json',reference_path=case/'reference.json',require_full_trace=True)
        actual=output/'python'/name;actual.mkdir(parents=True,exist_ok=True)
        write_json_atomic(actual/'result.json',result.to_dict())
        write_json_atomic(actual/'normalized.json',normalize_python(engine,result,include_extended=True))
        write_json_atomic(actual/'comparison.json',parity)
        fixed=fixed_case(inp,output/'fixed'/name,*fixed_runtime)
        cross=sum(e['owner_device_id']!=e['staging_device_id'] for e in ref['events'])
        release_parity=None
        if name=='multi_device_diamond':
            released=create_replay_engine(inp,ReplayRunOptions(edge_data_policy='release_after_materialization'))
            released_result=released.run()
            release_parity=compare_dynamic_reference(released,released_result,ref,manifest_path=case/'manifest.json',
                input_path=case/'input.json',reference_path=case/'reference.json',require_full_trace=True)
            write_json_atomic(actual/'released-result.json',released_result.to_dict())
            write_json_atomic(actual/'released-comparison.json',release_parity)
        row=dict(case=name,capture=capture,parity=parity,fixed=fixed,actual_cross_device_events=cross,release_parity=release_parity)
        report['cases'].append(row);write_json_atomic(output/'checks.json',report)
        print(name,parity['classification'],fixed['classification'],'cross',cross,flush=True)
    report['interruption']=check_interruption(output,runtime,build)
    report['negative_cases']=negative_cases(output/'negative')
    (output/'lifecycle').mkdir(exist_ok=True)
    report['java_lifecycle_probes']=java_probes(output/'lifecycle',java)
    report['passed']=all(r['capture']['passed'] and r['parity']['passed'] and r['fixed']['passed'] for r in report['cases']) and report['interruption']['passed'] and report['java_lifecycle_probes']['passed'] and all(r['passed'] for r in report['negative_cases']) and all(r['release_parity'] is None or r['release_parity']['passed'] for r in report['cases'])
    report['status']='COMPLETED';write_json_atomic(output/'checks.json',report)
    return report


def performance(output):
    """Same-input full small runs; no inference about paper-scale performance."""
    output.mkdir(parents=True,exist_ok=True);cfg=load_experiment_config(ROOT/'configs/examples/step5_dynamic.json')
    rows=[];facts={}
    for seed in (7,42):
        for policy in ('retain','release_after_materialization'):
            c=replace(cfg,source=replace(cfg.source,seed=seed,environment=EnvironmentConfig(2,1,1,True)),
                      run=replace(cfg.run,trace_enabled=False,edge_data_policy=policy))
            gc.collect();tracemalloc.start();start=time.perf_counter()
            ctx=create_dynamic_context(c);result=ctx.run()
            elapsed=time.perf_counter()-start;gc.collect();current,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
            value=result.to_dict();value['diagnostics'].pop('edge_data_cleanup');facts[seed,policy]=value
            assert ctx.config.run.edge_data_policy==policy
            if policy=='release_after_materialization':
                assert ctx.engine.cleanup_totals['released_task_count']==len(ctx.engine.state.tasks_by_key)
            rows.append(dict(seed=seed,policy=policy,status=result.status,elapsed_seconds=elapsed,current_bytes=current,
                peak_bytes=peak,events=result.processed_event_count,tasks=len(result.task_records),
                cleanup=ctx.engine.cleanup_totals,rng_final=ctx.snapshot_rng().fingerprint))
            del ctx,result
    report=dict(passed=all(r['status']=='SUCCEEDED' for r in rows) and all(facts[seed,'retain']==facts[seed,'release_after_materialization'] for seed in (7,42)),
        scope='full small dynamic run including initialization and event execution; 2 seeds, 2 devices, 1 edge, 1 cloud, trace off; not paper scale',
        measurements=rows,conclusion='measured peak/current/time; no unconditional speedup or scale generalization')
    write_json_atomic(output/'checks.json',report);return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--java');p.add_argument('--output',type=Path,default=ROOT/'outputs/final');p.add_argument('--phase',choices=('dynamic','performance'),required=True)
    args=p.parse_args(argv);output=args.output.resolve()
    result=fresh_dynamic(output/'dynamic',args.java) if args.phase=='dynamic' else performance(output/'performance')
    print(json.dumps(dict(passed=result['passed'],phase=args.phase)),flush=True)
    return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
