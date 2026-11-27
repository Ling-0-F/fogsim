"""Run V16 native random and explicitly scripted boundary fixtures, three modes."""
from pathlib import Path
import argparse
import json
import sys
import tempfile
import subprocess
from export_java_dynamic import ROOT, export_case, compile_dynamic, prepare_request
from dynamic_export_contract import write_json, read_json, audit_input, normalize_environment, write_manifest, verify_manifest
from fogsim.errors import InputError

CHAIN = '<adag><job id="Z"/><job id="a"/><child ref="a"><parent ref="Z"/></child></adag>'
DIAMOND = '<adag><job id="root"/><job id="left"/><job id="right"/><job id="join"/>' + \
    '<child ref="join"><parent ref="right"/><parent ref="left"/></child>' + \
    '<child ref="right"><parent ref="root"/></child><child ref="left"><parent ref="root"/></child></adag>'


def cases():
    common = dict(seed=7,N=2,W=2,devices=2,edges=1,clouds=1,local=True,min_type=0,max_type=0)
    return [
        ('minimal_chain',dict(common,N=1,W=1,devices=1,edges=0,clouds=0),CHAIN,None),
        ('multi_device_diamond',common,DIAMOND,None),
        ('local_disabled',dict(common,local=False,edges=2,clouds=2),DIAMOND,None),
        ('first_device_rejected',dict(common,N=1,W=1),CHAIN,{'inter_release_time':[0.0,10.0,200.0,200.0,200.0]}),
        ('all_devices_rejected',common,DIAMOND,{'inter_release_time':[0.0,0.0]}),
        ('arrival_rejected',dict(common,N=1,W=0,devices=1,edges=0,clouds=0),CHAIN,{'inter_release_time':[2.0,0.0]}),
        ('pending_at_stop',dict(common,N=1,W=1),CHAIN,{'inter_release_time':[1.0,10000.0,10000.0]}),
        ('native_standard_dax',dict(common,seed=-9223372036854775808,N=2,W=2,local=False),None,None),
        ('native_multiple_types',dict(common,seed=9223372036854775807,max_type=4,N=2,W=2),None,None),
    ]


def check_interruption(output,java,build):
    directory = output/'interrupted-capture'
    request = dict(seed=7,N=1,W=1,devices=2,edges=0,clouds=0,local=True,min_type=0,max_type=0)
    with tempfile.TemporaryDirectory(prefix='v16-interrupted-') as temporary:
        dax = Path(temporary); (dax/'CyberShake_30.xml').write_text(CHAIN)
        prepare_request(request,dax,directory,build,scripted_values={'inter_release_time':[1.0]},label='interrupted_capture')
    folder = directory/'full'; (folder/'dax').mkdir(parents=True)
    import shutil
    shutil.copyfile(directory/'sources/dax/CyberShake_30.xml',folder/'dax/CyberShake_30.xml')
    command = [str(java),'-cp',build['builds']['observed']['classpath'],'fogsim.adapter.DynamicExportMain',
               str(directory/'request.json'),'full',str(folder)]
    run = subprocess.run(command,cwd=folder,capture_output=True,text=True,timeout=60)
    (folder/'stdout.txt').write_text(run.stdout); (folder/'stderr.txt').write_text(run.stderr)
    write_json(folder/'run.json',{'command':command,'exit_code':run.returncode})
    value = read_json(folder/'input.json'); normalize_environment(value)
    archive = audit_input(value,require_complete=False)
    rejected = False
    try: audit_input(value)
    except InputError: rejected = True
    passed = (run.returncode != 0 and 'script exhausted' in run.stderr and rejected and
              not value['capture']['complete'] and len(archive.generation_attempts)==1 and
              not (folder/'reference.json').exists())
    write_json(directory/'partial-input.json',value)
    result = {'passed':passed,'classification':'EXPECTED_DIFFERENCE_CONFIRMED' if passed else 'FAILED',
              'reason':'forced sampler script exhaustion during second initialization; full gate rejects partial capture',
              'complete_attempts':len(archive.generation_attempts),'full_audit_rejected':rejected}
    write_json(directory/'comparison.json',result); write_manifest(directory,{'build_fingerprint':build['fingerprint']})
    verify_manifest(directory)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--java'); p.add_argument('--output',type=Path,default=ROOT/'outputs/step4')
    a = p.parse_args(argv); output = a.output.resolve(); output.mkdir(parents=True,exist_ok=True)
    report = {'scope':'V16 Java export only; V17/V19/complete V01 NOT_EXECUTED','passed':False,'cases':[]}
    try:
        java, build = compile_dynamic(output/'build',a.java)
        for name,request,xml,scripts in cases():
            with tempfile.TemporaryDirectory(prefix='v16-dax-') as temporary:
                dax = Path(temporary)
                if xml is None:
                    dax = ROOT/'dax'
                else:
                    (dax/'CyberShake_30.xml').write_text(xml)
                result = export_case(request,dax,output/'cases'/name,java,build,
                                     scripted_values=scripts,label=name)
                report['cases'].append(result)
                print(f"{name}: {result['classification']} ({result['counts']})",flush=True)
        report['interruption_check'] = check_interruption(output,java,build)
        report['passed'] = all(x['passed'] for x in report['cases']) and report['interruption_check']['passed']
        report['classification'] = 'NORMAL_PARITY_PASSED' if report['passed'] else 'FAILED'
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as ex:
        report.update(classification='INFRASTRUCTURE_ERROR',error=f'{type(ex).__name__}: {ex}')
    write_json(output/'checks.json',report)
    print(json.dumps({'passed':report['passed'],'classification':report['classification'],
                      'error':report.get('error'),'cases':len(report['cases'])},indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__': raise SystemExit(main())
