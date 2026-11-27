from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from fogsim.errors import StateError
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .workflow import Workflow
    from .resource import Resource


class EdgeDataState(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"
    RETAINED = "RETAINED"
    RELEASED = "RELEASED"


@dataclass(eq=False)
class Task:
    id: str
    workflow: Workflow
    parents: list[Task] = field(default_factory=list)
    children: list[Task] = field(default_factory=list)
    options: list[TaskOption] = field(default_factory=list)
    dispatched: bool = False
    completed: bool = False
    workload: float | None = None
    data_size: float | None = None
    input_data_by_parent: dict[str, float] | None = None
    output_data_by_child: dict[str, float] | None = None
    total_input_data: float | None = None
    total_output_data: float | None = None
    edge_data_state: EdgeDataState = EdgeDataState.UNAVAILABLE
    java_index: int | None = None

    def validate_edge_data(self):
        if self.edge_data_state == EdgeDataState.RETAINED:
            valid = isinstance(self.input_data_by_parent, dict) and isinstance(self.output_data_by_child, dict)
        elif self.edge_data_state in (EdgeDataState.UNAVAILABLE, EdgeDataState.RELEASED):
            valid = self.input_data_by_parent is None and self.output_data_by_child is None
        else:
            valid = False
        if not valid:
            raise StateError(f"inconsistent edge data state for {self.key}")

    def edge_data(self):
        """Return explicit retained maps; missing/released data never means zero."""
        self.validate_edge_data()
        if self.edge_data_state != EdgeDataState.RETAINED:
            raise StateError(f"edge data {self.edge_data_state.value} for {self.key}")
        return self.input_data_by_parent, self.output_data_by_child

    @property
    def key(self):
        return self.workflow.id, self.id


@dataclass(eq=False)
class TaskOption:
    task: Task
    resource: Resource
    processing_time: float
    upload_time: float
    download_time: float
    ready_time: float = 0.0
    priority: float = 0.0

    @property
    def key(self):
        return (*self.task.key, self.resource.id)
