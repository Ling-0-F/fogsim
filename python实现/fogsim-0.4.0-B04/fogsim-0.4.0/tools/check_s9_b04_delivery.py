"""Exercise current source and installed wheel without DEAP; audit portable frozen rules."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import time
import zipfile
from fogsim.training.protocols import read_json, write_json
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/step9/B04'


def command(name,argv,pythonpath,expected=0):
    start=time.monotonic();env=dict(os.environ,PYTHONPATH=str(pythonpath))
    run=subprocess.run(argv,cwd=ROOT,env=env,capture_output=True,text=True)
    folder=OUT/'commands';folder.mkdir(parents=True,exist_ok=True)
    (folder/(name+'.stdout.txt')).write_text(run.stdout)
    (folder/(name+'.stderr.txt')).write_text(run.stderr)
    write_json(folder/(name+'.json'),dict(argv=argv,cwd=str(ROOT),environment=dict(PYTHONPATH=str(pythonpath)),
        exit_code=run.returncode,expected_exit=expected,duration_seconds=time.monotonic()-start))
    if run.returncode!=expected:raise RuntimeError(name+': '+run.stderr)
    return run.stdout


def independent(prefix,pythonpath,execute=True):
    rows=[]
    for mode,batch,lane in [('single','B02','single-first'),('dual','B03','dual-first')]:
        historical=ROOT/f'outputs/step9/{batch}/{lane}'
        trial=historical/'trial-0001';output=OUT/(prefix+'-'+mode)
        if execute:
            command(prefix+'-'+mode,[sys.executable,'-S','-m','fogsim.training.cli','evaluate',
                '--rules',str(trial/'selected_rule.json'),'--plan',str(historical/'plans/test.json'),
                '--output',str(output)],pythonpath)
        evaluation=read_json(output/'evaluation.json');old=read_json(trial/'test/evaluation.json')
        matched=evaluation['status']=='FEASIBLE' and evaluation['rule_pair_id']==old['rule_pair_id'] and evaluation['fitness']==old['fitness']
        result_bytes_equal=True;input_semantic_equal=True;origin_changes=[]
        from fogsim.replay.export_input import implementation_fingerprint
        for a,b in zip(evaluation['runs'],old['runs']):
            result_bytes_equal &= (output/a['result_ref']).read_bytes()==(trial/'test'/b['result_ref']).read_bytes()
            before=read_json(trial/'test'/b['input_ref']);after=read_json(output/a['input_ref'])
            old_fp=before['origin']['code_dependency_fingerprint'];new_fp=after['origin']['code_dependency_fingerprint']
            origin_changes.append(dict(path='/origin/code_dependency_fingerprint',historical=old_fp,current=new_fp))
            # Source changed between batches; only this recorded origin field may differ.
            # Check the new value against the current implementation, then compare every other field.
            input_semantic_equal &= new_fp==implementation_fingerprint()
            after['origin']['code_dependency_fingerprint']=old_fp
            input_semantic_equal &= before==after
        matched &= result_bytes_equal and input_semantic_equal
        matched &= len(evaluation['runs'])==len(old['runs'])==2
        rows.append(dict(mode=mode,completed_runs=evaluation['completed_runs'],matched=bool(matched),result_bytes_equal=bool(result_bytes_equal),input_semantic_equal=bool(input_semantic_equal),origin_changes=origin_changes,
            source_evidence=str((trial/'test').relative_to(ROOT)),current_evidence=str(output.relative_to(ROOT))))
    return rows


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--wheel',type=Path,required=True);parser.add_argument('--install-target',type=Path,required=True);parser.add_argument('--audit-existing',action='store_true',help='audit already executed current-source outputs; do not simulate again');args=parser.parse_args()
    if args.install_target.exists() and not args.audit_existing:raise ValueError('installation target must be new')
    source=independent('independent-selected',ROOT/'src',execute=not args.audit_existing)
    write_json(OUT/'independent-selected-check.json',dict(passed=all(r['matched'] for r in source),runs=source,completed_runs=sum(r['completed_runs'] for r in source)))
    code="""import json,sys,importlib.abc
class NoDeap(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,*args):
  if fullname.split('.')[0]=='deap':raise AssertionError('DEAP must not be imported')
sys.meta_path.insert(0,NoDeap())
from fogsim import create_engine,parse_instance,RunConfig
from fogsim.training.selection import load_selected_rule
raw=json.load(open('data/cases/chain_remote.json'))
r=create_engine(parse_instance(raw),RunConfig(routing_kind='fixed_resource',fixed_resource_id='E0')).run()
assert r.status=='SUCCEEDED'
for p in ['outputs/step9/B02/single-first/trial-0001/selected_rule.json','outputs/step9/B03/dual-first/trial-0001/selected_rule.json']:load_selected_rule(p)
print(json.dumps(dict(passed=True,status=r.status,deap_loaded='deap' in sys.modules)))
"""
    raw=command('no-deap-fixed',[sys.executable,'-S','-c',code],ROOT/'src')
    command('no-deap-train',[sys.executable,'-S','-m','fogsim.training.cli','train','--config','configs/training/smoke-dual.json','--output',str(OUT/'must-not-create')],ROOT/'src',2)
    assert not (OUT/'must-not-create').exists()
    write_json(OUT/'no-deap.json',dict(passed=True,fixed_and_loading=json.loads(raw),source_independent_runs=4,missing_training_dependency_exit=2))
    if not args.audit_existing:command('wheel-install',[sys.executable,'-m','pip','install','--no-deps','--target',str(args.install_target),str(args.wheel.resolve())],ROOT/'src')
    with zipfile.ZipFile(args.wheel) as archive:
        mismatches=[name for name in archive.namelist() if name.startswith('fogsim/') and name.endswith('.py') and archive.read(name)!=(ROOT/'src'/name).read_bytes()]
    installed=independent('wheel-selected',args.install_target,execute=not args.audit_existing)
    location=command('wheel-import',[sys.executable,'-S','-c','import fogsim;print(fogsim.__file__)'],args.install_target).strip()
    passed=not mismatches and all(r['matched'] for r in installed) and Path(location).is_relative_to(args.install_target)
    write_json(OUT/'wheel-check.json',dict(passed=passed,wheel=str(args.wheel.resolve().relative_to(ROOT)),source_mismatches=mismatches,import_location=location,
        independent_evaluations=installed,completed_runs=sum(r['completed_runs'] for r in installed)))
    assert passed and all(r['matched'] for r in source)
    print(json.dumps(dict(passed=True,source_independent_runs=4,wheel_independent_runs=4)))
if __name__=='__main__':main()
