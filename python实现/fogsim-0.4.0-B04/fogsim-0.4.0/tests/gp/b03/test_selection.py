from copy import copy
from dataclasses import replace
import math
import struct
import pytest

from fogsim.gp.diagnostics import GPStateError
from fogsim.gp import evaluator
from fogsim.rules.contexts import RoutingContext, SequencingContext, graph_fingerprint
from fogsim.rules.selection import choose_route, choose_next
from .helpers import prepared, pair


BIT_PATTERNS = ["0000000000000000", "8000000000000000", "3ff0000000000000", "bff0000000000000",
    "4000000000000000", "c000000000000000", "0000000000000001", "8000000000000001",
    "0010000000000000", "8010000000000000", "7fefffffffffffff", "ffefffffffffffff",
    "7ff0000000000000", "fff0000000000000", "7ff8000000000001", "7ff8000000000002"]


def number(bits): return struct.unpack(">d", bytes.fromhex(bits))[0]
def bits(value): return struct.pack(">d", value).hex()


def score_order(value):
    # Independent mathematical total-order oracle, rather than double_compare.
    if math.isnan(value): return (3, 0)
    if value < 0: return (0, value)
    if value == 0: return (1, int(math.copysign(1, value) > 0))
    return (2, value)


@pytest.mark.parametrize("role", ["routing", "sequencing"])
@pytest.mark.parametrize("a", BIT_PATTERNS)
@pytest.mark.parametrize("b", BIT_PATTERNS)
def test_gp_score_order_original_objects_and_priority_writes(role, a, b, evidence_b03):
    f, ctx = pair(role)
    first, second = ctx.candidates
    # Boundary-only score fixture; never run these durations as physical times.
    first.processing_time, second.processing_time = number(a), number(b)
    first.priority, second.priority = 101.0, 202.0
    rule = getattr(prepared("PT", "PT"), role)
    history = []
    class Recorder:
        def decision(self, context, scores, selected):
            history.append((scores, selected))
    chooser = choose_route if role == "routing" else choose_next
    selected = chooser(ctx, rule, Recorder())
    assert bits(first.priority) == a and bits(second.priority) == b
    expected = second if score_order(number(b)) < score_order(number(a)) else first
    assert selected is expected
    assert history[0][1] is selected
    assert [s["option"] for s in history[0][0]] == [list(o.key) for o in ctx.candidates]
    assert [bits(s["priority"]) for s in history[0][0]] == [a, b]
    evidence_b03("selection-matrix", dict(role=role, a=a,b=b,selected_index=int(selected is second),
        expected_index=int(expected is second), candidate_order=[o.key for o in ctx.candidates],passed=True))


@pytest.mark.parametrize("role", ["routing", "sequencing"])
def test_each_call_reads_then_selector_writes_in_original_order(role, monkeypatch, evidence_b03):
    f, ctx = pair(role); rule = getattr(prepared("PT", "PT"), role)
    for option, priority in zip(ctx.candidates, (101., 202.)): option.priority = priority
    reads = []
    original = evaluator.read_feature
    def observe(feature, option, context):
        reads.append(dict(key=option.key, priorities=[o.priority for o in ctx.candidates],
                          queue=[o.key for o in option.resource.waiting_queue]))
        return original(feature, option, context)
    monkeypatch.setattr(evaluator, "read_feature", observe)
    (choose_route if role == "routing" else choose_next)(ctx, rule)
    assert reads[0]["priorities"] == [101., 202.]
    assert reads[1]["priorities"] == [ctx.candidates[0].processing_time, 202.]
    assert [r["key"] for r in reads] == [o.key for o in ctx.candidates]
    if role == "sequencing":
        assert all(row["queue"] == [o.key for o in ctx.candidates] for row in reads)
    evidence_b03("priority-order", dict(role=role, reads=reads))


@pytest.mark.parametrize("key", ["release", "owner", "workflow", "stable"])
def test_exact_sequencing_tie_keys_no_task_or_resource_tie_key(key, evidence_b03):
    f, ctx = pair("sequencing"); first, second = ctx.candidates
    a, b = first.task.workflow, second.task.workflow
    if key == "release": a.release_time, b.release_time = 8., 5.
    elif key == "owner":
        # Canonical M1 is in the state view; numeric ID, not string ID, decides.
        a.owner_device = next(r for r in ctx.view.resources if r.id == "M1")
    elif key == "workflow": a.id, b.id = 20, 10
    else:
        a.tasks.remove(first.task); b.tasks.append(first.task); first.task.workflow = b
        first.task.id, second.task.id = "Z-last-lexically", "A-first-lexically"
    selected = choose_next(ctx, prepared(sequence="0").sequencing)
    assert selected is (first if key == "stable" else second)
    evidence_b03("tie-keys", dict(key=key,selected=selected.key,stable_first=key=="stable"))


@pytest.mark.parametrize("role", ["routing", "sequencing"])
@pytest.mark.parametrize("fault", ["outside_option", "foreign_option", "foreign_task", "foreign_resource",
    "foreign_workflow", "foreign_owner", "foreign_context", "completed", "dispatched"])
def test_real_entry_identity_and_phase_errors(role, fault, evidence_b03):
    f, ctx = pair(role); selected = ctx.candidates[0]
    if fault == "outside_option": selected = copy(selected)
    elif fault == "foreign_option":
        cloned = copy(selected); selected.task.options.remove(selected)
        selected.task.options.append(cloned)
    elif fault == "foreign_task": selected.task = copy(selected.task)
    elif fault == "foreign_resource": selected.resource = copy(selected.resource)
    elif fault == "foreign_workflow": selected.task.workflow = copy(selected.task.workflow)
    elif fault == "foreign_owner": selected.task.workflow.owner_device = copy(selected.task.workflow.owner_device)
    elif fault == "foreign_context":
        ctx = replace(ctx, **({"task":copy(ctx.task)} if role=="routing" else {"resource":copy(ctx.resource)}))
    elif fault == "completed": selected.task.completed = True
    else: selected.task.dispatched = role == "routing"
    expected = "GP_CONTEXT_PHASE_INVALID" if fault in ("completed","dispatched") else "GP_CONTEXT_IDENTITY_MISMATCH"
    before = graph_fingerprint(ctx)
    try:
        with pytest.raises(GPStateError) as caught:
            getattr(prepared(), role).priority(selected, ctx)
        assert caught.value.code == expected
    finally: assert graph_fingerprint(ctx) == before
    evidence_b03("context-errors", dict(role=role,fault=fault,code=caught.value.code,unchanged=True))


def test_no_longer_queued_is_phase_error():
    f, ctx = pair("sequencing"); option = ctx.candidates[0]
    option.resource.remove_waiting(option)
    with pytest.raises(GPStateError, match="GP_CONTEXT_PHASE_INVALID"):
        prepared().sequencing.priority(option, ctx)


def test_role_mismatch_and_single_candidate_still_evaluates(monkeypatch):
    f, ctx = pair("routing"); p = prepared()
    with pytest.raises(GPStateError, match="GP_RULE_ROLE_MISMATCH"):
        p.sequencing.priority(ctx.candidates[0], ctx)
    calls=[]; original=evaluator.read_feature
    def observe(*args): calls.append(args[1]); return original(*args)
    monkeypatch.setattr(evaluator,"read_feature",observe)
    one=replace(ctx,candidates=(ctx.candidates[0],))
    assert choose_route(one,p.routing) is one.candidates[0]
    assert calls == [one.candidates[0]]


def test_shared_server_reads_each_candidate_workflow_and_full_queue():
    f, ctx = pair("sequencing")
    f.other_workflow.release_time = 9.
    # The fixture has a finish record only on candidate two's workflow.
    rule=prepared(sequence="(+ TIS NTR)").sequencing
    scores=[rule.priority(o,ctx) for o in ctx.candidates]
    assert scores == [13., 18.]
    assert len(ctx.resource.waiting_queue)==2
    qrule=prepared(sequence="NIQ").sequencing
    assert [qrule.priority(o,ctx) for o in ctx.candidates] == [2.,2.]


@pytest.mark.parametrize("role",["routing","sequencing"])
def test_one_ulp_is_not_treated_as_a_tie(role):
    f,ctx=pair(role)
    ctx.candidates[0].processing_time=math.nextafter(1.,math.inf)
    ctx.candidates[1].processing_time=1.
    selected=(choose_route if role=="routing" else choose_next)(ctx,getattr(prepared("PT","PT"),role))
    assert selected is ctx.candidates[1]


def test_normal_return_mutation_is_detected_without_rollback(monkeypatch):
    f,ctx=pair("routing"); resource=ctx.candidates[0].resource
    original=evaluator.read_feature
    def mutate(*args): resource.available_time=999.; return original(*args)
    monkeypatch.setattr(evaluator,"read_feature",mutate)
    with pytest.raises(GPStateError,match="GP_STATE_MUTATION_DETECTED"):
        choose_route(ctx,prepared().routing)
    assert resource.available_time==999.
    assert ctx.candidates[0].priority==0.
