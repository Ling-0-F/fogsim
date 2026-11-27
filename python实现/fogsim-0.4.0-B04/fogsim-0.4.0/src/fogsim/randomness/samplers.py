"""Parameter-only samplers; the caller supplies the one shared input RNG.

Constructing or cloning a sampler does not create, draw from, reset or clone RNGs.
"""
from dataclasses import dataclass, fields, replace
import math
from typing import Protocol
from fogsim.errors import InputError
from fogsim.input_validation import integer
from fogsim.experiment_config import SamplerParameters, WorkflowTypeRange


class InputRng(Protocol):
    def random(self) -> float: ...
    def randint(self, lower: int, upper: int) -> int: ...
    def expovariate(self, rate: float) -> float: ...


def _finite_real(value, where):
    if type(value) not in (int, float):
        raise InputError(f"{where}: expected real number, not bool/string")
    try:
        result = float(value)
    except OverflowError as exc:
        raise InputError(f"{where}: binary64 overflow") from exc
    if not math.isfinite(result):
        raise InputError(f"{where}: expected finite real number")
    return result


def _open_unit(rng):
    value = rng.random()
    while value == 0.0:
        value = rng.random()
    return value


@dataclass(frozen=True, slots=True)
class UniformRealSampler:
    lower: float
    upper: float

    def __post_init__(self):
        object.__setattr__(self, "lower", _finite_real(self.lower, "uniform.lower"))
        object.__setattr__(self, "upper", _finite_real(self.upper, "uniform.upper"))
        if self.lower >= self.upper:
            raise InputError("real uniform requires lower < upper")

    def sample(self, rng: InputRng) -> float:
        u = _open_unit(rng)
        # Preserve Java scaling parentheses; do not clamp or redraw rounded endpoints.
        return u * self.upper + (1.0 - u) * self.lower

    def clone(self):
        return replace(self)


@dataclass(frozen=True, slots=True)
class UniformIntegerSampler:
    lower: int
    upper: int

    def __post_init__(self):
        integer(self.lower, "integer.lower", -(1 << 31), (1 << 31) - 1)
        integer(self.upper, "integer.upper", -(1 << 31), (1 << 31) - 1)
        if self.lower > self.upper:
            raise InputError("integer uniform requires lower <= upper")

    def sample(self, rng: InputRng) -> int:
        return rng.randint(self.lower, self.upper)  # singleton ranges still draw

    def clone(self):
        return replace(self)


@dataclass(frozen=True, slots=True)
class ExponentialSampler:
    mean: float

    def __post_init__(self):
        value = _finite_real(self.mean, "exponential.mean")
        if value <= 0:
            raise InputError("exponential mean must be positive")
        object.__setattr__(self, "mean", value)

    def sample(self, rng: InputRng) -> float:
        return rng.expovariate(1.0 / self.mean)  # zero is allowed, with no retry/epsilon

    def clone(self):
        return replace(self)


@dataclass(frozen=True, slots=True)
class WeightSampler:
    def sample(self, rng: InputRng) -> float:
        u = _open_unit(rng)
        return 4.0 if u < 0.2 else 2.0 if u < 0.8 else 1.0

    def clone(self):
        return type(self)()


@dataclass(frozen=True, slots=True)
class CloudBandwidthSampler:
    def sample(self, rng: InputRng) -> float:
        u = _open_unit(rng)
        return 256.0 if u < 0.2 else 512.0 if u < 0.8 else 128.0

    def clone(self):
        return type(self)()


@dataclass(frozen=True, slots=True)
class EdgeBandwidthSampler:
    def sample(self, rng: InputRng) -> float:
        return 1024.0

    def clone(self):
        return type(self)()


@dataclass(frozen=True, slots=True)
class SamplerBundle:
    workflow_type: UniformIntegerSampler
    inter_release_time: ExponentialSampler
    weight: WeightSampler
    workload: UniformRealSampler
    data_size: UniformRealSampler
    edge_data: UniformRealSampler
    processing_rate_device: UniformRealSampler
    processing_rate_edge: UniformRealSampler
    processing_rate_cloud: UniformRealSampler
    upload_bandwidth_edge: EdgeBandwidthSampler
    download_bandwidth_edge: EdgeBandwidthSampler
    upload_bandwidth_cloud: CloudBandwidthSampler
    download_bandwidth_cloud: CloudBandwidthSampler

    def __post_init__(self):
        expected = {
            "workflow_type": UniformIntegerSampler, "inter_release_time": ExponentialSampler,
            "weight": WeightSampler, "upload_bandwidth_edge": EdgeBandwidthSampler,
            "download_bandwidth_edge": EdgeBandwidthSampler, "upload_bandwidth_cloud": CloudBandwidthSampler,
            "download_bandwidth_cloud": CloudBandwidthSampler,
        }
        for item in fields(self):
            if type(getattr(self, item.name)) is not expected.get(item.name, UniformRealSampler):
                raise InputError(f"sampler bundle: wrong sampler for {item.name}")
        if self.upload_bandwidth_cloud is self.download_bandwidth_cloud or self.upload_bandwidth_edge is self.download_bandwidth_edge:
            raise InputError("upload/download must be separate sampler roles")

    def clone(self):
        return type(self)(**{item.name: getattr(self, item.name).clone() for item in fields(self)})


def make_samplers(parameters: SamplerParameters, workflow_types: WorkflowTypeRange) -> SamplerBundle:
    if type(parameters) is not SamplerParameters or type(workflow_types) is not WorkflowTypeRange:
        raise InputError("make_samplers requires frozen SamplerParameters and WorkflowTypeRange")
    real_roles = {}
    for name in ("workload", "data_size", "edge_data", "processing_rate_device", "processing_rate_edge", "processing_rate_cloud"):
        bounds = getattr(parameters, name)
        real_roles[name] = UniformRealSampler(bounds.lower, bounds.upper)
    return SamplerBundle(
        workflow_type=UniformIntegerSampler(workflow_types.lower, workflow_types.upper),
        inter_release_time=ExponentialSampler(parameters.inter_release_mean), weight=WeightSampler(),
        **real_roles,
        upload_bandwidth_edge=EdgeBandwidthSampler(), download_bandwidth_edge=EdgeBandwidthSampler(),
        upload_bandwidth_cloud=CloudBandwidthSampler(), download_bandwidth_cloud=CloudBandwidthSampler())
