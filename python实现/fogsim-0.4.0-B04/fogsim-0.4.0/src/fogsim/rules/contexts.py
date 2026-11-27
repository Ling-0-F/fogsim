"""No state/engine back-reference. Reachable models belong only to arrived workflows.

Canonical objects remain shared. A per-call graph guard detects accidental writes;
this API is for trusted Python rules, not a sandbox for hostile Python programs.
"""
from dataclasses import dataclass, fields, is_dataclass
import struct
from .base import RuleKind


@dataclass(frozen=True)
class StateView:
    clock_time: float
    resources: tuple
    active_workflows: tuple
    completed_workflows: tuple

    @classmethod
    def from_state(cls, state):
        return cls(state.clock_time, tuple(state.resources_by_id.values()),
                   tuple(state.active_workflows.values()), tuple(state.completed_workflows.values()))


@dataclass(frozen=True)
class RoutingContext:
    task: object
    candidates: tuple
    view: StateView
    round_number: int = 1
    kind: RuleKind = RuleKind.ROUTING


@dataclass(frozen=True)
class SequencingContext:
    resource: object
    candidates: tuple
    view: StateView
    round_number: int = 1
    kind: RuleKind = RuleKind.SEQUENCING


def graph_fingerprint(root):
    """Capture all reachable fields, identities and collection order without copying models."""
    seen = set()
    def visit(value):
        if isinstance(value, float):
            return ("float", struct.pack(">d", value))
        if value is None or isinstance(value, (str, int, bool)):
            return value
        oid = id(value)
        if oid in seen:
            return ("ref", oid)
        seen.add(oid)
        if is_dataclass(value):
            return (type(value).__name__, oid, tuple((f.name, visit(getattr(value, f.name))) for f in fields(value)))
        if isinstance(value, (list, tuple)):
            return (type(value).__name__, oid, tuple(visit(x) for x in value))
        if isinstance(value, dict):
            return ("dict", oid, tuple((visit(k), visit(v)) for k, v in value.items()))
        raise TypeError(f"unsupported rule-view object: {type(value)}")
    return visit(root)
