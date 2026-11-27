"""Independent fogsim-train entry point. B03 supports single routing and dual-tree closed loops."""
import argparse
import json
from pathlib import Path
from fogsim.errors import InputError
from fogsim.rules.factory import prepare_rules
from fogsim.rules.specs import RuleSpec
from .config import load_training_config
from .plans import build_training_plans, parse_training_plan
from .evaluation import evaluate_rule_pair
from .protocols import read_json, write_json, empty_output


def main(argv=None):
    parser = argparse.ArgumentParser(prog="fogsim-train")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="preflight and freeze all plans, without simulation")
    validate.add_argument("--config", required=True)
    validate.add_argument("--output", required=True)
    evaluate = sub.add_parser("evaluate", help="evaluate an explicit fixed rule pair on one frozen plan")
    evaluate.add_argument("--rules", required=True)
    evaluate.add_argument("--plan", required=True)
    evaluate.add_argument("--output", required=True)
    training = sub.add_parser("train", help="single or dual-tree evolution, validation and frozen-rule test")
    training.add_argument("--config", required=True)
    training.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "train":
            from .trainer import train
            from .preflight import preflight_report
            cfg = load_training_config(args.config)
            print(json.dumps(preflight_report(cfg, build_training_plans(cfg))), flush=True)
            result = train(cfg, args.output).to_dict()
            print(json.dumps(result))
            return 0 if result["status"] == "COMPLETED" else 130 if result["status"] == "INCOMPLETE" else 1
        if args.command == "validate":
            cfg = load_training_config(args.config)
            plans = build_training_plans(cfg)
            output = empty_output(args.output)
            write_json(output / "resolved_config.json", cfg.to_dict())
            for g, plan in enumerate(plans.training):
                write_json(output / f"plans/train-{g:04d}.json", plan.to_dict())
            write_json(output / "plans/validation.json", plans.validation.to_dict())
            write_json(output / "plans/test.json", plans.test.to_dict())
            from .preflight import preflight_report
            summary = preflight_report(cfg, plans)
            write_json(output / "preflight.json", summary)
            print(json.dumps(summary))
            return 0
        rules = read_json(args.rules)
        if isinstance(rules, dict) and rules.get("format") == "fogsim.selected-rule":
            from .selection import evaluate_selected_rule
            result = evaluate_selected_rule(args.rules, parse_training_plan(read_json(args.plan)), args.output).to_dict()
            print(json.dumps({k: result[k] for k in ("evaluation_id", "status", "fitness", "completed_runs")}))
            return 0 if result["status"] == "FEASIBLE" else 130 if result["status"] == "INCOMPLETE" else 1
        from fogsim.instances.fixed import object_fields
        object_fields(rules, ("routing", "sequencing"), where="fixed-rule-pair")
        prepared = prepare_rules(RuleSpec.from_mapping("routing", rules["routing"]),
                                 RuleSpec.from_mapping("sequencing", rules["sequencing"]))
        plan = parse_training_plan(read_json(args.plan))
        result = evaluate_rule_pair(prepared, plan, args.output).to_dict()
        print(json.dumps({k: result[k] for k in ("evaluation_id", "status", "fitness", "completed_runs")}))
        return 0 if result["status"] == "FEASIBLE" else 1 if result["status"] == "INFEASIBLE" else 130
    except InputError as exc:
        parser.exit(2, f"configuration/input error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
