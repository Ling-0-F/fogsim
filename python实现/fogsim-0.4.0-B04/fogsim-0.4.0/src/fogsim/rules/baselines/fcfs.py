from dataclasses import dataclass
from fogsim.rules.base import RuleKind


@dataclass(frozen=True)
class FCFS:
    def priority(self, option, context):
        if context.kind == RuleKind.ROUTING:
            return option.resource.available_time
        return option.task.workflow.release_time


@dataclass(frozen=True)
class FixedResource:
    """Debug rule only; not a baseline algorithm from the paper."""
    resource_id: str

    def priority(self, option, context):
        return 0.0 if option.resource.id == self.resource_id else 1.0
