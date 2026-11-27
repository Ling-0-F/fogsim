"""Assemble the B08 regression, source-retention, and delivery gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_TEST_COMPATIBILITY_CHANGES = {
    "tests/gp/b06/conftest.py",
    "tests/stage_d/b07/conftest.py",
    "tools/build_release.py",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def junit_counts(path: Path) -> dict[str, int]:
    suites = list(ET.parse(path).getroot().iter("testsuite"))
    return {key: sum(int(suite.get(key, "0")) for suite in suites)
            for key in ("tests", "failures", "errors", "skipped")}


def audit(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    active = json.loads((ROOT / "development/b07/active-files.json").read_text())
    mismatches = []
    for row in active["files"]:
        path = ROOT / row["path"]
        actual = None if not path.is_file() else digest(path)
        if actual != row["sha256"]:
            mismatches.append({"path": row["path"], "expected": row["sha256"], "actual": actual})
    allowed = [row for row in mismatches if row["path"] in ALLOWED_TEST_COMPATIBILITY_CHANGES]
    unexpected = [row for row in mismatches if row["path"] not in ALLOWED_TEST_COMPATIBILITY_CHANGES]
    production_paths = [p for p in active["files"] if p["path"].startswith("src/fogsim/")]
    production_changed = [row for row in mismatches if row["path"].startswith("src/fogsim/")]

    tests = junit_counts(ROOT / "outputs/pytest-results.xml")
    dynamic = json.loads((ROOT / "outputs/final/current/dynamic/checks.json").read_text())
    performance = json.loads((ROOT / "outputs/final/performance/checks.json").read_text())
    contracts = json.loads((ROOT / "outputs/final/contracts-audit.json").read_text())
    validation = json.loads((ROOT / "outputs/validation-manifest.json").read_text())

    result = {
        "format": "fogsim.b08-source-audit",
        "schema_version": 1,
        "batch": "B08",
        "baseline": "B07-r1-20261107",
        "active_baseline_files": len(active["files"]),
        "active_baseline_files_checked": len(active["files"]),
        "baseline_mismatches": mismatches,
        "allowed_test_compatibility_changes": allowed,
        "unexpected_mismatches": unexpected,
        "production_simulator_source_changed": bool(production_changed),
        "production_source_files_checked": len(production_paths),
        "tests": tests,
        "regression_passed": tests == {"tests": 5797, "failures": 0, "errors": 0, "skipped": 0},
        "dynamic_gate_passed": bool(dynamic.get("passed")),
        "performance_gate_passed": bool(performance.get("passed")),
        "contract_audit_passed": not contracts.get("unresolved_contracts", contracts.get("unresolved", [])),
        "validation_snapshot_passed": bool(validation.get("acceptance_passed")),
        "all_matched": not unexpected and not production_changed,
        "passed": (not unexpected and not production_changed
                   and tests == {"tests": 5797, "failures": 0, "errors": 0, "skipped": 0}
                   and dynamic.get("passed") and performance.get("passed")
                   and not contracts.get("unresolved_contracts", contracts.get("unresolved", []))
                   and validation.get("acceptance_passed")),
        "scope": "B08 regression, contract audit, source retention, final dynamic/performance gates; B07 evidence remains immutable except test compatibility imports",
    }
    (output / "source-audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("passed", "all_matched", "tests", "baseline_mismatches", "production_simulator_source_changed")}))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/final")
    args = parser.parse_args()
    result = audit(args.output)
    raise SystemExit(0 if result["passed"] else 1)
