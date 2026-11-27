"""Native same-semantics Java GP generation -> complete input -> independent Python."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import shutil
import builtins,io,os
from unittest.mock import patch
from java_stage_d_support import write,run_stage_d,sha
from export_java_dynamic import prepare_request
from dynamic_export_contract import normalize_environment
from fogsim.replay.loader import load_replay_input,read_replay_json
from fogsim.replay.engine import create_replay_engine
from fogsim.validation.gp_observe import attach_observer
from fogsim.validation.gp_normalize import python_dynamic,java_dynamic
from fogsim.validation.gp_compare import compare_replay_reference,first_difference,validate_reference
from fogsim.serialization.result import decode_result,_score_fields
from fogsim.serialization.f64 import encode_f64
from .coverage import dynamic_coverage

ROOT=Path(__file__).resolve().parents[2]

class ReferenceAccessGuard:
    """Observe every Python open, including byte copies and hashing."""
    def __init__(self,folder):self.folder=folder.resolve();self.stopped=False;self.reads=[]
    def wrap(self,original):
        def watched(file,*args,**kwargs):
            mode=args[0] if args else kwargs.get('mode','r')
            if isinstance(file,(str,bytes,os.PathLike)):
                p=Path(os.fsdecode(file)).resolve()
                if p.name in ('reference.json','manifest.json','audit.json') and p.is_relative_to(self.folder) and not any(x in mode for x in ('w','a','x')):
                    self.reads.append(dict(path=p.relative_to(self.folder).as_posix(),after_python_stop=self.stopped))
                    if not self.stopped:raise AssertionError('reference/audit read before independent Python run stopped')
            return original(file,*args,**kwargs)
        return watched

def dynamic_case(case,build,folder):
    guard=ReferenceAccessGuard(folder)
    try:
        with patch.object(builtins,'open',guard.wrap(builtins.open)),patch.object(io,'open',guard.wrap(io.open)):
            return _dynamic_case(case,build,folder,guard)
    finally:
        if folder.exists():write(folder/'reference-access.json',dict(passed=all(r['after_python_stop'] for r in guard.reads),reads=guard.reads))

def _dynamic_case(case,build,folder,guard):
    from validate_stage_d_b07 import binding
    base={k:case[k] for k in ('seed','N','W','devices','edges','clouds','local')}
    base.update(min_type=0,max_type=0)
    r=prepare_request(base,ROOT/'development/b07/fixtures'/case['shape'],folder,
        dict(fingerprint=build['manifest']['fingerprint']),label=case['id'])
    r.update(routing_rule=case['routing_rule'],sequencing_rule=case['sequencing_rule'])
    r['origin'].update(implementation_version='multiDeviceDebug+stage-d-b07',
        rules=dict(routing=case['routing_rule'],sequencing=case['sequencing_rule']))
    r['effective_config'].update(routing_rule=case['routing_rule'],sequencing_rule=case['sequencing_rule'],
        trace_enabled=True,check_invariants=True,edge_data_policy='release_after_materialization')
    write(folder/'request.json',r)
    for mode in ('plain','full'):
        f=folder/mode;(f/'dax').mkdir(parents=True)
        for xml in (folder/'sources/dax').iterdir():shutil.copyfile(xml,f/'dax'/xml.name)
        process=run_stage_d(build,folder/'request.json',f/'java-log',main='fogsim.adapter.StageDDynamicMain',
            args=[mode,str(f.resolve())],cwd=f,timeout=120)
        if process['exit_code']!=0:raise RuntimeError(f'Java {mode} failed; process/full partial input retained')
    def observed(path):
        d=read_replay_json(path)
        # Plain intentionally does not intercept poll; that one membership is
        # unobservable there. All full Java/Python memberships compare below.
        return {k:d[k] for k in ('rng_final_state_sha256','environment','final_state')}|dict(
            native_result={k:v for k,v in d['native_result'].items() if k!='not_arrived_workflow_ids'})
    value=read_replay_json(folder/'full/input.json');normalize_environment(value)
    write(folder/'input.json',value)
    inp=load_replay_input(folder/'input.json')
    e=create_replay_engine(inp);attach_observer(e,dynamic=True)
    result=e.run()
    guard.stopped=True
    # All reference/audit reads and even file-byte binding hashes are post-run.
    shutil.copyfile(folder/'full/reference.json',folder/'reference.json')
    diff=first_difference(observed(folder/'plain/audit.json'),observed(folder/'full/audit.json'))
    noninterference=dict(passed=diff is None,first_difference=diff,
        exclusions=[dict(path='native_result.not_arrived_workflow_ids',reason='plain does not hook event-queue poll; full reference/replay still compares this membership exactly')])
    write(folder/'noninterference.json',noninterference)
    ref=validate_reference(read_replay_json(folder/'reference.json'))
    binding(folder,ref)
    report=compare_replay_reference(e,result,ref,
        manifest_path=folder/'manifest.json',input_path=folder/'input.json',reference_path=folder/'reference.json')
    write(folder/'trace-comparison.json',report)
    result=replace(result,diagnostics=result.diagnostics|dict(comparison=report,comparison_status=report['classification']))
    write(folder/'python-result.json',result.to_dict())
    wire=read_replay_json(folder/'python-result.json');back=decode_result(wire);_score_fields(back,encode_f64)
    roundtrip=first_difference(wire,back,raw_f64=True)
    write(folder/'wire-roundtrip.json',dict(passed=roundtrip is None,first_difference=roundtrip))
    py=python_dynamic(e,result);write(folder/'python.json',py)
    java=java_dynamic(ref)
    coverage={side:dynamic_coverage(case,payload,value) for side,payload in [('python',py),('java',java)]}
    write(folder/'coverage.json',coverage)
    passed=report['passed'] and noninterference['passed'] and roundtrip is None and all(c['passed'] for c in coverage.values())
    assessment=dict(report,passed=passed,classification='NORMAL_PARITY_PASSED' if passed else 'FAILED',
        scenario_coverage=coverage,observer_noninterference=noninterference,wire_roundtrip_passed=roundtrip is None)
    write(folder/'comparison.json',assessment)
    return dict(id=case['id'],executed=True,compared=True,passed=passed,classification=assessment['classification'],
        first_difference=report['first_difference'],coverage=coverage,observer_noninterference=noninterference,
        source_consumption=dict(consumed=e.admission.source.position,available=len(inp.archive.generation_attempts)),
        events=len(result.events),decisions=len(result.decisions),input_sha256=sha(folder/'input.json'))
