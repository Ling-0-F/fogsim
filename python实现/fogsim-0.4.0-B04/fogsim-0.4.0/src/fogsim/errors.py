"""Expected input, API and simulation errors; programming bugs are not swallowed."""

class InputError(ValueError):
    pass


class StateError(RuntimeError):
    pass


class EngineUsageError(RuntimeError):
    pass


class NumericDerivationError(StateError):
    """A sampled/derived dynamic value cannot enter the input or runtime model."""
    reason_code = "NUMERIC_DERIVATION_ERROR"

    def __init__(self, operation, value):
        self.operation = operation
        self.value = value
        super().__init__(f"{self.reason_code}: {operation}: invalid value {value!r}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise StateError(message)


class SimulationFailure(StateError):
    def __init__(self, reason_code, message):
        self.reason_code = reason_code
        super().__init__(message)


class PreparationError(RuntimeError):
    """Expected preparation failure; the failed round and its input state survive."""
    def __init__(self, context, result):
        self.context, self.result = context, result
        self.engine = context.engine
        self.reason_code = result.reason_code
        super().__init__(result.reason)
