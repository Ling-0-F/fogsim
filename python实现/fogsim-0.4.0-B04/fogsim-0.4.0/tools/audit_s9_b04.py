"""Final source-retention and current protocol audit; never reruns historical trials."""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile
from importlib.metadata import version
from fogsim.training.protocols import read_json, write_json, source_provenance
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/step9/B04"
ALLOWED = {"README.md", "docs/SOURCE-DISTRIBUTION.md", "src/fogsim/training/cli.py",
    "src/fogsim/training/trainer.py", "src/fogsim/training/evaluation.py"}


def source_audit(baseline):
    changed = []; missing = []; checked = 0; historical = 0
    with zipfile.ZipFile(baseline) as archive:
        # Read B03's delivered content manifest; do not rerun its evidence or algorithms.
        manifest = json.loads(archive.read("fogsim-0.4.0/S9-B03-FILES.json"))["files"]
    for name, row in manifest.items():
        p = ROOT / name; checked += 1
        historical += name.startswith(("outputs/", "development/"))
        if not p.is_file(): missing.append(name); continue
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        if actual != row["sha256"]:
            changed.append(dict(path=name, before=row["sha256"], after=actual))
    unexpected = [row for row in changed if row["path"] not in ALLOWED]
    src = source_provenance()
    # B03 acceptance describes the exact previous simulator/training source.
    old = read_json(ROOT / "outputs/step9/B03/acceptance.json")["source"]["source_files"]
    source_delta = [k for k in sorted(old.keys() | src["source_files"].keys()) if old.get(k) != src["source_files"].get(k)]
    expected_delta = {"training/cli.py", "training/trainer.py", "training/evaluation.py", "training/preflight.py"}
    result = dict(passed=not missing and not unexpected and set(source_delta) == expected_delta,
        baseline="fogsim-0.4.0-B03.zip", files_checked=checked, historical_members_checked=historical,
        changed=changed, missing=missing, unexpected=unexpected, production_source_delta=source_delta,
        algorithms_unchanged=all(k.startswith("training/") and k in expected_delta for k in source_delta),
        scope="B04 cumulative byte-retention/impact audit; no historical result re-execution", source=src)
    write_json(OUT / "source-audit.json", result)
    return result


def schema_audit():
    import jsonschema
    formats = {"fogsim.training-preflight": "preflight", "fogsim.individual-evaluation": "evaluation",
        "fogsim.training-plan": "plan", "fogsim.evolution-result": "evolution-result",
        "fogsim.training-result": "training-result", "fogsim.selected-rule": "selected-rule",
        "fogsim.candidate-archive": "candidate-archive"}
    checked = []; references = []; errors = []
    names = {"preflight.json", "evaluation.json", "evolution-result.json", "training-result.json", "selected_rule.json", "archive.json", "plan.json"}
    for p in sorted(OUT.rglob("*.json")):
        if p.name not in names and "plans" not in p.parts: continue
        d = read_json(p); kind = formats.get(d.get("format")) if isinstance(d, dict) else None
        if not kind: continue
        rel = p.relative_to(ROOT).as_posix()
        try:
            jsonschema.validate(d, read_json(ROOT / f"schemas/training/{kind}.schema.json"))
            checked.append(rel)
            if kind == "evaluation":
                for row in d["runs"]:
                    for field in ("result_ref", "input_ref"):
                        if row[field]:
                            target = p.parent / row[field]
                            if not target.is_file(): raise ValueError("missing referenced file " + str(target))
                            references.append(target.relative_to(ROOT).as_posix())
        except Exception as exc:
            errors.append(dict(path=rel, error=str(exc)))
    result = dict(passed=bool(checked) and not errors, checked=len(checked), reference_count=len(references),
        files=checked, errors=errors, jsonschema_version=version("jsonschema"))
    write_json(OUT / "schema-audit.json", result)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument("action",choices=["source","schemas"])
    parser.add_argument("--baseline",type=Path);args=parser.parse_args()
    result=source_audit(args.baseline) if args.action=="source" else schema_audit()
    print(json.dumps({k:v for k,v in result.items() if k in ("passed","files_checked","checked","reference_count","changed","errors","missing","unexpected","production_source_delta")}))
    return 0 if result["passed"] else 1
if __name__=="__main__":raise SystemExit(main())
