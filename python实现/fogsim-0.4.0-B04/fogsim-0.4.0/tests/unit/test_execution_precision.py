import pytest
from fogsim.errors import StateError
from fogsim.model.execution import Execution


@pytest.mark.parametrize("start,pt", [(1.0,1e-20),(1e9,1e-8),(float(2**53),1.0)])
def test_positive_input_can_lose_its_whole_execution_interval(engine, start, pt):
    option = engine.state.tasks_by_key[0,"A"].options[0]
    option.processing_time = pt
    assert start + pt == start
    with pytest.raises(StateError, match="duration lost to floating-point precision"):
        Execution(option, start)
    assert engine.state.executions_by_task == {}
    assert option.resource.pending_start is None


def test_representable_total_interval_is_retained(engine):
    option = engine.state.tasks_by_key[0,"A"].options[1]
    option.processing_time = 1e-20
    option.download_time = 1
    execution = Execution(option, 1)
    assert execution.compute_finish_time == 1 and execution.finish_time == 2
