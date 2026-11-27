"""Ordered environment sampling and fresh canonical resource construction."""
from fogsim.errors import InputError
from fogsim.experiment_config import EnvironmentConfig
from fogsim.input_validation import text
from fogsim.model.resource import MobileDevice, Server, ResourceType
from fogsim.numerics import checked_number
from fogsim.randomness.state import RandomInputState
from fogsim.simulation.state import SystemState
from .spec import DeviceSnapshot, ServerSnapshot, EnvironmentSnapshot


def sample_environment(config: EnvironmentConfig, inputs: RandomInputState, *, parameter_source: str) -> EnvironmentSnapshot:
    """Devices first, then EDGE and CLOUD, sharing inputs.rng with generation.

    This always samples a device's rate, even when local execution is disabled.
    There is no first-workflow generation, registration or event side effect.
    """
    if type(config) is not EnvironmentConfig or type(inputs) is not RandomInputState:
        raise InputError("sample_environment requires EnvironmentConfig and RandomInputState")
    text(parameter_source, "parameter_source")
    samplers, rng = inputs.samplers, inputs.rng
    devices = []
    for index in range(config.num_mobile_devices):
        rate = checked_number(samplers.processing_rate_device.sample(rng), f"M{index}.processing_rate", positive=True)
        devices.append(DeviceSnapshot(f"M{index}", index, rate, config.can_mobile_devices_process_tasks))
    servers = []
    for kind, prefix, count, upload, download, processing in (
        ("EDGE", "E", config.num_edge_servers, samplers.upload_bandwidth_edge,
         samplers.download_bandwidth_edge, samplers.processing_rate_edge),
        ("CLOUD", "C", config.num_cloud_servers, samplers.upload_bandwidth_cloud,
         samplers.download_bandwidth_cloud, samplers.processing_rate_cloud),
    ):
        for index in range(count):
            rid = f"{prefix}{index}"
            up = checked_number(upload.sample(rng), f"{rid}.upload_bandwidth", positive=True)
            down = checked_number(download.sample(rng), f"{rid}.download_bandwidth", positive=True)
            rate = checked_number(processing.sample(rng), f"{rid}.processing_rate", positive=True)
            servers.append(ServerSnapshot(rid, len(servers), kind, rate, up, down))
    return EnvironmentSnapshot(tuple(devices), tuple(servers), parameter_source)


def build_environment(snapshot: EnvironmentSnapshot) -> SystemState:
    """Build a fresh empty state, preserving values but sharing no runtime objects."""
    if type(snapshot) is not EnvironmentSnapshot:
        raise InputError("build_environment requires EnvironmentSnapshot")
    state = SystemState()
    for device in snapshot.devices:
        resource = MobileDevice(device.id, device.numeric_id, ResourceType.MOBILE,
                                processing_rate=device.processing_rate, can_process_tasks=device.can_process_tasks)
        state.mobile_devices.append(resource)
        state.resources_by_id[resource.id] = resource
    for server in snapshot.servers:
        resource = Server(server.id, server.numeric_id, ResourceType(server.type), processing_rate=server.processing_rate,
                          upload_bandwidth=server.upload_bandwidth, download_bandwidth=server.download_bandwidth)
        state.servers.append(resource)
        state.resources_by_id[resource.id] = resource
    state.check_invariants()
    return state
