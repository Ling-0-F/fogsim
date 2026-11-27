from copy import deepcopy
from functools import lru_cache
import hashlib,json,os,sys
from pathlib import Path
import pytest
from fogsim import parse_instance, create_engine, RunConfig
from fogsim.simulation.engine import EventContext

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))

# Historical tests import ``conftest`` directly.  Export the cumulative
# helpers here as well because pytest loads this nested conftest under the
# same compatibility module name as the older suites.
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

@lru_cache(None)
def cached(path):return json.loads(Path(path).read_text())
def read(path):return deepcopy(cached(str(path)))

@pytest.fixture
def fixed_data():
    plan=read(ROOT/'development/b07/fixtures/fixed-plan-v2.json')
    def get(name):
        c=next(c for c in plan['cases'] if c['id']==name)
        return c,read(Path(os.environ.get('FOGSIM_B07_FIXED_RESULTS',str(ROOT/'development/b07/evidence/fixed-final')))/name/'python.json')
    return get

@pytest.fixture
def dynamic_data():
    plan=read(ROOT/'development/b07/fixtures/dynamic-plan-v3.json')
    def get(name='D09A-shared-fork-join'):
        folder=Path(os.environ.get('FOGSIM_B07_DYNAMIC_RESULTS',str(ROOT/'development/b07/evidence/dynamic-final')))/name
        return next(c for c in plan['cases'] if c['id']==name),read(folder/'python.json'),read(folder/'input.json'),folder
    return get

@pytest.fixture
def record(request,tmp_path):
    root=Path(os.environ.get('FOGSIM_B07_EVIDENCE',str(tmp_path)))
    root.mkdir(parents=True,exist_ok=True)
    def save(value):
        p=root/(hashlib.sha256(request.node.nodeid.encode()).hexdigest()+'.json')
        p.write_text(json.dumps(dict(test=request.node.nodeid,observation=value),indent=2,allow_nan=False)+'\n')
    return save
