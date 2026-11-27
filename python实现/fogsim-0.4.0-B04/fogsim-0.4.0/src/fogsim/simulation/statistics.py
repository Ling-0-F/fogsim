"""Java jobsCompleted compatibility, separate from physical completion facts."""
from dataclasses import dataclass, field
from fogsim.errors import require, NumericDerivationError
from fogsim.input_validation import INT32_MAX


@dataclass(eq=False)
class DynamicStatistics:
    num_jobs_recorded: int
    warmup_jobs: int
    cutoff_release_time: float
    generated_by_device: dict
    completed_by_device: dict
    recorded_by_device: dict
    generated_total: int = 0
    recorded_workflows: dict = field(default_factory=dict)
    legacy_nonrecording_events: int = 0

    @classmethod
    def create(cls, config, devices, initial_cutoff):
        ids = [d.id for d in devices]
        return cls(config.num_jobs_recorded, config.warmup_jobs, initial_cutoff,
                   dict.fromkeys(ids, 0), dict.fromkeys(ids, 0), dict.fromkeys(ids, 0))

    @property
    def recorded_total(self):
        return len(self.recorded_workflows)

    def check_acceptance_capacity(self, owner_id):
        for label, value in (("generated_total", self.generated_total),
                             ("generated_by_device", self.generated_by_device[owner_id])):
            if value >= INT32_MAX:
                raise NumericDerivationError(label + " + 1 exceeds int32", value + 1)

    def accepted(self, workflow):
        self.generated_total += 1
        self.generated_by_device[workflow.owner_device.id] += 1
        if self.generated_total < self.num_jobs_recorded + self.warmup_jobs:
            # Assignment, not max: a later device may lower this boundary.
            self.cutoff_release_time = workflow.release_time

    def completed(self, workflow):
        # Only the caller receiving True from register_completion may call this.
        owner = workflow.owner_device.id
        self.completed_by_device[owner] += 1
        if (self.generated_total > self.warmup_jobs and workflow.id >= 0
                and workflow.release_time <= self.cutoff_release_time):
            require(workflow.id not in self.recorded_workflows, "duplicate statistical completion")
            self.recorded_workflows[workflow.id] = workflow
            self.recorded_by_device[owner] += 1

    def after_event(self, previous_recorded):
        if self.recorded_total > self.warmup_jobs and self.recorded_total == previous_recorded:
            # Original global count is cumulative, not a consecutive streak.
            self.legacy_nonrecording_events += 1

    def guard_hits(self, state):
        hits = []
        def hit(code, actual, limit, resource_id=None):
            if actual > limit:
                hits.append(dict(reason_code=code, actual=actual, limit=limit, resource_id=resource_id))
        hit("JAVA_NONRECORDING_EVENT_LIMIT", self.legacy_nonrecording_events, 400000)
        for device in state.mobile_devices:
            if device.can_process_tasks:
                hit("JAVA_DEVICE_QUEUE_LIMIT", len(device.waiting_queue), 400, device.id)
        for server in state.servers:
            hit("JAVA_SERVER_QUEUE_LIMIT", len(server.waiting_queue), 400, server.id)
        hit("JAVA_GENERATED_JOB_LIMIT", self.generated_total,
            500 * (self.num_jobs_recorded + self.warmup_jobs))
        return hits

    def check_invariants(self, state):
        require(self.generated_total == len(state.workflows_by_id), "dynamic G/index mismatch")
        require(self.generated_total == sum(self.generated_by_device.values()), "dynamic device G mismatch")
        require(self.recorded_total == sum(self.recorded_by_device.values()), "dynamic device R mismatch")
        require(sum(self.completed_by_device.values()) == len(state.completed_workflows), "dynamic physical count mismatch")
        for wid, workflow in self.recorded_workflows.items():
            require(state.completed_workflows.get(wid) is workflow, "statistical workflow is not physically complete")
        for owner in self.generated_by_device:
            require(self.generated_by_device[owner] == sum(w.owner_device.id == owner for w in state.workflows_by_id.values()),
                    "generated owner mismatch")
            require(self.completed_by_device[owner] == sum(w.owner_device.id == owner for w in state.completed_workflows.values()),
                    "completed owner mismatch")
            require(self.recorded_by_device[owner] == sum(w.owner_device.id == owner for w in self.recorded_workflows.values()),
                    "recorded owner mismatch")
