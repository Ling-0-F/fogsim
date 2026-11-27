"""Atomic two-slot preparation and exact active-source installation checks.

The exact structural keys here are local installation keys. B04 owns the frozen
wire identities and manifest; these keys are never published as rule IDs.
"""
from dataclasses import dataclass

from fogsim.errors import InputError
from fogsim.gp.parser import parse_expression
from fogsim.gp.program import compile_expression
from fogsim.gp.diagnostics import GPCode, GPDiagnostic, GPInputError
from .baselines import FCFS, FixedResource
from .gp import GPRule
from .specs import RuleSpec, RuleRole


def _input(code, message, role=None):
    raise GPInputError(GPDiagnostic(code, message, "rules", role))


def _check_spec(spec, role):
    if type(spec) is not RuleSpec:
        _input(GPCode.RULE_SPEC_INVALID, "expected RuleSpec", role.value)
    if spec.role != role:
        _input(GPCode.RULE_ROLE_MISMATCH, "rule is bound to the wrong slot", role.value)


def _check_binding(spec, rule):
    if spec.kind == "gp":
        if type(rule) is not GPRule or rule.spec != spec:
            _input(GPCode.PREPARED_RULE_MISMATCH, "GP binding differs from its active source", spec.role.value)
        # Revalidate immutable provenance and versions at installation too.
        rule.validate_binding()
    elif spec.kind == "fcfs":
        if type(rule) is not FCFS:
            _input(GPCode.PREPARED_RULE_MISMATCH, "FCFS binding mismatch", spec.role.value)
    elif type(rule) is not FixedResource or rule.resource_id != spec.resource_id:
        _input(GPCode.PREPARED_RULE_MISMATCH, "fixed target binding mismatch", spec.role.value)


@dataclass(frozen=True, slots=True)
class PreparedRules:
    routing_spec: RuleSpec
    sequencing_spec: RuleSpec
    routing: object
    sequencing: object

    def __post_init__(self):
        for role in RuleRole:
            spec = getattr(self, role.value + "_spec")
            _check_spec(spec, role)
            _check_binding(spec, getattr(self, role.value))

    @property
    def rule_manifest(self):
        from fogsim.gp.identity import rule_manifest
        return rule_manifest(self)

    @property
    def rule_pair_id(self):
        return self.rule_manifest["rule_pair_id"]

    @property
    def has_gp(self):
        return self.routing_spec.kind == "gp" or self.sequencing_spec.kind == "gp"


def prepare_rules(routing_spec, sequencing_spec):
    _check_spec(routing_spec, RuleRole.ROUTING)
    _check_spec(sequencing_spec, RuleRole.SEQUENCING)
    programs = {}  # Bounded to this pair; never stores runtime objects.

    def bind(spec):
        if spec.kind == "fcfs":
            return FCFS()
        if spec.kind == "fixed_resource":
            return FixedResource(spec.resource_id)
        parsed = parse_expression(spec.expression, role=spec.role.value,
                                  field_path=f"{spec.role.value}_rule.expression")
        compiled = compile_expression(parsed)
        compiled = programs.setdefault(compiled.structure_key, compiled)
        return GPRule(spec, parsed, compiled)

    routing = bind(routing_spec)
    sequencing = bind(sequencing_spec)
    prepared = PreparedRules(routing_spec, sequencing_spec, routing, sequencing)
    # Validate identity encodability before a control layer can create an RNG.
    try:
        prepared.rule_manifest
    except (ValueError, UnicodeError) as exc:
        raise GPInputError(GPDiagnostic(GPCode.RULE_IDENTITY_MISMATCH,
            str(exc), "rule_manifest")) from exc
    return prepared


def specs_for_config(config):
    if hasattr(config, "routing_rule"):
        return (RuleSpec.from_mapping("routing", config.routing_rule.to_dict()),
                RuleSpec.from_mapping("sequencing", config.sequencing_rule.to_dict()))
    return (RuleSpec("routing", config.routing_kind, config.fixed_resource_id, config.routing_expression),
            RuleSpec("sequencing", config.sequencing_kind, expression=config.sequencing_expression))


def install_rules(config, prepared=None):
    routing, sequencing = specs_for_config(config)
    if prepared is None:
        return prepare_rules(routing, sequencing)
    if type(prepared) is not PreparedRules:
        _input(GPCode.PREPARED_RULE_MISMATCH, "expected PreparedRules")
    prepared.__post_init__()
    if (prepared.routing_spec != routing or prepared.sequencing_spec != sequencing):
        _input(GPCode.PREPARED_RULE_MISMATCH, "prepared rules do not match the active configuration")
    return prepared


def validate_rules_for_environment(prepared, environment_or_fixed_spec):
    """Validate a fixed target for every task/device before consuming a source."""
    if type(prepared) is not PreparedRules:
        _input(GPCode.PREPARED_RULE_MISMATCH, "expected PreparedRules")
    if prepared.routing_spec.kind != "fixed_resource":
        return
    target = prepared.routing_spec.resource_id
    scene = environment_or_fixed_spec
    if hasattr(scene, "is_eligible_for_all"):
        valid = scene.is_eligible_for_all(target)
    elif hasattr(scene, "eligible_resource_ids"):
        valid = all(target in scene.eligible_resource_ids(d.id) for d in scene.devices)
    elif hasattr(scene, "resources_by_id"):
        resource = scene.resources_by_id.get(target)
        valid = resource is not None and all(
            resource in scene.servers or (resource is d and d.can_process_tasks) for d in scene.mobile_devices)
        valid = valid and all(any(o.resource is resource for o in t.options) for t in scene.tasks_by_key.values())
    else:
        valid = all(any(o.resource_id == target for o in t.options) for w in scene.workflows for t in w.tasks)
    if not valid:
        raise InputError(f"fixed target {target} is not eligible for every task/device")
