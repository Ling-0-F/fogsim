from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import math
from typing import TYPE_CHECKING
from fogsim.errors import require
if TYPE_CHECKING:
    from .task import TaskOption
    from .execution import Execution


class ResourceType(str, Enum):
    MOBILE = "MOBILE"
    EDGE = "EDGE"
    CLOUD = "CLOUD"


@dataclass(eq=False)
class Resource:
    id: str
    numeric_id: int
    resource_type: ResourceType
    available_time: float = 0.0
    waiting_queue: list[TaskOption] = field(default_factory=list)
    queued_processing_time: float = 0.0
    queued_total_time: float = 0.0
    completed_task_count: int = 0
    pending_start: Execution | None = None
    processing_rate: float | None = None

    def enqueue(self, option: TaskOption) -> None:
        # EventContext verifies arrival and absence from the global execution index.
        require(option.resource is self and option.task.dispatched and not option.task.completed,
                f"ineligible queued option {option.key}")
        require(not any(o.task is option.task for o in self.waiting_queue), "duplicate queue entry")
        require(self.pending_start is None or self.pending_start.task is not option.task,
                "reserved task cannot enter queue")
        processing = self.queued_processing_time + option.processing_time
        total = self.queued_total_time + (option.processing_time + option.upload_time + option.download_time)
        require(math.isfinite(processing) and math.isfinite(total), "queue cache overflow")
        self.waiting_queue.append(option)
        self.queued_processing_time = processing
        self.queued_total_time = total

    def remove_waiting(self, option: TaskOption) -> None:
        require(any(o is option for o in self.waiting_queue), "waiting option identity not found")
        self.waiting_queue.remove(option)
        if self.resource_type != ResourceType.MOBILE and not self.waiting_queue:
            self.queued_processing_time = 0.0
            self.queued_total_time = 0.0
        else:
            self.queued_processing_time -= option.processing_time
            self.queued_total_time -= (option.processing_time + option.upload_time + option.download_time)

    @property
    def waiting_processing_time(self):
        if self.resource_type != ResourceType.MOBILE and not self.waiting_queue:
            return 0.0
        return self.queued_processing_time

    @property
    def waiting_total_time(self):
        if self.resource_type != ResourceType.MOBILE and not self.waiting_queue:
            return 0.0
        return self.queued_total_time

    def begin_execution(self, execution: Execution) -> None:
        require(execution.resource is self and self.pending_start is execution,
                f"reservation mismatch on {self.id}")
        require(not execution.task.completed and execution.task.dispatched, "invalid start task")
        self.pending_start = None
        self.available_time = execution.finish_time


@dataclass(eq=False)
class MobileDevice(Resource):
    can_process_tasks: bool = True


@dataclass(eq=False)
class Server(Resource):
    upload_bandwidth: float | None = None
    download_bandwidth: float | None = None
