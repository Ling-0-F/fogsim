"""V20/V21 real cleanup/experiment/CLI checks and preparation memory measurement."""
from dataclasses import asdict,replace
import gc
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import tracemalloc

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from fogsim import (load_experiment_config,create_dynamic_context,run_experiment,export_replay_input,
    simulate_replay,load_replay_input,create_replay_engine)
from fogsim.experiment_config import RepeatConfig,parse_experiment_config
from fogsim.model.task import EdgeDataState
from fogsim.io import write_json_atomic


def business(output):
    cfg=load_experiment_config(ROOT/'configs/examples/step5_dynamic.json')
    retained=create_dynamic_context(cfg)
    released=create_dynamic_context(replace(cfg,run=replace(cfg.run,edge_data_policy='release_after_materialization')))
    a,b=retained.run(),released.run()
    def comparable(result):
        value=result.to_dict();value['diagnostics'].pop('edge_data_cleanup');return value
    inp=export_replay_input(released.engine,cfg.source)
    write_json_atomic(output/'python-input.json',inp.to_dict())
    replay=simulate_replay(load_replay_input(output/'python-input.json'))
    write_json_atomic(output/'retain-result.json',a.to_dict());write_json_atomic(output/'release-result.json',b.to_dict())
    write_json_atomic(output/'replay-result.json',replay.to_dict())
    checks=dict(retain_release_identical=comparable(a)==comparable(b),
        archive_identical=retained.input_archive==released.input_archive,rng_identical=retained.snapshot_rng()==released.snapshot_rng(),
        input_alone_replays=replay.status==b.status=='SUCCEEDED' and replay.task_records==b.task_records and replay.workflow_records==b.workflow_records,
        all_maps_released=all(t.edge_data_state==EdgeDataState.RELEASED for t in released.engine.state.tasks_by_key.values()))
    batches={}
    for mode in ('fresh_same_seed','fresh_seed_list','java_rerun'):
        c=replace(cfg,source=replace(cfg.source,seed=None) if mode=='fresh_seed_list' else cfg.source,
            repeat=RepeatConfig(3,mode,(7,-1,42) if mode=='fresh_seed_list' else None))
        result=run_experiment(c);write_json_atomic(output/(mode+'.json'),result.to_dict())
        batches[mode]=dict(status=result.status,completed_runs=len(result.runs),failed_runs=result.failed_runs,
            rng_boundaries=[{k:r.diagnostics[k] for k in ('run_index','rng_start_fingerprint','rng_final_fingerprint','initial_cutoff_release_time','cutoff_release_time','environment_fingerprint')} for r in result.runs])
    for policy in ('retain','release_after_materialization'):
        c=load_experiment_config(ROOT/'configs/examples/step6_verify.json')
        c=replace(c,source=replace(c.source,input_path=(ROOT/'outputs/step4/cases/multi_device_diamond/input.json'),
            reference_path=(ROOT/'outputs/step4/cases/multi_device_diamond/reference.json')),
            run=replace(c.run,edge_data_policy=policy),repeat=RepeatConfig(2,'same_input'))
        result=run_experiment(c);write_json_atomic(output/('java-reference-'+policy+'.json'),result.to_dict())
        checks['java_reference_'+policy]=result.status=='SUCCEEDED' and all(r.diagnostics['comparison_status']=='NORMAL_PARITY_PASSED' for r in result.runs)
    return dict(passed=all(checks.values()) and all(b['status']=='SUCCEEDED' for b in batches.values()),checks=checks,batches=batches)


def memory_measurement(output):
    """Measure preparation only; no claim about complete-run speed or memory."""
    with tempfile.TemporaryDirectory(prefix='step7-memory-',dir=output) as temp:
        directory=Path(temp);n=300
        xml='<adag>'+''.join(f'<job id="T{i}"/>' for i in range(n))+''.join(
            f'<child ref="T{i}"><parent ref="T{i-1}"/></child>' for i in range(1,n))+'</adag>'
        (directory/'CyberShake_30.xml').write_text(xml)
        cfg=load_experiment_config(ROOT/'configs/examples/step5_dynamic.json')
        cfg=replace(cfg,source=replace(cfg.source,dag_root=directory.resolve()))
        rows=[]
        for policy in ('retain','release_after_materialization'):
            gc.collect();tracemalloc.start();start=time.perf_counter()
            ctx=create_dynamic_context(replace(cfg,run=replace(cfg.run,edge_data_policy=policy,trace_enabled=False)))
            elapsed=time.perf_counter()-start;gc.collect();current,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
            entries=sum(len(m) for t in ctx.engine.state.tasks_by_key.values()
                        for m in (t.input_data_by_parent,t.output_data_by_child) if m is not None)
            rows.append(dict(policy=policy,elapsed_seconds=elapsed,current_bytes=current,peak_bytes=peak,
                tasks=len(ctx.engine.state.tasks_by_key),remaining_runtime_mapping_entries=entries,
                cleanup=ctx.engine.cleanup_totals))
            del ctx
        return dict(scope='300-task chain, context/environment/generation/materialization/initialization only; no events executed; full-run performance NOT_MEASURED',
            measurements=rows,conclusion='Measured current/peak/time only; release success does not imply full-run speedup or lower peak')


def cli_checks(output):
    cases=[('dynamic',['dynamic','--config',str(ROOT/'configs/examples/step5_dynamic.json'),'--repeat','2','--repeat-mode','java_rerun','--no-trace','--edge-data-policy','release_after_materialization'],0),
        ('replay',['replay','--config',str(ROOT/'configs/examples/step6_verify.json'),'--repeat','2'],0),
        ('coverage',['replay','--config',str(ROOT/'configs/examples/step6_reuse.json')],1),
        ('invalid',['dynamic','--config',str(ROOT/'configs/examples/step5_dynamic.json'),'--repeat','2'],2)]
    rows=[]
    for name,args,expected in cases:
        path=output/(name+'.json');command=[sys.executable,'-m','fogsim',*args,'--output',str(path)]
        proc=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=60)
        (output/(name+'-stdout.txt')).write_text(proc.stdout);(output/(name+'-stderr.txt')).write_text(proc.stderr)
        rows.append(dict(case=name,command=command,exit_code=proc.returncode,expected_exit_code=expected,
            passed=proc.returncode==expected,output_exists=path.exists()))
    return rows


def main():
    output=ROOT/'outputs/step7/checks';output.mkdir(parents=True,exist_ok=True)
    report=dict(passed=False,status='RUNNING',environment=dict(python=sys.version,platform=platform.platform(),command=sys.argv))
    write_json_atomic(output/'checks.json',report)
    report['business']=business(output)
    report['memory']=memory_measurement(output)
    report['cli']=cli_checks(output)
    report.update(status='COMPLETED',passed=report['business']['passed'] and all(r['passed'] for r in report['cli']))
    write_json_atomic(output/'checks.json',report)
    print(json.dumps(dict(passed=report['passed'],business=report['business']['checks'],memory=report['memory']),indent=2))
    return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
