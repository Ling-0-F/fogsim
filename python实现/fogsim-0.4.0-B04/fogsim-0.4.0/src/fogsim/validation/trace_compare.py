"""Chronological comparison with narrowly declared representation conversions.

No sorting, event realignment, score replacement or inferred missing decisions.
Raw inputs are not mutated. Failed runs are never accepted as passing parity.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path


def _difference(python, java, path, abs_tol, rel_tol):
    def mismatch(reason):
        return {"path": path, "python_value": python, "java_value": java, "reason": reason}
    if isinstance(python, bool) or isinstance(java, bool):
        return None if type(python) is type(java) and python == java else mismatch("boolean mismatch")
    if isinstance(python, dict) and isinstance(java, dict):
        for key in python:  # schema/insertion order, never sorting the trace
            if key not in java:
                return {"path": f"{path}.{key}", "python_value": python[key], "java_value": None,
                        "reason": "key missing from Java trace"}
            diff = _difference(python[key], java[key], f"{path}.{key}", abs_tol, rel_tol)
            if diff is not None:
                return diff
        if python.keys() != java.keys():
            return {"path": path, "python_value": list(python), "java_value": list(java), "reason": "extra Java object keys"}
        return None
    if isinstance(python, list) and isinstance(java, list):
        # Compare shared prefix first so a later missing item does not mask an earlier mismatch.
        for index, (left, right) in enumerate(zip(python, java)):
            diff = _difference(left, right, f"{path}[{index}]", abs_tol, rel_tol)
            if diff is not None:
                return diff
        return None if len(python) == len(java) else {
            "path": f"{path}[{min(len(python), len(java))}]", "python_value": len(python),
            "java_value": len(java), "reason": "list length differs after common prefix"}
    if type(python) in (int, float) and type(java) in (int, float):
        if type(python) is int and type(java) is int:
            return None if python == java else mismatch("integer mismatch")
        leaf = path.rsplit(".", 1)[-1]
        if leaf not in ("time", "priority", "makespan") and not leaf.endswith("_time"):
            return None if type(python) is type(java) and python == java else mismatch("identifier/count numeric type or value differs")
        if not math.isfinite(python) or not math.isfinite(java):
            return mismatch("non-finite value outside fixed-input trace contract")
        if path.endswith(".priority") and python == java == 0:
            return None if math.copysign(1, python) == math.copysign(1, java) else mismatch("priority signed zero differs")
        if math.isclose(python, java, abs_tol=abs_tol, rel_tol=rel_tol):
            return None
        return dict(mismatch("numeric mismatch"), absolute_error=abs(python - java))
    return None if type(python) is type(java) and python == java else mismatch("value/type mismatch")


def normalized_result(trace):
    """Return a detached comparable result; preserve native details in raw files."""
    result = deepcopy(trace["result"])
    language = trace["language"]
    if language not in ("python", "java"):
        raise ValueError("unsupported trace language")
    for event in result["events"]:
        for boundary in ("before", "after"):
            state = event[boundary]
            for resource in state["resources"]:
                if language == "python":
                    pending = resource.pop("pending_start")
                    resource["pending_starts"] = [] if pending is None else [pending]
                else:
                    resource["pending_starts"] = resource.pop("observed_pending_starts")
            if language == "java":
                for workflow in state["workflows"]:
                    # Only the known native default is translated. Unexpected nonzero values stay visible.
                    if not workflow["completion_registered"] and workflow["completion_time"] == 0.0:
                        workflow["completion_time"] = None
    return result


def compare_traces(python_trace, java_trace, *, abs_tol=1e-9, rel_tol=1e-12):
    if not all(math.isfinite(x) and x >= 0 for x in (abs_tol, rel_tol)):
        raise ValueError("comparison tolerances must be finite and nonnegative")
    if python_trace.get("language") != "python" or java_trace.get("language") != "java":
        raise ValueError("expected Python trace followed by Java trace")
    if python_trace.get("schema_version") != 1 or java_trace.get("schema_version") != 1:
        raise ValueError("unsupported trace schema")
    left, right = normalized_result(python_trace), normalized_result(java_trace)
    report = {
        "passed": False, "first_difference": None,
        "event_count": {"python": len(left["events"]), "java": len(right["events"])},
        "decision_count": {"python": len(left["decisions"]), "java": len(right["decisions"])},
        "tolerance": {"abs_tol": abs_tol, "rel_tol": rel_tol},
        "representation_mappings": [
            "unregistered Java workflow completion_time==0.0 -> Python None; nonzero values are not hidden",
            "Python pending_start -> zero/one item list; Java pending starts are observed event references only",
            "Java accepted Process plans/completed ProcessFinishEvent history -> task-keyed execution observations",
        ],
        "comparison_order": "input, config, loaded model; each event header, before, chronological actions, emitted, after, error; final records",
        "java_observations": deepcopy(java_trace.get("observations", {})),
    }
    def check(a, b, path, phase, event=None):
        diff = _difference(a, b, path, abs_tol, rel_tol)
        if diff is not None:
            diff["phase"] = phase
            if event is not None:
                diff.update(event_sequence=event["sequence"], event_type=event["type"], time=event["time"])
            report["first_difference"] = diff
            return False
        return True
    for field in ("input", "config", "loaded_model"):
        if not check(python_trace[field], java_trace[field], f"$.{field}", "input/config"):
            return report
    headers = ("sequence", "type", "time", "owner", "workflow_id", "task_id", "resource_id", "staging_device")
    for index, (a, b) in enumerate(zip(left["events"], right["events"])):
        path = f"$.result.events[{index}]"
        if not check({k: a[k] for k in headers}, {k: b[k] for k in headers}, path, "event header", a):
            return report
        for phase in ("before", "actions", "emitted", "after", "error"):
            if not check(a[phase], b[phase], f"{path}.{phase}", phase, a):
                return report
        if a.keys() != b.keys():
            check(list(a), list(b), path, "event schema", a)
            return report
    if not check(len(left["events"]), len(right["events"]), "$.result.events.length", "event count"):
        return report
    # Flat decisions are deliberately checked too; a damaged side index must not be ignored.
    for field in ("decisions", "task_records", "workflow_records", "status", "reason", "final_clock_time",
                  "completed_workflow_count", "processed_event_count", "makespan"):
        if not check(left[field], right[field], f"$.result.{field}", "final/decision index"):
            return report
    observations = java_trace.get("observations", {})
    if not check([], observations.get("anomalies", []), "$.observations.anomalies", "Java observer anomalies"):
        return report
    if left["status"] != "SUCCEEDED" or right["status"] != "SUCCEEDED":
        report["first_difference"] = {"path": "$.result.status", "python_value": left["status"],
            "java_value": right["status"], "phase": "acceptance", "reason": "failed runs are not parity passes"}
        return report
    if not left["events"] or len(left["events"]) != left["processed_event_count"]:
        report["first_difference"] = {"path": "$.result.events", "python_value": len(left["events"]),
            "java_value": len(right["events"]), "phase": "trace completeness", "reason": "missing detailed events or invalid count"}
        return report
    if left.keys() != right.keys():
        check(list(left), list(right), "$.result.keys", "result schema")
        return report
    if not check(True, observations.get("random_generator_is_null"), "$.observations.random_generator_is_null", "fixed-input isolation"):
        return report
    if not check(len(python_trace["input"]["workflows"]), observations.get("suppressed_generation_calls"),
                 "$.observations.suppressed_generation_calls", "fixed-input isolation"):
        return report
    report["passed"] = True
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare raw fixed-instance traces without reordering")
    parser.add_argument("python_trace", type=Path)
    parser.add_argument("java_trace", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--abs-tol", type=float, default=1e-9)
    parser.add_argument("--rel-tol", type=float, default=1e-12)
    args = parser.parse_args(argv)
    try:
        report = compare_traces(json.loads(args.python_trace.read_text(encoding="utf-8")),
                                json.loads(args.java_trace.read_text(encoding="utf-8")),
                                abs_tol=args.abs_tol, rel_tol=args.rel_tol)
    except (ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"trace error: {exc}\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "first_difference": report["first_difference"]}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
