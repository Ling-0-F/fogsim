"""Pure validation shared by the new input contracts; no I/O or random state."""
import math
import re
from fogsim.errors import InputError

INT32_MAX = (1 << 31) - 1
SIGNED64_MIN = -(1 << 63)
SIGNED64_MAX = (1 << 63) - 1


def integer(value, where, lower=0, upper=None):
    if type(value) is not int or value < lower or (upper is not None and value > upper):
        raise InputError(f"{where}: expected integer in [{lower}, {upper}]")
    return value


def finite(value, where, positive=False):
    if type(value) not in (int, float):
        raise InputError(f"{where}: expected real number, not bool/string")
    try:
        result = float(value)
    except OverflowError as exc:
        raise InputError(f"{where}: binary64 overflow") from exc
    if not math.isfinite(result) or (result <= 0 if positive else result < 0):
        raise InputError(f"{where}: expected finite {'positive' if positive else 'nonnegative'} value")
    return result


def text(value, where):
    if type(value) is not str or not value.strip():
        raise InputError(f"{where}: expected nonempty string")
    return value


def boolean(value, where):
    if type(value) is not bool:
        raise InputError(f"{where}: expected boolean")
    return value


def choice(value, allowed, where):
    if type(value) is not str or value not in allowed:
        raise InputError(f"{where}: expected one of {allowed}")
    return value


def sha256(value, where):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise InputError(f"{where}: expected lowercase SHA256 hex digest")
    return value


def sequence(value, item_type, where, nonempty=False):
    if type(value) not in (list, tuple) or (nonempty and not value):
        raise InputError(f"{where}: expected {'nonempty ' if nonempty else ''}ordered sequence")
    if any(type(item) is not item_type for item in value):
        raise InputError(f"{where}: expected {item_type.__name__} items")
    return tuple(value)


def unique(values, where):
    if len(set(values)) != len(values):
        raise InputError(f"{where}: duplicate identity")


def dependencies(value, task_ids, where):
    """Validate an ordered DAG without changing task or adjacency order."""
    if type(value) not in (list, tuple):
        raise InputError(f"{where}: expected ordered dependencies")
    edges = []
    children = {tid: [] for tid in task_ids}
    indegree = {tid: 0 for tid in task_ids}
    for edge in value:
        if type(edge) not in (list, tuple) or len(edge) != 2 or any(type(x) is not str for x in edge):
            raise InputError(f"{where}: expected parent/child string pair")
        parent, child = edge
        if parent not in children or child not in children or parent == child:
            raise InputError(f"{where}: invalid dependency {edge}")
        edges.append((parent, child))
        children[parent].append(child)
        indegree[child] += 1
    unique(edges, where)
    todo = [tid for tid in task_ids if indegree[tid] == 0]
    visited = 0
    while todo:
        parent = todo.pop()
        visited += 1
        for child in children[parent]:
            indegree[child] -= 1
            if indegree[child] == 0:
                todo.append(child)
    if visited != len(task_ids):
        raise InputError(f"{where}: dependency cycle")
    return tuple(edges)
