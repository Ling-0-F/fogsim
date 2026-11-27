"""Assemble final S01-S17 scope from explicit inherited and new evidence."""
from pathlib import Path
import argparse
import xml.etree.ElementTree as ET
from fogsim.training.protocols import read_json,write_json,source_provenance
from freeze_s9_b04 import files,ROOT
OUT=ROOT/'outputs/step9/B04'


def junit(path):
    suites=list(ET.parse(path).getroot().iter('testsuite'))
    return {k:sum(int(s.get(k,'0')) for s in suites) for k in ('tests','failures','errors','skipped')}|dict(seconds=sum(float(s.get('time','0')) for s in suites))


def main():
    unit=junit(OUT/'unit-final.xml');regression=junit(OUT/'regression.xml')
    assert all(x['tests']>0 and all(x[k]==0 for k in ('failures','errors','skipped')) for x in (unit,regression))
    frozen=read_json(OUT/'source-freeze.json');assert files()==frozen['files']
    source=read_json(OUT/'source-audit.json');assert source['passed']
    contracts=read_json(OUT/'contracts-audit.json');assert not contracts['unresolved']
    schema=read_json(OUT/'schema-audit.json');assert schema['passed']
    independent=read_json(OUT/'independent-selected-check.json');assert independent['passed'] and independent['completed_runs']==4
    no_deap=read_json(OUT/'no-deap.json');wheel=read_json(OUT/'wheel-check.json');assert no_deap['passed'] and wheel['passed']
    inherited={b:read_json(ROOT/f'outputs/step9/{b}/acceptance.json') for b in ('B01','B02','B03')}
    assert all(x['acceptance_passed'] for x in inherited.values())
    preflights={m:read_json(OUT/f'preflight-large-{m}/preflight.json') for m in ('single','dual')}
    assert all(x['status']=='PREFLIGHT_ONLY' and x['simulations_executed']==0 and x['closed_loop_budget']['total_upper_bound']==50510 for x in preflights.values())
    gate_specs={
        'S01':('configuration, plans, split, signed64 and seed rotation',['tests/training/test_b01.py'],['B01']),
        'S02':('DEAP/B08 ordered identities, Java grow, full, node roles and clone isolation',['tests/training/test_b02.py','tests/training/test_b03.py'],['B02','B03']),
        'S03':('D03 full-plan equal-run mean and denominators',['tests/training/test_b01.py'],['B01']),
        'S04':('domain continuation versus program/input/interruption failures',['tests/training/test_b01.py','tests/training/test_b02.py'],['B01','B02']),
        'S05':('NaN/infinity/signed-zero rule score and identity compatibility',['tests/training/test_b01.py','tests/training/test_b02.py','tests/training/test_b03.py'],['B01','B02','B03']),
        'S06':('fresh context/objects/queue/B order isolation',['tests/training/test_b01.py'],['B01']),
        'S07':('evolution versus simulator/caller RNG isolation',['tests/training/test_b01.py','tests/training/test_b02.py'],['B01','B02']),
        'S08':('plan rotation, elite/copy re-evaluation, actual counts, final-generation stop',['tests/training/test_b02.py','tests/training/test_b03.py'],['B02','B03']),
        'S09':('single routing/explicit FCFS real decisions, controlled operators and full closure',['tests/training/test_b02.py'],['B02']),
        'S10':('dual roles real decisions, four branches/tail/retries/source and clones',['tests/training/test_b03.py'],['B03']),
        'S11':('executed independent J01-J06 local Java cases and lifecycle; original evidence retained',[],['B01','B02','B03']),
        'S12':('dedup/all occurrences, fixed validation, pre-test freeze and no candidate switching',['tests/training/test_b02.py','tests/training/test_b03.py'],['B02','B03']),
        'S13':('single and dual two seeds plus complete same-config repeats; semantic comparison',[],['B02','B03']),
        'S14':('height/nodes/mutation/init/event/wallclock/EOF-exit evidence',['tests/training/test_b01.py','tests/training/test_b02.py','tests/training/test_b03.py','tests/training/test_b04.py'],['B01','B02','B03']),
        'S15':('CLI/API/protocols/source/lineage/independent freeze loading and output protection',['tests/training/test_b04.py'],['B01','B02','B03']),
        'S16':('final combined legacy/training regression, DEAP-free paths and pinned dependencies',['tests'],['B01','B02','B03']),
        'S17':('editable large templates preflight, budget/retention/versions, default validate entry and small explicit runs',['tests/training/test_b04.py'],[])}
    gates={k:dict(status='PASSED',scope=scope,current_tests=tests,inherited_batches=batches,
        current_evidence=['outputs/step9/B04/unit-final.xml','outputs/step9/B04/regression.xml'] if tests else [],
        inherited_evidence=[f'outputs/step9/{b}/acceptance.json' for b in batches]) for k,(scope,tests,batches) in gate_specs.items()}
    java={b:inherited[b].get('java_lifecycle',inherited[b].get('java_local')) for b in inherited}
    result=dict(format='fogsim.training-acceptance',schema_version=1,batch='S9-B04',version='0.4.0',design='S9-frozen-1',
        acceptance_passed=True,source=source_provenance(),source_freeze_id=frozen['source_freeze_id'],
        unit_tests=unit,combined_regression=regression,gates=gates,legacy_contract_count=len(contracts['contracts']),unresolved_contracts=contracts['unresolved'],
        source_retention=source,schema_audit=dict(checked=schema['checked'],references=schema['reference_count'],passed=True),
        inherited_java_evidence=java,inherited_closure_simulations={b:inherited[b]['closure_simulations'] for b in ('B02','B03')},
        historical_closure_budget_upper_bound=848,closure_reexecuted_in_B04=False,
        source_independent_evaluations=independent,wheel_independent_evaluations=wheel,
        large_templates=dict(executed_simulations=0,preflights=preflights),
        impact='Current-source preflight observations and evaluation EOF exit evidence only; unchanged training/simulator algorithms inherit accepted closure/Java semantics. Historical source IDs remain historical; not claimed as new current-source trials.',
        limitations=['No paper-scale training or paper-table/numerical reproduction.','No numeric ERC search, parallel speedup or arbitrary checkpoint resume.',
            'Java/Python native RNG streams may differ; controlled local alignment is not arbitrary-input equivalence.',
            'Two optional old large native fixed projections remain NOT_EXECUTED and are outside required minimum scope.',
            'JDK17 is an external environment requirement, not bundled. Offline dependency wheels target CPython3.12/Linux x86_64.',
            'Legacy JUnit case count is not an instrumented simulation total.'])
    write_json(OUT/'acceptance.json',result)
    print(__import__('json').dumps(dict(acceptance_passed=True,unit_tests=unit,combined_regression=regression,gates=len(gates))))
if __name__=='__main__':main()
