"""Seed representation only. RNG creation and lifecycle belong to step 2/5."""
from .input_validation import integer, SIGNED64_MIN, SIGNED64_MAX

SEED_ENCODING = "signed64-bits-v1"


def encode_seed(seed: int) -> int:
    return integer(seed, "seed", SIGNED64_MIN, SIGNED64_MAX) & ((1 << 64) - 1)


def rotated_seed(seed: int) -> int:
    """Pure Java-long addition by 10000; does not reset any RNG."""
    bits = (encode_seed(seed) + 10000) & ((1 << 64) - 1)
    return bits if bits <= SIGNED64_MAX else bits - (1 << 64)
