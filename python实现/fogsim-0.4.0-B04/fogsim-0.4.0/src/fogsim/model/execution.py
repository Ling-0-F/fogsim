from __future__ import annotations
from dataclasses import dataclass, field
import math
from .task import TaskOption
from fogsim.errors import require


@dataclass(eq=False, frozen=True)
class Execution:
    option: TaskOption
    start_time: float
    compute_finish_time: float = field(init=False)
    finish_time: float = field(init=False)

    def __post_init__(self):
        compute = self.start_time + self.option.processing_time
        finish = compute + self.option.download_time
        require(all(math.isfinite(x) and x >= 0 for x in (self.start_time, compute, finish)),
                f"invalid execution time for {self.option.key}")
        # PT > 0 in the input is insufficient: binary64 addition can erase it.
        # Zero-length executions accumulate same-resource Finish events and the
        # original Java queue continuation can then schedule overlapping Starts.
        # Reject before registering a plan; never weaken the reservation guard.
        require(finish > self.start_time,
                f"execution duration lost to floating-point precision for {self.option.key}: "
                f"start={self.start_time!r}, PT={self.option.processing_time!r}, "
                f"DT={self.option.download_time!r}; reduce the time origin or use higher-precision time arithmetic")
        object.__setattr__(self, "compute_finish_time", compute)
        object.__setattr__(self, "finish_time", finish)

    @property
    def task(self):
        return self.option.task

    @property
    def resource(self):
        return self.option.resource

    @property
    def duration(self):
        return self.finish_time - self.start_time
