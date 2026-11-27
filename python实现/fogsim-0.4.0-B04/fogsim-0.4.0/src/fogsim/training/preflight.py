"""Cost and retention facts, computed without simulation or evolution RNG draws."""
import platform
import sys
from importlib.metadata import version, PackageNotFoundError


def preflight_report(config, plans):
    from .trainer import simulation_budget
    from .protocols import SEMANTICS
    cfg = config.to_dict()
    entries = [entry for plan in plans.all_plans() for entry in plan.to_dict()["entries"]]
    budgets = [entry["effective_config"].get("run", {}).get("max_events") for entry in entries]
    dependencies = {}
    for name in ("deap", "numpy", "moocore", "cffi", "platformdirs", "pycparser"):
        try:
            dependencies[name] = version(name)
        except PackageNotFoundError:
            dependencies[name] = None
    bound = simulation_budget(cfg, plans)
    # A coarse ceiling for processed events, not CPU, elapsed time, RAM or disk.
    event_bound = None if any(b is None for b in budgets) else bound["total_upper_bound"] * max(budgets)
    return dict(format="fogsim.training-preflight", schema_version=1,
        status="PREFLIGHT_ONLY", simulations_executed=0, mode=cfg["mode"],
        closed_loop_budget=bound,
        training_simulation_upper_bound=bound["training_per_trial"] * bound["trials"],
        event_budgets=budgets, processed_event_upper_bound=event_bound,
        wallclock_seconds_per_run=cfg["limits"]["wallclock_seconds_per_run"],
        retention=cfg["output"], semantics=SEMANTICS,
        versions=dict(python=sys.version, platform=platform.platform(), dependencies=dependencies),
        plan_ids=[p.plan_id for p in plans.all_plans()],
        deferred="Preflight performs no simulation. Use train or --execute to run the configured experiment.",
        cost_note="Bounds cover one configured execution; candidate deduplication or interruption can reduce runs. No time, memory or byte estimate is inferred from event counts.")
