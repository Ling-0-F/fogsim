"""One serial spawn worker per evaluation. No shared global RNG with caller."""
import random
import traceback
from fogsim.rules.specs import RuleSpec
from fogsim.rules.factory import prepare_rules
from .runtime import run_entry
from .fitness import classify


def evaluation_worker(conn, rules, plan, evolution_seed):
    try:
        random.seed(evolution_seed)
        evolution_start = repr(random.getstate())
        prepared = prepare_rules(RuleSpec.from_mapping("routing", rules["routing"]),
                                 RuleSpec.from_mapping("sequencing", rules["sequencing"]))
        for index, entry in enumerate(plan["entries"]):
            conn.send(dict(kind="run_started", index=index, run_id=entry["run_id"]))
            if conn.recv() != "START":
                raise RuntimeError("invalid controller acknowledgement")
            partial = {}
            try:
                raw, archive = run_entry(entry, prepared, plan["dataset_role"], partial.update,
                    on_config=lambda config: conn.send(dict(kind="active_config", index=index, config=config)))
                # A coverage/metric classification error must still retain the
                # untouched B08 result and input returned just before it.
                partial.update(result=raw, input=archive)
                classification = classify(raw)
            except BaseException as exc:
                conn.send(dict(kind="error", index=index, error_type=type(exc).__name__, message=str(exc),
                    traceback=traceback.format_exc(), partial=partial,
                    classification=getattr(exc, "classification", "INPUT_OR_PLAN_ERROR" if isinstance(exc, ValueError) else "PROGRAM_EXCEPTION")))
                return
            conn.send(dict(kind="run_completed", index=index, raw=raw, archive=archive,
                classification=classification))
        conn.send(dict(kind="done", evolution_rng_unchanged=repr(random.getstate()) == evolution_start))
    except BaseException as exc:
        conn.send(dict(kind="error", error_type=type(exc).__name__, message=str(exc),
            traceback=traceback.format_exc(), classification="PROGRAM_EXCEPTION"))
    finally:
        conn.close()
