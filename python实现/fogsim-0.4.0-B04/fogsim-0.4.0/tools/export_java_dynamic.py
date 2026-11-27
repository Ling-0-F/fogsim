"""Export one fresh Java dynamic run and its independent V16 observations.

Requires JDK 17; only FCFS/FCFS and the original standardFull sampler parameters
are offered in this stage. This is a development tool, not the final Python CLI.
"""
from pathlib import Path
import argparse
from dataclasses import asdict
import json
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from fogsim.errors import InputError
from fogsim.instances.dax import parse_dax
from fogsim.instances.catalog import STANDARD_DAX_FILES
from fogsim.input_validation import integer, boolean
from java_support import sha
from java_dynamic_support import compile_dynamic
from dynamic_export_contract import (audit_input,normalize_environment,read_json,write_json,
                                     write_manifest,verify_manifest)
from check_step3 import first_difference


def validate_request(r):
    required = {'seed','N','W','devices','edges','clouds','local','min_type','max_type'}
    if not isinstance(r,dict) or set(r) != required:
        raise InputError(f'request fields must be exactly {sorted(required)}')
    integer(r['seed'],'seed',-(1 << 63),(1 << 63)-1)
    for key in ('N','devices'): integer(r[key],key,1,2**31-1)
    for key in ('W','edges','clouds'): integer(r[key],key,0,2**31-1)
    if r['N']+r['W']>(2**31-1)//500: raise InputError('N+W exceeds int32 guard multiplier range')
    if r['edges']+r['clouds']>2**31-1: raise InputError('combined server count exceeds int32')
    integer(r['min_type'],'min_type',0,19); integer(r['max_type'],'max_type',r['min_type'],19)
    boolean(r['local'],'local')
    if not r['local'] and r['edges']+r['clouds']==0:
        raise InputError('no eligible resource')
    return r


def prepare_request(request,dax_root,directory,build,*,scripted_values=None,label='user_request'):
    r = dict(validate_request(request)); directory = Path(directory)
    if directory.exists() and any(directory.iterdir()):
        raise InputError(f'output directory is not empty: {directory}')
    (directory/'sources/dax').mkdir(parents=True)
    templates = []
    for i in range(r['min_type'],r['max_type']+1):
        source = Path(dax_root)/STANDARD_DAX_FILES[i]
        template = parse_dax(source,dag_type_id=i)
        shutil.copyfile(source,directory/'sources/dax'/source.name)
        templates.append(asdict(template))
    # JSON arrays, never unordered dictionaries, encode topology and attempt order.
    r['templates'] = templates
    r['origin'] = {'language':'Java','implementation_version':'multiDeviceDebug+fogsim-v030-observer-v2',
        'code_dependency_fingerprint':build['fingerprint'],'rules':{'sequencing':'FCFS','routing':'FCFS'},
        'operation':'fresh','fixture_kind':'scripted_boundary' if scripted_values else 'native_random',
        'label':label}
    r['initial_state'] = {'B':0.0,'public_seed':r['seed'],'seed_encoding_version':'java-signed64-v1','run_index':0}
    r['effective_config'] = {'num_jobs_recorded':r['N'],'warmup_jobs':r['W'],
        'statistics_policy':'java_jobsCompleted','sequencing_rule':'FCFS','routing_rule':'FCFS',
        'exception_policy':'java_original','event_order':'java_two_level_priority_queue',
        'guards':{'resource_queue_greater_than':400,'stagnation_greater_than':400000,
                  'generated_greater_than_multiplier':500},
        'samplers':{'workload':[5000.0,15000.0],'data_size':[5120.0,20480.0], 'edge_data':[100.0,200.0],
            'inter_release_time':{'family':'java_exponential','effective_mean':100.0},'weight':'java_TwoSixTwo',
            'upload_bandwidth_edge':'java_BandwidthEdge','download_bandwidth_edge':'java_BandwidthEdge',
            'upload_bandwidth_cloud':'java_BandwidthCloud','download_bandwidth_cloud':'java_BandwidthCloud',
            'processing_rate_device':[125.0,250.0],'processing_rate_edge':[250.0,500.0],
            'processing_rate_cloud':[500.0,1000.0],'workflow_type':[r['min_type'],r['max_type']]},
        'additional_budget':None}
    if scripted_values: r['scripted_values'] = scripted_values
    write_json(directory/'request.json',r)
    write_json(directory/'sources/build-provenance.json',build)
    return r


def _legacy_observations(value):
    """Compare original observation fields; new provenance is observed-only.

    Baseline has no source hooks and cannot observe actual staging. Extra owner/
    staging fields are independently checked by the full Python replay; they
    cannot be inferred from baseline's historically misnamed producer field.
    """
    if isinstance(value,list): return [_legacy_observations(x) for x in value]
    if isinstance(value,dict):
        event = 'kind' in value and 'producer_device_id' in value
        return {k:_legacy_observations(v) for k,v in value.items()
                if not (event and k in ('owner_device_id','staging_device_id'))}
    return value


def export_case(request,dax_root,directory,java,build,*,scripted_values=None,label='user_request'):
    directory = Path(directory).resolve()
    r = prepare_request(request,dax_root,directory,build,scripted_values=scripted_values,label=label)
    raws = {}; observations = {}
    for mode in (('baseline','minimal','full') if scripted_values else ('plain','baseline','minimal','full')):
        folder = directory/mode; (folder/'dax').mkdir(parents=True)
        for xml in (directory/'sources/dax').iterdir(): shutil.copyfile(xml,folder/'dax'/xml.name)
        classpath = build['builds']['baseline' if mode in ('baseline','plain') else 'observed']['classpath']
        command = [str(java),'-cp',classpath,'fogsim.adapter.DynamicExportMain',str(directory/'request.json'),mode,str(folder)]
        run = subprocess.run(command,cwd=folder,capture_output=True,text=True,timeout=60)
        (folder/'stdout.txt').write_text(run.stdout); (folder/'stderr.txt').write_text(run.stderr)
        write_json(folder/'run.json',{'command':command,'cwd':str(folder),'exit_code':run.returncode})
        if run.returncode:
            raise RuntimeError(f'{label}/{mode}: Java failed; see {folder}/stderr.txt (partial capture retained)')
        raws[mode] = read_json(folder/'audit.json')
        observations[mode] = read_json(folder/'observation.json')
    comparisons = {}
    if 'plain' in raws:
        def native_summary(raw):
            return {key:raw[key] for key in ('rng_final_state_sha256','environment')} | {
                'native_result':{k:v for k,v in raw['native_result'].items() if k not in (
                    'completed_workflow_ids','not_arrived_workflow_ids','unfinished_workflow_ids')}}
        comparisons['plain_vs_audited_baseline'] = first_difference(native_summary(raws['plain']),native_summary(raws['baseline']))
    for mode in ('minimal','full'):
        comparisons[f'baseline_vs_{mode}'] = first_difference(_legacy_observations(raws['baseline']),_legacy_observations(raws[mode]))
    comparisons['minimal_vs_full_capture'] = first_difference(
        {k:v for k,v in observations['minimal'].items() if k!='mode'},
        {k:v for k,v in observations['full'].items() if k!='mode'})
    # Java Double.toString and Python JSON both roundtrip the original binary64.
    # Only the environment fingerprint encoding is normalized to the existing
    # Python snapshot algorithm; the raw Java file remains available under full/.
    value = read_json(directory/'full/input.json'); normalize_environment(value)
    archive = audit_input(value)
    write_json(directory/'input.json',value)
    shutil.copyfile(directory/'full/reference.json',directory/'reference.json')
    # Prove the one file alone contains everything needed to instantiate inputs.
    accepted = sum(a.observed_acceptance for a in archive.generation_attempts)
    reference = read_json(directory/'reference.json')
    actions = reference['actions']; emitted = [x for x in actions if x['kind']=='EMIT']
    expected_emitted = (len(reference['events']) + reference['native_result']['pending_global_events'] +
                        sum(r.get('staged_events',0) for r in reference['final_state']['resources']))
    reference_checks = {
        'emitted_events_accounted_for':len(emitted)==expected_emitted,
        'decisions_accounted_for':sum(x['kind']=='DECISION' for x in actions)==len(reference['decisions']),
        'event_sequences_contiguous':[x['event_sequence'] for x in reference['events']]==list(range(1,len(reference['events'])+1)),
        'java_maps_cleared_but_export_edges_retained':all(t['edge_maps_cleared'] for w in reference['final_state']['workflows'] for t in w['tasks']),
        'attempts_link_to_actual_arrivals':all(
            reference['events'][a.cause.event_sequence-1]['kind']=='JobArrivalEvent' and
            reference['events'][a.cause.event_sequence-1]['workflow_id']==a.cause.causing_workflow_id and
            reference['events'][a.cause.event_sequence-1]['time']==a.cause.clock_time
            for a in archive.generation_attempts if a.cause.phase=='after_arrival'),
    }
    report = {'case':label,'scope':'V16 Java observation noninterference and complete input; no Python dynamic replay',
        'passed':all(x is None for x in comparisons.values()) and all(reference_checks.values()),
        'first_differences':comparisons,'reference_checks':reference_checks,
        'counts':{'attempts':len(archive.generation_attempts),'accepted':accepted,
            'rejected':len(archive.generation_attempts)-accepted,
            'events':len(raws['full']['events']),'decisions':len(raws['full']['decisions']),
            'samples':len(raws['full']['samples']),'templates':len(archive.templates)},
        'java_native_result':raws['full']['native_result'],
        'python_dynamic_parity':'NOT_EXECUTED'}
    report['classification'] = ('NORMAL_PARITY_PASSED' if report['java_native_result']['target_reached']
                                else 'EXPECTED_DIFFERENCE_CONFIRMED') if report['passed'] else 'FAILED'
    report['observation_noninterference_passed'] = report['passed']
    write_json(directory/'comparison.json',report)
    provenance = {'build_fingerprint':build['fingerprint'],'source_DAX':{t['source_name']:t['source_sha256'] for t in r['templates']},
                  'original_sources':build['inputs'],'request_sha256':sha(directory/'request.json')}
    write_manifest(directory,provenance); verify_manifest(directory)
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--java'); p.add_argument('--request',type=Path,required=True)
    p.add_argument('--dax-root',type=Path,default=ROOT/'dax')
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args(argv)
    request = validate_request(read_json(a.request)) # fail before Java compilation/RNG
    java,build = compile_dynamic(a.output.resolve().parent/(a.output.name+'-build'))
    report = export_case(request,a.dax_root,a.output,java,build)
    print(json.dumps(report,ensure_ascii=False,indent=2)); return 0 if report['passed'] else 1


if __name__ == '__main__': raise SystemExit(main())
