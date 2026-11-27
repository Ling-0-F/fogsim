from dataclasses import dataclass, asdict
import hashlib
import json
from fogsim.errors import InputError
from fogsim.input_validation import integer, finite, boolean, choice, text, sequence, unique, INT32_MAX


@dataclass(frozen=True)
class DeviceSnapshot:
    id: str
    numeric_id: int
    processing_rate: float
    can_process_tasks: bool

    def __post_init__(self):
        text(self.id, "device.id")
        integer(self.numeric_id, "device.numeric_id", 0, INT32_MAX)
        object.__setattr__(self, "processing_rate", finite(self.processing_rate, "processing_rate", True))
        boolean(self.can_process_tasks, "can_process_tasks")


@dataclass(frozen=True)
class ServerSnapshot:
    id: str
    numeric_id: int
    type: str
    processing_rate: float
    upload_bandwidth: float
    download_bandwidth: float

    def __post_init__(self):
        text(self.id, "server.id")
        integer(self.numeric_id, "server.numeric_id", 0, INT32_MAX)
        choice(self.type, ("EDGE", "CLOUD"), "server.type")
        for key in ("processing_rate", "upload_bandwidth", "download_bandwidth"):
            object.__setattr__(self, key, finite(getattr(self, key), key, True))


@dataclass(frozen=True)
class EnvironmentSnapshot:
    devices: tuple[DeviceSnapshot, ...]
    servers: tuple[ServerSnapshot, ...]
    parameter_source: str

    def __post_init__(self):
        devices = sequence(self.devices, DeviceSnapshot, "devices", True)
        servers = sequence(self.servers, ServerSnapshot, "servers")
        text(self.parameter_source, "parameter_source")
        unique([r.id for r in (*devices, *servers)], "environment.resources")
        if tuple(r.numeric_id for r in devices) != tuple(range(len(devices))):
            raise InputError("device numeric IDs must follow device order")
        if tuple(r.numeric_id for r in servers) != tuple(range(len(servers))):
            raise InputError("server numeric IDs must follow server order")
        if list(servers) != [s for kind in ("EDGE", "CLOUD") for s in servers if s.type == kind]:
            raise InputError("servers must be ordered EDGE then CLOUD")
        if not servers and any(not d.can_process_tasks for d in devices):
            raise InputError("every device must have at least one eligible resource")
        object.__setattr__(self, "devices", devices)
        object.__setattr__(self, "servers", servers)

    @property
    def fingerprint(self):
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def eligible_resource_ids(self, owner_device_id):
        owner = next((d for d in self.devices if d.id == owner_device_id), None)
        if owner is None:
            raise InputError(f"unknown MOBILE owner: {owner_device_id}")
        return ((owner.id,) if owner.can_process_tasks else ()) + tuple(s.id for s in self.servers)
