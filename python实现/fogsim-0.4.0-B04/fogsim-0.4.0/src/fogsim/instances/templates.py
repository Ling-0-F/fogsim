"""Immutable topology and diagnostic values, independent of runtime graphs."""
from dataclasses import dataclass
from fogsim.errors import InputError
from fogsim.input_validation import integer, text, sha256, sequence, dependencies
from .identity import task_identities


@dataclass(frozen=True)
class TemplateRef:
    dag_type_id: int | None
    source_sha256: str

    def __post_init__(self):
        if self.dag_type_id is not None:
            integer(self.dag_type_id, "dag_type_id", 0, 19)
        sha256(self.source_sha256, "source_sha256")


@dataclass(frozen=True)
class DagTaskSpec:
    xml_id: str
    java_index: int

    def __post_init__(self):
        text(self.xml_id, "xml_id")
        integer(self.java_index, "java_index")


@dataclass(frozen=True)
class DagDiagnostic:
    code: str
    attribute: str
    declared_value: str
    actual_count: int

    def __post_init__(self):
        text(self.code, "diagnostic.code")
        text(self.attribute, "diagnostic.attribute")
        if type(self.declared_value) is not str:
            raise InputError("diagnostic.declared_value: expected string")
        integer(self.actual_count, "diagnostic.actual_count")


@dataclass(frozen=True)
class DagTemplate:
    dag_type_id: int | None
    source_name: str
    source_sha256: str
    tasks: tuple[DagTaskSpec, ...]
    dependencies: tuple[tuple[str, str], ...]
    diagnostics: tuple[DagDiagnostic, ...] = ()

    def __post_init__(self):
        TemplateRef(self.dag_type_id, self.source_sha256)
        text(self.source_name, "source_name")
        tasks = sequence(self.tasks, DagTaskSpec, "template.tasks", nonempty=True)
        mapping = task_identities(t.xml_id for t in tasks)
        if tuple(t.java_index for t in tasks) != tuple(index for _, index in mapping):
            raise InputError("java_index must equal template task position, starting at 0")
        edges = dependencies(self.dependencies, [t.xml_id for t in tasks], "template.dependencies")
        object.__setattr__(self, "tasks", tasks)
        object.__setattr__(self, "dependencies", edges)
        object.__setattr__(self, "diagnostics", sequence(self.diagnostics, DagDiagnostic, "template.diagnostics"))

    @property
    def ref(self):
        return TemplateRef(self.dag_type_id, self.source_sha256)

    @property
    def task_mapping(self):
        return task_identities(t.xml_id for t in self.tasks)

    def adjacency(self):
        """Return independent ordered ID lists; no runtime Tasks are created."""
        parents = {t.xml_id: [] for t in self.tasks}
        children = {t.xml_id: [] for t in self.tasks}
        for parent, child in self.dependencies:
            children[parent].append(child)
            parents[child].append(parent)
        return ({key: tuple(value) for key, value in parents.items()},
                {key: tuple(value) for key, value in children.items()})
