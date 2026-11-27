"""Fixed-rule API, parent-owned persistence, progress and wall-clock supervision."""
import multiprocessing
import platform
import sys
import time
import traceback
from pathlib import Path
from fogsim.errors import InputError
from fogsim.rules.factory import PreparedRules
from .protocols import Snapshot, canonical, identity, write_json, empty_output, IMPLEMENTATION, POLICY, source_provenance, append_jsonl
from .plans import parse_training_plan
from .fitness import summarize
from .worker import evaluation_worker


class RemoteEvaluationError(RuntimeError):
    def __init__(self, error, evaluation):
        self.error, self.evaluation = error, evaluation
        super().__init__(f"{error['error_type']}: {error['message']}\nRemote exception chain:\n{error['traceback']}")


def evaluate_rule_pair(prepared_rules, plan, output_dir=None, *, evaluation_sequence=0, trial_id="trial-0001",
                       evolution_seed=50001, trees=None, on_progress=None):
    from fogsim.input_validation import integer, text
    from fogsim.seed import encode_seed
    from .config import TREES
    from .runtime import preflight
    if type(prepared_rules) is not PreparedRules:
        raise InputError("expected PreparedRules")
    plan = parse_training_plan(plan.to_dict())
    p = plan.to_dict()
    integer(evaluation_sequence, "evaluation_sequence")
    text(trial_id, "trial_id")
    encode_seed(evolution_seed)
    if trees is None:
        trees = dict(TREES)
    else:
        from .config import parse_training_config
        trees = parse_training_config(dict(format="fogsim.training-config", schema_version=1, mode="single_routing",
            plans=dict(training="x", validation="y", test="z"), trees=trees), Path.cwd()).to_dict()["trees"]
    preflight(prepared_rules, p, trees)
    output = empty_output(output_dir) if output_dir is not None else None
    source = source_provenance()
    binding = dict(rule_pair_id=prepared_rules.rule_pair_id, plan_id=plan.plan_id, implementation_source_id=source["source_id"],
        implementation=IMPLEMENTATION, failure_policy=POLICY, trial_id=trial_id,
        evaluation_sequence=evaluation_sequence, trees=trees)
    records, interrupted = [], None
    def snapshot(complete=False, rng=None):
        return Snapshot(canonical(dict(format="fogsim.individual-evaluation", schema_version=1,
            evaluation_id=identity("evaluation", binding), **binding, rule_manifest=prepared_rules.rule_manifest,
            **summarize(records, len(p["entries"]), complete), runs=records, interruption=interrupted,
            evolution_rng_unchanged=rng)))
    if output:
        write_json(output / "plan.json", p)
        write_json(output / "provenance.json", dict(python=sys.version, platform=platform.platform(),
            start_method="spawn", evolution_seed=evolution_seed, implementation=IMPLEMENTATION,
            tree_limits=trees, wallclock_start="acknowledged run_started before construction", **source))
        write_json(output / "evaluation.json", snapshot().to_dict())
    ctx = multiprocessing.get_context("spawn")
    parent, child = ctx.Pipe()
    process = ctx.Process(target=evaluation_worker, args=(child,
        dict(routing=prepared_rules.routing_spec.to_dict(), sequencing=prepared_rules.sequencing_spec.to_dict()),
        p, evolution_seed))
    started, active = None, None
    error = None
    done, rng = False, None
    def save():
        if output:
            write_json(output / "evaluation.json", snapshot(done, rng).to_dict())
    try:
        process.start()
        child.close()
        while not done:
            seconds = p["limits"]["wallclock_seconds_per_run"]
            remaining = seconds - (time.monotonic()-started) if seconds is not None and started is not None else None
            if remaining is not None and remaining <= 0:
                interrupted = dict(classification="WALLCLOCK_INTERRUPTED", run_index=active,
                    capture_complete=False, coverage="received completed runs only", seconds=seconds)
                break
            if parent.poll(min(.05, max(0, remaining)) if remaining is not None else .05):
                try:
                    message = parent.recv()
                except EOFError:
                    interrupted = dict(classification="WORKER_EXIT", exitcode=process.exitcode)
                    break
                kind = message["kind"]
                if output:
                    append_jsonl(output / "progress.jsonl", {k: v for k, v in message.items() if k not in ("raw", "archive", "partial")})
                if kind == "run_started":
                    active = message["index"]
                    # callback time is outside the run budget, and callback receives a detached fact.
                    if on_progress:
                        on_progress(dict(message))
                    started = time.monotonic()
                    if output:
                        write_json(output / "active_run.json", dict(message, capture_complete=False))
                    parent.send("START")
                elif kind == "active_config":
                    if output:
                        write_json(output / f"runs/{message['index']:04d}/active_config.json", message["config"])
                elif kind == "run_completed":
                    started = None
                    index = message["index"]
                    raw, archive = message["raw"], message["archive"]
                    result_ref, input_ref = f"runs/{index:04d}/result.json", f"runs/{index:04d}/input.json"
                    if output:
                        write_json(output / result_ref, raw)
                        if archive is not None:
                            write_json(output / input_ref, archive)
                    records.append(dict(index=index, run_id=p["entries"][index]["run_id"],
                        classification=message["classification"], status=raw["status"], makespan=raw["makespan"],
                        reason_code=raw.get("reason_code"), reason=raw.get("reason"),
                        result_ref=result_ref if output else None, input_ref=input_ref if output and archive is not None else None,
                        raw_result=raw if not output else None, input_archive=archive if not output else None))
                    save()
                    if on_progress:
                        on_progress(dict(kind=kind, index=index, evaluation=snapshot().to_dict()))
                elif kind == "error":
                    error = message
                    interrupted = dict(classification=message["classification"], run_index=message.get("index"),
                        error_type=message["error_type"], message=message["message"])
                    if output:
                        write_json(output / "failures/exception.json", message)
                    break
                elif kind == "done":
                    started = None
                    done, rng = True, message["evolution_rng_unchanged"]
                else:
                    raise RuntimeError("unknown worker protocol message")
            elif not process.is_alive():
                # One final poll drains already-sent messages before classifying an exit.
                if parent.poll():
                    continue
                interrupted = dict(classification="WORKER_EXIT", exitcode=process.exitcode)
                break
    except BaseException as exc:
        interrupted = dict(classification="CANCELLED" if isinstance(exc, KeyboardInterrupt) else "CONTROLLER_EXCEPTION",
                           error_type=type(exc).__name__, message=str(exc), run_index=active)
        if output:
            write_json(output / "failures/controller-exception.json", dict(interrupted, traceback=traceback.format_exc()))
        save()
        raise
    finally:
        if process.pid is not None:
            if not done and process.is_alive():
                process.terminate()
            process.join(timeout=2)
            if process.is_alive():
                process.kill()
                process.join()
        # EOF can precede exitcode publication; join above establishes the final status.
        if interrupted and interrupted["classification"] == "WORKER_EXIT":
            interrupted["exitcode"] = process.exitcode
        parent.close()
        child.close()
        if output and interrupted:
            write_json(output / "failures/interruption.json", interrupted)
        save()
    result = snapshot(done, rng)
    if error is not None:
        raise RemoteEvaluationError(error, result)
    return result
