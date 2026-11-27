"""Finite generated graphs through the unchanged kernel; no dynamic source hook."""
from dataclasses import replace
import pytest
from conftest import ROOT
from fogsim import (load_experiment_config, prepare_random_input, sample_environment, build_environment,
                    generate_workflow_input, materialize_workflow)
from fogsim.config import RunConfig
from fogsim.environment.spec import EnvironmentSnapshot, DeviceSnapshot, ServerSnapshot
from fogsim.instances.generated import (GenerationCause, CandidateRecord, GenerationAttempt, InputArchive, AdmissionMapping)
from fogsim.experiment_config import WorkflowTypeRange
from fogsim.simulation.engine import Engine
from fogsim.simulation.events import JobArrivalEvent


def test_environment_then_initial_devices_share_exact_input_stream():
    cfg = load_experiment_config(ROOT / "configs/examples/step1_dynamic.json")
    cfg = replace(cfg, source=replace(cfg.source, workflow_types=WorkflowTypeRange(0, 0)))
    first, second = prepare_random_input(cfg), prepare_random_input(cfg)
    e1 = sample_environment(cfg.source.environment, first, parameter_source=cfg.fingerprint)
    e2 = sample_environment(cfg.source.environment, second, parameter_source=cfg.fingerprint)
    assert e1 == e2 and first.rng is not second.rng
    records, attempts, mappings = [], [], []
    for i, device in enumerate(e1.devices):
        cause = GenerationCause("initialize", device.id, 0)
        a = generate_workflow_input(first, e1, cause, candidate_id=i)
        b = generate_workflow_input(second, e2, cause, candidate_id=i)
        assert a == b
        records.append(CandidateRecord(str(i + 1), a))
        attempts.append(GenerationAttempt(i + 1, cause, str(i + 1), True))
        mappings.append(AdmissionMapping(str(i + 1), i))
    assert first.snapshot() == second.snapshot()
    archive = InputArchive(first.catalog.templates, e1, tuple(records), tuple(attempts), tuple(mappings))
    state = build_environment(e1)
    graphs = [materialize_workflow(r.workflow_input, first.catalog.template(0), state, input_record_id=r.record_id) for r in records]
    assert graphs[0].tasks[0].options[1].resource is graphs[1].tasks[0].options[1].resource
    graphs[0].tasks[0].output_data_by_child.clear()
    assert archive == InputArchive(first.catalog.templates, e1, tuple(records), tuple(attempts), tuple(mappings))


def test_single_server_parent_and_child_keep_upload_download(tmp_path):
    (tmp_path / "CyberShake_30.xml").write_text('<adag><job id="A"/><job id="B"/>'
        '<child ref="B"><parent ref="A"/></child></adag>')
    cfg = load_experiment_config(ROOT / "configs/examples/step1_dynamic.json")
    cfg = replace(cfg, source=replace(cfg.source, dag_root=tmp_path, workflow_types=WorkflowTypeRange(0, 0)))
    inputs = prepare_random_input(cfg)
    # Controlled scalar values exercise the real two-pass generator and existing events.
    from unittest.mock import patch
    samplers = inputs.samplers
    def values(self, rng):
        if self is samplers.workload: return 100.0
        if self is samplers.data_size: return 10.0
        if self is samplers.edge_data: return 5.0
        raise AssertionError("unexpected sampling role")
    env = EnvironmentSnapshot((DeviceSnapshot("M0", 0, 125, False),),
        (ServerSnapshot("E0", 0, "EDGE", 100, 10, 10),), "hand-check")
    with patch.object(type(samplers.workload), "sample", values), patch.object(type(samplers.inter_release_time), "sample", return_value=2):
        candidate = generate_workflow_input(inputs, env, GenerationCause("initialize", "M0", 0), candidate_id=0)
    state = build_environment(env)
    graph = materialize_workflow(candidate, inputs.catalog.template(0), state, input_record_id="1")
    # Test-only fixed finite registration. Production centralized admission is step 5.
    state.workflows_by_id[0] = state.pending_arrivals[0] = graph
    state.tasks_by_key.update((t.key, t) for t in graph.tasks)
    engine = Engine(state, RunConfig())
    engine.event_queue.stage(JobArrivalEvent(graph), graph.owner_device)
    result = engine.run()
    assert result.status == "SUCCEEDED" and result.makespan == 7
    assert [e.finish_time for e in graph.completed_executions] == [5.5, 9]
    assert graph.tasks[1].options[0].upload_time == 1.5
    assert graph.tasks[1].options[0].download_time == 1


@pytest.mark.parametrize("type_id", range(20))
def test_all_standard_templates_generate_complete_independent_graphs(type_id):
    cfg = load_experiment_config(ROOT / "configs/examples/step1_dynamic.json")
    cfg = replace(cfg, source=replace(cfg.source, workflow_types=WorkflowTypeRange(type_id, type_id)))
    inputs = prepare_random_input(cfg)
    env = sample_environment(cfg.source.environment, inputs, parameter_source=cfg.fingerprint)
    state = build_environment(env)
    t = inputs.catalog.template(type_id)
    graphs = []
    for index, device in enumerate(env.devices):
        c = generate_workflow_input(inputs, env, GenerationCause("initialize", device.id, 0), candidate_id=index)
        graph = materialize_workflow(c, t, state, input_record_id=str(index + 1))
        assert len(c.edges) == len(t.dependencies) and len(graph.tasks) == len(t.tasks)
        edge_values = {(e.parent_id, e.child_id): e.data_size for e in c.edges}
        for task in graph.tasks:
            input_total = 0.0; output_total = 0.0
            for parent in task.parents: input_total += edge_values[parent.id, task.id]
            for child in task.children: output_total += edge_values[task.id, child.id]
            assert task.total_input_data == input_total and task.total_output_data == output_total
            assert list(task.input_data_by_parent) == [p.id for p in task.parents]
            assert list(task.output_data_by_child) == [child.id for child in task.children]
            assert task.workflow is graph
            for option in task.options:
                assert option.resource is state.resources_by_id[option.resource.id]
        graphs.append(graph)
    assert graphs[0].tasks[0] is not graphs[1].tasks[0]
    assert graphs[0].tasks[0].options[1].resource is graphs[1].tasks[0].options[1].resource
    assert not state.workflows_by_id and not state.tasks_by_key
