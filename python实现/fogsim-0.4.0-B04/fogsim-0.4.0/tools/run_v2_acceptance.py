"""Run named parity, deterministic input sweep and explicitly expected boundaries.

The sweep generates fixed JSON inputs with Python random.Random, NOT the Java
workload distribution or an RNG port. Both runtimes receive those same bytes.
Known negative cases remain failed parity comparisons, never normalized away.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import random
import subprocess
import sys

from run_fixed_parity import ROOT, run_suite, run_case, run_java_request, write_json, sha
from java_support import java_tools
from v2_cases import V2_CASES

SEED = 20261029
SWEEP_SIZE = 96


def generated_input(index):
    rng = random.Random(SEED + index)
    device_count = 1 + index % 2
    devices = [{"id": f"M{i}", "type": "MOBILE", "can_process_tasks": index % 7 != 0}
               for i in range(device_count)]
    servers = [{"id": "E0", "type": "EDGE"}, {"id": "C0", "type": "CLOUD"}]
    resources = devices + servers
    if index % 3 == 0: resources = resources[::-1]
    workflows = []
    for wid in rng.sample(range(-20, 40), rng.randint(2, 5)):
        owner = rng.choice(devices)
        tasks = []
        for ti in range(rng.randint(1, 5)):
            times = {}
            candidates = ([owner] if owner["can_process_tasks"] else []) + servers
            for r in candidates:
                remote = r["type"] != "MOBILE"
                fractional = index % 4 == 0
                times[r["id"]] = {
                    "upload_time": rng.choice([0, .1, .2, .3]) if remote and fractional else rng.randint(0, 2) if remote else 0,
                    "processing_time": rng.choice([.1, .2, .3, .5, 1.0]) if fractional else rng.randint(1, 5),
                    "download_time": rng.choice([0, .1, .2]) if remote and fractional else rng.randint(0, 2) if remote else 0}
            tasks.append({"id": f"T{ti}", "execution_times": times})
        edges = [[f"T{i}", f"T{j}"] for i in range(len(tasks)) for j in range(i+1, len(tasks)) if rng.random() < .35]
        workflows.append({"id": wid, "owner_device_id": owner["id"],
                          "release_time": rng.choice([0, 0, .1, .3, 1, 2, 3]),
                          "tasks": tasks, "dependencies": edges})
    return {"time_unit": "s", "resources": resources, "workflows": workflows}


def positive_intervals(result):
    by_resource = {}
    for row in result["task_records"]:
        if (row["start_time"] is not None and row["finish_time"] is not None
                and row["finish_time"] > row["start_time"]):
            by_resource.setdefault(row["resource_id"], []).append(row)
    overlaps = []
    for rid, rows in by_resource.items():
        rows.sort(key=lambda r: r["start_time"])
        for a, b in zip(rows, rows[1:]):
            if a["finish_time"] > b["start_time"]:
                overlaps.append({"resource_id": rid, "first": [a["workflow_id"], a["task_id"]],
                                 "second": [b["workflow_id"], b["task_id"]],
                                 "first_finish": a["finish_time"], "second_start": b["start_time"]})
    return overlaps


def run_acceptance(output=None, java=None, sweep_size=SWEEP_SIZE):
    output = Path(output or ROOT / "outputs/v2").resolve()
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "summary.json", {"passed": False, "status": "RUNNING"})
    try:
        parity = run_suite(output / "parity", java)
        build = json.loads((output / "parity/build/build-manifest.json").read_text())
        java, _ = java_tools(java)
        classpath = build["runtime_classpath"]
        sweep = []
        for i in range(sweep_size):
            case = output / "sweep" / f"case-{i:03}"
            case.mkdir(parents=True, exist_ok=True)
            write_json(case / "input.json", generated_input(i))
            write_json(case / "config.json", {"instance": "input.json",
                "routing_rule": {"kind": "fcfs"} if i % 3 else {"kind": "fixed_resource", "resource_id": "E0"},
                "sequencing_rule": {"kind": "fcfs"}})
            report = run_case(case / "config.json", case, java, classpath, build["fingerprint"])
            sweep.append({"index": i, "passed": report["passed"], "events": report["event_count"],
                          "decisions": report["decision_count"], "first_difference": report["first_difference"]})
        # Injected local states are a separate method-boundary experiment.
        probe = output / "reservation-probe"; probe.mkdir(exist_ok=True)
        request = json.loads((output / "parity/v2_diamond/java-request.json").read_text())
        write_json(probe / "request.json", request)
        command = [str(java), "-cp", classpath, "fogsim.adapter.ReservationBoundaryMain",
                   str(probe / "request.json"), str(probe / "result.json")]
        (probe / "result.json").unlink(missing_ok=True)
        proc = subprocess.run(command, capture_output=True, text=True, timeout=30)
        write_json(probe / "process.json", {"command": command, "exit_code": proc.returncode,
                                          "stdout": proc.stdout, "stderr": proc.stderr})
        if proc.returncode: raise RuntimeError(f"reservation probe failed: {proc.stderr}")
        boundary = json.loads((probe / "result.json").read_text())
        # This is a negative acceptance: Python must fail explicitly; the unmodified
        # Java reference still overlaps, and the comparator must still report it.
        negative = output / "precision-collapse"
        comparison = run_case(ROOT / "configs/v2_precision_collapse.json", negative, java, classpath, build["fingerprint"])
        py = json.loads((negative / "python-raw.json").read_text())["result"]
        jv = json.loads((negative / "java-raw.json").read_text())["result"]
        precision = {"parity_passed": comparison["passed"], "python_status": py["status"],
                     "python_reason": py["reason"], "java_status": jv["status"],
                     "java_overlaps": positive_intervals(jv), "first_difference": comparison["first_difference"]}
        precision["expected_boundary_detected"] = (not comparison["passed"] and py["status"] == "FAILED"
            and py["makespan"] is None and "lost to floating-point precision" in py["reason"]
            and bool(precision["java_overlaps"]))
        checks = []
        for parent in [output / "parity", output / "sweep"]:
            for raw in parent.glob("*/java-raw.json"):
                trace = json.loads(raw.read_text())
                for check in trace["observations"]["reservation_checks"]:
                    checks.append({"case": raw.parent.name, **check})
        unexpected = [c for c in checks if c["original_allowed"] != (not c["observed_pending_starts"])]
        reservation = {"canAddToQueue_calls": len(checks), "guard_disagreements_in_normal_runs": unexpected,
                       "note": "busy visits short-circuit canAddToQueue; all event boundaries also compare pending starts"}
        totals = {"events_per_language": sum(c["events"]["python"] for c in parity["cases"]+sweep),
                  "decisions_per_language": sum(c["decisions"]["python"] for c in parity["cases"]+sweep)}
        expected_probe = [True, False, True, False]
        probe_ok = [c["equal"] for c in boundary["cases"]] == expected_probe
        summary = {"status": "COMPLETED", "passed": parity["passed"] and all(c["passed"] for c in sweep)
                   and probe_ok and precision["expected_boundary_detected"] and not unexpected,
                   "scope": "V2-01..05 fixed-input acceptance with explicit numeric domain boundary",
                   "named_parity": parity, "sweep_seed": SEED, "sweep_cases": sweep,
                   "totals": totals, "reservation_checks": reservation, "injected_boundary": boundary,
                   "precision_boundary": precision, "java_build_fingerprint": build["fingerprint"],
                   "not_validated": ["arbitrary-input equivalence", "DAX/Java RNG/workload distributions", "GP/training/paper-scale experiments"]}
        write_json(output / "summary.json", summary)
        return summary
    except Exception as exc:
        write_json(output / "summary.json", {"passed": False, "status": "ERROR", "error": f"{type(exc).__name__}: {exc}"})
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--java"); p.add_argument("--output", type=Path)
    a = p.parse_args()
    result = run_acceptance(a.output, a.java)
    print(json.dumps({k: result[k] for k in ("passed", "totals", "reservation_checks", "precision_boundary")}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__": raise SystemExit(main())
