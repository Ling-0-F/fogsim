from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import pytest
from fogsim import create_dynamic_context
from fogsim.cli import main
from fogsim.errors import InputError
from fogsim.experiment_config import parse_experiment_config, RuleConfig
from fogsim.rules.factory import prepare_rules
from fogsim.rules.specs import RuleSpec
from fogsim.serialization.result import read_result
from ..b03.helpers import dynamic_config, gp_dynamic
from conftest import ROOT

@pytest.mark.parametrize('route',['fcfs','fixed_resource','gp'])
@pytest.mark.parametrize('sequence',['fcfs','gp'])
def test_v2_json_six_combinations(tmp_path,route,sequence):
    cfg=replace(dynamic_config(tmp_path,edges=1),schema_version=2)
    data=cfg.to_dict()
    data['run']['routing_rule']={'kind':route}
    if route=='gp':data['run']['routing_rule']['expression']='(+ PT 1)'
    if route=='fixed_resource':data['run']['routing_rule']['resource_id']='E0'
    data['run']['sequencing_rule']={'kind':sequence}
    if sequence=='gp':data['run']['sequencing_rule']['expression']='TWT'
    loaded=parse_experiment_config(data)
    assert loaded.schema_version==2 and loaded.to_dict()==data
    assert create_dynamic_context(loaded).run().to_dict()['schema_version']==2

@pytest.mark.parametrize('version',[0,3,True,2.0,'2',None])
def test_unknown_schema_rejected(tmp_path,version):
    data=dynamic_config(tmp_path).to_dict();data['schema_version']=version
    with pytest.raises(InputError):parse_experiment_config(data)

@pytest.mark.parametrize('role',['routing','sequencing'])
@pytest.mark.parametrize('rule',[dict(kind='gp'),dict(kind='gp',expression=''),dict(kind='gp',expression='  '),
    dict(kind='gp',expression='PT',resource_id=None),dict(kind='fcfs',expression=None),
    dict(kind='fcfs',extra=0),dict(kind='gp',expression='PT',extra=0)])
def test_v2_rules_exact_fields(tmp_path,role,rule):
    data=replace(dynamic_config(tmp_path),schema_version=2).to_dict();data['run'][role+'_rule']=rule
    with pytest.raises(InputError):parse_experiment_config(data)


def test_identity_encoding_error_happens_before_input_rng(tmp_path,monkeypatch):
    import fogsim.simulation.context as module
    cfg=dynamic_config(tmp_path,edges=1)
    # Also exercise the common preparation entry independently of eligibility.
    calls=[]
    def forbidden(*a,**kw):calls.append(True);raise AssertionError('RNG creation')
    monkeypatch.setattr(module,'prepare_random_input',forbidden)
    with pytest.raises(InputError,match='GP_RULE_IDENTITY_MISMATCH'):
        prepare_rules(RuleSpec('routing','fixed_resource','\ud800'),RuleSpec('sequencing'))
    assert not calls


@pytest.mark.parametrize('trace',[True,False])
def test_fixed_cli_override_clears_entire_route_preserves_sequence(tmp_path,trace):
    cfg=dict(instance=str(ROOT/'data/cases/chain_remote.json'),
        routing_rule=dict(kind='gp',expression='PT'),sequencing_rule=dict(kind='gp',expression='-0.0'))
    path=tmp_path/'fixed.json';path.write_text(json.dumps(cfg));out=tmp_path/'out.json'
    args=['--config',str(path),'--fixed-resource','E0','--output',str(out)]
    if not trace:args+=['--no-trace']
    assert main(args)==0
    result=read_result(out);bindings=result['rule_manifest']['bindings']
    assert bindings['routing']['kind']=='fixed_resource' and 'source' not in bindings['routing']
    assert bindings['sequencing']['source']['expression']=='-0.0'
    assert bool(result['events'])==trace


@pytest.mark.parametrize('trace',[True,False])
def test_dynamic_cli_v2_single_run(tmp_path,trace):
    cfg=gp_dynamic(tmp_path,edges=1)
    path=tmp_path/'dynamic.json';path.write_text(json.dumps(cfg.to_dict()))
    out=tmp_path/'out.json'
    args=['dynamic','--config',str(path),'--output',str(out),'--fixed-resource','E0']
    if not trace:args+=['--no-trace']
    assert main(args)==0
    result=read_result(out)
    assert result['format']=='fogsim.dynamic-result' and result['status']=='SUCCEEDED'
    assert result['rule_manifest']['bindings']['sequencing']['kind']=='gp'
    assert result['rule_manifest']['bindings']['routing']['kind']=='fixed_resource'
    assert bool(result['events'])==trace


@pytest.mark.parametrize('mode',['repeat','archive'])
def test_b05_entries_capture_and_repeat_v2(tmp_path,mode):
    cfg=gp_dynamic(tmp_path);path=tmp_path/'dynamic.json';path.write_text(json.dumps(cfg.to_dict()))
    out=tmp_path/'out.json';archive=tmp_path/'archive'
    args=['dynamic','--config',str(path),'--output',str(out)]
    args+=['--repeat','2','--repeat-mode','fresh_same_seed'] if mode=='repeat' else ['--archive-dir',str(archive)]
    assert main(args)==0
    result=json.loads(out.read_text());assert result['schema_version']==2 and result['status']=='SUCCEEDED'
    assert len(result['runs'])==(2 if mode=='repeat' else 1)
    if mode=='archive':
        from fogsim.replay import load_replay_input
        assert load_replay_input(archive/'run-000000.input.json').schema_version==2


def test_cli_bad_rule_and_domain_failure_exit_codes(tmp_path):
    cfg=dict(instance=str(ROOT/'data/cases/chain_remote.json'),routing_rule=dict(kind='gp',expression='(+ PT)'),sequencing_rule=dict(kind='fcfs'))
    path=tmp_path/'bad.json';out=tmp_path/'out.json';path.write_text(json.dumps(cfg))
    with pytest.raises(SystemExit) as caught:main(['--config',str(path),'--output',str(out)])
    assert caught.value.code==2 and not out.exists()
    cfg['routing_rule']['expression']='PT';cfg['max_events']=1;path.write_text(json.dumps(cfg))
    assert main(['--config',str(path),'--output',str(out)])==1
    assert read_result(out)['status']=='FAILED'
