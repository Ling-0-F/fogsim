from enum import Enum
from typing import Protocol


class RuleKind(str, Enum):
    ROUTING = "ROUTING"
    SEQUENCING = "SEQUENCING"


class PriorityRule(Protocol):
    """Rules must only read candidates/context. Selectors own priority writes."""
    def priority(self, option, context) -> float: ...
