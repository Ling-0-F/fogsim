"""V02 topology parity and frozen V04 distribution checks, independent of scheduling.

Runs Python and, unless --python-only, original Java parser/samplers. Writes an
explicit non-passing infrastructure report if Java compilation/execution fails.
"""
from pathlib import Path
import argparse
from dataclasses import fields
import hashlib
import json
import math
import os
import platform
import random
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fogsim import load_experiment_config, load_dax_catalog
from fogsim.experiment_config import SamplerParameters, WorkflowTypeRange
from fogsim.randomness.samplers import make_samplers, UniformIntegerSampler
from fogsim.seed import encode_seed
from java_support import ORIGINAL, reference_jdk, sha

SAMPLES = 100000
SEEDS = (0, 1, 20261104)
THRESHOLDS = {"discrete_absolute_frequency_error": .01, "uniform_mean_width_fraction": .01,
              "exponential_mean_relative_error": .02, "exponential_variance_relative_error": .05,
              "exponential_cdf_absolute_error": .01}


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def summarize(sampler, rng, discrete):
    total = square = 0.0
    minimum, maximum = math.inf, -math.inf
    below = 0
    counts = {}
    for _ in range(SAMPLES):
        value = sampler.sample(rng)
        if not math.isfinite(value):
            raise ValueError("non-finite sample")
        total += value; square += value * value
        minimum = min(minimum, value); maximum = max(maximum, value)
        below += value <= 100
        if discrete:
            key = str(float(value))
            counts[key] = counts.get(key, 0) + 1
    mean = total / SAMPLES
    return {"mean": mean, "variance": square / SAMPLES - mean * mean,
            "minimum": minimum, "maximum": maximum, "cdf_at_100": below / SAMPLES, "counts": counts}


def python_distributions():
    bundle = make_samplers(SamplerParameters(), WorkflowTypeRange(0, 19))
    roles = {item.name: getattr(bundle, item.name) for item in fields(bundle)}
    roles["integer_singleton"] = UniformIntegerSampler(0, 0)
    records = []
    for seed in SEEDS:
        for role, sampler in roles.items():
            discrete = role in ("workflow_type", "integer_singleton", "weight") or "bandwidth" in role
            records.append({"role": role, "seed": seed, "samples": SAMPLES,
                            "statistics": summarize(sampler, random.Random(encode_seed(seed)), discrete)})
    return records


def check_distributions(records):
    parameters = SamplerParameters()
    checked = []
    for record in records:
        role, stats = record["role"], record["statistics"]
        checks = {}
        if role in ("workload", "data_size", "edge_data", "processing_rate_device", "processing_rate_edge", "processing_rate_cloud"):
            bounds = getattr(parameters, role)
            checks["range"] = bounds.lower <= stats["minimum"] <= stats["maximum"] <= bounds.upper
            checks["mean"] = abs(stats["mean"] - (bounds.lower + bounds.upper) / 2) <= (bounds.upper - bounds.lower) * .01
        elif role == "inter_release_time":
            checks = {"nonnegative": stats["minimum"] >= 0,
                      "mean": abs(stats["mean"] / 100 - 1) <= .02,
                      "variance": abs(stats["variance"] / 10000 - 1) <= .05,
                      "cdf": abs(stats["cdf_at_100"] - (1 - math.exp(-1))) <= .01}
        else:
            if role == "weight":
                probabilities = {"4.0": .2, "2.0": .6, "1.0": .2}
            elif "cloud" in role:
                probabilities = {"256.0": .2, "512.0": .6, "128.0": .2}
            elif "edge" in role:
                probabilities = {"1024.0": 1.0}
            elif role == "integer_singleton":
                probabilities = {"0.0": 1.0}
            else:
                probabilities = {str(float(i)): 1 / 20 for i in range(20)}
            checks["support"] = set(stats["counts"]) <= set(probabilities)
            checks["frequencies"] = all(abs(stats["counts"].get(k, 0) / SAMPLES - p) <= .01 for k, p in probabilities.items())
            if len(probabilities) == 1:
                checks["exact_singleton"] = stats["counts"] == {next(iter(probabilities)): SAMPLES}
        checked.append(dict(record, checks=checks, passed=all(checks.values())))
    expected = {(seed, role) for seed in SEEDS for role in (
        "workflow_type", "inter_release_time", "weight", "workload", "data_size", "edge_data",
        "processing_rate_device", "processing_rate_edge", "processing_rate_cloud", "upload_bandwidth_edge",
        "download_bandwidth_edge", "upload_bandwidth_cloud", "download_bandwidth_cloud", "integer_singleton")}
    actual = [(r["seed"], r["role"]) for r in records]
    complete = len(actual) == len(expected) and set(actual) == expected and all(r["samples"] == SAMPLES for r in records)
    return {"passed": complete and all(r["passed"] for r in checked), "coverage_complete": complete, "records": checked}


def python_topology():
    config = load_experiment_config(ROOT / "configs/examples/step1_dynamic.json")
    catalog = load_dax_catalog(config)
    result = []
    for template in catalog.templates:
        parents, children = template.adjacency()
        result.append({"dag_type_id": template.dag_type_id, "filename": template.source_name,
                       "tasks": [{"xml_id": t.xml_id, "java_index": t.java_index,
                                  "parents": list(parents[t.xml_id]), "children": list(children[t.xml_id])}
                                 for t in template.tasks]})
    return result


def java_oracle(output, java):
    java = Path(java or os.environ.get("FOGSIM_JAVA") or shutil.which("java") or "").resolve()
    reference = reference_jdk(java)
    integrity_path = ROOT / "outputs/source-integrity-v2.json"
    expected_originals = json.loads(integrity_path.read_text())["files"]
    for relative, expected in expected_originals.items():
        if sha(ORIGINAL / relative) != expected:
            raise RuntimeError(f"original Java source/dependency differs from verified baseline: {relative}")
    jars = sorted(p for p in (ORIGINAL / "libraries").glob("*.jar") if "javadoc" not in p.name)
    main = ROOT / "tools/java/step2/fogsim/adapter/Step2Oracle.java"
    codec = ROOT / "tools/java/src/fogsim/adapter/Json.java"
    source_inputs = [*sorted((ORIGINAL / "src").rglob("*.java")), main, codec, *jars]
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in source_inputs}
    fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    classes = output / "classes" / fingerprint[:16]
    classes.mkdir(parents=True, exist_ok=True)
    javac = java.with_name("javac.exe" if java.suffix == ".exe" else "javac")
    compiler = [str(javac)] if javac.is_file() else [str(java), "-m", "jdk.compiler/com.sun.tools.javac.Main"]
    classpath = os.pathsep.join(str(p) for p in jars)
    command = [*compiler, "-encoding", "UTF-8", "-d", str(classes), "-cp", classpath,
               "-sourcepath", str(ORIGINAL / "src"), str(main), str(codec)]
    compilation = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (output / "javac-stdout.txt").write_text(compilation.stdout)
    (output / "javac-stderr.txt").write_text(compilation.stderr)
    manifest = {"original_source_unchanged": True, "constructor_overlays": [],
                "original_integrity_files": len(expected_originals), "original_integrity_manifest_sha256": sha(integrity_path),
                "scope": "original DAX parser and samplers, not dynamic scheduling",
                "inputs": hashes, "reference_jdk": reference, "compiler_command": command,
                "compiler_exit_code": compilation.returncode, "compiler_mode": "javac" if javac.is_file() else "jdk.compiler module"}
    write(output / "java-build.json", manifest)
    if compilation.returncode:
        raise RuntimeError("Java compile failed; see javac-stderr.txt")
    raw_path = output / "java-raw.json"
    raw_path.unlink(missing_ok=True)
    command = [str(java), "-cp", os.pathsep.join([str(classes), classpath]), "fogsim.adapter.Step2Oracle", str(ROOT / "dax"), str(raw_path)]
    run = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (output / "java-stdout.txt").write_text(run.stdout)
    (output / "java-stderr.txt").write_text(run.stderr)
    manifest.update(runtime_command=command, runtime_exit_code=run.returncode)
    write(output / "java-build.json", manifest)
    if run.returncode:
        raise RuntimeError("Java oracle failed; see java-stderr.txt")
    return json.loads(raw_path.read_text())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java")
    parser.add_argument("--python-only", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/step2")
    args = parser.parse_args(argv)
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    topology = python_topology()
    write(output / "python-topology.json", topology)
    py = check_distributions(python_distributions())
    write(output / "python-distributions.json", py)
    report = {"scope": "V02 topology and V04 independent distribution checks; no scheduling parity",
              "python": platform.python_version(), "seeds": SEEDS, "samples_per_role_seed": SAMPLES,
              "thresholds": THRESHOLDS, "python_distributions_passed": py["passed"],
              "java_status": "NOT_EXECUTED", "topology_status": "NOT_EXECUTED", "passed": False}
    if not args.python_only:
        try:
            raw = java_oracle(output, args.java)
            java_distribution = check_distributions(raw["distributions"])
            write(output / "java-distributions.json", java_distribution)
            equal = topology == raw["topology"]
            report.update(java_status="PASSED" if java_distribution["passed"] else "FAILED",
                          topology_status="NORMAL_PARITY_PASSED" if equal else "FAILED",
                          topology_cases=len(topology),
                          topology_tasks=sum(len(t["tasks"]) for t in topology),
                          topology_edges=sum(len(task["children"]) for t in topology for task in t["tasks"]),
                          java_distributions_passed=java_distribution["passed"],
                          passed=py["passed"] and java_distribution["passed"] and equal)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            report.update(java_status="INFRASTRUCTURE_ERROR", error=f"{type(exc).__name__}: {exc}")
    write(output / "checks.json", report)
    print(json.dumps(report, indent=2))
    return 0 if (report["passed"] or (args.python_only and py["passed"])) else 1


if __name__ == "__main__":
    raise SystemExit(main())
