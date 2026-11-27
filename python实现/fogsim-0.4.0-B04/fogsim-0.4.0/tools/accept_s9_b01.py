"""Assemble B01 acceptance from actual JUnit, lifecycle, smoke and byte audit."""
import hashlib
import json
from pathlib import Path
import platform
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/step9/B01'


def read(path):return json.loads(path.read_text())
def sha(data):return hashlib.sha256(data).hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def junit(path):
    root=ET.parse(path).getroot();suites=list(root.iter('testsuite'))
    return {key:sum(int(s.get(key,0)) for s in suites) for key in ['tests','failures','errors','skipped']} | dict(
        seconds=sum(float(s.get('time',0)) for s in suites),evidence=path.relative_to(ROOT).as_posix())


def audit():
    allowed={'README.md','pyproject.toml','src/fogsim/__init__.py','tests/unit/test_final_contracts.py'}
    original=ROOT/'rollback/fogsim-0.3.0-b08.zip';mismatches=[];changed=[];checked=0;production=0
    with zipfile.ZipFile(original) as z:
        assert z.testzip() is None
        for info in z.infolist():
            if info.is_dir():continue
            rel='/'.join(info.filename.split('/')[1:])
            if not rel:continue
            expected=sha(z.read(info));p=ROOT/rel
            actual=sha(p.read_bytes()) if p.exists() else None
            checked+=1
            production+=rel.startswith('src/')
            if actual!=expected:
                (changed if rel in allowed else mismatches).append(dict(path=rel,before=expected,after=actual))
    return dict(original_zip_sha256=sha(original.read_bytes()),files_checked=checked,production_files_checked=production,
                allowed_changes=changed,unexpected_mismatches=mismatches,passed=not mismatches)


def main():
    from fogsim.training.protocols import source_provenance,identity,canonical
    full=junit(OUT/'identity-final-regression.xml');unit=junit(OUT/'unit-identity-final.xml');life=read(OUT/'lifecycle-final/checks.json')
    old=audit();write(OUT/'source-retention.json',old)
    a=read(OUT/'identity-smoke/evaluation.json');b=read(OUT/'identity-smoke-repeat/evaluation.json')
    # Output refs are relative. All evaluation and raw-run fields are semantic;
    # only provenance contains observed process/environment fields.
    smoke_equal=a==b
    for row in a['runs']:
        for key in ('result_ref','input_ref'):
            if row[key]:smoke_equal &= (OUT/'identity-smoke'/row[key]).read_bytes()==(OUT/'identity-smoke-repeat'/row[key]).read_bytes()
    source=source_provenance()
    smoke_equal &= a['implementation_source_id']==source['source_id']
    passed=all(full[k]==0 and unit[k]==0 for k in ('failures','errors','skipped')) and old['passed'] and life['passed'] and smoke_equal and a['status']=='FEASIBLE'
    current_lanes={lane:read(OUT/lane/'summary.json') for lane in ['regression-fixed','regression-dynamic','regression-native-retry']}
    passed &= all(p['passed'] for p in current_lanes.values())
    scope={
      'S01':('B01_PASSED','strict config, plan freezing/rotation/signed64, leakage, unknown fields','evolution execution remains B02/B03'),
      'S03':('B01_PASSED','real fixed makespans 1/1/10 => mean 4, full-plan denominator','none'),
      'S04':('B01_PASSED','domain, event budget, continuation, unknown exception chain, coverage and invalid metric abort','training no-feasible population belongs B02'),
      'S05':('B01_PASSED','real B08 special scores and cumulative identity/numerics regression','DEAP constant adaptation belongs B02'),
      'S06':('B01_PASSED','A/B order invariance, independent mutable contexts/resources/RNG/queues/B','trial population lifecycle belongs B02'),
      'S07':('B01_PASSED','spawn, extra evolution draws, extra simulation, caller/old RNG isolation','actual DEAP components belong B02'),
      'S11':('B01_PART_PASSED','J05 actual independent JDK17 lifecycle; 68 checks','J01-J04/J06 operators and evolution belong B02/B03'),
      'S14':('B01_PART_PASSED','height 7/8, nodes, event budget, in-B08 wallclock, worker exit','mutation subtree 0..3 belongs B02'),
      'S15':('B01_PART_PASSED','validate/evaluate API+CLI, result/input/exception protocols, output protection, callback failure','train/evolution/selected-rule/spectra logs belong B02/B03'),
      'S16':('B01_PASSED','full current regression, DEAP absent and import blocker, fixed/v1/v2/dynamic/replay/identity/CLI','B04 final combined audit still required'),
    }
    gates={k:dict(status=status,executed_scope=done,deferred=later) for k,(status,done,later) in scope.items()}
    for k in ['S02','S08','S09','S10','S12','S13','S17']:
        gates[k]=dict(status='NOT_EXECUTED',reason='outside S9-B01; B02/B03/B04',component_note='fixed-rule repeat is component evidence only' if k=='S13' else None)
    report=dict(format='fogsim.training-acceptance',schema_version=1,batch='S9-B01',version='0.4.0',
        design='S9-frozen-1',acceptance_passed=bool(passed),tests=full,component_tests=unit,
        historical_test_count_not_reused=True,source_retention=old,source=source,
        java_lifecycle=dict(passed=life['passed'],checks=len(life['checks']),evidence='outputs/step9/B01/lifecycle-final'),
        current_compatibility_lanes={k:dict(passed=v['passed'],counts=v['counts']) for k,v in current_lanes.items()},
        fixed_rule_repeat=dict(passed=smoke_equal,fitness=a['fitness'],runs_per_evaluation=a['planned_runs'],evaluations=2),
        gates=gates,budget_848_executed=False,evolution_trials_executed=0,
        known_differences=['Native Python and Java RNG values are not compared. Java original B/seed/resource lifecycle is independently observed.',
           'B01 main path is fresh; reset/rerun/rotate only in lifecycle probes.',
           'Missing B07 fixtures reconstructed from supplied generators; evidence independently regenerated and labelled current.',
           'No paper-scale training, DEAP integration, single/dual evolution or final winner is claimed.'])
    write(OUT/'acceptance.json',report)
    vectors=[dict(domain='test-vector',payload=x,canonical=canonical(x),expected=identity('test-vector',x)) for x in
        [dict(a='中文',b=[-9223372036854775808,None,0.0,-0.0]),dict(a=1),dict(a=None),{}]]
    write(ROOT/'development/S9-B01/identity-vectors.json',dict(encoding='fogsim.training.<domain>.v1 + LF + canonical UTF-8',vectors=vectors,
        actual_plan_vector='outputs/step9/B01/identity-preflight/plans/train-0000.json'))
    print(json.dumps(dict(acceptance_passed=bool(passed),tests=full,component_tests=unit,java_checks=len(life['checks']))))
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
