"""Immutable replay description; JSON metadata is stored as immutable text."""
from dataclasses import dataclass
import json
from fogsim.errors import InputError
from fogsim.experiment_config import DynamicRunConfig
from fogsim.instances.generated import InputArchive
from fogsim.input_validation import finite, integer, boolean, choice, text
from fogsim.seed import encode_seed


class ReplayInputError(InputError):
    def __init__(self, message, reason_code="REPLAY_INPUT_INVALID"):
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


@dataclass(frozen=True)
class ReplayInitialState:
    B: float
    public_seed: int
    seed_encoding_version: str
    run_index: int
    rng_seed_decimal: str | None = None

    def __post_init__(self):
        object.__setattr__(self, 'B', finite(self.B, 'initial_state.B'))
        encode_seed(self.public_seed)
        choice(self.seed_encoding_version, ('java-signed64-v1', 'signed64-bits-v1'), 'seed_encoding_version')
        integer(self.run_index, 'run_index')
        if self.rng_seed_decimal is not None and (type(self.rng_seed_decimal) is not str or
                self.rng_seed_decimal != str(encode_seed(self.public_seed))):
            raise InputError('rng_seed_decimal must exactly encode the unsigned64 public seed bit pattern')


@dataclass(frozen=True)
class ReplayCapture:
    complete: bool
    complete_attempt_count: int
    write_interrupted: bool
    process_interrupted: bool
    termination: str

    def __post_init__(self):
        for key in ('complete', 'write_interrupted', 'process_interrupted'):
            boolean(getattr(self, key), 'capture.' + key)
        integer(self.complete_attempt_count, 'complete_attempt_count')
        text(self.termination, 'termination')
        if self.complete and (self.write_interrupted or self.process_interrupted):
            raise InputError('complete capture has interruption flag')

    @property
    def is_complete(self):
        return self.complete and not self.write_interrupted and not self.process_interrupted


@dataclass(frozen=True)
class ReplayInput:
    archive: InputArchive
    initial_state: ReplayInitialState
    capture: ReplayCapture
    run_config: DynamicRunConfig
    document_json: str
    input_sha256: str | None = None

    def __post_init__(self):
        for name, cls in (('archive', InputArchive), ('initial_state', ReplayInitialState),
                          ('capture', ReplayCapture), ('run_config', DynamicRunConfig)):
            if type(getattr(self, name)) is not cls:
                raise InputError(f'{name}: expected {cls.__name__}')
        if self.capture.complete_attempt_count != len(self.archive.generation_attempts):
            raise InputError('capture attempt count mismatch')

    @property
    def schema_version(self):
        return self.to_dict()["schema_version"]

    @property
    def recorded_rule_manifest(self):
        if self.schema_version == 2:
            return self.to_dict()["rule_manifest"]
        from fogsim.rules.factory import install_rules
        return install_rules(self.run_config).rule_manifest

    def to_dict(self):
        """A detached document; mutating it cannot change the replay."""
        return json.loads(self.document_json)
