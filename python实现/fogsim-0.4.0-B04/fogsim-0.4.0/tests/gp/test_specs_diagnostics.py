from dataclasses import FrozenInstanceError

import pytest

from fogsim.errors import InputError, StateError
from fogsim.gp.diagnostics import GPCode, GPDiagnostic, GPInputError, GPStateError
from fogsim.rules import specs
from fogsim.rules.specs import RuleRole, RuleSpec


@pytest.mark.parametrize("routing", [dict(kind="fcfs"), dict(kind="fixed_resource", resource_id="E0"),
    dict(kind="gp", expression=" \t(+ PT UT)\r\n")])
@pytest.mark.parametrize("sequencing", [dict(kind="fcfs"), dict(kind="gp", expression="(- 0 TWT)")])
def test_six_combinations_roundtrip_and_immutability(routing, sequencing):
    for role, data in (("routing", routing), ("sequencing", sequencing)):
        spec = RuleSpec.from_mapping(role, data)
        assert spec.role == RuleRole(role)
        assert spec.to_dict() == data
        with pytest.raises(FrozenInstanceError):
            spec.expression = "PT"
        exported = spec.to_dict()
        exported["kind"] = "invalid"
        assert spec.to_dict() == data


@pytest.mark.parametrize("role,data,suffix,code", [
    ("routing", {}, ".kind", GPCode.RULE_SPEC_INVALID),
    ("routing", [], "", GPCode.RULE_SPEC_INVALID),
    ("routing", {"kind": True}, ".kind", GPCode.RULE_SPEC_INVALID),
    ("routing", {"kind": "GP", "expression": "PT"}, ".expression", GPCode.RULE_SPEC_INVALID),
    ("routing", {"kind": "gp"}, ".expression", GPCode.RULE_SPEC_INVALID),
    ("routing", {"kind": "gp", "expression": []}, ".expression", GPCode.RULE_SPEC_INVALID),
    ("routing", {"kind": "gp", "expression": " \t\r\n\v\f"}, ".expression", GPCode.EMPTY_EXPRESSION),
    ("routing", {"kind": "gp", "expression": ""}, ".expression", GPCode.EMPTY_EXPRESSION),
    ("routing", {"kind": "gp", "expression": "PT", "resource_id": None}, ".resource_id", GPCode.RULE_SPEC_INVALID),
    ("routing", {"kind": "fcfs", "expression": None}, ".expression", GPCode.RULE_SPEC_INVALID),
    ("routing", {"kind": "fixed_resource", "resource_id": " "}, ".resource_id", GPCode.RULE_SPEC_INVALID),
    ("routing", {"kind": "fixed_resource", "resource_id": "E0", "expression": "PT"}, ".expression", GPCode.RULE_SPEC_INVALID),
    ("sequencing", {"kind": "fixed_resource", "resource_id": "E0"}, ".kind", GPCode.RULE_SPEC_INVALID),
    ("sequencing", {"kind": "fcfs", "extra": 1}, ".extra", GPCode.RULE_SPEC_INVALID),
])
def test_strict_descriptors(role, data, suffix, code, evidence):
    with pytest.raises(GPInputError) as caught:
        RuleSpec.from_mapping(role, data, field_path="run.rule")
    d = caught.value.diagnostic
    assert isinstance(caught.value, InputError)
    assert d.code == code and d.role == role and d.field_path == "run.rule" + suffix
    evidence("descriptor-errors", d.to_dict())


@pytest.mark.parametrize("role", [None, [], "ROUTING", "other", 1, True])
def test_invalid_roles(role):
    with pytest.raises(GPInputError):
        RuleSpec(role)


def test_description_is_not_a_parser_or_configuration_upgrade():
    text = "(+ PT)\u00a0"
    assert RuleSpec("routing", "gp", expression=text).expression == text
    from fogsim.config import RunConfig
    from fogsim.experiment_config import RuleConfig
    with pytest.raises(InputError):
        RunConfig(routing_kind="gp")
    with pytest.raises(InputError):
        RuleConfig("gp")
    assert set(RunConfig().to_dict()) == {"routing_kind", "fixed_resource_id", "sequencing_kind",
        "trace_enabled", "event_policy", "max_events", "check_invariants"}


def test_versions_are_exact():
    assert [specs.LANGUAGE_VERSION, specs.FEATURE_SEMANTICS_VERSION, specs.NUMERIC_SEMANTICS_VERSION,
        specs.SELECTION_POLICY_VERSION, specs.IDENTITY_ENCODING_VERSION, specs.SCORE_ENCODING_VERSION,
        specs.FCFS_SEMANTICS_VERSION, specs.FIXED_RESOURCE_SEMANTICS_VERSION] == [
        "fogsim-gp-lisp-v1", "fogsim-features-java-v1", "fogsim-gp-f64-dual-zero-v1",
        "fogsim-selection-java-v1", "fogsim-rule-identity-v1", "ieee754-binary64-hex-v1",
        "fogsim-fcfs-v1", "fogsim-fixed-resource-v1"]


@pytest.mark.parametrize("text,start,end,line,column", [
    ("x\r\n\tPT", 4, 6, 2, 2), ("x\rPT", 2, 4, 2, 1), ("x\nPT", 2, 4, 2, 1),
    ("\r\n\r\n", 4, 4, 3, 1), ("PT", 2, 2, 1, 3), ("\t?", 1, 2, 1, 2),
])
def test_source_coordinates(text, start, end, line, column, evidence):
    d = GPDiagnostic.at_source(GPCode.UNKNOWN_FEATURE, "unknown", text=text, start=start, end=end,
        field_path="routing_rule.expression", role="routing")
    assert (d.start, d.end, d.line, d.column, d.token) == (start, end, line, column, text[start:end])
    with pytest.raises(FrozenInstanceError):
        d.start = 0
    evidence("diagnostics", d.to_dict())


def test_diagnostic_error_domains_and_invalid_spans():
    d = GPDiagnostic(GPCode.CONTEXT_PHASE_INVALID, "phase", "option", "sequencing")
    assert isinstance(GPStateError(d), StateError)
    assert GPStateError(d).reason_code == "GP_CONTEXT_PHASE_INVALID"
    with pytest.raises(ValueError):
        GPDiagnostic(GPCode.ARITY_ERROR, "arity", "expression", start=0)
    with pytest.raises(ValueError):
        GPDiagnostic.at_source(GPCode.ARITY_ERROR, "arity", text="PT", start=True, end=2, field_path="x")
    with pytest.raises(ValueError):
        GPDiagnostic.at_source(GPCode.ARITY_ERROR, "arity", text="PT", start=0, end=3, field_path="x")
