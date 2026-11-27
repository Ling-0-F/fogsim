from dataclasses import replace
from pathlib import Path
import random
import pytest
from conftest import ROOT
from test_environment_build import trace_roles
from fogsim import (load_experiment_config, prepare_random_input, sample_environment, build_environment,
                    generate_workflow_input, materialize_workflow, release_rejection_reason)
from fogsim.errors import InputError, NumericDerivationError
from fogsim.experiment_config import EnvironmentConfig, WorkflowTypeRange, SamplerParameters, RealRange
from fogsim.environment.spec import DeviceSnapshot, ServerSnapshot, EnvironmentSnapshot
from fogsim.instances.catalog import DagCatalog
from fogsim.instances.templates import DagTemplate, DagTaskSpec
from fogsim.instances.generated import (GenerationCause, GenerationAttempt, CandidateRecord, AdmissionMapping, InputArchive)
from fogsim.randomness.state import RandomInputState
from fogsim.randomness.samplers import make_samplers


def template(ids=("Z", "A", "join"), dependencies=(("A", "join"), ("Z", "join"))):
    return DagTemplate(0, "scripted.xml", "a" * 64,
        tuple(DagTaskSpec(tid, index) for index, tid in enumerate(ids)), dependencies)


def inputs_for(t=None, *, seed=7, parameters=None, rng=None):
    t = t or template()
    types = WorkflowTypeRange(0, 0)
    return RandomInputState(seed, DagCatalog(ROOT / "dax", types, (t,)),
                            make_samplers(parameters or SamplerParameters(), types), rng or random.Random(seed))


def environment(local=True):
    return EnvironmentSnapshot((DeviceSnapshot("phone-X", 0, 100, local), DeviceSnapshot("phone-Y", 1, 125, local)),
        (ServerSnapshot("edge-X", 0, "EDGE", 200, 100, 50), ServerSnapshot("cloud-X", 1, "CLOUD", 400, 200, 100)), "scripted")


def test_two_pass_sample_order_formulas_and_edge_identity(monkeypatch):
    inputs = inputs_for()
    calls = trace_roles(monkeypatch, inputs, {"workflow_type": [0], "inter_release_time": [2], "weight": [4],
        "workload": [1000, 2000, 3000], "data_size": [10, 20, 30], "edge_data": [100, 150]})
    env = environment()
    cause = GenerationCause("initialize", "phone-X", 0)
    candidate = generate_workflow_input(inputs, env, cause, candidate_id=0)
    assert calls == ["workflow_type", "inter_release_time", "weight",
                     "workload", "data_size", "edge_data", "workload", "data_size", "edge_data", "workload", "data_size"]
    assert candidate.release_time == candidate.inter_release_time == 2 and candidate.weight == 4
    assert [(e.parent_id, e.child_id, e.data_size) for e in candidate.edges] == [("Z", "join", 100), ("A", "join", 150)]
    assert [(t.total_input_data, t.total_output_data) for t in candidate.tasks] == [(0, 100), (0, 150), (250, 0)]
    assert [[o.resource_id for o in t.options] for t in candidate.tasks] == [["phone-X", "edge-X", "cloud-X"]] * 3
    local, edge, cloud = candidate.tasks[0].options
    assert (local.processing_time, local.upload_time, local.download_time) == (10, 0, 0)
    assert (edge.processing_time, edge.upload_time, edge.download_time) == (5, .1, 2.2)
    assert (cloud.processing_time, cloud.upload_time, cloud.download_time) == (2.5, .05, 1.1)
    join = candidate.tasks[2].options[1]
    assert (join.processing_time, join.upload_time, join.download_time) == (15, 2.8, .6)
    assert release_rejection_reason(candidate, cause) is None


def test_input_accumulates_in_parent_order_output_in_children_order(monkeypatch):
    t = template(("p0", "p1", "p2", "J", "X", "Y"),
                 (("p2", "J"), ("p1", "J"), ("p0", "J"), ("p0", "X"), ("p0", "Y"), ("J", "X")))
    inputs = inputs_for(t, parameters=SamplerParameters(edge_data=RealRange(0, 2e16)))
    trace_roles(monkeypatch, inputs, {"edge_data": [1e16, 1, 1, 1, 1, 5]})
    c = generate_workflow_input(inputs, environment(), GenerationCause("initialize", "phone-X", 0), candidate_id=0)
    assert c.tasks[0].total_output_data == 1e16  # sequential +1,+1 are lost
    assert c.tasks[3].total_input_data == 10000000000000002.0  # +1,+1 before +1e16
    assert c.tasks[4].total_input_data == 6
    assert [(e.parent_id, e.child_id) for e in c.edges] != list(t.dependencies)


@pytest.mark.parametrize("local,servers", [(True, True), (False, True), (True, False)])
def test_candidate_eligibility_and_no_base_data_in_totals(local, servers):
    inputs = inputs_for(template(("single",), ()))
    env = environment(local)
    if not servers: env = replace(env, servers=())
    c = generate_workflow_input(inputs, env, GenerationCause("initialize", "phone-X", 0), candidate_id=0)
    task = c.tasks[0]
    assert task.total_input_data == task.total_output_data == 0
    expected = (["phone-X"] if local else []) + (["edge-X", "cloud-X"] if servers else [])
    assert [o.resource_id for o in task.options] == expected
    for option in task.options:
        if option.resource_id != "phone-X":
            assert option.upload_time > 0 and option.download_time > 0


def test_release_zero_consumes_full_generation_and_does_not_touch_state():
    class FirstRealZero(random.Random):
        def __init__(self, seed): super().__init__(seed); self.real_calls = 0
        def getrandbits(self, k): return super().getrandbits(k)
        def random(self):
            value = super().random(); self.real_calls += 1
            return 0.0 if self.real_calls == 1 else value
    inputs = inputs_for(rng=FirstRealZero(7)); control = inputs_for()
    env = environment(); state = build_environment(env)
    before = inputs.snapshot()
    cause = GenerationCause("initialize", "phone-X", 0)
    c = generate_workflow_input(inputs, env, cause, candidate_id=0)
    ordinary = generate_workflow_input(control, env, cause, candidate_id=0)
    assert c.inter_release_time == c.release_time == 0
    assert release_rejection_reason(c, cause) == "REJECTED_RELEASE_NOT_FUTURE"
    assert c.tasks == ordinary.tasks and c.edges == ordinary.edges
    assert inputs.snapshot() != before and inputs.rng.getstate() == control.rng.getstate()
    assert not state.workflows_by_id and not state.tasks_by_key and state.clock_time == 0
    # Complete rejected input can be archived without consuming a formal ID.
    a = InputArchive((template(),), env, (CandidateRecord("1", c),),
        (GenerationAttempt(1, cause, "1", False, "REJECTED_RELEASE_NOT_FUTURE"),), ())
    assert a.workflow_input("1") is c and not a.admissions


def test_release_rounding_rejection_retains_original_delta(monkeypatch):
    inputs = inputs_for()
    calls = trace_roles(monkeypatch, inputs, {"inter_release_time": [1]})
    cause = GenerationCause("after_arrival", "phone-X", float(1 << 53), 0, 1)
    c = generate_workflow_input(inputs, environment(), cause, candidate_id=3)
    assert c.inter_release_time == 1 and c.release_time == cause.clock_time
    assert release_rejection_reason(c, cause) == "REJECTED_RELEASE_NOT_FUTURE"
    assert calls[-1] == "data_size" and calls.count("edge_data") == 2


def test_invalid_owner_and_id_do_not_draw():
    inputs = inputs_for(); before = inputs.snapshot()
    for cause, cid in ((GenerationCause("initialize", "missing", 0), 0),
                       (GenerationCause("initialize", "phone-X", 0), True)):
        with pytest.raises(InputError): generate_workflow_input(inputs, environment(), cause, candidate_id=cid)
    assert inputs.snapshot() == before


@pytest.mark.parametrize("defect", ["release_overflow", "workload_zero", "data_negative", "edge_nan",
    "output_total_overflow", "input_total_overflow", "combined_upload_overflow", "combined_download_overflow",
    "pt_underflow", "pt_overflow", "ut_overflow", "dt_overflow"])
def test_numerical_failures_are_not_ordinary_rejections(defect, monkeypatch):
    t = template(("a", "b", "c"), (("a", "b"), ("a", "c")))
    env = environment(); cause = GenerationCause("initialize", "phone-X", 0)
    script = {}
    if defect == "release_overflow":
        cause = GenerationCause("after_arrival", "phone-X", 1e308, 0, 1); script["inter_release_time"] = [1e308]
    elif defect == "workload_zero": script["workload"] = [0]
    elif defect == "data_negative": script["data_size"] = [-1]
    elif defect == "edge_nan": script["edge_data"] = [float("nan")]
    elif defect == "output_total_overflow": script["edge_data"] = [1e308, 1e308]
    elif defect == "input_total_overflow":
        t = template(("a", "b", "c"), (("a", "c"), ("b", "c"))); script["edge_data"] = [1e308, 1e308]
    elif defect in ("combined_upload_overflow", "combined_download_overflow"):
        script.update(data_size=[1e308] * 3, edge_data=[1e308, 0])
        if defect == "combined_upload_overflow":
            # Keep the parent's base small so failure occurs at the child's upload.
            script["data_size"] = [0, 1e308, 0]
    elif defect in ("pt_underflow", "pt_overflow"):
        script["workload"] = [5e-324 if defect == "pt_underflow" else 1e308] * 3
        rate = 1e308 if defect == "pt_underflow" else 5e-324
        env = replace(env, devices=(replace(env.devices[0], processing_rate=rate), env.devices[1]))
    else:
        field = "upload_bandwidth" if defect == "ut_overflow" else "download_bandwidth"
        env = replace(env, servers=(replace(env.servers[0], **{field: 5e-324}), env.servers[1]))
    inputs = inputs_for(t); trace_roles(monkeypatch, inputs, script)
    with pytest.raises(NumericDerivationError): generate_workflow_input(inputs, env, cause, candidate_id=0)


def test_unexpected_sampler_exception_propagates(monkeypatch):
    inputs = inputs_for()
    def bug(self, rng): raise RuntimeError("injected implementation bug")
    monkeypatch.setattr(type(inputs.samplers.workload), "sample", bug)
    with pytest.raises(RuntimeError, match="injected implementation bug"):
        generate_workflow_input(inputs, environment(), GenerationCause("initialize", "phone-X", 0), candidate_id=0)
