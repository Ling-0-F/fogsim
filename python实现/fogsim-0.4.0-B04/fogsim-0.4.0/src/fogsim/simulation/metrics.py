from dataclasses import dataclass, asdict, field
from copy import deepcopy
from fogsim.errors import InputError


@dataclass(frozen=True)
class RunResult:
    status: str
    reason: str | None
    final_clock_time: float
    completed_workflow_count: int
    processed_event_count: int
    makespan: float | None
    workflow_records: list
    task_records: list
    events: list
    decisions: list
    output_profile: str = field(default="v1", kw_only=True, repr=False)

    rule_manifest: dict | None = field(default=None, kw_only=True, repr=False)
    final_state: dict | None = field(default=None, kw_only=True, repr=False)
    decision_errors: list = field(default_factory=list, kw_only=True, repr=False)

    def to_dict(self):
        from fogsim.serialization.result import encode_result
        return encode_result(self)


def collect_result(engine):
    s = engine.state
    makespan = None
    if engine.run_status == "SUCCEEDED":
        makespan = max(w.completion_time for w in s.completed_workflows.values()) - min(w.release_time for w in s.workflows_by_id.values())
    return RunResult(engine.run_status, engine.stop_reason, s.clock_time,
        len(s.completed_workflows), engine.processed_event_count, makespan,
        [{"workflow_id": w.id, "owner_device_id": w.owner_device.id, "release_time": w.release_time,
          "completion_time": w.completion_time, "flow_time": w.flow_time} for w in s.workflows_by_id.values()],
        deepcopy(list(engine.trace.tasks.values())), deepcopy(engine.trace.events), deepcopy(engine.trace.decisions),
        output_profile=getattr(engine, "output_profile", "v1"),
        **result_observations(engine))


def result_observations(engine):
    if getattr(engine, "output_profile", "v1") != "v2":
        return {}
    from .trace import state_snapshot
    return dict(rule_manifest=deepcopy(engine.prepared_rules.rule_manifest),
        final_state=state_snapshot(engine.state), decision_errors=deepcopy(engine.trace.decision_errors))
