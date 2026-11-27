"""Explicit independent/fresh-seed/continuing-stream experiment orchestration."""
from copy import deepcopy
from dataclasses import dataclass
import statistics
import hashlib
import json
from dataclasses import asdict
from fogsim.errors import InputError, PreparationError
from fogsim.experiment_config import ExperimentConfig
from fogsim.simulation.context import create_dynamic_context
from fogsim.replay.loader import load_replay_input
from fogsim.replay.engine import simulate_replay_config
from fogsim.replay.export_input import export_replay_input

METRICS = ('makespan', 'mean_flow_time')


@dataclass(frozen=True)
class ExperimentResult:
    runs: tuple
    input_archives: tuple
    run_metadata: tuple
    planned_runs: int
    repeat_mode: str
    config_fingerprint: str
    effective_config: dict
    batch_complete: bool
    verification_required: bool = False
    schema_version: int = 1

    @property
    def succeeded_runs(self):
        return sum(r.status == 'SUCCEEDED' for r in self.runs)

    @property
    def failed_runs(self):
        return sum(r.status == 'FAILED' for r in self.runs)

    @property
    def not_run(self):
        return self.planned_runs - len(self.runs)

    @property
    def verification_failures(self):
        if not self.verification_required:
            return []
        return [dict(run_index=i,classification=r.diagnostics.get('comparison_status','NOT_COMPARED'))
                for i,r in enumerate(self.runs) if r.diagnostics.get('comparison_status')!='NORMAL_PARITY_PASSED']

    @property
    def aggregation_compatible(self):
        return len({r['scene_fingerprint'] for r in self.run_metadata}) <= 1

    @property
    def status(self):
        if not self.batch_complete: return 'INCOMPLETE'
        return 'SUCCEEDED' if not self.not_run and not self.failed_runs and not self.verification_failures and self.aggregation_compatible else 'FAILED'

    @property
    def failure_reasons(self):
        return [dict(run_index=i,reason_code=r.reason_code,reason=r.reason)
                for i,r in enumerate(self.runs) if r.status=='FAILED']

    def _metrics(self, function, minimum=1):
        if not self.aggregation_compatible: return None
        successful = [r for r in self.runs if r.status=='SUCCEEDED']
        if len(successful)<minimum: return None
        return {key:function(getattr(r,key) for r in successful) for key in METRICS}

    @property
    def all_runs_mean(self):
        return self._metrics(statistics.mean) if self.status=='SUCCEEDED' else None

    @property
    def mean_over_successes(self):
        return self._metrics(statistics.mean)

    @property
    def sample_stddev(self):
        return self._metrics(statistics.stdev,2)

    def to_dict(self):
        return dict(format='fogsim.experiment-result',schema_version=self.schema_version,status=self.status,batch_complete=self.batch_complete,
            planned_runs=self.planned_runs,completed_runs=len(self.runs),succeeded_runs=self.succeeded_runs,
            failed_runs=self.failed_runs,not_run=self.not_run,repeat_mode=self.repeat_mode,
            config_fingerprint=self.config_fingerprint,aggregation_compatible=self.aggregation_compatible,effective_config=deepcopy(self.effective_config),
            runs=[r.to_dict() for r in self.runs],inputs=[a.to_dict() if a is not None else None for a in self.input_archives],
            run_metadata=deepcopy(list(self.run_metadata)),failure_reasons=self.failure_reasons,
            verification_required=self.verification_required,verification_failures=self.verification_failures,
            all_runs_mean=self.all_runs_mean,mean_over_successes=self.mean_over_successes,
            success_denominator=self.succeeded_runs,sample_stddev_over_successes=self.sample_stddev,
            failure_rate=self.failed_runs/len(self.runs) if self.runs else None,
            failure_rate_denominator=len(self.runs),not_run_fraction=self.not_run/self.planned_runs,
            aggregation_scope='same configured scene/statistics/rules; allowed seeds vary by explicit mode; successes are runtime successes')


def run_experiment(config, *, on_progress=None):
    """Run the validated plan; domain failures continue, unknown bugs propagate.

    on_progress receives detached INCOMPLETE checkpoints and a final result.
    No reset/rotation/preparation happens after the final planned run.
    """
    if type(config) is not ExperimentConfig:
        raise InputError('run_experiment requires ExperimentConfig')
    replay_input = load_replay_input(config.source.input_path) if config.mode=='replay' else None
    runs, inputs, metadata = [], [], []
    context = None
    verification = config.mode=='replay' and config.source.purpose=='verify_reference'
    def snapshot(complete=False):
        return ExperimentResult(tuple(deepcopy(runs)),tuple(inputs),tuple(deepcopy(metadata)),config.repeat.count,
            config.repeat.mode,config.fingerprint,deepcopy(config.effective_parameters()),complete,verification,config.schema_version)
    if on_progress is not None: on_progress(snapshot())
    for index in range(config.repeat.count):
        single = config.single_run(index)
        if config.mode=='replay':
            result = simulate_replay_config(single,replay_input=replay_input)
            archive = replay_input
        else:
            if config.repeat.mode=='java_rerun' and context is not None:
                result = context.rerun()
            else:
                try:
                    context = create_dynamic_context(single)
                    result = context.run()
                except PreparationError as exc:
                    context, result = exc.context, exc.result
            engine = context.engine
            archive = (export_replay_input(engine,single.source,dataset_role=config.output.dataset_role)
                       if engine.environment is not None and engine.admission is not None else None)
        # result/archives contain no runtime object graph; later rounds cannot
        # change earlier facts, RNG fingerprints, B or source cursor snapshots.
        runs.append(result);inputs.append(archive)
        templates = (replay_input.archive.templates if config.mode=='replay' else context.inputs.catalog.templates)
        scene = dict(config_fingerprint=config.fingerprint,templates=[asdict(t) for t in templates])
        scene_fingerprint = hashlib.sha256(json.dumps(scene,sort_keys=True).encode()).hexdigest()
        metadata.append(dict(scene_fingerprint=scene_fingerprint,experiment_run_index=index,engine_run_index=result.diagnostics['run_index'],
            public_seed=result.diagnostics['public_seed'],environment_fingerprint=result.diagnostics['environment_fingerprint'],
            initial_B=result.diagnostics['initial_cutoff_release_time'],status=result.status,
            source_summary=deepcopy(result.source_summary),dataset_role=config.output.dataset_role,
            input_role='original_recorded_stream' if config.mode=='replay' else 'observed_python_round',
            single_run_config_fingerprint=single.fingerprint))
        if config.schema_version == 2:
            metadata[-1].update(rule_pair_id=result.rule_manifest["rule_pair_id"],
                rule_manifest=deepcopy(result.rule_manifest), replay_rules=deepcopy(result.diagnostics.get("replay_rules")))
        if on_progress is not None: on_progress(snapshot())
    result = snapshot(True)
    if on_progress is not None: on_progress(result)
    return result
