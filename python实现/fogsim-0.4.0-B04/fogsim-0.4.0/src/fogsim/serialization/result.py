"""Explicit v2 score locations; physical values never use score tags."""
from copy import deepcopy
from dataclasses import asdict
import json
import math
from pathlib import Path
from fogsim.errors import InputError
from fogsim.gp.identity import validate_rule_manifest
from fogsim.rules.specs import SCORE_ENCODING_VERSION
from .f64 import encode_f64, decode_f64

_FIXED = {"status", "reason", "final_clock_time", "completed_workflow_count", "processed_event_count",
          "makespan", "workflow_records", "task_records", "events", "decisions"}
_DYNAMIC = {"reason_code", "generated_workflow_count", "arrived_workflow_count", "recorded_workflow_count",
            "mean_flow_time", "device_statistics", "source_summary", "diagnostics"}
_META = {"format", "schema_version", "score_encoding_version", "rule_manifest", "final_state"}


def _state_scores(state, visit, path):
    if state is None: return
    for ti, task in enumerate(state["tasks"]):
        for oi, option in enumerate(task["options"]):
            option["priority"] = visit(option["priority"], field_path=f"{path}.tasks[{ti}].options[{oi}].priority")


def _scores(rows, visit, path):
    for i, row in enumerate(rows):
        row["priority"] = visit(row["priority"], field_path=f"{path}[{i}].priority")


def _decision(row, visit, path):
    _scores(row["candidates"], visit, path + ".candidates")


def _error(row, visit, path):
    _scores(row["scored_prefix"], visit, path + ".scored_prefix")


def _score_fields(value, visit):
    """Schema paths, including every duplicated observation and failed snapshot."""
    for i, row in enumerate(value["decisions"]): _decision(row, visit, f"decisions[{i}]")
    for i, event in enumerate(value["events"]):
        path = f"events[{i}]"
        for phase in ("before", "after"): _state_scores(event[phase], visit, path + "." + phase)
        for j, action in enumerate(event["actions"]):
            if action["kind"] == "DECISION": _decision(action["decision"], visit, f"{path}.actions[{j}].decision")
            elif action["kind"] == "DECISION_ERROR": _error(action["decision_error"], visit, f"{path}.actions[{j}].decision_error")
    for i, error in enumerate(value["diagnostics"]["decision_errors"]): _error(error, visit, f"diagnostics.decision_errors[{i}]")
    _state_scores(value["final_state"], visit, "final_state")


def _check_decision_bindings(value):
    bindings = value["rule_manifest"]["bindings"]
    def check(row):
        role = {"ROUTING": "routing", "SEQUENCING": "sequencing"}.get(row.get("kind"))
        if role is None or row.get("rule_id") != bindings[role]["rule_id"]:
            raise InputError("GP_RULE_IDENTITY_MISMATCH: decision binding mismatch")
    for row in value["decisions"]: check(row)
    for event in value["events"]:
        for action in event["actions"]:
            if action["kind"] == "DECISION": check(action["decision"])
            elif action["kind"] == "DECISION_ERROR": check(action["decision_error"])
    for row in value["diagnostics"]["decision_errors"]: check(row)



def _physical_fields(value):
    """Validate named time/cache/metric slots; tags are only valid at score slots."""
    def number(item, path, nullable=False):
        if item is None and nullable: return
        if type(item) not in (int, float): raise InputError(f"{path}: expected finite JSON number")
        try: finite = math.isfinite(item)
        except OverflowError: finite = False
        if not finite: raise InputError(f"{path}: expected finite JSON number")
    def fields(row, names, path, nullable=False):
        for name in names: number(row[name], path + "." + name, nullable)
    def state(row, path):
        if type(row) is not dict: raise InputError(f"{path}: expected state object")
        fields(row, ("clock_time",), path)
        for task in row["tasks"]:
            for option in task["options"]: fields(option, ("ready_time",), path + ".options")
        for resource in row["resources"]:
            fields(resource, ("available_time", "queued_processing_time", "queued_total_time"), path + ".resources")
        for execution in row["executions"]:
            fields(execution, ("planned_start_time", "planned_compute_finish_time", "planned_finish_time"), path + ".executions")
        for workflow in row["workflows"]: fields(workflow, ("completion_time",), path + ".workflows", True)
        if "dynamic_statistics" in row:
            fields(row["dynamic_statistics"], ("cutoff_release_time",), path + ".dynamic_statistics")
    def decision(row, path):
        fields(row, ("time",), path)
        for candidate in row["candidate_state"]: fields(candidate, ("ready_time", "release_time"), path + ".candidate_state")
        for resource in row["resource_state"]:
            fields(resource, ("available_time", "queued_processing_time", "queued_total_time"), path + ".resource_state")
    fields(value, ("final_clock_time",), "result")
    fields(value, ("makespan",), "result", True)
    if "mean_flow_time" in value: fields(value, ("mean_flow_time",), "result", True)
    for row in value["workflow_records"]:
        fields(row, ("release_time",), "workflow_records")
        fields(row, ("completion_time", "flow_time"), "workflow_records", True)
    for row in value["task_records"]:
        fields(row, ("dispatch_time", "arrival_time", "start_time", "compute_finish_time", "finish_time"), "task_records", True)
        if row["plan"] is not None:
            fields(row["plan"], ("start_time", "compute_finish_time", "finish_time"), "task_records.plan")
    for row in value["decisions"]: decision(row, "decisions")
    for row in value["diagnostics"]["decision_errors"]: fields(row, ("time",), "decision_errors")
    for event in value["events"]:
        fields(event, ("time",), "events")
        for phase in ("before", "after"): state(event[phase], "events." + phase)
        for emitted in event["emitted"]: fields(emitted, ("time",), "events.emitted")
        for action in event["actions"]:
            if action["kind"] == "DECISION": decision(action["decision"], "actions.decision")
            elif action["kind"] == "DECISION_ERROR": fields(action["decision_error"], ("time",), "actions.decision_error")
            elif action["kind"] == "EMIT": fields(action["event"], ("time",), "actions.event")
    state(value["final_state"], "final_state")


def encode_result(result):
    value = asdict(result)
    profile = value.pop("output_profile")
    manifest, final, errors = (value.pop(k) for k in ("rule_manifest", "final_state", "decision_errors"))
    if profile == "v1": return value
    if profile != "v2": raise InputError("unknown result output profile")
    validate_rule_manifest(manifest)
    dynamic = "source_summary" in value
    value.update(format="fogsim.dynamic-result" if dynamic else "fogsim.fixed-result", schema_version=2,
        score_encoding_version=SCORE_ENCODING_VERSION, rule_manifest=manifest, final_state=final)
    value.setdefault("diagnostics", {})["decision_errors"] = errors
    _score_fields(value, encode_f64)
    _check_decision_bindings(value)
    _physical_fields(value)
    # Fails on any non-finite physical field; no global permissive encoder.
    json.dumps(value, allow_nan=False)
    return value


def decode_result(value):
    """Validate a v2 record, return detached data with float priorities only."""
    if type(value) is not dict: raise InputError("result must be an object")
    if type(value.get("schema_version")) is not int or value["schema_version"] != 2:
        raise InputError("unsupported result schema_version")
    fmt = value.get("format")
    if fmt not in ("fogsim.fixed-result", "fogsim.dynamic-result"): raise InputError("unknown result format")
    expected = _FIXED | _META | (_DYNAMIC if fmt == "fogsim.dynamic-result" else {"diagnostics"})
    if set(value) != expected: raise InputError("invalid result root fields")
    if value["score_encoding_version"] != SCORE_ENCODING_VERSION: raise InputError("unsupported score encoding")
    validate_rule_manifest(value["rule_manifest"])
    try:
        # JSON reader rejects NaN/Infinity/overflow even outside score fields.
        json.dumps(value, allow_nan=False)
        _physical_fields(value)
        result = deepcopy(value)
        _score_fields(result, decode_f64)
        _check_decision_bindings(result)
        return result
    except InputError: raise
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise InputError(f"invalid v2 result: {exc}") from exc


def read_result(path):
    from fogsim.instances.fixed import read_json
    return decode_result(read_json(Path(path)))
