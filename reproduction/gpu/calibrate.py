"""Check the first paper generation against B04 Python and time GPU block widths."""

import argparse
import csv
import json
from pathlib import Path
import random
from statistics import median
from time import perf_counter

from fogsim.training.config import TREES
from paper import generate
from . import compact_gp
from .fitness import attach_programs, device_scores, pack_instance
from .protocol import FIXTURES
from .trainer import encode


def reference_generation(dax):
    limits = dict(TREES, init_min_height=1, init_max_height=5, max_height=7)
    rng = random.Random(50001)
    pairs = [compact_gp.initialize_dual(limits, rng)[0] for _ in range(1000)]
    instance = pack_instance(generate(dax, "small", 1, 1000000))
    with (FIXTURES / "first-generation.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    if [int(row["distinct_pair"]) for row in rows] != list(range(1000)) or len(set(pairs)) != 1000:
        raise ValueError("Expected all 1,000 distinct pairs in B04 initialization order")
    return attach_programs(instance, pairs, encode), [float(row["makespan"]) for row in rows]


def checked_call(packed, expected, lanes, engine):
    scores, timing = device_scores(packed, lanes, engine)
    if scores != expected:
        raise ValueError(f"Fitness differs from B04 Python at width {lanes}")
    return timing


def calibrate(dax, out, check_only, engine):
    begin = perf_counter()
    packed, expected = reference_generation(dax)
    if check_only:
        checked_call(packed, expected, 64, engine)
        print("All 1,000 GPU fitness values equal the archived Python reference.")
        return
    out.mkdir(parents=True, exist_ok=False)
    widths = (1, 4, 8, 16, 32, 64)
    rows = []
    for repeat, order in enumerate((widths, widths, tuple(reversed(widths)), widths[2:] + widths[:2])):
        for lanes in order:
            timing = checked_call(packed, expected, lanes, engine)
            rows.append(dict(repeat=repeat, lanes=lanes, **timing))
    times = {w: median(r["call_wall_s"] for r in rows if r["lanes"] == w and r["repeat"]) for w in widths}
    best = min(widths, key=times.get)
    with (out / "widths.csv").open("x", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    choice = dict(
        engine=engine,
        lanes=best,
        median_call_s=times,
        workload=len(expected),
        wall_s=perf_counter() - begin,
    )
    (out / "width-choice.json").write_text(json.dumps(choice, indent=2) + "\n")
    print(f"Selected {best} lanes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dax", type=Path, required=True)
    parser.add_argument("--engine", choices=("cuda", "musa"), required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--out", type=Path, help="New benchmark output directory")
    mode.add_argument(
        "--check-only", action="store_true", help="Verify all 1,000 scores with one GPU launch"
    )
    args = parser.parse_args()
    calibrate(args.dax, args.out, args.check_only, args.engine)
