"""Dynamic results extend RunResult without changing fixed-mode serialization."""
from copy import deepcopy
from dataclasses import dataclass, asdict
from .metrics import RunResult, result_observations
from fogsim.numerics import checked_number


@dataclass(frozen=True)
class DynamicRunResult(RunResult):
    reason_code: str | None
    generated_workflow_count: int
    arrived_workflow_count: int
    recorded_workflow_count: int
    mean_flow_time: float | None
    device_statistics: list
    source_summary: dict
    diagnostics: dict


def collect_dynamic_result(engine):
    state, stats = engine.state, engine.statistics
    makespan = mean = None
    if engine.run_status == "SUCCEEDED":
        recorded = tuple(stats.recorded_workflows.values())
        makespan = checked_number(max(w.completion_time for w in recorded) - min(w.release_time for w in recorded),
                                  "statistical makespan")
        total = 0.0
        for w in recorded:
            total = checked_number(total + w.flow_time, "statistical flow-time sum")
        mean = checked_number(total / len(recorded), "mean flow time")
    workflows = [{"workflow_id": w.id, "owner_device_id": w.owner_device.id, "release_time": w.release_time,
                  "completion_time": w.completion_time, "flow_time": w.flow_time,
                  "recorded": w.id in stats.recorded_workflows, "weight": w.weight,
                  "dag_type_id": w.dag_type_id, "template_hash": w.template_hash, "input_record_id": w.input_record_id}
                 for w in state.workflows_by_id.values()]
    tasks = deepcopy(list(engine.trace.tasks.values()))
    for row in tasks:
        task = state.tasks_by_key[row["workflow_id"], row["task_id"]]
        row["java_index"] = task.java_index
    devices = [dict(device_id=d.id, generated_workflow_count=stats.generated_by_device[d.id],
                    completed_workflow_count=stats.completed_by_device[d.id],
                    recorded_workflow_count=stats.recorded_by_device[d.id]) for d in state.mobile_devices]
    source = engine.admission.summary() if engine.admission is not None else dict(
        kind="random", generation_call_count=0, attempt_count=0, rejected_count=0, consumed_attempt_count=0,
        incomplete_attempt=False, capture_complete=False, coverage="environment_preparation_failed")
    diagnostics = dict(run_index=engine.run_index, operation=engine.operation, public_seed=engine.public_seed,
                       initial_cutoff_release_time=engine.initial_cutoff,
                       cutoff_release_time=stats.cutoff_release_time,
                       legacy_nonrecording_events=stats.legacy_nonrecording_events,
                       guard_hits=deepcopy(engine.failure_hits), initialization_complete=engine.initialization_complete,
                       initialization_actions=deepcopy(engine.initialization_actions),
                       environment_fingerprint=engine.environment.fingerprint if engine.environment is not None else None)
    if hasattr(engine, "cleanup_totals"):
        diagnostics["edge_data_cleanup"] = dict(policy=engine.config.edge_data_policy, **engine.cleanup_totals)
    # Full native state, version and Python provenance are retained on Engine;
    # result diagnostics contain their stable identifiers, not a second RNG.
    for name in ("rng_start", "rng_ready", "rng_final"):
        value = getattr(engine, name, None)
        diagnostics[name + "_fingerprint"] = value.fingerprint if value is not None else None
    return DynamicRunResult(engine.run_status, engine.stop_reason, state.clock_time,
        len(state.completed_workflows), engine.processed_event_count, makespan, workflows, tasks,
        deepcopy(engine.trace.events), deepcopy(engine.trace.decisions), engine.reason_code,
        stats.generated_total, state.arrived_workflow_count, stats.recorded_total, mean,
        devices, source, diagnostics, output_profile=getattr(engine, "output_profile", "v1"), **result_observations(engine))
