"""Measure and run a GPU-only B04 search on one remote host."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
from multiprocessing import get_context
import os
from pathlib import Path
import re
import subprocess
import threading
from tempfile import TemporaryDirectory
from time import monotonic

from .protocol import FIXTURES, REFERENCE_COMMIT
from .trainer import measure_trial

PHASE_FIELDS = (
    "trial",
    "phase",
    "index",
    "elapsed_s",
    "trial_elapsed_s",
    "interval_s",
    "unique",
    "tasks",
    "encoding_s",
    "kernel_ms",
    "call_wall_s",
    "program_words",
)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def save_json(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n")
    temp.replace(path)


def file_digest(path):
    return sha256(path.read_bytes()).hexdigest()


def sample_device(output, origin, stop, cli):
    cmd = [
        cli,
        "-i",
        "0",
        "--query-gpu=utilization.gpu,memory.used,temperature.gpu,power.draw",
        "--format=csv,noheader",
    ]
    with output.open("x", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(("elapsed_s", "busy_pct", "memory_mib", "temperature_c", "power_w", "error"))
        while not stop.is_set():
            tic = monotonic()
            try:
                raw = subprocess.run(
                    cmd, capture_output=True, text=True, check=True, timeout=4
                ).stdout.strip()
                values = []
                for part in raw.split(","):
                    match = re.search(r"-?\d+(?:\.\d+)?", part)
                    values.append(float(match.group()) if match else "")
                if len(values) != 4:
                    raise ValueError(raw)
                writer.writerow([monotonic() - origin, *values, ""])
            except (OSError, ValueError, subprocess.SubprocessError) as e:
                writer.writerow([monotonic() - origin, "", "", "", "", str(e)])
            f.flush()
            stop.wait(max(0.0, 1.0 - (monotonic() - tic)))


def run_one(folder, trial, lanes, origin, dax, engine):
    prefix = f"small-1-trial-{trial:02d}"
    started = monotonic()
    prev = started
    events = folder / "events" / f"{prefix}.csv"
    with events.open("x", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PHASE_FIELDS, lineterminator="\n")
        writer.writeheader()

        def observed(phase, index, stats):
            nonlocal prev
            now = monotonic()
            writer.writerow(
                dict(
                    trial=trial,
                    phase=phase,
                    index=index,
                    elapsed_s=now - origin,
                    trial_elapsed_s=now - started,
                    interval_s=now - prev,
                    **stats,
                )
            )
            f.flush()
            prev = now

        with TemporaryDirectory(dir=folder / "trials", prefix=".trial-") as temporary:
            staging = Path(temporary) / prefix
            staging.mkdir()
            job = (dax, "small", 1, trial - 1, 1000, 51, 10, 7, staging)
            expr_start = monotonic()
            name, per_generation, phases = measure_trial(job, lanes, engine, observed)
            trainer_wall = monotonic() - expr_start
            if name != prefix:
                raise ValueError(f"Unexpected trial name {name}")
            digests = {ext: file_digest(staging / (prefix + ext)) for ext in (".json", ".csv")}
            config = dict(
                upstream=REFERENCE_COMMIT,
                profile="paper",
                engine=engine,
                scale="small",
                devices=1,
                trial=trial,
                population=1000,
                generations=51,
                elites=10,
                tournament=7,
                threads=None,
                lanes=lanes,
                genomes="compact",
            )
            save_json(
                staging / "timing.json",
                dict(
                    config=config,
                    trial_wall_s=trainer_wall,
                    per_generation=per_generation,
                    phases=phases,
                    sha256=digests,
                ),
            )
            staging.rename(folder / "trials" / prefix)
    ended = monotonic()
    return dict(
        trial=trial,
        pid=os.getpid(),
        start_s=started - origin,
        end_s=ended - origin,
        trainer_wall_s=trainer_wall,
        unique_train=sum(r["unique"] for r in per_generation),
        sha256=digests,
    )


def run_group(root, label, count, parallel, lanes, dax, engine):
    folder = root / label
    summary = folder / "run.json"
    if summary.is_file():
        saved = json.loads(summary.read_text())
        if (saved["count"], saved["parallel"], saved["lanes"], saved.get("engine", "musa")) != (
            count,
            parallel,
            lanes,
            engine,
        ):
            raise ValueError(f"Existing group settings do not match {label}")
        for trial in saved["trials"]:
            prefix = f"small-1-trial-{trial['trial']:02d}"
            for ext, digest in trial["sha256"].items():
                if file_digest(folder / "trials" / prefix / (prefix + ext)) != digest:
                    raise ValueError(f"Changed result {label} {prefix}")
        return saved
    if folder.exists():
        raise FileExistsError(
            f"Incomplete timing group {folder}. Preserve it before measuring a fresh group."
        )
    cli = "nvidia-smi" if engine == "cuda" else "mthreads-gmi"
    device_name = subprocess.check_output(
        [cli, "-i", "0", "--query-gpu=name", "--format=csv,noheader"], text=True
    ).strip()
    (folder / "events").mkdir(parents=True)
    (folder / "trials").mkdir()
    origin = monotonic()
    start_utc = utc_now()
    print(f"{start_utc} {label}: {parallel} GPU search processes, {count} whole trials", flush=True)
    stop = threading.Event()
    telemetry = threading.Thread(
        target=sample_device, args=(folder / "device.csv", origin, stop, cli), daemon=True
    )
    telemetry.start()
    trials = []
    try:
        # Spawn distinct GPU contexts without inheriting an initialized driver from the parent.
        with ProcessPoolExecutor(max_workers=parallel, mp_context=get_context("spawn")) as pool:
            futures = [
                pool.submit(run_one, folder, n, lanes, origin, dax, engine) for n in range(1, count + 1)
            ]
            for fut in as_completed(futures):
                result = fut.result()
                trials.append(result)
                print(f"{label}: {len(trials)}/{count} complete after {result['end_s']:.1f} s", flush=True)
        wall = monotonic() - origin
        end_utc = utc_now()
    finally:
        stop.set()
        telemetry.join(timeout=5)
    trials.sort(key=lambda r: r["trial"])
    result = dict(
        label=label,
        count=count,
        parallel=parallel,
        lanes=lanes,
        engine=engine,
        gpu_name=device_name,
        start_utc=start_utc,
        end_utc=end_utc,
        wall_s=wall,
        last_result_s=max(r["end_s"] for r in trials),
        unique_train=sum(r["unique_train"] for r in trials),
        trials=trials,
    )
    save_json(summary, result)
    return result


def compare_outputs(left, right):
    a = {r["trial"]: r["sha256"] for r in left["trials"]}
    b = {r["trial"]: r["sha256"] for r in right["trials"]}
    for trial in a.keys() & b.keys():
        if a[trial] != b[trial]:
            raise ValueError(f"Trial {trial} differs between {left['label']} and {right['label']}")


def main(root, dax, engine):
    root = root.resolve()
    width = json.loads((root / "width-choice.json").read_text())
    if width.get("engine", "musa") != engine:
        raise ValueError("Width calibration is for a different engine")
    lanes = width["lanes"]
    original = FIXTURES / "paper-trial-01.sha256.json"
    initial = run_group(root, "cal-1", 4, 1, lanes, dax, engine)
    if initial["trials"][0]["sha256"] != json.loads(original.read_text()):
        raise ValueError("First complete trial differs from the archived reference")
    two = run_group(root, "cal-2", 4, 2, lanes, dax, engine)
    compare_outputs(initial, two)
    groups = [initial, two]
    fastest = min(groups, key=lambda r: r["wall_s"])
    if initial["wall_s"] / two["wall_s"] > 1.03:
        four = run_group(root, "cal-4", 4, 4, lanes, dax, engine)
        compare_outputs(initial, four)
        groups.append(four)
        fastest = min(groups, key=lambda r: r["wall_s"])
        if two["wall_s"] / four["wall_s"] > 1.03:
            four_long = run_group(root, "cal-4-long", 8, 4, lanes, dax, engine)
            eight = run_group(root, "cal-8", 8, 8, lanes, dax, engine)
            compare_outputs(initial, four_long)
            compare_outputs(four_long, eight)
            groups.extend([four_long, eight])
            fastest = min((four_long, eight), key=lambda r: r["wall_s"])
    choice = dict(
        lanes=lanes,
        parallel=fastest["parallel"],
        groups=[
            {k: g[k] for k in ("label", "count", "parallel", "lanes", "wall_s", "unique_train")}
            for g in groups
        ],
    )
    save_json(root / "parallel-choice.json", choice)
    final = run_group(root, "search", 30, choice["parallel"], lanes, dax, engine)
    for g in groups:
        compare_outputs(g, final)
    print(f"Completed {final['count']} trials in {final['wall_s']:.2f} s", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--dax", required=True, type=Path)
    parser.add_argument("--engine", choices=("cuda", "musa"), required=True)
    args = parser.parse_args()
    main(args.out, args.dax.resolve(), args.engine)
