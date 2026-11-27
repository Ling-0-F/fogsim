from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .resource import MobileDevice
    from .task import Task
    from .execution import Execution


@dataclass(eq=False)
class Workflow:
    id: int
    owner_device: MobileDevice
    release_time: float
    tasks: list[Task] = field(default_factory=list)
    completion_time: float | None = None
    completed_executions: list[Execution] = field(default_factory=list)
    completion_registered: bool = False
    weight: float | None = None
    dag_type_id: int | None = None
    template_hash: str | None = None
    input_record_id: str | None = None

    @property
    def task_count(self):
        return len(self.tasks)

    @property
    def completed_task_count(self):
        return len(self.completed_executions)

    @property
    def is_done(self):
        return all(t.completed for t in self.tasks)

    @property
    def flow_time(self):
        return None if self.completion_time is None else self.completion_time - self.release_time
