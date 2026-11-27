"""Complete immutable candidate/archive values, separate from runtime objects.

This is not a generator or replay loader. Recorded durations remain authoritative;
formula/cumulative-value audits belong to generation and replay verification.
"""
from dataclasses import dataclass
from fogsim.errors import InputError
from fogsim.input_validation import integer, finite, text, boolean, choice, sequence, unique, dependencies, INT32_MAX
from fogsim.environment.spec import EnvironmentSnapshot
from .templates import DagTemplate, TemplateRef
from .spec import OptionSpec


@dataclass(frozen=True)
class TaskInput:
    id: str
    workload: float
    data_size: float
    total_input_data: float
    total_output_data: float
    options: tuple[OptionSpec, ...]

    def __post_init__(self):
        text(self.id, "task.id")
        for key in ("workload", "data_size", "total_input_data", "total_output_data"):
            object.__setattr__(self, key, finite(getattr(self, key), key, key == "workload"))
        options = sequence(self.options, OptionSpec, "task.options", True)
        for option in options:
            text(option.resource_id, "option.resource_id")
            for key in ("upload_time", "processing_time", "download_time"):
                finite(getattr(option, key), key, key == "processing_time")
        unique([o.resource_id for o in options], "task.options")
        object.__setattr__(self, "options", options)


@dataclass(frozen=True)
class EdgeInput:
    parent_id: str
    child_id: str
    data_size: float

    def __post_init__(self):
        text(self.parent_id, "parent_id")
        text(self.child_id, "child_id")
        object.__setattr__(self, "data_size", finite(self.data_size, "edge.data_size"))
        if self.parent_id == self.child_id:
            raise InputError("edge cannot reference itself")


@dataclass(frozen=True)
class WorkflowInput:
    candidate_id: int
    owner_device_id: str
    template_ref: TemplateRef
    release_time: float
    inter_release_time: float
    weight: float
    tasks: tuple[TaskInput, ...]
    edges: tuple[EdgeInput, ...]

    def __post_init__(self):
        # INT32_MAX can be proposed by a rejected attempt; accepting it would
        # overflow G+1 and is checked by the archive/admission boundary.
        integer(self.candidate_id, "candidate_id", 0, INT32_MAX)
        text(self.owner_device_id, "owner_device_id")
        if type(self.template_ref) is not TemplateRef:
            raise InputError("template_ref: expected TemplateRef")
        for key in ("release_time", "inter_release_time", "weight"):
            object.__setattr__(self, key, finite(getattr(self, key), key, key == "weight"))
        tasks = sequence(self.tasks, TaskInput, "workflow.tasks", True)
        edges = sequence(self.edges, EdgeInput, "workflow.edges")
        ids = [t.id for t in tasks]
        unique(ids, "workflow.tasks")
        dependencies([(e.parent_id, e.child_id) for e in edges], ids, "workflow.edges")
        object.__setattr__(self, "tasks", tasks)
        object.__setattr__(self, "edges", edges)


@dataclass(frozen=True)
class GenerationCause:
    phase: str
    owner_device_id: str
    clock_time: float
    causing_workflow_id: int | None = None
    event_sequence: int | None = None

    def __post_init__(self):
        choice(self.phase, ("initialize", "after_arrival"), "phase")
        text(self.owner_device_id, "cause.owner_device_id")
        object.__setattr__(self, "clock_time", finite(self.clock_time, "cause.clock_time"))
        if self.phase == "initialize":
            if self.clock_time != 0 or self.causing_workflow_id is not None or self.event_sequence is not None:
                raise InputError("initialize cause requires clock=0 and no triggering workflow/event")
        else:
            integer(self.causing_workflow_id, "causing_workflow_id", 0, INT32_MAX)
            if self.event_sequence is not None:
                integer(self.event_sequence, "event_sequence", 1)


@dataclass(frozen=True)
class GenerationAttempt:
    attempt_sequence: int
    cause: GenerationCause
    workflow_input_ref: str
    observed_acceptance: bool
    rejection_reason: str | None = None

    def __post_init__(self):
        integer(self.attempt_sequence, "attempt_sequence", 1)
        if type(self.cause) is not GenerationCause:
            raise InputError("cause: expected GenerationCause")
        text(self.workflow_input_ref, "workflow_input_ref")
        if self.workflow_input_ref != str(self.attempt_sequence):
            raise InputError("record_id must be the stable decimal attempt sequence")
        boolean(self.observed_acceptance, "observed_acceptance")
        if self.observed_acceptance:
            if self.rejection_reason is not None:
                raise InputError("accepted attempt cannot have rejection_reason")
        elif self.rejection_reason != "REJECTED_RELEASE_NOT_FUTURE":
            raise InputError("rejected attempt requires REJECTED_RELEASE_NOT_FUTURE")


@dataclass(frozen=True)
class CandidateRecord:
    record_id: str
    workflow_input: WorkflowInput

    def __post_init__(self):
        text(self.record_id, "record_id")
        if type(self.workflow_input) is not WorkflowInput:
            raise InputError("workflow_input: expected WorkflowInput")


@dataclass(frozen=True)
class AdmissionMapping:
    record_id: str
    workflow_id: int

    def __post_init__(self):
        text(self.record_id, "record_id")
        integer(self.workflow_id, "workflow_id", 0, INT32_MAX - 1)


@dataclass(frozen=True)
class InputArchive:
    templates: tuple[DagTemplate, ...]
    environment: EnvironmentSnapshot
    candidates: tuple[CandidateRecord, ...]
    generation_attempts: tuple[GenerationAttempt, ...]
    admissions: tuple[AdmissionMapping, ...]

    def __post_init__(self):
        templates = sequence(self.templates, DagTemplate, "templates")
        candidates = sequence(self.candidates, CandidateRecord, "candidates")
        attempts = sequence(self.generation_attempts, GenerationAttempt, "generation_attempts")
        admissions = sequence(self.admissions, AdmissionMapping, "admissions")
        if type(self.environment) is not EnvironmentSnapshot:
            raise InputError("environment: expected EnvironmentSnapshot")
        unique([t.ref for t in templates], "templates")
        typed_ids = [t.dag_type_id for t in templates if t.dag_type_id is not None]
        unique(typed_ids, "template type IDs")
        if typed_ids != sorted(typed_ids):
            raise InputError("standard templates must be stored in type ID order")
        unique([c.record_id for c in candidates], "candidates")
        unique([a.record_id for a in admissions], "admissions.records")
        unique([a.workflow_id for a in admissions], "admissions.workflow_ids")
        if tuple(a.attempt_sequence for a in attempts) != tuple(range(1, len(attempts) + 1)):
            raise InputError("attempt_sequence must be contiguous from 1")
        if tuple(c.record_id for c in candidates) != tuple(a.workflow_input_ref for a in attempts):
            raise InputError("candidates and attempts must be one-to-one in attempt order")
        templates_by_ref = {t.ref: t for t in templates}
        accepted = []
        accepted_inputs = {}
        initialization_count = 0
        triggered_workflows = set()
        previous_clock = 0.0
        for record, attempt in zip(candidates, attempts):
            workflow = record.workflow_input
            template = templates_by_ref.get(workflow.template_ref)
            if template is None:
                raise InputError("candidate references unknown template")
            if tuple(t.id for t in workflow.tasks) != tuple(t.xml_id for t in template.tasks):
                raise InputError("candidate task IDs/order do not match template")
            if {(e.parent_id, e.child_id) for e in workflow.edges} != set(template.dependencies):
                raise InputError("candidate edges do not match template dependencies")
            children = {t.xml_id: [] for t in template.tasks}
            for parent, child in template.dependencies:
                children[parent].append(child)
            sample_order = tuple((t.xml_id, child) for t in template.tasks for child in children[t.xml_id])
            if tuple((e.parent_id, e.child_id) for e in workflow.edges) != sample_order:
                raise InputError("candidate edges must follow task/children sampling order")
            expected = self.environment.eligible_resource_ids(workflow.owner_device_id)
            for task in workflow.tasks:
                if tuple(o.resource_id for o in task.options) != expected:
                    raise InputError("candidate options/order do not match eligible resources")
                for option in task.options:
                    if option.resource_id == workflow.owner_device_id and (option.upload_time != 0 or option.download_time != 0):
                        raise InputError("local upload/download must be zero")
            cause = attempt.cause
            if cause.owner_device_id != workflow.owner_device_id:
                raise InputError("attempt/candidate owner mismatch")
            if cause.clock_time < previous_clock:
                raise InputError("attempt clocks must not move backwards")
            previous_clock = cause.clock_time
            if cause.phase == "initialize":
                if (initialization_count >= len(self.environment.devices) or triggered_workflows
                        or cause.owner_device_id != self.environment.devices[initialization_count].id):
                    raise InputError("initialization attempts must follow device order exactly once")
                initialization_count += 1
            else:
                if initialization_count != len(self.environment.devices):
                    raise InputError("after_arrival cannot precede complete initialization")
                if cause.causing_workflow_id in triggered_workflows:
                    raise InputError("each arrival can cause only one generation attempt")
                trigger = accepted_inputs.get(cause.causing_workflow_id)
                if trigger is None or trigger.owner_device_id != cause.owner_device_id or trigger.release_time != cause.clock_time:
                    raise InputError("after_arrival must reference an accepted owner workflow at its release time")
                triggered_workflows.add(cause.causing_workflow_id)
            if workflow.candidate_id != len(accepted):
                raise InputError("candidate_id must equal G before acceptance; rejections do not consume IDs")
            if workflow.release_time != cause.clock_time + workflow.inter_release_time:
                raise InputError("release_time must preserve clock + sampled inter_release_time")
            if attempt.observed_acceptance != (workflow.release_time > cause.clock_time):
                raise InputError("observed acceptance conflicts with release > clock")
            if attempt.observed_acceptance:
                accepted.append(AdmissionMapping(record.record_id, workflow.candidate_id))
                accepted_inputs[workflow.candidate_id] = workflow
        if tuple(accepted) != admissions:
            raise InputError("admissions must exactly map accepted candidates in acceptance order")
        for name, value in (("templates", templates), ("candidates", candidates),
                            ("generation_attempts", attempts), ("admissions", admissions)):
            object.__setattr__(self, name, value)

    def workflow_input(self, record_id):
        for record in self.candidates:
            if record.record_id == record_id:
                return record.workflow_input
        raise InputError(f"unknown input record: {record_id}")
