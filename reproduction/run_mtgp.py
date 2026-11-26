"""Train scenario-specific double trees and test frozen winners on unseen streams."""
import argparse
import csv
import gc
import json
import multiprocessing
import random
from functools import partial
from pathlib import Path
from statistics import fmean

from fogsim.training import dual_operators
from fogsim.training.config import TREES, EVOLUTION
from fogsim.training.deap_adapter import to_expression
from fogsim.training.operators import choose_operator

from paper import SCALES, generate, simulate_sample


def expressions(trees):
    return tuple(to_expression(tree) for tree in trees)


def score(sample, pair):
    metrics = simulate_sample(sample, "MTGP", pair)
    gc.collect()
    return metrics["makespan"]


class PythonBackend:
    operators = dual_operators
    rule_key = staticmethod(expressions)
    rule_text = staticmethod(tuple)
    sample = staticmethod(generate)

    @staticmethod
    def evaluate(sample, distinct, phase):
        return {pair: score(sample, pair) for pair in distinct}

    @staticmethod
    def test(sample, pair):
        return simulate_sample(sample, "MTGP", pair)


def run_trial(job, backend=PythonBackend):
    root, scale, devices, trial, pop_size, generations, elites, tournament_size, out = job
    # Heights count edges (ECJ depth counts nodes).
    limits = dict(TREES, init_min_height=1, init_max_height=5, max_height=7)
    rng = random.Random(50001 + trial)
    population = [backend.operators.initialize_dual(limits, rng)[0] for _ in range(pop_size)]
    history, candidates = [], []
    for gen in range(generations):
        seed = 1000000 + trial * 100000 + gen
        sample = backend.sample(root, scale, devices, seed)
        pairs = [backend.rule_key(t) for t in population]
        fitness = backend.evaluate(sample, dict.fromkeys(pairs), "train")
        ordered = sorted(range(pop_size), key=lambda i: fitness[pairs[i]])
        best = pairs[ordered[0]]
        history.append(dict(generation=gen, instance_seed=seed, best=backend.rule_text(best),
                            makespan=fitness[best], unique=len(fitness)))
        if best not in candidates:
            candidates.append(best)
        del sample
        if gen + 1 == generations:
            break

        def parent():
            indices = [rng.randrange(pop_size) for _ in range(tournament_size)]
            return population[min(indices, key=lambda i: fitness[pairs[i]])]

        children = [population[i] for i in ordered[:elites]]
        while len(children) < pop_size:
            op, _ = choose_operator(EVOLUTION["operator_weights"], rng)
            if op == "crossover":
                result, _ = backend.operators.crossover_dual(parent(), parent(), limits,
                                                            outputs=min(2, pop_size - len(children)), rng=rng)
            elif op == "mutation":
                result, _ = backend.operators.mutate_dual(parent(), limits, rng=rng)
            else:
                result, _ = backend.operators.reproduce_dual(parent())
            children.extend(result)
        population = children

    validation = {pair: [] for pair in candidates}
    for seed in range(80000, 80003):
        sample = backend.sample(root, scale, devices, seed)
        for pair, value in backend.evaluate(sample, candidates, "validate").items():
            validation[pair].append(value)
    selected = min(candidates, key=lambda p: fmean(validation[p]))
    sequencing, routing = backend.rule_text(selected)
    prefix = out / f"{scale}-{devices}-trial-{trial + 1:02d}"
    record = dict(scale=scale, devices=devices, trial=trial + 1, evolution_seed=50001 + trial,
                  population=pop_size, generations=generations, elites=elites, history=history,
                  validation_seeds=list(range(80000, 80003)),
                  validation=[dict(pair=backend.rule_text(p), makespans=v) for p, v in validation.items()],
                  selected=dict(sequencing=sequencing, routing=routing))
    prefix.with_suffix(".json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    with prefix.with_suffix(".csv").open("x", newline="") as f:
        writer = csv.DictWriter(f, fieldnames="scale devices trial seed method makespan workflows measured tasks events".split())
        writer.writeheader()
        for seed in range(90000, 90030):
            metrics = backend.test(backend.sample(root, scale, devices, seed), selected)
            writer.writerow(dict(scale=scale, devices=devices, trial=trial+1, seed=seed, method="MTGP", **metrics))
            gc.collect()
    return prefix.name


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dax", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--engine", choices=("python", "cuda", "musa"), default="python")
    p.add_argument("--lanes", type=int, default=64, help="GPU threads per rule pair (1 to 64)")
    p.add_argument("--first-trial", type=int, default=1, help="First one-based trial in the selected profile")
    p.add_argument("--trial-count", type=int, help="Run this many consecutive trials")
    p.add_argument("--profile", choices=("pilot", "long", "paper"), default="pilot")
    p.add_argument("--scales", choices=SCALES, nargs="+", default=list(SCALES))
    p.add_argument("--devices", type=int, choices=(1, 2, 3), nargs="+", default=(1, 2, 3))
    args = p.parse_args()
    profiles = {"pilot": (8, 3, 1, 3), "long": (32, 51, 2, 3), "paper": (1000, 51, 10, 30)}
    pop, gens, elites, trials = profiles[args.profile]
    last = trials if args.trial_count is None else args.first_trial + args.trial_count - 1
    if not 1 <= args.first_trial <= last <= trials or args.workers < 1 or not 1 <= args.lanes <= 64:
        p.error("Check the trial range, positive worker count and GPU block width (1 to 64)")
    worker = run_trial
    context = multiprocessing.get_context()
    if args.engine != "python":
        from gpu.trainer import run_gpu_trial
        worker = partial(run_gpu_trial, engine=args.engine, lanes=args.lanes)
        context = multiprocessing.get_context("spawn")
    args.out.mkdir(parents=True, exist_ok=False)
    # B04's smaller searches use its default of 3. The Java multi-tree
    # configuration supplies the tournament size omitted from Table VI.
    tournament_size = 7 if args.profile == "paper" else 3
    jobs = [(str(args.dax.resolve()), scale, devices, i, pop, gens, elites, tournament_size, args.out)
            for scale in dict.fromkeys(args.scales) for devices in dict.fromkeys(args.devices)
            for i in range(args.first_trial - 1, last)]
    with context.Pool(args.workers) as pool:
        for done in pool.imap_unordered(worker, jobs):
            print(done, flush=True)


if __name__ == "__main__":
    main()
