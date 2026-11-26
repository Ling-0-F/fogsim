"""Pack a B04 scenario and evaluate independent rule pairs in one GPU launch."""

from array import array
import ctypes as ct
from functools import lru_cache
import os
from pathlib import Path
from time import perf_counter

from fogsim.instances.identity import resource_identities


OPS = "PT UT DT NIQ WIQ TTIQ MRT TIS TWT NTR literal + - * / Min Max".split()
INT_PTR = ct.POINTER(ct.c_int)
DOUBLE_PTR = ct.POINTER(ct.c_double)


class Shape(ct.Structure):
    _fields_ = [
        (name, ct.c_int) for name in "tasks resources workflows mobiles edges warmup policies words".split()
    ]


def pack_instance(sample):
    """Keep tasks in B04's workflow order and resources in its numeric priority order."""
    spec = sample.spec
    resources = resource_identities(spec.resources)
    resource_ids = {resource.id: i for i, resource in enumerate(resources)}
    nr, nt, nw = len(resources), sample.tasks, len(spec.workflows)
    upload, processing, download = (array("d", [0.0]) * (nt * nr) for _ in range(3))
    workflow, owners, first, releases = [], [], [0], []
    parents = [0] * nt
    children = [[] for _ in range(nt)]
    for wi, item in enumerate(spec.workflows):
        if wi != item.id:
            raise ValueError("Expected contiguous B04 workflow IDs")
        owners.append(resource_ids[item.owner_device_id])
        releases.append(item.release_time)
        task_ids = {}
        for task in item.tasks:
            task_ids[task.id] = t = len(workflow)
            workflow.append(wi)
            for option in task.options:
                cell = t * nr + resource_ids[option.resource_id]
                upload[cell] = option.upload_time
                processing[cell] = option.processing_time
                download[cell] = option.download_time
        for parent, child in item.dependencies:
            children[task_ids[parent]].append(task_ids[child])
            parents[task_ids[child]] += 1
        first.append(len(workflow))
    edges, offsets = [], [0]
    for successors in children:
        edges.extend(sorted(successors))
        offsets.append(len(edges))
    ints = array("i")
    for block in (workflow, owners, first, parents, offsets, edges, [r.numeric_id for r in resources]):
        ints.extend(block)
    floats = array("d", releases)
    for block in (upload, processing, download):
        floats.extend(block)
    shape = Shape(nt, nr, nw, sum(r.type == "MOBILE" for r in resources), len(edges), sample.warmup, 0, 0)
    if ints.itemsize != 4 or floats.itemsize != 8:
        raise RuntimeError("The GPU ABI requires 32-bit integers and binary64 values")
    return shape, ints, floats


def attach_programs(instance, pairs, encode):
    shape, ints, floats = instance
    offsets = array("i", [0])
    opcodes = array("i")
    for pair in pairs:
        for tree in pair:
            opcodes.extend(encode(tree))
            offsets.append(len(opcodes))
    sized = Shape(
        shape.tasks,
        shape.resources,
        shape.workflows,
        shape.mobiles,
        shape.edges,
        shape.warmup,
        len(pairs),
        len(opcodes),
    )
    # B04's fixed training grammar has no ephemeral numeric constants.
    return sized, ints + offsets + opcodes, floats + array("d", [0.0]) * len(opcodes)


@lru_cache(maxsize=1)
def native_function(path):
    try:
        library = ct.CDLL(path)
    except OSError as exc:
        raise RuntimeError(
            f"Cannot load {path}. Build the selected library as described in reproduction/gpu/README.md"
        ) from exc
    fn = library.full_fitness
    fn.argtypes = [
        Shape,
        INT_PTR,
        DOUBLE_PTR,
        INT_PTR,
        DOUBLE_PTR,
        ct.c_int,
        INT_PTR,
        DOUBLE_PTR,
        ct.c_int,
        ct.POINTER(ct.c_float),
    ]
    fn.restype = ct.c_char_p
    return fn


def device_scores(packed, lanes, engine):
    shape, ints, floats = packed
    if engine not in ("cuda", "musa"):
        raise ValueError(f"Unrecognized GPU engine {engine}")
    library = os.environ.get(
        f"FOGSIM_{engine.upper()}_LIBRARY", str(Path(__file__).with_name(f"libfogsim_{engine}.so"))
    )
    fn = native_function(library)
    status = (ct.c_int * shape.policies)()
    scores = (ct.c_double * shape.policies)()
    kernel_ms = ct.c_float()
    begin = perf_counter()
    error = fn(
        shape,
        ct.cast(ints.buffer_info()[0], INT_PTR),
        ct.cast(floats.buffer_info()[0], DOUBLE_PTR),
        status,
        scores,
        0,
        None,
        None,
        lanes,
        ct.byref(kernel_ms),
    )
    wall = perf_counter() - begin
    if error:
        raise RuntimeError(error.decode())
    expected = 3 * shape.tasks + shape.workflows
    if any(count != expected for count in status):
        raise RuntimeError(f"Incomplete {engine} simulation, expected {expected} events per rule pair")
    return list(scores), dict(kernel_ms=kernel_ms.value, call_wall_s=wall)
