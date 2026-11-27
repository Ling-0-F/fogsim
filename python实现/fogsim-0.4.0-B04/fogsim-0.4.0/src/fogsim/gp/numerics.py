"""Six binary64 operations; deliberately separate from physical-time checks.

Operands are already evaluated binary64 values. The caller must evaluate the
entire left subtree, then the entire right subtree, even for protected divide.
There is no finite-value filtering, epsilon, reassociation or signed-zero fixup.
"""
from enum import Enum


class BinaryFunction(str, Enum):
    ADD = "+"
    SUB = "-"
    MUL = "*"
    DIV = "/"
    MAX = "Max"
    MIN = "Min"


def apply_binary(function: BinaryFunction | str, a: float, b: float) -> float:
    function = BinaryFunction(function)
    if type(a) is not float or type(b) is not float:
        raise TypeError("GP operands must be binary64 floats")
    if function == BinaryFunction.ADD:
        return a + b
    if function == BinaryFunction.SUB:
        return a - b
    if function == BinaryFunction.MUL:
        return a * b
    if function == BinaryFunction.DIV:
        return 1.0 if b == 0.0 else a / b
    if function == BinaryFunction.MAX:
        return a if b < a else b
    return a if b > a else b
