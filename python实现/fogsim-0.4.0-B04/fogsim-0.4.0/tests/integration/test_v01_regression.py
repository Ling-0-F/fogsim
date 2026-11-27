"""The new instrumentation must preserve the stored 0.1 execution results."""
from copy import deepcopy
import json
import pytest
from fogsim import simulate,load_fixed_instance
from fogsim.config import load_config
from conftest import ROOT


@pytest.mark.parametrize("case",["single_local","single_local_release5","chain_remote","chain_fcfs"])
def test_v01_behavior_unchanged(case):
    path,config=load_config(ROOT/f"configs/{case}.json")
    current=simulate(load_fixed_instance(path),config).to_dict()
    baseline=json.loads((ROOT/f"outputs/v0.1/{case}.json").read_text(encoding="utf-8"))
    current=deepcopy(current)
    for event in current["events"]:event.pop("actions")
    for decision in current["decisions"]:
        for field in ("event_sequence","decision_sequence","candidate_state"):decision.pop(field)
    assert current == baseline
