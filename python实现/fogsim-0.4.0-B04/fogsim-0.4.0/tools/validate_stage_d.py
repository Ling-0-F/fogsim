"""B06 independent JDK17 GP references and strict comparison acceptance.

Run from repository root: PYTHONPATH=src:tools python tools/validate_stage_d.py
  --java /path/to/jdk17/bin/java --output /fresh/evidence/directory
This is B06 adapter/kernel acceptance, not the B07 full scenario matrix.
"""
from pathlib import Path
from copy import deepcopy
from dataclasses import asdict
import argparse,json,shutil,sys,traceback,math,struct
from java_stage_d_support import compile_stage_d,run_stage_d,write,sha
from stage_d_cases import cases,legacy_differences
from stage_d_probe import run_document
from fogsim.config import RunConfig
from fogsim.instances.fixed import parse_instance
from fogsim.simulation.engine import create_engine
from fogsim.validation.gp_observe import attach_observer
from fogsim.validation.gp_normalize import python_fixed,java_fixed
from fogsim.validation.gp_compare import compare_probes,compare_reference,first_difference,bind_reference
from fogsim.serialization.f64 import decode_f64,encode_f64
from export_java_dynamic import prepare_request
from dynamic_export_contract import normalize_environment
from fogsim.replay.loader import load_replay_input
from fogsim.replay.engine import simulate_replay
ROOT=Path(__file__).resolve().parents[1]

def require(run):
    if run['exit_code']!=0:raise RuntimeError('Java process failed; raw process/log retained')
def load(p):return json.loads(Path(p).read_text())
def binding(folder,input_path,reference_path,ref):
    p=folder/'manifest.json';write(p,dict(format='fogsim.gp-reference-manifest',schema_version=2,files={Path(x).relative_to(folder).as_posix():sha(x) for x in (input_path,reference_path)},rule_pair_id=ref['rule_manifest']['rule_pair_id'],source_fingerprint=ref['provenance']['source_fingerprint'],build_manifest_sha256=ref['provenance']['build_manifest_sha256']))
    return bind_reference(p,input_path,reference_path,rule_pair_id=ref['rule_manifest']['rule_pair_id'],source_fingerprint=ref['provenance']['source_fingerprint'])

def core(build,folder):
    folder.mkdir();common=cases();write(folder/'common-inputs.json',common)
    require(run_stage_d(build,folder/'common-inputs.json',folder/'java.json'))
    py=run_document(common);write(folder/'python.json',py);report=compare_probes(common,py,load(folder/'java.json'))
    # Same-side branch assertions use actual raw payloads, separately from NaN category comparison.
    checks=[]
    for side,doc in [('python',py),('java',load(folder/'java.json'))]:
        for c,row in zip(common['cases'],doc['cases']):
            if c['mode']=='function' and c['op'] in ('Max','Min'):
                a,b=decode_f64(c['a']),decode_f64(c['b'])
                rhs=not (a>b if c['op']=='Max' else a<b)
                checks.append(dict(side=side,id=c['id'],expected=c['b' if rhs else 'a']['bits'],actual=row['value']['bits'],passed=row['value']==c['b' if rhs else 'a']))
    purity=[]
    def without_priorities(value):
        if type(value) is dict:return {k:without_priorities(v) for k,v in value.items() if k!='priority'}
        if type(value) is list:return [without_priorities(v) for v in value]
        return value
    for side,doc in [('python',py),('java',load(folder/'java.json'))]:
        for row in doc['cases']:
            if 'loaded' not in row:continue
            assertions=dict(feature_reads_read_only=first_difference(row['loaded'],row['after_features']) is None,
                selection_only_writes_priorities=first_difference(without_priorities(row['loaded']),without_priorities(row['after_selection'])) is None,
                rng_absent=row['rng_is_null'] is True,selected_original_object=row['selected_is_candidate'] is True)
            purity.append(dict(side=side,id=row['id'],checks=assertions,passed=all(assertions.values())))
    write(folder/'state-isolation.json',purity);report['state_isolation']=dict(planned=len(purity),executed=len(purity),compared=len(purity),passed=sum(r['passed'] for r in purity));report['passed'] &= all(r['passed'] for r in purity)
    write(folder/'branch-checks.json',checks);report['same_side_branch_checks']=dict(planned=len(checks),executed=len(checks),compared=len(checks),passed=sum(c['passed'] for c in checks));report['passed'] &= all(c['passed'] for c in checks);write(folder/'comparison.json',report);return report

def original_identity(target):
    """Independently rehash diagnostic original-channel IDs; no production selector."""
    from fogsim.gp.identity import canonical_json
    import hashlib
    def digest(domain,p):return 'sha256:'+hashlib.sha256(domain.encode()+b'\n'+canonical_json(p)).hexdigest()
    m=deepcopy(target);ids={}
    for e in m['expressions']:
        old=e.pop('expression_id');e['numeric_semantics_version']='java-original-positive-zero-v1';e['expression_id']=digest('fogsim.expression-id.v1',e);ids[old]=e['expression_id']
    m['expressions'].sort(key=lambda e:e['expression_id'])
    for role,b in m['bindings'].items():
        if b['kind']!='gp':continue
        b['expression_id']=ids[b['expression_id']];p={k:v for k,v in b.items() if k not in ('rule_id','source')};p['identity_encoding_version']=m['identity_encoding_version'];b['rule_id']=digest('fogsim.rule-id.v1',p)
    m['rule_pair_id']=digest('fogsim.rule-pair-id.v1',dict(identity_encoding_version=m['identity_encoding_version'],routing_rule_id=m['bindings']['routing']['rule_id'],sequencing_rule_id=m['bindings']['sequencing']['rule_id']));return m

def legacy(build,folder):
    folder.mkdir();common=legacy_differences();write(folder/'common-inputs.json',common)
    target=[1.]*9+[3.,1.,1.];old=[-math.inf,math.inf,math.nan,math.nan,-math.inf,math.inf,math.nan,-math.inf,-math.inf,-math.inf,0.,2.]
    # Persist explicit triggers and expected first numerical cause BEFORE either run.
    expectations=[dict(id=c['id'],source='mengxu/gp/function/Div.java: Double.compare(rd.value, 0) == 0',trigger='negative-zero divisor',first_cause='unpatched Div divides by -0; frozen overlay protects both signed zeros',target_score=encode_f64(a),original_score=encode_f64(b)) for c,a,b in zip(common['cases'],target,old)]
    expectations.append(dict(id=common['cases'][-1]['id'],trigger='one +0 and one -0 denominator',target_selected=[0,'T0','E0'],original_selected=[0,'T0','C0'],target_scores=[encode_f64(1.),encode_f64(1.)],original_scores=[encode_f64(1.),encode_f64(-math.inf)]))
    write(folder/'registered-before-execution.json',expectations)
    for flavor in ('target','original'):require(run_stage_d(build,folder/'common-inputs.json',folder/(flavor+'.json'),flavor=flavor))
    targetdoc,olddoc=load(folder/'target.json'),load(folder/'original.json');py=run_document(common);write(folder/'python.json',py);normal=compare_probes(common,py,targetdoc);rows=[]
    for i,(c,a,b) in enumerate(zip(common['cases'],targetdoc['cases'],olddoc['cases'])):
        e=expectations[i];checks={}
        checks['independent_original_identity']=original_identity(a['rule_manifest'])==b['rule_manifest']
        checks['distinct_pair_identity']=a['rule_manifest']['rule_pair_id']!=b['rule_manifest']['rule_pair_id']
        if i<12:
            checks['target']=first_difference(e['target_score'],a['scores'][0]['priority']) is None
            checks['original']=first_difference(e['original_score'],b['scores'][0]['priority']) is None
        else:
            checks['selection']=a['selected']==e['target_selected'] and b['selected']==e['original_selected']
            checks['scores']=first_difference(e['target_scores'],[s['priority'] for s in a['scores']]) is None and first_difference(e['original_scores'],[s['priority'] for s in b['scores']]) is None
        rows.append(dict(id=c['id'],classification='EXPECTED_DIFFERENCE_CONFIRMED' if all(checks.values()) else 'FAILED',checks=checks,first_difference=first_difference(a['scores'],b['scores'])))
    report=dict(passed=normal['passed'] and all(r['classification']=='EXPECTED_DIFFERENCE_CONFIRMED' for r in rows),classification='EXPECTED_DIFFERENCE_CONFIRMED',counts=dict(planned=len(rows),executed=len(rows),compared=len(rows),passed=sum(all(r['checks'].values()) for r in rows)),target_python_comparison=normal,cases=rows);write(folder/'comparison.json',report);return report

def fixed(build,folder):
    folder.mkdir();instance=load(ROOT/'data/cases/chain_remote.json')
    r={'kind':'gp','expression':'(+ MRT (+ PT TWT))'};s={'kind':'gp','expression':'(- 0 (+ NTR PT))'}
    inp=dict(schema_version=1,record_trace=True,input=instance,config=dict(max_events=1000,event_policy='java_compatible',routing_kind='gp',sequencing_kind='gp',routing_rule=r,sequencing_rule=s))
    write(folder/'input.json',inp);require(run_stage_d(build,folder/'input.json',folder/'reference.json',main='fogsim.adapter.StageDFixedMain'));ref=load(folder/'reference.json')
    e=create_engine(parse_instance(instance),RunConfig(routing_kind='gp',routing_expression=r['expression'],sequencing_kind='gp',sequencing_expression=s['expression']));attach_observer(e);result=e.run();actual=python_fixed(e,result);write(folder/'python.json',actual)
    coverage=dict(passed=ref['coverage']['completed'] and result.status=='SUCCEEDED' and len(result.events)==ref['coverage']['events'] and bool(actual['feature_observations']),events=len(result.events),decisions=len(result.decisions),scope='adapter bootstrap; full F01-F06 is B07')
    report=compare_reference(ref,actual,e.prepared_rules.rule_manifest,binding=binding(folder,folder/'input.json',folder/'reference.json',ref),coverage=coverage);write(folder/'comparison.json',report);return report

def dynamic(build,folder):
    request=dict(seed=31,N=2,W=1,devices=1,edges=1,clouds=1,local=True,min_type=0,max_type=0)
    r=prepare_request(request,ROOT/'development/b05/fixtures/dax',folder,dict(fingerprint=build['manifest']['fingerprint']),label='B06_dynamic_adapter_bootstrap')
    r['routing_rule']={'kind':'gp','expression':'(+ MRT (+ PT TWT))'};r['sequencing_rule']={'kind':'gp','expression':'(- 0 (+ NTR PT))'}
    r['origin']['implementation_version']='multiDeviceDebug+stage-d-b06';r['origin']['rules']={'routing':r['routing_rule'],'sequencing':r['sequencing_rule']}
    r['effective_config'].update(routing_rule=r['routing_rule'],sequencing_rule=r['sequencing_rule'],trace_enabled=True,check_invariants=True,edge_data_policy='release_after_materialization')
    write(folder/'request.json',r)
    for mode in ('plain','full'):
        f=folder/mode;(f/'dax').mkdir(parents=True)
        for xml in (folder/'sources/dax').iterdir():shutil.copyfile(xml,f/'dax'/xml.name)
        require(run_stage_d(build,folder/'request.json',f/'java-log',main='fogsim.adapter.StageDDynamicMain',args=[mode,str(f.resolve())],cwd=f.resolve()))
    def audited(p):
        a=load(p);return {k:a[k] for k in ('rng_final_state_sha256','environment','final_state')}|dict(native_result={k:v for k,v in a['native_result'].items() if k not in ('completed_workflow_ids','not_arrived_workflow_ids','unfinished_workflow_ids')})
    noninterference=first_difference(audited(folder/'plain/audit.json'),audited(folder/'full/audit.json'));write(folder/'noninterference.json',dict(passed=noninterference is None,first_difference=noninterference))
    value=load(folder/'full/input.json');normalize_environment(value);write(folder/'input.json',value)
    shutil.copyfile(folder/'full/reference.json',folder/'reference.json');ref=load(folder/'reference.json');binding(folder,folder/'input.json',folder/'reference.json',ref)
    inp=load_replay_input(folder/'input.json');result=simulate_replay(inp,reference_path=folder/'reference.json',input_path=folder/'input.json',manifest_path=folder/'manifest.json');write(folder/'python-result.json',result.to_dict())
    report=result.diagnostics['comparison'];report['observer_noninterference_passed']=noninterference is None;report['passed'] &= noninterference is None;write(folder/'comparison.json',report);return report

def run(output,java,existing_build=None):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    write(output/'invocation.json',dict(argv=sys.argv,cwd=str(Path.cwd()),scope='B06; B07/B08 not executed'))
    build=compile_stage_d(output/'build',java) if existing_build is None else dict(java=str(Path(java).resolve()),output=str(Path(existing_build).resolve()),manifest=load(Path(existing_build)/'build-manifest.json'))
    reports={}
    for name,operation in [('core',core),('legacy',legacy),('fixed',fixed),('dynamic',dynamic)]:
        try:reports[name]=operation(build,output/name)
        except Exception as exc:
            (output/(name+'-failure.txt')).write_text(traceback.format_exc());reports[name]=dict(passed=False,classification='FAILED',reason=str(exc))
        write(output/'summary.json',dict(passed=all(r['passed'] for r in reports.values()),reports={k:{x:v for x,v in r.items() if x not in ('cases','target_python_comparison')} for k,r in reports.items()}))
        print(name,reports[name]['passed'],reports[name].get('first_difference',reports[name].get('reason')),flush=True)
    return reports
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--java',required=True);p.add_argument('--output',required=True,type=Path);p.add_argument('--existing-build',type=Path);a=p.parse_args();r=run(a.output,a.java,a.existing_build);sys.exit(0 if all(x['passed'] for x in r.values()) else 1)
