"""Bind final executable source, tests, configs, protocols, adapters and locks."""
from pathlib import Path
import argparse
import hashlib
import json
from fogsim.training.protocols import write_json, identity
ROOT = Path(__file__).resolve().parents[1]


def files():
    paths = []
    for name in ("src", "tests", "tools", "configs", "schemas"):
        paths.extend(p for p in (ROOT / name).rglob("*") if p.is_file()
            and "__pycache__" not in p.parts and not any(x.endswith(".egg-info") for x in p.parts)
            and p.suffix not in (".pyc", ".class"))
    paths.extend(ROOT / name for name in ("pyproject.toml", "README.md", "docs/RUNNING-0.4.0.md",
        "docs/TRAINING-PROTOCOL-B04.md", "docs/SOURCE-DISTRIBUTION.md", "development/S9-B04/PLAN.md",
        "development/S9-B04/environment.json", "development/S9-B04/requirements-test.lock",
        "development/S9-B02/requirements-train.lock", "references/design/fogsim-0.4.0-design.md",
        "references/design/fogsim-stage-d-detailed-design.md"))
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["freeze", "verify"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    current = files()
    if args.action == "freeze":
        if args.output.exists(): raise ValueError("refuse to overwrite source freeze")
        result = dict(format="fogsim.source-freeze", schema_version=1, batch="S9-B04",
            files=current, source_freeze_id=identity("source-freeze", current))
        write_json(args.output, result)
        print(result["source_freeze_id"])
    else:
        expected = json.loads(args.output.read_text())["files"]
        differences = [k for k in sorted(expected.keys() | current.keys()) if expected.get(k) != current.get(k)]
        print(json.dumps(dict(passed=not differences, files=len(current), differences=differences)))
        if differences: raise SystemExit(1)
if __name__ == "__main__": main()
