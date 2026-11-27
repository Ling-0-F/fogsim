"""Compare all 14 current fixed-mode results with saved 0.2.1 evidence.

This runs Python only. It does not re-run Java or claim new cross-language parity.
"""
import json
import pytest
from conftest import ROOT
from fogsim import load_fixed_instance, simulate
from fogsim.config import load_config


CASES = [p.stem for p in sorted((ROOT / "configs").glob("*.json"))
         if p.stem != "v2_precision_collapse"]


@pytest.mark.parametrize("case", CASES)
def test_all_fixed_results_unchanged(case):
    path, config = load_config(ROOT / "configs" / f"{case}.json")
    actual = simulate(load_fixed_instance(path), config).to_dict()
    saved = json.loads((ROOT / "outputs" / "parity" / case / "python-raw.json").read_text())
    assert actual == saved["result"]  # exact result + events + decisions, no normalization
