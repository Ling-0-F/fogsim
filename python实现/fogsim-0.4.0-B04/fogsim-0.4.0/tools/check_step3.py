"""Scoped V06/V07/V08/V11 oracle with identical scripted sampler values.

Original Java constructor/setup/generate methods execute without source changes.
No events are triggered. Python's loop below is a test harness, not admission or
dynamic simulation. This tool deliberately does not implement the V16 exporter.
"""
from pathlib import Path
import argparse
from contextlib import ExitStack
from dataclasses import asdict, fields, replace
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fogsim import (load_experiment_config, prepare_random_input, sample_environment,
                    generate_workflow_input, release_rejection_reason)
from fogsim.experiment_config import EnvironmentConfig, WorkflowTypeRange
from fogsim.instances.generated import GenerationCause
from java_support import ORIGINAL, reference_jdk, sha


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def first_difference(left, right, path="$"):
    if isinstance(left, dict) and isinstance(right, dict):
        if left.keys() != right.keys(): return {"path": path, "left_keys": list(left), "right_keys": list(right)}
        for key in left:
            difference = first_difference(left[key], right[key], f"{path}.{key}")
            if difference: return difference
        return None
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right): return {"path": path, "left_length": len(left), "right_length": len(right)}
        for index, (a, b) in enumerate(zip(left, right)):
            difference = first_difference(a, b, f"{path}[{index}]")
            if difference: return difference
        return None
    equal = struct.pack(">d", left) == struct.pack(">d", right) if type(left) is type(right) is float else left == right
    return None if equal else {"path": path, "left": left, "right": right}


def make_cases():
    common = {"num_mobile_devices": 2, "num_edge_servers": 2, "num_cloud_servers": 2,
              "can_mobile_devices_process_tasks": True}
    ordinary = '<adag><job id="Z"/><job id="A"/><job id="join"/>' + \
               '<child ref="join"><parent ref="A"/><parent ref="Z"/></child></adag>'
    ordered = '<adag>' + ''.join(f'<job id="{x}"/>' for x in ("p0", "p1", "p2", "J", "X", "Y")) + \
        '<child ref="J"><parent ref="p2"/><parent ref="p1"/><parent ref="p0"/></child>' + \
        '<child ref="X"><parent ref="p0"/><parent ref="J"/></child><child ref="Y"><parent ref="p0"/></child></adag>'
    definitions = [
        ("normal", common, [2, 3], None, ordinary, 3, 2),
        ("local_disabled", dict(common, can_mobile_devices_process_tasks=False), [2, 3], None, ordinary, 3, 2),
        ("local_only", dict(common, num_edge_servers=0, num_cloud_servers=0), [2, 3], None, ordinary, 3, 2),
        ("first_device_rejected", common, [0, 3], None, ordinary, 3, 2),
        ("all_devices_rejected", common, [0, 0], None, ordinary, 3, 2),
        ("release_rounding", common, [2, 3, 1], float(1 << 53), ordinary, 3, 2),
        ("adjacency_accumulation", common, [2, 3], None, ordered, 6, 6),
    ]
    cases = []
    for name, environment, deltas, clock, xml, tasks, edges in definitions:
        n = len(deltas)
        role_values = {
            "processing_rate_device": [125 + 25*i for i in range(environment["num_mobile_devices"])],
            "processing_rate_edge": [250 + 50*i for i in range(environment["num_edge_servers"])],
            "processing_rate_cloud": [500 + 100*i for i in range(environment["num_cloud_servers"])],
            "upload_bandwidth_edge": [1024] * environment["num_edge_servers"],
            "download_bandwidth_edge": [1024] * environment["num_edge_servers"],
            "upload_bandwidth_cloud": [256, 512][:environment["num_cloud_servers"]],
            "download_bandwidth_cloud": [128, 256][:environment["num_cloud_servers"]],
            "workflow_type": [0] * n, "inter_release_time": deltas, "weight": [4, 2, 1][:n],
            "workload": [5000 + 137*i for i in range(n*tasks)],
            "data_size": [5120 + 17*i for i in range(n*tasks)],
            "edge_data": [100 + 7*i for i in range(n*edges)],
        }
        if name == "adjacency_accumulation": role_values["edge_data"] = [1e16, 1, 1, 1, 1, 5] * n
        cases.append({"name": name, "environment": environment, "extra_clock": clock,
                      "xml": xml, "role_values": role_values})
    return cases


def python_case(case, directory):
    cfg = load_experiment_config(ROOT / "configs/examples/step1_dynamic.json")
    cfg = replace(cfg, source=replace(cfg.source, dag_root=directory / "dax", seed=7,
        workflow_types=WorkflowTypeRange(0, 0), environment=EnvironmentConfig(**case["environment"])))
    inputs = prepare_random_input(cfg)
    names = {id(getattr(inputs.samplers, f.name)): f.name for f in fields(inputs.samplers)}
    streams = {key: iter(values) for key, values in case["role_values"].items()}
    calls = []
    def feed(sampler, rng):
        if rng is not inputs.rng: raise AssertionError("input stream not shared")
        role = names[id(sampler)]; value = next(streams[role])
        calls.append({"role": role, "value": float(value)})
        return int(value) if role == "workflow_type" else float(value)
    eligible, candidates, staged = [], [], [0] * cfg.source.environment.num_mobile_devices
    with ExitStack() as stack:
        for cls in {type(getattr(inputs.samplers, f.name)) for f in fields(inputs.samplers)}:
            stack.enter_context(patch.object(cls, "sample", feed))
        snapshot = sample_environment(cfg.source.environment, inputs, parameter_source="scripted-oracle")
        device_indices = {device.id: index for index, device in enumerate(snapshot.devices)}
        causes = [GenerationCause("initialize", d.id, 0) for d in snapshot.devices]
        if case["extra_clock"] is not None:
            # A direct numeric probe of the generation method, not an Arrival replay.
            causes.append(GenerationCause("after_arrival", "M0", case["extra_clock"], 0, 1))
        for cause in causes:
            candidate = generate_workflow_input(inputs, snapshot, cause, candidate_id=len(eligible))
            candidates.append(asdict(candidate))
            if release_rejection_reason(candidate, cause) is None:
                staged[device_indices[cause.owner_device_id]] += 1
                eligible.append({"id": candidate.candidate_id, "owner_device_id": candidate.owner_device_id,
                    "release_time": candidate.release_time, "weight": candidate.weight,
                    "tasks": [dict(asdict(t), java_index=i, options=[asdict(o) for o in t.options]) for i, t in enumerate(candidate.tasks)]})
    # expected G/Arrival counts are harness expectations for Java's release gate;
    # the Python production admission/event layer is deliberately not implemented.
    comparable = {"devices": [asdict(d) for d in snapshot.devices], "servers": [asdict(s) for s in snapshot.servers],
        "accepted_workflows": eligible, "calls": calls, "generated_total": len(eligible),
        "staged_arrivals": staged, "clock_time": case["extra_clock"] or 0.0, "shared_input_rng": True}
    write(directory / "python-candidates.json", candidates)
    write(directory / "python-raw.json", comparable)
    return comparable


def compile_oracle(output, explicit):
    java = Path(explicit or os.environ.get("FOGSIM_JAVA") or shutil.which("java") or "").resolve()
    version = reference_jdk(java)
    integrity = json.loads((ROOT / "outputs/source-integrity-v2.json").read_text())["files"]
    for relative, expected in integrity.items():
        if sha(ORIGINAL / relative) != expected: raise RuntimeError(f"original source changed: {relative}")
    main = ROOT / "tools/java/step3/fogsim/adapter/Step3Oracle.java"
    codec = ROOT / "tools/java/src/fogsim/adapter/Json.java"
    jars = sorted(p for p in (ORIGINAL / "libraries").glob("*.jar") if "javadoc" not in p.name)
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in [*sorted((ORIGINAL / "src").rglob("*.java")), *jars, main, codec]}
    fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    classes = output / "classes" / fingerprint[:16]; classes.mkdir(parents=True, exist_ok=True)
    javac = java.with_name("javac.exe" if java.suffix == ".exe" else "javac")
    compiler = [str(javac)] if javac.is_file() else [str(java), "-m", "jdk.compiler/com.sun.tools.javac.Main"]
    classpath = os.pathsep.join(str(p) for p in jars)
    command = [*compiler, "-encoding", "UTF-8", "-cp", classpath, "-sourcepath", str(ORIGINAL / "src"), "-d", str(classes), str(main), str(codec)]
    compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (output / "javac-stdout.txt").write_text(compiled.stdout)
    (output / "javac-stderr.txt").write_text(compiled.stderr)
    manifest = {"reference_jdk": version, "original_integrity_files": len(integrity), "inputs": hashes,
        "source_overlays": [], "sampler_inputs": "scripted test values, not RNG parity", "compiler_command": command,
        "compiler_exit_code": compiled.returncode}
    write(output / "java-build.json", manifest)
    if compiled.returncode: raise RuntimeError("Java compilation failed; see javac-stderr.txt")
    return java, os.pathsep.join([str(classes), classpath])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java"); parser.add_argument("--output", type=Path, default=ROOT / "outputs/step3")
    args = parser.parse_args(argv)
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    report = {"scope": "scripted original constructor/setup/generation only; no triggered events or full input export",
              "known_differences": ["Python retains edge maps; original Java clears maps", "scripted test samplers replace RNG sampling only"],
              "cases": [], "passed": False}
    try:
        java, classpath = compile_oracle(output, args.java)
        for case in make_cases():
            directory = output / "cases" / case["name"]; (directory / "dax").mkdir(parents=True, exist_ok=True)
            (directory / "dax/CyberShake_30.xml").write_text(case["xml"])
            request = directory / "request.json"; write(request, case)
            expected = python_case(case, directory)
            raw = directory / "java-raw.json"; raw.unlink(missing_ok=True)
            command = [str(java), "-cp", classpath, "fogsim.adapter.Step3Oracle", str(request), str(raw)]
            run = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=60)
            (directory / "java-stdout.txt").write_text(run.stdout); (directory / "java-stderr.txt").write_text(run.stderr)
            write(directory / "run.json", {"command": command, "cwd": str(directory), "exit_code": run.returncode})
            if run.returncode: raise RuntimeError(f"Java oracle failed for {case['name']}")
            actual = json.loads(raw.read_text()); difference = first_difference(expected, actual)
            result = {"case": case["name"], "classification": "NORMAL_PARITY_PASSED" if difference is None else "FAILED",
                      "passed": difference is None, "first_difference": difference}
            write(directory / "comparison.json", result); report["cases"].append(result)
        report["passed"] = all(case["passed"] for case in report["cases"])
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        report.update(classification="INFRASTRUCTURE_ERROR", error=f"{type(exc).__name__}: {exc}")
    write(output / "checks.json", report); print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__": raise SystemExit(main())
