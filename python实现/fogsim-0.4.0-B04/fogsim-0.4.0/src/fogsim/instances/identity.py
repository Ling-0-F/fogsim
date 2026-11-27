"""Explicit identities: list positions, never numeric suffixes or sorting."""
from dataclasses import dataclass
from fogsim.input_validation import text, unique, choice, integer


@dataclass(frozen=True)
class ResourceIdentity:
    id: str
    type: str
    numeric_id: int

    def __post_init__(self):
        text(self.id, "resource.id")
        choice(self.type, ("MOBILE", "EDGE", "CLOUD"), "resource.type")
        integer(self.numeric_id, "resource.numeric_id")


def resource_identities(resources) -> tuple[ResourceIdentity, ...]:
    """Input order preserved; devices and EDGE-then-CLOUD have separate spaces."""
    resources = tuple(resources)
    for resource in resources:
        text(resource.id, "resource.id")
        choice(resource.type, ("MOBILE", "EDGE", "CLOUD"), "resource.type")
    unique([r.id for r in resources], "resources")
    numeric = {}
    for kinds in (("MOBILE",), ("EDGE", "CLOUD")):
        ordered = [r for kind in kinds for r in resources if r.type == kind]
        numeric.update((r.id, index) for index, r in enumerate(ordered))
    return tuple(ResourceIdentity(r.id, r.type, numeric[r.id]) for r in resources)


def task_identities(task_ids) -> tuple[tuple[str, int], ...]:
    """Ordered XML/string-ID to Java-position mapping, scoped to one workflow."""
    ids = tuple(task_ids)
    for tid in ids:
        text(tid, "task.id")
    unique(ids, "tasks")
    return tuple((tid, index) for index, tid in enumerate(ids))
