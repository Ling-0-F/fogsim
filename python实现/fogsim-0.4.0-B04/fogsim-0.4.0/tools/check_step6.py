"""V17-V19 production replay and same-projection fixed Java/Python acceptance.

V17 uses independently captured Java references from step4, hash-bound to their
original manifests. V19 compiles and runs Java now, through the existing fixed
adapter. No sampler patches or graph-guard bypasses are used.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from fogsim import (load_replay_input,create_replay_engine,export_fixed_instance,fixed_projection_metadata,
    audit_formulas,RunConfig,create_engine,parse_replay_input,simulate_replay)
from fogsim.experiment_config import ReplayRunOptions,RuleConfig
from fogsim.errors import InputError,PreparationError
from fogsim.replay.loader import read_replay_json
from fogsim.validation.dynamic_compare import compare_dynamic_reference,normalize_python
from fogsim.validation.trace_compare import compare_traces, normalized_result
from java_support import prepare_and_compile,sha
from run_fixed_parity import run_java_request,loaded_model,write_json


def dynamic_case(case, output):
    output.mkdir(parents=True,exist_ok=True)
    inp=load_replay_input(case/'input.json')
    try:
        engine=create_replay_engine(inp);result=engine.run()
    except PreparationError as exc:engine,result=exc.engine,exc.result
    write_json(output/'python-result.json',result.to_dict())
    write_json(output/'python-input-consumption.json',dict(candidates=[asdict(c) for c in engine.admission.archive.candidates],
        attempts=[asdict(a) for a in engine.admission.archive.generation_attempts],source_summary=result.source_summary))
    write_json(output/'python-normalized.json',normalize_python(engine,result))
    # Only here, after execution, is the independent reference opened.
    reference=read_replay_json(case/'reference.json')
    report=compare_dynamic_reference(engine,result,reference,manifest_path=case/'manifest.json',
        input_path=case/'input.json',reference_path=case/'reference.json')
    report['formula_audit']=audit_formulas(inp)
    report['reference_source']='independent Java step4 capture; no fresh dynamic Java export in this step'
    report['input_sha256']=sha(case/'input.json');report['reference_sha256']=sha(case/'reference.json')
    write_json(output/'comparison.json',report)
    return report,inp


def fixed_case(inp, output, java, classpath, build):
    output.mkdir(parents=True,exist_ok=True)
    try:spec=export_fixed_instance(inp)
    except InputError as exc:
        if inp.archive.admissions:
            raise
        report=dict(passed=True,classification='EXPECTED_DIFFERENCE_CONFIRMED',reason=str(exc),
            scope='empty accepted set cannot be represented by legacy nonempty fixed format; no fixed execution claimed')
        write_json(output/'comparison.json',report);return report
    write_json(output/'fixed-input.json',spec.to_dict())
    metadata=fixed_projection_metadata(inp)
    metadata.update(fixed_input_sha256=sha(output/'fixed-input.json'),java_build_fingerprint=build['fingerprint'])
    write_json(output/'projection-manifest.json',metadata)
    reports=[]
    for kind,target in [('fcfs',None),*([('fixed_resource',inp.archive.environment.servers[0].id)] if inp.archive.environment.servers else [])]:
        lane=output/kind;lane.mkdir(exist_ok=True)
        config=RunConfig(routing_kind=kind,fixed_resource_id=target)
        engine=create_engine(spec,config);model=loaded_model(engine.state);result=engine.run()
        python=dict(schema_version=1,language='python',input=spec.to_dict(),config=config.to_dict(),loaded_model=model,result=result.to_dict())
        write_json(lane/'python-raw.json',python)
        request=dict(schema_version=1,input=spec.to_dict(),config=config.to_dict(),record_trace=True)
        other=run_java_request(java,classpath,request,lane)
        report=compare_traces(python,other)
        report.update(classification='NORMAL_PARITY_PASSED' if report['passed'] else 'FAILED',scope=metadata['metrics_scope'])
        write_json(lane/'comparison.json',report);write_json(lane/'python-normalized.json',normalized_result(python))
        write_json(lane/'java-normalized.json',normalized_result(other));reports.append(report)
    report=dict(passed=all(r['passed'] for r in reports),classification='NORMAL_PARITY_PASSED' if all(r['passed'] for r in reports) else 'FAILED',lanes=reports)
    write_json(output/'comparison.json',report);return report


def negative_cases(output):
    output.mkdir(parents=True,exist_ok=True);results=[]
    value=read_replay_json(ROOT/'tests/fixtures/dynamic_v1/input.json')
    value['candidates'].pop();value['generation_attempts'].pop();value['capture']['complete_attempt_count']=1
    r=simulate_replay(parse_replay_input(value));write_json(output/'missing-record-result.json',r.to_dict())
    results.append(dict(case='missing_record',passed=r.reason_code=='REPLAY_INPUT_EXHAUSTED',classification='INPUT_COVERAGE_INSUFFICIENT',reason_code=r.reason_code))
    value['capture'].update(complete=False,process_interrupted=True)
    try:parse_replay_input(value)
    except InputError as exc:results.append(dict(case='incomplete_capture',passed=exc.reason_code=='REPLAY_CAPTURE_INCOMPLETE',classification='EXPECTED_DIFFERENCE_CONFIRMED',reason_code=exc.reason_code))
    else:results.append(dict(case='incomplete_capture',passed=False,classification='FAILED'))
    inp=load_replay_input(ROOT/'outputs/step4/cases/multi_device_diamond/input.json')
    r=simulate_replay(inp,ReplayRunOptions(routing_rule=RuleConfig('fixed_resource','E0')),purpose='reuse_inputs')
    write_json(output/'changed-rule-result.json',r.to_dict())
    results.append(dict(case='changed_rule_coverage',passed=r.reason_code=='REPLAY_INPUT_EXHAUSTED',classification='INPUT_COVERAGE_INSUFFICIENT',reason_code=r.reason_code))
    from fogsim.replay.source import ReplayWorkflowSource
    from fogsim.instances.generated import GenerationCause
    from fogsim.errors import SimulationFailure
    s=ReplayWorkflowSource(inp,purpose='verify_reference')
    try:s.generate(GenerationCause('initialize','M1',0),candidate_id=0)
    except SimulationFailure as exc:
        results.append(dict(case='wrong_call_position',passed=exc.reason_code=='REPLAY_INPUT_DIVERGENCE',classification='EXPECTED_DIFFERENCE_CONFIRMED',diagnostic=s.summary()))
    else:results.append(dict(case='wrong_call_position',passed=False,classification='FAILED'))
    write_json(output/'checks.json',results);return results


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'outputs/step6/acceptance')
    p.add_argument('--java');p.add_argument('--cases',nargs='*');p.add_argument('--skip-fixed',action='store_true')
    p.add_argument('--include-large-fixed',action='store_true',help='also run native_* fixed projections (expensive full graph guards)')
    args=p.parse_args(argv);out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    report=dict(passed=False,status='RUNNING',cases=[],scope=__doc__,environment=dict(python=sys.version,platform=platform.platform(),command=sys.argv,LD_LIBRARY_PATH=os.environ.get('LD_LIBRARY_PATH')))
    write_json(out/'checks.json',report)
    try:
        fixed=None
        if not args.skip_fixed:
            fixed=prepare_and_compile(out/'fixed-build',args.java)
            report['java_build_fingerprint']=fixed[2]['fingerprint']
        report['negative_cases']=negative_cases(out/'negative')
        names=args.cases or [p.name for p in sorted((ROOT/'outputs/step4/cases').iterdir())]
        for name in names:
            start=time.monotonic();print(name,'started',flush=True)
            dynamic,inp=dynamic_case(ROOT/'outputs/step4/cases'/name,out/'dynamic'/name)
            row=dict(case=name,dynamic=dynamic)
            row['fixed_planned']=bool(fixed) and (args.include_large_fixed or not name.startswith('native_'))
            if row['fixed_planned']:row['fixed']=fixed_case(inp,out/'fixed'/name,*fixed)
            else:row['fixed']=dict(classification='NOT_EXECUTED',passed=False,
                reason='outside selected fixed validation scope; enable --include-large-fixed for native large projections')
            row['elapsed_seconds']=time.monotonic()-start;report['cases'].append(row)
            write_json(out/'checks.json',report)
            print(name,dynamic['classification'],row['fixed']['classification'],round(row['elapsed_seconds'],2),flush=True)
        report['passed']=all(r['dynamic']['passed'] and (not r['fixed_planned'] or r['fixed']['passed']) for r in report['cases']) and all(r['passed'] for r in report['negative_cases'])
        report['status']='COMPLETED'
    except (OSError,ValueError,RuntimeError) as exc:
        report.update(status='INFRASTRUCTURE_ERROR',error=f'{type(exc).__name__}: {exc}')
    write_json(out/'checks.json',report)
    print(json.dumps(dict(passed=report['passed'],status=report['status'],error=report.get('error')),indent=2),flush=True)
    return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
