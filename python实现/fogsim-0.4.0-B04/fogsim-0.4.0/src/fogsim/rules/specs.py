"""Public immutable rule descriptions and frozen stage-D semantic versions.

This module deliberately does not parse expressions or install rules. Existing
v1 configuration classes are unchanged until their assigned integration batch.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from fogsim.gp.diagnostics import GPCode, GPDiagnostic, GPInputError

LANGUAGE_VERSION = "fogsim-gp-lisp-v1"
FEATURE_SEMANTICS_VERSION = "fogsim-features-java-v1"
NUMERIC_SEMANTICS_VERSION = "fogsim-gp-f64-dual-zero-v1"
SELECTION_POLICY_VERSION = "fogsim-selection-java-v1"
IDENTITY_ENCODING_VERSION = "fogsim-rule-identity-v1"
SCORE_ENCODING_VERSION = "ieee754-binary64-hex-v1"
FCFS_SEMANTICS_VERSION = "fogsim-fcfs-v1"
FIXED_RESOURCE_SEMANTICS_VERSION = "fogsim-fixed-resource-v1"


class RuleRole(str, Enum):
    ROUTING = "routing"
    SEQUENCING = "sequencing"


def _invalid(message, role, field_path, code=GPCode.RULE_SPEC_INVALID):
    raise GPInputError(GPDiagnostic(code, message, field_path, role))


def _role(value, field_path):
    if not isinstance(value, (str, RuleRole)):
        _invalid("role must be routing or sequencing", None, field_path)
    try:
        return RuleRole(value)
    except ValueError as exc:
        raise GPInputError(GPDiagnostic(GPCode.RULE_SPEC_INVALID,
            "role must be routing or sequencing", field_path)) from exc


@dataclass(frozen=True, slots=True)
class RuleSpec:
    role: RuleRole
    kind: str = "fcfs"
    resource_id: str | None = None
    expression: str | None = None

    def __post_init__(self):
        role = _role(self.role, "rule.role")
        object.__setattr__(self, "role", role)
        self._validate(f"{role.value}_rule")

    def _validate(self, field_path):
        role = self.role.value
        allowed = ("fcfs", "fixed_resource", "gp") if self.role == RuleRole.ROUTING else ("fcfs", "gp")
        if type(self.kind) is not str or self.kind not in allowed:
            _invalid(f"unsupported {role} kind: {self.kind!r}", role, f"{field_path}.kind")
        if self.kind == "fixed_resource":
            if type(self.resource_id) is not str or not self.resource_id.strip():
                _invalid("fixed_resource requires nonempty resource_id", role, f"{field_path}.resource_id")
        elif self.resource_id is not None:
            _invalid("resource_id is only valid for fixed_resource", role, f"{field_path}.resource_id")
        if self.kind == "gp":
            if type(self.expression) is not str:
                _invalid("gp requires expression text", role, f"{field_path}.expression")
            # The language has exactly six ASCII whitespace characters. Other
            # characters remain intact for the B02 strict lexer to diagnose.
            if not self.expression.strip(" \t\n\v\f\r"):
                raise GPInputError(GPDiagnostic.at_source(GPCode.EMPTY_EXPRESSION,
                    "expression is empty", text=self.expression, start=len(self.expression),
                    end=len(self.expression), field_path=f"{field_path}.expression", role=role))
        elif self.expression is not None:
            _invalid("expression is only valid for gp", role, f"{field_path}.expression")

    @classmethod
    def from_mapping(cls, role, data, *, field_path=None):
        """Validate exact public fields without normalising original text."""
        role = _role(role, "rule.role")
        path = field_path if field_path is not None else f"{role.value}_rule"
        if not isinstance(data, Mapping):
            _invalid("rule must be an object", role.value, path)
        kind = data.get("kind")
        allowed = {"kind"}
        if kind == "fixed_resource":
            allowed.add("resource_id")
        elif kind == "gp":
            allowed.add("expression")
        for key in data:
            if key not in allowed:
                _invalid(f"unknown or conflicting field: {key!r}", role.value, f"{path}.{key}")
        try:
            return cls(role, kind, data.get("resource_id"), data.get("expression"))
        except GPInputError as exc:
            # Rebase only diagnostic paths, never the rule's source text.
            d = exc.diagnostic
            prefix = f"{role.value}_rule"
            if d.field_path.startswith(prefix):
                from dataclasses import replace
                raise GPInputError(replace(d, field_path=path + d.field_path[len(prefix):])) from exc
            raise

    def to_dict(self):
        result = {"kind": self.kind}
        if self.kind == "fixed_resource":
            result["resource_id"] = self.resource_id
        elif self.kind == "gp":
            result["expression"] = self.expression
        return result
