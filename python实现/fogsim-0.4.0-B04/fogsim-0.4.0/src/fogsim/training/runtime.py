"""Real B08 execution only. Each entry constructs a fresh engine/context."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import base64
from fogsim.errors import PreparationError
from fogsim.experiment_config import parse_experiment_config, RuleConfig
from fogsim.config import RunConfig
from fogsim.instances.fixed import parse_instance
from fogsim.simulation.engine import create_engine
from fogsim.simulation.context import create_dynamic_context
from fogsim.replay.engine import create_replay_engine
from fogsim.replay.loader import parse_replay_input
from fogsim.replay.export_input import export_replay_input


def rule_config(spec):
    return RuleConfig(spec.kind, spec.resource_id, spec.expression)


def bind_config(entry, prepared, root):
    cfg = entry["effective_config"]
    if entry["mode"] == "fixed":
        return RunConfig(**(cfg | dict(routing_kind=prepared.routing_spec.kind,
            fixed_resource_id=prepared.routing_spec.resource_id, routing_expression=prepared.routing_spec.expression,
            sequencing_kind=prepared.sequencing_spec.kind, sequencing_expression=prepared.sequencing_spec.expression)))
    from copy import deepcopy
    cfg = deepcopy(cfg)
    if entry["mode"] == "dynamic":
        cfg["source"]["dag_root"] = str(root)
    cfg["run"].update(routing_rule=prepared.routing_spec.to_dict(), sequencing_rule=prepared.sequencing_spec.to_dict())
    return parse_experiment_config(cfg, base_dir=root)


def preflight(prepared, plan, trees):
    from fogsim.rules.factory import validate_rules_for_environment, install_rules
    from fogsim.instances.catalog import load_dax_catalog, STANDARD_DAX_FILES
    from fogsim.errors import InputError
    for expression in prepared.rule_manifest["expressions"]:
        nodes = expression["ast"]["nodes"]
        depths, stack = [], [(0, 0)]
        while stack:
            index, depth = stack.pop()
            depths.append(depth)
            node = nodes[index]
            if node["kind"] == "binary":
                stack.extend(((node["left"], depth+1), (node["right"], depth+1)))
        if max(depths) > trees["max_height"] or len(nodes) > trees["max_nodes"]:
            raise InputError("training rule exceeds per-tree height/node budget")
    # Validate every entry and all rules before any input RNG is created.
    for e in plan["entries"]:
        with TemporaryDirectory(prefix="fogsim-preflight-") as tmp:
            root = Path(tmp)
            cfg = bind_config(e, prepared, root)
            if e["mode"] == "dynamic":
                types = cfg.source.workflow_types
                expected = {STANDARD_DAX_FILES[i] for i in range(types.lower, types.upper+1)}
                if set(e["templates"]) != expected:
                    raise InputError("frozen template names do not match requested catalog")
                for name, value in e["templates"].items():
                    (root / name).write_bytes(base64.b64decode(value, validate=True))
                load_dax_catalog(cfg)
                install_rules(cfg.run, prepared)
                validate_rules_for_environment(prepared, cfg.source.environment)
            elif e["mode"] == "fixed":
                install_rules(cfg, prepared)
                validate_rules_for_environment(prepared, parse_instance(e["input"]))
            else:
                inp = parse_replay_input(e["input"])
                install_rules(replace(inp.run_config, routing_rule=rule_config(prepared.routing_spec),
                    sequencing_rule=rule_config(prepared.sequencing_spec)), prepared)
                validate_rules_for_environment(prepared, inp.archive.environment)


def run_entry(entry, prepared, dataset_role, on_fault, on_config=None):
    engine, cfg = None, None
    with TemporaryDirectory(prefix="fogsim-run-") as tmp:
        root = Path(tmp)
        cfg = bind_config(entry, prepared, root)
        active = cfg.to_dict()
        if entry["mode"] == "dynamic":
            active["source"]["dag_root"] = "@frozen-templates"
        if on_config is not None:
            on_config(active)
        try:
            try:
                if entry["mode"] == "dynamic":
                    for name, text in entry["templates"].items():
                        (root / name).write_bytes(base64.b64decode(text, validate=True))
                    context = create_dynamic_context(cfg, prepared_rules=prepared)
                    engine = context.engine
                elif entry["mode"] == "fixed":
                    engine = create_engine(parse_instance(entry["input"]), cfg, prepared_rules=prepared)
                else:
                    engine = create_replay_engine(parse_replay_input(entry["input"]), cfg.run,
                        purpose="reuse_inputs", output_profile="v2")
                result = engine.run()
            except PreparationError as exc:
                engine, result = exc.engine, exc.result
            archive = export_replay_input(engine, cfg.source, dataset_role=dataset_role).to_dict() if entry["mode"] == "dynamic" and engine.admission is not None and engine.environment is not None else None
            if entry["mode"] != "dynamic":
                archive = entry["input"]
            return result.to_dict(), archive
        except BaseException:
            # Preserve the original exception even if diagnostic collection fails.
            partial = {}
            if engine is not None:
                try:
                    partial["result"] = engine.result().to_dict()
                except Exception as exc:
                    partial["snapshot_error"] = repr(exc)
                if entry["mode"] == "dynamic":
                    try:
                        partial["input"] = export_replay_input(engine, cfg.source, dataset_role=dataset_role).to_dict()
                    except Exception as exc:
                        partial["capture_error"] = repr(exc)
            on_fault(partial)
            raise
