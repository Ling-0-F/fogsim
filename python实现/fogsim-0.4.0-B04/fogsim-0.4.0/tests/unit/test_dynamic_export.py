"""V16 writer/audit contracts; the Java runtime gate is tools/check_step4.py."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from dynamic_export_contract import (read_json,audit_input,write_json,write_manifest,verify_manifest)
from export_java_dynamic import validate_request
from java_dynamic_support import EDITS, observation_overlay, ORIGINAL
from check_step3 import first_difference
from fogsim.errors import InputError


@pytest.fixture
def data():
    return read_json(ROOT/'tests/fixtures/dynamic_v1/input.json')


def test_input_is_self_contained_and_maps_retain_after_java_clear(data,tmp_path):
    write_json(tmp_path/'input.json',data)
    archive = audit_input(read_json(tmp_path/'input.json'))
    assert archive.candidates[0].workflow_input.tasks[0].id == 'Z'
    assert archive.candidates[0].workflow_input.edges[0].data_size > 0
    assert archive.candidates[1].workflow_input.release_time > 0
    assert not (tmp_path/'reference.json').exists()
    assert not (tmp_path/'dax').exists()


@pytest.mark.parametrize('version', [True,0,2,'1',None])
def test_unknown_version_is_rejected(data,version):
    data['schema_version'] = version
    with pytest.raises(InputError): audit_input(data)


@pytest.mark.parametrize('location', ['root','origin','rules','units','config','guards','samplers','capture','environment',
    'device','template','template_task','candidate','workflow','template_ref','task','option','edge','attempt','initial_state'])
def test_unknown_fields_rejected(data,location):
    w = data['candidates'][0]['workflow_input']
    target = {'root':data,'origin':data['origin'],'rules':data['origin']['rules'],'units':data['units'],
        'config':data['effective_config'],'guards':data['effective_config']['guards'],'samplers':data['effective_config']['samplers'],
        'capture':data['capture'],'environment':data['environment'],'device':data['environment']['devices'][0],
        'template':data['templates'][0],'template_task':data['templates'][0]['tasks'][0],
        'candidate':data['candidates'][0],'workflow':w,'template_ref':w['template_ref'],
        'task':w['tasks'][0],'option':w['tasks'][0]['options'][0],'edge':w['edges'][0],
        'attempt':data['generation_attempts'][0],'initial_state':data['initial_state']}[location]
    target['unexpected'] = 1
    with pytest.raises(InputError): audit_input(data)


@pytest.mark.parametrize('mutation', ['missing_edge','missing_task','missing_option','wrong_total','wrong_duration','bad_acceptance',
    'record_order','wrong_template_hash','wrong_candidate_id','missing_candidate','missing_attempt','extra_candidate',
    'bad_count','missing_initialization','wrong_release','wrong_owner','bad_fingerprint','incomplete','interrupted'])
def test_corrupt_records_fail(data,mutation):
    w = data['candidates'][0]['workflow_input']
    if mutation=='missing_edge': w['edges'].clear()
    elif mutation=='missing_task': w['tasks'].pop()
    elif mutation=='missing_option': w['tasks'][0]['options'].clear()
    elif mutation=='wrong_total': w['tasks'][0]['total_output_data'] += 1
    elif mutation=='wrong_duration': w['tasks'][0]['options'][0]['processing_time'] += 1
    elif mutation=='bad_acceptance': data['generation_attempts'][0]['observed_acceptance'] = False
    elif mutation=='record_order': data['generation_attempts'].reverse()
    elif mutation=='wrong_template_hash': w['template_ref']['source_sha256'] = 'a'*64
    elif mutation=='wrong_candidate_id': w['candidate_id'] = 1
    elif mutation=='missing_candidate': data['candidates'].pop()
    elif mutation=='missing_attempt': data['generation_attempts'].pop()
    elif mutation=='extra_candidate': data['candidates'].append(deepcopy(data['candidates'][0]))
    elif mutation=='bad_count': data['capture']['complete_attempt_count'] += 1
    elif mutation=='missing_initialization':
        data['generation_attempts'].clear(); data['candidates'].clear(); data['capture']['complete_attempt_count'] = 0
    elif mutation=='wrong_release': w['release_time'] += 1
    elif mutation=='wrong_owner': w['owner_device_id'] = 'M99'
    elif mutation=='bad_fingerprint': data['environment']['fingerprint'] = '0'*64
    elif mutation=='incomplete': data['capture']['complete'] = False
    elif mutation=='interrupted': data['capture']['write_interrupted'] = True
    with pytest.raises(InputError): audit_input(data)


@pytest.mark.parametrize('seed', [-(1<<63),(1<<63)-1,-1,0])
def test_exact_signed_seed(data,seed,tmp_path):
    data['initial_state']['public_seed'] = seed
    write_json(tmp_path/'input.json',data)
    loaded = read_json(tmp_path/'input.json')
    assert type(loaded['initial_state']['public_seed']) is int
    assert loaded['initial_state']['public_seed'] == seed
    audit_input(loaded)


@pytest.mark.parametrize('seed', [-(1<<63)-1,1<<63,True,1.0])
def test_bad_seed(data,seed):
    data['initial_state']['public_seed'] = seed
    with pytest.raises(InputError): audit_input(data)


@pytest.mark.parametrize('raw', ['{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}','{"x":-Infinity}','{"x":1e999}'])
def test_strict_json(tmp_path,raw):
    path = tmp_path/'bad.json'; path.write_text(raw)
    with pytest.raises(InputError): read_json(path)


def test_partial_capture_cannot_pass_full_gate(data):
    data['capture'].update(complete=False,process_interrupted=True)
    audit_input(data,require_complete=False)
    with pytest.raises(InputError,match='incomplete'): audit_input(data)


def test_input_audit_is_pure_and_duration_preserving(data):
    original = deepcopy(data); audit_input(data); assert data == original


def test_manifest_detects_modified_missing_and_extra_files(tmp_path):
    (tmp_path/'input.json').write_text('{}'); (tmp_path/'reference.json').write_text('{}')
    write_manifest(tmp_path,{'sources':{'x':'a'*64}}); verify_manifest(tmp_path)
    (tmp_path/'input.json').write_text('{"x":1}')
    with pytest.raises(InputError,match='hash'): verify_manifest(tmp_path)
    write_manifest(tmp_path,{})
    (tmp_path/'extra.txt').write_text('extra')
    with pytest.raises(InputError,match='coverage'): verify_manifest(tmp_path)
    (tmp_path/'extra.txt').unlink(); (tmp_path/'reference.json').unlink()
    with pytest.raises(InputError,match='coverage'): verify_manifest(tmp_path)


@pytest.mark.parametrize('relative',list(EDITS))
def test_overlay_adds_only_observation_calls(relative):
    source = (ORIGINAL/'src'/relative).read_text()
    overlay = observation_overlay(relative,source)
    for anchor,addition in EDITS[relative]: overlay = overlay.replace(addition,'',1)
    assert overlay == source
    with pytest.raises(RuntimeError): observation_overlay(relative,'')


def test_noninterference_comparator_detects_extra_sample_and_bit_change():
    original = {'samples':[{'role':'workload','value':1.0}],'rng':'state'}
    changed = deepcopy(original); changed['samples'].append({'role':'workload','value':1.0})
    assert first_difference(original,changed)['path'] == '$.samples'
    assert first_difference({'x':0.0},{'x':-0.0})['path'] == '$.x'


@pytest.mark.parametrize('change', [{'seed':1<<63},{'N':0},{'W':-1},{'devices':False},{'max_type':20},
    {'min_type':5,'max_type':4},{'local':False,'edges':0,'clouds':0},{'N':2**31-1,'W':1},{'unexpected':0}])
def test_export_request_fails_before_compilation(change):
    request = dict(seed=1,N=1,W=1,devices=1,edges=0,clouds=0,local=True,min_type=0,max_type=0)
    request.update(change)
    with pytest.raises(InputError): validate_request(request)
