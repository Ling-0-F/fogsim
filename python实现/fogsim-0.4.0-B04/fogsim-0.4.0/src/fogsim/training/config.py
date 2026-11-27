"""Strict training-config v1. Parsing and preflight consume no RNG."""
from pathlib import Path
import math
from fogsim.errors import InputError
from fogsim.instances.fixed import object_fields
from fogsim.input_validation import integer, finite, boolean, choice, text
from fogsim.seed import encode_seed
from .protocols import Snapshot, canonical, read_json, SEMANTICS

EVOLUTION = dict(population_size=12, generations=4, elite_count=1, tournament_size=3,
    variation_policy="exclusive_choice_v1", operator_weights=dict(crossover=.8, mutation=.15, reproduction=.05),
    tournament_tie_break="first_sampled", crossover_attempts=1, mutation_attempts=1)
TREES = dict(init_min_height=1, init_max_height=3, init_full_probability=.5,
    grow_policy="java_terminal_entry_v1", node_nonterminal_probability=.9,
    mutation_max_height=3, max_height=7, max_nodes=255, numeric_erc=False, initialization_attempts=100)
EVALUATION = dict(objective="makespan", aggregation="run_equal_mean", failure_policy="all_success_feasible_v1",
    lifecycle="fresh_dynamic_same_plan", rotation_period=1, seed_rotation_step=10000)
OUTPUT = dict(trace="selected_cases", save_run_results=True, save_input_archives=True)


def _section(data, name, defaults):
    raw = data.get(name, {})
    object_fields(raw, (), tuple(defaults), name)
    return dict(defaults, **raw)


def parse_training_config(data, base_dir):
    object_fields(data, ("format", "schema_version", "mode", "plans"),
                  ("trials", "evolution", "trees", "evaluation", "limits", "output", "semantics"), "training")
    choice(data["format"], ("fogsim.training-config",), "format")
    integer(data["schema_version"], "schema_version", 1, 1)
    choice(data["mode"], ("single_routing", "dual_tree"), "mode")
    trials = _section(data, "trials", dict(evolution_seeds=[50001, 50002]))
    seeds = trials["evolution_seeds"]
    if type(seeds) is not list or not seeds:
        raise InputError("evolution_seeds must be a nonempty array")
    for seed in seeds:
        encode_seed(seed)
    if len(set(seeds)) != len(seeds):
        raise InputError("independent trials require distinct evolution seeds")
    e = _section(data, "evolution", EVOLUTION)
    for key in ("population_size", "generations", "tournament_size", "crossover_attempts", "mutation_attempts"):
        integer(e[key], key, 1)
    integer(e["elite_count"], "elite_count", 0, e["population_size"])
    choice(e["variation_policy"], ("exclusive_choice_v1",), "variation_policy")
    choice(e["tournament_tie_break"], ("first_sampled",), "tournament_tie_break")
    weights = e["operator_weights"]
    object_fields(weights, ("crossover", "mutation", "reproduction"), where="operator_weights")
    weights = {k: finite(v, k) for k, v in weights.items()}
    total = math.fsum(weights.values())
    if abs(total - 1.0) > 1e-12:
        raise InputError("operator_weights must sum to 1 (absolute tolerance 1e-12)")
    e["operator_weights"] = {k: v / total for k, v in weights.items()}
    t = _section(data, "trees", TREES)
    for key in ("init_min_height", "init_max_height", "mutation_max_height", "max_height"):
        integer(t[key], key, 0, 7)
    for key in ("max_nodes", "initialization_attempts"):
        integer(t[key], key, 1, 255 if key == "max_nodes" else None)
    if not t["init_min_height"] <= t["init_max_height"] <= t["max_height"] or t["mutation_max_height"] > t["max_height"]:
        raise InputError("incompatible tree heights")
    if 2 ** (t["init_max_height"] + 1) - 1 > t["max_nodes"]:
        raise InputError("full initialization at maximum target height cannot fit max_nodes")
    for key in ("init_full_probability", "node_nonterminal_probability"):
        t[key] = finite(t[key], key)
        if t[key] > 1:
            raise InputError(f"{key}: probability > 1")
    boolean(t["numeric_erc"], "numeric_erc")
    if t["numeric_erc"]:
        raise InputError("numeric ERC search is not supported")
    choice(t["grow_policy"], ("java_terminal_entry_v1",), "grow_policy")
    ev = _section(data, "evaluation", EVALUATION)
    for key, expected in EVALUATION.items():
        if key == "rotation_period":
            integer(ev[key], key, 1)
        elif key == "seed_rotation_step":
            integer(ev[key], key, 10000, 10000)
        else:
            choice(ev[key], (expected,), key)
    limits = _section(data, "limits", dict(wallclock_seconds_per_run=None))
    if limits["wallclock_seconds_per_run"] is not None:
        limits["wallclock_seconds_per_run"] = finite(limits["wallclock_seconds_per_run"], "wallclock", True)
    out = _section(data, "output", OUTPUT)
    choice(out["trace"], ("selected_cases", "all", "none"), "trace")
    for key in ("save_run_results", "save_input_archives"):
        boolean(out[key], key)
        if not out[key]:
            raise InputError("B01 requires original results and available input archives")
    semantic = _section(data, "semantics", SEMANTICS)
    if semantic != SEMANTICS:
        raise InputError("unsupported semantic version binding")
    paths = data["plans"]
    object_fields(paths, ("training", "validation", "test"), where="plans")
    base = Path(base_dir).resolve()
    paths = {k: str((base / text(v, k)).resolve()) for k, v in paths.items()}
    return Snapshot(canonical(dict(format=data["format"], schema_version=1, mode=data["mode"], trials=trials,
        evolution=e, trees=t, evaluation=ev, limits=limits, output=out, plans=paths,
        semantics=semantic, resolution_root=str(base))))


def load_training_config(path):
    return parse_training_config(read_json(path), Path(path).resolve().parent)
