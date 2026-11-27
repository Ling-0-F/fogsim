"""Immutable role/source binding; runtime validation precedes pure evaluation."""
from dataclasses import dataclass, field
import hashlib

from fogsim.gp.ast import ParsedExpression, structural_key
from fogsim.gp.program import CompiledExpression
from fogsim.gp.evaluator import evaluate
from fogsim.gp.parser import parse_expression
from fogsim.gp.diagnostics import GPCode, GPDiagnostic, GPInputError, GPStateError
from .base import RuleKind
from .contexts import RoutingContext, SequencingContext
from .specs import (RuleSpec, RuleRole, LANGUAGE_VERSION, FEATURE_SEMANTICS_VERSION,
                    NUMERIC_SEMANTICS_VERSION)


@dataclass(frozen=True, slots=True)
class GPRule:
    spec: RuleSpec
    parsed: ParsedExpression
    compiled: CompiledExpression
    source_sha256: str = field(init=False)

    def __post_init__(self):
        self.validate_binding()
        object.__setattr__(self, "source_sha256", "sha256:" + hashlib.sha256(
            self.parsed.text.encode("utf-8")).hexdigest())

    def validate_binding(self):
        if type(self.spec) is not RuleSpec or self.spec.kind != "gp":
            raise GPInputError(GPDiagnostic(GPCode.PREPARED_RULE_MISMATCH,
                "GPRule requires a GP RuleSpec", "rule"))
        source = parse_expression(self.spec.expression, role=self.spec.role.value,
                                  field_path=f"{self.spec.role.value}_rule.expression")
        if (type(self.parsed) is not ParsedExpression
                or type(self.compiled) is not CompiledExpression
                or self.parsed.text != self.spec.expression
                or structural_key(source.root) != structural_key(self.parsed.root)
                or source.spans != self.parsed.spans
                or structural_key(self.parsed.root) != self.compiled.structure_key
                or structural_key(self.compiled.root) != self.compiled.structure_key
                or (self.compiled.language_version, self.compiled.feature_semantics_version,
                    self.compiled.numeric_semantics_version) !=
                   (LANGUAGE_VERSION, FEATURE_SEMANTICS_VERSION, NUMERIC_SEMANTICS_VERSION)):
            raise GPInputError(GPDiagnostic(GPCode.PREPARED_RULE_MISMATCH,
                "GP source, structure or semantic versions do not match", "rule", self.spec.role.value))
        expected = "sha256:" + hashlib.sha256(self.parsed.text.encode("utf-8")).hexdigest()
        if hasattr(self, "source_sha256") and self.source_sha256 != expected:
            raise GPInputError(GPDiagnostic(GPCode.PREPARED_RULE_MISMATCH,
                "GP source digest mismatch", "rule", self.spec.role.value))

    @property
    def role(self):
        return self.spec.role

    def priority(self, option, context, *, observer=None):
        validate_context(self.role, option, context)
        return evaluate(self.compiled, option, context) if observer is None else evaluate(self.compiled, option, context, observer=observer)


def validate_context(role, option, context):
    """Use object identity throughout; equal IDs never authorize foreign objects.

    Context clocks are values and must be freshly constructed by EventContext.
    This validation cannot turn an old context into a historical snapshot.
    """
    def fail(code, message):
        raise GPStateError(GPDiagnostic(code, message, "context", role.value))

    expected = RoutingContext if role == RuleRole.ROUTING else SequencingContext
    kind = RuleKind.ROUTING if role == RuleRole.ROUTING else RuleKind.SEQUENCING
    if type(context) is not expected or context.kind != kind:
        fail(GPCode.RULE_ROLE_MISMATCH, "rule role and context role differ")
    if not any(candidate is option for candidate in context.candidates):
        fail(GPCode.CONTEXT_IDENTITY_MISMATCH, "option is not a context candidate")

    def canonical(value, objects):
        matches = [item for item in objects if item.id == value.id]
        return len(matches) == 1 and matches[0] is value

    for candidate in context.candidates:
        task, resource = candidate.task, candidate.resource
        workflow = task.workflow
        if (not canonical(resource, context.view.resources)
                or not canonical(workflow, context.view.active_workflows)
                or not canonical(workflow.owner_device, context.view.resources)
                or not any(item is task for item in workflow.tasks)
                or not any(item is candidate for item in task.options)):
            fail(GPCode.CONTEXT_IDENTITY_MISMATCH, "foreign resource, workflow, task or option")
        if role == RuleRole.ROUTING:
            if task is not context.task:
                fail(GPCode.CONTEXT_IDENTITY_MISMATCH, "routing candidates must share the context task")
            if task.dispatched or task.completed:
                fail(GPCode.CONTEXT_PHASE_INVALID, "routing task must be incomplete and undispatched")
        else:
            if resource is not context.resource:
                fail(GPCode.CONTEXT_IDENTITY_MISMATCH, "sequencing candidates must share the context resource")
            if (not task.dispatched or task.completed
                    or not any(item is candidate for item in resource.waiting_queue)):
                fail(GPCode.CONTEXT_PHASE_INVALID, "sequencing candidate must remain dispatched and queued")
