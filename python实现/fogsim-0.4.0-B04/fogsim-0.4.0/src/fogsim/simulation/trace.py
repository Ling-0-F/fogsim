"""Snapshots are output only. Scheduling code never reads these records."""
from copy import deepcopy
from fogsim.errors import StateError


def event_snapshot(event):
    option = getattr(event, "option", None)
    ex = getattr(event, "execution", None)
    if ex is not None:
        option = ex.option
    workflow = option.task.workflow if option else event.workflow
    return {"type": type(event).__name__, "time": event.time,
            "owner": event.owner.id, "workflow_id": workflow.id,
            "task_id": option.task.id if option else None,
            "resource_id": option.resource.id if option else None}


def state_snapshot(state):
    return {
        "clock_time": state.clock_time,
        "pending_arrivals": list(state.pending_arrivals),
        "active_workflows": list(state.active_workflows),
        "completed_workflows": list(state.completed_workflows),
        "tasks": [{"key": list(t.key), "dispatched": t.dispatched, "completed": t.completed,
                   "options": [{"resource_id": o.resource.id, "ready_time": o.ready_time, "priority": o.priority}
                               for o in t.options]} for t in state.tasks_by_key.values()],
        "resources": [{"id": r.id, "numeric_id": r.numeric_id, "type": r.resource_type.value,
                       "available_time": r.available_time,
                       "waiting_queue": [list(o.key) for o in r.waiting_queue],
                       "queued_processing_time": r.queued_processing_time,
                       "queued_total_time": r.queued_total_time,
                       "pending_start": list(r.pending_start.task.key) if r.pending_start else None,
                       "completed_task_count": r.completed_task_count}
                      for r in state.resources_by_id.values()],
        "executions": [{"task": list(e.task.key), "resource_id": e.resource.id,
                        "planned_start_time": e.start_time, "planned_compute_finish_time": e.compute_finish_time,
                        "planned_finish_time": e.finish_time} for e in state.executions_by_task.values()],
        "workflows": [{"id": w.id, "completion_registered": w.completion_registered,
                       "completion_time": w.completion_time,
                       "completed_tasks": [e.task.id for e in w.completed_executions]}
                      for w in state.workflows_by_id.values()],
    }


class TraceRecorder:
    def __init__(self, enabled, state, *, manifest=None):
        self.enabled = enabled
        self.manifest = deepcopy(manifest)
        self.decision_errors = []
        self.events, self.decisions = [], []
        self.current_event_sequence = 0
        self.actions = []
        self.tasks = {t.key: {"workflow_id": t.workflow.id, "task_id": t.id,
                             "resource_id": None, "dispatch_time": None, "arrival_time": None,
                             "start_time": None, "compute_finish_time": None, "finish_time": None,
                             "plan": None} for t in state.tasks_by_key.values()}

    def validate_new_workflow(self, workflow):
        from fogsim.errors import require
        require(all(t.key not in self.tasks for t in workflow.tasks), "duplicate task facts")

    def register_workflow(self, workflow):
        self.validate_new_workflow(workflow)
        for t in workflow.tasks:
            self.tasks[t.key] = {"workflow_id": workflow.id, "task_id": t.id,
                "resource_id": None, "dispatch_time": None, "arrival_time": None,
                "start_time": None, "compute_finish_time": None, "finish_time": None, "plan": None}

    def append(self, record):
        if self.enabled:
            self.events.append(deepcopy(record))

    def begin_event(self, sequence):
        self.current_event_sequence = sequence
        self.actions = []

    def emitted(self, record):
        if self.enabled:
            self.actions.append(deepcopy({"kind": "EMIT", "event": record}))

    def lifecycle(self, option, action, time):
        row = self.tasks[option.task.key]
        row["resource_id"] = option.resource.id
        row[action + "_time"] = time

    def plan(self, execution):
        self.tasks[execution.task.key]["plan"] = {
            "start_time": execution.start_time,
            "compute_finish_time": execution.compute_finish_time,
            "finish_time": execution.finish_time,
        }

    def started(self, execution):
        self.lifecycle(execution.option, "start", execution.start_time)
        # Derived from actual start, not a fifth event or an observed compute completion.
        self.tasks[execution.task.key]["compute_finish_time"] = execution.compute_finish_time

    def decision(self, context, scores, best):
        if self.enabled:
            record = deepcopy({
                "event_sequence": self.current_event_sequence,
                "decision_sequence": len(self.decisions) + 1,
                "time": context.view.clock_time, "kind": context.kind.value,
                "round": context.round_number, "candidates": scores, "selected": list(best.key),
                "candidate_state": [{"option": list(o.key), "ready_time": o.ready_time,
                    "dispatched": o.task.dispatched, "completed": o.task.completed,
                    "release_time": o.task.workflow.release_time,
                    "owner_numeric_id": o.task.workflow.owner_device.numeric_id} for o in context.candidates],
                "resource_state": [{"id": r.id, "available_time": r.available_time,
                    "queue": [list(o.key) for o in r.waiting_queue],
                    "queued_processing_time": r.queued_processing_time,
                    "queued_total_time": r.queued_total_time} for r in context.view.resources],
            })
            if self.manifest is not None:
                record["rule_id"] = self.manifest["bindings"][context.kind.value.lower()]["rule_id"]
            self.decisions.append(record)
            self.actions.append(deepcopy({"kind": "DECISION", "decision": record}))

    def decision_error(self, context, scores, index, option, exc):
        if self.manifest is None:
            return
        role = context.kind.value.lower()
        record = dict(event_sequence=self.current_event_sequence, time=context.view.clock_time,
            kind=context.kind.value, role=role, round_number=context.round_number,
            rule_id=self.manifest["bindings"][role]["rule_id"],
            failed_candidate_key=list(option.key), failed_candidate_index=index,
            scored_prefix=deepcopy(scores),
            error=dict(code=getattr(exc, "reason_code", getattr(exc, "code",
                       "STATE_INVARIANT_VIOLATION" if isinstance(exc, StateError) else "UNEXPECTED_PROGRAMMING_EXCEPTION")),
                       type=type(exc).__name__, message=str(exc)))
        self.decision_errors.append(deepcopy(record))
        if self.enabled:
            self.actions.append(dict(kind="DECISION_ERROR", decision_error=deepcopy(record)))
