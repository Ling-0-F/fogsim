"""Fresh native Python GP -> complete capture -> independent same-rule replay."""
from contextlib import ExitStack
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import random
from unittest.mock import patch

from java_stage_d_support import write,sha
from fogsim import create_dynamic_context
from fogsim.experiment_config import parse_experiment_config
from fogsim.instances.source import RandomWorkflowSource
from fogsim.randomness import samplers
from fogsim.replay.native import write_native_replay_bundle,compare_native_reference,NATIVE_EXCLUSIONS
from fogsim.replay.export_input import export_replay_input
from fogsim.replay.native import strict_difference
from fogsim.replay.loader import read_replay_json,load_replay_input
from fogsim.replay.engine import create_replay_engine
from fogsim.validation.gp_observe import attach_observer
from fogsim.validation.gp_normalize import python_dynamic
from fogsim.serialization.result import decode_result
from .coverage import dynamic_coverage

ROOT=Path(__file__).resolve().parents[2]

def native_cases():return read_replay_json(ROOT/'development/b07/fixtures/native-plan-v3.json')['cases']

def native_case(case,folder):
    folder.mkdir()
    write(folder/'config.json',case['config'])
    cfg=parse_experiment_config(case['config'],base_dir=ROOT/'configs/examples')
    ctx=create_dynamic_context(cfg);attach_observer(ctx.engine,dynamic=True)
    native=ctx.run();write(folder/'native-result.json',native.to_dict())
    before=ctx.snapshot_rng();module_before=random.getstate()
    attempts=[];access=[];stage={'stopped':False,'phase':'pure_input_capture'}
    read_text,read_bytes,open_path=Path.read_text,Path.read_bytes,Path.open
    def watched(method,name):
        def call(path,*args,**kwargs):
            mode=args[0] if name=='open' and args else kwargs.get('mode','r')
            reading=name!='open' or not any(x in mode for x in ('w','a','x'))
            if path.name in ('reference.json','manifest.json') and reading:
                access.append(dict(method=name,filename=path.name,phase=stage['phase'],after_replay_stop=stage['stopped']))
                if stage['phase']=='replay_consumer' and not stage['stopped']:raise AssertionError('reference accessed before replay stopped')
            return method(path,*args,**kwargs)
        return call
    def forbidden(label):
        def call(*args,**kwargs):attempts.append(label);raise AssertionError('unexpected RNG/source entry: '+label)
        return call
    def scope():
        stack=ExitStack()
        for name in dir(random.Random):
            if not name.startswith('_') and name!='getstate' and callable(getattr(random.Random,name)):
                stack.enter_context(patch.object(random.Random,name,forbidden('Random.'+name)))
                if callable(getattr(random,name,None)):stack.enter_context(patch.object(random,name,forbidden('random.'+name)))
        for cls in (random.Random,random.SystemRandom):stack.enter_context(patch.object(cls,'__init__',forbidden(cls.__name__+'.__init__')))
        for name in ('random','getrandbits'):stack.enter_context(patch.object(random.SystemRandom,name,forbidden('SystemRandom.'+name)))
        for cls in (samplers.UniformRealSampler,samplers.UniformIntegerSampler,samplers.ExponentialSampler,
            samplers.WeightSampler,samplers.CloudBandwidthSampler,samplers.EdgeBandwidthSampler):
            stack.enter_context(patch.object(cls,'sample',forbidden(cls.__name__+'.sample')))
        stack.enter_context(patch.object(RandomWorkflowSource,'generate',forbidden('native source.generate')))
        stack.enter_context(patch.object(Path,'read_text',watched(read_text,'read_text')))
        stack.enter_context(patch.object(Path,'read_bytes',watched(read_bytes,'read_bytes')))
        stack.enter_context(patch.object(Path,'open',watched(open_path,'open')))
        return stack
    with scope():
        captured=export_replay_input(ctx.engine,cfg.source).to_dict()
        after_capture=ctx.snapshot_rng()
    # Atomic publication uses tempfile's private filename RNG. This I/O scope
    # is separate from input capture/GP/replay and cannot touch the source RNG.
    manifest=write_native_replay_bundle(ctx.engine,cfg.source,folder/'bundle')
    after_publication=ctx.snapshot_rng()
    stage['phase']='replay_consumer'
    with scope():
        inp=load_replay_input(folder/'bundle/input.json')
        assert strict_difference(captured,inp.to_dict()) is None
        replay_engine=create_replay_engine(inp);attach_observer(replay_engine,dynamic=True)
        replay=replay_engine.run();stage['stopped']=True
        reference=read_replay_json(folder/'bundle/reference.json')
        report=compare_native_reference(replay_engine,replay,reference,
            manifest_path=folder/'bundle/manifest.json',input_path=folder/'bundle/input.json',reference_path=folder/'bundle/reference.json')
        replay=replace(replay,diagnostics=replay.diagnostics|dict(comparison=report,comparison_status=report['classification']))
        after=ctx.snapshot_rng()
    write(folder/'replay-result.json',replay.to_dict())
    decode_result(read_replay_json(folder/'native-result.json'));decode_result(read_replay_json(folder/'replay-result.json'))
    py=python_dynamic(ctx.engine,native);rp=python_dynamic(replay_engine,replay)
    write(folder/'native-observed.json',py);write(folder/'replay-observed.json',rp)
    value=read_replay_json(folder/'bundle/input.json')
    coverage={side:dynamic_coverage(case,payload,value) for side,payload in [('native',py),('replay',rp)]}
    write(folder/'coverage.json',coverage)
    rng=dict(attempts=attempts,pure_capture_state_unchanged=before==after_capture,
        atomic_publication_source_state_unchanged=before==after_publication,
        publication_scope='tempfile private filename RNG allowed only for atomic I/O; no input/source/GP RNG operation',
        native_state_unchanged=before==after,module_state_unchanged=module_before==random.getstate(),
        native_before=list(before.native_state),native_after=list(after.native_state),
        fingerprint_before=before.fingerprint,fingerprint_after=after.fingerprint)
    write(folder/'rng-observation.json',rng);write(folder/'reference-access.json',access)
    consumer_reads=[a for a in access if a['phase']=='replay_consumer']
    passed=report['passed'] and all(x['passed'] for x in coverage.values()) and before==after and not attempts and module_before==random.getstate() and bool(consumer_reads) and all(a['after_replay_stop'] for a in consumer_reads)
    assessment=dict(report,passed=passed,classification='NORMAL_PARITY_PASSED' if passed else 'FAILED',
        coverage=coverage,RNG=rng,replay_reference_reads_all_after_stop=all(a['after_replay_stop'] for a in consumer_reads),
        producer_reference_access='only persisted-byte hashing after native run, while creating its binding; consumer has no reference access before replay stops',
        exclusion_whitelist=['.'.join(p) for p in NATIVE_EXCLUSIONS])
    write(folder/'comparison.json',assessment)
    return dict(id=case['id'],executed=True,compared=True,passed=passed,classification=assessment['classification'],
        first_difference=report.get('first_difference'),coverage=coverage,RNG_unchanged=before==after,RNG_attempts=attempts,
        exclusion_whitelist=assessment['exclusion_whitelist'],
        source_consumption=dict(consumed=replay_engine.admission.source.position,available=len(inp.archive.generation_attempts)),
        events=len(native.events),decisions=len(native.decisions),input_sha256=sha(folder/'bundle/input.json'))

def build_native_plan():
    plan=[]
    for label,shape,devices,edges,clouds,local,N in [
        ('chain','chain',1,1,0,True,2),('shared-fork-join','fork_join',2,1,0,True,2),
        ('no-local','chain',2,1,1,False,2)]:
        routing='(+ PT (* 0 (+ MRT WIQ)))' if label=='shared-fork-join' else '(+ MRT (+ TTIQ (+ PT (+ UT DT))))'
        sequence='(- 0 TIS)' if label in ('chain','shared-fork-join') else '(- 0 PT)'
        W=2 if devices>1 else 1
        workload=(2000,4000) if label=='chain' else (500,1500)
        cfg=dict(format='fogsim.experiment',schema_version=2,mode='dynamic',source=dict(seed=7,
            dag_root='../../development/b07/fixtures/'+shape,workflow_types=dict(lower=0,upper=0),
            environment=dict(num_mobile_devices=devices,num_edge_servers=edges,num_cloud_servers=clouds,can_mobile_devices_process_tasks=local),
            samplers=dict(workload=dict(lower=workload[0],upper=workload[1]),data_size=dict(lower=0,upper=1),edge_data=dict(lower=0,upper=1),
                processing_rate_device=dict(lower=10,upper=20),processing_rate_edge=dict(lower=20,upper=30),processing_rate_cloud=dict(lower=30,upper=40))),
            run=dict(num_jobs_recorded=N,warmup_jobs=W,max_events=2000,trace_enabled=True,edge_data_policy='release_after_materialization',
                routing_rule=dict(kind='gp',expression=routing),sequencing_rule=dict(kind='gp',expression=sequence)))
        plan.append(dict(id='D09B-'+label,shape=shape,devices=devices,edges=edges,clouds=clouds,local=local,N=N,W=W,
            require_shared_nonfirst=label=='shared-fork-join',config=cfg))
    return dict(format='fogsim.b07-native-plan',schema_version=1,cases=plan)
