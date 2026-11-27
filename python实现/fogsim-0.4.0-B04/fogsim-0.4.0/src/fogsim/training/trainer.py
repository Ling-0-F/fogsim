"""Parent controller: serial spawn trials, per-run supervision and durable facts."""
import multiprocessing
import platform
import sys
import time
import traceback
from pathlib import Path
from importlib.metadata import version
from fogsim.errors import InputError
from fogsim.rules.factory import prepare_rules
from fogsim.rules.specs import RuleSpec
from .config import load_training_config, parse_training_config
from .plans import build_training_plans
from .protocols import Snapshot, canonical, identity, write_json, read_json, empty_output, source_provenance, append_jsonl


class RemoteTrainingError(RuntimeError):
    def __init__(self,error,result):
        self.error,self.result=error,result
        super().__init__(f"{error['error_type']}: {error['message']}\nRemote exception chain:\n{error['traceback']}")


def simulation_budget(cfg,plans):
    n=len(cfg['trials']['evolution_seeds']);e=cfg['evolution']
    training=e['population_size']*sum(len(p.to_dict()['entries']) for p in plans.training)
    validation=e['generations']*len(plans.validation.to_dict()['entries'])
    test=len(plans.test.to_dict()['entries'])
    return dict(trials=n,training_per_trial=training,validation_upper_bound_per_trial=validation,
        test_per_trial=test,total_upper_bound=n*(training+validation+test))


def train(config,output_dir,on_progress=None):
    # Import only on the training route, with a helpful dependency error.
    from . import deap_adapter
    from .evolution import trial_worker, IMPLEMENTATIONS
    from .runtime import preflight
    if isinstance(config,(str,Path)):config=load_training_config(config)
    raw=config.to_dict();raw.pop('resolution_root',None)
    config=parse_training_config(raw,Path.cwd());cfg=config.to_dict()
    implementation=IMPLEMENTATIONS[cfg['mode']]
    plans=build_training_plans(config)
    placeholder=prepare_rules(RuleSpec('routing','gp',expression='PT'),
        RuleSpec('sequencing','gp',expression='PT') if cfg['mode']=='dual_tree' else RuleSpec('sequencing','fcfs'))
    for plan in plans.all_plans():preflight(placeholder,plan.to_dict(),cfg['trees'])
    output=empty_output(output_dir)
    write_json(output/'resolved_config.json',cfg)
    from .preflight import preflight_report
    write_json(output/'preflight.json',preflight_report(config,plans))
    pmap=dict(training=[p.to_dict() for p in plans.training],validation=plans.validation.to_dict(),test=plans.test.to_dict())
    for g,plan in enumerate(pmap['training']):write_json(output/f'plans/train-{g:04d}.json',plan)
    for key in ('validation','test'):write_json(output/f'plans/{key}.json',pmap[key])
    dependencies={p:version(p) for p in ('deap','numpy','moocore','cffi','platformdirs','pycparser')}
    provenance=dict(python=sys.version,platform=platform.platform(),dependencies=dependencies,start_method='spawn',
        implementation=implementation,**source_provenance(),shared_plans_across_trials=True,
        wallclock_scope='acknowledged run_started through run_completed',semantic_exclusions=['output location','platform observations'])
    write_json(output/'provenance.json',provenance)
    result=dict(format='fogsim.training-result',schema_version=1,implementation=implementation,status='INCOMPLETE',
        budget=simulation_budget(cfg,plans),trials=[],source_id=provenance['source_id'])
    write_json(output/'training-result.json',result)
    for index,seed in enumerate(cfg['trials']['evolution_seeds'],1):
        trial_id=f'trial-{index:04d}';trial_root=output/trial_id
        ctx=multiprocessing.get_context('spawn');parent,child=ctx.Pipe()
        process=ctx.Process(target=trial_worker,args=(child,cfg,pmap,str(trial_root),trial_id,seed))
        active=None;started=None;seconds=None;done=False;interruption=None;error=None
        def interrupt_evaluation():
            if active and (trial_root/active['evaluation_ref']).exists():
                path=trial_root/active['evaluation_ref'];value=read_json(path)
                value.update(status='INCOMPLETE',fitness=None,interruption=interruption)
                write_json(path,value)
                write_json(path.parent/'failures/interruption.json',interruption)
        try:
            process.start();child.close()
            while not done:
                remaining=seconds-(time.monotonic()-started) if started is not None and seconds is not None else None
                if remaining is not None and remaining<=0:
                    interruption=dict(classification='WALLCLOCK_INTERRUPTED',capture_complete=False,
                        coverage='committed evaluation records only',active_run=active,seconds=seconds);break
                if parent.poll(min(.05,max(0,remaining)) if remaining is not None else .05):
                    try:message=parent.recv()
                    except EOFError:
                        interruption=dict(classification='WORKER_EXIT',exitcode=process.exitcode,capture_complete=False);break
                    append_jsonl(output/'progress.jsonl',message)
                    kind=message['kind']
                    if kind=='error':error=message;break
                    if kind=='trial_done':
                        result['trials'].append(message['result']);done=True;continue
                    # Stop the timer before a completed-run callback.
                    if kind=='run_completed':started=None
                    if on_progress:on_progress(Snapshot(canonical(message)).to_dict())
                    if kind=='run_started':
                        active=message;seconds=message['seconds'];started=time.monotonic()
                        write_json(trial_root/'active_run.json',dict(message,capture_complete=False))
                        parent.send('START')
                    elif kind in ('evaluation_completed','candidates_frozen','selected_rule_frozen','evaluation_started'):pass
                    elif kind!='run_completed':raise RuntimeError('unknown training worker message')
                elif not process.is_alive():
                    if parent.poll():continue
                    interruption=dict(classification='WORKER_EXIT',exitcode=process.exitcode,capture_complete=False);break
        except BaseException as exc:
            interruption=dict(classification='CANCELLED' if isinstance(exc,KeyboardInterrupt) else 'CONTROLLER_EXCEPTION',
                error_type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc(),capture_complete=False)
            write_json(output/'failures/controller-exception.json',interruption)
            raise
        finally:
            if process.pid is not None:
                if not done and process.is_alive():process.terminate()
                process.join(timeout=2)
                if process.is_alive():process.kill();process.join()
            parent.close();child.close()
            if interruption:
                if interruption['classification']=='WORKER_EXIT':
                    interruption['exitcode']=process.exitcode
                interrupt_evaluation()
                write_json(trial_root/'failures/interruption.json',interruption)
                path=trial_root/'evolution-result.json'
                value=read_json(path) if path.exists() else dict(format='fogsim.evolution-result',schema_version=1,trial_id=trial_id,
                    evolution_seed=seed,training_status='INCOMPLETE',validation_status='NOT_STARTED',test_status='NOT_STARTED')
                value.update(status='INCOMPLETE',interruption=interruption)
                write_json(path,value)
                result['interruption']=interruption
            write_json(output/'training-result.json',result)
        if error:
            write_json(output/'failures/worker-exception.json',error)
            raise RemoteTrainingError(error,Snapshot(canonical(result)))
        if interruption:break
    else:result['status']='COMPLETED' if all(t['status']=='COMPLETED' for t in result['trials']) else 'DOMAIN_FAILED'
    write_json(output/'training-result.json',result)
    return Snapshot(canonical(result))
