"""Standard Java type names and frozen, eagerly loaded DAX catalog."""
from dataclasses import dataclass
from pathlib import Path
from fogsim.errors import InputError
from fogsim.experiment_config import DynamicSourceConfig, ExperimentConfig, WorkflowTypeRange
from fogsim.input_validation import integer, sequence, unique
from .dax import parse_dax
from .templates import DagTemplate

STANDARD_DAX_FILES = (
    "CyberShake_30.xml", "Epigenomics_24.xml", "Inspiral_30.xml", "Montage_25.xml", "Sipht_30.xml",
    "CyberShake_50.xml", "Epigenomics_46.xml", "Inspiral_50.xml", "Montage_50.xml", "Sipht_60.xml",
    "CyberShake_100.xml", "Epigenomics_100.xml", "Inspiral_100.xml", "Montage_100.xml", "Sipht_100.xml",
    "CyberShake_1000.xml", "Epigenomics_997.xml", "Inspiral_1000.xml", "Montage_1000.xml", "Sipht_1000.xml",
)


@dataclass(frozen=True)
class DagCatalog:
    dag_root: Path
    workflow_types: WorkflowTypeRange
    templates: tuple[DagTemplate, ...]

    def __post_init__(self):
        if not isinstance(self.dag_root, Path) or not self.dag_root.is_absolute():
            raise InputError("catalog.dag_root: expected absolute Path")
        if type(self.workflow_types) is not WorkflowTypeRange:
            raise InputError("catalog.workflow_types: expected WorkflowTypeRange")
        templates = sequence(self.templates, DagTemplate, "catalog.templates", True)
        ids = tuple(t.dag_type_id for t in templates)
        unique(ids, "catalog type IDs")
        if ids != tuple(range(self.workflow_types.lower, self.workflow_types.upper + 1)):
            raise InputError("catalog templates must exactly cover the ordered requested type range")
        object.__setattr__(self, "templates", templates)

    def template(self, dag_type_id):
        integer(dag_type_id, "dag_type_id", self.workflow_types.lower, self.workflow_types.upper)
        return self.templates[dag_type_id - self.workflow_types.lower]


def load_dax_catalog(config: DynamicSourceConfig | ExperimentConfig) -> DagCatalog:
    if type(config) is ExperimentConfig:
        if config.mode != "dynamic":
            raise InputError("DAX catalog requires dynamic config")
        config = config.source
    if type(config) is not DynamicSourceConfig:
        raise InputError("DAX catalog requires DynamicSourceConfig or dynamic ExperimentConfig")
    types = config.workflow_types
    # Finish every requested parse before publishing the catalog; no RNG exists here.
    templates = tuple(parse_dax(config.dag_root / STANDARD_DAX_FILES[i], dag_type_id=i)
                      for i in range(types.lower, types.upper + 1))
    return DagCatalog(config.dag_root, types, templates)
