"""Run the original Java scheduling core and Python with the same fixed input."""
from __future__ import annotations
import argparse
from dataclasses import replace
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fogsim import load_fixed_instance, simulate, create_engine
from fogsim.config import load_config
from fogsim.errors import InputError
from fogsim.validation.trace_compare import compare_traces, normalized_result
from java_support import prepare_and_compile, sha
from v2_cases import DEFAULT_CASES



def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def loaded_model(state):
    return {"resources": [{"id": r.id, "type": r.resource_type.value, "numeric_id": r.numeric_id,
                           "can_process_tasks": getattr(r, "can_process_tasks", None)} for r in state.resources_by_id.values()],
            "workflows": [{"id": w.id, "owner_device_id": w.owner_device.id, "release_time": w.release_time,
                "tasks": [{"id": t.id, "numeric_id": index, "parents": [p.id for p in t.parents],
                    "children": [c.id for c in t.children], "options": [
                        {"resource_id": o.resource.id, "processing_time": o.processing_time,
                         "upload_time": o.upload_time, "download_time": o.download_time} for o in t.options]}
                    for index, t in enumerate(w.tasks)]} for w in state.workflows_by_id.values()]}


def run_java_request(java, classpath, request, destination, *, stem="java"):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", stem):
        raise ValueError("invalid output stem")
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    request_path = destination / f"{stem}-request.json"
    trace_path = destination / f"{stem}-raw.json"
    if trace_path.resolve().parent != destination:
        raise ValueError("trace output must remain in its destination directory")
    write_json(request_path, request)
    # A failed new JVM must never be mistaken for a previous successful trace.
    trace_path.unlink(missing_ok=True)
    command = [str(java), "-Dfile.encoding=UTF-8", "-Duser.language=en", "-cp", classpath,
               "fogsim.adapter.FixedInstanceMain", str(request_path.resolve()), str(trace_path.resolve())]
    completed = subprocess.run(command, capture_output=True, timeout=120)
    (destination / f"{stem}-stdout.txt").write_bytes(completed.stdout)
    (destination / f"{stem}-stderr.txt").write_bytes(completed.stderr)
    write_json(destination / f"{stem}-process.json", {"command": command, "exit_code": completed.returncode,
                                                    "request_sha256": sha(request_path)})
    if not trace_path.is_file():
        raise RuntimeError(f"Java produced no trace, exit {completed.returncode}: {completed.stderr.decode('utf-8', errors='replace')[-3000:]}")
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    if completed.returncode not in (0, 1):
        raise RuntimeError(f"unexpected Java exit {completed.returncode}")
    return trace


def run_case(config_path, output, java, classpath, build_fingerprint):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    instance_path, config = load_config(config_path)
    config = replace(config, trace_enabled=True)
    spec = load_fixed_instance(instance_path)
    if any(not -(2**31) <= w.id < 2**31 for w in spec.workflows):
        raise InputError("Java reference workflow IDs must fit signed int32; IDs are never silently renumbered")
    # Validate fixed target eligibility before either side is executed.
    state = create_engine(spec, config).state
    request = {"schema_version": 1, "input": spec.to_dict(), "config": config.to_dict(), "record_trace": True}
    python_trace = {"schema_version": 1, "language": "python", "input": spec.to_dict(),
                    "config": config.to_dict(), "loaded_model": loaded_model(state),
                    "result": simulate(spec, config).to_dict()}
    write_json(output / "python-raw.json", python_trace)
    java_trace = run_java_request(java, classpath, request, output)
    report = compare_traces(python_trace, java_trace)
    write_json(output / "comparison.json", report)
    write_json(output / "python-normalized.json", normalized_result(python_trace))
    write_json(output / "java-normalized.json", normalized_result(java_trace))
    manifest = {
        "instance_path": str(instance_path), "instance_sha256": sha(instance_path),
        "config_path": str(Path(config_path).resolve()), "config_file_sha256": sha(config_path),
        "effective_config": config.to_dict(), "java_build_fingerprint": build_fingerprint,
        "resource_ids": [[r.id, r.resource_type.value, r.numeric_id] for r in state.resources_by_id.values()],
        "devices": [r.id for r in state.mobile_devices],
        "task_ids": [{"workflow_id": w.id, "string_id": t.id, "java_numeric_id": index,
                      "candidate_order": [o.resource.id for o in t.options]}
                     for w in state.workflows_by_id.values() for index, t in enumerate(w.tasks)],
        "initial_stage_order": [[w.id, w.owner_device.id, w.release_time] for w in state.workflows_by_id.values()],
        "raw_trace_sha256": {name: sha(output / name) for name in ("python-raw.json", "java-raw.json")},
    }
    write_json(output / "run-manifest.json", manifest)
    return report


def _run_suite(output=None, java=None, configs=None):
    output = Path(output or ROOT / "outputs/parity").resolve()
    java, classpath, build = prepare_and_compile(output / "build", java)
    configs = configs or [ROOT / f"configs/{name}.json" for name in DEFAULT_CASES]
    cases = []
    names = set()
    for config in configs:
        config = Path(config).resolve(); name = config.stem
        if name in names:
            raise ValueError(f"duplicate case output name: {name}")
        names.add(name)
        report = run_case(config, output / name, java, classpath, build["fingerprint"])
        cases.append({"case": name, "passed": report["passed"], "events": report["event_count"],
                      "decisions": report["decision_count"], "first_difference": report["first_difference"],
                      "report": f"{name}/comparison.json"})
    summary = {"scope": "0.2 named fixed-instance acceptance; positive representable execution intervals",
               "passed": all(c["passed"] for c in cases), "cases": cases,
               "java_build_fingerprint": build["fingerprint"],
               "first_difference": next((dict(case=c["case"], **c["first_difference"])
                    for c in cases if c["first_difference"] is not None), None),
               "not_validated": ["arbitrary-input equivalence", "full multi-device model extension",
                                 "precision-collapse inputs (separate negative acceptance)",
                                 "random generation/GP/training statistics"]}
    write_json(output / "summary.json", summary)
    return summary


def run_suite(output=None, java=None, configs=None):
    output = Path(output or ROOT / "outputs/parity").resolve()
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "summary.json", {"status": "RUNNING", "passed": False})
    try:
        return _run_suite(output, java, configs)
    except Exception as exc:
        write_json(output / "summary.json", {"status": "ERROR", "passed": False,
                   "error": f"{type(exc).__name__}: {exc}", "first_difference": None,
                   "reason": "infrastructure/input failure; no parity conclusion"})
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java")
    parser.add_argument("--config", type=Path, action="append", help="repeat for selected cases; default fourteen named configs")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/parity")
    args = parser.parse_args(argv)
    try:
        summary = run_suite(args.output, args.java, args.config)
    except (InputError, ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        parser.exit(2, f"parity run error: {exc}\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
