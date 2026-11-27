from itertools import product
from types import SimpleNamespace as NS
import math
import pytest
from fogsim.errors import StateError
from fogsim.model.resource import ResourceType, MobileDevice
from fogsim.simulation.events import JobArrivalEvent, ProcessStartEvent, TaskVisitEvent, ProcessFinishEvent
from fogsim.simulation.event_queue import compare_event_java, JavaPriorityQueue, EventQueue


def event(kind, time=0.0, wid=0, device=0, local=True, server=0):
    owner=MobileDevice(f"M{device}",device,ResourceType.MOBILE)
    w=NS(id=wid,release_time=time,owner_device=owner)
    t=NS(workflow=w)
    r=owner if local else NS(resource_type=ResourceType.EDGE,numeric_id=server)
    o=NS(task=t,resource=r)
    ex=NS(task=t,resource=r,option=o,start_time=time,finish_time=time)
    return [lambda:JobArrivalEvent(w),lambda:ProcessStartEvent(ex),
            lambda:TaskVisitEvent(time,o),lambda:ProcessFinishEvent(ex)][kind]()


@pytest.mark.parametrize("a,b",list(product(range(4),repeat=2)))
def test_complete_same_time_matrix(a,b):
    matrix=[[-1,-1,-1,-1],[1,0,-1,-1],[1,1,0,-1],[1,1,1,1]]
    assert compare_event_java(event(a),event(b))==matrix[a][b]


def test_numeric_ties_and_exact_time():
    assert compare_event_java(event(0,wid=10),event(0,wid=2))==1
    assert compare_event_java(event(3,device=1),event(3,device=2))==-1
    assert compare_event_java(event(3,device=10),event(3,local=False,server=0))==-1
    assert compare_event_java(event(3,local=False,server=1),event(3,local=False,server=0))==1
    assert compare_event_java(event(3,time=1),event(0,time=math.nextafter(1,math.inf)))==-1
    assert compare_event_java(event(0,time=-0.0),event(0,time=0.0))==-1


def test_equal_heap_is_not_fifo():
    heap=JavaPriorityQueue(lambda a,b:0)
    for i in range(7):heap.offer(i)
    # OpenJDK replacement of root by last element, stopping on compare <= 0.
    assert [heap.poll() for _ in range(7)]==[0,6,5,4,3,2,1]
    assert heap.poll() is None


def test_staging_drain_and_each_event_recompetition(engine):
    w=engine.state.workflows_by_id[0];a,b=[t.options[1] for t in w.tasks]
    q=EventQueue(engine.state.mobile_devices);d=w.owner_device
    va,vb=TaskVisitEvent(2,a),TaskVisitEvent(2,b)
    q.stage(va,d);q.stage(vb,d)
    assert q.has_pending() and len(q.global_heap)==0 and len(q.staging_heaps[d])==2
    assert q.pop_next() is va
    from fogsim.model.execution import Execution
    start=ProcessStartEvent(Execution(a,2));q.stage(start,d)
    assert q.pop_next() is start and q.pop_next() is vb and q.pop_next() is None
    assert not q.has_pending()


def test_owner_and_staging_are_distinct(raw):
    from conftest import two_workflows
    from fogsim import create_engine,parse_instance
    from fogsim.simulation.engine import EventContext
    from fogsim.model.execution import Execution
    data=two_workflows(raw)
    data["resources"].append({"id":"M1","type":"MOBILE"})
    w=data["workflows"][1];w["owner_device_id"]="M1"
    w["tasks"][0]["execution_times"]["M1"]=w["tasks"][0]["execution_times"].pop("M0")
    e=create_engine(parse_instance(data));m0,m1=e.state.mobile_devices
    option=e.state.tasks_by_key[1,"A"].options[1]
    start=ProcessStartEvent(Execution(option,5))
    ctx=EventContext(e,m0);ctx.emit(start)
    assert start.owner is m1 and start in e.event_queue.staging_heaps[m0].snapshot()
    assert start not in e.event_queue.staging_heaps[m1].snapshot()
    assert ctx.emitted[-1]["staging_device"]=="M0" and ctx.emitted[-1]["owner"]=="M1"


@pytest.mark.parametrize("time",[math.nan,math.inf,-1])
def test_illegal_event_time(engine,time):
    option=engine.state.tasks_by_key[0,"A"].options[1]
    with pytest.raises(StateError):engine.event_queue.stage(TaskVisitEvent(time,option),engine.state.mobile_devices[0])


def test_emit_past_and_duplicate_event(engine):
    from fogsim.simulation.engine import EventContext
    s=engine.state;s.clock_time=2;option=s.tasks_by_key[0,"A"].options[1]
    ctx=EventContext(engine,s.mobile_devices[0])
    with pytest.raises(StateError,match="past"):ctx.emit(TaskVisitEvent(1,option))
    event=TaskVisitEvent(2,option);ctx.emit(event)
    with pytest.raises(StateError,match="already queued"):ctx.emit(event)
