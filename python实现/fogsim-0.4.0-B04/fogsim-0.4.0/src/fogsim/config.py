from dataclasses import dataclass, asdict
from pathlib import Path
from fogsim.errors import InputError
from fogsim.instances.fixed import read_json, object_fields
from fogsim.experiment_config import ExperimentConfig, load_experiment_config, parse_experiment_config
from fogsim.rules.specs import RuleSpec


@dataclass(frozen=True)
class RunConfig:
    routing_kind: str = "fcfs"
    fixed_resource_id: str | None = None
    sequencing_kind: str = "fcfs"
    trace_enabled: bool = True
    event_policy: str = "java_compatible"
    max_events: int = 100000
    check_invariants: bool = True
    routing_expression: str | None = None
    sequencing_expression: str | None = None

    def __post_init__(self):
        RuleSpec("routing", self.routing_kind, self.fixed_resource_id, self.routing_expression)
        RuleSpec("sequencing", self.sequencing_kind, expression=self.sequencing_expression)
        if self.event_policy != "java_compatible":
            raise InputError("only java_compatible event policy is implemented")
        if type(self.max_events) is not int or self.max_events < 1:
            raise InputError("max_events must be a positive integer")
        if type(self.trace_enabled) is not bool or type(self.check_invariants) is not bool:
            raise InputError("trace_enabled/check_invariants must be booleans")

    def to_dict(self):
        result = asdict(self)
        for key in ("routing_expression", "sequencing_expression"):
            if result[key] is None:
                del result[key]
        return result


def load_config(path):
    data = read_json(path)
    object_fields(data, ("instance", "routing_rule", "sequencing_rule"),
                  ("trace_enabled", "event_policy", "max_events", "check_invariants"), "config")
    routing = RuleSpec.from_mapping("routing", data["routing_rule"])
    sequencing = RuleSpec.from_mapping("sequencing", data["sequencing_rule"])
    if not isinstance(data["instance"], str) or not data["instance"]:
        raise InputError("config.instance must be a path string")
    config = RunConfig(
        routing_kind=routing.kind,
        fixed_resource_id=routing.resource_id,
        sequencing_kind=sequencing.kind,
        routing_expression=routing.expression,
        sequencing_expression=sequencing.expression,
        **{k: data[k] for k in ("trace_enabled", "event_policy", "max_events", "check_invariants") if k in data},
    )
    # Explicit, portable contract: instance paths are relative to the configuration file.
    return (Path(path).resolve().parent / data["instance"]).resolve(), config
