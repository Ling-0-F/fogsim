"""Checks for dynamic derivations; input/config validation stays separate."""
import math
from fogsim.errors import NumericDerivationError


def checked_number(value, operation, *, positive=False):
    # Unexpected programmer types/errors propagate; do not wrap arbitrary exceptions.
    if not math.isfinite(value) or (value <= 0 if positive else value < 0):
        raise NumericDerivationError(operation, value)
    return value
