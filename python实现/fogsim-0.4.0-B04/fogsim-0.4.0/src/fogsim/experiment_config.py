"""Versioned, pure experiment configuration; does not load inputs or create RNGs.

The fixed-mode RunConfig/load_config contract remains in config.py unchanged.
"""
from dataclasses import dataclass, field, asdict, replace
from pathlib import Path
import hashlib
import json
from fogsim.errors import InputError
from fogsim.instances.fixed import object_fields, read_json
from fogsim.input_validation import integer, finite, boolean, choice, text, INT32_MAX
from fogsim.seed import encode_seed
from fogsim.rules.specs import RuleSpec


@dataclass(frozen=True)
class RealRange:
    lower: float
    upper: float

    def __post_init__(self):
        for key in ("lower", "upper"):
            object.__setattr__(self, key, finite(getattr(self, key), key))
        if self.lower >= self.upper:
            raise InputError("real uniform range requires lower < upper")


@dataclass(frozen=True)
class WorkflowTypeRange:
    lower: int
    upper: int

    def __post_init__(self):
        integer(self.lower, "workflow_types.lower", 0, 19)
        integer(self.upper, "workflow_types.upper", 0, 19)
        if self.lower > self.upper:
            raise InputError("workflow_types requires lower <= upper")


@dataclass(frozen=True)
class SamplerParameters:
    workload: RealRange = field(default_factory=lambda: RealRange(5000, 15000))
    data_size: RealRange = field(default_factory=lambda: RealRange(5120, 20480))
    edge_data: RealRange = field(default_factory=lambda: RealRange(100, 200))
    processing_rate_device: RealRange = field(default_factory=lambda: RealRange(125, 250))
    processing_rate_edge: RealRange = field(default_factory=lambda: RealRange(250, 500))
    processing_rate_cloud: RealRange = field(default_factory=lambda: RealRange(500, 1000))
    inter_release_mean: float = 100.0
    weight_profile: str = "two_six_two"
    cloud_bandwidth_profile: str = "bandwidth_cloud"
    edge_bandwidth: float = 1024.0

    def __post_init__(self):
        for key in RANGE_FIELDS:
            value = getattr(self, key)
            if type(value) is not RealRange:
                raise InputError(f"samplers.{key}: expected RealRange")
            if key not in ("data_size", "edge_data") and value.lower <= 0:
                raise InputError(f"samplers.{key}: lower bound must be positive")
        for key, expected in (("inter_release_mean", 100.0), ("edge_bandwidth", 1024.0)):
            value = finite(getattr(self, key), key, True)
            if value != expected:
                raise InputError(f"java_legacy profile requires {key}={expected}")
            object.__setattr__(self, key, value)
        choice(self.weight_profile, ("two_six_two",), "weight_profile")
        choice(self.cloud_bandwidth_profile, ("bandwidth_cloud",), "cloud_bandwidth_profile")

    def effective_parameters(self):
        """Include fixed distributions explicitly in fingerprints/recorded config."""
        return dict(asdict(self), distributions={
            "real_uniform": "reject-zero-java-scaling-v1",
            "workflow_type": "randint-inclusive",
            "inter_release": {"family": "exponential", "mean": self.inter_release_mean},
            "weight": {"values": [4, 2, 1], "thresholds": [0.2, 0.8]},
            "cloud_bandwidth": {"values": [256, 512, 128], "thresholds": [0.2, 0.8]},
            "edge_bandwidth": {"family": "constant", "value": self.edge_bandwidth},
        })


RANGE_FIELDS = ("workload", "data_size", "edge_data", "processing_rate_device",
                "processing_rate_edge", "processing_rate_cloud")
SAMPLER_FIELDS = (*RANGE_FIELDS, "inter_release_mean", "weight_profile",
                  "cloud_bandwidth_profile", "edge_bandwidth")


@dataclass(frozen=True)
class EnvironmentConfig:
    num_mobile_devices: int
    num_edge_servers: int
    num_cloud_servers: int
    can_mobile_devices_process_tasks: bool

    def __post_init__(self):
        integer(self.num_mobile_devices, "num_mobile_devices", 1, INT32_MAX)
        integer(self.num_edge_servers, "num_edge_servers", 0, INT32_MAX)
        integer(self.num_cloud_servers, "num_cloud_servers", 0, INT32_MAX)
        boolean(self.can_mobile_devices_process_tasks, "can_mobile_devices_process_tasks")
        if self.num_edge_servers + self.num_cloud_servers > INT32_MAX:
            raise InputError("combined server count exceeds int32")
        if not self.can_mobile_devices_process_tasks and not (self.num_edge_servers + self.num_cloud_servers):
            raise InputError("no eligible resource: local processing disabled and no servers")

    def is_eligible_for_all(self, resource_id):
        # Membership in the standard generator's names only. Runtime numeric IDs
        # still come exclusively from ordered identity maps (also for custom IDs).
        for prefix, count in (("E", self.num_edge_servers), ("C", self.num_cloud_servers)):
            if type(resource_id) is str and resource_id.startswith(prefix):
                suffix = resource_id[len(prefix):]
                if len(suffix) <= 10 and suffix.isascii() and suffix.isdecimal():
                    index = int(suffix)
                    return resource_id == f"{prefix}{index}" and index < count
        return (self.can_mobile_devices_process_tasks and self.num_mobile_devices == 1
                and resource_id == "M0")


@dataclass(frozen=True)
class RuleConfig:
    kind: str = "fcfs"
    resource_id: str | None = None
    expression: str | None = None

    def __post_init__(self):
        RuleSpec("routing", self.kind, self.resource_id, self.expression)

    def to_dict(self):
        return RuleSpec("routing", self.kind, self.resource_id, self.expression).to_dict()


def _diagnostics(config):
    if config.max_events is not None:
        integer(config.max_events, "max_events", 1)
    boolean(config.check_invariants, "check_invariants")
    boolean(config.trace_enabled, "trace_enabled")
    choice(config.edge_data_policy, ("retain", "release_after_materialization"), "edge_data_policy")


@dataclass(frozen=True)
class DynamicRunConfig:
    num_jobs_recorded: int
    warmup_jobs: int
    statistics_policy: str = "java_legacy"
    failure_policy: str = "explicit_failure"
    event_policy: str = "java_compatible"
    routing_rule: RuleConfig = field(default_factory=RuleConfig)
    sequencing_rule: RuleConfig = field(default_factory=RuleConfig)
    max_events: int | None = None
    check_invariants: bool = True
    trace_enabled: bool = True
    edge_data_policy: str = "retain"

    def __post_init__(self):
        integer(self.num_jobs_recorded, "num_jobs_recorded", 1, INT32_MAX // 500)
        integer(self.warmup_jobs, "warmup_jobs", 0, INT32_MAX // 500)
        if self.num_jobs_recorded + self.warmup_jobs > INT32_MAX // 500:
            raise InputError("num_jobs_recorded + warmup_jobs exceeds floor(INT32_MAX/500)")
        choice(self.statistics_policy, ("java_legacy",), "statistics_policy")
        choice(self.failure_policy, ("explicit_failure",), "failure_policy")
        choice(self.event_policy, ("java_compatible",), "event_policy")
        _rules(self.routing_rule, self.sequencing_rule)
        _diagnostics(self)


def _rules(routing, sequencing):
    if type(routing) is not RuleConfig or type(sequencing) is not RuleConfig:
        raise InputError("routing_rule/sequencing_rule: expected RuleConfig")
    RuleSpec.from_mapping("routing", routing.to_dict())
    RuleSpec.from_mapping("sequencing", sequencing.to_dict())


@dataclass(frozen=True)
class ReplayRunOptions:
    max_events: int | None = None
    check_invariants: bool = True
    trace_enabled: bool = True
    edge_data_policy: str = "retain"
    routing_rule: RuleConfig | None = None
    sequencing_rule: RuleConfig | None = None

    def __post_init__(self):
        _diagnostics(self)
        if self.routing_rule is not None and type(self.routing_rule) is not RuleConfig:
            raise InputError("routing_rule: expected RuleConfig")
        if self.sequencing_rule is not None:
            _rules(self.routing_rule or RuleConfig(), self.sequencing_rule)


def _absolute_path(path, where):
    if not isinstance(path, Path) or not path.is_absolute():
        raise InputError(f"{where}: use absolute Path or parse_experiment_config(base_dir=...)")


@dataclass(frozen=True)
class DynamicSourceConfig:
    dag_root: Path
    workflow_types: WorkflowTypeRange
    environment: EnvironmentConfig
    seed: int | None = None
    samplers: SamplerParameters = field(default_factory=SamplerParameters)

    def __post_init__(self):
        _absolute_path(self.dag_root, "dag_root")
        if type(self.workflow_types) is not WorkflowTypeRange or type(self.environment) is not EnvironmentConfig:
            raise InputError("source requires WorkflowTypeRange and EnvironmentConfig")
        if type(self.samplers) is not SamplerParameters:
            raise InputError("source.samplers: expected SamplerParameters")
        if self.seed is not None:
            encode_seed(self.seed)


@dataclass(frozen=True)
class ReplaySourceConfig:
    input_path: Path
    purpose: str = "verify_reference"
    reference_path: Path | None = None

    def __post_init__(self):
        _absolute_path(self.input_path, "input_path")
        choice(self.purpose, ("verify_reference", "reuse_inputs"), "purpose")
        if self.reference_path is not None:
            _absolute_path(self.reference_path, "reference_path")
        if self.purpose == "verify_reference" and self.reference_path is None:
            raise InputError("verify_reference requires reference_path; input-only runs use reuse_inputs")


@dataclass(frozen=True)
class RepeatConfig:
    count: int = 1
    mode: str | None = None
    seeds: tuple[int, ...] | None = None

    def __post_init__(self):
        integer(self.count, "repeat.count", 1)
        if self.mode is not None:
            choice(self.mode, ("fresh_same_seed", "fresh_seed_list", "java_rerun", "same_input"), "repeat.mode")
        if self.mode == "fresh_seed_list":
            if type(self.seeds) not in (list, tuple) or len(self.seeds) != self.count:
                raise InputError("fresh_seed_list requires exactly repeat.count seeds")
            for seed in self.seeds:
                encode_seed(seed)
            object.__setattr__(self, "seeds", tuple(self.seeds))
        elif self.seeds is not None:
            raise InputError("repeat.seeds is only valid for fresh_seed_list")


@dataclass(frozen=True)
class OutputConfig:
    dataset_role: str = "debug"

    def __post_init__(self):
        choice(self.dataset_role, ("debug", "train", "test"), "dataset_role")


@dataclass(frozen=True)
class ExperimentConfig:
    mode: str
    source: DynamicSourceConfig | ReplaySourceConfig
    run: DynamicRunConfig | ReplayRunOptions
    repeat: RepeatConfig = field(default_factory=RepeatConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    format: str = "fogsim.experiment"
    schema_version: int = 1

    def __post_init__(self):
        choice(self.mode, ("dynamic", "replay"), "mode")
        choice(self.format, ("fogsim.experiment",), "format")
        integer(self.schema_version, "schema_version", 1, 2)
        if self.schema_version == 1 and any(getattr(self.run, k, None) is not None
                and getattr(self.run, k).kind == "gp" for k in ("routing_rule", "sequencing_rule")):
            raise InputError("schema_version=1 rejects GP rules")
        if type(self.repeat) is not RepeatConfig or type(self.output) is not OutputConfig:
            raise InputError("repeat/output: expected typed configuration")
        repeat = self.repeat
        if self.mode == "dynamic":
            if type(self.source) is not DynamicSourceConfig or type(self.run) is not DynamicRunConfig:
                raise InputError("dynamic requires DynamicSourceConfig and DynamicRunConfig")
            if repeat.count > 1 and repeat.mode is None:
                raise InputError("dynamic repeat.count > 1 requires explicit repeat.mode")
            if repeat.mode == "same_input":
                raise InputError("dynamic cannot repeat same input; use recorded replay")
            if repeat.mode == "fresh_seed_list":
                if self.source.seed is not None and self.source.seed != repeat.seeds[0]:
                    raise InputError("source.seed must equal repeat.seeds[0] when both are supplied")
            elif self.source.seed is None:
                raise InputError("dynamic source.seed is required outside fresh_seed_list")
            rule = self.run.routing_rule
            if rule.kind == "fixed_resource" and not self.source.environment.is_eligible_for_all(rule.resource_id):
                raise InputError("fixed_resource target must be eligible for every device")
            if repeat.mode is None:
                object.__setattr__(self, "repeat", replace(repeat, mode="fresh_same_seed"))
        else:
            if type(self.source) is not ReplaySourceConfig or type(self.run) is not ReplayRunOptions:
                raise InputError("replay requires ReplaySourceConfig and ReplayRunOptions")
            if repeat.mode not in (None, "same_input"):
                raise InputError("replay repeat means independent runs from the same input start")
            if self.source.purpose == "verify_reference" and (self.run.routing_rule or self.run.sequencing_rule):
                raise InputError("rule overrides require replay purpose=reuse_inputs")
            object.__setattr__(self, "repeat", replace(repeat, mode="same_input"))

    def to_dict(self):
        def convert(value):
            if isinstance(value, Path):
                return str(value)
            if isinstance(value, dict):
                return {k: convert(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [convert(v) for v in value]
            return value
        result = convert(asdict(self))
        for key in ("routing_rule", "sequencing_rule"):
            rule = result["run"][key]
            if rule is not None:
                if rule["expression"] is None:
                    del rule["expression"]
                else:
                    del rule["resource_id"]
        # Keep this normalized config parseable by the strict loader.
        if self.schema_version == 2:
            for role in ("routing", "sequencing"):
                rule = getattr(self.run, role + "_rule")
                if rule is not None:
                    result["run"][role + "_rule"] = rule.to_dict()
        if result["repeat"]["seeds"] is None:
            del result["repeat"]["seeds"]
        if self.mode == "dynamic" and result["source"]["seed"] is None:
            del result["source"]["seed"]
        if self.mode == "replay":
            if result["source"]["reference_path"] is None:
                del result["source"]["reference_path"]
            for key in ("routing_rule", "sequencing_rule"):
                if result["run"][key] is None:
                    del result["run"][key]
        return result

    def effective_parameters(self):
        result = self.to_dict()
        if self.mode == "dynamic":
            result["source"]["samplers"] = self.source.samplers.effective_parameters()
        return result

    @property
    def fingerprint(self):
        payload = json.dumps(self.effective_parameters(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def single_run(self, index=0):
        """Expand one plan row; experiments.runner owns lifecycle orchestration."""
        integer(index, "run index", 0, self.repeat.count - 1)
        if self.mode == "replay":
            return replace(self, repeat=RepeatConfig(mode="same_input"))
        seed = self.repeat.seeds[index] if self.repeat.mode == "fresh_seed_list" else self.source.seed
        return replace(self, source=replace(self.source, seed=seed), repeat=RepeatConfig(mode="fresh_same_seed"))


def _path(value, base_dir, where):
    text(value, where)
    path = Path(value)
    if not path.is_absolute():
        if base_dir is None:
            raise InputError(f"{where}: relative path requires explicit base_dir")
        path = Path(base_dir) / path
    return path.resolve()


def _rule(value, role, version):
    if version == 1:
        object_fields(value, ("kind",), ("resource_id",), "rule")
        if value["kind"] == "gp":
            raise InputError("schema_version=1 rejects GP rules")
        return RuleConfig(**value)
    spec = RuleSpec.from_mapping(role, value, field_path=f"run.{role}_rule")
    return RuleConfig(spec.kind, spec.resource_id, spec.expression)


def parse_experiment_config(data, *, base_dir=None) -> ExperimentConfig:
    object_fields(data, ("format", "schema_version", "mode", "source"), ("run", "repeat", "output"), "experiment")
    choice(data["format"], ("fogsim.experiment",), "format")
    integer(data["schema_version"], "schema_version", 1, 2)
    choice(data["mode"], ("dynamic", "replay"), "mode")
    source, run = data["source"], data.get("run", {})
    if data["mode"] == "dynamic":
        object_fields(source, ("dag_root", "workflow_types", "environment"), ("seed", "samplers"), "source")
        if "seed" in source:
            encode_seed(source["seed"])
        object_fields(source["workflow_types"], ("lower", "upper"), where="workflow_types")
        object_fields(source["environment"], ("num_mobile_devices", "num_edge_servers", "num_cloud_servers",
                      "can_mobile_devices_process_tasks"), where="environment")
        sampler_data = source.get("samplers", {})
        object_fields(sampler_data, (), SAMPLER_FIELDS, "samplers")
        samplers = {}
        for key, value in sampler_data.items():
            if key in RANGE_FIELDS:
                object_fields(value, ("lower", "upper"), where=f"samplers.{key}")
                value = RealRange(**value)
            samplers[key] = value
        source_cfg = DynamicSourceConfig(
            _path(source["dag_root"], base_dir, "dag_root"), WorkflowTypeRange(**source["workflow_types"]),
            EnvironmentConfig(**source["environment"]), source.get("seed"), SamplerParameters(**samplers))
        required = ("num_jobs_recorded", "warmup_jobs")
        optional = ("statistics_policy", "failure_policy", "event_policy", "routing_rule", "sequencing_rule",
                    "max_events", "check_invariants", "trace_enabled", "edge_data_policy")
        object_fields(run, required, optional, "run")
        run_type = DynamicRunConfig
    else:
        object_fields(source, ("input_path",), ("reference_path", "purpose"), "source")
        source_cfg = ReplaySourceConfig(_path(source["input_path"], base_dir, "input_path"),
            source.get("purpose", "verify_reference"),
            _path(source["reference_path"], base_dir, "reference_path") if "reference_path" in source else None)
        object_fields(run, (), ("max_events", "check_invariants", "trace_enabled", "edge_data_policy",
                                "routing_rule", "sequencing_rule"), "run")
        run_type = ReplayRunOptions
    run_values = {key: (_rule(value, key.removesuffix("_rule"), data["schema_version"]) if key in ("routing_rule", "sequencing_rule") else value)
                  for key, value in run.items()}
    repeat = data.get("repeat", {})
    output = data.get("output", {})
    object_fields(repeat, (), ("count", "mode", "seeds"), "repeat")
    if "seeds" in repeat and repeat.get("mode") != "fresh_seed_list":
        raise InputError("repeat.seeds is only valid for fresh_seed_list")
    object_fields(output, (), ("dataset_role",), "output")
    return ExperimentConfig(data["mode"], source_cfg, run_type(**run_values), RepeatConfig(**repeat), OutputConfig(**output),
                            schema_version=data["schema_version"])


def load_experiment_config(path) -> ExperimentConfig:
    return parse_experiment_config(read_json(path), base_dir=Path(path).resolve().parent)
