"""Validate the test-only recorder against the complete production trace."""
from pathlib import Path
import sys
from conftest import ROOT
sys.path.insert(0,str(ROOT/'tools'))
from check_step5 import controlled_case
from dynamic_export_contract import read_json


def test_compact_oracle_keeps_every_compared_event_decision_and_action(tmp_path):
    case=ROOT/'outputs/step4/cases/multi_device_diamond'
    a=controlled_case(case,tmp_path/'full',compact=False)
    b=controlled_case(case,tmp_path/'compact',compact=True,trusted_fcfs=True)
    assert a['passed'] and b['passed']
    assert read_json(tmp_path/'full/python-normalized.json')==read_json(tmp_path/'compact/python-normalized.json')
    left=read_json(tmp_path/'full/python-result.json');right=read_json(tmp_path/'compact/python-result.json')
    assert left['workflow_records']==right['workflow_records'] and left['task_records']==right['task_records']
    assert left['diagnostics']==right['diagnostics'] and left['source_summary']==right['source_summary']
