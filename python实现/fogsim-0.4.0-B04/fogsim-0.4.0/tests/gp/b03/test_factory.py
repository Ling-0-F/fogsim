from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import pytest

from fogsim import RunConfig, create_engine, load_fixed_instance, create_dynamic_context
from fogsim.config import load_config
from fogsim.experiment_config import RuleConfig, parse_experiment_config
from fogsim.errors import InputError
from fogsim.gp.diagnostics import GPInputError
from fogsim.gp.parser import parse_expression
from fogsim.gp.program import compile_expression
from fogsim.rules.gp import GPRule
from fogsim.rules.factory import (prepare_rules, install_rules, validate_rules_for_environment)
from fogsim.rules.specs import RuleSpec
from conftest import ROOT
from .helpers import prepared, gp_dynamic, dynamic_config


@pytest.mark.parametrize("route", [RuleSpec("routing"), RuleSpec("routing", "fixed_resource", "E0"),
                                    RuleSpec("routing", "gp", expression="PT")])
@pytest.mark.parametrize("sequence", [RuleSpec("sequencing"), RuleSpec("sequencing", "gp", expression="TWT")])
def test_six_bindings_are_atomic_and_immutable(route, sequence, evidence_b03):
    p = prepare_rules(route, sequence)
    cfg = RunConfig(route.kind, route.resource_id, sequence.kind,
                    routing_expression=route.expression, sequencing_expression=sequence.expression)
    assert install_rules(cfg, p) is p
    with pytest.raises(FrozenInstanceError): p.routing = object()
    for rule in (p.routing, p.sequencing):
        assert not any(hasattr(rule, attr) for attr in ("current_option", "context", "last_score", "last_features"))
    evidence_b03("factory", dict(routing=route.to_dict(), sequencing=sequence.to_dict(), immutable=True))


def test_same_structure_two_roles_share_program_keep_sources():
    p = prepared("(+ PT 1)", "( + PT 1d )")
    assert p.routing is not p.sequencing
    assert p.routing.role != p.sequencing.role
    assert p.routing.compiled is p.sequencing.compiled
    for rule in (p.routing, p.sequencing):
        assert rule.source_sha256 == "sha256:" + hashlib.sha256(rule.spec.expression.encode()).hexdigest()
        assert rule.parsed.text == rule.spec.expression
        with pytest.raises(FrozenInstanceError): rule.compiled = None
    assert p.routing.source_sha256 != p.sequencing.source_sha256


@pytest.mark.parametrize("text", ["PT", "(+ PT 1)", "(- PT 0)", "-0.0"])
def test_same_structure_different_current_source_is_not_silently_installed(text):
    p = prepared(text, "TWT")
    cfg = RunConfig("gp", sequencing_kind="gp", routing_expression=" " + text,
                    sequencing_expression="TWT")
    with pytest.raises(GPInputError, match="GP_PREPARED_RULE_MISMATCH"):
        install_rules(cfg, p)


@pytest.mark.parametrize("slot", ["routing", "sequencing"])
def test_invalid_expression_never_publishes_pair(slot, monkeypatch):
    import fogsim.rules.factory as factory
    calls = []
    original = factory.PreparedRules
    monkeypatch.setattr(factory, "PreparedRules", lambda *args: calls.append(args))
    specs = dict(routing=RuleSpec("routing", "gp", expression="PT"),
                 sequencing=RuleSpec("sequencing", "gp", expression="TWT"))
    specs[slot] = RuleSpec(slot, "gp", expression="(+ PT)")
    with pytest.raises(GPInputError) as caught:
        factory.prepare_rules(specs["routing"], specs["sequencing"])
    assert caught.value.diagnostic.role == slot
    assert caught.value.diagnostic.field_path == slot + "_rule.expression"
    assert calls == []
    monkeypatch.setattr(factory, "PreparedRules", original)


def test_role_mismatch_rejected():
    with pytest.raises(GPInputError, match="GP_RULE_ROLE_MISMATCH"):
        prepare_rules(RuleSpec("sequencing"), RuleSpec("routing"))


@pytest.mark.parametrize("attribute,value", [("language_version", "wrong"),
    ("feature_semantics_version", "wrong"), ("numeric_semantics_version", "wrong")])
def test_install_checks_semantic_versions(attribute, value):
    p = prepared()
    object.__setattr__(p.routing.compiled, attribute, value)
    with pytest.raises(GPInputError, match="GP_PREPARED_RULE_MISMATCH"):
        install_rules(RunConfig("gp", sequencing_kind="gp", routing_expression="PT",
                               sequencing_expression="(- 0 PT)"), p)


def test_constructor_rejects_source_with_unrelated_tree():
    source = parse_expression("PT")
    object.__setattr__(source, "text", "UT")
    with pytest.raises(GPInputError, match="GP_PREPARED_RULE_MISMATCH"):
        GPRule(RuleSpec("routing", "gp", expression="UT"), source, compile_expression(source))


@pytest.mark.parametrize("target", ["E0", "missing", "M0"])
def test_fixed_eligibility_for_every_task_and_device(target, tmp_path):
    p = prepare_rules(RuleSpec("routing", "fixed_resource", target), RuleSpec("sequencing"))
    spec = load_fixed_instance(ROOT / "data/cases/chain_remote.json")
    if target == "missing":
        with pytest.raises(InputError): validate_rules_for_environment(p, spec)
    else: validate_rules_for_environment(p, spec)
    cfg = dynamic_config(tmp_path, devices=2, edges=1)
    if target == "E0": validate_rules_for_environment(p, cfg.source.environment)
    else:
        with pytest.raises(InputError): validate_rules_for_environment(p, cfg.source.environment)


def test_old_positional_api_and_exact_output_shape():
    old = RunConfig("fixed_resource", "E0", "fcfs", False, "java_compatible", 77, False)
    assert old.to_dict() == dict(routing_kind="fixed_resource",fixed_resource_id="E0",sequencing_kind="fcfs",
        trace_enabled=False,event_policy="java_compatible",max_events=77,check_invariants=False)
    assert RuleConfig().to_dict() == {"kind":"fcfs"}


def test_old_fixed_config_accepts_two_gp_slots_and_rejects_extra(tmp_path):
    data = dict(instance="input.json", routing_rule=dict(kind="gp",expression="PT"),
                sequencing_rule=dict(kind="gp",expression="TWT"))
    path = tmp_path / "config.json"; path.write_text(json.dumps(data))
    instance, cfg = load_config(path)
    assert instance == tmp_path / "input.json"
    assert cfg.routing_expression == "PT" and cfg.sequencing_expression == "TWT"
    data["sequencing_rule"]["resource_id"] = "E0"; path.write_text(json.dumps(data))
    with pytest.raises(InputError): load_config(path)


def test_v1_rejects_gp_and_v2_json_is_supported_by_b04(tmp_path):
    cfg = dynamic_config(tmp_path)
    from dataclasses import replace
    with pytest.raises(InputError, match="schema_version=1"):
        replace(cfg, run=replace(cfg.run, routing_rule=RuleConfig("gp", expression="PT")))
    data = cfg.to_dict(); data["schema_version"] = 2
    # v2 uses exact field shapes; the v1 historical normalization includes null.
    for role in ("routing", "sequencing"):
        data["run"][role + "_rule"] = getattr(cfg.run, role + "_rule").to_dict()
    assert parse_experiment_config(data).schema_version == 2


@pytest.mark.parametrize("failure", ["parse", "prepared"])
def test_invalid_rule_before_rng_environment_or_source(tmp_path, monkeypatch, failure):
    import fogsim.simulation.context as module
    cfg = gp_dynamic(tmp_path, route="(+ PT)" if failure == "parse" else "PT")
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(True); raise AssertionError("input preparation attempted")
    for name in ("prepare_random_input", "sample_environment", "RandomWorkflowSource"):
        monkeypatch.setattr(module, name, forbidden)
    with pytest.raises(GPInputError):
        create_dynamic_context(cfg, prepared_rules=None if failure == "parse" else prepared("UT"))
    assert calls == []


def test_run_result_and_capture_cannot_mislabel_v2_as_v1(tmp_path):
    from fogsim.replay.export_input import export_replay_input
    from fogsim.experiments.runner import run_experiment
    cfg = gp_dynamic(tmp_path)
    context = create_dynamic_context(cfg); result = context.run()
    assert result.status == "SUCCEEDED" and result.output_profile == "v2"
    assert result.to_dict()["schema_version"] == 2
    assert export_replay_input(context.engine, cfg.source).schema_version == 2
    assert run_experiment(cfg).to_dict()["schema_version"] == 2


def test_explicit_v2_baselines_also_require_v2_output(tmp_path):
    cfg = replace(dynamic_config(tmp_path), schema_version=2)
    context = create_dynamic_context(cfg); result = context.run()
    assert result.status == "SUCCEEDED" and result.output_profile == "v2"
    assert result.to_dict()["schema_version"] == 2


def test_v2_replay_adapter_reads_validated_inputs(tmp_path):
    from fogsim.experiment_config import ExperimentConfig,ReplaySourceConfig,ReplayRunOptions
    from fogsim.replay.export_input import export_replay_input
    import fogsim.replay.engine as module
    import json
    cfg=gp_dynamic(tmp_path);ctx=create_dynamic_context(cfg);ctx.run()
    path=tmp_path/"input.json";path.write_text(json.dumps(export_replay_input(ctx.engine,cfg.source).to_dict()))
    replay=ExperimentConfig("replay",ReplaySourceConfig(path,purpose="reuse_inputs"),ReplayRunOptions(),schema_version=2)
    result=module.simulate_replay_config(replay)
    assert result.status=="SUCCEEDED" and result.to_dict()["schema_version"]==2
