"""Immutable, ordered input descriptions, reusable across independent runs."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceSpec:
    id: str
    type: str
    can_process_tasks: bool = True


@dataclass(frozen=True)
class OptionSpec:
    resource_id: str
    upload_time: float
    processing_time: float
    download_time: float


@dataclass(frozen=True)
class TaskSpec:
    id: str
    options: tuple[OptionSpec, ...]


@dataclass(frozen=True)
class WorkflowSpec:
    id: int
    owner_device_id: str
    release_time: float
    tasks: tuple[TaskSpec, ...]
    dependencies: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class InstanceSpec:
    resources: tuple[ResourceSpec, ...]
    workflows: tuple[WorkflowSpec, ...]
    time_unit: str = "s"

    def to_dict(self) -> dict:
        return {
            "time_unit": self.time_unit,
            "resources": [dict(id=r.id, type=r.type, **(
                {"can_process_tasks": r.can_process_tasks} if r.type == "MOBILE" else {}
            )) for r in self.resources],
            "workflows": [{
                "id": w.id, "owner_device_id": w.owner_device_id,
                "release_time": w.release_time,
                "tasks": [{"id": t.id, "execution_times": {
                    o.resource_id: dict(upload_time=o.upload_time,
                        processing_time=o.processing_time, download_time=o.download_time)
                    for o in t.options}} for t in w.tasks],
                "dependencies": [list(e) for e in w.dependencies],
            } for w in self.workflows],
        }
