from dataclasses import replace
from pathlib import Path
import sys

from fogsim.rules.factory import prepare_rules
from fogsim.rules.specs import RuleSpec
from fogsim.rules.contexts import RoutingContext, SequencingContext
from fogsim.model.resource import Server, ResourceType
from fogsim.model.task import TaskOption
from ..feature_fixtures import fixture


def prepared(route="PT", sequence="(- 0 PT)"):
    return prepare_rules(RuleSpec("routing", "gp", expression=route),
                         RuleSpec("sequencing", "gp", expression=sequence))


def pair(role):
    f = fixture(ResourceType.EDGE, role)
    if role == "routing":
        other = Server("S1", 1, ResourceType.EDGE)
        second = TaskOption(f.option.task, other, 7.0, 0.0, 0.0)
        f.option.task.options.append(second)
        view = replace(f.context.view, resources=(*f.context.view.resources, other))
        ctx = RoutingContext(f.option.task, tuple(f.option.task.options), view)
    else:
        # Equal metadata isolates numeric selection and stable traversal.
        for w in f.context.view.active_workflows:
            w.release_time = 5.0
            w.owner_device = f.workflow.owner_device
        f.other_workflow.id = 9
        ctx = f.context
    return f, ctx


def dynamic_config(tmp_path, **kwargs):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "unit"))
    from dynamic_helpers import config
    return config(tmp_path, **kwargs)


def gp_dynamic(tmp_path, *, route="PT", sequence="(- 0 PT)", **kwargs):
    from fogsim.experiment_config import RuleConfig
    cfg = dynamic_config(tmp_path, **kwargs)
    return replace(cfg, schema_version=2, run=replace(cfg.run,
        routing_rule=RuleConfig("gp", expression=route),
        sequencing_rule=RuleConfig("gp", expression=sequence)))
