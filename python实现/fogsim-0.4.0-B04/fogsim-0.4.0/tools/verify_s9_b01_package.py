"""Verify an independent extraction, including fresh Python and Java executions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile


def sha(data):return hashlib.sha256(data).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--package',required=True);p.add_argument('--output',required=True)
    p.add_argument('--java',required=True);p.add_argument('--test-deps',required=True);a=p.parse_args()
    package=Path(a.package).resolve();out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(package) as z:
        assert z.testzip() is None
        assert all(n=='fogsim-0.4.0/' or n.startswith('fogsim-0.4.0/') for n in z.namelist())
        assert not any('..' in Path(n).parts for n in z.namelist())
        manifest=json.loads(z.read('fogsim-0.4.0/S9-B01-FILES.json'))
        for name,item in manifest['files'].items():
            data=z.read('fogsim-0.4.0/'+name)
            assert len(data)==item['size'] and sha(data)==item['sha256'],name
        z.extractall(out/'unpacked')
    root=out/'unpacked/fogsim-0.4.0';env=dict(os.environ,
        PYTHONPATH=os.pathsep.join([str(Path(a.test_deps).resolve()),str(root/'src'),str(root/'tools')]),
        PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',FOGSIM_JAVA=str(Path(a.java).resolve()))
    commands=[]
    def run(name,args):
        start=time.monotonic();r=subprocess.run(args,cwd=root,env=env,text=True,capture_output=True,timeout=180)
        (out/(name+'.stdout.txt')).write_text(r.stdout);(out/(name+'.stderr.txt')).write_text(r.stderr)
        commands.append(dict(name=name,argv=args,cwd=str(root),exit_code=r.returncode,seconds=time.monotonic()-start))
        if r.returncode:raise RuntimeError(f'{name} failed; see preserved output')
    run('unit',[sys.executable,'-m','pytest','tests/training','-q','-p','no:cacheprovider',
                '--basetemp='+str(out/'cases'),'--junitxml='+str(out/'unit.xml')])
    run('version',[sys.executable,'-m','fogsim','--version'])
    run('old-fixed',[sys.executable,'-c',"import json;from fogsim import RunConfig,simulate,load_fixed_instance; r=simulate(load_fixed_instance('data/cases/single_local.json'),RunConfig()); print(json.dumps(r.to_dict())); assert r.status=='SUCCEEDED'"])
    run('preflight',[sys.executable,'-m','fogsim.training.cli','validate','--config','configs/training/B01.json','--output',str(out/'preflight')])
    run('evaluation',[sys.executable,'-m','fogsim.training.cli','evaluate','--rules','configs/training/rules.json',
                      '--plan',str(out/'preflight/plans/train-0000.json'),'--output',str(out/'evaluation')])
    run('java-lifecycle',[sys.executable,'tools/check_s9_lifecycle.py','--java',str(Path(a.java).resolve()),'--output',str(out/'java-lifecycle')])
    suites=list(ET.parse(out/'unit.xml').getroot().iter('testsuite'))
    counts={k:sum(int(s.get(k,0)) for s in suites) for k in ['tests','failures','errors','skipped']}
    life=json.loads((out/'java-lifecycle/checks.json').read_text())
    report=dict(format='fogsim.s9-B01-package-verification',schema_version=1,
        package=package.name,package_bytes=package.stat().st_size,package_sha256=sha(package.read_bytes()),
        crc_passed=True,top_directory='fogsim-0.4.0/',manifest_files_verified=len(manifest['files']),
        independent_extraction=True,tests=counts,java_checks=len(life['checks']),java_passed=life['passed'],
        commands=commands,passed=all(counts[k]==0 for k in ['failures','errors','skipped']) and life['passed'])
    (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['passed','tests','java_checks','package_sha256']}))

if __name__=='__main__':main()
