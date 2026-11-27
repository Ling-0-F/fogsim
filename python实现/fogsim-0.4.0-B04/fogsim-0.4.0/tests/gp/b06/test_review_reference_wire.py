"""Reject malformed v2 Java wire scores before representation normalization."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from fogsim.errors import InputError
from fogsim.validation.gp_compare import validate_reference
from fogsim.validation.gp_normalize import java_dynamic

FIXTURE = Path(__file__).parent / 'fixtures/dynamic/reference.json'

def read():
    return json.loads(FIXTURE.read_text())

def score_paths(value, path=()):
    if type(value) is dict:
        if value.get('kind') == 'f64' and set(value) == {'kind', 'bits'}:
            yield path
        else:
            for key, item in value.items():
                yield from score_paths(item, path+(key,))
    elif type(value) is list:
        for index, item in enumerate(value):
            yield from score_paths(item, path+(index,))

PATHS = list(score_paths(read()['payload']))

def replace_score(reference, path, value):
    node = reference['payload']
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value

@pytest.mark.parametrize('path', PATHS)
def test_raw_java_reference_requires_tag_at_every_declared_score(path):
    reference = read()
    replace_score(reference, path, 0.0)
    with pytest.raises(InputError, match='GP_F64_ENCODING_INVALID'):
        validate_reference(reference)

@pytest.mark.parametrize('value', [0, -0.0, 1.5, None, False, '0000000000000000'])
def test_reference_normalizer_never_repairs_raw_score(value):
    reference = read()
    replace_score(reference, ('decisions', 0, 'selected', 'priority'), value)
    with pytest.raises(InputError, match='GP_F64_ENCODING_INVALID'):
        java_dynamic(reference)

@pytest.mark.parametrize('bits', ['0000000000000000', '8000000000000000',
    '7ff0000000000000', 'fff0000000000000', '7ff8000000000011', '7ff8000000000022'])
def test_valid_wire_score_preserves_all_bits_without_mutating_reference(bits):
    reference = read()
    path = ('decisions', 0, 'selected', 'priority')
    replace_score(reference, path, {'kind':'f64', 'bits':bits})
    before = deepcopy(reference)
    payload = java_dynamic(reference)
    assert payload['decisions'][0]['selected']['priority'] == {'kind':'f64', 'bits':bits}
    assert reference == before
