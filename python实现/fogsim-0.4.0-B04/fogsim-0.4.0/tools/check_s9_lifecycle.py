"""Independent original Java runtime plus separately executed B08 Python lifecycle."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from dataclasses import replace, asdict
from java_support import ORIGINAL, reference_jdk, sha

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--java',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
    java=Path(args.java).resolve();env=reference_jdk(java)
    original=ORIGINAL/'src/mengxu/simulation/DynamicSimulation.java'
    before=original.read_text()
    after=before.replace('public void setup(){','public void setup(){\n fogsim.adapter.S9LifeObserver.mark("setup_before_input",this);',1)
    after=after.replace('    public PriorityQueue<AbstractEvent> getEventQueue()',
        '    public PriorityQueue<AbstractEvent> getEventQueue()',1)
    # Insert before the closing brace of setup, identified by its next method.
    anchor='    public PriorityQueue<AbstractEvent> getEventQueue()'
    pos=after.index(anchor);end=after.rfind('    }',0,pos)
    after=after[:end]+'        fogsim.adapter.S9LifeObserver.mark("setup_after_input",this);\n'+after[end:]
    after=after.replace('    public void run(){','    public void run(){\n fogsim.adapter.S9LifeObserver.mark("run_start",this);',1)
    pos=after.index('    public void rerun()');end=after.rfind('    }',0,pos)
    after=after[:end]+'        fogsim.adapter.S9LifeObserver.mark("run_end",this);\n'+after[end:]
    overlay=out/'overlay/mengxu/simulation/DynamicSimulation.java';overlay.parent.mkdir(parents=True,exist_ok=True);overlay.write_text(after)
    (out/'observation.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='original/DynamicSimulation.java',tofile='observed/DynamicSimulation.java')))
    jars=sorted((ORIGINAL/'libraries').glob('*.jar'))
    classes=out/'classes';classes.mkdir(exist_ok=True)
    sources=[overlay,ROOT/'tools/java/src/fogsim/adapter/Json.java',ROOT/'tools/java/step5/fogsim/adapter/Step5Probe.java',ROOT/'tools/java/s9/fogsim/adapter/S9LifeObserver.java']
    cp=os.pathsep.join(map(str,jars))
    command=[str(java.parent/'javac'),'-encoding','UTF-8','-cp',cp,'-sourcepath',os.pathsep.join(map(str,[out/'overlay',ORIGINAL/'src',ROOT/'tools/java/src',ROOT/'tools/java/step5',ROOT/'tools/java/s9'])),'-d',str(classes),*map(str,sources)]
    build=subprocess.run(command,capture_output=True,text=True)
    (out/'compile.stdout').write_text(build.stdout);(out/'compile.stderr').write_text(build.stderr)
    run_cwd=out/'working';(run_cwd/'dax').mkdir(parents=True,exist_ok=True)
    shutil.copy(ROOT/'examples/step5/dax/CyberShake_30.xml',run_cwd/'dax/CyberShake_30.xml')
    run_cmd=[str(java),'-cp',str(classes)+os.pathsep+cp,'fogsim.adapter.S9LifeObserver',str(out/'java.json')]
    manifest=dict(environment=env,source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [original,*sources[1:]]},overlay_sha256=sha(overlay),
        original_sources={p.relative_to(ORIGINAL).as_posix():sha(p) for p in sorted((ORIGINAL/'src').rglob('*.java'))},
        jars={p.name:sha(p) for p in jars},compile_command=command,compile_returncode=build.returncode,
        run_command=run_cmd,run_cwd=str(run_cwd),javac_sha256=sha(java.parent/'javac'),dax_sha256=sha(run_cwd/'dax/CyberShake_30.xml'))
    if build.returncode:
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2));raise RuntimeError(build.stderr)
    run=subprocess.run(run_cmd,cwd=run_cwd,capture_output=True,text=True,timeout=30)
    (out/'run.stdout').write_text(run.stdout);(out/'run.stderr').write_text(run.stderr)
    manifest['run_returncode']=run.returncode
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    if run.returncode:raise RuntimeError(run.stderr)
    raw=json.loads((out/'java.json').read_text());checks=[]
    for case in raw['cases']:
        rows=case['rows'];initial=rows[0]['environment'];samples=case['samples']
        def check(name,condition):checks.append(dict(case=[case['initial_seed'],case['N']],name=name,passed=bool(condition)))
        check('environment retained throughout',all(r['environment']==initial for r in rows))
        check('construction consumes resource prefix',rows[0]['rng']!=case['seed_origin_rng'] and any(x['role'].startswith('rate_') for x in samples[:rows[0]['samples_so_far']]))
        for op in ['rerun','reset','rotateSeed']:
            begin=next(r for r in rows if r['operation']==op and r['boundary']=='before_operation')
            cleared=next(r for r in rows if r['operation']==op and r['boundary']=='setup_before_input')
            generated=next(r for r in rows if r['operation']==op and r['boundary']=='setup_after_input')
            check(op+' clears runtime before input',cleared['clock']==0 and cleared['recorded']==0 and cleared['generated']==0 and cleared['jobs_in_system']==0 and cleared['event_queue']==0 and all(q['queue']==0 for q in cleared['queues']))
            check(op+' retains B before generation',cleared['B']==begin['B'])
            check(op+' input consumes RNG',generated['rng']!=cleared['rng'])
            check(op+' no resource resampling',not any(x['role'].startswith(('rate_','upload_','download_')) for x in samples[begin['samples_so_far']:generated['samples_so_far']]))
            if op=='rerun':check('rerun continues RNG',cleared['rng']==begin['rng'])
            if op in ['reset','rotateSeed']:
                check(op+' resets RNG at independent seed origin',cleared['rng']==case['seed_origin_rng' if op=='reset' else 'rotated_seed_origin_rng'])
            if case['sentinel_B_probe']:check(op+' sentinel B retained after setup',generated['B']==1000000.0)
            else:check(op+' B updated by new input',generated['B']!=cleared['B'])
        end=next(r for r in rows if r['operation']=='rotateSeed' and r['boundary']=='after_operation')
        expected=((case['initial_seed']+10000+2**63)%2**64)-2**63
        check('Java long rotation',end['seed']==expected)
        check('each run observed on both boundaries',len([r for r in rows if r['boundary']=='run_start'])==4 and len([r for r in rows if r['boundary']=='run_end'])==4)
    # Independent Python state contract, never asserting native RNG sample parity.
    from fogsim.experiment_config import load_experiment_config
    from fogsim import create_dynamic_context
    cfg=load_experiment_config(ROOT/'configs/training/train-a.json')
    py=[];ctx=create_dynamic_context(cfg)
    def snap(op,boundary):
        e=ctx.engine
        py.append(dict(operation=op,boundary=boundary,seed=ctx.public_seed,environment=ctx.environment.fingerprint,
            B=ctx.cutoff_release_time,initial_B=e.initial_cutoff,status=e.run_status,clock=e.state.clock_time,
            G=e.statistics.generated_total,R=e.statistics.recorded_total,rng=ctx.inputs.snapshot().fingerprint))
    snap('construct','after')
    for op in ['run','rerun','reset','run_after_reset','rotate_seed','run_after_rotate']:
        snap(op,'before')
        getattr(ctx,'run' if op.startswith('run') else op)()
        snap(op,'after')
    (out/'python.json').write_text(json.dumps(py,indent=2))
    checks.append(dict(name='Python fresh starts B=0 and runtime RNG consumes',passed=py[0]['initial_B']==0 and py[0]['rng']!=py[2]['rng']))
    checks.append(dict(name='Python environment retained in lifecycle',passed=len({r['environment'] for r in py})==1))
    report=dict(format='fogsim.s9-lifecycle-checks',schema_version=1,checks=checks,passed=all(c['passed'] for c in checks),
        scope='J05 only; Java/Python native random values are intentionally not compared')
    (out/'checks.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(passed=report['passed'],checks=len(checks))))
    return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
