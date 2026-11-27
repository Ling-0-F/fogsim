"""B07 complete fixed, native Java dynamic, and Python capture/replay acceptance."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import traceback

from java_stage_d_support import compile_stage_d,run_stage_d,write,sha,environment
from java_support import ORIGINAL
from stage_d_b07.coverage import fixed_coverage
from fogsim.config import RunConfig
from fogsim.instances.fixed import parse_instance
from fogsim.rules.specs import RuleSpec
from fogsim.simulation.state import build_state
from fogsim.simulation.engine import Engine
from fogsim.simulation.events import JobArrivalEvent
from fogsim.validation.gp_observe import attach_observer
from fogsim.validation.gp_normalize import python_fixed,java_fixed
from fogsim.validation.gp_compare import compare_reference,first_difference,bind_reference,validate_reference
from fogsim.replay.loader import read_replay_json
from fogsim.serialization.result import decode_result,_score_fields
from fogsim.serialization.f64 import encode_f64

ROOT=Path(__file__).resolve().parents[1]
PLANS=ROOT/'development/b07/fixtures'

def read(path):return read_replay_json(path)
def config(case):
    r,s=case['routing_rule'],case['sequencing_rule']
    return RunConfig(routing_kind=r['kind'],fixed_resource_id=r.get('resource_id'),
        sequencing_kind=s['kind'],routing_expression=r.get('expression'),sequencing_expression=s.get('expression'),max_events=10000)

def engine(case):
    # Explicit v2 validation profile also covers the two no-GP combinations.
    # Only ordinary initial loading is performed; original event objects run.
    spec=parse_instance(case['instance']);state=build_state(spec)
    e=Engine(state,config(case),output_profile='v2')
    for w in state.workflows_by_id.values():e.event_queue.stage(JobArrivalEvent(w),w.owner_device)
    state.check_invariants()
    return e

def binding(folder,reference,input_name='input.json'):
    write(folder/'manifest.json',dict(format='fogsim.gp-reference-manifest',schema_version=2,
        files={n:sha(folder/n) for n in (input_name,'reference.json')},rule_pair_id=reference['rule_manifest']['rule_pair_id'],
        source_fingerprint=reference['provenance']['source_fingerprint'],build_manifest_sha256=reference['provenance']['build_manifest_sha256']))
    return bind_reference(folder/'manifest.json',folder/input_name,folder/'reference.json',
        rule_pair_id=reference['rule_manifest']['rule_pair_id'],source_fingerprint=reference['provenance']['source_fingerprint'])

def fixed_case(case,build,folder):
    folder.mkdir()
    write(folder/'instance.json',case['instance'])
    write(folder/'config.json',dict(instance='instance.json',routing_rule=case['routing_rule'],sequencing_rule=case['sequencing_rule'],trace_enabled=True))
    inp=dict(schema_version=1,record_trace=True,input=case['instance'],
        config=dict(max_events=10000,event_policy='java_compatible',routing_kind=case['routing_rule']['kind'],
            sequencing_kind=case['sequencing_rule']['kind'],routing_rule=case['routing_rule'],sequencing_rule=case['sequencing_rule']))
    write(folder/'input.json',inp)
    e=engine(case);attach_observer(e);result=e.run()
    wire=result.to_dict();write(folder/'python-result.json',wire)
    # Formal output -> strict read -> score re-encode. No value is repaired.
    loaded=read(folder/'python-result.json');decoded=decode_result(loaded)
    _score_fields(decoded,encode_f64)
    roundtrip=first_difference(loaded,decoded,raw_f64=True)
    write(folder/'wire-roundtrip.json',dict(passed=roundtrip is None,first_difference=roundtrip))
    py=python_fixed(e,result);write(folder/'python.json',py)
    run=run_stage_d(build,folder/'input.json',folder/'reference.json',main='fogsim.adapter.StageDFixedMain',timeout=90)
    if run['exit_code']!=0:raise RuntimeError('Java fixed run failed; raw process and Python result retained')
    # The reference is first opened after Python and Java independently stop.
    reference=validate_reference(read(folder/'reference.json'));j=java_fixed(reference)
    coverage={side:fixed_coverage(case,payload) for side,payload in [('python',py),('java',j)]}
    write(folder/'coverage.json',coverage)
    report=compare_reference(reference,read(folder/'python.json'),e.prepared_rules.rule_manifest,
        binding=binding(folder,reference),coverage=dict(passed=roundtrip is None and all(x['passed'] for x in coverage.values()),
            checks=coverage,wire_roundtrip_passed=roundtrip is None))
    write(folder/'comparison.json',report)
    return dict(id=case['id'],family=case['family'],executed=True,compared=True,passed=report['passed'],
        classification=report['classification'],first_difference=report['first_difference'],coverage=coverage,
        events=len(result.events),decisions=len(result.decisions),input_sha256=sha(folder/'input.json'))

def audit_build(path,java):
    p=Path(path).resolve();m=read(p/'build-manifest.json')
    for rel,digest in m['original_sources'].items():assert sha(ORIGINAL/'src'/rel)==digest
    for group in ('adapter_sources','dependencies'):
        for rel,digest in m[group].items():assert sha(ROOT/rel)==digest,(group,rel)
    for flavor,b in m['builds'].items():
        for rel,digest in b['classes'].items():assert sha(p/flavor/'classes'/rel)==digest
    env=read(p/'environment.json');assert sha(java)==env['java_sha256']
    return dict(java=str(Path(java).resolve()),output=str(p),manifest=m)

def run(output,java,phase='fixed',existing_build=None,fixed_plan=None,dynamic_plan=None):
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    fixed_plan=Path(fixed_plan) if fixed_plan else PLANS/'fixed-plan-v2.json'
    dynamic_plan=Path(dynamic_plan) if dynamic_plan else PLANS/'dynamic-plan-v3.json'
    write(out/'invocation.json',dict(argv=sys.argv,cwd=str(Path.cwd()),phase=phase,java=str(java),
        fixed_plan_path=str(fixed_plan.resolve()),fixed_plan_sha256=sha(fixed_plan),dynamic_plan_path=str(dynamic_plan.resolve()),dynamic_plan_sha256=sha(dynamic_plan),
        environment={k:v for k,v in os.environ.items() if k in ('PYTHONPATH','LD_LIBRARY_PATH','FOGSIM_JAVA','PYTEST_DISABLE_PLUGIN_AUTOLOAD')},
        authorized_batch='B07',B08_implemented=False))
    if phase=='native':build=None
    else:build=audit_build(existing_build,java) if existing_build else compile_stage_d(out/'build',java)
    if phase=='fixed':
        plan=read(fixed_plan);operation=lambda c:fixed_case(c,build,out/c['id'])
    elif phase=='dynamic':
        from stage_d_b07.dynamic import dynamic_case
        plan=read(dynamic_plan);operation=lambda c:dynamic_case(c,build,out/c['id'])
    elif phase=='native':
        from stage_d_b07.native import native_cases,native_case
        plan=dict(cases=native_cases());operation=lambda c:native_case(c,out/c['id'])
    else:raise ValueError('unknown phase')
    reports=[]
    for case in plan['cases']:
        try:report=operation(case)
        except Exception as exc:
            (out/(case['id']+'-failure.txt')).write_text(traceback.format_exc())
            report=dict(id=case['id'],executed=False,compared=False,passed=False,classification='FAILED',error=str(exc),
                note='failed partial execution retained; see process/result files for exact executed substeps')
        reports.append(report)
        summary=dict(phase=phase,passed=len(reports)==len(plan['cases']) and all(r['passed'] for r in reports),
            classification='NORMAL_PARITY_PASSED' if len(reports)==len(plan['cases']) and all(r['passed'] for r in reports) else 'FAILED',
            counts=dict(planned=len(plan['cases']),attempted=len(reports),executed=sum(bool(r['executed']) for r in reports),
                compared=sum(bool(r['compared']) for r in reports),passed=sum(r['passed'] for r in reports)),cases=reports,B08_implemented=False)
        write(out/'summary.json',summary)
        print(case['id'],report['passed'],report.get('first_difference',report.get('error')),flush=True)
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--java',required=True,type=Path)
    p.add_argument('--phase',choices=('fixed','dynamic','native'),default='fixed');p.add_argument('--existing-build',type=Path)
    p.add_argument('--fixed-plan',type=Path)
    p.add_argument('--dynamic-plan',type=Path)
    a=p.parse_args()
    raise SystemExit(0 if run(a.output,a.java,a.phase,a.existing_build,a.fixed_plan,a.dynamic_plan)['passed'] else 1)
