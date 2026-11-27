"""Java-compatible compare branches and offer/poll, without stable tie keys.

Reference: OpenJDK jdk17u tag jdk-17.0.16+8 PriorityQueue, siftUpComparable /
siftDownComparable. See docs/JAVA-REFERENCE.md for evidence and limitations.
"""
import math
from fogsim.errors import require
from fogsim.model.resource import ResourceType
from .events import JobArrivalEvent, TaskVisitEvent, ProcessStartEvent, ProcessFinishEvent


def compare_event_java(a, b):
    if a.time < b.time:
        return -1
    if a.time > b.time:
        return 1
    if isinstance(a, JobArrivalEvent):
        if isinstance(b, JobArrivalEvent) and a.workflow.id > b.workflow.id:
            return 1
        return -1  # Includes equal job IDs, intentionally.
    if isinstance(a, ProcessStartEvent):
        if isinstance(b, ProcessStartEvent):
            return 0
        return -1 if isinstance(b, (TaskVisitEvent, ProcessFinishEvent)) else 1
    if isinstance(a, TaskVisitEvent):
        if isinstance(b, TaskVisitEvent):
            return 0
        return 1 if isinstance(b, (JobArrivalEvent, ProcessStartEvent)) else -1
    if isinstance(a, ProcessFinishEvent):
        if isinstance(b, ProcessFinishEvent):
            ar, br = a.execution.resource, b.execution.resource
            al, bl = ar.resource_type == ResourceType.MOBILE, br.resource_type == ResourceType.MOBILE
            if al != bl:
                return -1 if al else 1
            ai = a.owner.numeric_id if al else ar.numeric_id
            bi = b.owner.numeric_id if bl else br.numeric_id
            if ai < bi:
                return -1
        return 1  # Includes equal finish IDs, intentionally.
    raise TypeError(f"unsupported event {type(a)}")


class JavaPriorityQueue:
    def __init__(self, compare):
        self.compare = compare
        self._items = []

    def __len__(self):
        return len(self._items)

    def snapshot(self):
        return tuple(self._items)

    def offer(self, item):
        k = len(self._items)
        self._items.append(item)
        while k > 0:
            parent = (k - 1) >> 1
            value = self._items[parent]
            if self.compare(item, value) >= 0:
                break
            self._items[k] = value
            k = parent
        self._items[k] = item

    def poll(self):
        if not self._items:
            return None
        result = self._items[0]
        item = self._items.pop()
        size = len(self._items)
        if size:
            k, half = 0, size >> 1
            while k < half:
                child = (k << 1) + 1
                value = self._items[child]
                right = child + 1
                if right < size and self.compare(value, self._items[right]) > 0:
                    child, value = right, self._items[right]
                if self.compare(item, value) <= 0:
                    break
                self._items[k] = value
                k = child
            self._items[k] = item
        return result


class EventQueue:
    def __init__(self, devices):
        self.devices = tuple(devices)
        self.global_heap = JavaPriorityQueue(compare_event_java)
        self.staging_heaps = {d: JavaPriorityQueue(compare_event_java) for d in self.devices}
        self._producer = {}

    def stage(self, event, staging_device):
        require(staging_device in self.staging_heaps and event.owner in self.staging_heaps,
                "foreign event owner/staging device")
        require(math.isfinite(event.time) and event.time >= 0, "invalid event time")
        require(event not in self._producer, "same event object already queued")
        self._producer[event] = staging_device
        self.staging_heaps[staging_device].offer(event)

    def merge_staging(self):
        for device in self.devices:
            heap = self.staging_heaps[device]
            while heap:
                self.global_heap.offer(heap.poll())

    def poll_global(self):
        return self.global_heap.poll()

    def pop_next(self):
        self.merge_staging()
        return self.poll_global()

    def consume_producer(self, event):
        return self._producer.pop(event)

    def has_pending(self):
        return bool(self.global_heap) or any(bool(h) for h in self.staging_heaps.values())

    def pending_events(self):
        return self.global_heap.snapshot() + tuple(e for h in self.staging_heaps.values() for e in h.snapshot())

    def check_reservations(self, resources):
        events = self.pending_events()
        for r in resources:
            starts = [e for e in events if isinstance(e, ProcessStartEvent) and e.execution.resource is r]
            require(len(starts) == (1 if r.pending_start is not None else 0), "reservation/start event count mismatch")
            if starts:
                require(starts[0].execution is r.pending_start, "reservation/start identity mismatch")
