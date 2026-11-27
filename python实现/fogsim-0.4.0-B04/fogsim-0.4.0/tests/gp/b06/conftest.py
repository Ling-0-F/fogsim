"""Development acceptance tools are part of the cumulative source distribution."""
import json
import sys
from copy import deepcopy
from pathlib import Path
import pytest

from fogsim import parse_instance, create_engine, RunConfig
from fogsim.simulation.engine import EventContext

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'tools'))


@pytest.fixture
def raw():
    return json.loads((ROOT / 'data/cases/chain_remote.json').read_text())


@pytest.fixture
def spec(raw):
    return parse_instance(raw)


@pytest.fixture
def engine(spec):
    return create_engine(spec, RunConfig(routing_kind='fixed_resource', fixed_resource_id='E0'))


def step(engine):
    event = engine.event_queue.pop_next()
    engine.event_queue.consume_producer(event)
    assert event.time >= engine.state.clock_time
    engine.state.clock_time = event.time
    engine.processed_event_count += 1
    ctx = EventContext(engine, event.owner)
    event.trigger(ctx)
    engine.state.check_invariants()
    engine.event_queue.check_reservations(engine.state.resources_by_id.values())
    return event, ctx


def two_workflows(raw, release=0):
    data = deepcopy(raw)
    w = data['workflows'][0]
    w['tasks'] = w['tasks'][:1]
    w['dependencies'] = []
    other = deepcopy(w)
    other['id'] = 1
    other['release_time'] = release
    data['workflows'].append(other)
    return data
