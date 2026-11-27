"""Dynamic control around the existing four event handlers and canonical state."""
from copy import deepcopy
import math
from fogsim.config import RunConfig
from fogsim.errors import EngineUsageError, StateError, SimulationFailure, require
from fogsim.instances.generated import GenerationCause
from fogsim.rules.factory import install_rules, validate_rules_for_environment
from .engine import Engine, EventContext
from .statistics import DynamicStatistics
from .admission import AdmissionService
from .dynamic_result import collect_dynamic_result
from .trace import state_snapshot, event_snapshot


class DynamicEngine(Engine):
    def __init__(self, state, config, environment, templates, source, *, initial_cutoff=0.0,
                 public_seed=0, run_index=0, operation="fresh", rng_start=None,
                 prepared_rules=None, output_profile=None):
        prepared = install_rules(config, prepared_rules)
        if environment is not None:
            validate_rules_for_environment(prepared, environment)
        # Reuse rule construction and the entire EventContext implementation.
        fixed_config = RunConfig(routing_kind=config.routing_rule.kind,
            fixed_resource_id=config.routing_rule.resource_id, trace_enabled=config.trace_enabled,
            check_invariants=config.check_invariants, sequencing_kind=config.sequencing_rule.kind,
            routing_expression=config.routing_rule.expression,
            sequencing_expression=config.sequencing_rule.expression)
        # Failed environment preparation still needs an empty diagnostic engine.
        if environment is None and not state.resources_by_id:
            # It has no source or runnable initialization; target eligibility was
            # already checked against EnvironmentConfig before RNG creation.
            diagnostic_config = RunConfig(trace_enabled=config.trace_enabled)
            super().__init__(state, diagnostic_config, output_profile=output_profile)
            self.prepared_rules = prepared
            self.routing_rule, self.sequencing_rule = prepared.routing, prepared.sequencing
            self.output_profile = "v2" if prepared.has_gp or output_profile == "v2" else "v1"
            self.trace.manifest = prepared.rule_manifest if self.output_profile == "v2" else None
        else:
            super().__init__(state, fixed_config, prepared, output_profile=output_profile)
        self.config = config
        self.environment = environment
        self.initial_cutoff, self.public_seed = initial_cutoff, public_seed
        self.run_index, self.operation = run_index, operation
        self.rng_start, self.rng_ready, self.rng_final = rng_start, None, None
        self.statistics = DynamicStatistics.create(config, state.mobile_devices, initial_cutoff)
        self.admission = AdmissionService(self, source, environment, templates) if source is not None else None
        self.initialization_complete = False
        self.initialization_actions = []
        self.reason_code = None
        self.failure_hits = []
        self.cleanup_totals = dict(workflows_released=0, released_task_count=0, removed_mapping_entry_count=0)

    def initialize(self):
        if self.run_status != "READY" or self.initialization_complete or self.admission is None:
            raise EngineUsageError("dynamic initialization requires a new empty READY round")
        for device in self.state.mobile_devices:
            cause = GenerationCause("initialize", device.id, self.state.clock_time)
            self.admission.admit(cause, EventContext(self, device))
        self.initialization_complete = True
        self.initialization_actions = deepcopy(self.trace.actions)
        self._check_invariants()

    def after_arrival(self, workflow, ctx):
        cause = GenerationCause("after_arrival", workflow.owner_device.id, self.state.clock_time,
                                workflow.id, self.processed_event_count)
        self.admission.admit(cause, ctx)

    def workflow_completed(self, workflow):
        self.statistics.completed(workflow)

    def _snapshot(self):
        value = state_snapshot(self.state)
        value["dynamic_statistics"] = dict(generated_total=self.statistics.generated_total,
            cutoff_release_time=self.statistics.cutoff_release_time, recorded_total=self.statistics.recorded_total,
            recorded_workflow_ids=list(self.statistics.recorded_workflows))
        return value

    def _check_invariants(self):
        if self.config.check_invariants:
            self.state.check_invariants()
            self.statistics.check_invariants(self.state)
            self.event_queue.check_reservations(self.state.resources_by_id.values())

    def _fail(self, exc):
        self.run_status, self.stop_reason = "FAILED", str(exc)
        self.reason_code = getattr(exc, "reason_code", "STATE_INVARIANT_VIOLATION")

    def _check_guards(self):
        self.failure_hits = self.statistics.guard_hits(self.state)
        if self.failure_hits:
            first = self.failure_hits[0]
            raise SimulationFailure(first["reason_code"],
                f"{first['reason_code']}: {first['resource_id'] or 'global'} "
                f"{first['actual']} > {first['limit']}")

    def run(self):
        if self.run_status != "READY" or not self.initialization_complete:
            raise EngineUsageError("dynamic Engine.run requires the current READY initialized round, once")
        self.run_status = "RUNNING"
        try:
            while True:
                # Exactly one merge, including the final boundary after R reaches N.
                self.event_queue.merge_staging()
                if self.statistics.recorded_total >= self.config.num_jobs_recorded:
                    break
                if not self.event_queue.global_heap:
                    raise SimulationFailure("EVENTS_EXHAUSTED_BEFORE_TARGET", "events exhausted before statistical target")
                if self.config.max_events is not None and self.processed_event_count >= self.config.max_events:
                    raise SimulationFailure("MAX_EVENTS_EXCEEDED", "dynamic event budget exhausted before next poll")
                event = self.event_queue.poll_global()
                producer = self.event_queue.consume_producer(event)
                require(math.isfinite(event.time) and event.time >= self.state.clock_time, "invalid/backward event time")
                self.state.clock_time = event.time
                self.processed_event_count += 1
                self.trace.begin_event(self.processed_event_count)
                ctx = EventContext(self, event.owner)
                before = self._snapshot() if self.trace.enabled else None
                previous_recorded = self.statistics.recorded_total
                error = None
                try:
                    event.trigger(ctx)
                    self.statistics.after_event(previous_recorded)
                    # Failure wins over simultaneous target achievement, by design.
                    self._check_guards()
                    self._check_invariants()
                except Exception as exc:
                    error = str(exc) if isinstance(exc, StateError) else f"{type(exc).__name__}: {exc}"
                    raise
                finally:
                    if self.trace.enabled:
                        self.trace.append(dict(event_snapshot(event), sequence=self.processed_event_count,
                            staging_device=producer.id, before=before, after=self._snapshot(),
                            emitted=ctx.emitted, actions=self.trace.actions, error=error))
            self._check_invariants()
            self.run_status = "SUCCEEDED"
        except StateError as exc:
            self._fail(exc)
        except Exception:
            self.run_status, self.stop_reason = "FAILED", "unexpected programming exception (propagated)"
            raise
        finally:
            source = self.admission.source if self.admission is not None else None
            if hasattr(source, "inputs"):
                self.rng_final = source.inputs.snapshot()
        try:
            return self.result()
        except StateError as exc:
            self._fail(exc)
            return self.result()
        except Exception:
            self.run_status, self.stop_reason = "FAILED", "unexpected result exception (propagated)"
            raise

    def result(self):
        return collect_dynamic_result(self)
