"""Preparation for future contexts; this module does not create an Engine.

Only RNG state can be saved/restored here. Environment reuse, B continuation,
reset/rerun/rotateSeed and enforcement of run boundaries belong to Context.
"""
from dataclasses import dataclass, field
import hashlib
import json
import math
import platform
import random
from fogsim.errors import InputError
from fogsim.experiment_config import ExperimentConfig
from fogsim.instances.catalog import DagCatalog, load_dax_catalog
from fogsim.seed import SEED_ENCODING, encode_seed
from .samplers import SamplerBundle, make_samplers


@dataclass(frozen=True)
class RngStateSnapshot:
    python_implementation: str
    python_version: str
    native_state: tuple
    seed_encoding: str = SEED_ENCODING

    def __post_init__(self):
        value = self.native_state
        valid = (type(value) is tuple and len(value) == 3 and type(value[0]) is int
                 and type(value[1]) is tuple and all(type(x) is int for x in value[1])
                 and (value[2] is None or (type(value[2]) is float and math.isfinite(value[2]))))
        if not valid:
            raise InputError("RNG snapshot requires immutable native getstate() data")
        if self.seed_encoding != SEED_ENCODING:
            raise InputError("unsupported RNG seed encoding")
        if type(self.python_implementation) is not str or type(self.python_version) is not str:
            raise InputError("RNG snapshot requires Python implementation and version strings")

    @property
    def state_version(self):
        return self.native_state[0]

    @property
    def fingerprint(self):
        payload = json.dumps([self.python_implementation, self.python_version, self.seed_encoding, self.native_state],
                             separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(payload.encode("ascii")).hexdigest()


@dataclass(frozen=True, eq=False)
class RandomInputState:
    public_seed: int
    catalog: DagCatalog
    samplers: SamplerBundle
    rng: random.Random = field(repr=False)

    def __post_init__(self):
        encode_seed(self.public_seed)
        if type(self.catalog) is not DagCatalog or type(self.samplers) is not SamplerBundle:
            raise InputError("random input state requires a catalog and sampler bundle")
        if not isinstance(self.rng, random.Random):
            raise InputError("random input state requires random.Random")

    @property
    def rng_seed_decimal(self):
        return str(encode_seed(self.public_seed))

    def snapshot(self):
        return RngStateSnapshot(platform.python_implementation(), platform.python_version(), self.rng.getstate())

    def restore_rng(self, snapshot):
        """Restore only this RNG, with version guard and rollback on invalid state."""
        if type(snapshot) is not RngStateSnapshot:
            raise InputError("restore_rng requires RngStateSnapshot")
        if (snapshot.python_implementation != platform.python_implementation()
                or snapshot.python_version != platform.python_version()
                or snapshot.state_version != self.rng.VERSION):
            raise InputError("RNG snapshot Python/state version mismatch")
        previous = self.rng.getstate()
        try:
            self.rng.setstate(snapshot.native_state)
        except (ValueError, TypeError, OverflowError) as exc:
            self.rng.setstate(previous)
            raise InputError(f"invalid native RNG state: {exc}") from exc


def prepare_random_input(config: ExperimentConfig) -> RandomInputState:
    """Validate/load every template before constructing exactly one seeded RNG.

    Accepts an expanded single-run dynamic config. No resources, workflows,
    events or statistics are prepared; the returned stream is at its seed origin.
    """
    if type(config) is not ExperimentConfig or config.mode != "dynamic":
        raise InputError("prepare_random_input requires dynamic ExperimentConfig")
    if config.repeat.count != 1 or config.source.seed is None:
        raise InputError("prepare_random_input requires expanded single-run config; call single_run(index)")
    seed = config.source.seed
    encoded = encode_seed(seed)
    catalog = load_dax_catalog(config)
    samplers = make_samplers(config.source.samplers, config.source.workflow_types)
    return RandomInputState(seed, catalog, samplers, random.Random(encoded))
