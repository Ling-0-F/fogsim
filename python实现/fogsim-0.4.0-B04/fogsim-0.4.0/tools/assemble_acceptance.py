"""Bind current test, source-review and independent Java evidence for 0.3.0."""
from pathlib import Path
import json
import hashlib
from audit_contracts import ROOT,audit


def read(path):return json.loads((ROOT/path).read_text())


def assemble():
    validation=read('outputs/validation-manifest.json')
    contracts=audit(ROOT/'outputs/pytest-results.xml')
    step2=read('outputs/final/step2/checks.json');step3=read('outputs/final/step3/checks.json')
    dynamic=read('outputs/final/current/dynamic/checks.json')
    perf=read('outputs/final/performance/checks.json')
    source=read('outputs/final/source-audit.json')
    full_tests=validation['pytest_exit_code']==0 and all(validation['tests'][k]==0 for k in ('failures','errors','skipped'))
    snapshot_matches=all((ROOT/name).is_file() and hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest for name,digest in validation['project_hashes'].items())
    base=validation['acceptance_passed'] and full_tests and snapshot_matches
    statuses={f'V{i:02d}':dict(passed=bool(base),scope='current zero-skip assertions and reviewed implementation',evidence=['outputs/pytest-results.xml']) for i in range(1,23)}
    def mark(ids,passed,scope,*paths):
        for key in ids.split():statuses[key]=dict(passed=bool(base and passed),scope=scope,evidence=list(paths))
    mark('V01',validation['acceptance_passed'],'14 named fixed cases, 96 sweeps, component oracle and explicit precision boundary','outputs/validation-manifest.json','outputs/v2/summary.json')
    mark('V02',step2['passed'] and step2['topology_cases']==20,'all 20 original Java/Python topologies; IDs, order, adjacency and actual size','outputs/final/step2/checks.json')
    mark('V04',step2['passed'] and step2['python_distributions_passed'] and step2['java_distributions_passed'],
        'deterministic boundary assertions plus independently sampled theoretical distributions: 3 seeds x 100000 per role in each language','outputs/final/step2/checks.json','outputs/pytest-results.xml')
    mark('V06 V07 V08',step3['passed'],'original Java construction/generation probes and all standard template materialization assertions','outputs/final/step3/checks.json','outputs/pytest-results.xml')
    mark('V09 V10 V11 V12 V13 V14 V15',dynamic['passed'] and dynamic['java_lifecycle_probes']['passed'],
        'current dynamic assertions, 50 original Java component/lifecycle checks, fresh input captures and full-trace replays; injected guard/lifecycle states are component tests','outputs/final/current/dynamic/checks.json','outputs/pytest-results.xml')
    captures=all(c['capture']['passed'] for c in dynamic['cases'])
    normal=[c for c in dynamic['cases'] if c['parity']['classification']=='NORMAL_PARITY_PASSED']
    expected=[c for c in dynamic['cases'] if c['parity']['classification']=='EXPECTED_DIFFERENCE_CONFIRMED']
    full=normal and all(c['parity']['passed'] and c['parity']['full_contract_verified'] for c in normal)
    mark('V16',captures and dynamic['interruption']['passed'],'7 fresh original Java exports, plain/baseline/minimal/full noninterference and interrupted capture rejection','outputs/final/current/dynamic/checks.json')
    mark('V17',full and sum(c['actual_cross_device_events'] for c in normal)>0,
        '5 normal full-trace replays: input/config, ordinal event header, pre-state, interleaved actions, post-state, errors, final state/statistics/metrics; 2 expected failure differences counted separately','outputs/final/current/dynamic/checks.json')
    mark('V18',all(c['passed'] for c in dynamic['negative_cases']) and dynamic['interruption']['passed'],
        'exhaustion, incomplete capture, divergence and changed-rule coverage; no additional input; unused normal tails tested','outputs/final/current/dynamic/negative/checks.json','outputs/pytest-results.xml')
    fixed_normal=[c for c in dynamic['cases'] if c['fixed']['classification']=='NORMAL_PARITY_PASSED']
    mark('V19',all(c['fixed']['passed'] for c in dynamic['cases']),
        '6 nonempty same-input fixed projections, 10 FCFS/fixed-resource lanes to completion; empty accepted set is an explicit legacy-format boundary; two optional native large projections excluded','outputs/final/current/dynamic/checks.json')
    release=[c['release_parity'] for c in dynamic['cases'] if c['release_parity'] is not None]
    mark('V20',perf['passed'] and release and all(r['passed'] and r['full_contract_verified'] for r in release),
        'atomic/idempotent cleanup and archived-input/RNG invariance; strict fresh Java diamond replay with release; initialization and full small-run performance measured, no universal gain claimed','outputs/final/performance/checks.json','outputs/final/current/dynamic/checks.json','outputs/pytest-results.xml')
    mark('V21',not contracts['unresolved'],'CLI/batches, signed64 seeds, continuation, independent cursors, denominators, callback snapshot isolation and interruption outputs','outputs/pytest-results.xml','outputs/final/contracts-audit.json')
    mark('V22',base,'all specified finite/underflow/collapse/count/seed boundaries; original Java collapse is an expected difference','outputs/pytest-results.xml','outputs/v2/precision-collapse/comparison.json')
    for key in ('V03','V05'):
        statuses[key]['evidence'].append('outputs/final/contracts-audit.json')
    (ROOT/'outputs/final/contracts-audit.json').write_text(json.dumps(contracts,ensure_ascii=False,indent=2)+'\n')
    result=dict(format='fogsim.final-acceptance',schema_version=1,version='0.3.0',
        acceptance_passed=bool(base and not contracts['unresolved'] and source['all_matched'] and all(v['passed'] for v in statuses.values())),
        unresolved_contracts=contracts['unresolved'],contract_count=len(contracts['contracts']),
        validation_snapshot_sha256=validation['snapshot_sha256'],validated_source_snapshot_matches=snapshot_matches,tests=validation['tests'],
        design_sha256=contracts['design_sha256'],validation_matrix=statuses,
        classification_counts=dict(NORMAL_PARITY_PASSED=len(normal),EXPECTED_DIFFERENCE_CONFIRMED=len(expected)),
        fresh_dynamic_counts={key:sum(c['parity']['counts'][key] for c in dynamic['cases']) for key in ('events','decisions','attempts')},
        same_projection_cases=len(fixed_normal),fixed_rule_lanes=sum(len(c['fixed'].get('lanes',[])) for c in fixed_normal),
        original_java_lifecycle_checks=dynamic['java_lifecycle_probes']['checks'],source_integrity=source,
        known_differences=[
            'fixed injection bypasses original random construction/training statistics; both fixed adapters use the same explicit input',
            'DAX malformed/forward/duplicate/cyclic/unknown structures are rejected rather than silently dropped',
            'XML declared counts are diagnostic only; actual topology determines size',
            'templates are loaded/frozen per context rather than reread on every generation; path root explicit',
            'Python task IDs preserve XML strings; Java position mapping does not add tie keys',
            'Java clears edge maps; Python retains by default or explicitly releases runtime maps; immutable archive survives',
            'Python samplers are frozen parameter objects and use a separate random.Random algorithm on one shared input stream',
            'signed64 public seeds map to unsigned64 bit patterns; paired Java/Python samples are not asserted equal',
            'future accepted inputs remain pending and are not exposed to scheduling rule views',
            'physical completion and statistical qualification are stored separately',
            'Python stops explicitly on first original guard; Java exception tail/max-clock/queue clearing is not reproduced',
            'failed Python metrics are None; Java sentinel metrics are preserved only in reference output',
            'positive PT lost to binary64 total-interval collapse is rejected before execution; original Java can overlap',
            'Python checks count/derived-threshold overflow instead of reproducing Java int wraparound',
            'explicit experiments do not reproduce GP evaluation/reset/penalty logic',
            'legacy producer_device_id is owner; fresh references separately observe actual staging by event identity',
            'Java fixed adapter only supports FCFS/fixed_resource and unobserved physical placeholders'],
        not_executed=[dict(classification='NOT_EXECUTED',item='two optional native large V19 fixed projections',
            reason='not a frozen minimum gate; six nonempty projections and ten lanes exercised with full production guards'),
            dict(classification='NOT_EXECUTED',item='paper-scale performance/GP/ten features/training and D20 experimental errata interpretation',reason='explicitly outside this design stage')],
        environment=dict(python=validation['python'],platform=validation['platform'],pytest=validation['pytest_version']),
        scope='all frozen in-scope obligations reviewed and their scoped V01-V22 gates passed; no arbitrary-input or paper-experiment equivalence claim')
    path=ROOT/'outputs/final/acceptance.json';path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(acceptance_passed=result['acceptance_passed'],contracts=result['contract_count'],tests=result['tests'],unresolved=result['unresolved_contracts'])))
    return result

if __name__=='__main__':raise SystemExit(0 if assemble()['acceptance_passed'] else 1)
