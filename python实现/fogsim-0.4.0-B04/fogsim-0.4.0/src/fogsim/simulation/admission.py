"""The single commit point for dynamic identity, facts, G/B and Arrival."""
from dataclasses import dataclass
from fogsim.errors import require
from fogsim.model.workflow import Workflow
from fogsim.instances.generated import (WorkflowInput, CandidateRecord, GenerationAttempt,
                                        AdmissionMapping, InputArchive)
from fogsim.instances.generation import release_rejection_reason
from fogsim.instances.materialize import materialize_workflow
from .events import JobArrivalEvent


@dataclass(frozen=True)
class AdmissionResult:
    accepted: bool
    workflow: Workflow | None
    reason_code: str | None

    def __post_init__(self):
        require(type(self.accepted) is bool, "accepted must be a boolean")
        if self.accepted:
            require(type(self.workflow) is Workflow and self.reason_code is None,
                    "successful admission requires workflow and no rejection reason")
        else:
            require(self.workflow is None and self.reason_code == "REJECTED_RELEASE_NOT_FUTURE",
                    "release rejection requires no workflow and its stable reason code")


class AdmissionService:
    def __init__(self, engine, source, environment, templates):
        self.engine, self.source, self.environment = engine, source, environment
        self.templates = tuple(templates)
        self._by_ref = {t.ref: t for t in templates}
        self._candidates, self._attempts, self._admissions = [], [], []
        self.generation_call_count = 0
        self.incomplete_attempt = False
        self.partial_candidate = None

    @property
    def archive(self):
        return InputArchive(self.templates, self.environment, tuple(self._candidates),
                            tuple(self._attempts), tuple(self._admissions))

    def summary(self):
        return dict(kind="random" if hasattr(self.source, "inputs") else "external_source",
                    generation_call_count=self.generation_call_count, attempt_count=len(self._attempts),
                    rejected_count=sum(not a.observed_acceptance for a in self._attempts),
                    consumed_attempt_count=len(self._attempts), incomplete_attempt=self.incomplete_attempt,
                    capture_complete=not self.incomplete_attempt and self.engine.initialization_complete,
                    coverage="observed_generation_calls_only")

    def attempt(self, cause, ctx):
        """Legacy convenience return; formal callers use admit's explicit result."""
        return self.admit(cause, ctx).workflow

    def admit(self, cause, ctx) -> AdmissionResult:
        """Generate and centrally admit exactly one candidate at the real call site.

        Ordinary release rejection is a value. Generation/validation/domain
        errors retain their original exception behavior and partial diagnostics.
        """
        engine, state, stats = self.engine, self.engine.state, self.engine.statistics
        require(cause.clock_time == state.clock_time and cause.owner_device_id == ctx.current_device.id,
                "generation cause/current state mismatch")
        require(engine.run_status in ("READY", "RUNNING"), "generation outside live round")
        self.generation_call_count += 1
        self.incomplete_attempt = True
        self.partial_candidate = None
        candidate = self.source.generate(cause, candidate_id=stats.generated_total)
        require(type(candidate) is WorkflowInput and candidate.candidate_id == stats.generated_total,
                "source returned wrong candidate identity")
        record_id = str(len(self._attempts) + 1)
        record = CandidateRecord(record_id, candidate)
        self.partial_candidate = record
        reason = release_rejection_reason(candidate, cause)
        validate = getattr(self.source, 'validate_admission', None)
        if validate is not None:
            validate(candidate, cause, reason)
        attempt = GenerationAttempt(len(self._attempts) + 1, cause, record_id, reason is None, reason)
        if reason is None:
            stats.check_acceptance_capacity(candidate.owner_device_id)
            template = self._by_ref.get(candidate.template_ref)
            require(template is not None, "source returned an unknown template")
            workflow = materialize_workflow(candidate, template, state, input_record_id=record_id)
            # Finish construction and all normal precondition checks before commit.
            state.validate_new_workflow(workflow)
            engine.trace.validate_new_workflow(workflow)
            state.register_workflow(workflow)
            engine.trace.register_workflow(workflow)
            stats.accepted(workflow)
            self._admissions.append(AdmissionMapping(record_id, workflow.id))
        self._candidates.append(record)
        self._attempts.append(attempt)
        self.incomplete_attempt = False
        self.partial_candidate = None
        if reason is None:
            # Release only after the complete candidate/admission is archived.
            if engine.config.edge_data_policy == "release_after_materialization":
                from .cleanup import release_edge_data
                report = release_edge_data(workflow, self.archive)
                engine.cleanup_totals["workflows_released"] += 1
                engine.cleanup_totals["released_task_count"] += report.released_task_count
                engine.cleanup_totals["removed_mapping_entry_count"] += report.removed_mapping_entry_count
            # Archive is complete before an event can make the workflow visible.
            ctx.emit(JobArrivalEvent(workflow))
            return AdmissionResult(True, workflow, None)
        return AdmissionResult(False, None, reason)
