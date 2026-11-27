"""S9-B01 evaluation layer; importing it does not require DEAP."""
from .config import parse_training_config, load_training_config
from .plans import build_training_plans, parse_training_plan, TrainingPlan, TrainingPlans
from .evaluation import evaluate_rule_pair, RemoteEvaluationError

__all__ = ["parse_training_config", "load_training_config", "build_training_plans",
    "parse_training_plan", "TrainingPlan", "TrainingPlans", "evaluate_rule_pair", "RemoteEvaluationError"]


def train(config, output_dir, on_progress=None):
    from .trainer import train as run
    return run(config, output_dir, on_progress)


def evaluate_selected_rule(rule_file, plan, output_dir, **kwargs):
    from .selection import evaluate_selected_rule as run
    return run(rule_file, plan, output_dir, **kwargs)

__all__ += ["train", "evaluate_selected_rule"]
