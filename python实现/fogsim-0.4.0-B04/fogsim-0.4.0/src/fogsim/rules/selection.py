import math
import struct
from fogsim.errors import require, StateError
from .base import RuleKind
from .contexts import graph_fingerprint
from fogsim.gp.diagnostics import GPCode, GPDiagnostic, GPStateError


def double_compare(a: float, b: float) -> int:
    """java.lang.Double.compare, including signed zero and canonical NaN."""
    if a < b:
        return -1
    if a > b:
        return 1
    def bits(x):
        if math.isnan(x):
            return 0x7ff8000000000000
        return struct.unpack(">q", struct.pack(">d", x))[0]
    aa, bb = bits(a), bits(b)
    return (aa > bb) - (aa < bb)


def is_preferred(candidate, incumbent) -> bool:
    cmp = double_compare(candidate.priority, incumbent.priority)
    if cmp:
        return cmp < 0
    a, b = candidate.task.workflow, incumbent.task.workflow
    if a.release_time != b.release_time:
        return a.release_time < b.release_time
    if a.owner_device.numeric_id != b.owner_device.numeric_id:
        return a.owner_device.numeric_id < b.owner_device.numeric_id
    return a.id < b.id


def _choose(context, rule, recorder=None):
    require(bool(context.candidates), "cannot select from empty candidates")
    best = context.candidates[0]
    scores = []
    for index, option in enumerate(context.candidates):
        try:
            before = graph_fingerprint(context)
            score = rule.priority(option, context)
            if graph_fingerprint(context) != before:
                raise GPStateError(GPDiagnostic(GPCode.STATE_MUTATION_DETECTED,
                    "priority rule mutated its read-only context", "context", context.kind.value.lower()))
            if type(score) not in (int, float):
                raise StateError("priority must return a number")
            try:
                option.priority = float(score)
            except OverflowError as exc:
                raise StateError("priority overflow") from exc
            scores.append({"option": list(option.key), "priority": option.priority})
            if index > 0 and is_preferred(option, best):
                best = option
        except Exception as exc:
            if recorder is not None and hasattr(recorder, "decision_error"):
                recorder.decision_error(context, scores, index, option, exc)
            raise
    if recorder is not None:
        recorder.decision(context, scores, best)
    return best


def choose_route(context, rule, recorder=None):
    require(context.kind == RuleKind.ROUTING, "expected routing context")
    return _choose(context, rule, recorder)


def choose_next(context, rule, recorder=None):
    require(context.kind == RuleKind.SEQUENCING, "expected sequencing context")
    return _choose(context, rule, recorder)
