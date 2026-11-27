"""Strict JSON loading. Missing candidates and unknown runtime fields are errors."""
import json
import math
from pathlib import Path

from fogsim.errors import InputError
from .spec import InstanceSpec, ResourceSpec, WorkflowSpec, TaskSpec, OptionSpec


def object_fields(value, required, optional=(), where="object"):
    if not isinstance(value, dict):
        raise InputError(f"{where}: expected object")
    missing = set(required) - value.keys()
    extra = value.keys() - set(required) - set(optional)
    if missing or extra:
        raise InputError(f"{where}: missing={sorted(missing)}, unknown={sorted(extra)}")


def items(value, where, nonempty=True):
    if not isinstance(value, list) or (nonempty and not value):
        raise InputError(f"{where}: expected {'nonempty ' if nonempty else ''}list")
    return value


def identifier(value, where):
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{where}: expected nonempty string ID")
    return value


def number(value, where, positive=False):
    if type(value) not in (float, int):
        raise InputError(f"{where}: expected numeric time (not bool/string)")
    try:
        value = float(value)
    except OverflowError as exc:
        raise InputError(f"{where}: numeric overflow") from exc
    if not math.isfinite(value) or (value <= 0 if positive else value < 0):
        raise InputError(f"{where}: expected finite {'positive' if positive else 'nonnegative'} time")
    return value


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"),
                          object_pairs_hook=_unique_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InputError(f"{path}: {exc}") from exc


def load_fixed_instance(path) -> InstanceSpec:
    return parse_instance(read_json(path))


def parse_instance(data) -> InstanceSpec:
    object_fields(data, ("time_unit", "resources", "workflows"), where="instance")
    if data["time_unit"] != "s":
        raise InputError("time_unit must be 's'")
    resources = []
    by_id = {}
    for r in items(data["resources"], "resources"):
        object_fields(r, ("id", "type"), ("can_process_tasks",), "resource")
        rid = identifier(r["id"], "resource.id")
        if rid in by_id or r["type"] not in ("MOBILE", "EDGE", "CLOUD"):
            raise InputError(f"duplicate resource or invalid type: {rid}")
        can = r.get("can_process_tasks", True)
        if type(can) is not bool or (r["type"] != "MOBILE" and "can_process_tasks" in r):
            raise InputError(f"{rid}: can_process_tasks is a MOBILE boolean")
        spec = ResourceSpec(rid, r["type"], can)
        resources.append(spec)
        by_id[rid] = spec
    if not any(r.type == "MOBILE" for r in resources):
        raise InputError("at least one MOBILE resource is required")
    servers = [r for kind in ("EDGE", "CLOUD") for r in resources if r.type == kind]
    workflows, seen_w = [], set()
    for w in items(data["workflows"], "workflows"):
        object_fields(w, ("id", "owner_device_id", "release_time", "tasks", "dependencies"), where="workflow")
        wid = w["id"]
        if type(wid) is not int or wid in seen_w:
            raise InputError("workflow ID must be a unique integer")
        seen_w.add(wid)
        owner_id = identifier(w["owner_device_id"], "owner_device_id")
        owner = by_id.get(owner_id)
        if owner is None or owner.type != "MOBILE":
            raise InputError(f"workflow {wid}: unknown MOBILE owner {owner_id}")
        release = number(w["release_time"], f"workflow {wid}.release_time")
        candidates = ([owner] if owner.can_process_tasks else []) + servers
        if not candidates:
            raise InputError(f"workflow {wid}: no eligible resource")
        tasks, seen_t = [], set()
        for t in items(w["tasks"], f"workflow {wid}.tasks"):
            object_fields(t, ("id", "execution_times"), where="task")
            tid = identifier(t["id"], "task.id")
            if tid in seen_t:
                raise InputError(f"workflow {wid}: duplicate task {tid}")
            seen_t.add(tid)
            times = t["execution_times"]
            object_fields(times, [r.id for r in candidates], where=f"{wid}/{tid}.execution_times")
            options = []
            for r in candidates:
                value = times[r.id]
                object_fields(value, ("upload_time", "processing_time", "download_time"), where=f"{tid}/{r.id}")
                ut = number(value["upload_time"], "upload_time")
                pt = number(value["processing_time"], "processing_time", positive=True)
                dt = number(value["download_time"], "download_time")
                if r.type == "MOBILE" and (ut != 0 or dt != 0):
                    raise InputError(f"{tid}/{r.id}: local UT and DT must be zero")
                options.append(OptionSpec(r.id, ut, pt, dt))
            tasks.append(TaskSpec(tid, tuple(options)))
        edges, seen_e = [], set()
        children = {t.id: [] for t in tasks}
        indegree = {t.id: 0 for t in tasks}
        for edge in items(w["dependencies"], "dependencies", nonempty=False):
            if not isinstance(edge, list) or len(edge) != 2 or any(type(x) is not str for x in edge):
                raise InputError("each dependency must be two task IDs")
            a, b = edge
            if a not in seen_t or b not in seen_t or a == b or (a, b) in seen_e:
                raise InputError(f"workflow {wid}: invalid dependency {edge}")
            seen_e.add((a, b)); edges.append((a, b))
            children[a].append(b); indegree[b] += 1
        todo = [t.id for t in tasks if indegree[t.id] == 0]
        count = 0
        while todo:
            a = todo.pop(); count += 1
            for b in children[a]:
                indegree[b] -= 1
                if indegree[b] == 0:
                    todo.append(b)
        if count != len(tasks):
            raise InputError(f"workflow {wid}: dependency cycle")
        workflows.append(WorkflowSpec(wid, owner_id, release, tuple(tasks), tuple(edges)))
    return InstanceSpec(tuple(resources), tuple(workflows))
