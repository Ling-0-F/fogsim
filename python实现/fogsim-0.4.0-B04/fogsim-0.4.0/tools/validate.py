"""Reproduce acceptance results and an evidence manifest from the current snapshot."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from fogsim import load_fixed_instance, simulate, create_engine, __version__
from fogsim.config import load_config
from v2_cases import DEFAULT_CASES


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output=ROOT/"outputs";output.mkdir(exist_ok=True)
    (output/"validation-manifest.json").write_text(json.dumps({"status":"RUNNING","acceptance_passed":False})+"\n")
    (output/"pytest-results.xml").unlink(missing_ok=True)
    (output/"parity/summary.json").unlink(missing_ok=True)
    (output/"v2/summary.json").unlink(missing_ok=True)
    command=[sys.executable,"-m","pytest","-q","--junitxml=outputs/pytest-results.xml"]
    tests=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
    (output/"pytest-console.txt").write_text(tests.stdout+tests.stderr,encoding="utf-8")
    print(tests.stdout,end="")
    if not (output/"pytest-results.xml").is_file():
        (output/"validation-manifest.json").write_text(json.dumps({"status":"INFRASTRUCTURE_ERROR",
            "acceptance_passed":False,"pytest_command":command,"pytest_exit_code":tests.returncode,
            "reason":"pytest produced no XML; see pytest-console.txt"},indent=2)+"\n")
        return tests.returncode or 1
    suite=ET.parse(output/"pytest-results.xml").getroot().find("testsuite")
    summary={k:int(suite.get(k,"0")) for k in ("tests","failures","errors","skipped")}
    runs={};mappings={}
    for name in DEFAULT_CASES:
        path,cfg=load_config(ROOT/f"configs/{name}.json");spec=load_fixed_instance(path)
        result=simulate(spec,cfg).to_dict();runs[name]={k:result[k] for k in ("status","makespan","final_clock_time","processed_event_count")}
        (output/f"{name}.json").write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
        engine=create_engine(spec,cfg)
        mappings[name]={"resources":[[r.id,r.resource_type.value,r.numeric_id] for r in engine.state.resources_by_id.values()],
            "device_order":[r.id for r in engine.state.mobile_devices],
            "task_order":[list(k) for k in engine.state.tasks_by_key],
            "candidate_order":{str(t.key):[o.resource.id for o in t.options] for t in engine.state.tasks_by_key.values()},
            "initial_stage_order":[[w.id,w.owner_device.id,w.release_time] for w in engine.state.workflows_by_id.values()]}
    tracked=[ROOT/name for name in ("pyproject.toml","README.md","references/INPUT-SHA256.json","CHANGES-FROM-0.2.0a1.patch")]
    for folder in ("src","tests","configs","data/cases","tools","docs","references/design"):
        tracked.extend(p for p in (ROOT/folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts
                       and not any(part.endswith(".egg-info") for part in p.parts))
    files={str(p.relative_to(ROOT)).replace("\\","/"):sha(p) for p in sorted(tracked)}
    input_hashes={p.name:sha(p) for p in ROOT.parent.iterdir() if p.is_file() and p.suffix in (".zip",".pdf",".md",".txt")}
    parity_path=output/"parity/summary.json"
    parity=json.loads(parity_path.read_text(encoding="utf-8")) if parity_path.exists() else {"status":"NOT_EXECUTED","passed":False}
    v2_path=output/"v2/summary.json"
    v2=json.loads(v2_path.read_text(encoding="utf-8")) if v2_path.exists() else {"status":"NOT_EXECUTED","passed":False}
    acceptance_passed=(tests.returncode == 0 and all(summary[k] == 0 for k in ("failures","errors","skipped"))
                       and parity.get("passed",False) and v2.get("passed",False))
    manifest={"status":"COMPLETED","scope":"V01 fixed regression, 14 named cases, 96 sweeps, component oracle and precision boundary; extended V20/V21 evidence is separate",
        "implementation_version":__version__,"python":sys.version,"platform":platform.platform(),
        "python_executable":sys.executable,"pytest_version":importlib.metadata.version("pytest"),
        "pytest_command":command,"pytest_exit_code":tests.returncode,"tests":summary,
        "design_versions":"00-07 v1.1.0; 08-11 v1.0.0; incremental documents take precedence",
        "runs":runs,"order_mappings":mappings,"source_files":input_hashes,"project_hashes":files,
        "snapshot_sha256":hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest(),
        "fixed_parity":parity,"v2_acceptance":v2,"acceptance_passed":acceptance_passed,
        "input_sources":json.loads((ROOT/"references/INPUT-SHA256.json").read_text(encoding="utf-8")),
        "known_boundaries":["Zero-length binary64 execution intervals are explicitly rejected; original Java can overlap"],
        "not_executed":["Arbitrary-input equivalence","Full prior-stage Java dynamic export/sampler oracle reruns","GP/training/paper-scale experiments"]}
    (output/"validation-manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"tests":summary,"runs":runs},indent=2))
    return 0 if acceptance_passed else (tests.returncode or 1)


if __name__=="__main__":raise SystemExit(main())
