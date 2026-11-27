"""One shared input stream, frozen parameters, and isolated runtime rounds."""
from dataclasses import replace, asdict
import hashlib
import json
from fogsim.errors import InputError, StateError, EngineUsageError, PreparationError
from fogsim.experiment_config import ExperimentConfig
from fogsim.randomness.state import prepare_random_input
from fogsim.environment.build import sample_environment, build_environment
from fogsim.instances.source import RandomWorkflowSource
from fogsim.seed import encode_seed, rotated_seed
from .state import SystemState
from .dynamic import DynamicEngine
from fogsim.rules.factory import install_rules, validate_rules_for_environment


class SimulationContext:
    def __init__(self, config, prepared_rules=None):
        if type(config) is not ExperimentConfig or config.mode != "dynamic":
            raise InputError("create_dynamic_context requires dynamic ExperimentConfig")
        if config.repeat.count != 1 or config.source.seed is None:
            raise InputError("context requires expanded single-run config; call single_run(index)")
        self._config = config
        self._prepared_rules = install_rules(config.run, prepared_rules)
        validate_rules_for_environment(self._prepared_rules, config.source.environment)
        payload = dict(environment=asdict(config.source.environment), samplers=config.source.samplers.effective_parameters())
        self._parameter_fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        # All file/config checks finish before the sole RNG is constructed.
        self._inputs = prepare_random_input(config)
        self._public_seed = config.source.seed
        self._environment = None
        self._engine = None
        self._next_run_index = 0
        self._prepare("fresh")

    @property
    def config(self):
        return self._config

    @property
    def inputs(self):
        return self._inputs

    @property
    def public_seed(self):
        return self._public_seed

    @property
    def environment(self):
        return self._environment

    @property
    def engine(self):
        return self._engine

    @property
    def cutoff_release_time(self):
        return self.engine.statistics.cutoff_release_time if self.engine is not None else 0.0

    @property
    def input_archive(self):
        return self.engine.admission.archive if self.engine.admission is not None else None

    def _boundary(self):
        if self.engine is not None and self.engine.run_status == "RUNNING":
            raise EngineUsageError("lifecycle operation requires a round boundary")

    def snapshot_rng(self):
        self._boundary()
        return self.inputs.snapshot()

    def _prepare(self, operation, seed=None):
        self._boundary()
        initial_cutoff = self.cutoff_release_time
        if self.engine is not None and self.engine.run_status == "READY":
            self.engine.run_status = "SUPERSEDED"
        if seed is not None:
            encoded = encode_seed(seed)
            self._public_seed = seed
            self.inputs.rng.seed(encoded)
            self._inputs = replace(self.inputs, public_seed=seed)
        start = self.inputs.snapshot()
        run_index = self._next_run_index
        engine = None
        try:
            # Only a missing complete snapshot is sampled. Ordinary reset/rerun
            # never consumes the resource prefix or rereads DAX.
            if self.environment is None:
                self._environment = sample_environment(self.config.source.environment, self.inputs,
                                                       parameter_source=self._parameter_fingerprint)
            validate_rules_for_environment(self._prepared_rules, self.environment)
            source = RandomWorkflowSource(self.inputs, self.environment)
            engine = DynamicEngine(build_environment(self.environment), self.config.run, self.environment,
                self.inputs.catalog.templates, source, initial_cutoff=initial_cutoff,
                public_seed=self.public_seed, run_index=run_index, operation=operation, rng_start=start,
                prepared_rules=self._prepared_rules, output_profile=f"v{self.config.schema_version}")
            self._engine = engine
            self._next_run_index += 1
            engine.initialize()
            engine.rng_ready = self.inputs.snapshot()
            return engine
        except StateError as exc:
            if engine is None:
                engine = DynamicEngine(SystemState(), self.config.run, self.environment,
                    self.inputs.catalog.templates, None, initial_cutoff=initial_cutoff,
                    public_seed=self.public_seed, run_index=run_index, operation=operation, rng_start=start,
                    prepared_rules=self._prepared_rules, output_profile=f"v{self.config.schema_version}")
                self._engine = engine
                self._next_run_index += 1
            engine._fail(exc)
            engine.rng_final = self.inputs.snapshot()
            raise PreparationError(self, engine.result()) from exc
        except Exception:
            if engine is not None:
                engine.run_status, engine.stop_reason = "FAILED", "unexpected programming exception (propagated)"
                engine.rng_final = self.inputs.snapshot()
            raise

    def run(self):
        return self.engine.run()

    def reset(self, seed=None):
        # Validate a supplied value before invalidating the prior READY engine.
        selected = self.public_seed if seed is None else seed
        encode_seed(selected)
        return self._prepare("reset", selected)

    def rerun(self):
        try:
            self._prepare("rerun")
        except PreparationError as exc:
            return exc.result
        return self.run()

    def rotate_seed(self):
        return self._prepare("rotate_seed", rotated_seed(self.public_seed))


def create_dynamic_context(config, *, prepared_rules=None):
    return SimulationContext(config, prepared_rules)


def simulate_dynamic(config, *, prepared_rules=None):
    try:
        return create_dynamic_context(config, prepared_rules=prepared_rules).run()
    except PreparationError as exc:
        return exc.result
