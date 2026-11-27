"""Content-frozen plans, including input bytes. Paths are provenance, not identity."""
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import base64
from fogsim.errors import InputError
from fogsim.instances.fixed import object_fields, parse_instance
from fogsim.instances.catalog import load_dax_catalog, STANDARD_DAX_FILES
from fogsim.experiment_config import parse_experiment_config
from fogsim.config import load_config, RunConfig
from fogsim.replay.loader import parse_replay_input
from fogsim.seed import encode_seed
from .protocols import Snapshot, canonical, identity, content_sha, read_json, POLICY

SPLITS = {"train": "train", "validation": "debug", "test": "test"}


@dataclass(frozen=True)
class TrainingPlan(Snapshot):
    @property
    def plan_id(self):
        return self.to_dict()["plan_id"]


@dataclass(frozen=True)
class TrainingPlans:
    training: tuple[TrainingPlan, ...]
    validation: TrainingPlan
    test: TrainingPlan

    def all_plans(self):
        return (*self.training, self.validation, self.test)


def _without_rules(run):
    return {k: v for k, v in run.items() if k not in ("routing_rule", "sequencing_rule", "trace_enabled",
        "routing_kind", "sequencing_kind", "routing_expression", "sequencing_expression", "fixed_resource_id")}


def _identities(entry):
    mode, cfg = entry["mode"], entry["effective_config"]
    if mode == "dynamic":
        source = parse_experiment_config(cfg, base_dir=Path.cwd()).source
        # Use B08's exact parameter-content digest, so a native capture cannot
        # evade split checks by being consumed through the replay entry point.
        parameters = dict(environment=asdict(source.environment), samplers=source.samplers.effective_parameters())
        parameter_source = content_sha(json.dumps(parameters, sort_keys=True, separators=(",", ":")).encode())
        family = dict(generator="python-b08-native-v1", parameter_source=parameter_source,
            workflow_types=asdict(source.workflow_types),
            templates=[dict(dag_type_id=i, source_sha256=entry["template_digests"][STANDARD_DAX_FILES[i]])
                       for i in range(source.workflow_types.lower, source.workflow_types.upper+1)])
        scene = dict(input_family=family, run=_without_rules(cfg["run"]))
        input_id = None
    else:
        inp = entry["input"]
        if mode == "fixed":
            full = inp
            run = _without_rules(cfg)
        else:
            # Input content excludes recorded rules, capture observations and statistics.
            full = {k: inp[k] for k in ("environment", "templates", "candidates", "generation_attempts", "initial_state")}
            full["generation_attempts"] = [{k: v for k, v in a.items() if k not in ("observed_acceptance", "rejection_reason")}
                                                for a in full["generation_attempts"]]
            run = dict(_without_rules(inp["effective_config"]), overrides=_without_rules(cfg["run"]))
            for k in ("sequencing_rule", "routing_rule"):
                run.pop(k, None)
        input_id = identity("input-content", full)
        if mode == "fixed":
            family = dict(mode=mode, input_content_id=input_id)
        elif inp["origin"].get("language") == "Python" and inp["origin"].get("fixture_kind") == "native_random":
            lower, upper = inp["effective_config"]["samplers"]["workflow_type"]
            family = dict(generator="python-b08-native-v1", parameter_source=inp["environment"]["parameter_source"],
                workflow_types=dict(lower=lower, upper=upper),
                templates=[dict(dag_type_id=t["dag_type_id"], source_sha256=t["source_sha256"]) for t in inp["templates"]])
        else:
            family = dict(generator="recorded-input-v1", environment=inp["environment"],
                samplers=inp["effective_config"]["samplers"], templates=inp["templates"])
        scene = dict(input_family=family, run=run)
    return identity("scene", scene), identity("input-family", family), input_id


def _entry(path, run_id, split, offset, output):
    raw = read_json(path)
    if type(raw) is not dict:
        raise InputError("scene config must be an object")
    if raw.get("format") == "fogsim.experiment":
        cfg = parse_experiment_config(raw, base_dir=path.parent)
        if cfg.schema_version != 2 or cfg.repeat.count != 1:
            raise InputError("training source scenes require B08 v2 and repeat.count=1")
        cfg = cfg.single_run()
        value = cfg.to_dict()
        # Scene rules are placeholders; the evaluated pair is installed explicitly.
        for role in ("routing", "sequencing"):
            value["run"][role + "_rule"] = dict(kind="fcfs")
        value["output"] = dict(dataset_role=SPLITS[split])
        if output["trace"] != "selected_cases":
            value["run"]["trace_enabled"] = output["trace"] == "all"
        if cfg.mode == "dynamic":
            if cfg.run.max_events is None:
                raise InputError("each dynamic entry requires an explicit event budget")
            seed = cfg.source.seed + offset
            encode_seed(seed)  # Arithmetic overflow is rejected, never long-wrapped.
            value["source"]["seed"] = seed
            catalog = load_dax_catalog(cfg)
            templates = {STANDARD_DAX_FILES[t.dag_type_id]: base64.b64encode((cfg.source.dag_root / STANDARD_DAX_FILES[t.dag_type_id]).read_bytes()).decode("ascii")
                         for t in catalog.templates}
            digests = {k: content_sha(base64.b64decode(v, validate=True)) for k, v in templates.items()}
            value["source"]["dag_root"] = "@frozen-templates"
            entry = dict(mode="dynamic", seed=seed, templates=templates, template_digests=digests,
                effective_config=value, input_contract="same_input_generation_mechanism",
                lifecycle="fresh_dynamic_same_plan")
        else:
            if cfg.source.purpose != "reuse_inputs" or cfg.source.reference_path is not None:
                raise InputError("controlled replay evaluation requires reuse_inputs without a reference")
            inp = read_json(cfg.source.input_path)
            parse_replay_input(inp)  # incomplete captures are not eligible
            if cfg.run.max_events is None:
                raise InputError("controlled replay requires an explicit event budget")
            value["source"]["input_path"] = "@frozen-input"
            entry = dict(mode="replay", seed=inp["initial_state"]["public_seed"], effective_config=value, input=inp, template_digests={},
                lifecycle="fresh_replay", input_contract="explicit_complete_recorded_input_coverage_checked_at_runtime")
    else:
        instance_path, cfg = load_config(path)
        inp = read_json(instance_path)
        parse_instance(inp)
        cfg = cfg.to_dict()
        cfg.update(routing_kind="fcfs", sequencing_kind="fcfs", fixed_resource_id=None)
        cfg.pop("routing_expression", None)
        cfg.pop("sequencing_expression", None)
        if output["trace"] != "selected_cases":
            cfg["trace_enabled"] = output["trace"] == "all"
        entry = dict(mode="fixed", seed=None, effective_config=cfg, input=inp, template_digests={},
            lifecycle="fresh_fixed", input_contract="explicit_fixed_input")
    entry.update(run_id=run_id, source_config_sha256=content_sha(path.read_bytes()))
    entry["scene_id"], entry["input_family_id"], entry["input_content_id"] = _identities(entry)
    entry["effective_config_sha256"] = content_sha(canonical(entry["effective_config"]).encode())
    return entry


def _plan(split, entries, limits):
    payload = dict(format="fogsim.training-plan", schema_version=1, split=split, entries=entries,
        lifecycle="fresh_dynamic_same_plan", failure_policy=POLICY, aggregation="run_equal_mean",
        limits=limits, dataset_role=SPLITS[split])
    # Exclude original file encoding/provenance; retain all effective content.
    semantic = dict(payload, entries=[{k: v for k, v in e.items() if k != "source_config_sha256"} for e in entries])
    return TrainingPlan(canonical(payload | dict(plan_id=identity("plan", semantic))))


def build_training_plans(config):
    cfg = config.to_dict()
    manifests = {}
    for split, key in (("train", "training"), ("validation", "validation"), ("test", "test")):
        path = Path(cfg["plans"][key])
        raw = read_json(path)
        object_fields(raw, ("format", "schema_version", "entries"), where="source-plan")
        if raw["format"] != "fogsim.training-source-plan" or type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
            raise InputError("unsupported source-plan protocol")
        if type(raw["entries"]) is not list or not raw["entries"]:
            raise InputError("source-plan requires at least one entry")
        rows, ids = [], set()
        for e in raw["entries"]:
            object_fields(e, ("run_id", "config"), where="source-plan.entry")
            if type(e["run_id"]) is not str or not e["run_id"].strip() or e["run_id"] in ids:
                raise InputError("run_id must be nonempty and unique within a plan")
            if type(e["config"]) is not str or not e["config"].strip():
                raise InputError("entry config must be a path")
            ids.add(e["run_id"])
            rows.append(((path.parent / e["config"]).resolve(), e["run_id"]))
        manifests[split] = rows
    groups = {}
    for split in SPLITS:
        count = cfg["evolution"]["generations"] if split == "train" else 1
        groups[split] = []
        for g in range(count):
            offset = 10000 * (g // cfg["evaluation"]["rotation_period"]) if split == "train" else 0
            entries = [_entry(p, i, split, offset, cfg["output"]) for p, i in manifests[split]]
            if split == "train" and any(e["mode"] != "dynamic" for e in entries):
                raise InputError("main training plans require fresh dynamic input")
            groups[split].append(_plan(split, entries, cfg["limits"]))
    seen_seed, seen_content = {}, {}
    for split, plans in groups.items():
        for plan in plans:
            for e in plan.to_dict()["entries"]:
                keys = [(seen_seed, (e["input_family_id"], e["seed"]))] if e["seed"] is not None else []
                if e["input_content_id"] is not None:
                    keys.append((seen_content, e["input_content_id"]))
                for seen, key in keys:
                    if key in seen and seen[key] != split:
                        raise InputError(f"cross-split input leakage: {seen[key]} / {split}")
                    seen[key] = split
    return TrainingPlans(tuple(groups["train"]), groups["validation"][0], groups["test"][0])


def parse_training_plan(raw):
    object_fields(raw, ("format", "schema_version", "split", "entries", "lifecycle", "failure_policy", "aggregation",
                        "limits", "dataset_role", "plan_id"), where="training-plan")
    if raw["split"] not in SPLITS or raw["format"] != "fogsim.training-plan" or type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise InputError("unsupported frozen plan")
    if type(raw["entries"]) is not list or not raw["entries"]:
        raise InputError("empty frozen plan")
    from .config import parse_training_config
    # Reuse strict resource validation without I/O.
    parse_training_config(dict(format="fogsim.training-config", schema_version=1, mode="single_routing",
        plans=dict(training="x", validation="y", test="z"), limits=raw["limits"]), Path.cwd())
    ids = set()
    for e in raw["entries"]:
        common = ("run_id", "mode", "seed", "effective_config", "template_digests", "lifecycle", "input_contract",
                  "source_config_sha256", "scene_id", "input_family_id", "input_content_id", "effective_config_sha256")
        object_fields(e, common + (("templates",) if e.get("mode") == "dynamic" else ("input",)), where="plan.entry")
        if type(e["run_id"]) is not str or not e["run_id"].strip() or e["run_id"] in ids:
            raise InputError("invalid frozen run_id")
        ids.add(e["run_id"])
        if e["mode"] == "dynamic":
            cfg = parse_experiment_config(e["effective_config"], base_dir=Path.cwd())
            if cfg.mode != "dynamic" or cfg.schema_version != 2 or cfg.repeat.count != 1 or cfg.source.seed is None or cfg.run.max_events is None:
                raise InputError("invalid frozen dynamic config")
            if e["effective_config"]["source"]["dag_root"] != "@frozen-templates" or cfg.output.dataset_role != SPLITS[raw["split"]]:
                raise InputError("invalid frozen dynamic source/output binding")
            expected_names = {STANDARD_DAX_FILES[i] for i in range(cfg.source.workflow_types.lower, cfg.source.workflow_types.upper+1)}
            if set(e["templates"]) != expected_names:
                raise InputError("invalid frozen template names")
            if e["template_digests"] != {k: content_sha(base64.b64decode(v, validate=True)) for k, v in e["templates"].items()}:
                raise InputError("frozen template digest mismatch")
            if e["seed"] != e["effective_config"]["source"]["seed"]:
                raise InputError("frozen seed mismatch")
            encode_seed(e["seed"])
        elif e["mode"] == "fixed":
            parse_instance(e["input"])
            try:
                RunConfig(**e["effective_config"])
            except TypeError as exc:
                raise InputError("invalid frozen fixed config") from exc
        elif e["mode"] == "replay":
            parse_replay_input(e["input"])
            if e["seed"] != e["input"]["initial_state"]["public_seed"]:
                raise InputError("frozen replay origin seed mismatch")
            cfg = parse_experiment_config(e["effective_config"], base_dir=Path.cwd())
            if cfg.mode != "replay" or cfg.schema_version != 2 or cfg.repeat.count != 1 or cfg.run.max_events is None or cfg.source.purpose != "reuse_inputs" or cfg.source.reference_path is not None:
                raise InputError("invalid controlled replay config")
            if e["effective_config"]["source"]["input_path"] != "@frozen-input" or cfg.output.dataset_role != SPLITS[raw["split"]]:
                raise InputError("invalid frozen replay source/output binding")
        else:
            raise InputError("unknown frozen mode")
        policies = dict(dynamic=("fresh_dynamic_same_plan", "same_input_generation_mechanism"),
            fixed=("fresh_fixed", "explicit_fixed_input"),
            replay=("fresh_replay", "explicit_complete_recorded_input_coverage_checked_at_runtime"))
        if (e["lifecycle"], e["input_contract"]) != policies[e["mode"]]:
            raise InputError("unsupported frozen lifecycle/input contract")
        if e["mode"] == "fixed" and e["seed"] is not None:
            raise InputError("fixed input seed must be null")
        if e["mode"] != "dynamic" and e["template_digests"] != {}:
            raise InputError("invalid explicit input metadata")
        expected = _identities(e)
        if expected != (e["scene_id"], e["input_family_id"], e["input_content_id"]):
            raise InputError("frozen scene/input identity mismatch")
        if e["effective_config_sha256"] != content_sha(canonical(e["effective_config"]).encode()):
            raise InputError("frozen effective config mismatch")
    rebuilt = _plan(raw["split"], raw["entries"], raw["limits"])
    if rebuilt.to_dict() != raw:
        raise InputError("frozen plan policy or identity mismatch")
    return rebuilt
