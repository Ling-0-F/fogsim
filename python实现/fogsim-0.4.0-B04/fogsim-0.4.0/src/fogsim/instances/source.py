"""A source returns complete inputs and has no registration/scheduling authority."""
from typing import Protocol
from .generated import WorkflowInput, GenerationCause
from .generation import generate_workflow_input


class WorkflowSource(Protocol):
    def generate(self, cause: GenerationCause, *, candidate_id: int) -> WorkflowInput: ...


class RandomWorkflowSource:
    def __init__(self, inputs, environment):
        self.inputs = inputs
        self.environment = environment

    def generate(self, cause, *, candidate_id):
        return generate_workflow_input(self.inputs, self.environment, cause, candidate_id=candidate_id)
