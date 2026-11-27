from copy import deepcopy
from types import SimpleNamespace

import pytest

from fogsim import RunConfig, create_engine, parse_instance
from fogsim.gp.features import Feature, read_feature
from fogsim.model.execution import Execution
from fogsim.model.resource import ResourceType
from fogsim.rules.contexts import RoutingContext, StateView, graph_fingerprint
from fogsim.simulation.engine import EventContext
from conftest import step
from .feature_fixtures import describe, fixture, option
from .f64_oracle import bits


@pytest.mark.parametrize("resource_type", list(ResourceType))
@pytest.mark.parametrize("role", ["routing", "sequencing"])
def test_loaded_state_ten_features(resource_type, role, evidence):
    f = fixture(resource_type, role)
    assert f.option.resource is f.resource
    assert f.option.task.workflow is f.workflow
    assert [t.id for t in f.workflow.tasks] == ["A", "B", "C", "D"]
    assert [e.task.id for e in f.workflow.completed_executions] == ["D"]
    assert [o.task.id for o in f.resource.waiting_queue] == (["Q0", "Q1"] if role == "routing" else ["Q0", "A"])
    before = graph_fingerprint(f.context)
    want = [2., 5., 40., 1.5, .5, 4., 7., 15., 8., 3.] if role == "routing" else [2., 6., 40., 1.5, .5, 4., 8.75, 15., 8., 3.]
    try:
        actual = [read_feature(feature, f.option, f.context) for feature in Feature]
        assert list(map(bits, actual)) == list(map(bits, want))
        # Shared server candidates read their own workflow, not the triggering one.
        if role == "sequencing":
            q0 = f.queue[0]
            assert read_feature("TIS", q0, f.context) == 11.0
            assert read_feature("NTR", q0, f.context) == 2.0
        evidence("feature-states", dict(loaded=describe(f),
            queue_history=[dict(action="enqueue", key=o.key) for o in f.queue],
            features={name.value: bits(value) for name, value in zip(Feature, actual)},
            expected_bits=list(map(bits, want)), passed=True))
    finally:
        assert graph_fingerprint(f.context) == before


@pytest.mark.parametrize("resource_type", list(ResourceType))
@pytest.mark.parametrize("durations,expected_hex", [
    ((.1, .2), "3c80000000000000"), ((.5, .1), "bc80000000000000"),
])
def test_empty_cache_preserves_local_residual(resource_type, durations, expected_hex, evidence):
    f = fixture(resource_type, "routing")
    for queued in list(f.resource.waiting_queue):
        f.resource.remove_waiting(queued)
    # Use a clean, newly constructed resource so the history is exactly listed.
    r = type(f.resource)("new", 0, resource_type)
    history = []
    items = [option(f.other_workflow, r, f"R{i}", pt) for i, pt in enumerate(durations)]
    for item in items:
        item.task.dispatched = True
        r.enqueue(item)
        history.append(dict(action="enqueue", key=item.key, pt=bits(item.processing_time)))
    for item in items:
        r.remove_waiting(item)
        history.append(dict(action="remove", key=item.key))
    candidate = option(f.workflow, r, "probe", 1)
    want = expected_hex if resource_type == ResourceType.MOBILE else "0000000000000000"
    assert bits(read_feature("NIQ", candidate, f.context)) == "0000000000000000"
    assert bits(read_feature("WIQ", candidate, f.context)) == want
    assert bits(read_feature("TTIQ", candidate, f.context)) == want
    evidence("cache-history", dict(resource_type=resource_type.value, history=history,
        wiq_bits=bits(read_feature("WIQ", candidate, f.context)),
        ttiq_bits=bits(read_feature("TTIQ", candidate, f.context)), expected_bits=want, passed=True))


@pytest.mark.parametrize("resource_type", list(ResourceType))
def test_nonempty_negative_cache_no_clamping_or_print(resource_type, capsys, evidence):
    f = fixture(resource_type, "routing")
    r = type(f.resource)("negative", 0, resource_type)
    items = [option(f.workflow, r, f"N{i}", pt) for i, pt in enumerate((.5, .1, 1e-20))]
    for item in items:
        item.task.dispatched = True
        r.enqueue(item)
    r.remove_waiting(items[0]); r.remove_waiting(items[1])
    assert r.waiting_queue == [items[2]]
    assert r.queued_processing_time < 0 and r.queued_total_time < 0
    assert read_feature("WIQ", items[2], f.context) == r.queued_processing_time
    assert read_feature("TTIQ", items[2], f.context) == r.queued_total_time
    assert capsys.readouterr() == ("", "")
    evidence("negative-cache", dict(resource_type=resource_type.value,
        enqueued_pt_bits=[bits(o.processing_time) for o in items], removed_indices=[0, 1],
        queue=[o.key for o in r.waiting_queue], wiq_bits=bits(r.queued_processing_time),
        ttiq_bits=bits(r.queued_total_time), passed=True))


def test_cache_parentheses_and_exclusion():
    f = fixture(ResourceType.EDGE, "routing")
    r = type(f.resource)("group", 0, ResourceType.EDGE)
    big = option(f.workflow, r, "big", 1e16, 1, 1)
    big.task.dispatched = True
    r.enqueue(big)
    assert bits(read_feature("TTIQ", big, f.context)) == bits(1e16)
    assert bits(1e16 + (1.0 + 1.0)) != bits(r.waiting_total_time)
    r.remove_waiting(big)
    r.pending_start = Execution(big, 0.0)
    assert read_feature("NIQ", big, f.context) == 0.0
    assert read_feature("TTIQ", big, f.context) == 0.0
    # A reservation neither creates queue work nor changes raw MRT.
    assert read_feature("MRT", big, f.context) == 0.0


def test_negative_times_completed_records_and_no_feature_cache():
    f = fixture(ResourceType.MOBILE, "routing")
    context = RoutingContext(f.option.task, (f.option,), StateView(1.0, (f.resource,), (f.workflow,), ()))
    assert read_feature("TIS", f.option, context) == -4.0
    assert read_feature("TWT", f.option, context) == -11.0
    # Remaining count is based on completion records, irrespective of task flags.
    f.workflow.tasks[1].completed = True
    assert read_feature("NTR", f.option, context) == 3.0
    f.resource.available_time = 13.0
    f.option.processing_time = 9.0
    assert read_feature("MRT", f.option, context) == 13.0
    assert read_feature("PT", f.option, context) == 9.0
    assert read_feature("MRT", f.option, f.context) == 13.0


def test_stored_durations_and_signed_zero_are_not_recomputed():
    f = fixture(ResourceType.CLOUD, "routing")
    f.resource.processing_rate = 12345.0
    f.resource.upload_bandwidth = 9000.0
    f.resource.download_bandwidth = 8000.0
    f.option.task.workload = 99999.0
    f.option.upload_time = f.option.download_time = -0.0
    assert bits(read_feature("UT", f.option, f.context)) == "8000000000000000"
    assert bits(read_feature("DT", f.option, f.context)) == "8000000000000000"
    assert read_feature("PT", f.option, f.context) == 4.0


def test_ntr_integer_subtraction_before_conversion():
    # Synthetic accessor boundary only: allocating >2**53 real tasks is infeasible.
    workflow = SimpleNamespace(task_count=2**53 + 1, completed_task_count=2**53)
    candidate = SimpleNamespace(task=SimpleNamespace(workflow=workflow))
    assert read_feature("NTR", candidate, None) == 1.0
    assert float(workflow.task_count) - float(workflow.completed_task_count) == 0.0
    workflow.completed_task_count = 2**53 + 2
    assert read_feature("NTR", candidate, None) == -1.0


def test_alphabet_and_error_path_is_readonly():
    assert tuple(x.value for x in Feature) == ("NIQ", "WIQ", "MRT", "UT", "DT", "PT", "TTIQ", "TIS", "TWT", "NTR")
    f = fixture(ResourceType.CLOUD, "routing")
    before = graph_fingerprint(f.context)
    try:
        for invalid in ("t", "W", "RT", "NTJ", "WR", "pt", "NIQ "):
            with pytest.raises(ValueError):
                read_feature(invalid, f.option, f.context)
    finally:
        assert graph_fingerprint(f.context) == before


def test_real_event_timing_with_baseline_rules(raw, monkeypatch, evidence):
    data = deepcopy(raw)
    other = deepcopy(data["workflows"][0]); other["id"] = 1
    other["tasks"] = other["tasks"][:1]; other["dependencies"] = []
    data["workflows"].append(other)
    engine = create_engine(parse_instance(data), RunConfig(routing_kind="fixed_resource", fixed_resource_id="E0"))
    observed = []

    def capture(ctx, candidate, kind, round_number):
        f = {feature.value: bits(read_feature(feature, candidate, ctx)) for feature in Feature}
        observed.append(dict(time=ctx.view.clock_time, kind=kind, round=round_number,
            key=candidate.key, features=f, pending=candidate.resource.pending_start is not None,
            queue=[o.key for o in candidate.resource.waiting_queue]))

    route, sequence = EventContext.choose_route, EventContext.choose_next

    def observe_route(self, task, round_number=1):
        ctx = RoutingContext(task, tuple(task.options), self.view(), round_number)
        for candidate in task.options:
            capture(ctx, candidate, "routing", round_number)
        return route(self, task, round_number)

    def observe_sequence(self, resource):
        from fogsim.rules.contexts import SequencingContext
        ctx = SequencingContext(resource, tuple(resource.waiting_queue), self.view())
        for candidate in resource.waiting_queue:
            capture(ctx, candidate, "sequencing", 1)
        return sequence(self, resource)

    monkeypatch.setattr(EventContext, "choose_route", observe_route)
    monkeypatch.setattr(EventContext, "choose_next", observe_sequence)
    step(engine); step(engine)  # root routing and upload, not queued
    a = engine.state.tasks_by_key[0, "A"].options[1]
    assert a.ready_time == 0.0
    step(engine)  # Visit changes only dispatched option, reservation precedes Start
    assert a.ready_time == 2.0
    assert all(o.ready_time == 0.0 for o in a.task.options if o is not a)
    ctx = RoutingContext(a.task, tuple(a.task.options), StateView.from_state(engine.state))
    assert read_feature("MRT", a, ctx) == 0.0 and read_feature("NIQ", a, ctx) == 0.0
    step(engine)  # actual Start
    assert read_feature("MRT", a, ctx) == 6.0
    step(engine); step(engine)  # second Visit, then first Finish
    selected = [row for row in observed if row["time"] == 6.0]
    assert [(row["kind"], row["round"]) for row in selected] == [("sequencing", 1)] + [("routing", 1)]*3 + [("routing", 2)]*3
    assert selected[0]["queue"] == [(1, "A", "E0")]
    assert selected[0]["features"]["NTR"] == bits(1.0)
    for row in selected[1:]:
        assert row["features"]["TWT"] == bits(6.0)
        assert row["features"]["NTR"] == bits(1.0)
        if row["key"][-1] == "E0":
            assert row["features"]["MRT"] == bits(6.0) and row["queue"] == [] and row["pending"]
    for row in observed:
        evidence("event-feature-observations", row)
