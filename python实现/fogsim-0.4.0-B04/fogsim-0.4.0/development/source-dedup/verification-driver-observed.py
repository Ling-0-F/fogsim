from pathlib import Path
import hashlib
import importlib.util
import json
import os
import platform
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

BASE = Path(__file__).resolve().parent
ZIP = BASE / 'dist/candidate-3/fogsim-0.4.0-B01-source-dedup.zip'
CHECK = BASE / 'evidence/candidate-3'
CHECK.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(ZIP) as z:
    assert z.testzip() is None
    assert all(x.startswith('fogsim-0.4.0/') for x in z.namelist())
    z.extractall(CHECK / 'unpacked')
ROOT = CHECK / 'unpacked/fogsim-0.4.0'
JAVA = BASE / 'runtime/jdk-17.0.21+9/bin/java'
ENV = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, [BASE/'runtime/test-deps', ROOT/'src', ROOT/'tools'])),
           PYTHONDONTWRITEBYTECODE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', FOGSIM_JAVA=str(JAVA))
rows = []


def command(name, argv, expected=0):
    started = time.monotonic()
    result = subprocess.run([sys.executable, *map(str, argv)], cwd=ROOT, env=ENV, capture_output=True, text=True)
    (CHECK / (name+'.stdout.txt')).write_text(result.stdout)
    (CHECK / (name+'.stderr.txt')).write_text(result.stderr)
    row = dict(name=name, argv=[sys.executable, *map(str,argv)], cwd=str(ROOT), exit_code=result.returncode,
               expected_exit_code=expected, seconds=time.monotonic()-started)
    rows.append(row)
    (CHECK/'commands.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps(row), flush=True)
    if result.returncode != expected:
        print(result.stdout[-4000:], result.stderr[-4000:], flush=True)
        raise RuntimeError(f'{name}: exit {result.returncode}, expected {expected}')
    return result


def junit(path):
    return {key:sum(int(s.get(key,'0')) for s in ET.parse(path).getroot().iter('testsuite'))
            for key in ('tests','failures','errors','skipped')}


command('distribution-integrity', ['tools/build_source_distribution.py','verify'])
command('unhydrated-status', ['tools/restore_sources.py','verify'], expected=1)
command('base-version', ['-m','fogsim','--version'])
command('base-fixed', ['-c', "import json,importlib.util; from fogsim import RunConfig,simulate,load_fixed_instance; assert importlib.util.find_spec('deap') is None; r=simulate(load_fixed_instance('data/cases/single_local.json'),RunConfig()); assert r.status=='SUCCEEDED'; print(json.dumps(r.to_dict()))"])
command('base-preflight', ['-m','fogsim.training.cli','validate','--config','configs/training/B01.json','--output',CHECK/'preflight'])
for label in ['evaluation','evaluation-repeat']:
    command(label, ['-m','fogsim.training.cli','evaluate','--rules','configs/training/rules.json','--plan',CHECK/'preflight/plans/train-0000.json','--output',CHECK/label])
a=json.loads((CHECK/'evaluation/evaluation.json').read_text())
b=json.loads((CHECK/'evaluation-repeat/evaluation.json').read_text())
assert a==b and a['status']=='FEASIBLE' and a['completed_runs']==2
for row in a['runs']:
    for key in ['result_ref','input_ref']:
        assert (CHECK/'evaluation'/row[key]).read_bytes()==(CHECK/'evaluation-repeat'/row[key]).read_bytes()
command('unhydrated-components',['-m','pytest','tests/packaging','tests/training','-q','-p','no:cacheprovider',
       '--basetemp='+str(CHECK/'component-cases'),'--junitxml='+str(CHECK/'components.xml')])
command('restore-dry-run',['tools/restore_sources.py','restore','--source-dir',BASE/'project_sources','--dry-run'])
command('restore',['tools/restore_sources.py','restore','--source-dir',BASE/'project_sources'])
command('restored-status',['tools/restore_sources.py','verify'])
command('restore-idempotent',['tools/restore_sources.py','restore','--source-dir',BASE/'project_sources'])
assert json.loads((CHECK/'restore.stdout.txt').read_text())['restored']==3373
assert json.loads((CHECK/'restore-idempotent.stdout.txt').read_text())['restored']==0
command('b08-byte-audit',['-c',"import json;from accept_s9_b01 import audit;r=audit();print(json.dumps(r));assert r['passed']"])
command('java-lifecycle',['tools/check_s9_lifecycle.py','--java',JAVA,'--output',CHECK/'lifecycle'])
command('full-regression',['-m','pytest','tests','-q','-p','no:cacheprovider',
       '--basetemp='+str(CHECK/'regression-cases'),'--junitxml='+str(CHECK/'regression.xml')])
# The legacy regression writes old outputs. Keep those new results in this
# disposable extraction, with original distribution and original sources intact.
component=junit(CHECK/'components.xml'); full=junit(CHECK/'regression.xml')
assert all(component[k]==0 and full[k]==0 for k in ('failures','errors','skipped'))
life=json.loads((CHECK/'lifecycle/checks.json').read_text())
assert life['passed'] and len(life['checks'])==68
baseline=zipfile.ZipFile(BASE/'project_sources/13-fogsim-0.4.0-B01.zip')
current=zipfile.ZipFile(ZIP)
kept=json.loads(current.read('fogsim-0.4.0/development/source-dedup/original-kept-files.json'))['files']
changed=[]
for item in kept:
    raw=current.read('fogsim-0.4.0/'+item['path'])
    if hashlib.sha256(raw).hexdigest()!=item['sha256']:
        changed.append(item['path'])
assert set(changed)=={'README.md','docs/RUNNING-S9-B01.md'}
original_active=[n for n in baseline.namelist() if any(n.startswith('fogsim-0.4.0/'+p) for p in ('src/','tests/','tools/'))]
assert all(current.read(n)==baseline.read(n) for n in original_active)
original_evidence=[n for n in baseline.namelist() if n.startswith('fogsim-0.4.0/outputs/step9/B01/')]
assert all(current.read(n)==baseline.read(n) for n in original_evidence)
report=dict(format='fogsim.source-dedup-candidate-verification', passed=True, package=ZIP.name,
    bytes=ZIP.stat().st_size, sha256=hashlib.sha256(ZIP.read_bytes()).hexdigest(),
    environment=dict(python=sys.version, platform=platform.platform(), deap_installed=False,
                     jdk='17.0.21+9', jdk_archive_sha256=hashlib.sha256((BASE/'runtime/jdk17.tar.gz').read_bytes()).hexdigest()),
    unhydrated_components=component, restored_regression=full, java_lifecycle_checks=68,
    restored_source_files=3373, idempotent=True, fixed_evaluation_repeat_equal=True,
    original_files_retained=len(kept), original_files_changed=changed,
    original_active_files_unchanged=len(original_active), original_B01_evidence_files_unchanged=len(original_evidence),
    commands=rows)
(CHECK/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('environment','commands')}),flush=True)
