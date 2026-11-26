"""Validate every GPU search output and build wall-clock curves on the experiment host."""

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import csv
from hashlib import sha256
import json
import math
from pathlib import Path
import random
from statistics import fmean, median

from .protocol import FIXTURES, REFERENCE_COMMIT


def read_csv(path):
    with path.open() as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def quantile(values, q):
    data = sorted(values)
    pos = (len(data) - 1) * q
    lo = int(pos)
    return data[lo] + (pos - lo) * (data[min(lo + 1, len(data) - 1)] - data[lo])


def device_stats(folder):
    rows = read_csv(folder / "device.csv")
    good = [r for r in rows if not r["error"] and r["busy_pct"] and r["memory_mib"]]
    if not good:
        raise ValueError(f"No usable device samples in {folder}")
    busy = [float(r["busy_pct"]) for r in good]
    return dict(
        device_samples=len(good),
        unusable_samples=len(rows) - len(good),
        busy_pct_mean=fmean(busy),
        busy_pct_median=median(busy),
        busy_at_least_90_pct=100 * sum(b >= 90 for b in busy) / len(busy),
        peak_memory_mib=max(float(r["memory_mib"]) for r in good),
    )


def check(condition, message):
    if not condition:
        raise ValueError(message)


def validate_trial(folder, run, trial, record):
    name = f"small-1-trial-{trial:02d}"
    root = folder / "trials" / name
    timing = json.loads((root / "timing.json").read_text())
    cfg = timing["config"]
    check(cfg["upstream"] == REFERENCE_COMMIT and cfg["threads"] is None, name)
    check(
        (
            cfg["scale"],
            cfg["devices"],
            cfg["trial"],
            cfg["engine"],
            cfg["lanes"],
            cfg["profile"],
            cfg["genomes"],
            cfg["population"],
            cfg["generations"],
            cfg["elites"],
            cfg["tournament"],
        )
        == (
            "small",
            1,
            trial,
            run.get("engine", "musa"),
            run["lanes"],
            "paper",
            "compact",
            1000,
            51,
            10,
            7,
        ),
        name,
    )
    for ext, expected in record["sha256"].items():
        check(
            sha256((root / (name + ext)).read_bytes()).hexdigest() == expected == timing["sha256"][ext],
            name,
        )
    scores = json.loads((root / (name + ".json")).read_text())
    tests = read_csv(root / (name + ".csv"))
    check(
        (scores["scale"], scores["devices"], scores["trial"], scores["evolution_seed"])
        == ("small", 1, trial, 50000 + trial)
        and scores["validation_seeds"] == list(range(80000, 80003)),
        name,
    )
    check([int(x["seed"]) for x in tests] == list(range(90000, 90030)), name)
    check(
        all(
            x["scale"] == "small"
            and int(x["devices"]) == 1
            and int(x["trial"]) == trial
            and x["method"] == "MTGP"
            and int(x["workflows"]) == 30
            and int(x["measured"]) == 20
            and math.isfinite(float(x["makespan"]))
            for x in tests
        ),
        name,
    )
    hist = scores["history"]
    valid = scores["validation"]
    check(
        all(len(v["makespans"]) == 3 and all(math.isfinite(y) for y in v["makespans"]) for v in valid), name
    )
    check(
        {tuple(v["pair"]) for v in valid} == {tuple(h["best"]) for h in hist}
        and len(valid) == len({tuple(v["pair"]) for v in valid}),
        name,
    )
    win = min(valid, key=lambda x: fmean(x["makespans"]))
    check(win["pair"] == [scores["selected"]["sequencing"], scores["selected"]["routing"]], name)
    observed = read_csv(folder / "events" / (name + ".csv"))
    phases = timing["phases"]
    series = [
        ("train", timing["per_generation"]),
        ("validate", phases["validation"]),
        ("test", phases["tests"]),
    ]
    check([len(v) for _, v in series] == [51, 3, 30] and len(observed) == 84 and len(hist) == 51, name)
    result = []
    i = 0
    prev = record["start_s"]
    for phase, stats in series:
        for ix, x in enumerate(stats):
            raw = observed[i]
            i += 1
            end = float(raw["elapsed_s"])
            unique = int(raw["unique"])
            n_tasks = int(raw["tasks"])
            check(
                (int(raw["trial"]), raw["phase"], int(raw["index"])) == (trial, phase, ix)
                and prev <= end <= record["end_s"] <= run["wall_s"]
                and unique == x["unique"]
                and n_tasks == x["tasks"]
                and float(raw["kernel_ms"]) == x["kernel_ms"]
                and math.isclose(float(raw["interval_s"]), end - prev, abs_tol=1e-6),
                name,
            )
            prev = end
            seed = (
                1000000 + (trial - 1) * 100000 + ix
                if phase == "train"
                else (80000 if phase == "validate" else 90000) + ix
            )
            best = None
            if phase == "train":
                h = hist[ix]
                check(
                    (h["generation"], h["instance_seed"], h["unique"]) == (ix, seed, unique)
                    and 1 <= unique <= 1000,
                    name,
                )
                best = h["makespan"]
                check(math.isfinite(best), name)
            else:
                check(unique == (len(valid) if phase == "validate" else 1), name)
                if phase == "test":
                    check(
                        int(tests[ix]["tasks"]) == n_tasks and int(tests[ix]["events"]) == 30 + 3 * n_tasks,
                        name,
                    )
            result.append(
                dict(
                    elapsed_s=end,
                    trial=trial,
                    phase=phase,
                    index=ix,
                    instance_seed=seed,
                    trial_elapsed_s=float(raw["trial_elapsed_s"]),
                    interval_s=float(raw["interval_s"]),
                    unique=unique,
                    tasks=n_tasks,
                    program_words=int(raw["program_words"]) if raw.get("program_words") else None,
                    kernel_ms=x["kernel_ms"],
                    call_wall_s=x["call_wall_s"],
                    encoding_s=x["encoding_s"],
                    train_best=best,
                )
            )
    test_values = [float(r["makespan"]) for r in tests]
    trial_stats = dict(
        trial=trial,
        evolution_seed=scores["evolution_seed"],
        start_s=record["start_s"],
        end_s=record["end_s"],
        wall_s=record["end_s"] - record["start_s"],
        unique_train=sum(x["unique"] for x in timing["per_generation"]),
        validation_candidates=len(valid),
        validation_mean=fmean(win["makespans"]),
        heldout_mean=fmean(test_values),
        train_end_s=result[50]["elapsed_s"],
        validation_end_s=result[53]["elapsed_s"],
        test_end_s=result[-1]["elapsed_s"],
    )
    return result, trial_stats, scores["selected"], test_values


def marker(elapsed, phase, trial=None):
    return dict(
        elapsed_s=elapsed,
        trial=trial,
        phase=phase,
        index=None,
        instance_seed=None,
        trial_elapsed_s=None,
        interval_s=None,
        unique=0,
        tasks=None,
        program_words=None,
        kernel_ms=None,
        call_wall_s=None,
        encoding_s=None,
        train_best=None,
    )


def summarize(root):
    folder = root / "search"
    run = json.loads((folder / "run.json").read_text())
    check(
        run["count"] == 30 and [t["trial"] for t in run["trials"]] == list(range(1, 31)), "Wrong trial set"
    )
    events = [marker(0.0, "start"), marker(run["wall_s"], "end")]
    trial_rows = []
    chosen = {}
    test_sets = {}
    by_gen = defaultdict(list)
    for r in run["trials"]:
        trial = r["trial"]
        rows, stats, chosen[trial], test_sets[trial] = validate_trial(folder, run, trial, r)
        events.extend(rows)
        events.extend([marker(r["start_s"], "trial_start", trial), marker(r["end_s"], "trial_done", trial)])
        trial_rows.append(stats)
        for row in rows[:51]:
            by_gen[row["index"]].append(row)
    events.sort(key=lambda r: r["elapsed_s"])
    totals = Counter()
    for r in events:
        phase = r["phase"]
        if phase in ("train", "validate", "test"):
            totals[phase] += r["unique"]
        if phase == "train":
            totals["positions"] += 1000
            totals["task_placements"] += r["unique"] * r["tasks"]
        totals["trials"] += phase == "trial_done"
        r.update(
            completed_trials=totals["trials"],
            train_positions=totals["positions"],
            cumulative_train=totals["train"],
            cumulative_validation=totals["validate"],
            cumulative_tests=totals["test"],
        )
    check(
        totals["positions"] == 1530000
        and totals["test"] == 900
        and totals["trials"] == 30
        and totals["train"] == run["unique_train"],
        "Search work totals differ",
    )
    write_csv(root / "timeline.csv", events)
    write_csv(root / "trials.csv", trial_rows)
    gen = []
    for k, rows in sorted(by_gen.items()):
        check(
            len(rows) == 30 and all(r["program_words"] is not None for r in rows),
            "Missing generation measurements",
        )
        times = [r["interval_s"] for r in rows]
        cum = [r["trial_elapsed_s"] for r in rows]
        gen.append(
            dict(
                generation=k + 1,
                unique_mean=fmean(r["unique"] for r in rows),
                tasks_mean=fmean(r["tasks"] for r in rows),
                program_words_per_pair=sum(r["program_words"] for r in rows)
                / sum(r["unique"] for r in rows),
                wall_p10_s=quantile(times, 0.1),
                wall_median_s=median(times),
                wall_mean_s=fmean(times),
                wall_p90_s=quantile(times, 0.9),
                kernel_median_s=median(r["kernel_ms"] for r in rows) / 1000,
                cumulative_p10_s=quantile(cum, 0.1),
                cumulative_median_s=median(cum),
                cumulative_p90_s=quantile(cum, 0.9),
            )
        )
    write_csv(root / "generations.csv", gen)
    t = [r["elapsed_s"] for r in events]

    def at(seconds):
        return events[bisect_right(t, seconds) - 1]["cumulative_train"]

    rates = []
    window = 30.0
    for end in [*range(math.ceil(run["wall_s"])), run["wall_s"]]:
        begin = max(0.0, end - window)
        rates.append(
            dict(
                elapsed_s=end,
                cumulative_train=at(end),
                trailing_train_per_s=(at(end) - at(begin)) / (end - begin) if end > begin else 0.0,
            )
        )
    write_csv(root / "throughput.csv", rates)
    choice = json.loads((root / "parallel-choice.json").read_text())
    check(
        (choice["lanes"], choice["parallel"]) == (run["lanes"], run["parallel"]),
        "Formal launch configuration differs",
    )
    calibration = []
    for g in choice["groups"]:
        group_folder = root / g["label"]
        measured = json.loads((group_folder / "run.json").read_text())
        check(all(measured[k] == v for k, v in g.items()), "Calibration manifest differs")
        for record in measured["trials"]:
            validate_trial(group_folder, measured, record["trial"], record)
            check(
                record["sha256"] == run["trials"][record["trial"] - 1]["sha256"],
                "Calibration search output differs",
            )
        calibration.append(
            dict(
                **g,
                unique_per_s=g["unique_train"] / g["wall_s"],
                trials_per_min=60 * g["count"] / g["wall_s"],
                **device_stats(group_folder),
            )
        )
    write_csv(root / "scaling.csv", calibration)
    winner = min(trial_rows, key=lambda r: (r["validation_mean"], r["trial"]))
    rng = random.Random(210021)
    ts = test_sets[winner["trial"]]
    means = [fmean(rng.choices(ts, k=30)) for _ in range(10000)]
    digests = json.loads((FIXTURES / "paper-trial-01.sha256.json").read_text())
    check(digests == run["trials"][0]["sha256"], "First trial differs from the frozen reference")
    archived = read_csv(FIXTURES / "paper-trial-01.csv")
    check(
        [int(row["seed"]) for row in archived] == list(range(90000, 90030)), "Reference test seeds differ"
    )
    baseline = [float(row["makespan"]) for row in archived]
    check(baseline == test_sets[1], "Changed reference test values")
    paired = [
        dict(seed=int(row["seed"]), winner_makespan_s=a, reference_makespan_s=b, saving_s=b - a)
        for row, a, b in zip(archived, ts, baseline, strict=True)
    ]
    write_csv(root / "winner-tests.csv", paired)
    savings = [r["saving_s"] for r in paired]
    diffs = [fmean(rng.choices(savings, k=30)) for _ in range(10000)]
    comparison = dict(
        trial=1,
        evolution_seed=50001,
        mean_makespan_s=fmean(baseline),
        mean_saving_s=fmean(savings),
        relative_saving_pct=100 * fmean(savings) / fmean(baseline),
        winner_shorter=sum(x > 0 for x in savings),
        tied=sum(x == 0 for x in savings),
        paired_saving_ci95_s=[quantile(diffs, 0.025), quantile(diffs, 0.975)],
    )
    milestone = {
        str(p): next(r["elapsed_s"] for r in events if r["cumulative_train"] >= p * totals["train"] / 100)
        for p in (25, 50, 75, 100)
    }
    done_times = sorted(row["end_s"] for row in trial_rows)
    trial_milestones = {str(n): done_times[n - 1] for n in (1, 5, 10, 15, 20, 25, 30)}
    windows = []
    for first, last in ((1, 10), (21, 30), (42, 51)):
        rows = [row for k in range(first - 1, last) for row in by_gen[k]]
        windows.append(
            dict(
                first_generation=first,
                last_generation=last,
                observations=len(rows),
                wall_median_s=median(row["interval_s"] for row in rows),
                unique_mean=fmean(row["unique"] for row in rows),
                tasks_mean=fmean(row["tasks"] for row in rows),
                program_words_per_pair=sum(row["program_words"] for row in rows)
                / sum(row["unique"] for row in rows),
            )
        )
    report = dict(
        scope="Small/1, GPU-only fitness",
        start_utc=run["start_utc"],
        end_utc=run["end_utc"],
        parallel=run["parallel"],
        lanes=run["lanes"],
        wall_s=run["wall_s"],
        last_result_s=run["last_result_s"],
        positions=totals["positions"],
        unique_train=totals["train"],
        validation=totals["validate"],
        tests=totals["test"],
        task_placements=totals["task_placements"],
        unique_train_per_s=totals["train"] / run["wall_s"],
        total_fitness_per_s=(totals["train"] + totals["validate"] + totals["test"]) / run["wall_s"],
        train_milestone_s=milestone,
        trial_milestone_s=trial_milestones,
        generation_windows=windows,
        trial_median_s=median(r["wall_s"] for r in trial_rows),
        trial_tail_median_s=median(r["end_s"] - r["train_end_s"] for r in trial_rows),
        trial_range_s=[min(r["wall_s"] for r in trial_rows), max(r["wall_s"] for r in trial_rows)],
        device=device_stats(folder),
        calibration=calibration,
        winner=winner,
        winner_rules=chosen[winner["trial"]],
        winner_test_ci95=[quantile(means, 0.025), quantile(means, 0.975)],
        archived_trial_comparison=comparison,
        trial_heldout_mean_median=median(r["heldout_mean"] for r in trial_rows),
    )
    rule_export = dict(
        trial=winner["trial"],
        evolution_seed=winner["evolution_seed"],
        selection="mean validation makespan",
        validation_seeds=list(range(80000, 80003)),
        validation_mean_s=winner["validation_mean"],
        test_seeds=list(range(90000, 90030)),
        test_mean_s=winner["heldout_mean"],
        rules=report["winner_rules"],
    )
    (root / "winner.json").write_text(json.dumps(rule_export, indent=2) + "\n")
    (root / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.folder), indent=2))
