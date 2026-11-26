"""Use compact dual trees and prefetch one workload during GPU evaluation."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from paper import generate
from . import compact_gp
from .fitness import attach_programs, device_scores, pack_instance


def prepare(root, scale, devices, seed):
    begin = perf_counter()
    sample = generate(root, scale, devices, seed)
    generated = perf_counter()
    return pack_instance(sample), generated - begin, perf_counter() - generated


def encode(tree):
    return compact_gp.compiled(tree)[1]


class GpuBackend:
    operators = compact_gp
    rule_key = staticmethod(tuple)

    def __init__(self, pool, job, lanes, engine, observer):
        root, scale, devices, trial, _, generations, _, _, _ = job
        first = 1000000 + trial * 100000
        self.seeds = iter([*range(first, first + generations), *range(80000, 80003), *range(90000, 90030)])
        self.prefix = (root, scale, devices)
        self.pool = pool
        self.lanes = lanes
        self.engine = engine
        self.observer = observer
        self.times = Counter()
        self.batches = {"train": [], "validate": [], "test": []}
        self.advance()

    @staticmethod
    def rule_text(pair):
        return tuple(compact_gp.compiled(tree)[0] for tree in pair)

    def advance(self):
        self.seed = next(self.seeds, None)
        self.future = self.pool.submit(prepare, *self.prefix, self.seed) if self.seed is not None else None

    def sample(self, root, scale, devices, seed):
        if self.prefix != (root, scale, devices) or seed != self.seed:
            raise RuntimeError("Unexpected workload order in the B04 trainer")
        begin = perf_counter()
        instance, gen_time, pack_time = self.future.result()
        self.times["input_wait_s"] += perf_counter() - begin
        self.times["input_generation_s"] += gen_time
        self.times["static_packing_s"] += pack_time
        self.advance()
        return instance

    def evaluate(self, instance, distinct, phase):
        pairs = list(distinct)
        begin = perf_counter()
        packed = attach_programs(instance, pairs, encode)
        ready = perf_counter()
        scores, times = device_scores(packed, self.lanes, self.engine)
        stats = dict(unique=len(pairs), tasks=packed[0].tasks, encoding_s=ready - begin, **times)
        batch = self.batches[phase]
        index = len(batch)
        if self.observer:
            self.observer(phase, index, dict(stats, program_words=packed[0].words))
        if phase == "train":
            stats["generation"] = index
        batch.append(stats)
        return dict(zip(pairs, scores, strict=True))

    def test(self, instance, pair):
        span = self.evaluate(instance, [pair], "test")[pair]
        shape = instance[0]
        return dict(
            makespan=span,
            workflows=shape.workflows,
            measured=shape.workflows - shape.warmup,
            tasks=shape.tasks,
            events=shape.workflows + 3 * shape.tasks,
        )


def measure_trial(job, lanes, engine, observer=None):
    from run_mtgp import run_trial

    with ThreadPoolExecutor(max_workers=1) as pool:
        backend = GpuBackend(pool, job, lanes, engine, observer)
        name = run_trial(job, backend)
    batches = backend.batches
    if backend.future is not None or tuple(map(len, batches.values())) != (job[5], 3, 30):
        raise RuntimeError("Incomplete B04 search")
    return (
        name,
        batches["train"],
        dict(**backend.times, validation=batches["validate"], tests=batches["test"]),
    )


def run_gpu_trial(job, *, engine, lanes):
    destination = job[-1]
    with TemporaryDirectory(prefix=".gpu-trial-", dir=destination) as temporary:
        staging = Path(temporary)
        name, _, _ = measure_trial((*job[:-1], staging), lanes, engine)
        # Use the history JSON as the completion marker for the public flat-file format.
        for extension in (".csv", ".json"):
            completed = staging / (name + extension)
            completed.rename(destination / completed.name)
    return name
